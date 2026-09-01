import asyncio
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import HTTPException

from app.auth.dependencies import AuthActor
from app.sales.schema import RefundCreate, RefundItemCreate
from app.sales.service import SalesService


class RecordingDB:
    def __init__(self):
        self.added = []
        self.commit = AsyncMock()

    def add(self, value):
        self.added.append(value)


class SalesHistoryActionsTest(unittest.TestCase):
    def receipt_fixture(self):
        company_id = uuid4()
        sale_id = uuid4()
        item_id = uuid4()
        sale = SimpleNamespace(
            id=sale_id,
            company_id=company_id,
            original_sale_id=None,
            reprint_count=0,
            last_reprinted_at=None,
        )
        item = SimpleNamespace(
            id=item_id,
            product_id=uuid4(),
            original_sale_item_id=None,
            product_name="Test item",
            quantity=Decimal("3.000"),
            selling_unit="each",
            unit_price=Decimal("2.00"),
            line_total=Decimal("6.00"),
        )
        prior_refund = SimpleNamespace(quantity=Decimal("1.000"))
        db = RecordingDB()
        repo = SimpleNamespace(
            db=db,
            get_sale_receipt=AsyncMock(return_value=(sale, [item])),
            list_refund_items_for_original_item=AsyncMock(
                return_value=[prior_refund]
            ),
        )
        return company_id, sale_id, sale, item, db, repo

    def test_view_receipt_does_not_mark_or_audit_a_reprint(self):
        company_id, sale_id, sale, item, db, repo = self.receipt_fixture()

        result = asyncio.run(
            SalesService(repo).get_sale_receipt(
                company_id,
                sale_id,
                actor=None,
                mark_reprint=False,
            )
        )

        self.assertEqual(sale.reprint_count, 0)
        self.assertEqual(db.added, [])
        db.commit.assert_not_awaited()
        self.assertEqual(result["items"][0]["refunded_quantity"], Decimal("1.000"))
        self.assertEqual(result["items"][0]["refundable_quantity"], Decimal("2.000"))
        repo.list_refund_items_for_original_item.assert_awaited_once_with(item.id)

    def test_reprint_marks_and_audits_separately(self):
        company_id, sale_id, sale, _item, db, repo = self.receipt_fixture()

        asyncio.run(
            SalesService(repo).get_sale_receipt(
                company_id,
                sale_id,
                actor=None,
                mark_reprint=True,
            )
        )

        self.assertEqual(sale.reprint_count, 1)
        self.assertEqual(db.added[0].action, "receipt_reprint")
        db.commit.assert_awaited_once()

    def test_refunds_permission_can_load_receipt_without_marking_reprint(self):
        company_id, sale_id, sale, _item, db, repo = self.receipt_fixture()
        actor = AuthActor(
            actor_type="employee",
            company_id=company_id,
            role="cashier",
            employee=SimpleNamespace(id=uuid4()),
            permissions={"sales": False, "refunds": True},
        )

        asyncio.run(
            SalesService(repo).get_sale_receipt(
                company_id,
                sale_id,
                actor=actor,
                mark_reprint=False,
            )
        )

        self.assertEqual(sale.reprint_count, 0)
        self.assertEqual(db.added, [])
        db.commit.assert_not_awaited()

    def test_refunds_permission_cannot_mark_receipt_as_reprinted(self):
        company_id, sale_id, _sale, _item, _db, repo = self.receipt_fixture()
        actor = AuthActor(
            actor_type="employee",
            company_id=company_id,
            role="cashier",
            employee=SimpleNamespace(id=uuid4()),
            permissions={"sales": False, "refunds": True},
        )

        with self.assertRaises(HTTPException) as caught:
            asyncio.run(
                SalesService(repo).get_sale_receipt(
                    company_id,
                    sale_id,
                    actor=actor,
                    mark_reprint=True,
                )
            )

        self.assertEqual(caught.exception.status_code, 403)

    def test_refund_rejects_quantity_above_remaining_amount(self):
        company_id = uuid4()
        sale_id = uuid4()
        item_id = uuid4()
        original_sale = SimpleNamespace(
            id=sale_id,
            original_sale_id=None,
            status="partially_refunded",
            branch_id=uuid4(),
            payment_method="cash",
        )
        original_item = SimpleNamespace(
            id=item_id,
            quantity=Decimal("3.000"),
        )
        repo = SimpleNamespace(
            db=RecordingDB(),
            get_sale_for_update=AsyncMock(return_value=original_sale),
            get_sale_items=AsyncMock(return_value=[original_item]),
            resolve_branch=AsyncMock(return_value=SimpleNamespace()),
            list_refund_items_for_original_item=AsyncMock(
                return_value=[SimpleNamespace(quantity=Decimal("2.000"))]
            ),
        )
        request = RefundCreate(
            company_id=company_id,
            original_sale_id=sale_id,
            reason="Customer return",
            items=[
                RefundItemCreate(
                    sale_item_id=item_id,
                    quantity=Decimal("1.001"),
                )
            ],
        )

        with self.assertRaises(HTTPException) as caught:
            asyncio.run(
                SalesService(repo).create_refund(request, actor=None)
            )

        self.assertEqual(caught.exception.status_code, 400)
        self.assertIn("exceeds remaining", caught.exception.detail)


if __name__ == "__main__":
    unittest.main()
