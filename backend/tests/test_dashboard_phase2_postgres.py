import os
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.dashboard.repository import DashboardRepository


TEST_DATABASE_ENV = "APEX_DASHBOARD_TEST_DATABASE_URL"


class DashboardPhase2PostgresTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        database_url = os.getenv(TEST_DATABASE_ENV)
        if not database_url:
            self.skipTest(f"{TEST_DATABASE_ENV} is not configured")

        parsed = make_url(database_url)
        if not (parsed.database or "").startswith("apexretail_phase2_test_"):
            self.fail("refusing Dashboard integration database without test prefix")

        self.engine = create_async_engine(database_url)
        self.connection = await self.engine.connect()
        self.transaction = await self.connection.begin()
        self.session = AsyncSession(bind=self.connection)

    async def asyncTearDown(self):
        if not hasattr(self, "engine"):
            return
        await self.session.close()
        await self.transaction.rollback()
        await self.connection.close()
        await self.engine.dispose()

    async def test_aggregates_dates_shops_refunds_cost_and_profit(self):
        company_id = uuid4()
        other_company_id = uuid4()
        shop_one = uuid4()
        shop_two = uuid4()
        other_shop = uuid4()

        for identifier, email in [
            (company_id, "phase2-a@example.test"),
            (other_company_id, "phase2-b@example.test"),
        ]:
            await self.connection.execute(
                text(
                    """
                    INSERT INTO companies
                        (id, name, owner_email, business_type, active, deleted)
                    VALUES
                        (:id, 'Phase 2 Test', :email, 'Retail', true, false)
                    """
                ),
                {"id": identifier, "email": email},
            )

        for identifier, owner, name in [
            (shop_one, company_id, "Harare"),
            (shop_two, company_id, "Bulawayo"),
            (other_shop, other_company_id, "Other Company"),
        ]:
            await self.connection.execute(
                text(
                    """
                    INSERT INTO shops
                        (id, company_id, name, active, deleted)
                    VALUES (:id, :company_id, :name, true, false)
                    """
                ),
                {"id": identifier, "company_id": owner, "name": name},
            )

        await self.connection.execute(
            text(
                """
                INSERT INTO company_settings
                    (id, company_id, currency_code, currency_symbol,
                     decimal_places, tax_name, tax_rate, tax_inclusive,
                     paper_size, auto_print, payment_methods, active, deleted)
                VALUES
                    (:id, :company_id, 'USD', 'Z$', 2, 'VAT', 0, false,
                     '80mm', false, '["cash"]'::jsonb, true, false)
                """
            ),
            {"id": uuid4(), "company_id": company_id},
        )

        sale_rows = [
            # A known-discount original and its partial refund in shop one.
            (uuid4(), company_id, shop_one, None, "partially_refunded", Decimal("100"), Decimal("10"), datetime(2026, 8, 10, 10, tzinfo=timezone.utc)),
            # An historical original with unknown discount in shop two.
            (uuid4(), company_id, shop_two, None, "completed", Decimal("50"), None, datetime(2026, 8, 11, 10, tzinfo=timezone.utc)),
            # Out-of-range data must not contribute.
            (uuid4(), company_id, shop_one, None, "completed", Decimal("900"), Decimal("0"), datetime(2026, 7, 31, 10, tzinfo=timezone.utc)),
            # Another company's data must not contribute.
            (uuid4(), other_company_id, other_shop, None, "completed", Decimal("700"), Decimal("0"), datetime(2026, 8, 10, 10, tzinfo=timezone.utc)),
        ]
        original_one_id = sale_rows[0][0]
        refund_id = uuid4()
        sale_rows.append(
            (
                refund_id,
                company_id,
                shop_one,
                original_one_id,
                "refunded",
                Decimal("-20"),
                None,
                datetime(2026, 8, 12, 10, tzinfo=timezone.utc),
            )
        )

        for index, row in enumerate(sale_rows):
            (
                sale_id,
                owner,
                shop_id,
                original_sale_id,
                status,
                total,
                discount,
                created_at,
            ) = row
            await self.connection.execute(
                text(
                    """
                    INSERT INTO sales
                        (id, company_id, original_sale_id, shop_id,
                         receipt_number, subtotal_amount, tax_rate, tax_amount,
                         tax_inclusive, total_amount, discount_amount,
                         amount_received, change_due, payment_method, status,
                         reprint_count, created_at)
                    VALUES
                        (:id, :company_id, :original_sale_id, :shop_id,
                         :receipt, :subtotal, 0, 0, false, :total, :discount,
                         :received, 0, 'cash', :status, 0, :created_at)
                    """
                ),
                {
                    "id": sale_id,
                    "company_id": owner,
                    "original_sale_id": original_sale_id,
                    "shop_id": shop_id,
                    "receipt": f"PHASE2-{index}",
                    "subtotal": total,
                    "total": total,
                    "discount": discount,
                    "received": max(total, Decimal("0")),
                    "status": status,
                    "created_at": created_at,
                },
            )

        item_rows = [
            (original_one_id, Decimal("30")),
            (original_one_id, Decimal("20")),
            (sale_rows[1][0], Decimal("20")),
            (sale_rows[2][0], Decimal("300")),
            (sale_rows[3][0], Decimal("200")),
            (refund_id, Decimal("-10")),
        ]
        for sale_id, line_cost in item_rows:
            await self.connection.execute(
                text(
                    """
                    INSERT INTO sale_items
                        (id, sale_id, product_id, product_name, quantity,
                         selling_unit, unit_price, line_total,
                         unit_cost, line_cost)
                    VALUES
                        (:id, :sale_id, :product_id, 'Test Item', 1,
                         'each', 1, 1, :line_cost, :line_cost)
                    """
                ),
                {
                    "id": uuid4(),
                    "sale_id": sale_id,
                    "product_id": uuid4(),
                    "line_cost": line_cost,
                },
            )

        repository = DashboardRepository(self.session)
        all_shops = await repository.get_phase2_summary(
            company_id,
            range_key="custom",
            date_from=date(2026, 8, 1),
            date_to=date(2026, 8, 31),
        )
        self.assertEqual(all_shops["metrics"]["gross_sales"]["value"], Decimal("150.00"))
        self.assertEqual(all_shops["metrics"]["refunds"]["value"], Decimal("20.00"))
        self.assertEqual(all_shops["metrics"]["net_sales"]["value"], Decimal("130.00"))
        self.assertEqual(all_shops["metrics"]["cost_of_sales"]["value"], Decimal("60.00"))
        self.assertEqual(all_shops["metrics"]["gross_profit"]["value"], Decimal("70.00"))
        self.assertFalse(all_shops["metrics"]["discounts"]["available"])

        one_shop = await repository.get_phase2_summary(
            company_id,
            range_key="custom",
            date_from=date(2026, 8, 1),
            date_to=date(2026, 8, 31),
            shop_id=shop_one,
        )
        self.assertEqual(one_shop["metrics"]["gross_sales"]["value"], Decimal("100.00"))
        self.assertEqual(one_shop["metrics"]["refunds"]["value"], Decimal("20.00"))
        self.assertEqual(one_shop["metrics"]["net_sales"]["value"], Decimal("80.00"))
        self.assertEqual(one_shop["metrics"]["cost_of_sales"]["value"], Decimal("40.00"))
        self.assertEqual(one_shop["metrics"]["gross_profit"]["value"], Decimal("40.00"))
        self.assertTrue(one_shop["metrics"]["discounts"]["available"])
        self.assertEqual(one_shop["metrics"]["discounts"]["value"], Decimal("10.00"))

        analytics = await repository.get_phase3_summary(
            company_id,
            range_key="custom",
            date_from=date(2026, 8, 1),
            date_to=date(2026, 8, 31),
            granularity="day",
        )
        self.assertEqual(analytics["metrics"], all_shops["metrics"])
        self.assertEqual(len(analytics["trends"]), 31)
        self.assertEqual(
            sum(point["metrics"]["net_sales"]["value"] for point in analytics["trends"]),
            Decimal("130.00"),
        )
        self.assertEqual(analytics["comparison"]["date_from"], date(2026, 7, 1))
        self.assertEqual(
            analytics["comparison"]["metrics"]["gross_sales"]["amount"],
            Decimal("-750.00"),
        )
        self.assertFalse(analytics["comparison"]["metrics"]["discounts"]["available"])
        self.assertEqual(
            sum(row["revenue"] for row in analytics["top_products"]),
            Decimal("4.00"),
        )
        self.assertEqual(analytics["top_categories"][0]["name"], "Uncategorised")
        self.assertEqual(analytics["payment_methods"][0]["net_sales"], Decimal("130.00"))
        self.assertEqual(
            sum(row["net_sales"] for row in analytics["shop_breakdown"]),
            Decimal("130.00"),
        )
        self.assertEqual(analytics["refund_breakdown"][0]["refunds"], Decimal("20.00"))
        self.assertEqual(
            {row["key"] for row in analytics["discount_breakdown"]},
            {"discounted", "unavailable"},
        )

        drilldown = await repository.get_drilldown(
            company_id,
            range_key="custom",
            date_from=date(2026, 8, 1),
            date_to=date(2026, 8, 31),
            metric="refunds",
            limit=10,
            offset=0,
        )
        self.assertEqual(drilldown["total"], 1)
        self.assertEqual(drilldown["rows"][0]["id"], refund_id)
        self.assertEqual(drilldown["rows"][0]["refunds"], Decimal("20.00"))
        self.assertTrue(drilldown["rows"][0]["discounts"]["available"])
