"""Full Phase 7A–7E migration rehearsal; exact disposable DB allowlist only.

Production records are hashed locally, never logged. Added columns are not
historical values: comparisons project the exact original columns in each old
table, and also compare currency-separated financial totals.
"""
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
database = make_url(url).database
if database not in {"apexretail_phase7e_production_clone_20261020", "apexretail_phase7e_synthetic_rehearsal", "apexretail_phase7e_tips_clone_20261020"}:
    raise SystemExit("Refusing non-disposable migration target")
quote = lambda name: '"' + name.replace('"', '""') + '"'


async def snapshot(columns=None):
    engine = create_async_engine(url)
    async with engine.connect() as db:
        if columns is None:
            columns = {}
            rows = (await db.execute(text("SELECT table_name,column_name FROM information_schema.columns WHERE table_schema='public' AND table_name <> 'alembic_version' ORDER BY table_name,ordinal_position"))).all()
            for table, column in rows: columns.setdefault(table, []).append(column)
        result = {}
        for table, names in columns.items():
            projected = ",".join(map(quote, names))
            rows = (await db.execute(text(f"SELECT row_to_json(t)::text FROM (SELECT {projected} FROM {quote(table)}) t"))).scalars().all()
            canonical = sorted(json.dumps(json.loads(row), sort_keys=True, separators=(",", ":")) for row in rows)
            result[table] = {"count": len(rows), "sha256": hashlib.sha256("\n".join(canonical).encode()).hexdigest()}
        revision = (await db.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
        totals = [dict(row) for row in (await db.execute(text("SELECT coalesce(base_currency_code,'legacy') currency,count(*) count,sum(total_amount)::text total FROM sales GROUP BY 1 ORDER BY 1"))).mappings()]
        flags = dict((await db.execute(text("SELECT (SELECT coalesce(sum(quantity),0)::text FROM inventory_balances) stock, (SELECT count(*) FROM sales WHERE shift_id IS NOT NULL) shift_links, (SELECT count(*) FROM company_settings WHERE shift_enforcement_enabled) enforcement_enabled"))).mappings().one())
    await engine.dispose()
    return {"columns": columns, "tables": result, "revision": revision, "currency_totals": totals, "flags": flags}


async def main():
    before = await snapshot()
    if before["revision"] != "p5h_runtime_write_permissions": raise SystemExit("Expected unchanged deployed Phase 5 baseline")
    revisions = ["p7a_product_composites", "p7b_variant_pricing_tax", "p7c_employee_roles_permissions", "p7d_printers_kitchen_jobs", "p7e_business_orders_batches", "p7f_offline_order_receipts", "p7g_batch_stock_operations", "p7h_tips_accounting", "p7i_pharmacy_return_holds"]
    stages = []
    async def run(direction, revision):
        subprocess.run([sys.executable, "-m", "alembic", direction, revision], check=True)
        after = await snapshot(before["columns"])
        for field in ("tables", "currency_totals", "flags"):
            if after[field] != before[field]: raise RuntimeError(f"Historical {field} changed at {direction} {revision}")
        stages.append({"direction": direction, "revision": after["revision"], "historical_content_unchanged": True})
    for revision in revisions: await run("upgrade", revision)
    await run("downgrade", "p5h_runtime_write_permissions")
    await run("upgrade", "p7i_pharmacy_return_holds")
    evidence = {"database": database, "baseline": before, "stages": stages,
        "live_production_connected": False, "scope": "restored backup" if "clone" in database else "synthetic"}
    Path(f"/tmp/{database}-rehearsal.json").write_text(json.dumps(evidence, indent=2))
    print(json.dumps({"database": database, "tables_checked": len(before["tables"]), "stages": stages}, indent=2))


asyncio.run(main())
