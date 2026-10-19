"""Create ONLY named disposable clones of previously verified synthetic fixtures."""
import os
import subprocess
import sys
from pathlib import Path

DATABASES = {
    "apexretail_phase7c_test_phase7d": "apexretail_phase7c_test",
    "apexretail_phase7b_test_phase7d": "apexretail_phase7b_test",
    "apexretail_phase5_test_phase7d": "apexretail_phase5_test_phase7b",
    "apexretail_phase4a_test_phase7d": "apexretail_phase4a_test_phase7b",
    "apexretail_phase4b_test_phase7d": "apexretail_phase4b_test_phase7b",
    "apexretail_phase2_test_phase7d": "apexretail_phase2_test_phase7b",
    "apexretail_phase4c_test_phase7d": "apexretail_phase4c_test_phase7b",
    "apexretail_registration_test_phase7d": "apexretail_registration_test_phase7b",
    "apexretail_barcode_test_phase7d": "apexretail_barcode_test_phase7b",
}


if __name__ == "__main__":
    for target, source in DATABASES.items():
        assert "test" in source and "test" in target and target.endswith("phase7d")
        present = subprocess.check_output(["psql", "-X", "-At", "-d", "postgres", "-c", f"SELECT 1 FROM pg_database WHERE datname='{target}'"], text=True).strip()
        if not present:
            subprocess.run(["psql", "-X", "-v", "ON_ERROR_STOP=1", "-d", "postgres", "-c", f"CREATE DATABASE {target} TEMPLATE {source}"], check=True)
        environment = dict(os.environ, DATABASE_URL=f"postgresql+asyncpg://postgres@/{target}?host=/var/run/postgresql")
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], env=environment, cwd=Path(__file__).resolve().parent.parent, check=True)
