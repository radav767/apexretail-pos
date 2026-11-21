"""Immutable revision lineage owns at most one accepted conversion."""
import unittest
from uuid import UUID,uuid4
from datetime import datetime,timedelta,timezone
from sqlalchemy import select,func,text
from sqlalchemy.exc import DBAPIError
from fastapi import HTTPException
from app.business_operations.quotation_revisions import revise
from app.business_operations.quotations import transition
from app.business_operations.schema import QuotationRevision,QuotationTransition,SettlementInput
from app.sales.schema import SaleCreate
from app.models import CommerceOrder,CommerceOrderItem,Sale,InventoryMovement,CompanySubscription
import test_phase11_quotations as fixtures
class RevisionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await fixtures.QuotationTests.asyncSetUp(self)
        self.c=self.company.id
    cleanup=fixtures.QuotationTests.cleanup
    action=fixtures.QuotationTests.action
    send=fixtures.QuotationTests.send
    accept=fixtures.QuotationTests.accept
    payment=fixtures.QuotationTests.payment
    async def child(self):
        return await revise(self.svc,self.order['id'],QuotationRevision(version=self.order['version'],request_id=uuid4(),reason='Synthetic revised offer'))
    async def test_new_draft_preserves_original_terms_items_and_full_input_replay(self):
        await self.accept();source=self.order.copy();command=QuotationRevision(version=source['version'],request_id=uuid4(),reason='Synthetic revision')
        child=await revise(self.svc,source['id'],command);again=await revise(self.svc,source['id'],command)
        self.assertEqual(child['id'],again['id']);self.assertEqual(child['quotation_revision'],1);self.assertEqual(str(child['parent_id']),str(source['id']));self.assertEqual(child['quotation_status'],'draft');self.assertIsNone(child['quotation_terms'])
        original=await self.svc.order_out(await self.svc.order(source['id']));self.assertEqual(original['quotation_terms'],source['quotation_terms']);self.assertEqual(original['items'],source['items']);self.assertEqual(original['version'],source['version']);self.assertEqual(self.balance.quantity,100)
        with self.assertRaises(HTTPException):await revise(self.svc,source['id'],command.model_copy(update={'reason':'Altered original intent'}))
        await self.db.refresh(self.user)
        sub=(await self.db.execute(select(CompanySubscription).where(CompanySubscription.company_id==self.c))).scalar_one();sub.status='expired';await self.db.commit()
        self.assertEqual((await revise(self.svc,source['id'],command))['id'],child['id'])
        with self.assertRaises(DBAPIError):
            async with self.db.begin_nested():await self.db.execute(text('UPDATE commerce_orders SET quotation_root_id=NULL WHERE id=:id'),{'id':UUID(str(child['id']))})
    async def test_later_sent_revision_supersedes_original_without_mutation_and_converts_once(self):
        await self.accept();source=self.order.copy();child=await self.child();self.order=child;await self.accept()
        original=await self.svc.order_out(await self.svc.order(source['id']));self.assertEqual(original['quotation_status'],'superseded');self.assertEqual(original['quotation_terms'],source['quotation_terms'])
        old_payment=SettlementInput(version=source['version'],payment=SaleCreate(company_id=self.company.id,payment_method='cash',amount_received=100,items=[]))
        with self.assertRaises(HTTPException):await self.svc.settle(source['id'],old_payment)
        settled=await self.svc.settle(self.order['id'],self.payment());self.assertIsNotNone(settled['sale_id']);self.assertEqual(self.balance.quantity,98)
        with self.assertRaises(HTTPException):await revise(self.svc,self.order['id'],QuotationRevision(version=self.order['version'],request_id=uuid4(),reason='Converted lineage'))
        self.assertEqual((await self.db.execute(select(func.count(Sale.id)).where(Sale.company_id==self.c))).scalar_one(),2)
    async def test_role_tenant_branch_revision_endpoint_and_draft_denial(self):
        response=await self.client.post(f"/api/operations/orders/{self.order['id']}/quotation-revision",json={'request_id':str(uuid4()),'version':self.order['version'],'reason':'Draft is not frozen'});self.assertEqual(response.status_code,409)
        await self.db.refresh(self.user)
        await self.accept();response=await self.client.post(f"/api/operations/orders/{self.order['id']}/quotation-revision",json={'request_id':str(uuid4()),'version':self.order['version'],'reason':'Synthetic API revision'});self.assertEqual(response.status_code,200,response.text)
        await self.db.refresh(self.balance);self.assertEqual(self.balance.quantity,100)
        await self.db.refresh(self.employee);await self.db.refresh(self.company)
        from app.auth.security import create_employee_access_token
        token=create_employee_access_token(employee_id=str(self.employee.id),company_id=str(self.company.id),role='cashier')
        response=await self.client.post(f"/api/operations/orders/{self.order['id']}/quotation-revision",headers={'Authorization':'Bearer '+token},json={'request_id':str(uuid4()),'version':self.order['version'],'reason':'Denied cashier'});self.assertEqual(response.status_code,403)
    async def test_clone_failure_rolls_back_child_items_and_proof(self):
        from unittest.mock import patch
        from app.models import QuotationCommand,InventoryBalance
        await self.accept();source_id=self.order['id'];source_terms=self.order['quotation_terms'];pid=self.product.id
        before=(await self.db.execute(select(func.count(CommerceOrder.id)).where(CommerceOrder.company_id==self.c))).scalar_one()
        command=QuotationRevision(version=self.order['version'],request_id=uuid4(),reason='Synthetic failure before revision commit')
        with patch.object(self.svc,'commit_operation',side_effect=RuntimeError('Synthetic revision commit failure')):
            with self.assertRaises(RuntimeError):await revise(self.svc,source_id,command)
        self.assertIsNone(await self.db.get(QuotationCommand,command.request_id))
        self.assertEqual((await self.db.execute(select(func.count(CommerceOrder.id)).where(CommerceOrder.company_id==self.c))).scalar_one(),before)
        original=await self.db.get(CommerceOrder,source_id);self.assertEqual(original.quotation_terms,source_terms)
        self.assertEqual((await self.db.execute(select(InventoryBalance.quantity).where(InventoryBalance.product_id==pid))).scalar_one(),100)
