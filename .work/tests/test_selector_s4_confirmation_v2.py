"""S4-C v2 erratum: synthetic-only, no evaluation split inspected."""
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
import sys

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
import selector_s4_confirmation as v1  # noqa: E402
import selector_s4_confirmation_v2 as v2  # noqa: E402
import test_selector_s4_confirmation as synthetic  # noqa: E402


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

    def test_over_budget_produces_final_scoped_reject_in_both_repeats(self):
        fixture = synthetic.SyntheticEvaluator()
        plan = fixture.plan()
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a", Path(tmp) / "b"
            fixture.make_repeat(a, plan, "A", 1, "runner-a")
            fixture.make_repeat(b, plan, "B", 2, "runner-b")
            for folder in (a, b):
                path = folder / "rust-cost.json"
                cost = json.loads(path.read_text(encoding="utf-8"))
                cost["index_bytes"] = 96 * cost["objects"]
                path.write_text(json.dumps(cost), encoding="utf-8")
            with patch.object(v2, "build_plan", return_value=plan):
                verdict = v2.evaluate(plan, a, b)
            self.assertEqual(verdict["verdict"], "G5_REJECT_K2")
            self.assertTrue(verdict["repeat_a"]["quality_ok"])
            self.assertTrue(verdict["repeat_b"]["quality_ok"])
            self.assertFalse(verdict["repeat_a"]["rust_cost"]["index_budget_ok"])
            self.assertFalse(verdict["repeat_b"]["rust_cost"]["index_budget_ok"])
            with patch.object(v1, "build_plan", return_value=plan):
                with self.assertRaises(v1.ConfirmError):
                    v1.evaluate(plan, a, b)

    def test_over_budget_on_only_one_repeat_still_rejects(self):
        fixture = synthetic.SyntheticEvaluator()
        plan = fixture.plan()
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a", Path(tmp) / "b"
            fixture.make_repeat(a, plan, "A", 1, "runner-a")
            fixture.make_repeat(b, plan, "B", 2, "runner-b")
            path = b / "rust-cost.json"
            cost = json.loads(path.read_text(encoding="utf-8"))
            cost["index_bytes"] = 96 * cost["objects"]
            path.write_text(json.dumps(cost), encoding="utf-8")
            with patch.object(v2, "build_plan", return_value=plan):
                verdict = v2.evaluate(plan, a, b)
            self.assertEqual(verdict["verdict"], "G5_REJECT_K2")
            self.assertTrue(verdict["repeat_a"]["eligible"])
            self.assertFalse(verdict["repeat_b"]["eligible"])

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
