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
