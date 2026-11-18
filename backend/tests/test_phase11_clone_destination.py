"""Destination guards run without importing application settings or opening a DB."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    'clone_verifier', Path(__file__).parents[1] / 'scripts/verify_phase10_clone_compatibility.py'
)
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


class CloneDestinationTests(unittest.TestCase):
    def test_missing_production_remote_and_wrong_driver_destinations_fail(self):
        for value in (None, '',
                      'postgresql+asyncpg://postgres@/apexretail_pos?host=/var/run/postgresql',
                      f'postgresql+asyncpg://postgres@remote/{verifier.DATABASE}',
                      f'postgresql+asyncpg://postgres@/{verifier.DATABASE}',
                      f'postgresql://postgres@/{verifier.DATABASE}?host=/tmp/socket'):
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                verifier.compatibility_url(value)

    def test_explicit_named_clone_socket_is_preserved(self):
        value = f'postgresql+asyncpg://postgres@/{verifier.DATABASE}?host=/tmp/synthetic-socket&port=55441'
        self.assertEqual(verifier.compatibility_url(value), value)
