import os
import unittest
from unittest.mock import patch

from app.core.config import resolve_database_urls


class DatabaseConfigTest(unittest.TestCase):
    def test_explicit_database_url_is_honored_for_alembic_and_app(self):
        rehearsal_url = (
            "postgresql+asyncpg://apex_user:apex123@127.0.0.1/"
            "apexretail_phase1_rehearsal_20260818_1510"
        )
        misleading_env = {
            "DATABASE_URL": "postgresql+asyncpg://apex_user:apex123@127.0.0.1/apexretail_pos",
            "JWT_SECRET": "test-secret",
        }

        resolved = resolve_database_urls(
            explicit_url=rehearsal_url,
            env=misleading_env,
        )

        self.assertEqual(
            resolved.database_name,
            "apexretail_phase1_rehearsal_20260818_1510",
        )
        self.assertIn(
            "apexretail_phase1_rehearsal_20260818_1510",
            resolved.async_url,
        )
        self.assertIn(
            "apexretail_phase1_rehearsal_20260818_1510",
            resolved.alembic_url,
        )
        self.assertNotIn("apexretail_pos", resolved.async_url)
        self.assertNotIn("apexretail_pos", resolved.alembic_url)
        self.assertTrue(resolved.async_url.startswith("postgresql+asyncpg://"))
        self.assertTrue(
            resolved.alembic_url.startswith("postgresql+psycopg2://")
        )

    def test_environment_database_url_is_honored(self):
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": (
                    "postgresql+asyncpg://apex_user:apex123@127.0.0.1/"
                    "apexretail_phase1_rehearsal_20260818_1510"
                ),
                "JWT_SECRET": "test-secret",
            },
            clear=False,
        ):
            resolved = resolve_database_urls()

        self.assertEqual(
            resolved.database_name,
            "apexretail_phase1_rehearsal_20260818_1510",
        )
        self.assertNotIn("apexretail_pos", resolved.alembic_url)

    def test_passwords_are_redacted(self):
        resolved = resolve_database_urls(
            explicit_url=(
                "postgresql+asyncpg://apex_user:super-secret@127.0.0.1/"
                "apexretail_phase1_rehearsal_20260818_1510"
            )
        )

        self.assertIn(":***@", resolved.redacted_async_url)
        self.assertIn(":***@", resolved.redacted_alembic_url)
        self.assertNotIn("super-secret", resolved.redacted_async_url)
        self.assertNotIn("super-secret", resolved.redacted_alembic_url)

    def test_missing_database_url_fails_clearly(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(
                RuntimeError,
                "DATABASE_URL is empty",
            ):
                resolve_database_urls(env={})

    def test_malformed_database_url_fails_clearly(self):
        with self.assertRaisesRegex(RuntimeError, "Malformed DATABASE_URL"):
            resolve_database_urls(explicit_url="not-a-url")


if __name__ == "__main__":
    unittest.main()
