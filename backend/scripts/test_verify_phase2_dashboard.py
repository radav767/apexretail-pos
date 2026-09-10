#!/usr/bin/env python3
import json
import os
import tempfile
import unittest
from decimal import Decimal
from unittest.mock import patch

import verify_phase2_dashboard as verifier


COMPANY_ID = "1b42be85-47a9-435a-8f40-9a051ee781ae"
ASYNC_URL = "postgresql+asyncpg://app:secret@db.example/apexretail_pos"


class FakeCursor:
    def __init__(self, row):
        self.row = row
        self.parameters = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, _sql, parameters):
        self.parameters = parameters

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, row):
        self.query = FakeCursor(row)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self.query


def dashboard_response(gross_sales="100.00"):
    return {
        "range_key": "today",
        "reporting_timezone": "Africa/Harare",
        "metrics": {
            "gross_sales": {"available": True, "value": gross_sales},
            "refunds": {"available": True, "value": "10.00"},
            "net_sales": {"available": True, "value": "90.00"},
            "cost_of_sales": {"available": True, "value": "40.00"},
            "gross_profit": {"available": True, "value": "50.00"},
            "discounts": {"available": True, "value": "5.00"},
        },
    }


class DashboardFinalizerTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory(
            prefix="apex-phase2-dashboard-finalizer-test."
        )
        self.response_file = os.path.join(self.temporary_directory.name, "response.json")
        self.database_row = tuple(
            Decimal(value) for value in ("100", "10", "90", "40", "50", "5")
        ) + (True,)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def write_response(self, response):
        with open(self.response_file, "w", encoding="utf-8") as output:
            json.dump(response, output)

    def test_mocked_success_uses_company_id_and_sync_psycopg2_url(self):
        self.write_response(dashboard_response())
        connection = FakeConnection(self.database_row)

        with patch.object(verifier.psycopg2, "connect", return_value=connection) as connect:
            verifier.verify_dashboard(self.response_file, COMPANY_ID, ASYNC_URL)

        connected_url = connect.call_args.args[0]
        self.assertTrue(connected_url.startswith("postgresql://"))
        self.assertNotIn("+asyncpg", connected_url)
        self.assertEqual(connection.query.parameters[0], COMPANY_ID)

    def test_main_reads_distinct_expected_company_environment_variable(self):
        self.write_response(dashboard_response())
        environment = {
            "DASHBOARD_RESPONSE": self.response_file,
            "EXPECTED_DASHBOARD_COMPANY_ID": COMPANY_ID,
        }
        with patch.dict(os.environ, environment, clear=True), patch.object(
            verifier, "dotenv_values", return_value={"DATABASE_URL": ASYNC_URL}
        ), patch.object(verifier, "verify_dashboard") as verify:
            verifier.main()

        verify.assert_called_once_with(self.response_file, COMPANY_ID, ASYNC_URL)

    def test_metric_mismatch_fails_finalization(self):
        self.write_response(dashboard_response(gross_sales="99.99"))
        connection = FakeConnection(self.database_row)

        with patch.object(verifier.psycopg2, "connect", return_value=connection):
            with self.assertRaisesRegex(SystemExit, "Dashboard gross_sales mismatch"):
                verifier.verify_dashboard(self.response_file, COMPANY_ID, ASYNC_URL)


if __name__ == "__main__":
    unittest.main()
