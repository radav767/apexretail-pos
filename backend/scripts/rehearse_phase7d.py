"""Hash every pre-existing table across upgrade/downgrade/forward recovery."""
import asyncio
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

url = os.environ["DATABASE_URL"]
if make_url(url).database != "apexretail_phase7d_rehearsal": raise SystemExit("Refusing non-disposable rehearsal database")
new_tables = {"business_profiles", "dining_tables", "hospitality_rooms", "guest_accounts", "commerce_orders", "commerce_order_items", "kitchen_tickets", "product_batches", "batch_allocations", "alembic_version"}


async def snapshot():
    engine = create_async_engine(url)
    result = {}
    async with engine.connect() as db:
        tables = (await db.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"))).scalars().all()
        for table in tables:
            if table in new_tables: continue
            quoted = '"' + table.replace('"', '""') + '"'
            expression = "to_jsonb(t) - 'order_id'" if table == "print_jobs" else "to_jsonb(t)"
            rows = (await db.execute(text(f"SELECT ({expression})::text FROM {quoted} t"))).scalars().all()
            canonical = sorted(json.dumps(json.loads(row), sort_keys=True, separators=(",", ":")) for row in rows)
            result[table] = {"count": len(rows), "sha256": hashlib.sha256("\n".join(canonical).encode()).hexdigest()}
        revision = (await db.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
        totals = (await db.execute(text("SELECT (SELECT coalesce(sum(total_amount),0)::text FROM sales) sales, (SELECT coalesce(sum(quantity),0)::text FROM inventory_balances) stock, (SELECT count(*) FROM sales WHERE shift_id IS NOT NULL) historical_shift_links, (SELECT count(*) FROM company_settings WHERE shift_enforcement_enabled) enforcement_enabled"))).mappings().one()
    await engine.dispose()
    return {"tables": result, "revision": revision, "totals": dict(totals)}


async def main():
    before = await snapshot()
    if before["revision"] != "p7d_printers_kitchen_jobs": raise SystemExit("Expected the Phase 7C parent revision")
    stages = {}
    for name, args in (("upgrade", ("upgrade", "p7e_business_orders_batches")), ("downgrade", ("downgrade", "p7d_printers_kitchen_jobs")), ("forward_recovery", ("upgrade", "p7e_business_orders_batches"))):
        subprocess.run([sys.executable, "-m", "alembic", *args], check=True)
        after = await snapshot()
        if after["tables"] != before["tables"] or after["totals"] != before["totals"]: raise SystemExit(f"Historical data changed at {name}")
        stages[name] = {"revision": after["revision"], "historical_content_unchanged": True}
    output = {"database": make_url(url).database, "baseline": before, "stages": stages, "production_accessed": False}
    Path("/tmp/phase7d-migration-rehearsal.json").write_text(json.dumps(output, indent=2))
    print(json.dumps({"stages": stages, "tables_checked": len(before["tables"]), "totals": before["totals"]}, indent=2))


asyncio.run(main())
