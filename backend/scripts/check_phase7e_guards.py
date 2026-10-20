"""Verify both populated acknowledgement ledgers refuse destructive downgrade."""
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
if make_url(url).database != "apexretail_phase7e_guard": raise SystemExit("Refusing non-disposable guard database")


async def signature():
    engine = create_async_engine(url)
    output = {}
    async with engine.connect() as db:
        tables = (await db.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"))).scalars().all()
        for table in tables:
            quoted = '"' + table.replace('"', '""') + '"'
            rows = sorted((await db.execute(text(f"SELECT to_jsonb(t)::text FROM {quoted} t"))).scalars().all())
            output[table] = {"count": len(rows), "sha256": hashlib.sha256("\n".join(rows).encode()).hexdigest()}
    await engine.dispose()
    return output


async def main():
    # Seed ONLY new operational receipts on a clone of synthetic fixtures. No
    # existing sale, stock, audit or financial row is updated or deleted.
    engine = create_async_engine(url)
    async with engine.begin() as db:
        await db.execute(text("""INSERT INTO product_batches(id,company_id,branch_id,product_id,code,expires_on,quantity)
            SELECT gen_random_uuid(),company_id,branch_id,product_id,'GUARD-ONLY',CURRENT_DATE,0
            FROM inventory_movements WHERE branch_id IS NOT NULL
            AND NOT EXISTS(SELECT FROM product_batches WHERE code='GUARD-ONLY') LIMIT 1"""))
        await db.execute(text("""INSERT INTO batch_stock_operations(id,company_id,request_id,payload_hash,batch_id,movement_id,operation)
            SELECT gen_random_uuid(),b.company_id,gen_random_uuid(),repeat('0',64),b.id,m.id,'dispose'
            FROM product_batches b JOIN inventory_movements m ON m.company_id=b.company_id AND m.branch_id=b.branch_id AND m.product_id=b.product_id
            WHERE b.code='GUARD-ONLY' AND NOT EXISTS(SELECT FROM batch_stock_operations) LIMIT 1"""))
        await db.execute(text("""INSERT INTO order_sync_receipts(id,company_id,employee_id,device_id,request_id,payload_hash,result,captured_at)
            SELECT gen_random_uuid(),e.company_id,e.id,d.id,gen_random_uuid(),repeat('0',64),jsonb_build_object('guard_only',true),CURRENT_TIMESTAMP
            FROM employees e JOIN devices d ON d.company_id=e.company_id AND d.branch_id=e.branch_id
            WHERE NOT EXISTS(SELECT FROM order_sync_receipts) LIMIT 1"""))
    await engine.dispose()
    before = await signature()
    if before["batch_stock_operations"]["count"] < 1 or before["order_sync_receipts"]["count"] < 1:
        raise RuntimeError("Expected committed synthetic receipts for both guards")
    result = subprocess.run([sys.executable, "-m", "alembic", "downgrade", "p7f_offline_order_receipts"], capture_output=True, text=True)
    if result.returncode == 0 or "Batch operation history exists" not in result.stderr: raise RuntimeError("Batch downgrade guard failed")
    if await signature() != before: raise RuntimeError("Rejected batch downgrade changed data")
    # The batch guard already proves runtime safety. Inspecting the offline
    # guard independently must not delete the batch history to reach it.
    from unittest.mock import patch
    import importlib.util
    spec = importlib.util.spec_from_file_location("offline_migration", Path(__file__).resolve().parent.parent / "migrations/versions/p7f_offline_order_receipts.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    engine = create_async_engine(url)
    async with engine.connect() as db:
        async def check(connection):
            def invoke(sync_connection):
                with patch.object(module.op, "get_bind", return_value=sync_connection):
                    try: module.downgrade()
                    except RuntimeError as error:
                        if "Offline acknowledgements exist" in str(error): return True
                        raise
                    raise RuntimeError("Offline downgrade guard failed")
            return await connection.run_sync(invoke)
        await check(db)
    await engine.dispose()
    if await signature() != before: raise RuntimeError("Offline guard changed data")
    evidence = {"database": "apexretail_phase7e_guard", "batch_guard": "full Alembic command refused",
        "offline_guard": "exact migration downgrade function refused against real PostgreSQL",
        "all_tables_unchanged": True, "tables_checked": len(before), "production_accessed": False}
    Path("/tmp/phase7e-downgrade-guards.json").write_text(json.dumps(evidence, indent=2))
    print(json.dumps(evidence, indent=2))


asyncio.run(main())
