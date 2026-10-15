import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from pydantic import ValidationError
from fastapi import HTTPException
from app.sales.schema import SaleCreate, SaleItemCreate, RefundCreate, RefundItemCreate
from app.sales.service import SalesService
from tests.test_weighted_sales_and_subscriptions import FakeSalesRepo
from tests.test_sales_history_actions import RecordingDB


class DiscountCheckoutTest(unittest.IsolatedAsyncioTestCase):
    async def test_client_sale_status_requires_same_tenant_authentication(self):
        company_id = uuid4()
        sale_id = uuid4()
        sale = SimpleNamespace(id=sale_id)
        repo = SimpleNamespace(
            get_by_client_sale_id=AsyncMock(return_value=sale),
        )
        service = SalesService(repo)

        with self.assertRaisesRegex(HTTPException, "Authentication"):
            await service.by_client_sale_id(company_id, uuid4(), None)

        wrong_tenant = SimpleNamespace(
            company_id=uuid4(),
            actor_type="user",
        )
        with self.assertRaisesRegex(HTTPException, "Forbidden"):
            await service.by_client_sale_id(
                company_id,
                uuid4(),
                wrong_tenant,
            )

        actor = SimpleNamespace(
            company_id=company_id,
            actor_type="employee",
            permissions={"sales": True},
        )
        result = await service.by_client_sale_id(
            company_id,
            uuid4(),
            actor,
        )
        self.assertIs(result, sale)

    async def checkout(
        self,
        discount="0.20",
        paid="0.80",
        *,
        line_discount=None,
        sale_discount=None,
    ):
        repo = FakeSalesRepo()
        payload = SaleCreate(company_id=uuid4(), client_sale_id=uuid4(),
            payment_method="card", discount_amount=discount,
            sale_discount_amount=sale_discount,
            items=[SaleItemCreate(product_id=repo.product.id, quantity="0.250",
                                  unit_price="4.00", line_total=paid,
                                  line_discount_amount=line_discount)])
        with patch("app.sales.service.BusinessSettingsService.get", return_value={
            "tax_rate": Decimal("0"), "tax_inclusive": False,
        }):
            sale = await SalesService(repo).create_sale(payload, actor=None)
        return repo, payload, sale

    async def test_offline_retry_preserves_original_snapshot_and_stock(self):
        cases = [
            (None, "0.80", None, None),
            ("0", "1", None, None),
            ("0.20", "0.80", None, None),
            ("0.30", "0.70", "0.20", "0.10"),
        ]
        for discount, paid, line_discount, sale_discount in cases:
            repo, payload, sale = await self.checkout(
                discount,
                paid,
                line_discount=line_discount,
                sale_discount=sale_discount,
            )
            quantity = repo.balance.quantity
            repo.get_by_client_sale_id = AsyncMock(return_value=sale)
            replay = SaleCreate.model_validate_json(payload.model_dump_json())
            result = await SalesService(repo).create_sale(replay, actor=None)
            self.assertIs(result, sale)
            self.assertEqual(repo.balance.quantity, quantity)
            self.assertEqual(result.discount_amount, None if discount is None else Decimal(discount))
            self.assertEqual(
                result.sale_discount_amount,
                None if sale_discount is None else Decimal(sale_discount),
            )

    async def test_single_and_combined_components_apply_exactly_once(self):
        cases = [
            ("0.20", "0.80", "0.20", "0.00"),
            ("0.10", "0.90", "0.00", "0.10"),
            ("0.30", "0.70", "0.20", "0.10"),
        ]
        for discount, paid, line_discount, sale_discount in cases:
            with self.subTest(
                line_discount=line_discount,
                sale_discount=sale_discount,
            ):
                repo, _payload, sale = await self.checkout(
                    discount,
                    paid,
                    line_discount=line_discount,
                    sale_discount=sale_discount,
                )
                item = repo.saved["items"][0]
                self.assertEqual(sale.total_amount, Decimal(paid))
                self.assertEqual(sale.subtotal_amount, Decimal(paid))
                self.assertEqual(sale.discount_amount, Decimal(discount))
                self.assertEqual(
                    sale.sale_discount_amount,
                    Decimal(sale_discount),
                )
                self.assertEqual(
                    item.line_discount_amount,
                    Decimal(line_discount),
                )
                self.assertEqual(item.line_total, Decimal(paid))

    async def test_mismatched_discount_components_are_rejected(self):
        with self.assertRaisesRegex(HTTPException, "line discounts plus"):
            await self.checkout(
                "0.30",
                "0.70",
                line_discount="0.20",
                sale_discount="0.20",
            )

    async def test_refund_uses_discounted_line_and_preserves_original_discount(self):
        repo, payload, original = await self.checkout(
            "0.30",
            "0.70",
            line_discount="0.20",
            sale_discount="0.10",
        )
        item = repo.saved["items"][0]
        item.id = uuid4()
        repo.db = RecordingDB()
        repo.get_sale_for_update = AsyncMock(return_value=original)
        repo.get_sale_items = AsyncMock(return_value=[item])
        repo.list_refund_items_for_original_item = AsyncMock(return_value=[])
        refund = await SalesService(repo).create_refund(RefundCreate(
            company_id=payload.company_id, original_sale_id=original.id, reason="Return",
            items=[RefundItemCreate(sale_item_id=item.id, quantity="0.250")]), actor=None)
        self.assertEqual(refund.total_amount, Decimal("-0.70"))
        self.assertEqual(original.discount_amount, Decimal("0.30"))
        self.assertEqual(original.sale_discount_amount, Decimal("0.10"))
        self.assertEqual(repo.saved["items"][0].line_cost, Decimal("-0.50"))
        self.assertEqual(repo.balance.quantity, Decimal("1"))

    def test_invalid_client_amounts_rejected(self):
        for field in ("amount_received", "discount_amount", "sale_discount_amount"):
            for value in ("NaN", "Infinity", "-1", "0.001", "10000000000"):
                with self.subTest(field=field, value=value), self.assertRaises(ValidationError):
                    SaleCreate(company_id=uuid4(), items=[], **{field: value})
        for field in ("unit_price", "line_total", "quantity"):
            for value in ("NaN", "Infinity", "-1", "0", "0.0001", "1000000000000"):
                data = dict(product_id=uuid4(), quantity="1", unit_price="1", line_total="1")
                data[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(ValidationError):
                    SaleItemCreate(**data)
        for value in ("NaN", "Infinity", "-1", "0.001", "10000000000"):
            with self.subTest(field="line_discount_amount", value=value), self.assertRaises(ValidationError):
                SaleItemCreate(
                    product_id=uuid4(),
                    quantity="1",
                    unit_price="1",
                    line_total="1",
                    line_discount_amount=value,
                )
