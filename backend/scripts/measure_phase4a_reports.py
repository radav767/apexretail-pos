"""Measure Phase 4A grouped queries with rolled-back synthetic data only."""
import asyncio
import json
import os
import time
from datetime import date
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.reports.accounting import utc_bounds
from app.reports.repository import ReportsRepository
from app.reports.schema import SalesHistoryQuery


COMPANY = UUID("51000000-0000-0000-0000-000000000001")
SHOP = UUID("52000000-0000-0000-0000-000000000001")
BRANCH = UUID("53000000-0000-0000-0000-000000000001")
CASHIER = UUID("54000000-0000-0000-0000-000000000001")
MAX_MS = 2000.0


def compact_plan(node):
    result = {
        key: node[key]
        for key in (
            "Node Type", "Join Type", "Relation Name", "Index Name",
            "Actual Rows", "Actual Loops", "Actual Total Time",
            "Rows Removed by Filter",
        )
        if key in node
    }
    children = [compact_plan(child) for child in node.get("Plans", [])]
    if children:
        result["Plans"] = children
    return result


async def main():
    database_url = os.environ["DATABASE_URL"]
    database_name = make_url(database_url).database or ""
    if not database_name.startswith("apexretail_phase4a_test_"):
        raise SystemExit("refusing measurement outside a Phase 4A test database")
    engine = create_async_engine(database_url)
    report = None
    async with engine.connect() as connection:
        transaction = await connection.begin()
        try:
            statements = [
                """INSERT INTO companies (id,name,owner_email,business_type,active,deleted)
                   VALUES (:company,'Performance','phase4a-performance@example.test','Retail',true,false)""",
                """INSERT INTO shops (id,company_id,name,active,deleted)
                   VALUES (:shop,:company,'Performance Shop',true,false)""",
                """INSERT INTO branches (id,company_id,shop_id,name,active,deleted)
                   VALUES (:branch,:company,:shop,'Performance Branch',true,false)""",
                """INSERT INTO employees (id,company_id,shop_id,branch_id,name,pin,role,permissions,active,deleted)
                   VALUES (:cashier,:company,:shop,:branch,'Performance Cashier','0000','cashier','{}'::jsonb,true,false)""",
                """INSERT INTO categories (id,company_id,name,active,deleted)
                   SELECT md5('p4category'||v)::uuid,:company,'Category '||v,true,false FROM generate_series(0,19) v""",
                """INSERT INTO products (id,company_id,category_id,name,unit,cost_price,selling_price,stock_qty,reorder_level,active,deleted)
                   SELECT md5('p4product'||v)::uuid,:company,md5('p4category'||(v%20))::uuid,'Product '||v,'each',15,40,1000,10,true,false FROM generate_series(0,19) v""",
                """INSERT INTO inventory_balances (id,company_id,shop_id,branch_id,product_id,quantity,reorder_level,active,deleted)
                   SELECT md5('p4balance'||v)::uuid,:company,:shop,:branch,md5('p4product'||v)::uuid,1000,10,true,false FROM generate_series(0,19) v""",
            ]
            params = {"company": COMPANY, "shop": SHOP, "branch": BRANCH, "cashier": CASHIER}
            for statement in statements:
                await connection.execute(text(statement), params)
            started = time.perf_counter()
            await connection.execute(text("""
                INSERT INTO sales (id,company_id,shop_id,branch_id,employee_id,original_sale_id,receipt_number,cashier_name,shop_name_snapshot,branch_name_snapshot,subtotal_amount,tax_rate,tax_amount,tax_inclusive,total_amount,discount_amount,amount_received,change_due,payment_method,status,reprint_count,created_at)
                SELECT md5('p4sale'||v)::uuid,:company,:shop,:branch,:cashier,
                  CASE WHEN v%10=0 THEN md5('p4sale'||(v-1))::uuid END,
                  'P4-'||v,'Performance Cashier','Performance Shop','Performance Branch',
                  CASE WHEN v%10=0 THEN -20 ELSE 100 END,0,0,false,
                  CASE WHEN v%10=0 THEN -20 ELSE 100 END,
                  CASE WHEN v%37=0 THEN NULL ELSE 5 END,
                  CASE WHEN v%10=0 THEN 0 ELSE 100 END,0,
                  CASE WHEN v%11=0 THEN 'credit' WHEN v%3=0 THEN 'card' ELSE 'cash' END,
                  CASE WHEN v%10=0 THEN 'refunded' WHEN v%29=0 THEN 'cancelled' ELSE 'completed' END,
                  0,TIMESTAMPTZ '2026-01-01 00:00:00+00'+((v%365)||' days')::interval
                FROM generate_series(1,25000) v
            """), params)
            await connection.execute(text("""
                INSERT INTO sale_items (id,sale_id,product_id,product_name,category_id_snapshot,category_name_snapshot,quantity,selling_unit,unit_price,line_total,unit_cost,line_cost,cost_snapshot_available)
                SELECT md5('p4item'||sale_no||'-'||line_no)::uuid,
                  md5('p4sale'||sale_no)::uuid,md5('p4product'||(sale_no%20))::uuid,
                  'Product '||(sale_no%20),md5('p4category'||(sale_no%20))::uuid,
                  'Category '||(sale_no%20),CASE WHEN sale_no%10=0 THEN .2 ELSE 1 END,
                  'each',40,CASE WHEN sale_no%10=0 THEN -6.67 ELSE 33.33 END,
                  15,CASE WHEN sale_no%10=0 THEN -3 ELSE 15 END,
                  CASE WHEN sale_no%41=0 THEN NULL ELSE true END
                FROM generate_series(1,25000) sale_no CROSS JOIN generate_series(1,3) line_no
            """))
            fixture_ms = (time.perf_counter() - started) * 1000
            await connection.execute(text("ANALYZE sales, sale_items, inventory_balances, products"))
            start_at, end_at = utc_bounds(date(2026,1,1), date(2026,12,31))
            query_params = {**params, "company_id": COMPANY,
                            "start_at": start_at, "end_at": end_at,
                            "shop_id": None, "branch_id": None, "cashier_id": None,
                            "product_id": None, "category_id": None, "payment_method": None}
            measurements = {}
            for view in ("individual","cashier","product","category","payment_type","shop_branch","credit_sales","refunds_cancellations"):
                query = SalesHistoryQuery(view=view,date_from=date(2026,1,1),date_to=date(2026,12,31))
                base, sort, direction = ReportsRepository.sales_history_rows_sql(query)
                sql = f"SELECT * FROM ({base}) report_rows ORDER BY {sort} {direction} NULLS LAST,label ASC LIMIT 25"
                result = await connection.execute(text("EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) "+sql), query_params)
                plan = result.scalar_one()[0]
                measurements[view] = {
                    "planning_ms": round(float(plan["Planning Time"]),3),
                    "execution_ms": round(float(plan["Execution Time"]),3),
                    "plan": compact_plan(plan["Plan"]),
                }
            failures = {name:data["execution_ms"] for name,data in measurements.items() if data["execution_ms"] > MAX_MS}
            report = {"database": database_name, "synthetic_sales": 25000,
                      "synthetic_sale_items": 75000, "fixture_insert_ms": round(fixture_ms,3),
                      "measurements": measurements, "max_query_execution_ms": MAX_MS,
                      "threshold_passed": not failures, "indexes_added": False,
                      "transaction_rolled_back": False}
        finally:
            await transaction.rollback()
    await engine.dispose()
    report["transaction_rolled_back"] = True
    print(json.dumps(report, indent=2, sort_keys=True))
    if failures:
        raise RuntimeError(f"Phase 4A query threshold failures: {failures}")


if __name__ == "__main__":
    asyncio.run(main())
