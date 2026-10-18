import unittest
import io
import zipfile
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from app.products.import_preview import preview
from app.products.media import store
from app.products.schema import ProductImportRequest
from app.products.service import ProductService
from app.sales.schema import SaleCreate, SaleItemCreate
from app.sales.service import SalesService
from tests.test_weighted_sales_and_subscriptions import FakeSalesRepo


SETTINGS = {
    "tax_name": "VAT",
    "tax_rate": Decimal("0"),
    "tax_inclusive": False,
    "receipt_footer": "Thank you",
}


class VariantSalesRepo(FakeSalesRepo):
    def __init__(self):
        super().__init__()
        self.product.product_type = "standard"
        self.product.track_inventory = True
        self.product.tax_rate = Decimal("15")
        self.product.tax_exempt = False
        self.variant = SimpleNamespace(
            id=uuid4(), name="Large / Green", selling_price=Decimal("6.00"),
            cost_price=Decimal("3.00"), active=True,
        )
        self.variant_balance = SimpleNamespace(quantity=Decimal("8.000"))
        self.customer = None
        self.level = None

    async def get_variant(self, _company_id, product_id, variant_id):
        if product_id == self.product.id and variant_id == self.variant.id:
            return self.variant
        return None

    async def get_variant_balance(self, *_args):
        return self.variant_balance

    async def get_product_components(self, *_args):
        return []

    async def get_category_name(self, *_args):
        return None

    async def get_customer_for_update(self, *_args):
        return self.customer

    async def get_price_level(self, *_args):
        return self.level


class Phase7A1SaleTests(unittest.IsolatedAsyncioTestCase):
    async def test_variant_sale_uses_variant_price_and_deducts_exactly_once(self):
        repo = VariantSalesRepo()
        payload = SaleCreate(
            company_id=uuid4(), client_sale_id=uuid4(), payment_method="card",
            items=[SaleItemCreate(
                product_id=repo.product.id, variant_id=repo.variant.id,
                quantity="2", unit_price="6.00", line_total="12.00",
            )],
        )
        with patch("app.sales.service.BusinessSettingsService.get", return_value=SETTINGS):
            sale = await SalesService(repo).create_sale(payload, actor=None)

        self.assertEqual(repo.variant_balance.quantity, Decimal("6.000"))
        self.assertEqual(sale.total_amount, Decimal("13.80"))
        item = repo.saved["items"][0]
        self.assertEqual(item.variant_id, repo.variant.id)
        self.assertEqual(item.variant_name_snapshot, "Large / Green")
        self.assertEqual(item.tax_amount, Decimal("1.80"))
        movement = repo.saved["movements"][0]
        self.assertEqual(movement.movement_type, "variant_sale")
        self.assertEqual(movement.variant_id, repo.variant.id)

        repo.get_by_client_sale_id = AsyncMock(return_value=sale)
        with patch("app.sales.service.BusinessSettingsService.get", return_value=SETTINGS):
            replay = await SalesService(repo).create_sale(payload, actor=None)
        self.assertIs(replay, sale)
        self.assertEqual(repo.variant_balance.quantity, Decimal("6.000"))

    async def test_customer_price_level_is_server_authoritative_without_receivable(self):
        repo = VariantSalesRepo()
        repo.product.tax_rate = None
        repo.customer = SimpleNamespace(
            id=uuid4(), name="Wholesale Buyer", customer_code="W001",
            price_level_name="Wholesale", credit_enabled=False,
            unlimited_credit=False, credit_limit=None, credit_terms_days=0,
        )
        repo.level = SimpleNamespace(name="Wholesale", price=Decimal("4.50"))
        shift = SimpleNamespace(
            id=uuid4(), device_id=None, employee_id=None,
            shop_name_snapshot="Main Shop", branch_name_snapshot="Front",
        )
        actor = SimpleNamespace(
            company_id=uuid4(), actor_type="user", role="owner",
            permissions={}, user=SimpleNamespace(id=uuid4()), employee=None,
        )
        payload = SaleCreate(
            company_id=actor.company_id, customer_id=repo.customer.id,
            payment_method="cash", amount_received="4.50",
            items=[SaleItemCreate(
                product_id=repo.product.id, quantity="1",
                unit_price="999.00", line_total="999.00",
            )],
        )
        with patch("app.sales.service.BusinessSettingsService.get", return_value=SETTINGS):
            sale = await SalesService(repo).create_sale(
                payload, actor=actor, resolved_shift=shift,
            )
        self.assertEqual(sale.total_amount, Decimal("4.50"))
        self.assertEqual(sale.price_level_name_snapshot, "Wholesale")
        self.assertEqual(repo.saved["items"][0].unit_price, Decimal("4.50"))
        self.assertEqual(repo.saved["items"][0].price_level_name_snapshot, "Wholesale")


