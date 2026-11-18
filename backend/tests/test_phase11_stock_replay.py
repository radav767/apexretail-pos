"""Direct stock APIs/services: exact replay after expiry cannot repeat movements."""
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4
import unittest
import httpx
from fastapi import HTTPException
from sqlalchemy import select, func, text
from sqlalchemy.exc import DBAPIError
from app.models import CompanySubscription, Branch, InventoryBalance, InventoryMovement, User, AuditEvent
from app.auth.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.inventory.service import InventoryService
from app.inventory.repository import InventoryRepository
from app.inventory.schema import GRNCreate, StockAdjustmentCreate, StockTakeCreate
from app.inventory.transfer_schema import TransferCreate
from app.inventory.transfer_service import TransferService
from app.inventory.transfer_repository import TransferRepository
from app.business_operations.batch_stock import BatchStockService
from app.business_operations.returns import ReturnService
from app.business_operations.schema import BatchStockInput, ProfileInput
import test_phase7d_operations as fixtures
import test_phase7e_recovery_returns as returns
import test_phase7e_tips as tips


class StockReplayTests(unittest.IsolatedAsyncioTestCase):
    cleanup = fixtures.Phase7DOperationsTests.cleanup
    returned = returns.RecoveryReturnTests.returned
    inspect = returns.RecoveryReturnTests.inspect

    async def asyncSetUp(self):
        await fixtures.Phase7DOperationsTests.asyncSetUp(self)
        self.license=(await self.db.execute(select(CompanySubscription).where(CompanySubscription.company_id==self.company.id))).scalar_one()
        self.destination=Branch(company_id=self.company.id,shop_id=self.shop.id,name='Synthetic destination')
        self.db.add(self.destination);await self.db.commit()
        async def override(): yield self.db
        app.dependency_overrides[get_db]=override;self.addCleanup(app.dependency_overrides.clear)
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://synthetic.test')
        self.addAsyncCleanup(self.client.aclose)
        self.headers={'Authorization':'Bearer '+create_access_token(str(self.user.id),self.user.email)}

    async def post(self,path,data,headers=None):
        return await self.client.post('/api/'+path,headers=headers or self.headers,json=data.model_dump(mode='json'))

    def count(self,**changes):
        values=dict(company_id=self.company.id,branch_id=self.branch.id,request_id=uuid4(),items=[{'product_id':self.product.id,'physical_qty':90,'expected_qty':100}])
        values.update(changes);return StockTakeCreate(**values)

    def transfer(self,**changes):
        values=dict(company_id=self.company.id,source_branch_id=self.branch.id,destination_branch_id=self.destination.id,request_id=uuid4(),
                    items=[{'product_id':self.product.id,'quantity':5}])
        values.update(changes);return TransferCreate(**values)

    def batch(self,**changes):
        values=dict(request_id=uuid4(),branch_id=self.branch.id,product_id=self.product.id,operation='receive',code='SYNTHETIC',
                    expires_on=date.today()+timedelta(days=30),quantity=2,reason='Synthetic confirmed stock')
        values.update(changes);return BatchStockInput(**values)

    async def test_count_then_transfer_replay_after_current_stock_and_license_change(self):
        count,transfer=self.count(),self.transfer()
        counted=await self.post('inventory/stock-take',count);self.assertEqual(counted.status_code,200,counted.text)
        moved=await self.post('inventory/transfers',transfer);self.assertEqual(moved.status_code,200,moved.text)
        self.license.status='expired';self.license.commercial_terms={'features':{}};self.product.active=False;await self.db.commit()
        for path,data,first in [('inventory/stock-take',count,counted),('inventory/transfers',transfer,moved)]:
            replay=await self.post(path,data);self.assertEqual(replay.status_code,200,replay.text)
            self.assertEqual([row['id'] for row in replay.json()],[row['id'] for row in first.json()])
            self.assertEqual((await self.post(path,data.model_copy(update={'notes':'Changed'}))).status_code,409)
            self.assertEqual((await self.post(path,data.model_copy(update={'request_id':uuid4()}))).status_code,402)
        await self.db.refresh(self.balance);self.assertEqual(self.balance.quantity,85)
        destination=(await self.db.execute(select(InventoryBalance).where(InventoryBalance.company_id==self.company.id,InventoryBalance.branch_id==self.destination.id))).scalar_one()
        self.assertEqual(destination.quantity,5)
        self.assertEqual((await self.db.execute(select(func.count(InventoryMovement.id)).where(InventoryMovement.company_id==self.company.id))).scalar_one(),3)

    async def test_variant_count_replay_after_variant_module_removal(self):
        from test_phase7_inventory_completion import InventoryCompletionTests
        await InventoryCompletionTests.prepare(self)
        data=self.count(items=[{'product_id':self.product.id,'variant_id':self.a['id'],'physical_qty':8,'expected_qty':10}])
        first=await self.post('inventory/stock-take',data);self.assertEqual(first.status_code,200,first.text)
        self.license.status='suspended';self.license.commercial_terms={'features':{}};await self.db.commit()
        replay=await self.post('inventory/stock-take',data);self.assertEqual(replay.status_code,200,replay.text)
        self.assertEqual(first.json()[0]['id'],replay.json()[0]['id'])
        self.assertEqual((await self.post('inventory/stock-take',data.model_copy(update={'request_id':uuid4()}))).status_code,402)
        from app.models import VariantInventoryBalance
        self.assertEqual((await self.db.execute(select(VariantInventoryBalance.quantity).where(VariantInventoryBalance.variant_id==self.a['id']))).scalar_one(),8)
        self.assertEqual(self.balance.quantity,100)

    async def test_batch_replay_survives_module_removal_without_stock_effects(self):
        await self.svc.save_profile(ProfileInput(profile="pharmacy"))
        data=self.batch();first=await self.post('operations/batches/stock',data);self.assertEqual(first.status_code,200,first.text)
        self.license.status='suspended';self.license.commercial_terms={'features':{}};self.product.active=False;await self.db.commit()
        second=await self.post('operations/batches/stock',data);self.assertEqual(second.status_code,200,second.text)
        self.assertEqual(second.json()['movement_id'],first.json()['movement_id']);self.assertTrue(second.json()['already_processed'])
        self.assertEqual((await self.post('operations/batches/stock',data.model_copy(update={'quantity':Decimal(3)}))).status_code,409)
        self.assertEqual((await self.post('operations/batches/stock',data.model_copy(update={'request_id':uuid4()}))).status_code,402)
        self.assertEqual(self.balance.quantity,102)

    async def test_inspected_refund_replay_survives_module_removal_without_second_refund(self):
        hold,refund=await self.returned()
        command=self.inspect(hold)
        first=await self.post('operations/batches/returns/inspect',command);self.assertEqual(first.status_code,200,first.text)
        self.license.status='expired';self.license.commercial_terms={'features':{}};self.product.active=False;await self.db.commit()
        replay=await self.post('operations/batches/returns/inspect',command);self.assertEqual(replay.status_code,200,replay.text)
        self.assertEqual(first.json()['id'],replay.json()['id']);self.assertEqual(self.balance.quantity,99)
        self.assertEqual(refund.status,'refunded')
        from app.models import Sale
        self.assertEqual((await self.db.execute(select(func.count(Sale.id)).where(Sale.company_id==self.company.id))).scalar_one(),3)

    async def test_direct_service_mutations_fail_before_effects_and_approval_consumption(self):
        self.license.status='expired';await self.db.commit()
        inventory=InventoryService(InventoryRepository(self.db));transfer=TransferService(TransferRepository(self.db))
        for call in [inventory.receive_stock(GRNCreate(company_id=self.company.id,branch_id=self.branch.id,product_id=self.product.id,quantity=2),actor=self.owner),
                     inventory.adjust_stock(StockAdjustmentCreate(company_id=self.company.id,branch_id=self.branch.id,product_id=self.product.id,quantity=2,adjustment_type='remove',reason='Synthetic'),actor=self.owner),
                     inventory.stock_take(self.count(),actor=self.owner),transfer.transfer(self.transfer(),actor=self.owner),
                     BatchStockService(self.db,self.owner).execute(self.batch())]:
            with self.assertRaises(HTTPException) as error:await call
            self.assertEqual(error.exception.status_code,402)
        self.assertEqual(self.balance.quantity,100)
        with self.assertRaises(HTTPException) as error:await inventory.receive_stock(GRNCreate(company_id=self.company.id,product_id=self.product.id,quantity=2))
        self.assertEqual(error.exception.status_code,401)

    async def test_missing_subscription_never_bootstraps_at_early_route_guard(self):
        from app.models import Company, CompanySubscriptionHistory
        from app.subscriptions.service import SubscriptionService
        from app.subscriptions.write_policy import require_new_write
        company=Company(name='Synthetic unlicensed tenant',owner_email=f'{uuid4()}@example.test')
        self.db.add(company);await self.db.flush()
        owner=User(company_id=company.id,email=f'{uuid4()}@example.test',password_hash='unused',role='owner')
        self.db.add(owner);await self.db.commit()
        headers={'Authorization':'Bearer '+create_access_token(str(owner.id),owner.email)}
        response=await self.post('inventory/grn',GRNCreate(company_id=company.id,product_id=uuid4(),quantity=1),headers)
        self.assertEqual(response.status_code,402,response.text)
        self.assertIsNone((await self.db.execute(select(CompanySubscription).where(CompanySubscription.company_id==company.id))).scalar_one_or_none())
        self.assertEqual((await self.db.execute(select(func.count(CompanySubscriptionHistory.id)).where(CompanySubscriptionHistory.company_id==company.id))).scalar_one(),0)
        # Preserve established active-without-end policy: old trial expiry is
        # not an active paid period. This does not grant a trial to missing rows.
        self.license.status='active';self.license.current_period_ends_at=None
        from datetime import datetime,timezone
        self.license.trial_ends_at=datetime.now(timezone.utc)-timedelta(days=2)
        await self.db.commit()
        await require_new_write(self.db,self.company.id)
        await SubscriptionService(self.db).enforce_writes_allowed(self.company.id)

    async def test_actor_register_and_immutable_audit_proof_remain_required(self):
        data=self.count();first=await self.post('inventory/stock-take',data);self.assertEqual(first.status_code,200,first.text)
        other=User(company_id=self.company.id,email=f'{uuid4()}@example.test',password_hash='unused',role='owner')
        self.db.add(other);await self.db.commit()
        other_headers={'Authorization':'Bearer '+create_access_token(str(other.id),other.email)}
        self.assertEqual((await self.post('inventory/stock-take',data,other_headers)).status_code,403)
        with self.assertRaises(DBAPIError):
            async with self.db.begin_nested():
                await self.db.execute(text("UPDATE audit_events SET details='{}' WHERE company_id=:company AND action='inventory_count_committed_v1'"),{'company':self.company.id})
        # Original employee/register context is part of a new transfer proof.
        self.cashier.permissions={**self.cashier.permissions,'inventory_transfer':True}
        service=TransferService(TransferRepository(self.db));move=self.transfer();await service.transfer(move,actor=self.cashier)
        self.device.assignment_revision+=1;await self.db.commit()
        with self.assertRaises(HTTPException) as error:await service.transfer(move,actor=self.cashier)
        self.assertEqual(error.exception.status_code,403)


