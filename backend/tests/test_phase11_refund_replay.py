"""Partial refund request proof before licensing, approvals or stock effects."""
import unittest
from uuid import uuid4
from decimal import Decimal
import httpx
from sqlalchemy import select,func,text
from sqlalchemy.exc import DBAPIError
from app.models import CompanySubscription, Sale, SaleItem, InventoryMovement, RefundCommandReceipt, User
from app.auth.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.sales.service import SalesService
from app.sales.repository import SalesRepository
from app.sales.schema import SaleCreate,SaleItemCreate,RefundCreate,RefundItemCreate
import test_phase7d_operations as fixtures


class RefundReplayTests(unittest.IsolatedAsyncioTestCase):
    cleanup=fixtures.Phase7DOperationsTests.cleanup
    async def asyncSetUp(self):
        await fixtures.Phase7DOperationsTests.asyncSetUp(self)
        self.license=(await self.db.execute(select(CompanySubscription).where(CompanySubscription.company_id==self.company.id))).scalar_one()
        self.sales=SalesService(SalesRepository(self.db))
        self.original=await self.sales.create_sale(SaleCreate(company_id=self.company.id,branch_id=self.branch.id,device_id=self.device.id,
            employee_id=self.employee.id,client_sale_id=uuid4(),amount_received=1000,items=[SaleItemCreate(product_id=self.product.id,quantity=10)]),actor=self.owner)
        self.original_item=(await self.db.execute(select(SaleItem).where(SaleItem.sale_id==self.original.id))).scalar_one()
        async def override():yield self.db
        app.dependency_overrides[get_db]=override;self.addCleanup(app.dependency_overrides.clear)
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://synthetic.test');self.addAsyncCleanup(self.client.aclose)
        self.headers={'Authorization':'Bearer '+create_access_token(str(self.user.id),self.user.email)}
    def command(self,**changes):
        values=dict(request_id=uuid4(),company_id=self.company.id,original_sale_id=self.original.id,branch_id=self.branch.id,device_id=self.device.id,
            device_key=self.device.device_key,reason='Synthetic partial return',items=[RefundItemCreate(sale_item_id=self.original_item.id,quantity=2)])
        values.update(changes);return RefundCreate(**values)
    async def submit(self,data,headers=None):return await self.client.post('/api/sales/refunds',headers=headers or self.headers,json=data.model_dump(mode='json'))
    async def test_identified_partial_refund_after_expiry_returns_original_without_second_stock_effect(self):
        data=self.command();first=await self.submit(data);self.assertEqual(first.status_code,200,first.text)
        self.assertEqual(self.balance.quantity,92)
        self.license.status='expired';self.license.commercial_terms={'features':{}};await self.db.commit()
        replay=await self.submit(data);self.assertEqual(replay.status_code,200,replay.text);self.assertEqual(replay.json()['id'],first.json()['id'])
        self.assertEqual(self.balance.quantity,92)
        self.assertEqual((await self.submit(data.model_copy(update={'reason':'Changed return'}))).status_code,409)
        self.assertEqual((await self.submit(self.command())).status_code,402)
        lookup=await self.client.get(f'/api/sales/by-client-id/{self.company.id}/{data.request_id}',headers=self.headers)
        self.assertEqual(lookup.status_code,200);self.assertEqual(lookup.json()['id'],first.json()['id'])
        self.assertEqual((await self.db.execute(select(func.count(InventoryMovement.id)).where(InventoryMovement.company_id==self.company.id))).scalar_one(),2)
        self.assertEqual((await self.db.execute(select(func.count(Sale.id)).where(Sale.company_id==self.company.id))).scalar_one(),3)
        self.assertEqual(self.original.status,'partially_refunded')
    async def test_actor_register_key_and_proof_immutability_remain_mandatory(self):
        data=self.command();result=await self.submit(data);self.assertEqual(result.status_code,200,result.text)
        other=User(company_id=self.company.id,email=f'{uuid4()}@example.test',password_hash='unused',role='owner');self.db.add(other);await self.db.commit()
        self.assertEqual((await self.submit(data,{'Authorization':'Bearer '+create_access_token(str(other.id),other.email)})).status_code,403)
        self.assertEqual((await self.submit(data.model_copy(update={'device_key':'incorrect-synthetic-key'}))).status_code,403)
        self.device.assignment_revision+=1;await self.db.commit()
        self.assertEqual((await self.submit(data)).status_code,403)
        with self.assertRaises(DBAPIError):
            async with self.db.begin_nested():await self.db.execute(text("DELETE FROM refund_command_receipts WHERE company_id=:company"),{'company':self.company.id})
    async def test_transaction_purpose_collision_and_new_register_key_failure_create_nothing(self):
        data=self.command(request_id=self.original.client_sale_id)
        self.assertEqual((await self.submit(data)).status_code,409)
        self.assertEqual((await self.submit(self.command(device_key='incorrect-synthetic-key'))).status_code,403)
        self.assertEqual(self.balance.quantity,90)
        data=self.command();self.assertEqual((await self.submit(data)).status_code,200)
        sale=SaleCreate(company_id=self.company.id,branch_id=self.branch.id,device_id=self.device.id,client_sale_id=data.request_id,
                        amount_received=100,items=[SaleItemCreate(product_id=self.product.id,quantity=1)])
        response=await self.client.post('/api/sales',headers=self.headers,json=sale.model_dump(mode='json'))
        self.assertEqual(response.status_code,409);self.assertEqual(self.balance.quantity,92)
        self.assertEqual((await self.db.execute(select(func.count(RefundCommandReceipt.request_id)).where(RefundCommandReceipt.company_id==self.company.id))).scalar_one(),1)
    async def test_duplicate_original_item_and_unknown_employee_cannot_restore_extra_stock(self):
        duplicate=self.command(items=[RefundItemCreate(sale_item_id=self.original_item.id,quantity=6),RefundItemCreate(sale_item_id=self.original_item.id,quantity=6)])
        self.assertEqual((await self.submit(duplicate)).status_code,422)
        self.assertEqual((await self.submit(self.command(employee_id=uuid4()))).status_code,404)
        self.assertEqual(self.balance.quantity,90)
        self.assertEqual((await self.db.execute(select(func.count(RefundCommandReceipt.request_id)).where(RefundCommandReceipt.company_id==self.company.id))).scalar_one(),0)

    async def test_active_employee_attribution_is_checked_before_new_refund(self):
        data=self.command(employee_id=self.employee.id)
        first=await self.submit(data);self.assertEqual(first.status_code,200,first.text)
        self.assertEqual(first.json()['employee_id'],str(self.employee.id))
        self.employee.active=False;await self.db.commit()
        self.assertEqual((await self.submit(self.command(employee_id=self.employee.id))).status_code,404)
        self.assertEqual(self.balance.quantity,92)

    async def test_failure_after_parent_flush_rolls_back_refund_proof_and_stock(self):
        from unittest.mock import patch, AsyncMock
        company_id=self.company.id
        with patch('app.business_operations.batches.allocate_batch_movements',new=AsyncMock(side_effect=RuntimeError('synthetic allocation fault'))):
            with self.assertRaisesRegex(RuntimeError,'synthetic allocation fault'):
                await self.sales.create_refund(self.command(),actor=self.owner)
        await self.db.refresh(self.balance);self.assertEqual(self.balance.quantity,90)
        await self.db.refresh(self.original);self.assertEqual(self.original.status,'completed')
        self.assertEqual((await self.db.execute(select(func.count(RefundCommandReceipt.request_id)).where(RefundCommandReceipt.company_id==company_id))).scalar_one(),0)
        self.assertEqual((await self.db.execute(select(func.count(InventoryMovement.id)).where(InventoryMovement.company_id==company_id))).scalar_one(),1)

    async def test_same_key_changed_quantity_is_not_an_additional_partial_refund(self):
        data=self.command();self.assertEqual((await self.submit(data)).status_code,200)
        changed=data.model_copy(update={'items':[RefundItemCreate(sale_item_id=self.original_item.id,quantity=3)]})
        self.assertEqual((await self.submit(changed)).status_code,409)
        self.assertEqual(self.balance.quantity,92)
        # Legacy callers without a UUID keep the old contract, explicitly not
        # certified idempotent. New first-party clients always supply the key.
        legacy=await self.submit(self.command(request_id=None))
        self.assertEqual(legacy.status_code,200,legacy.text);self.assertEqual(self.balance.quantity,94)
