"""Measure Phase 3 queries with rolled-back synthetic data on an isolated DB."""

import asyncio
import json
import os
import time
from datetime import date
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.dashboard.accounting import transaction_filters, transaction_population_cte, utc_bounds


COMPANY_ID = UUID("33333333-3333-3333-3333-333333333333")
SHOP_ID = UUID("44444444-4444-4444-4444-444444444444")


async def main():
    database_url = os.environ["DATABASE_URL"]
    database_name = make_url(database_url).database or ""
    if not database_name.startswith(("apexretail_phase2_test_", "apexretail_phase3_test_")):
        raise SystemExit("refusing performance measurement outside a Phase 2/3 test database")

    engine = create_async_engine(database_url)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        try:
            setup_statements = ["""
                INSERT INTO companies (id, name, owner_email, business_type, active, deleted)
                VALUES (:company, 'Phase 3 Performance', 'phase3-performance@example.test',
                        'Retail', true, false)
            """, """
                INSERT INTO shops (id, company_id, name, active, deleted)
                VALUES (:shop, :company, 'Performance Shop', true, false)
            """, """
                INSERT INTO categories (id, company_id, name, active, deleted)
                SELECT md5('category' || value)::uuid, :company,
                       'Category ' || value, true, false
                FROM generate_series(0, 19) value
            """, """
                INSERT INTO products
                    (id, company_id, category_id, name, unit, cost_price,
                     selling_price, stock_qty, reorder_level, active, deleted)
                SELECT md5('product' || value)::uuid, :company,
                       md5('category' || value)::uuid, 'Product ' || value,
                       'each', 15, 40, 1000, 10, true, false
                FROM generate_series(0, 19) value
            """]
            for statement in setup_statements:
                await connection.execute(
                    text(statement), {"company": COMPANY_ID, "shop": SHOP_ID}
                )

            started = time.perf_counter()
            await connection.execute(text("""
                INSERT INTO sales
                    (id, company_id, shop_id, original_sale_id, receipt_number,
                     subtotal_amount, tax_rate, tax_amount, tax_inclusive,
                     total_amount, discount_amount, amount_received, change_due,
                     payment_method, status, reprint_count, created_at)
                SELECT md5('sale' || value)::uuid, :company, :shop,
                       CASE WHEN value % 10 = 0
                            THEN md5('sale' || (value - 1))::uuid END,
                       'P3-' || value, CASE WHEN value % 10 = 0 THEN -20 ELSE 100 END,
                       0, 0, false, CASE WHEN value % 10 = 0 THEN -20 ELSE 100 END,
                       CASE WHEN value % 17 = 0 THEN NULL ELSE 5 END,
                       CASE WHEN value % 10 = 0 THEN 0 ELSE 100 END, 0,
                       CASE WHEN value % 3 = 0 THEN 'card' ELSE 'cash' END,
                       CASE WHEN value % 10 = 0 THEN 'refunded' ELSE 'completed' END,
                       0, TIMESTAMPTZ '2026-01-01 00:00:00+00'
                          + ((value % 365) || ' days')::interval
                FROM generate_series(1, 25000) value
            """), {"company": COMPANY_ID, "shop": SHOP_ID})
            await connection.execute(text("""
                INSERT INTO sale_items
                    (id, sale_id, product_id, product_name, quantity, selling_unit,
                     unit_price, line_total, unit_cost, line_cost)
                SELECT md5('item' || sale_no || '-' || line_no)::uuid,
                       md5('sale' || sale_no)::uuid,
                       md5('product' || (sale_no % 20))::uuid,
                       'Product ' || (sale_no % 20),
                       CASE WHEN sale_no % 10 = 0 THEN -1 ELSE 1 END,
                       'each', 40,
                       CASE WHEN sale_no % 10 = 0 THEN -6.67 ELSE 33.33 END,
                       15, CASE WHEN sale_no % 10 = 0 THEN -5 ELSE 5 END
                FROM generate_series(1, 25000) sale_no
                CROSS JOIN generate_series(1, 3) line_no
            """))
            fixture_ms = (time.perf_counter() - started) * 1000

            start_at, end_at = utc_bounds(date(2026, 1, 1), date(2026, 12, 31))
            params = {
                "company_id": COMPANY_ID, "shop_id": None,
                "start_at": start_at, "end_at": end_at,
            }
            cte = transaction_population_cte(transaction_filters())
            queries = {
                "summary": cte + " SELECT SUM(net_sales), SUM(gross_profit) FROM transaction_population",
                "daily_trend": cte + " SELECT date_trunc('day', created_at AT TIME ZONE 'Africa/Harare'), SUM(net_sales), SUM(gross_profit) FROM transaction_population GROUP BY 1",
                "top_products": cte + " SELECT si.product_id, SUM(si.line_total), SUM(si.line_total-si.line_cost) FROM transaction_population tp JOIN sale_items si ON si.sale_id=tp.id GROUP BY si.product_id ORDER BY SUM(si.line_total) DESC LIMIT 10",
            }
            measurements = {}
            for name, query in queries.items():
                result = await connection.execute(
                    text("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + query), params
                )
                plan = result.scalar_one()[0]
                measurements[name] = {
                    "planning_ms": round(float(plan["Planning Time"]), 3),
                    "execution_ms": round(float(plan["Execution Time"]), 3),
                    "root_plan": plan["Plan"]["Node Type"],
                }
            print(json.dumps({
                "database": database_name, "synthetic_sales": 25000,
                "synthetic_sale_items": 75000,
                "fixture_insert_ms": round(fixture_ms, 3),
                "measurements": measurements, "indexes_added": False,
                "transaction_rolled_back": True,
            }, indent=2, sort_keys=True))
        finally:
            await transaction.rollback()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
