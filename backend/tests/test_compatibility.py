import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
import inspect
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
import httpx

from app.auth.dependencies import (
    AuthActor,
    get_auth_actor,
    get_optional_auth_actor,
    require_billable_body_company,
    require_billable_path_company,
)
from app.db.session import get_db
from app.devices.router import get_service as get_device_service
from app.inventory.router import get_service as get_inventory_service
from app.inventory.service import (
    InventoryService,
    LEGACY_GRN_REASON,
)
from app.inventory.schema import GRNCreate
from app.main import app
from app.models.branch import Branch
from app.models.employee import Employee
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.products.repository import ProductRepository
from app.products.router import get_service as get_product_service
from app.products.schema import ProductCreate
from app.products.service import ProductService
from app.sales.router import get_service as get_sales_service


@contextmanager
def dependency_overrides(overrides):
    original = dict(app.dependency_overrides)

    normalized = {}

    for dependency, override in overrides.items():
        if inspect.iscoroutinefunction(override):
            normalized[dependency] = override
            continue

        async def async_wrapper(_override=override):
            return _override()

        normalized[dependency] = async_wrapper

    app.dependency_overrides.update(normalized)
    try:
        yield
    finally:
        app.dependency_overrides = original


async def allow_billable_company():
    return None


class FakeAsyncDb:
    def __init__(self):
        self.added = []

    def add(self, value):
        self.added.append(value)

    def add_all(self, values):
        self.added.extend(values)

    async def flush(self):
        return None

    async def commit(self):
        return None

    async def refresh(self, _value):
        return None

    async def rollback(self):
        return None


class ProductRepositoryOpeningStockTest(unittest.IsolatedAsyncioTestCase):
    async def test_opening_stock_creates_one_branch_balance(self):
        company_id = uuid4()
        branch_one = Branch(
            id=uuid4(),
            company_id=company_id,
            shop_id=uuid4(),
            name="Main Branch",
            active=True,
            deleted=False,
        )
        branch_two = Branch(
            id=uuid4(),
            company_id=company_id,
            shop_id=uuid4(),
            name="Second Branch",
            active=True,
            deleted=False,
        )

        class TestRepo(ProductRepository):
            async def list_active_branches(self, _company_id):
                return [branch_one, branch_two]

        fake_db = FakeAsyncDb()
        repo = TestRepo(fake_db)

        async def fake_sync_product_total(product):
            total = Decimal("0")
            for item in fake_db.added:
                if (
                    isinstance(item, InventoryBalance)
                    and item.product_id == product.id
                ):
                    total += Decimal(item.quantity or 0)
            product.stock_qty = total
            return total

        repo.stock = SimpleNamespace(
            sync_product_total=fake_sync_product_total
        )

        product = Product(
            id=uuid4(),
            company_id=company_id,
            name="Sugar",
            unit="each",
            cost_price=Decimal("1.25"),
            selling_price=Decimal("2.00"),
            reorder_level=Decimal("3"),
            stock_qty=Decimal("0"),
            active=True,
            deleted=False,
        )

        await repo.create_product(
            product,
            opening_quantity=Decimal("7"),
            branch_id=branch_one.id,
        )

        balances = [
            item
            for item in fake_db.added
            if isinstance(item, InventoryBalance)
        ]
        movements = [
            item
            for item in fake_db.added
            if isinstance(item, InventoryMovement)
        ]

        self.assertEqual(len(balances), 1)
        self.assertEqual(balances[0].branch_id, branch_one.id)
        self.assertEqual(balances[0].quantity, Decimal("7"))
        self.assertEqual(len(movements), 1)
        self.assertEqual(movements[0].movement_type, "opening_stock")