class TipReplayTests(unittest.IsolatedAsyncioTestCase):
    cleanup=fixtures.Phase7DOperationsTests.cleanup
    asyncSetUp=tips.TipIntegrationTests.asyncSetUp
    command=tips.TipIntegrationTests.command

    async def test_committed_tip_after_expiry_returns_one_cash_effect_and_new_tip_denied(self):
        data=self.command();first=await self.pos.record(data)
        subscription=(await self.db.execute(select(CompanySubscription).where(CompanySubscription.company_id==self.company.id))).scalar_one()
        subscription.status='expired';await self.db.commit()
        second=await self.pos.record(data);self.assertEqual(first['id'],second['id']);self.assertTrue(second['already_recorded'])
        with self.assertRaises(HTTPException) as error:await self.pos.record(self.command())
        self.assertEqual(error.exception.status_code,402)
        from app.models import CashierShiftCashMovement,TipEntry
        self.assertEqual((await self.db.execute(select(func.count(CashierShiftCashMovement.id)).where(CashierShiftCashMovement.shift_id==self.shift['id']))).scalar_one(),1)
        self.assertEqual((await self.db.execute(select(func.count(TipEntry.id)).where(TipEntry.company_id==self.company.id))).scalar_one(),1)
        from app.auth.security import hash_session_token
        token='synthetic-tip-'+str(uuid4())
        self.session.token_hash=hash_session_token(token)
        self.employee.permissions={**self.employee.permissions,'tips_collect':True}
        await self.db.commit()
        async def override():yield self.db
        app.dependency_overrides[get_db]=override;self.addCleanup(app.dependency_overrides.clear)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://synthetic.test') as client:
            headers={'Authorization':'Bearer '+token}
            replay=await client.post('/api/operations/tips/entries',headers=headers,json=data.model_dump(mode='json'))
            self.assertEqual(replay.status_code,200,replay.text)
            denied=await client.post('/api/operations/tips/entries',headers=headers,json=self.command().model_dump(mode='json'))
            self.assertEqual(denied.status_code,402,denied.text)
        self.assertEqual(self.balance.quantity,100)
