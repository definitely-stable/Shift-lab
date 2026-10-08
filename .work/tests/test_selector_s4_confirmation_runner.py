import json
import tempfile
import unittest
from pathlib import Path
import sys

TOOLS = Path(__file__).resolve().parents[1] / "tools"
ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT
sys.path.insert(0, str(TOOLS))

import selector_s4_confirmation as frozen  # noqa: E402
import selector_s4_confirmation_runner as runner  # noqa: E402


class RunnerPlan(unittest.TestCase):
    def test_runner_accepts_exact_frozen_plan(self):
        plan = frozen.build_plan(runner.PROTOCOL_SHA)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plan.json"
            path.write_text(json.dumps(plan), encoding="utf-8")
            got = runner.load_plan(path)
        self.assertEqual(got, plan)
        self.assertEqual(got["expected_measurements"], 115)

    def test_driver_input_is_closed_and_deterministic(self):
        plan = frozen.build_plan(runner.PROTOCOL_SHA)
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / "a.tsv"
            b = Path(tmp) / "b.tsv"
            runner.driver_input(plan, a)
            runner.driver_input(plan, b)
            self.assertEqual(a.read_bytes(), b.read_bytes())
            lines = a.read_text(encoding="utf-8").splitlines()
        self.assertEqual(sum(line.startswith("T\t") for line in lines), 9)
        self.assertEqual(sum(line.startswith("B\t") for line in lines), 106)
        self.assertTrue(all(len(line.split("\t")) == 8 for line in lines))

    def test_selection_record_keeps_rust_and_python_independent(self):
        rust = {
            "selections": [
                {"target_occurrence_id": "a", "rust_k2": ["x", "y"]},
                {"target_occurrence_id": "b", "rust_k2": ["z"]},
            ]
        }
        python = {"a": ["x", "y"], "b": ["z"]}
        got = runner.selection_record(rust, python)
        self.assertEqual(got["schema"], runner.SELECTION_SCHEMA)
        self.assertEqual(got["targets"][0]["rust_k2"], got["targets"][0]["python_k2"])


class WorkflowBoundary(unittest.TestCase):
    def read(self, name):
        return (REPO / ".github" / "workflows" / name).read_text(encoding="utf-8")

    def test_autostart_is_one_shot_on_exact_parent(self):
        text = self.read("selector-s4-confirm-autostart.yml")
        self.assertIn(
            "github.event.before == 'e1ee235fe08c7cc1f6e8ec8884b65439435adf92'",
            text,
        )
        self.assertIn('test "$GITHUB_WORKFLOW_SHA" = "$GITHUB_SHA"', text)
        self.assertIn("selector-s4-confirm-repeat.yml/dispatches", text)
        self.assertIn('--arg repeat "A"', text)

    def test_repeat_is_exact_sha_bound_and_has_no_rerun_path(self):
        text = self.read("selector-s4-confirm-repeat.yml")
        self.assertIn("actions: write", text)
        self.assertIn('test "$SOURCE_SHA" = "$GITHUB_SHA"', text)
        self.assertIn('test "$GITHUB_WORKFLOW_SHA" = "$GITHUB_SHA"', text)
        self.assertIn("abf6bd07540a132ddf2af4fa1001db103b27a9f8", text)
        self.assertIn("selector-s4-confirm-repeat.yml/dispatches", text)
        self.assertIn("selector-s4-confirm-evaluate.yml/dispatches", text)
        self.assertNotIn("rerun", text.lower())
        self.assertNotIn("re-run", text.lower())

    def test_parity_precedes_any_chunkshift_measurement(self):
        text = (TOOLS / "selector_s4_confirmation_runner.py").read_text(encoding="utf-8")
        parity = text.index("parity_ok =")
        manifests = text.index("create_manifests(plan, store, cli, work)")
        quality = text.index("quality_table(plan, store, cli, manifests, work)")
        self.assertLess(parity, manifests)
        self.assertLess(parity, quality)

    def test_evaluator_closes_provider_and_artifact_surface(self):
        text = self.read("selector-s4-confirm-evaluate.yml")
        self.assertIn("Require exactly two S4-C repeat runs for this implementation", text)
        self.assertIn("expected exact two-run provider set", text)
        self.assertIn('"run_attempt": 1', text)
        self.assertIn('"path": ".github/workflows/selector-s4-confirm-repeat.yml"', text)
        self.assertIn("artifact_digest", text)
        self.assertIn("unexpected repeat artifact files", text)
        self.assertIn("protocol/.work/tools/selector_s4_confirmation.py evaluate", text)
        for name in (
            "admission.json", "measurements.jsonl", "manifests.jsonl",
            "selection.json", "rust-cost.json", "timing.json", "run.json",
        ):
            self.assertIn(name, text)


if __name__ == "__main__":
    unittest.main()