@pytest.mark.asyncio
async def test_csv_import_preview_reports_valid_and_invalid_rows():
    upload = SimpleNamespace(
        filename="products.csv",
        read=AsyncMock(return_value=(
            b"name,sku,selling_price,stock_qty,variant_name,variant_sku\n"
            b"T Shirt,TSHIRT,12.50,5,Small,TS-S\n"
            b",BROKEN,4.00,2,,\n"
        )),
    )
    result = await preview(upload)
    assert result["total_rows"] == 2
    assert result["valid_rows"] == 1
    assert result["rows"][0]["values"]["variant_name"] == "Small"
    assert result["rows"][1]["errors"]


@pytest.mark.asyncio
async def test_xlsx_import_preview_supports_inline_excel_strings():
    workbook = io.BytesIO()
    with zipfile.ZipFile(workbook, "w") as archive:
        archive.writestr("xl/worksheets/sheet1.xml", """<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>name</t></is></c><c r="B1" t="inlineStr"><is><t>sku</t></is></c></row><row r="2"><c r="A2" t="inlineStr"><is><t>Excel Product</t></is></c><c r="B2" t="inlineStr"><is><t>XLS-1</t></is></c></row></sheetData></worksheet>""")
    upload = SimpleNamespace(filename="products.xlsx", read=AsyncMock(return_value=workbook.getvalue()))
    result = await preview(upload)
    assert result["valid_rows"] == 1
    assert result["rows"][0]["values"]["name"] == "Excel Product"


@pytest.mark.asyncio
async def test_product_media_rejects_cross_tenant_product_and_spoofed_image():
    foreign_repo = SimpleNamespace(get_product=AsyncMock(return_value=None))
    missing = SimpleNamespace(
        filename="photo.png", content_type="image/png",
        read=AsyncMock(return_value=b"\x89PNG\r\n\x1a\ncontent"),
    )
    with pytest.raises(Exception) as error:
        await store(foreign_repo, uuid4(), uuid4(), missing)
    assert getattr(error.value, "status_code", None) == 404

    product_repo = SimpleNamespace(
        get_product=AsyncMock(return_value=SimpleNamespace(image_url=None))
    )
    spoofed = SimpleNamespace(
        filename="photo.png", content_type="image/png",
        read=AsyncMock(return_value=b"not-a-png"),
    )
    with pytest.raises(Exception) as error:
        await store(product_repo, uuid4(), uuid4(), spoofed)
    assert getattr(error.value, "status_code", None) == 415


@pytest.mark.asyncio
async def test_variant_import_does_not_duplicate_parent_opening_stock():
    company_id, branch_id, product_id = uuid4(), uuid4(), uuid4()
    service = ProductService(SimpleNamespace(get_category_by_name=AsyncMock(return_value=None)))
    service.create_product = AsyncMock(return_value=SimpleNamespace(id=product_id))
    service.create_variant = AsyncMock()
    data = ProductImportRequest.model_validate({
        "company_id": company_id,
        "branch_id": branch_id,
        "rows": [
            {"name": "T Shirt", "sku": "TS", "stock_qty": "99", "variant_name": "Small", "variant_sku": "TS-S", "variant_stock_qty": "4"},
            {"name": "T Shirt", "sku": "TS", "stock_qty": "99", "variant_name": "Large", "variant_sku": "TS-L", "variant_stock_qty": "7"},
        ],
    })
    await service.import_products(data)
    parent = service.create_product.await_args.args[0]
    assert parent.stock_qty == Decimal("0")
    assert service.create_product.await_count == 1
    assert service.create_variant.await_count == 2

