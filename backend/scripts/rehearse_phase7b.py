"""Guarded migration rehearsal using synthetic data in a disposable database.

Run from backend with a schema-owner DATABASE_URL. Never accepts production
names. The destructive downgrade is limited to this explicit test prefix.
"""
import asyncio
import hashlib
import json
import os
from types import SimpleNamespace

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine


URL = os.environ["DATABASE_URL"]
DATABASE = make_url(URL).database or ""
if DATABASE != "apexretail_phase7b_test":
    raise SystemExit("Refusing to rehearse against any database except apexretail_phase7b_test")
CONFIG = Config("alembic.ini")
NEW_TABLES = {"employee_roles", "employee_device_access", "manager_authorizations", "alembic_version"}


async def seed():
    # Reuse the established, entirely synthetic multi-company reporting
    # fixture: historical sales, refunds, cancelled sales, products and stock.
    from tests.test_phase4a_postgres import Phase4APostgresTest
    engine = create_async_engine(URL)
    try:
        async with engine.begin() as connection:
            count = (await connection.execute(text("SELECT count(*) FROM companies"))).scalar_one()
            if count == 0:
                await Phase4APostgresTest.seed(SimpleNamespace(connection=connection))
    finally:
        await engine.dispose()


async def snapshot():
    engine = create_async_engine(URL)
    try:
        async with engine.connect() as connection:
            tables = (await connection.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"))).scalars().all()
            result = {}
            for table in tables:
                if table in NEW_TABLES:
                    continue
                escaped = table.replace('"', '""')
                expression = "to_jsonb(t)"
                if table == "employees":
                    expression += " - ARRAY['role_id','role_overrides','device_restricted']"
                rows = (await connection.execute(text(f'SELECT ({expression})::text FROM "{escaped}" t ORDER BY ({expression})::text'))).scalars().all()
                result[table] = {"count": len(rows), "sha256": hashlib.sha256("\n".join(rows).encode()).hexdigest()}
            result["financial_totals"] = dict((await connection.execute(text("""SELECT
                (SELECT coalesce(sum(total_amount),0)::text FROM sales) AS sale_amount,
                (SELECT coalesce(sum(line_cost),0)::text FROM sale_items) AS line_cost,
                (SELECT coalesce(sum(quantity),0)::text FROM inventory_balances) AS stock_quantity,
                (SELECT count(*) FROM sales WHERE shift_id IS NOT NULL) AS shift_links,
                (SELECT count(*) FROM company_settings WHERE shift_enforcement_enabled) AS enforced_companies
            """))).mappings().one())
            return result
    finally:
        await engine.dispose()


def main():
    # Test fixture contains no Phase 7B role data; capture old data at p7b.
    command.downgrade(CONFIG, "p7b_variant_pricing_tax")
    asyncio.run(seed())
    baseline = asyncio.run(snapshot())
    command.upgrade(CONFIG, "p7c_employee_roles_permissions")
    upgraded = asyncio.run(snapshot())
    assert baseline == upgraded, "Historical content changed during upgrade"
    command.downgrade(CONFIG, "p7b_variant_pricing_tax")
    rolled_back = asyncio.run(snapshot())
    assert baseline == rolled_back, "Historical content changed during downgrade"
    command.upgrade(CONFIG, "p7c_employee_roles_permissions")
    recovered = asyncio.run(snapshot())
    assert baseline == recovered, "Historical content changed during forward recovery"
    print(json.dumps({"database": DATABASE, "revision": "p7c_employee_roles_permissions", "upgrade": "PASS", "downgrade": "PASS", "forward_recovery": "PASS", "historical_content_preserved": baseline}, indent=2))


if __name__ == "__main__":
    main()
