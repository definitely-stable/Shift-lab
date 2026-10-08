"""S4-C v3: synthetic-only runner-name counterexample, no E1 inspection."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_selector_s4_confirmation import SyntheticEvaluator
import selector_s4_confirmation_v2 as v2
import selector_s4_confirmation_v3 as v3


class RunnerNameErratum(unittest.TestCase):
    def fixture(self, root, same_name=True, same_id=False):
        synthetic = SyntheticEvaluator()
        plan = synthetic.plan()
        a, b = root / "A", root / "B"
        synthetic.make_repeat(a, plan, "A", 10, "Hosted Agent")
        synthetic.make_repeat(b, plan, "B", 10 if same_id else 11,
                              "Hosted Agent" if same_name else "Other Agent")
        return plan, a, b

    def test_same_display_name_is_not_a_validity_failure_for_distinct_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan, a, b = self.fixture(Path(tmp), same_name=True)
            with patch.object(v2, "build_plan", return_value=plan):
                with self.assertRaisesRegex(v2.ConfirmError, "runner name"):
                    v2.evaluate(plan, a, b)
            with patch.object(v3, "build_plan", return_value=plan):
                result = v3.evaluate(plan, a, b)
            self.assertIn(result["verdict"], ("G5_SCOPED_PASS_K2", "G5_REJECT_K2"))
            self.assertTrue(result["repeat_a"]["quality_ok"])
            self.assertTrue(result["repeat_b"]["quality_ok"])

    def test_distinct_names_preserve_v2_science_verdict(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan, a, b = self.fixture(Path(tmp), same_name=False)
            with patch.object(v2, "build_plan", return_value=plan):
                previous = v2.evaluate(plan, a, b)
            with patch.object(v3, "build_plan", return_value=plan):
                current = v3.evaluate(plan, a, b)
            self.assertEqual(current, previous)

    def test_duplicate_github_run_ids_remain_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan, a, b = self.fixture(Path(tmp), same_name=True, same_id=True)
            with patch.object(v3, "build_plan", return_value=plan):
                with self.assertRaisesRegex(v3.ConfirmError, "run id"):
                    v3.evaluate(plan, a, b)

    def test_missing_runner_provenance_still_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan, a, b = self.fixture(Path(tmp), same_name=True)
            file = b / "run.json"
            run = json.loads(file.read_text(encoding="utf-8"))
            run["runner_name"] = ""
            file.write_text(json.dumps(run), encoding="utf-8")
            with patch.object(v3, "build_plan", return_value=plan):
                with self.assertRaisesRegex(v3.ConfirmError, "runner missing"):
                    v3.evaluate(plan, a, b)

    def test_all_frozen_quality_cost_constants_and_schema_match_v2(self):
        for name in (
            "CONSUMER_SHA", "CANDIDATE_LOCK_SHA256", "COVERAGE_SHA256",
            "CORPUS_LOCK_SHA256", "EXPECTED_TARGETS", "EXPECTED_PAIRS",
            "K", "ROUND_ORDERS", "PLAN_SCHEMA", "RESULT_SCHEMA",
            "MEASUREMENT_SCHEMA", "COST_SCHEMA", "TIMING_SCHEMA",
        ):
            self.assertEqual(getattr(v2, name), getattr(v3, name), name)


if __name__ == "__main__":
    unittest.main()
