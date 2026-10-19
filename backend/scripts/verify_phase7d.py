"""Run all backend tests exclusively on the Phase 7D disposable fixture clones."""
import os
import subprocess
import sys
from pathlib import Path

databases = {
    "DATABASE_URL": "apexretail_phase7c_test_phase7d",
    "APEX_PHASE7D_TEST_DATABASE_URL": "apexretail_phase7c_test_phase7d",
    "APEX_PHASE7C_TEST_DATABASE_URL": "apexretail_phase7c_test_phase7d",
    "APEX_PHASE7B_TEST_DATABASE_URL": "apexretail_phase7b_test_phase7d",
    "APEX_PHASE5_TEST_DATABASE_URL": "apexretail_phase5_test_phase7d",
    "APEX_PHASE4A_TEST_DATABASE_URL": "apexretail_phase4a_test_phase7d",
    "APEX_PHASE4B_TEST_DATABASE_URL": "apexretail_phase4b_test_phase7d",
    "APEX_DASHBOARD_TEST_DATABASE_URL": "apexretail_phase2_test_phase7d",
    "APEX_PHASE4C_TEST_DATABASE_URL": "apexretail_phase4c_test_phase7d",
    "APEX_REGISTRATION_TEST_DATABASE_URL": "apexretail_registration_test_phase7d",
    "APEX_BARCODE_TEST_DATABASE_URL": "apexretail_barcode_test_phase7d",
}
environment = dict(os.environ, JWT_SECRET="phase7d-disposable-only")
for key, database in databases.items():
    assert "test" in database and database.endswith("phase7d")
    environment[key] = f"postgresql+asyncpg://postgres@/{database}?host=/var/run/postgresql"
raise SystemExit(subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--tb=short", *sys.argv[1:]], cwd=Path(__file__).resolve().parent.parent, env=environment).returncode)
