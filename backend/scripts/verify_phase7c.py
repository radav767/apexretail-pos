"""Run regression suites with explicitly isolated test database settings only."""
import os
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
databases = {
    "DATABASE_URL": "apexretail_phase7c_test",
    "APEX_PHASE7C_TEST_DATABASE_URL": "apexretail_phase7c_test",
    "APEX_PHASE7B_TEST_DATABASE_URL": "apexretail_phase7b_test",
    "APEX_PHASE5_TEST_DATABASE_URL": "apexretail_phase5_test_phase7b",
    "APEX_PHASE4A_TEST_DATABASE_URL": "apexretail_phase4a_test_phase7b",
    "APEX_PHASE4B_TEST_DATABASE_URL": "apexretail_phase4b_test_phase7b",
    "APEX_DASHBOARD_TEST_DATABASE_URL": "apexretail_phase2_test_phase7b",
    "APEX_PHASE4C_TEST_DATABASE_URL": "apexretail_phase4c_test_phase7b",
    "APEX_REGISTRATION_TEST_DATABASE_URL": "apexretail_registration_test_phase7b",
    "APEX_BARCODE_TEST_DATABASE_URL": "apexretail_barcode_test_phase7b",
}
environment = dict(os.environ, JWT_SECRET="phase7c-disposable-only")
for key, database in databases.items():
    if "test" not in database: raise SystemExit("Refusing non-test database")
    environment[key] = f"postgresql+asyncpg://postgres@/{database}?host=/var/run/postgresql"
raise SystemExit(subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--tb=short"], cwd=root, env=environment).returncode)