class ProductServiceIdempotencyTest(unittest.IsolatedAsyncioTestCase):
    async def test_retry_does_not_duplicate_product_or_quantity(self):
        company_id = uuid4()
        create_key = "idem-product-001"
        product_id = uuid4()

        class FakeRepo:
            def __init__(self):
                self.saved_by_key = {}
                self.create_calls = 0
                self.opening_stock_applied = Decimal("0")

            async def get_by_create_request_key(
                self,
                _company_id,
                key,
            ):
                return self.saved_by_key.get(key)

            async def get_category(self, *_args, **_kwargs):
                return None

            async def find_product_conflict(self, *_args, **_kwargs):
                return None

            async def resolve_branch(self, company_id_arg, branch_id):
                return SimpleNamespace(
                    id=branch_id,
                    company_id=company_id_arg,
                )

            async def create_product(
                self,
                product,
                *,
                opening_quantity,
                branch_id,
            ):
                self.create_calls += 1
                product.id = product_id
                product.branch_id = branch_id
                product.stock_qty = opening_quantity
                self.opening_stock_applied += opening_quantity
                self.saved_by_key[product.create_request_key] = product
                return product

        repo = FakeRepo()
        service = ProductService(repo)
        payload = ProductCreate(
            company_id=company_id,
            branch_id=uuid4(),
            create_request_key=create_key,
            name="Rice",
            unit="each",
            cost_price=Decimal("5"),
            selling_price=Decimal("8"),
            stock_qty=Decimal("10"),
            reorder_level=Decimal("2"),
        )

        first = await service.create_product(payload)
        second = await service.create_product(payload)

        self.assertEqual(repo.create_calls, 1)
        self.assertEqual(repo.opening_stock_applied, Decimal("10"))
        self.assertEqual(first.id, second.id)


