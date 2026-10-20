"""Full Alembic rollback refusal on an isolated populated synthetic clone."""
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
if make_url(url).database != "apexretail_phase7e_tips_guard_20261020": raise SystemExit("Refusing non-disposable guard target")


async def snapshot():
    engine = create_async_engine(url); result = {}
    async with engine.connect() as db:
        for name in (await db.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"))).scalars():
            quoted = '"' + name.replace('"','""') + '"'
            rows = sorted((await db.execute(text(f"SELECT to_jsonb(t)::text FROM {quoted} t"))).scalars().all())
            result[name] = {"count": len(rows), "sha256": hashlib.sha256("\n".join(rows).encode()).hexdigest()}
        result["schema_create"] = (await db.execute(text("SELECT has_schema_privilege('apex_user','public','CREATE')"))).scalar_one()
    await engine.dispose(); return result


async def main():
    before = await snapshot()
    if before["tip_entries"]["count"] < 1: raise RuntimeError("Expected committed synthetic tip payments")
    attempt = subprocess.run([sys.executable,"-m","alembic","downgrade","p7g_batch_stock_operations"],capture_output=True,text=True)
    if attempt.returncode == 0 or "Tip records/settings exist" not in attempt.stderr:
        raise RuntimeError("Populated tip downgrade was not safely rejected")
    if await snapshot() != before: raise RuntimeError("Rejected downgrade changed historical data/schema")
    subprocess.run([sys.executable,"-m","alembic","upgrade","head"],check=True)
    if await snapshot() != before: raise RuntimeError("Forward no-op recovery changed data")
    report = {"database":make_url(url).database,"full_alembic_downgrade_refused":True,
        "all_tables_unchanged":True,"tables_checked":len(before)-1,"tip_entries_preserved":before["tip_entries"]["count"],
        "schema_create_privilege_unchanged":True,"production_accessed":False}
    Path("/tmp/phase7e-tip-guards.json").write_text(json.dumps(report,indent=2)); print(json.dumps(report,indent=2))


asyncio.run(main())
