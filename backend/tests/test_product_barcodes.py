import asyncio
import os
import unittest
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from app.models.product import Product
from app.products.schema import ProductCreate, ProductUpdate
from app.products.service import ProductService
from app.products.router import lookup_product_by_barcode
from app.auth.dependencies import AuthActor
from app.models.employee import Employee


class FakeBarcodeRepository:
    def __init__(self):
        self.products = []
        self.branch = SimpleNamespace(id=uuid4())

    async def get_by_create_request_key(self, *_args):
        return None

    async def get_category(self, *_args):
        return None

    async def resolve_branch(self, *_args):
        return self.branch

    async def find_product_conflict(
        self, company_id, sku, barcode, exclude_id=None,
    ):
        for product in self.products:
            if product.company_id != company_id or product.id == exclude_id:
                continue
            if sku and product.sku and product.sku.lower() == sku.lower():
                return product
            if barcode and product.barcode and product.barcode.strip() == barcode:
                return product
        return None

    async def create_product(self, product, **_kwargs):
        product.id = product.id or uuid4()
        self.products.append(product)
        return product

    async def get_product(self, company_id, product_id):
        return next(
            (p for p in self.products if p.company_id == company_id and p.id == product_id),
            None,
        )

    async def update_product(self, product, changes):
        for key, value in changes.items():
            setattr(product, key, value)
        return product

    async def find_active_by_barcode(self, company_id, barcode):
        return next(
            (
                p for p in self.products
                if p.company_id == company_id
                and p.active
                and not p.deleted
                and p.barcode
                and p.barcode.strip() == barcode
            ),
            None,
        )

    async def get_branch_stock_quantity(self, *_args):
        return Decimal("4.000")


def payload(company_id, barcode):
    return ProductCreate(
        company_id=company_id,
        branch_id=uuid4(),
        name="Barcode Product",
        barcode=barcode,
        unit="each",
        selling_price=Decimal("2.00"),
        stock_qty=Decimal("1"),
    )


class ProductBarcodeServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_trim_only_preserves_zeroes_case_and_internal_characters(self):
        repo = FakeBarcodeRepository()
        service = ProductService(repo)
        product = await service.create_product(
            payload(uuid4(), "  001 Ab-C/ 9  ")
        )
        self.assertEqual(product.barcode, "001 Ab-C/ 9")

    async def test_duplicate_rejected_in_company_but_case_is_distinct(self):
        company = uuid4()
        repo = FakeBarcodeRepository()
        service = ProductService(repo)
        await service.create_product(payload(company, " AbC-001 "))
        with self.assertRaisesRegex(HTTPException, "Barcode already exists"):
            await service.create_product(payload(company, "AbC-001"))
        second = await service.create_product(payload(company, "abc-001"))
        self.assertEqual(second.barcode, "abc-001")

    async def test_same_barcode_allowed_for_different_companies(self):
        repo = FakeBarcodeRepository()
        service = ProductService(repo)
        first = await service.create_product(payload(uuid4(), "00012345"))
        second = await service.create_product(payload(uuid4(), "00012345"))
        self.assertNotEqual(first.company_id, second.company_id)

    async def test_update_duplicate_is_rejected(self):
        company = uuid4()
        repo = FakeBarcodeRepository()
        service = ProductService(repo)
        first = await service.create_product(payload(company, "ONE"))
        await service.create_product(payload(company, "TWO"))
        with self.assertRaisesRegex(HTTPException, "Barcode already exists"):
            await service.update_product(
                company,
                first.id,
                ProductUpdate(barcode=" TWO "),
            )

    async def test_lookup_is_company_active_and_branch_scoped(self):
        company = uuid4()
        repo = FakeBarcodeRepository()
        service = ProductService(repo)
        product = await service.create_product(payload(company, "00001234"))
        result = await service.lookup_barcode(
            company, repo.branch.id, " 00001234 ",
        )
        self.assertEqual(result["id"], product.id)
        self.assertEqual(result["branch_id"], repo.branch.id)
        self.assertEqual(result["branch_stock_qty"], Decimal("4.000"))
        with self.assertRaisesRegex(HTTPException, "Product Not Found"):
            await service.lookup_barcode(uuid4(), repo.branch.id, "00001234")

    async def test_lookup_route_enforces_company_and_employee_branch(self):
        company = uuid4()
        branch = uuid4()
        other_branch = uuid4()
        actor = AuthActor(
            actor_type="employee",
            company_id=company,
            role="cashier",
            employee=Employee(
                id=uuid4(), company_id=company, shop_id=uuid4(),
                branch_id=branch, name="Cashier", pin="1234",
                role="cashier", active=True, deleted=False,
            ),
            permissions={"sales": True},
        )
        service = SimpleNamespace(lookup_barcode=lambda *_args: None)
        with self.assertRaisesRegex(HTTPException, "Forbidden"):
            await lookup_product_by_barcode(
                uuid4(), "ABC", branch, service, actor,
            )
        with self.assertRaisesRegex(HTTPException, "Branch access denied"):
            await lookup_product_by_barcode(
                company, "ABC", other_branch, service, actor,
            )


@unittest.skipUnless(
    os.getenv("APEX_BARCODE_TEST_DATABASE_URL"),
    "APEX_BARCODE_TEST_DATABASE_URL is required for PostgreSQL index tests",
)
class ProductBarcodePostgresTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine(
            os.environ["APEX_BARCODE_TEST_DATABASE_URL"]
        )
        self.company_one = uuid4()
        self.company_two = uuid4()

    async def asyncTearDown(self):
        async with self.engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM products WHERE company_id IN (:one, :two)"),
                {"one": self.company_one, "two": self.company_two},
            )
        await self.engine.dispose()

    async def insert(self, company_id, barcode):
        async with self.engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO products
                      (id, company_id, name, barcode, unit, stock_qty,
                       reorder_level, active, deleted)
                    VALUES
                      (:id, :company, 'Concurrent barcode', :barcode, 'each',
                       0, 0, true, false)
                    """
                ),
                {"id": uuid4(), "company": company_id, "barcode": barcode},
            )

    async def test_index_company_case_trim_and_concurrency(self):
        await self.insert(self.company_one, "Case")
        await self.insert(self.company_one, "case")
        await self.insert(self.company_two, "Case")

        results = await asyncio.gather(
            self.insert(self.company_one, " 00009999 "),
            self.insert(self.company_one, "00009999"),
            return_exceptions=True,
        )
        failures = [item for item in results if isinstance(item, IntegrityError)]
        self.assertEqual(len(failures), 1)


if __name__ == "__main__":
    unittest.main()