class InventoryServiceCompatibilityTest(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_grn_without_reason_uses_default_reason(self):
        company_id = uuid4()
        branch_id = uuid4()
        product_id = uuid4()
        captured = {}

        class FakeRepo:
            async def resolve_branch(self, *_args, **_kwargs):
                return SimpleNamespace(id=branch_id, shop_id=uuid4())

            async def get_product_for_update(self, *_args, **_kwargs):
                return SimpleNamespace(
                    id=product_id,
                    name="Mealie Meal",
                    cost_price=Decimal("12.00"),
                )

            async def get_balance_for_update(
                self,
                *_args,
                **_kwargs,
            ):
                return SimpleNamespace(quantity=Decimal("4"))

            async def sync_product_total(self, _product):
                return Decimal("7")

            async def apply_movement(
                self,
                _product,
                _balance,
                movement,
            ):
                captured["reason"] = movement.reason
                return movement

        service = InventoryService(FakeRepo())

        movement = await service.receive_stock(
            GRNCreate(
                company_id=company_id,
                branch_id=branch_id,
                product_id=product_id,
                quantity=Decimal("3"),
                reason=None,
            )
        )

        self.assertEqual(
            captured["reason"],
            LEGACY_GRN_REASON,
        )
        self.assertEqual(movement.reason, LEGACY_GRN_REASON)


class RouteCompatibilityTest(unittest.IsolatedAsyncioTestCase):
    async def request(self, method: str, path: str, **kwargs):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.request(method, path, **kwargs)

    async def test_legacy_sale_without_bearer_header_uses_legacy_flow(self):
        company_id = uuid4()
        branch_id = uuid4()
        employee_id = uuid4()
        product_id = uuid4()
        recorded = {}

        class FakeSalesService:
            async def create_sale(self, data, *, actor):
                recorded["actor"] = actor
                recorded["employee_id"] = data.employee_id
                return {
                    "id": str(uuid4()),
                    "company_id": str(data.company_id),
                    "client_sale_id": None,
                    "client_created_at": None,
                    "shop_id": str(uuid4()),
                    "branch_id": str(data.branch_id),
                    "employee_id": str(data.employee_id),
                    "cashier_name": "Cashier",
                    "receipt_number": "APR-20260818-LEGACY01",
                    "subtotal_amount": "10.00",
                    "tax_name": "Tax",
                    "tax_rate": "0.000",
                    "tax_amount": "0.00",
                    "tax_inclusive": False,
                    "total_amount": "10.00",
                    "amount_received": "10.00",
                    "change_due": "0.00",
                    "payment_method": "cash",
                    "status": "completed",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }

        with dependency_overrides(
            {
                get_sales_service: lambda: FakeSalesService(),
                get_optional_auth_actor: lambda: None,
                require_billable_body_company: allow_billable_company,
            }
        ):
            response = await self.request(
                "POST",
                "/api/sales",
                json={
                    "company_id": str(company_id),
                    "branch_id": str(branch_id),
                    "employee_id": str(employee_id),
                    "payment_method": "cash",
                    "amount_received": "10.00",
                    "items": [
                        {
                            "product_id": str(product_id),
                            "quantity": "1",
                        }
                    ],
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(recorded["actor"])
        self.assertEqual(
            recorded["employee_id"],
            employee_id,
        )

    async def test_unauthorized_product_management_is_rejected(self):
        company_id = uuid4()

        async def denied_actor():
            return AuthActor(
                actor_type="employee",
                company_id=company_id,
                role="cashier",
                employee=Employee(
                    id=uuid4(),
                    company_id=company_id,
                    shop_id=uuid4(),
                    branch_id=uuid4(),
                    name="Cashier",
                    pin="1234",
                    role="cashier",
                    permissions={"sales": True},
                    active=True,
                    deleted=False,
                ),
                permissions={
                    "sales": True,
                    "manage_products": False,
                    "manage_inventory": False,
                },
            )

        class FakeProductService:
            async def create_product(self, _data):
                raise AssertionError("must not be called")

        with dependency_overrides(
            {
                get_auth_actor: denied_actor,
                get_product_service: lambda: FakeProductService(),
                require_billable_body_company: allow_billable_company,
            }
        ):
            response = await self.request(
                "POST",
                "/api/products",
                json={
                    "company_id": str(company_id),
                    "name": "Soap",
                    "unit": "each",
                    "cost_price": "1.00",
                    "selling_price": "2.00",
                    "stock_qty": "1",
                    "reorder_level": "0",
                },
            )

        self.assertEqual(response.status_code, 403)

    async def test_owner_product_access_succeeds(self):
        company_id = uuid4()

        async def owner_actor():
            return AuthActor(
                actor_type="user",
                company_id=company_id,
                role="owner",
                permissions=None,
            )

        class FakeProductService:
            async def create_product(self, data):
                return {
                    "id": str(uuid4()),
                    "company_id": str(data.company_id),
                    "category_id": None,
                    "name": data.name,
                    "sku": None,
                    "barcode": None,
                    "unit": data.unit,
                    "cost_price": "1.00",
                    "selling_price": "2.00",
                    "stock_qty": "5.000",
                    "reorder_level": "1.000",
                    "active": True,
                }

        with dependency_overrides(
            {
                get_auth_actor: owner_actor,
                get_product_service: lambda: FakeProductService(),
                require_billable_body_company: allow_billable_company,
            }
        ):
            response = await self.request(
                "POST",
                "/api/products",
                json={
                    "company_id": str(company_id),
                    "create_request_key": "owner-create-1",
                    "name": "Soap",
                    "unit": "each",
                    "cost_price": "1.00",
                    "selling_price": "2.00",
                    "stock_qty": "5",
                    "reorder_level": "1",
                },
            )

        self.assertEqual(response.status_code, 200)

    async def test_permitted_employee_inventory_access_succeeds(self):
        company_id = uuid4()
        branch_id = uuid4()
        product_id = uuid4()

        async def inventory_actor():
            return AuthActor(
                actor_type="employee",
                company_id=company_id,
                role="manager",
                employee=Employee(
                    id=uuid4(),
                    company_id=company_id,
                    shop_id=uuid4(),
                    branch_id=branch_id,
                    name="Manager",
                    pin="1234",
                    role="manager",
                    permissions={"manage_inventory": True},
                    active=True,
                    deleted=False,
                ),
                permissions={
                    "sales": True,
                    "manage_products": True,
                    "manage_inventory": True,
                },
            )

        class FakeInventoryService:
            async def receive_stock(self, data):
                return {
                    "id": str(uuid4()),
                    "company_id": str(data.company_id),
                    "shop_id": str(uuid4()),
                    "branch_id": str(data.branch_id),
                    "product_id": str(data.product_id),
                    "product_name": "Flour",
                    "movement_type": "grn",
                    "quantity": str(data.quantity),
                    "before_qty": "0.000",
                    "after_qty": str(data.quantity),
                    "unit_cost": "4.50",
                    "reference": None,
                    "supplier": None,
                    "reason": data.reason,
                    "notes": None,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }

        with dependency_overrides(
            {
                get_auth_actor: inventory_actor,
                get_inventory_service: lambda: FakeInventoryService(),
                require_billable_body_company: allow_billable_company,
            }
        ):
            response = await self.request(
                "POST",
                "/api/inventory/grn",
                json={
                    "company_id": str(company_id),
                    "branch_id": str(branch_id),
                    "product_id": str(product_id),
                    "quantity": "4",
                    "reason": "New stock",
                },
            )

        self.assertEqual(response.status_code, 200)

    async def test_unauthorized_device_activation_request_is_rejected(self):
        company_id = uuid4()
        recorded = {"called": False}

        async def denied_actor():
            return AuthActor(
                actor_type="employee",
                company_id=company_id,
                role="cashier",
                employee=Employee(
                    id=uuid4(),
                    company_id=company_id,
                    shop_id=uuid4(),
                    branch_id=uuid4(),
                    name="Cashier",
                    pin="1234",
                    role="cashier",
                    permissions={"sales": True, "settings": False},
                    active=True,
                    deleted=False,
                ),
                permissions={
                    "sales": True,
                    "settings": False,
                },
            )

        class FakeDeviceService:
            async def request_activation(self, _data):
                recorded["called"] = True
                raise AssertionError("must not be called")

        with dependency_overrides(
            {
                get_auth_actor: denied_actor,
                get_device_service: lambda: FakeDeviceService(),
                require_billable_body_company: allow_billable_company,
            }
        ):
            response = await self.request(
                "POST",
                "/api/devices/activate/request",
                json={
                    "company_id": str(company_id),
                    "friendly_name": "Counter 1",
                    "pos_number": 1,
                    "shop_id": str(uuid4()),
                    "branch_id": str(uuid4()),
                },
            )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(recorded["called"])

    async def test_unauthorized_shop_settings_write_is_rejected(self):
        company_id = uuid4()
        shop_id = uuid4()
        recorded = {"called": False}

        async def denied_actor():
            return AuthActor(
                actor_type="employee",
                company_id=company_id,
                role="cashier",
                employee=Employee(
                    id=uuid4(),
                    company_id=company_id,
                    shop_id=shop_id,
                    branch_id=uuid4(),
                    name="Cashier",
                    pin="1234",
                    role="cashier",
                    permissions={"sales": True, "settings": False},
                    active=True,
                    deleted=False,
                ),
                permissions={
                    "sales": True,
                    "settings": False,
                },
            )

        class FakeDb:
            async def execute(self, *_args, **_kwargs):
                recorded["called"] = True
                raise AssertionError("must not be called")

        with dependency_overrides(
            {
                get_auth_actor: denied_actor,
                get_db: lambda: FakeDb(),
                require_billable_path_company: allow_billable_company,
            }
        ):
            response = await self.request(
                "PATCH",
                f"/api/settings/shops/{company_id}/{shop_id}",
                json={
                    "address_line_1": "12 Main Street",
                    "city": "Harare",
                },
            )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(recorded["called"])

    async def test_sale_receipt_endpoint_returns_items_for_reprint(self):
        company_id = uuid4()
        sale_id = uuid4()
        recorded = {}

        async def sales_actor():
            return AuthActor(
                actor_type="employee",
                company_id=company_id,
                role="cashier",
                employee=Employee(
                    id=uuid4(),
                    company_id=company_id,
                    shop_id=uuid4(),
                    branch_id=uuid4(),
                    name="Cashier",
                    pin="1234",
                    role="cashier",
                    permissions={"sales": True},
                    active=True,
                    deleted=False,
                ),
                permissions={
                    "sales": True,
                    "manage_products": False,
                    "manage_inventory": False,
                },
            )

        class FakeSalesService:
            async def get_sale_receipt(
                self,
                requested_company_id,
                requested_sale_id,
                *,
                actor,
            ):
                recorded["company_id"] = requested_company_id
                recorded["sale_id"] = requested_sale_id
                recorded["actor"] = actor

                return {
                    "id": str(sale_id),
                    "company_id": str(company_id),
                    "client_sale_id": None,
                    "client_created_at": None,
                    "shop_id": str(uuid4()),
                    "branch_id": str(uuid4()),
                    "employee_id": str(uuid4()),
                    "cashier_name": "Cashier",
                    "receipt_number": "APR-20260818-REPRINT01",
                    "subtotal_amount": "10.00",
                    "tax_name": "Tax",
                    "tax_rate": "15.000",
                    "tax_amount": "1.50",
                    "tax_inclusive": False,
                    "total_amount": "11.50",
                    "amount_received": "20.00",
                    "change_due": "8.50",
                    "payment_method": "cash",
                    "status": "completed",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "items": [
                        {
                            "id": str(uuid4()),
                            "product_id": str(uuid4()),
                            "product_name": "Bread",
                            "quantity": "1.000",
                            "unit_price": "10.00",
                            "line_total": "10.00",
                        }
                    ],
                }

        with dependency_overrides(
            {
                get_optional_auth_actor: sales_actor,
                get_sales_service: lambda: FakeSalesService(),
            }
        ):
            response = await self.request(
                "GET",
                f"/api/sales/receipt/{company_id}/{sale_id}",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(recorded["company_id"], company_id)
        self.assertEqual(recorded["sale_id"], sale_id)
        self.assertIsNotNone(recorded["actor"])
        self.assertEqual(
            response.json()["receipt_number"],
            "APR-20260818-REPRINT01",
        )
        self.assertEqual(len(response.json()["items"]), 1)
