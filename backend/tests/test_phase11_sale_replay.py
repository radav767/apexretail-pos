"""Real API/service paths, synthetic PostgreSQL fixtures and outer rollbacks."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4
import unittest
from fastapi import HTTPException
import httpx
from sqlalchemy import select, func, text
from sqlalchemy.exc import DBAPIError
from app.models import CompanySubscription, Sale, InventoryMovement, SaleCommandReceipt, Company, User, Branch
from app.auth.security import create_access_token, create_employee_access_token
from app.auth.dependencies import AuthActor
from app.db.session import get_db
from app.main import app
from app.sales.service import SalesService
from app.sales.repository import SalesRepository
from app.sales.schema import SaleCreate, SaleItemCreate
import test_phase7d_operations as fixtures


class SaleReplayTests(unittest.IsolatedAsyncioTestCase):
    cleanup = fixtures.Phase7DOperationsTests.cleanup

    async def asyncSetUp(self):
        await fixtures.Phase7DOperationsTests.asyncSetUp(self)
        self.license = (await self.db.execute(select(CompanySubscription).where(CompanySubscription.company_id==self.company.id))).scalar_one()
        self.license.status='trial'; self.license.trial_ends_at=datetime.now(timezone.utc)+timedelta(days=1); self.license.commercial_terms=None
        await self.db.commit()
        self.sales = SalesService(SalesRepository(self.db))
        async def override(): yield self.db
        app.dependency_overrides[get_db] = override; self.addCleanup(app.dependency_overrides.clear)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://synthetic.test')
        self.addAsyncCleanup(self.client.aclose)
        self.headers = {'Authorization': 'Bearer '+create_access_token(str(self.user.id), self.user.email)}

    def command(self, **changes):
        values = dict(company_id=self.company.id, branch_id=self.branch.id, device_id=self.device.id,
                      employee_id=self.employee.id, client_sale_id=uuid4(), amount_received=Decimal('100'),
                      items=[SaleItemCreate(product_id=self.product.id, quantity='2')])
        values.update(changes); return SaleCreate(**values)

    async def submit(self, data, headers=None):
        return await self.client.post('/api/sales', headers=headers or self.headers, json=data.model_dump(mode='json'))

    async def test_exact_committed_replay_after_expiry_and_plan_change_does_not_repeat_effects(self):
        data = self.command()
        first = await self.submit(data); self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(self.balance.quantity, 98)
        self.license.status = 'suspended'; self.license.commercial_terms = {'features': {}}
        self.product.selling_price = 999; await self.db.commit()
        replay = await self.submit(data)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json()['id'], first.json()['id'])
        self.assertEqual(self.balance.quantity, 98)
        self.assertEqual((await self.db.execute(select(func.count(Sale.id)).where(Sale.company_id==self.company.id))).scalar_one(), 2)
        self.assertEqual((await self.db.execute(select(func.count(InventoryMovement.id)).where(InventoryMovement.company_id==self.company.id))).scalar_one(), 1)
        changed = data.model_copy(update={'amount_received': Decimal('101')})
        self.assertEqual((await self.submit(changed)).status_code, 409)
        self.assertEqual((await self.submit(self.command())).status_code, 402)

    async def test_new_queued_or_direct_service_write_needs_current_license_without_changing_timestamp(self):
        self.license.status='expired'; await self.db.commit()
        data=self.command(client_created_at=datetime.now(timezone.utc)-timedelta(hours=1))
        self.assertEqual((await self.submit(data)).status_code, 402)
        with self.assertRaises(HTTPException) as error: await self.sales.create_sale(data, actor=self.owner)
        self.assertEqual(error.exception.status_code, 402)
        self.assertIsNotNone(data.client_created_at)
        self.assertEqual(self.balance.quantity, 100)
        self.assertEqual((await self.db.execute(select(func.count(SaleCommandReceipt.client_sale_id)).where(SaleCommandReceipt.company_id==self.company.id))).scalar_one(), 0)
        with self.assertRaises(HTTPException) as error: await self.sales.create_sale(self.command(), actor=None)
        self.assertEqual(error.exception.status_code, 401)

    async def test_legacy_identity_requires_lookup_and_receipts_are_immutable(self):
        key=uuid4(); self.sale.client_sale_id=key; await self.db.commit()
        result=await self.submit(self.command(client_sale_id=key))
        self.assertEqual(result.status_code, 409)
        self.license.status='expired'; self.license.commercial_terms={'features': {}}; await self.db.commit()
        result=await self.client.get(f'/api/sales/by-client-id/{self.company.id}/{key}', headers=self.headers)
        self.assertEqual(result.status_code, 200, result.text)
        self.license.status='trial'; self.license.commercial_terms=None; await self.db.commit()
        self.assertEqual((await self.submit(self.command())).status_code, 200)
        with self.assertRaises(DBAPIError):
            async with self.db.begin_nested(): await self.db.execute(text('UPDATE sale_command_receipts SET payload_hash=payload_hash'))

    async def test_actor_branch_register_and_feature_checks_survive_replay_exception(self):
        data=self.command(); first=await self.submit(data); self.assertEqual(first.status_code, 200, first.text)
        another=User(company_id=self.company.id, email=f'{uuid4()}@example.com', password_hash='synthetic', role='owner')
        self.db.add(another); await self.db.commit()
        headers={'Authorization': 'Bearer '+create_access_token(str(another.id), another.email)}
        self.assertEqual((await self.submit(data, headers)).status_code, 403)
        self.device.assignment_revision += 1; await self.db.commit()
        self.assertEqual((await self.submit(data)).status_code, 403)
        self.license.commercial_terms={'features': {}}; self.product.product_type='composite'; await self.db.commit()
        self.assertEqual((await self.submit(self.command())).status_code, 403)
        self.assertEqual(self.balance.quantity, 98)

    async def test_historical_financial_read_is_not_hidden_by_plan_removal(self):
        self.license.status='expired'; self.license.commercial_terms={'features': {}}; await self.db.commit()
        result=await self.client.get(f'/api/reports/financial-summary/{self.company.id}?date_from=2026-01-01&date_to=2026-12-31', headers=self.headers)
        self.assertEqual(result.status_code, 200, result.text)
