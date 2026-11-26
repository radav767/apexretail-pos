"""Bounded variant/tier/name acceptance; synthetic rollback database only."""
import unittest
from uuid import uuid4
from decimal import Decimal
from unittest.mock import patch
from sqlalchemy import select,func
from fastapi import HTTPException
from app.models import (Product,ProductVariant,VariantInventoryBalance,InventoryBalance,Customer,ProductPriceLevel,SaleItem,Sale,CommerceOrderItem,InventoryMovement,CompanySetting)
from app.business_operations.schema import OrderInput,OrderItemInput,QuotationRevision
from app.business_operations.pricing_review import PricingReview,review
from app.business_operations.saved_pricing import SavePricing,save
from app.business_operations.quotation_revisions import revise
import test_phase11_saved_quotation_pricing as fixture

class CatalogAcceptanceTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=fixture.SavedPricingTests.asyncSetUp
    cleanup=fixture.SavedPricingTests.cleanup
    action=fixture.SavedPricingTests.action
    send=fixture.SavedPricingTests.send
    accept=fixture.SavedPricingTests.accept
    payment=fixture.SavedPricingTests.payment
    async def configured(self):
        self.customer=Customer(company_id=self.company.id,customer_code='BOUND',name='Synthetic tier customer',price_level_name='Bulk')
        self.first=ProductVariant(company_id=self.company.id,product_id=self.product.id,name='Red',selling_price=14,cost_price=2)
        self.second=ProductVariant(company_id=self.company.id,product_id=self.product.id,name='Blue',selling_price=15,cost_price=3)
        self.other=Product(company_id=self.company.id,name='Other position',selling_price=5,cost_price=1,tax_exempt=True,stock_qty=20)
        self.level=ProductPriceLevel(company_id=self.company.id,product_id=self.product.id,name='Bulk',price=10,minimum_quantity=6)
        self.db.add_all([self.customer,self.first,self.second,self.other,self.level]);await self.db.flush()
        for variant,qty in [(self.first,60),(self.second,40)]:self.db.add(VariantInventoryBalance(company_id=self.company.id,shop_id=self.shop.id,branch_id=self.branch.id,product_id=self.product.id,variant_id=variant.id,quantity=qty,reorder_level=0))
        self.db.add(InventoryBalance(company_id=self.company.id,shop_id=self.shop.id,branch_id=self.branch.id,product_id=self.other.id,quantity=20,reorder_level=0))
        self.product.tax_rate=15;await self.db.commit()
        self.order=await self.svc.create_order(OrderInput(branch_id=self.branch.id,device_id=self.device.id,customer_id=self.customer.id,kind='quotation',request_id=uuid4()))
        for product,variant,quantity in [(self.product,self.first,6),(self.product,self.second,3),(self.other,None,1)]:
            self.order=await self.svc.add_item(self.order['id'],OrderItemInput(version=self.order['version'],product_id=product.id,variant_id=variant.id if variant else None,quantity=quantity))
    async def saved(self):
        lines=[]
        for i in self.order['items']:
            if Decimal(i['quantity'])<=0:continue
            lines.append({'item_id':i['id'],'quantity':i['quantity'],'unit':i['unit'],'discount':1 if i['variant_id']==self.first.id else Decimal('.5') if i['variant_id']==self.second.id else 0})
        proposal=PricingReview(version=self.order['version'],lines=lines,sale_discount=2)
        priced=await review(self.svc,self.order['id'],proposal)
        result=await save(self.svc,self.order['id'],SavePricing(**proposal.model_dump(),request_id=uuid4(),expected_total=priced['total'],expected_display_total=priced['display_total']))
        self.order=await self.svc.order_out(await self.svc.order(self.order['id']));return result
    async def test_multiple_variants_have_independent_tiers_tax_cost_stock_and_exact_replay(self):
        await self.configured();saved=await self.saved();plan=saved['quotation_pricing'];await self.accept()
        command=self.payment().model_copy(update={'payment':self.payment().payment.model_copy(update={'amount_received':Decimal(200)})})
        result=await self.svc.settle(self.order['id'],command);again=await self.svc.settle(self.order['id'],command);self.assertEqual(result['sale_id'],again['sale_id'])
        rows=(await self.db.execute(select(SaleItem).where(SaleItem.sale_id==result['sale_id']))).scalars().all();by={r.variant_id:r for r in rows}
        self.assertEqual(by[self.first.id].unit_price,10);self.assertEqual(by[self.first.id].price_level_name_snapshot,'Bulk');self.assertEqual(by[self.second.id].unit_price,15);self.assertIsNone(by[self.second.id].price_level_name_snapshot)
        sale=await self.db.get(Sale,result['sale_id']);self.assertEqual(sale.total_amount,Decimal(plan['total']));self.assertEqual(sum(r.line_total+r.tax_amount for r in rows),sale.total_amount);self.assertEqual(sum(r.line_cost for r in rows),22)
        quantities=dict((await self.db.execute(select(VariantInventoryBalance.variant_id,VariantInventoryBalance.quantity).where(VariantInventoryBalance.product_id==self.product.id))).all());self.assertEqual(quantities,{self.first.id:54,self.second.id:37})
        self.assertEqual((await self.db.execute(select(func.count(InventoryMovement.id)).where(InventoryMovement.company_id==self.company.id))).scalar_one(),3)
    async def test_name_changes_refresh_only_drafts_and_conflict_after_acceptance(self):
        await self.configured();self.product.name='Renamed source';self.first.name='Crimson';await self.db.commit();await self.saved()
        self.assertIn('Renamed source (Crimson)',[r['name'] for r in self.order['items']]);await self.accept();frozen=self.order['quotation_terms']
        self.first.name='Scarlet';await self.db.commit()
        with self.assertRaises(HTTPException) as error:await self.svc.settle(self.order['id'],self.payment())
        self.assertEqual(error.exception.status_code,409)
        self.assertEqual((await self.svc.order_out(await self.svc.order(self.order['id'])))['quotation_terms'],frozen)
        self.order=await revise(self.svc,self.order['id'],QuotationRevision(version=self.order['version'],request_id=uuid4(),reason='Synthetic catalogue revision'))
        await self.saved();self.assertIn('Renamed source (Scarlet)',[r['name'] for r in self.order['items']])
    async def test_tier_label_change_same_price_and_locked_label_race_conflict(self):
        await self.configured();await self.saved();await self.accept()
        self.customer.price_level_name='Other';self.db.add(ProductPriceLevel(company_id=self.company.id,product_id=self.product.id,name='Other',price=10,minimum_quantity=6));await self.db.commit()
        with self.assertRaises(HTTPException) as error:await self.svc.settle(self.order['id'],self.payment())
        self.assertEqual(error.exception.status_code,409)
    async def test_legacy_plan_without_optional_tier_label_is_not_rewritten(self):
        await self.configured();await self.saved()
        row=await self.svc.order(self.order['id']);plan={**row.quotation_pricing,'items':[{k:v for k,v in i.items() if k not in {'price_level_name','track_inventory'}} for i in row.quotation_pricing['items']]};row.quotation_pricing=plan;await self.db.commit()
        await self.accept();self.assertTrue(all('price_level_name' not in i for i in self.order['quotation_terms']['items']))

    async def test_catalog_drift_rejected_without_movement_or_sale_proof(self):
        await self.configured();await self.saved();await self.accept()
        cases=[(self.first,'cost_price',9),(self.first,'active',False),(self.level,'price',9),(self.product,'tax_rate',19),(self.product,'track_inventory',False)]
        for entity,field,value in cases:
            previous=getattr(entity,field);setattr(entity,field,value);await self.db.commit()
            with self.assertRaises(HTTPException) as error:await self.svc.settle(self.order['id'],self.payment())
            self.assertEqual(error.exception.status_code,409,(field,error.exception.detail))
            setattr(entity,field,previous);await self.db.commit()
        self.assertEqual((await self.db.execute(select(func.count(InventoryMovement.id)).where(InventoryMovement.company_id==self.company.id))).scalar_one(),0)
    async def test_unrepresentable_foreign_tender_rejects_before_stock_or_proof(self):
        from datetime import datetime,timezone,timedelta
        from app.models import CompanyCurrency,CurrencyExchangeRate,SaleCommandReceipt
        await self.configured()
        settings=(await self.db.execute(select(CompanySetting).where(CompanySetting.company_id==self.company.id))).scalar_one();settings.multi_currency_enabled=True
        cur=CompanyCurrency(company_id=self.company.id,code='SY0',display_name='Synthetic zero',symbol='S0',decimal_places=0,active=True,is_base=False);self.db.add(cur);await self.db.flush();self.db.add(CurrencyExchangeRate(company_id=self.company.id,currency_id=cur.id,currency_code='SY0',foreign_units_per_base=2,effective_at=datetime.now(timezone.utc)-timedelta(days=1),created_by_user_id=self.user.id));await self.db.commit()
        proposal=PricingReview(version=self.order['version'],currency_code='SY0',lines=[{'item_id':i['id'],'quantity':i['quantity'],'unit':i['unit']} for i in self.order['items']]);priced=await review(self.svc,self.order['id'],proposal);await save(self.svc,self.order['id'],SavePricing(**proposal.model_dump(),request_id=uuid4(),expected_total=priced['total'],expected_display_total=priced['display_total']));self.order=await self.svc.order_out(await self.svc.order(self.order['id']));await self.accept()
        command=self.payment().model_copy(update={'payment':self.payment().payment.model_copy(update={'tendered_amount_original':Decimal('1000.0001')})})
        result=await self.client.post('/api/operations/orders/'+str(self.order['id'])+'/settle',json=command.model_dump(mode='json'));self.assertEqual(result.status_code,422,result.text)
        self.assertIsNone(await self.db.get(SaleCommandReceipt,self.order['id']))
        self.assertEqual((await self.db.execute(select(func.count(InventoryMovement.id)).where(InventoryMovement.company_id==self.company.id))).scalar_one(),0)
    async def test_recipe_repeated_position_and_non_two_decimal_base_remain_gated(self):
        from sqlalchemy import update
        from app.models import CompanyCurrency
        await self.configured();pid=self.product.id;company=self.company.id
        self.order=await self.svc.add_item(self.order['id'],OrderItemInput(version=self.order['version'],product_id=pid,variant_id=self.first.id,quantity=1))
        body={'version':self.order['version'],'lines':[{'item_id':str(i['id']),'quantity':str(i['quantity']),'unit':i['unit']} for i in self.order['items']]}
        async def denied(fragment):
            review_response=await self.client.post('/api/operations/orders/'+str(self.order['id'])+'/pricing/review',json=body);self.assertEqual(review_response.status_code,200,review_response.text);priced=review_response.json()
            result=await self.client.post('/api/operations/orders/'+str(self.order['id'])+'/quotation-pricing',json={**body,'request_id':str(uuid4()),'expected_total':priced['total'],'expected_display_total':priced['display_total']});self.assertEqual(result.status_code,409,result.text);self.assertIn(fragment,result.json()['detail'])
        await denied('repeated')
        await self.db.execute(update(Product).where(Product.id==pid).values(product_type='bundle'));await self.db.commit();await denied('recipe')
        await self.db.execute(update(Product).where(Product.id==pid).values(product_type='standard'));await self.db.execute(update(CompanyCurrency).where(CompanyCurrency.company_id==company,CompanyCurrency.is_base.is_(True)).values(decimal_places=0));await self.db.commit();await denied('Non-two-decimal')
        self.assertEqual((await self.db.execute(select(func.count(InventoryMovement.id)).where(InventoryMovement.company_id==company))).scalar_one(),0)

    async def test_removed_position_is_retained_but_not_priced_or_moved(self):
        from app.business_operations.schema import ItemUpdate
        await self.configured();await self.saved();removed=next(i for i in self.order['items'] if i['product_id']==self.other.id)
        self.order=await self.svc.edit_item(self.order['id'],removed['id'],ItemUpdate(version=self.order['version'],quantity=0,notes='Synthetic removed position'))
        plan=(await self.saved())['quotation_pricing'];self.assertEqual(len(plan['items']),2);await self.accept()
        command=self.payment();command=command.model_copy(update={'payment':command.payment.model_copy(update={'amount_received':Decimal(200)})});result=await self.svc.settle(self.order['id'],command)
        self.assertEqual((await self.db.execute(select(func.count(SaleItem.id)).where(SaleItem.sale_id==result['sale_id']))).scalar_one(),2)
        self.assertEqual((await self.db.execute(select(InventoryBalance.quantity).where(InventoryBalance.product_id==self.other.id))).scalar_one(),20)
        self.assertEqual((await self.db.get(CommerceOrderItem,removed['id'])).quantity,0)

    async def test_tier_eligibility_is_revalidated_after_initial_selection(self):
        from app.sales.repository import SalesRepository
        await self.configured();await self.saved();await self.accept();company=self.company.id
        native=SalesRepository.get_price_level
        async def became_inactive(repo,*args):
            result=await native(repo,*args)
            if result:result.active=False;await repo.db.flush([result])
            return result
        with patch.object(SalesRepository,'get_price_level',became_inactive):
            with self.assertRaises(HTTPException) as error:await self.svc.settle(self.order['id'],self.payment())
        self.assertEqual(error.exception.status_code,409);self.assertIn('tier changed',error.exception.detail)
        self.assertEqual((await self.db.execute(select(func.count(InventoryMovement.id)).where(InventoryMovement.company_id==company))).scalar_one(),0)
