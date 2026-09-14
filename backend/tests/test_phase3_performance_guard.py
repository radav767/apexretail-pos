import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).parents[1] / "scripts/measure_phase3_dashboard.py"
SPEC = importlib.util.spec_from_file_location("measure_phase3_dashboard", SCRIPT)
MEASURE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MEASURE)


class Phase3PerformanceGuardTest(unittest.TestCase):
    def test_threshold_accepts_queries_at_or_below_ceiling(self):
        measurements = {
            "summary": {"execution_ms": MEASURE.MAX_QUERY_EXECUTION_MS},
            "daily_trend": {"execution_ms": 125.0},
        }
        self.assertEqual(MEASURE.threshold_failures(measurements), {})

    def test_threshold_reports_each_slow_query(self):
        measurements = {
            "summary": {"execution_ms": MEASURE.MAX_QUERY_EXECUTION_MS + 0.001},
            "daily_trend": {"execution_ms": 125.0},
        }
        self.assertEqual(
            MEASURE.threshold_failures(measurements),
            {"summary": MEASURE.MAX_QUERY_EXECUTION_MS + 0.001},
        )

    def test_plan_evidence_keeps_diagnostic_nodes_without_query_text(self):
        plan = {
            "Node Type": "Hash Join",
            "Join Type": "Inner",
            "Actual Rows": 3,
            "Filter": "sensitive query detail",
            "Plans": [{
                "Node Type": "Seq Scan",
                "Relation Name": "sale_items",
                "Actual Loops": 1,
            }],
        }
        self.assertEqual(MEASURE.plan_evidence(plan), {
            "Node Type": "Hash Join",
            "Join Type": "Inner",
            "Actual Rows": 3,
            "Plans": [{
                "Node Type": "Seq Scan",
                "Relation Name": "sale_items",
                "Actual Loops": 1,
            }],
        })


if __name__ == "__main__":
    unittest.main()
