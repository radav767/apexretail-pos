import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from pydantic import ValidationError
from app.sales.schema import SaleCreate, SaleItemCreate, RefundCreate, RefundItemCreate
from app.sales.service import SalesService
from tests.test_weighted_sales_and_subscriptions import FakeSalesRepo
from tests.test_sales_history_actions import RecordingDB


class DiscountCheckoutTest(unittest.IsolatedAsyncioTestCase):
    async def checkout(self, discount="0.20", paid="0.80"):
        repo = FakeSalesRepo()
        payload = SaleCreate(company_id=uuid4(), client_sale_id=uuid4(),
            payment_method="card", discount_amount=discount,
            items=[SaleItemCreate(product_id=repo.product.id, quantity="0.250",
                                  unit_price="4.00", line_total=paid)])
        with patch("app.sales.service.BusinessSettingsService.get", return_value={
            "tax_rate": Decimal("0"), "tax_inclusive": False,
        }):
            sale = await SalesService(repo).create_sale(payload, actor=None)
        return repo, payload, sale

    async def test_offline_retry_preserves_original_snapshot_and_stock(self):
        for discount in (None, "0", "0.20"):
            repo, payload, sale = await self.checkout(discount, "1" if discount == "0" else "0.80")
            quantity = repo.balance.quantity
            repo.get_by_client_sale_id = AsyncMock(return_value=sale)
            replay = SaleCreate.model_validate_json(payload.model_dump_json())
            result = await SalesService(repo).create_sale(replay, actor=None)
            self.assertIs(result, sale)
            self.assertEqual(repo.balance.quantity, quantity)
            self.assertEqual(result.discount_amount, None if discount is None else Decimal(discount))

    async def test_refund_uses_discounted_line_and_preserves_original_discount(self):
        repo, payload, original = await self.checkout()
        item = repo.saved["items"][0]
        item.id = uuid4()
        repo.db = RecordingDB()
        repo.get_sale_for_update = AsyncMock(return_value=original)
        repo.get_sale_items = AsyncMock(return_value=[item])
        repo.list_refund_items_for_original_item = AsyncMock(return_value=[])
        refund = await SalesService(repo).create_refund(RefundCreate(
            company_id=payload.company_id, original_sale_id=original.id, reason="Return",
            items=[RefundItemCreate(sale_item_id=item.id, quantity="0.250")]), actor=None)
        self.assertEqual(refund.total_amount, Decimal("-0.80"))
        self.assertEqual(original.discount_amount, Decimal("0.20"))
        self.assertEqual(repo.saved["items"][0].line_cost, Decimal("-0.50"))
        self.assertEqual(repo.balance.quantity, Decimal("1"))

    def test_invalid_client_amounts_rejected(self):
        for field in ("amount_received", "discount_amount"):
            for value in ("NaN", "Infinity", "-1", "0.001", "10000000000"):
                with self.subTest(field=field, value=value), self.assertRaises(ValidationError):
                    SaleCreate(company_id=uuid4(), items=[], **{field: value})
        for field in ("unit_price", "line_total", "quantity"):
            for value in ("NaN", "Infinity", "-1", "0", "0.0001", "1000000000000"):
                data = dict(product_id=uuid4(), quantity="1", unit_price="1", line_total="1")
                data[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(ValidationError):
                    SaleItemCreate(**data)
