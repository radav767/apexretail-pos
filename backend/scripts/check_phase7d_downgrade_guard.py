"""Prove a populated disposable Phase 7D clone refuses destructive downgrade."""
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
if make_url(url).database != "apexretail_phase7d_rollback_guard": raise SystemExit("Refusing non-disposable database")


async def signature():
    engine = create_async_engine(url)
    result = {}
    async with engine.connect() as db:
        names = (await db.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"))).scalars().all()
        for name in names:
            quoted = '"' + name.replace('"', '""') + '"'
            rows = sorted((await db.execute(text(f"SELECT to_jsonb(t)::text FROM {quoted} t"))).scalars().all())
            result[name] = {"count": len(rows), "sha256": hashlib.sha256("\n".join(rows).encode()).hexdigest()}
    await engine.dispose(); return result


async def main():
    before = await signature()
    if before["commerce_orders"]["count"] == 0: raise SystemExit("Expected committed synthetic orders")
    result = subprocess.run([sys.executable, "-m", "alembic", "downgrade", "p7d_printers_kitchen_jobs"], capture_output=True, text=True)
    if result.returncode == 0 or "refusing destructive downgrade" not in result.stderr:
        raise SystemExit("Downgrade guard did not reject the populated clone")
    after = await signature()
    if before != after: raise SystemExit("Data changed despite downgrade guard")
    evidence = {"database": make_url(url).database, "downgrade_refused": True, "all_content_unchanged": True,
        "tables_checked": len(before), "orders_preserved": before["commerce_orders"]["count"], "production_accessed": False}
    Path("/tmp/phase7d-downgrade-guard.json").write_text(json.dumps(evidence, indent=2))
    print(json.dumps(evidence, indent=2))


asyncio.run(main())
