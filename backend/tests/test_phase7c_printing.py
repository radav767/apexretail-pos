"""Printer service tests use a disposable PostgreSQL DB and outer rollbacks."""
import asyncio
import os
import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from types import SimpleNamespace

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from app.auth.dependencies import AuthActor
from app.employees.permissions import normalize_permissions
from app.employees.manager_approval import issue_manager_authorization
from app.employees.schema import ManagerAuthorizationCreate
from app.auth.security import hash_password
from app.models import Company, Shop, Branch, Device, Employee, PosSession, Product, Category, Sale, SaleItem, PrintJob, PrinterStation, AuditEvent
from app.printing.schema import StationInput, RouteInput, JobInput, ClaimInput, ResultInput, RetryInput, OfflineReviewInput
from app.printing.service import PrintingService, digest


class PrinterValidationTests(unittest.TestCase):
    def test_network_destinations_are_lan_only(self):
        data = dict(shop_id=uuid4(), branch_id=uuid4(), device_id=uuid4(), name="Kitchen", transport="network")
        for endpoint in ("127.0.0.1:9100", "169.254.169.254:9100", "8.8.8.8:9100", "localhost:9100", "192.168.1.1:22", "192.168.01.1:9100"):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValidationError): StationInput(**data, address=endpoint)
        for endpoint in ("10.0.0.5:9100", "172.16.1.2:9100", "192.168.1.50:9100"):
            self.assertEqual(StationInput(**data, address=endpoint).address, endpoint)

    def test_snapshot_hash_is_canonical(self):
        self.assertEqual(digest({"a": 1, "b": 2}), digest({"b": 2, "a": 1}))
        self.assertNotEqual(digest({"a": 1}), digest({"a": 2}))


class PrintingPostgresTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        url = os.getenv("APEX_PHASE7C_TEST_DATABASE_URL")
        if not url: self.skipTest("APEX_PHASE7C_TEST_DATABASE_URL is not configured")
        if not (make_url(url).database or "").startswith("apexretail_phase7c_test"):
            self.fail("Refusing non-disposable printing database")
        self.engine = create_async_engine(url)
        self.connection = await self.engine.connect()
        self.transaction = await self.connection.begin()
        self.db = AsyncSession(bind=self.connection, expire_on_commit=False, join_transaction_mode="create_savepoint")
        self.addAsyncCleanup(self.cleanup)
        self.company = Company(name="Synthetic Kitchen", owner_email=f"{uuid4()}@example.test")
        self.db.add(self.company); await self.db.flush()
        self.shop = Shop(company_id=self.company.id, name="Synthetic shop")
        self.db.add(self.shop); await self.db.flush()
        self.branch = Branch(company_id=self.company.id, shop_id=self.shop.id, name="Main")
        self.db.add(self.branch); await self.db.flush()
        self.device = Device(company_id=self.company.id, shop_id=self.shop.id, branch_id=self.branch.id, name="Till A", device_key=str(uuid4()))
        self.employee = Employee(company_id=self.company.id, shop_id=self.shop.id, branch_id=self.branch.id, name="Waiter", role="cashier", pin=hash_password("1234"), permissions=normalize_permissions("cashier", {}))
        self.category = Category(company_id=self.company.id, name="Food")
        self.db.add_all([self.device, self.employee, self.category]); await self.db.flush()
        self.product = Product(company_id=self.company.id, name="Synthetic meal", category_id=self.category.id, selling_price=12, stock_qty=100)
        self.sale = Sale(company_id=self.company.id, shop_id=self.shop.id, branch_id=self.branch.id, device_id=self.device.id, employee_id=self.employee.id,
            receipt_number=f"T-{uuid4()}", total_amount=12, subtotal_amount=12, status="completed", cashier_name="Waiter", created_at=datetime.now(timezone.utc))
        self.db.add_all([self.product, self.sale]); await self.db.flush()
        self.item = SaleItem(sale_id=self.sale.id, product_id=self.product.id, product_name=self.product.name, category_id_snapshot=self.category.id, quantity=1, unit_price=12, line_total=12)
        self.session = PosSession(company_id=self.company.id, shop_id=self.shop.id, branch_id=self.branch.id, device_id=self.device.id, employee_id=self.employee.id, token_hash=str(uuid4()), expires_at=datetime.now(timezone.utc)+timedelta(hours=1))
        self.db.add_all([self.item, self.session]); await self.db.commit()
        self.owner = AuthActor(actor_type="user", company_id=self.company.id, role="owner")
        self.cashier = AuthActor(actor_type="employee", company_id=self.company.id, role="cashier", employee=self.employee, permissions=self.employee.permissions, pos_session=self.session)
        self.svc = PrintingService(self.db, self.owner)
        self.pos = PrintingService(self.db, self.cashier)
        self.config = StationInput(shop_id=self.shop.id, branch_id=self.branch.id, device_id=self.device.id, name="Receipt", purpose="receipt", transport="system")
        self.station_id = (await self.svc.save_station(self.config))["id"]

    async def cleanup(self):
        await self.db.close()
        if self.transaction.is_active: await self.transaction.rollback()
        await self.connection.close(); await self.engine.dispose()

    async def receipt(self, **changes):
        return await self.pos.enqueue(self.station_id, JobInput(sale_id=self.sale.id, request_key="original", **changes))

    async def test_receipt_snapshot_and_financial_invariance(self):
        job = await self.receipt()
        self.assertEqual(job["payload"]["total_amount"], "12")
        self.assertEqual(job["payload_hash"], digest(job["payload"]))
        self.assertEqual(self.product.stock_qty, 100)
        self.assertEqual(self.sale.total_amount, 12)
        self.assertEqual(self.sale.reprint_count, 0)
        self.assertEqual(job["status"], "pending")

    async def test_double_enqueue_has_one_identity(self):
        a = await self.receipt(); b = await self.pos.enqueue(self.station_id, JobInput(sale_id=self.sale.id, request_key="another-click"))
        self.assertEqual(a["id"], b["id"])
        self.assertEqual(len((await self.db.execute(select(PrintJob).where(PrintJob.station_id == self.station_id))).scalars().all()), 1)
        self.cashier.permissions = {"sales_process": False}
        with self.assertRaises(HTTPException): await self.receipt()

    async def test_claim_result_retry_and_duplicate_protection(self):
        job = await self.receipt(); token = "a" * 32
        await self.pos.claim(job["id"], ClaimInput(token=token))
        with self.assertRaises(HTTPException): await self.pos.claim(job["id"], ClaimInput(token="b" * 32))
        with self.assertRaises(HTTPException): await self.pos.result(job["id"], ResultInput(token="b" * 32, outcome="submitted"))
        await self.pos.result(job["id"], ResultInput(token=token, outcome="submitted"))
        self.assertEqual((await self.pos.result(job["id"], ResultInput(token=token, outcome="submitted")))["status"], "submitted")
        with self.assertRaises(HTTPException): await self.svc.retry(job["id"], RetryInput(reason="Inspect paper"))

    async def test_uncertain_never_auto_retried(self):
        job = await self.receipt(); token = "a" * 32
        await self.pos.claim(job["id"], ClaimInput(token=token))
        await self.pos.result(job["id"], ResultInput(token=token, outcome="uncertain"))
        with self.assertRaises(HTTPException): await self.pos.claim(job["id"], ClaimInput(token=token))
        with self.assertRaises(HTTPException): await self.svc.retry(job["id"], RetryInput(reason="Checked printer"))
        row = await self.db.get(PrintJob, job["id"]); row.claimed_at -= timedelta(minutes=2); await self.db.flush()
        with self.assertRaises(HTTPException): await self.pos.retry(job["id"], RetryInput(reason="Checked printer"))
        result = await self.svc.retry(job["id"], RetryInput(reason="Confirmed no paper output"))
        self.assertEqual(result["status"], "pending")
        actions = (await self.db.execute(select(AuditEvent.action))).scalars().all()
        self.assertIn("print_retry_authorized", actions)

    async def test_authorized_retries_have_attempt_limit(self):
        job = await self.receipt(); token = "a" * 32
        for _ in range(5):
            await self.pos.claim(job["id"], ClaimInput(token=token))
            await self.pos.result(job["id"], ResultInput(token=token, outcome="uncertain"))
            row = await self.db.get(PrintJob, job["id"]); row.claimed_at -= timedelta(minutes=2); await self.db.flush()
            await self.svc.retry(job["id"], RetryInput(reason="Confirmed no paper output"))
        with self.assertRaises(HTTPException): await self.pos.claim(job["id"], ClaimInput(token=token))

    async def test_kitchen_category_and_product_routes_do_not_duplicate_items(self):
        config = self.config.model_copy(update={"purpose": "kitchen", "name": "Kitchen", "routes": [RouteInput(target_type="product", target_id=self.product.id), RouteInput(target_type="category", target_id=self.category.id)]})
        station = (await self.svc.save_station(config))["id"]
        job = await self.pos.enqueue(station, JobInput(sale_id=self.sale.id, kind="kot", request_key="kot", table="12", notes="Allergy", item_notes={self.item.id: "No nuts"}))
        self.assertEqual(len(job["payload"]["items"]), 1)
        self.assertEqual(job["payload"]["table"], "12")
        self.assertEqual(job["payload"]["items"][0]["notes"], "No nuts")
        self.assertNotIn("total_amount", job["payload"])
        self.assertEqual(job["payload"]["waiter"], "Waiter")

    async def test_no_route_means_no_kitchen_job(self):
        station = (await self.svc.save_station(self.config.model_copy(update={"purpose": "bar"})))["id"]
        with self.assertRaises(HTTPException): await self.pos.enqueue(station, JobInput(sale_id=self.sale.id, kind="kot", request_key="kot"))

    async def test_company_and_branch_and_register_isolation(self):
        with self.assertRaises(HTTPException): await self.svc.list_stations(uuid4())
        foreign = PrintingService(self.db, AuthActor(actor_type="user", company_id=uuid4(), role="owner"))
        with self.assertRaises(HTTPException): await foreign.station(self.station_id)
        self.cashier.pos_session = SimpleNamespace(device_id=uuid4())
        with self.assertRaises(HTTPException): await self.receipt()
        self.cashier.pos_session = self.session
        self.cashier.employee = SimpleNamespace(id=self.employee.id, branch_id=uuid4())
        with self.assertRaises(HTTPException): await self.receipt()

    async def test_reprints_permissions_and_manager_approval(self):
        self.cashier.permissions = {"sales_process": True, "sales_receipt_reprint": False}
        with self.assertRaises(HTTPException): await self.pos.enqueue(self.station_id, JobInput(sale_id=self.sale.id, request_key="reprint", reprint=True))
        manager = Employee(company_id=self.company.id, shop_id=self.shop.id, branch_id=self.branch.id, name="Manager", role="supervisor", pin=hash_password("9876"), permissions=normalize_permissions("supervisor", {}))
        self.db.add(manager); await self.db.commit()
        token = (await issue_manager_authorization(self.db, self.cashier, ManagerAuthorizationCreate(company_id=self.company.id, manager_pin="9876", action="receipt_reprint", reason="Customer copy", context={"sale_id": str(self.sale.id), "station_id": str(self.station_id)})))["authorization_token"]
        job = await self.pos.enqueue(self.station_id, JobInput(sale_id=self.sale.id, request_key="reprint", reprint=True, manager_authorization=token))
        self.assertTrue(job["payload"]["reprint"])
        # An identical retry returns the original result without consuming twice.
        same = await self.pos.enqueue(self.station_id, JobInput(sale_id=self.sale.id, request_key="reprint", reprint=True, manager_authorization=token))
        self.assertEqual(job["id"], same["id"])

    async def test_configuration_permission_and_foreign_targets(self):
        with self.assertRaises(HTTPException): await self.pos.save_station(self.config)
        with self.assertRaises(HTTPException): await self.svc.save_station(self.config.model_copy(update={"routes": [RouteInput(target_type="product", target_id=uuid4())]}))

    async def test_printer_changes_do_not_redirect_queued_job(self):
        job = await self.receipt()
        await self.svc.save_station(self.config.model_copy(update={"name": "Updated", "paper_width": "58mm"}), self.station_id)
        queued = await self.db.get(PrintJob, job["id"])
        self.assertEqual(queued.payload["printer"]["paper_width"], "80mm")
        self.assertEqual(queued.payload["printer"]["name"], "Receipt")

    async def test_mutated_snapshot_cannot_be_claimed(self):
        job = await self.receipt()
        row = await self.db.get(PrintJob, job["id"]); row.payload = {**row.payload, "title": "tampered"}; await self.db.flush()
        with self.assertRaises(HTTPException): await self.pos.claim(job["id"], ClaimInput(token="a" * 32))

    async def test_test_print_is_not_a_financial_transaction(self):
        job = await self.svc.enqueue(self.station_id, JobInput(kind="test", request_key="x" * 120))
        self.assertIsNone(job["sale_id"])
        self.assertEqual(job["payload"]["title"], "PRINTER TEST — NOT A SALE")
        self.assertEqual(self.product.stock_qty, 100)

    async def test_runtime_grants_protect_snapshot(self):
        values = (await self.db.execute(text("SELECT has_column_privilege('apex_user','print_jobs','payload','UPDATE'), has_column_privilege('apex_user','print_jobs','status','UPDATE'), has_table_privilege('apex_user','print_jobs','DELETE')"))).one()
        self.assertEqual(tuple(values), (False, True, False))

    async def test_offline_review_is_audited_without_financial_changes(self):
        await self.pos.offline_review(self.sale.id, OfflineReviewInput(reason="Paper output checked", decision="already_printed"))
        event = (await self.db.execute(select(AuditEvent).where(AuditEvent.action == "offline_print_reviewed", AuditEvent.company_id == self.company.id))).scalar_one()
        self.assertEqual(event.details["sale_id"], str(self.sale.id))
        self.assertEqual(self.product.stock_qty, 100)
        self.assertEqual(self.sale.total_amount, 12)

    async def test_offline_review_cannot_be_inherited(self):
        self.cashier.pos_session = SimpleNamespace(device_id=uuid4())
        with self.assertRaises(HTTPException): await self.pos.offline_review(self.sale.id, OfflineReviewInput(reason="Paper output checked", decision="already_printed"))

    async def test_next_cashier_cannot_read_or_claim_previous_jobs(self):
        job = await self.receipt()
        self.cashier.employee = SimpleNamespace(id=uuid4(), branch_id=self.branch.id)
        self.assertEqual(await self.pos.list_jobs(self.station_id), [])
        with self.assertRaises(HTTPException): await self.pos.claim(job["id"], ClaimInput(token="b" * 32))
        with self.assertRaises(HTTPException): await self.pos.enqueue(self.station_id, JobInput(sale_id=self.sale.id, request_key="original"))

    async def test_http_routes_require_authentication(self):
        import httpx
        from app.main import app
        from app.db.session import get_db
        async def db_override(): yield self.db
        app.dependency_overrides[get_db] = db_override
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                self.assertEqual((await client.get(f"/api/printing/stations/{self.company.id}")).status_code, 401)
                self.assertEqual((await client.post("/api/printing/stations", json={})).status_code, 401)
        finally: app.dependency_overrides.pop(get_db, None)

    async def test_z_parallel_requests_have_one_job_and_one_claim(self):
        # Commit only synthetic fixtures in the prefix-guarded disposable DB so
        # independent worker connections can exercise real PostgreSQL locks.
        await self.transaction.commit()
        async def enqueue():
            async with AsyncSession(self.engine, expire_on_commit=False) as db:
                return await PrintingService(db, self.owner).enqueue(self.station_id, JobInput(sale_id=self.sale.id, request_key="parallel"))
        a, b = await asyncio.gather(enqueue(), enqueue())
        self.assertEqual(a["id"], b["id"])
        async def claim(token):
            async with AsyncSession(self.engine, expire_on_commit=False) as db:
                try:
                    await PrintingService(db, self.owner).claim(a["id"], ClaimInput(token=token))
                    return "claimed"
                except HTTPException as error:
                    await db.rollback()
                    return error.status_code
        self.assertCountEqual(await asyncio.gather(claim("a" * 32), claim("b" * 32)), ["claimed", 409])
