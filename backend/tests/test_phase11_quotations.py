"""Quotation lifecycle freezes commercial terms without stock or payment effects."""
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from uuid import uuid4
from unittest.mock import patch
import unittest
import httpx
from fastapi import HTTPException
from sqlalchemy import select,func,text
from sqlalchemy.exc import DBAPIError
from app.models import CompanySubscription,CompanySetting,CommerceOrder,CommerceOrderItem,Sale,InventoryMovement,QuotationCommand
from app.business_operations.schema import ProfileInput,OrderInput,OrderItemInput,SettlementInput,QuotationTransition
from app.business_operations.quotations import transition
from app.sales.schema import SaleCreate
from app.auth.security import create_access_token
from app.db.session import get_db
from app.main import app
import test_phase7d_operations as fixtures

class QuotationTests(unittest.IsolatedAsyncioTestCase):
    cleanup=fixtures.Phase7DOperationsTests.cleanup
    async def asyncSetUp(self):
        await fixtures.Phase7DOperationsTests.asyncSetUp(self)
        await self.svc.save_profile(ProfileInput(profile='wholesale'))
        self.order=await self.svc.create_order(OrderInput(branch_id=self.branch.id,device_id=self.device.id,kind='quotation',request_id=uuid4()))
        self.order=await self.svc.add_item(self.order['id'],OrderItemInput(version=self.order['version'],product_id=self.product.id,quantity=2))
        async def override():yield self.db
        app.dependency_overrides[get_db]=override;self.addCleanup(app.dependency_overrides.clear)
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://synthetic.test',headers={'Authorization':'Bearer '+create_access_token(str(self.user.id),self.user.email)})
        self.addAsyncCleanup(self.client.aclose)
    def action(self,action,**extra):return QuotationTransition(version=self.order['version'],request_id=uuid4(),action=action,**extra)
    async def send(self):
        self.sent=self.action('sent',valid_until=datetime.now(timezone.utc)+timedelta(days=2));self.order=await transition(self.svc,self.order['id'],self.sent);return self.order
    async def accept(self):
        await self.send();self.accepted=self.action('accepted');self.order=await transition(self.svc,self.order['id'],self.accepted);return self.order
    def payment(self):return SettlementInput(version=self.order['version'],payment=SaleCreate(company_id=self.company.id,payment_method='cash',amount_received=100,items=[]))
    async def test_draft_sent_accept_convert_and_committed_replay_have_single_stock_effect(self):
        from app.business_operations.schema import SplitInput
        with self.assertRaises(HTTPException):await self.svc.split(self.order['id'],SplitInput(version=self.order['version'],request_id=uuid4(),item_ids=[self.order['items'][0]['id']]))
        with self.assertRaises(HTTPException) as error:await self.svc.settle(self.order['id'],self.payment())
        self.assertEqual(error.exception.status_code,409);self.assertEqual(self.balance.quantity,100)
        await self.accept();self.assertEqual(self.order['quotation_status'],'accepted');self.assertEqual(self.balance.quantity,100)
        self.assertEqual(self.order['quotation_terms']['total'],'24.00');command=self.payment();result=await self.svc.settle(self.order['id'],command)
        self.assertEqual(self.balance.quantity,98);self.assertEqual((await self.db.get(Sale,result['sale_id'])).total_amount,24);self.assertEqual((await self.db.get(Sale,result['sale_id'])).discount_amount,0)
        sub=(await self.db.execute(select(CompanySubscription).where(CompanySubscription.company_id==self.company.id))).scalar_one();sub.status='expired';sub.commercial_terms={'features':{}};await self.db.commit()
        again=await self.svc.settle(self.order['id'],command);self.assertEqual(result['sale_id'],again['sale_id']);self.assertEqual(self.balance.quantity,98)
        self.assertEqual((await self.db.execute(select(func.count(InventoryMovement.id)).where(InventoryMovement.company_id==self.company.id))).scalar_one(),1)
    async def test_transition_api_exact_expired_replay_and_changed_payload_conflict(self):
        command=self.action('sent',valid_until=datetime.now(timezone.utc)+timedelta(days=1));url=f"/api/operations/orders/{self.order['id']}/quotation-transition"
        response=await self.client.post(url,json=command.model_dump(mode='json'));self.assertEqual(response.status_code,200,response.text)
        sub=(await self.db.execute(select(CompanySubscription).where(CompanySubscription.company_id==self.company.id))).scalar_one();sub.status='expired';sub.commercial_terms={'features':{}};await self.db.commit()
        again=await self.client.post(url,json=command.model_dump(mode='json'));self.assertEqual(again.status_code,200,again.text)
        conflict=await self.client.post(url,json=command.model_copy(update={'action':'accepted','valid_until':None}).model_dump(mode='json'));self.assertEqual(conflict.status_code,409,conflict.text)
        new=await self.client.post(url,json=command.model_copy(update={'request_id':uuid4()}).model_dump(mode='json'));self.assertEqual(new.status_code,402,new.text)
        self.assertEqual(self.balance.quantity,100)
    async def test_terms_and_item_rows_frozen_and_accepted_catalog_or_tax_drift_denies_conversion(self):
        await self.accept();oid=self.order['id'];item_id=self.order['items'][0]['id']
        for sql,params in [('UPDATE commerce_orders SET quotation_terms=\'{}\'::jsonb WHERE id=:id',{'id':oid}),('UPDATE commerce_order_items SET price=1 WHERE id=:id',{'id':item_id})]:
            with self.assertRaises(DBAPIError):
                async with self.db.begin_nested():await self.db.execute(text(sql),params)
        with self.assertRaises(HTTPException):await self.svc.add_item(oid,OrderItemInput(version=self.order['version'],product_id=self.product.id,quantity=1))
        self.product.selling_price=13;await self.db.commit()
        with self.assertRaises(HTTPException) as error:await self.svc.settle(oid,self.payment())
        self.assertEqual(error.exception.status_code,409);self.assertEqual(self.balance.quantity,100)
    async def test_rejected_expired_and_legacy_unproved_quotes_cannot_convert(self):
        await self.send();self.order=await transition(self.svc,self.order['id'],self.action('rejected'))
        with self.assertRaises(HTTPException):await self.svc.settle(self.order['id'],self.payment())
        self.assertEqual(self.balance.quantity,100)
        # Expiry is derived from time; never mutate immutable validity for a test.
        from app.business_operations import quotations
        future=datetime.now(timezone.utc)+timedelta(days=5)
        class Clock(datetime):
            @classmethod
            def now(cls,tz=None):return future
        # New second quote, accepted with a real future deadline, then clock past it.
        self.order=await self.svc.create_order(OrderInput(branch_id=self.branch.id,device_id=self.device.id,kind='quotation',request_id=uuid4()))
        self.order=await self.svc.add_item(self.order['id'],OrderItemInput(version=self.order['version'],product_id=self.product.id,quantity=2));await self.accept()
        with patch.object(quotations,'datetime',Clock):
            self.assertEqual((await self.svc.order_out(await self.svc.order(self.order['id'])))['quotation_status'],'expired')
            with self.assertRaises(HTTPException):await self.svc.settle(self.order['id'],self.payment())
        self.assertEqual(self.balance.quantity,100)
    async def test_current_stock_checked_only_at_conversion_and_failure_has_no_sale(self):
        await self.accept();self.balance.quantity=1;self.product.stock_qty=1;await self.db.commit()
        before=(await self.db.execute(select(func.count(Sale.id)).where(Sale.company_id==self.company.id))).scalar_one()
        with self.assertRaises(HTTPException):await self.svc.settle(self.order['id'],self.payment())
        await self.db.rollback()
        count=(await self.db.execute(select(func.count(Sale.id)).where(Sale.company_id==self.owner.company_id))).scalar_one();self.assertEqual(count,before)

    async def test_tax_terms_missing_history_and_changed_register_remain_gated(self):
        oid=self.order['id']
        await self.db.execute(text('UPDATE commerce_orders SET quotation_status=NULL WHERE id=:id'),{'id':oid});await self.db.commit()
        with self.assertRaises(HTTPException):await self.svc.settle(oid,self.payment())
        with self.assertRaises(HTTPException):await self.send()
        await self.db.execute(text("UPDATE commerce_orders SET quotation_status='draft' WHERE id=:id"),{'id':oid});await self.db.commit()
        settings=(await self.db.execute(select(CompanySetting).where(CompanySetting.company_id==self.company.id))).scalar_one();settings.tax_rate=15;settings.tax_inclusive=False;await self.db.commit()
        await self.accept();self.assertEqual(self.order['quotation_terms']['total'],'27.60');self.assertEqual(self.order['quotation_terms']['tax'],'3.60')
        # Register assignment is revalidated even for an otherwise exact ACK.
        await self.db.refresh(self.device);self.device.assignment_revision+=1;await self.db.commit()
        with self.assertRaises(HTTPException) as error:await transition(self.svc,oid,self.sent)
        self.assertEqual(error.exception.status_code,403)
        self.assertEqual(self.balance.quantity,100)

    async def test_final_sale_comparison_failure_rolls_back_proof_stock_and_order(self):
        await self.accept();oid=self.order['id'];company=self.company.id;product=self.product.id
        with patch('app.business_operations.quotations.validate_sale',side_effect=HTTPException(409,'synthetic frozen-term mismatch')):
            with self.assertRaises(HTTPException):await self.svc.settle(oid,self.payment())
        await self.db.rollback()
        row=await self.db.get(CommerceOrder,oid);self.assertEqual(row.status,'open');self.assertIsNone(row.sale_id)
        self.assertEqual((await self.db.execute(select(func.count(InventoryMovement.id)).where(InventoryMovement.company_id==company))).scalar_one(),0)
        from app.models import InventoryBalance,SaleCommandReceipt
        self.assertEqual((await self.db.execute(select(InventoryBalance.quantity).where(InventoryBalance.product_id==product))).scalar_one(),100)
        self.assertIsNone(await self.db.get(SaleCommandReceipt,oid))
