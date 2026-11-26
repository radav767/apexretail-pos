"""Synthetic saved plans: draft effects, exact recovery and native conversion."""
import unittest
from decimal import Decimal
from uuid import uuid4
from unittest.mock import patch
from sqlalchemy import select,func,text
from sqlalchemy.exc import DBAPIError
from fastapi import HTTPException
from app.core.config import get_settings
from app.models import Sale,SaleItem,InventoryMovement,CompanySubscription,CommerceOrder
from app.business_operations.saved_pricing import SavePricing,save
from app.business_operations.pricing_review import PricingReview,review
import test_phase11_quotations as fixtures

class SavedPricingTests(unittest.IsolatedAsyncioTestCase):
    cleanup=fixtures.QuotationTests.cleanup
    action=fixtures.QuotationTests.action
    send=fixtures.QuotationTests.send
    accept=fixtures.QuotationTests.accept
    payment=fixtures.QuotationTests.payment
    async def asyncSetUp(self):
        await fixtures.QuotationTests.asyncSetUp(self)
        self.mode=patch('app.business_operations.saved_pricing.get_settings',return_value=get_settings().model_copy(update={'quotation_pricing_mode':'test'}));self.mode.start();self.addCleanup(self.mode.stop)
        self.product.purchase_unit='box';self.product.units_per_purchase=12;self.product.cost_price=2;await self.db.commit()
    async def plan(self):
        proposed=PricingReview(version=self.order['version'],lines=[{'item_id':self.order['items'][0]['id'],'quantity':'.5','unit':'box','discount':1}],sale_discount=2)
        priced=await review(self.svc,self.order['id'],proposed)
        command=SavePricing(**proposed.model_dump(),request_id=uuid4(),expected_total=priced['total'],expected_display_total=priced['display_total'])
        result=await save(self.svc,self.order['id'],command)
        self.order=await self.svc.order_out(await self.svc.order(self.order['id']))
        return command,result
    async def test_api_plan_accept_convert_exact_recovery_and_stock_once(self):
        command,result=await self.plan();self.assertEqual(result['quotation_pricing']['total'],'69.00');self.assertEqual(self.balance.quantity,100)
        response=await self.client.post(f"/api/operations/orders/{self.order['id']}/quotation-pricing",json=command.model_dump(mode='json'))
        self.assertEqual(response.status_code,200,response.text);self.assertEqual(response.json(),result);self.assertNotIn('cost',result['quotation_pricing']['items'][0]);self.assertNotIn('cost',self.order['quotation_pricing']['items'][0])
        await self.accept();self.assertEqual(self.balance.quantity,100)
        payment=self.payment();out=await self.svc.settle(self.order['id'],payment)
        sale=await self.db.get(Sale,out['sale_id']);self.assertEqual(sale.total_amount,69);self.assertEqual(sale.discount_amount,3);self.assertEqual(self.balance.quantity,94)
        item=(await self.db.execute(select(SaleItem).where(SaleItem.sale_id==sale.id))).scalar_one();self.assertEqual(item.quantity,6);self.assertEqual(item.unit_cost,2)
        sub=(await self.db.execute(select(CompanySubscription).where(CompanySubscription.company_id==self.company.id))).scalar_one();sub.status='expired';await self.db.commit()
        with patch('app.business_operations.saved_pricing.get_settings',return_value=get_settings()):
            again=await self.svc.settle(self.order['id'],payment)
        self.assertEqual(out['sale_id'],again['sale_id']);self.assertEqual(self.balance.quantity,94)
        self.assertEqual((await self.db.execute(select(func.count(InventoryMovement.id)).where(InventoryMovement.company_id==self.company.id))).scalar_one(),1)
    async def test_changed_request_and_expectation_fail_without_draft_or_stock_effect(self):
        command,result=await self.plan();version=self.order['version']
        with self.assertRaises(HTTPException) as error:await save(self.svc,self.order['id'],command.model_copy(update={'expected_total':Decimal('1')}))
        self.assertEqual(error.exception.status_code,409)
        current=await self.svc.order_out(await self.svc.order(self.order['id']));self.assertEqual(current['version'],version);self.assertEqual(current['quotation_pricing'],result['quotation_pricing']);await self.db.refresh(self.balance);self.assertEqual(self.balance.quantity,100)
    async def test_catalog_change_denies_conversion_without_stock(self):
        await self.plan();await self.accept();self.product.units_per_purchase=10;await self.db.commit()
        with self.assertRaises(HTTPException) as error:await self.svc.settle(self.order['id'],self.payment())
        self.assertEqual(error.exception.status_code,409)
        self.assertEqual((await self.db.execute(select(func.count(Sale.id)).where(Sale.company_id==self.company.id))).scalar_one(),1)
    async def test_conversion_failure_rolls_back_native_stock_and_proof(self):
        await self.plan();await self.accept();oid=self.order['id'];company=self.company.id
        with patch('app.business_operations.quotations.validate_sale',side_effect=HTTPException(409,'synthetic final comparison failure')):
            with self.assertRaises(HTTPException):await self.svc.settle(oid,self.payment())
        row=await self.db.get(CommerceOrder,oid);self.assertIsNone(row.sale_id);self.assertEqual(row.status,'open')
        self.assertEqual((await self.db.execute(select(func.count(InventoryMovement.id)).where(InventoryMovement.company_id==company))).scalar_one(),0)
    async def test_accepted_pricing_and_converted_sale_evidence_frozen(self):
        await self.plan();await self.accept();out=await self.svc.settle(self.order['id'],self.payment())
        for sql,params in [("UPDATE commerce_orders SET quotation_pricing='{}'::jsonb WHERE id=:id",{'id':self.order['id']}),("UPDATE sales SET total_amount=1 WHERE id=:id",{'id':out['sale_id']}),("UPDATE commerce_orders SET sale_id=NULL WHERE id=:id",{'id':self.order['id']})]:
            with self.assertRaises(DBAPIError):
                async with self.db.begin_nested():await self.db.execute(text(sql),params)
    async def test_currency_plan_conversion_and_cumulative_returns_use_original_frozen_fx(self):
        from datetime import datetime,timedelta,timezone
        from app.models import CompanyCurrency,CurrencyExchangeRate,CompanySetting
        setting=(await self.db.execute(select(CompanySetting).where(CompanySetting.company_id==self.company.id))).scalar_one();setting.multi_currency_enabled=True
        currency=CompanyCurrency(company_id=self.company.id,code='JPY',display_name='Synthetic yen',symbol='JPY',decimal_places=0,active=True,is_base=False);self.db.add(currency);await self.db.flush()
        self.db.add(CurrencyExchangeRate(company_id=self.company.id,currency_id=currency.id,currency_code='JPY',foreign_units_per_base=Decimal('150.05'),effective_at=datetime.now(timezone.utc)-timedelta(days=1),created_by_user_id=self.user.id));await self.db.commit()
        proposed=PricingReview(version=self.order['version'],lines=[{'item_id':self.order['items'][0]['id'],'quantity':'.5','unit':'box','discount':1}],sale_discount=2,currency_code='JPY')
        priced=await review(self.svc,self.order['id'],proposed);command=SavePricing(**proposed.model_dump(),request_id=uuid4(),expected_total=priced['total'],expected_display_total=priced['display_total'])
        saved=await save(self.svc,self.order['id'],command);self.assertEqual(saved['quotation_pricing']['display_total'],'10353')
        self.order=await self.svc.order_out(await self.svc.order(self.order['id']));await self.accept()
        from app.workflows.documents import DocumentService
        from types import SimpleNamespace
        _,snapshot=await DocumentService(self.db,self.owner).snapshot(SimpleNamespace(source_kind='quotation',company_id=self.company.id,source_id=self.order['id']))
        self.assertEqual(snapshot['totals']['Display total'],'10353');self.assertIn('.5 box',snapshot['rows'][0]['quantity']);self.assertIn('69.00 net',snapshot['rows'][0]['amount'])
        from app.sales.repository import SalesRepository
        from app.sales.service import SalesService
        from app.sales.schema import RefundCreate,RefundItemCreate
        payment=self.payment();payment=payment.model_copy(update={'payment':payment.payment.model_copy(update={'tendered_amount_original':Decimal(12000)})})
        out=await self.svc.settle(self.order['id'],payment);sale=await self.db.get(Sale,out['sale_id']);self.assertEqual(sale.payment_amount_original,10353);self.assertEqual(sale.change_amount_original,1647)
        item=(await self.db.execute(select(SaleItem).where(SaleItem.sale_id==sale.id))).scalar_one()
        currency.active=False;currency.decimal_places=4;setting.multi_currency_enabled=False;setting.currency_config_version+=1;await self.db.commit()
        refund=RefundCreate(company_id=self.company.id,original_sale_id=sale.id,branch_id=self.branch.id,device_id=self.device.id,request_id=uuid4(),reason='Synthetic frozen FX return',items=[RefundItemCreate(sale_item_id=item.id,quantity=1)])
        service=SalesService(SalesRepository(self.db));first=await service.create_refund(refund,actor=self.owner);self.assertEqual(first.payment_amount_original,-1726)
        again=await service.create_refund(refund,actor=self.owner);self.assertEqual(first.id,again.id)
        final=await service.create_refund(refund.model_copy(update={'request_id':uuid4(),'items':[RefundItemCreate(sale_item_id=item.id,quantity=5)]}),actor=self.owner)
        self.assertEqual(final.payment_amount_original,-8627);self.assertEqual(first.total_amount+final.total_amount,-69);self.assertEqual(final.exchange_rate_snapshot,Decimal('150.05'));self.assertEqual(final.exchange_rate_id,sale.exchange_rate_id)
        await self.db.execute(text('SET CONSTRAINTS ALL IMMEDIATE'))
        with self.assertRaises(DBAPIError):
            async with self.db.begin_nested():await self.db.execute(text('UPDATE sales SET payment_amount_original=-1 WHERE id=:id'),{'id':final.id})
        await self.db.refresh(self.balance);self.assertEqual(self.balance.quantity,100)

    async def test_draft_edit_invalidates_saved_plan_and_foreign_order_denied(self):
        from app.business_operations.schema import OrderItemInput
        await self.plan()
        self.order=await self.svc.add_item(self.order['id'],OrderItemInput(version=self.order['version'],product_id=self.product.id,quantity=1))
        with self.assertRaises(HTTPException) as error:await self.send()
        self.assertEqual(error.exception.status_code,409);self.assertIn('resave',error.exception.detail)
        denied=await self.client.post(f"/api/operations/orders/{uuid4()}/quotation-pricing",json={'version':1,'request_id':str(uuid4()),'expected_total':'1','expected_display_total':'1','lines':[{'item_id':str(uuid4()),'quantity':1,'unit':'each'}]})
        self.assertEqual(denied.status_code,404)
    async def test_aggregate_tax_residuals_conserve_saved_total(self):
        from app.models import Product,InventoryBalance,CompanySetting
        from app.business_operations.schema import OrderItemInput
        self.product.selling_price=Decimal('.05');self.product.tax_rate=15
        settings=(await self.db.execute(select(CompanySetting).where(CompanySetting.company_id==self.company.id))).scalar_one();settings.tax_rate=15;settings.tax_inclusive=False
        await self.db.commit()
        # Existing line quantity is replaced explicitly in the proposed saved plan.
        for n in range(2):
            p=Product(company_id=self.company.id,name='Synthetic penny '+str(n),selling_price=Decimal('.05'),cost_price=0,tax_rate=15,stock_qty=10)
            self.db.add(p);await self.db.flush();self.db.add(InventoryBalance(company_id=self.company.id,shop_id=self.shop.id,branch_id=self.branch.id,product_id=p.id,quantity=10,reorder_level=0));await self.db.commit()
            self.order=await self.svc.add_item(self.order['id'],OrderItemInput(version=self.order['version'],product_id=p.id,quantity=1))
        proposed=PricingReview(version=self.order['version'],lines=[{'item_id':i['id'],'quantity':1,'unit':'each'} for i in self.order['items']])
        priced=await review(self.svc,self.order['id'],proposed);self.assertEqual(priced['total'],'0.17')
        saved=await save(self.svc,self.order['id'],SavePricing(**proposed.model_dump(),request_id=uuid4(),expected_total=priced['total'],expected_display_total=priced['display_total']))
        self.order=await self.svc.order_out(await self.svc.order(self.order['id']));await self.accept();out=await self.svc.settle(self.order['id'],self.payment())
        sale=await self.db.get(Sale,out['sale_id']);self.assertEqual(sale.total_amount,Decimal('.17'));self.assertEqual(sale.tax_amount,Decimal('.02'))
        rows=(await self.db.execute(select(SaleItem).where(SaleItem.sale_id==sale.id))).scalars().all();self.assertEqual(sum(r.tax_amount for r in rows),Decimal('.02'))
        expected={r['product_id']:Decimal(r['tax']) for r in saved['quotation_pricing']['items']};self.assertEqual({str(r.product_id):r.tax_amount for r in rows},expected)
    async def test_current_role_revocation_and_disabled_mode_before_save_replay(self):
        command,_=await self.plan();body=command.model_dump(mode='json');url=f"/api/operations/orders/{self.order['id']}/quotation-pricing"
        with patch('app.business_operations.saved_pricing.get_settings',return_value=get_settings()):
            recovered=await self.client.post(url,json=body);self.assertEqual(recovered.status_code,200,recovered.text)
        self.user.session_version+=1;await self.db.commit()
        denied=await self.client.post(url,json=body);self.assertEqual(denied.status_code,401,denied.text)
    async def test_role_cannot_save_pricing_even_with_valid_order_and_request(self):
        command,_=await self.plan()
        with self.assertRaises(HTTPException) as error:await save(self.waiter_svc,self.order['id'],command.model_copy(update={'request_id':uuid4(),'version':self.order['version']}))
        self.assertEqual(error.exception.status_code,403)
    async def test_partial_final_base_returns_conserve_discount_tax_and_stock(self):
        from app.sales.repository import SalesRepository
        from app.sales.service import SalesService
        from app.sales.schema import RefundCreate,RefundItemCreate
        await self.plan();await self.accept();out=await self.svc.settle(self.order['id'],self.payment())
        rows=(await self.db.execute(select(SaleItem).where(SaleItem.sale_id==out['sale_id']))).scalars().all();item=rows[0]
        refund=RefundCreate(company_id=self.company.id,original_sale_id=out['sale_id'],branch_id=self.branch.id,device_id=self.device.id,request_id=uuid4(),reason='Synthetic saved quote return',items=[RefundItemCreate(sale_item_id=item.id,quantity=1)])
        service=SalesService(SalesRepository(self.db));first=await service.create_refund(refund,actor=self.owner)
        again=await service.create_refund(refund,actor=self.owner);self.assertEqual(first.id,again.id)
        final=await service.create_refund(refund.model_copy(update={'request_id':uuid4(),'items':[RefundItemCreate(sale_item_id=item.id,quantity=5)]}),actor=self.owner)
        self.assertEqual(first.total_amount+final.total_amount,Decimal('-69'));await self.db.refresh(self.balance);self.assertEqual(self.balance.quantity,100)
    async def test_configured_customer_tier_and_credit_budget_use_base_quantity(self):
        from app.models import Customer,ProductPriceLevel,CreditReceivable
        from app.business_operations.schema import OrderInput,OrderItemInput
        customer=Customer(company_id=self.company.id,customer_code='SYNTH-TIER',name='Synthetic tier customer',price_level_name='Bulk',credit_enabled=True,credit_limit=100,credit_terms_days=0)
        self.db.add(customer);self.db.add(ProductPriceLevel(company_id=self.company.id,product_id=self.product.id,name='Bulk',price=10,minimum_quantity=6));await self.db.commit()
        self.order=await self.svc.create_order(OrderInput(branch_id=self.branch.id,device_id=self.device.id,kind='quotation',customer_id=customer.id,request_id=uuid4()))
        self.order=await self.svc.add_item(self.order['id'],OrderItemInput(version=self.order['version'],product_id=self.product.id,quantity=2))
        _,result=await self.plan();self.assertEqual(result['quotation_pricing']['total'],'57.00');await self.accept()
        payment=self.payment();payment=payment.model_copy(update={'payment':payment.payment.model_copy(update={'payment_method':'credit','amount_received':None})})
        out=await self.svc.settle(self.order['id'],payment);sale=await self.db.get(Sale,out['sale_id']);self.assertEqual(sale.total_amount,57)
        receivable=(await self.db.execute(select(CreditReceivable).where(CreditReceivable.sale_id==sale.id))).scalar_one();self.assertEqual(receivable.original_amount,57);self.assertEqual(self.balance.quantity,94)
    async def test_four_decimal_foreign_conversion_through_api_and_original_refund(self):
        from datetime import datetime,timedelta,timezone
        from app.models import CompanyCurrency,CurrencyExchangeRate,CompanySetting
        from app.sales.schema import RefundCreate,RefundItemCreate
        setting=(await self.db.execute(select(CompanySetting).where(CompanySetting.company_id==self.company.id))).scalar_one();setting.multi_currency_enabled=True
        currency=CompanyCurrency(company_id=self.company.id,code='SYN4',display_name='Synthetic four places',symbol='S4',decimal_places=4,active=True,is_base=False);self.db.add(currency);await self.db.flush()
        self.db.add(CurrencyExchangeRate(company_id=self.company.id,currency_id=currency.id,currency_code='SYN4',foreign_units_per_base=Decimal('1.23456789'),effective_at=datetime.now(timezone.utc)-timedelta(days=1),created_by_user_id=self.user.id));await self.db.commit()
        proposal=PricingReview(version=self.order['version'],lines=[{'item_id':self.order['items'][0]['id'],'quantity':'.5','unit':'box','discount':1}],sale_discount=2,currency_code='SYN4')
        priced=await review(self.svc,self.order['id'],proposal);self.assertEqual(priced['display_total'],'85.1852')
        await save(self.svc,self.order['id'],SavePricing(**proposal.model_dump(),request_id=uuid4(),expected_total=priced['total'],expected_display_total=priced['display_total']))
        self.order=await self.svc.order_out(await self.svc.order(self.order['id']));await self.accept()
        payment=self.payment();payment=payment.model_copy(update={'payment':payment.payment.model_copy(update={'tendered_amount_original':Decimal(100)})})
        response=await self.client.post(f"/api/operations/orders/{self.order['id']}/settle",json=payment.model_dump(mode='json'));self.assertEqual(response.status_code,200,response.text);sid=response.json()['sale_id']
        again=await self.client.post(f"/api/operations/orders/{self.order['id']}/settle",json=payment.model_dump(mode='json'));self.assertEqual(again.status_code,200,again.text);self.assertEqual(again.json()['sale_id'],sid)
        item=(await self.db.execute(select(SaleItem).where(SaleItem.sale_id==sid))).scalar_one()
        refund=RefundCreate(company_id=self.company.id,original_sale_id=sid,branch_id=self.branch.id,device_id=self.device.id,request_id=uuid4(),reason='Synthetic four-decimal original return',items=[RefundItemCreate(sale_item_id=item.id,quantity=1)])
        wrong=await self.client.post('/api/sales/refunds',json=refund.model_copy(update={'payment_currency_code':'USD'}).model_dump(mode='json'));self.assertEqual(wrong.status_code,409,wrong.text)
        first=await self.client.post('/api/sales/refunds',json=refund.model_dump(mode='json'));self.assertEqual(first.status_code,200,first.text);self.assertEqual(Decimal(str(first.json()['payment_amount_original'])),Decimal('-14.1975'))
        final=await self.client.post('/api/sales/refunds',json=refund.model_copy(update={'request_id':uuid4(),'items':[RefundItemCreate(sale_item_id=item.id,quantity=5)]}).model_dump(mode='json'));self.assertEqual(final.status_code,200,final.text);self.assertEqual(Decimal(str(final.json()['payment_amount_original'])),Decimal('-70.9877'))
        await self.db.execute(text('SET CONSTRAINTS ALL IMMEDIATE'))
    async def test_editor_capability_and_safe_configured_options(self):
        profile=await self.svc.profile();self.assertFalse(profile['quotation_pricing_enabled'])
        with patch('app.core.config.get_settings',return_value=get_settings().model_copy(update={'quotation_pricing_mode':'test'})):
            self.assertTrue((await self.svc.profile())['quotation_pricing_enabled'])
        options=await self.svc.options();product=next(r for r in options['products'] if r['id']==self.product.id)
        self.assertEqual(product['purchase_unit'],'box');self.assertEqual(product['units_per_purchase'],12);self.assertNotIn('cost_price',product);self.assertEqual(options['currencies'][0]['id'],'USD')
