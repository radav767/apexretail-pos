"""Prepare synthetic clones or run all regressions. Never targets production."""
import os
import subprocess
import sys
from pathlib import Path
from prepare_phase7d_tests import DATABASES

targets = {old.replace("phase7d", "phase7e"): old for old in DATABASES}
backend = Path(__file__).resolve().parent.parent
if "--prepare" in sys.argv:
    for target, source in targets.items():
        assert target.endswith("test_phase7e") and source.endswith("test_phase7d")
        exists = subprocess.check_output(["psql", "-X", "-At", "-d", "postgres", "-c",
            f"SELECT 1 FROM pg_database WHERE datname='{target}'"], text=True).strip()
        if not exists:
            subprocess.run(["psql", "-X", "-v", "ON_ERROR_STOP=1", "-d", "postgres", "-c",
                f"CREATE DATABASE {target} TEMPLATE {source}"], check=True)
        env = dict(os.environ, DATABASE_URL=f"postgresql+asyncpg://postgres@/{target}?host=/var/run/postgresql")
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], env=env, cwd=backend, check=True)
else:
    keys = ["DATABASE_URL", "APEX_PHASE7D_TEST_DATABASE_URL", "APEX_PHASE7C_TEST_DATABASE_URL",
        "APEX_PHASE7B_TEST_DATABASE_URL", "APEX_PHASE5_TEST_DATABASE_URL", "APEX_PHASE4A_TEST_DATABASE_URL",
        "APEX_PHASE4B_TEST_DATABASE_URL", "APEX_DASHBOARD_TEST_DATABASE_URL", "APEX_PHASE4C_TEST_DATABASE_URL",
        "APEX_REGISTRATION_TEST_DATABASE_URL", "APEX_BARCODE_TEST_DATABASE_URL"]
    names = list(targets)
    values = [names[0], names[0], *names]
    env = dict(os.environ, JWT_SECRET="phase7e-disposable-only")
    for key, name in zip(keys, values, strict=True):
        env[key] = f"postgresql+asyncpg://postgres@/{name}?host=/var/run/postgresql"
    result = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
        "--tb=short", *sys.argv[1:]], cwd=backend, env=env, capture_output=True, text=True)
    log = result.stdout + result.stderr
    Path("/tmp/phase7e-backend-final.log").write_text(log)
    print(log, end="")
    raise SystemExit(result.returncode)
