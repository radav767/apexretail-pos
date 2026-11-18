"""Licensed drawer writes, exact replay and expired-account shift finalization."""
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4
import httpx
from fastapi import HTTPException
from sqlalchemy import select, func, text
from sqlalchemy.exc import DBAPIError
from app.models import CompanySubscription, CashierShift, CashierShiftCashMovement, ShiftCommandReceipt, InventoryMovement, Sale, OfflineSaleResolution
from app.auth.security import create_access_token, hash_session_token
from app.db.session import get_db
from app.main import app
from app.shifts.service import ShiftService
from app.shifts.repository import ShiftRepository
from app.shifts.schema import ShiftOpen, ShiftClose, CashMovementCreate, OfflineSaleResolutionCreate
from app.sales.schema import SaleCreate, SaleItemCreate
import test_phase7d_operations as fixtures


class ShiftCommandTests(unittest.IsolatedAsyncioTestCase):
    cleanup=fixtures.Phase7DOperationsTests.cleanup

    async def asyncSetUp(self):
        await fixtures.Phase7DOperationsTests.asyncSetUp(self)
        self.license=(await self.db.execute(select(CompanySubscription).where(CompanySubscription.company_id==self.company.id))).scalar_one()
        permissions={**self.employee.permissions,'shifts_open':True,'shifts_close':True,'cash_movements_manage':True}
        self.employee.permissions=permissions;self.cashier.permissions=permissions
        token='synthetic-shift-'+str(uuid4());self.session.token_hash=hash_session_token(token);await self.db.commit()
        self.headers={'Authorization':'Bearer '+token}
        self.owner_headers={'Authorization':'Bearer '+create_access_token(str(self.user.id),self.user.email)}
        async def override():yield self.db
        app.dependency_overrides[get_db]=override;self.addCleanup(app.dependency_overrides.clear)
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://synthetic.test')
        self.addAsyncCleanup(self.client.aclose)
        self.shifts=ShiftService(ShiftRepository(self.db))

    async def post(self,path,data,owner=False):
        return await self.client.post('/api/shifts/'+path,headers=self.owner_headers if owner else self.headers,json=data.model_dump(mode='json'))
    def opening(self):return ShiftOpen(opening_balances=[{'currency_code':'USD','amount':20}],idempotency_key=str(uuid4()),opening_note='Synthetic float')
    def closing(self,amount=20,**changes):
        data=dict(counted_balances=[{'currency_code':'USD','amount':amount}],idempotency_key=str(uuid4()),confirmed=True)
        data.update(changes);return ShiftClose(**data)
    def movement(self,**changes):
        data=dict(movement_type='cash_in',currency_code='USD',amount=10,reason='Synthetic confirmed manual float',idempotency_key=str(uuid4()))
        data.update(changes);return CashMovementCreate(**data)
    async def opened(self):
        data=self.opening();response=await self.post('open',data);self.assertEqual(response.status_code,200,response.text)
        return data,response.json()

    async def test_opening_and_drawer_replay_after_expiry_do_not_duplicate_effects(self):
        opening,shift=await self.opened();movement=self.movement()
        first=await self.post(f"{shift['id']}/cash-movements",movement);self.assertEqual(first.status_code,200,first.text)
        self.license.status='expired';await self.db.commit()
        replay=await self.post('open',opening);self.assertEqual(replay.status_code,200,replay.text);self.assertEqual(replay.json()['id'],shift['id'])
        second=await self.post(f"{shift['id']}/cash-movements",movement);self.assertEqual(second.status_code,200,second.text)
        self.assertEqual(second.json()['id'],first.json()['id'])
        self.assertEqual((await self.post('open',opening.model_copy(update={'opening_note':'Changed'}))).status_code,409)
        self.assertEqual((await self.post(f"{shift['id']}/cash-movements",movement.model_copy(update={'reason':'Changed'}))).status_code,409)
        self.assertEqual((await self.post('open',self.opening())).status_code,402)
        self.assertEqual((await self.post(f"{shift['id']}/cash-movements",self.movement())).status_code,402)
        self.assertEqual((await self.db.execute(select(func.count(CashierShift.id)).where(CashierShift.company_id==self.company.id))).scalar_one(),1)
        self.assertEqual((await self.db.execute(select(func.count(CashierShiftCashMovement.id)).where(CashierShiftCashMovement.company_id==self.company.id))).scalar_one(),1)
        self.assertEqual(self.balance.quantity,100)
        with self.assertRaises(HTTPException) as error:await self.shifts.create_cash_movement(UUID(shift['id']),self.movement(),self.cashier)
        self.assertEqual(error.exception.status_code,402)

    async def test_closure_allowed_after_expiry_but_changed_counts_cannot_replay(self):
        _,shift=await self.opened();self.license.status='suspended';await self.db.commit()
        data=self.closing();first=await self.post(f"{shift['id']}/close",data);self.assertEqual(first.status_code,200,first.text)
        self.assertEqual(first.json()['status'],'closed')
        self.assertEqual((await self.post(f"{shift['id']}/close",data)).status_code,200)
        changed=self.closing(21,idempotency_key=data.idempotency_key)
        self.assertEqual((await self.post(f"{shift['id']}/close",changed)).status_code,409)
        self.assertEqual((await self.post('open',self.opening())).status_code,402)
        self.assertEqual((await self.post(f"{shift['id']}/cash-movements",self.movement())).status_code,402)
        with self.assertRaises(DBAPIError):
            async with self.db.begin_nested():await self.db.execute(text("UPDATE shift_command_receipts SET payload_hash='changed' WHERE company_id=:company"),{'company':self.company.id})

    async def test_manager_closure_preserves_exception_and_actor_proof(self):
        _,shift=await self.opened();self.license.status='expired';await self.db.commit()
        data=self.closing(exception_reason='Synthetic cashier unavailable')
        path=f"{shift['id']}/manager-close"
        first=await self.post(path,data,owner=True);self.assertEqual(first.status_code,200,first.text)
        self.assertEqual((await self.post(path,data,owner=True)).status_code,200)
        self.assertEqual((await self.post(path,data.model_copy(update={'exception_reason':'Changed reason'}),owner=True)).status_code,409)
        from app.models import User
        other=User(company_id=self.company.id,email=f'{uuid4()}@example.test',password_hash='unused',role='owner');self.db.add(other);await self.db.commit()
        response=await self.client.post('/api/shifts/'+path,headers={'Authorization':'Bearer '+create_access_token(str(other.id),other.email)},json=data.model_dump(mode='json'))
        self.assertEqual(response.status_code,403)

    async def test_closed_shift_cash_replay_and_reserved_tip_namespace(self):
        _,shift=await self.opened();data=self.movement()
        first=await self.post(f"{shift['id']}/cash-movements",data);self.assertEqual(first.status_code,200,first.text)
        closed=await self.post(f"{shift['id']}/close",self.closing(30));self.assertEqual(closed.status_code,200,closed.text)
        self.license.status='expired';await self.db.commit()
        self.assertEqual((await self.post(f"{shift['id']}/cash-movements",data)).status_code,200)
        self.assertEqual((await self.post('current/cash-movements',data)).status_code,200)
        self.assertEqual((await self.post(f"{shift['id']}/cash-movements",self.movement(idempotency_key='tip:'+str(uuid4())))).status_code,422)
        self.device.assignment_revision+=1;await self.db.commit()
        self.assertEqual((await self.post(f"{shift['id']}/cash-movements",data)).status_code,403)

    async def test_command_keys_cannot_attach_cash_or_closure_to_another_shift(self):
        _,first_shift=await self.opened();cash=self.movement()
        self.assertEqual((await self.post(f"{first_shift['id']}/cash-movements",cash)).status_code,200)
        close=self.closing(30)
        self.assertEqual((await self.post(f"{first_shift['id']}/close",close)).status_code,200)
        _,next_shift=await self.opened()
        self.assertEqual((await self.post(f"{next_shift['id']}/cash-movements",cash)).status_code,409)
        manager_close=self.closing(20,idempotency_key=close.idempotency_key,exception_reason='Synthetic unavailable cashier')
        self.assertEqual((await self.post(f"{next_shift['id']}/manager-close",manager_close,owner=True)).status_code,409)
        row=await self.db.get(CashierShift,UUID(next_shift['id']));self.assertEqual(row.status,'open')
        self.assertEqual((await self.db.execute(select(func.count(CashierShiftCashMovement.id)).where(CashierShiftCashMovement.company_id==self.company.id))).scalar_one(),1)
        replay=await self.post('current/cash-movements',cash)
        self.assertEqual(replay.status_code,200,replay.text);self.assertEqual(replay.json()['shift_id'],first_shift['id'])

    async def resolution(self,action='post_to_original_shift'):
        _,shift=await self.opened();capture=datetime.now(timezone.utc)
        closed=await self.post(f"{shift['id']}/close",self.closing());self.assertEqual(closed.status_code,200,closed.text)
        sale=SaleCreate(company_id=self.company.id,branch_id=self.branch.id,device_id=self.device.id,employee_id=self.employee.id,
            shift_id=UUID(shift['id']),offline_shift_token=shift['offline_shift_token'],client_sale_id=uuid4(),client_created_at=capture,
            amount_received=100,items=[SaleItemCreate(product_id=self.product.id,quantity=2)])
        return OfflineSaleResolutionCreate(action=action,reason='Synthetic manager reviewed original evidence',idempotency_key=str(uuid4()),sale=sale),shift

    async def test_manager_posting_original_closed_shift_is_atomic_and_exact_after_expiry(self):
        data,shift=await self.resolution()
        first=await self.post('offline-resolutions',data,owner=True);self.assertEqual(first.status_code,200,first.text)
        self.license.status='expired';await self.db.commit()
        second=await self.post('offline-resolutions',data,owner=True);self.assertEqual(second.status_code,200,second.text)
        self.assertEqual(first.json()['id'],second.json()['id']);self.assertEqual(self.balance.quantity,98)
        self.assertEqual((await self.post('offline-resolutions',data.model_copy(update={'reason':'Changed review'}),owner=True)).status_code,409)
        changed=data.model_copy(update={'idempotency_key':str(uuid4()),'sale':data.sale.model_copy(update={'client_sale_id':uuid4()})})
        self.assertEqual((await self.post('offline-resolutions',changed,owner=True)).status_code,402)
        self.assertEqual((await self.db.execute(select(func.count(OfflineSaleResolution.id)).where(OfflineSaleResolution.company_id==self.company.id))).scalar_one(),1)
        self.assertEqual((await self.db.execute(select(func.count(InventoryMovement.id)).where(InventoryMovement.company_id==self.company.id))).scalar_one(),1)
        original=await self.db.get(CashierShift,UUID(shift['id']));self.assertEqual(original.net_sales_base,0)

    async def test_retaining_quarantine_is_evidence_exception_not_permission_to_post(self):
        data,_=await self.resolution('retain_quarantined');self.license.status='expired';await self.db.commit()
        first=await self.post('offline-resolutions',data,owner=True);self.assertEqual(first.status_code,200,first.text)
        self.assertIsNone(first.json()['sale_id']);self.assertEqual(self.balance.quantity,100)
        self.assertEqual((await self.post('offline-resolutions',data,owner=True)).status_code,200)
        self.assertEqual((await self.post('offline-resolutions',data.model_copy(update={'action':'post_to_original_shift'}),owner=True)).status_code,409)
