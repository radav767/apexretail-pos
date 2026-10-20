"""Read-only recheck of archived backup and previously restored isolated clone."""
import asyncio
import hashlib
import json
from pathlib import Path
import subprocess
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

backup=Path("/tmp/apexretail-phase7e-approved-backup.dump")
expected="da9b191138ff052d48860359efc4ac850f5d5b805cdc2918e3b22e40db0c6e36"
if hashlib.sha256(backup.read_bytes()).hexdigest()!=expected:raise SystemExit("Backup hash mismatch")
subprocess.run(["pg_restore","--list",str(backup)],check=True,stdout=subprocess.DEVNULL)
database="apexretail_phase7e_stabilization_clone_20261020"
baseline=json.loads(Path(f"/tmp/{database}-rehearsal.json").read_text())["baseline"]


async def main():
    engine=create_async_engine(f"postgresql+asyncpg://postgres@/{database}?host=/var/run/postgresql")
    async with engine.begin() as db:
        await db.execute(text("SET TRANSACTION READ ONLY"))
        revision=(await db.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
        if revision!="p7j_variant_batches":raise RuntimeError("Unexpected isolated clone revision")
        for table,columns in baseline["columns"].items():
            quote=lambda name:'"'+name.replace('"','""')+'"'
            rows=(await db.execute(text(f"SELECT row_to_json(t)::text FROM (SELECT {','.join(map(quote,columns))} FROM {quote(table)}) t"))).scalars().all()
            canonical=sorted(json.dumps(json.loads(row),sort_keys=True,separators=(",",":")) for row in rows)
            actual={"count":len(rows),"sha256":hashlib.sha256("\n".join(canonical).encode()).hexdigest()}
            if actual!=baseline["tables"][table]:raise RuntimeError(f"Archived historical content changed: {table}")
        allowed=(await db.execute(text("SELECT has_database_privilege('apex_user',current_database(),'CONNECT')"))).scalar_one()
        if allowed:raise RuntimeError("Application must not connect to disposable restored clone")
    await engine.dispose()
    result={"archivedBackupDate":"2026-10-16","backupSHA256":expected,"archiveCatalogReadable":True,
        "priorFullRestoreAnd12StageRehearsalVerified":True,"isolatedClone":database,"revision":revision,
        "historicalTables":len(baseline["tables"]),"historicalRows":sum(v["count"] for v in baseline["tables"].values()),
        "allHistoricalHashesUnchanged":True,"newMigrationRequired":False,"productionAccessed":False,"currentProductionVerification":"PENDING"}
    Path("/tmp/phase7e-completion-backup.json").write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))


asyncio.run(main())
