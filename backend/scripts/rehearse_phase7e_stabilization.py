"""Restore the verified archived backup, never connect to live production."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys

backup = Path("/tmp/apexretail-phase7e-approved-backup.dump")
expected = "da9b191138ff052d48860359efc4ac850f5d5b805cdc2918e3b22e40db0c6e36"
if hashlib.sha256(backup.read_bytes()).hexdigest() != expected:
    raise SystemExit("Archived backup checksum mismatch")
backend = Path(__file__).resolve().parent.parent
for name, restored in (("apexretail_phase7e_stabilization_clone_20261020", True), ("apexretail_phase7e_stabilization_empty_20261020", False)):
    # No reset, drop, overwrite or arbitrary database parameters.
    subprocess.run(["psql", "-X", "-v", "ON_ERROR_STOP=1", "-d", "postgres", "-c", f"CREATE DATABASE {name}"], check=True)
    subprocess.run(["psql", "-X", "-v", "ON_ERROR_STOP=1", "-d", "postgres", "-c", f"REVOKE CONNECT ON DATABASE {name} FROM PUBLIC,apex_user"], check=True)
    env = dict(os.environ, DATABASE_URL=f"postgresql+asyncpg://postgres@/{name}?host=/var/run/postgresql")
    if restored:
        subprocess.run(["pg_restore", "--exit-on-error", "-d", name, str(backup)], check=True)
    else:
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "p5h_runtime_write_permissions"], cwd=backend, env=env, check=True)
    access = subprocess.check_output(["psql", "-X", "-At", "-d", "postgres", "-c", f"SELECT has_database_privilege('apex_user','{name}','CONNECT')"], text=True).strip()
    if access != "f": raise SystemExit("Application access to clone must remain disabled")
    subprocess.run([sys.executable, str(backend / "scripts/rehearse_phase7e.py")], cwd=backend, env=env, check=True)
print("Archived-backup and empty-database upgrade/downgrade/forward rehearsals passed")
