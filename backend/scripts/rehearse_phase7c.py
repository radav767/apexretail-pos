"""Phase 7C only: content-preservation rehearsal on an explicitly disposable clone."""
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
if not (make_url(url).database or "").startswith("apexretail_phase7c_rehearsal"):
    raise SystemExit("Refusing database outside disposable rehearsal prefix")
new_tables = {"printer_stations", "printer_routes", "print_jobs", "alembic_version"}


async def snapshot():
    engine = create_async_engine(url)
    output = {}
    async with engine.connect() as db:
        tables = (await db.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"))).scalars().all()
        for table in tables:
            if table in new_tables: continue
            # Names come only from pg_catalog, quoted against embedded quotes.
            quoted = '"' + table.replace('"', '""') + '"'
            rows = (await db.execute(text(f"SELECT row_to_json(t)::text FROM {quoted} t"))).scalars().all()
            canonical = sorted(json.dumps(json.loads(r), sort_keys=True, separators=(",", ":")) for r in rows)
            output[table] = {"count": len(rows), "sha256": hashlib.sha256("\n".join(canonical).encode()).hexdigest()}
        revision = (await db.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
        totals = (await db.execute(text("SELECT (SELECT coalesce(sum(total_amount),0)::text FROM sales) sales, (SELECT coalesce(sum(quantity),0)::text FROM inventory_balances) stock, (SELECT count(*) FROM sales WHERE shift_id IS NOT NULL) shift_links"))).mappings().one()
    await engine.dispose()
    return {"tables": output, "revision": revision, "totals": dict(totals)}


def migrate(*args):
    subprocess.run([sys.executable, "-m", "alembic", *args], check=True)


async def main():
    before = await snapshot()
    if before["revision"] != "p7c_employee_roles_permissions": raise SystemExit("Expected the Phase 7B parent revision")
    stages = {}
    for name, args in (("upgrade", ("upgrade", "p7d_printers_kitchen_jobs")), ("downgrade", ("downgrade", "p7c_employee_roles_permissions")), ("forward_recovery", ("upgrade", "p7d_printers_kitchen_jobs"))):
        migrate(*args)
        result = await snapshot()
        if result["tables"] != before["tables"] or result["totals"] != before["totals"]:
            raise SystemExit(f"Historical content changed during {name}")
        stages[name] = {"revision": result["revision"], "historical_content_unchanged": True}
    output = {"database": make_url(url).database, "baseline": before, "stages": stages, "production_accessed": False}
    Path(os.environ.get("PHASE7C_MIGRATION_EVIDENCE", "/tmp/phase7c-migration-rehearsal.json")).write_text(json.dumps(output, indent=2))
    print(json.dumps({"stages": stages, "tables_checked": len(before["tables"]), "totals": before["totals"]}, indent=2))


asyncio.run(main())
