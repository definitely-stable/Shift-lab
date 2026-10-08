"""S4-C v2 erratum: synthetic-only, no evaluation split inspected."""
import json
import tempfile
import unittest
from pathlib import Path
import sys

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
import selector_s4_confirmation as v1  # noqa: E402
import selector_s4_confirmation_v2 as v2  # noqa: E402


class CostGateErratum(unittest.TestCase):
    def cost(self, index_bytes):
        return {
            "schema": v2.COST_SCHEMA,
            "objects": 2,
            "object_bytes_scanned": 1024 * 1024,
            "descriptor_bytes": 128,
            "descriptor_wall_ns": 1_000_000,
            "descriptor_cpu_ns": 500_000,
            "catalog_wall_ns": 1_000,
            "catalog_cpu_ns": 1_000,
            "index_bytes": index_bytes,
            "query_ns": [1_000] * v2.EXPECTED_TARGETS,
        }

    def evaluate_cost(self, module, index_bytes):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cost.json"
            path.write_text(json.dumps(self.cost(index_bytes)), encoding="utf-8")
            return module._cost(path)

    def test_under_and_exactly_at_frozen_limit_keep_v1_decision(self):
        for index in [0, 64, 127, 128]:
            with self.subTest(index=index):
                old = self.evaluate_cost(v1, index)
                new = self.evaluate_cost(v2, index)
                self.assertTrue(new["index_budget_ok"])
                self.assertTrue(new["eligible"])
                for field in old:
                    self.assertEqual(old[field], new[field])

    def test_valid_over_budget_is_cost_rejection_not_invalid(self):
        for index in [129, 192, 10_000]:
            with self.subTest(index=index):
                with self.assertRaises(v1.ConfirmError):
                    self.evaluate_cost(v1, index)
                got = self.evaluate_cost(v2, index)
                self.assertFalse(got["index_budget_ok"])
                self.assertFalse(got["eligible"])
                self.assertEqual(got["index_bytes"], index)

    def test_malformed_cost_remains_invalid(self):
        for index in [-1, None, True, 3.5, "192", [], {}]:
            with self.subTest(index=index):
                with self.assertRaises(v2.ConfirmError):
                    self.evaluate_cost(v2, index)

    def test_all_science_thresholds_unchanged_except_verdict_class(self):
        # Guard against accidental edits to fixed population, K, and thresholds.
        self.assertEqual(v1.CONSUMER_SHA, v2.CONSUMER_SHA)
        self.assertEqual(v1.PLAN_SCHEMA, v2.PLAN_SCHEMA)
        self.assertEqual(v1.RESULT_SCHEMA, v2.RESULT_SCHEMA)
        self.assertEqual(v1.EXPECTED_TARGETS, v2.EXPECTED_TARGETS)
        self.assertEqual(v1.EXPECTED_PAIRS, v2.EXPECTED_PAIRS)
        self.assertEqual(v1.ROUND_ORDERS, v2.ROUND_ORDERS)
        self.assertEqual(v1.K, v2.K)


if __name__ == "__main__":
    unittest.main()
