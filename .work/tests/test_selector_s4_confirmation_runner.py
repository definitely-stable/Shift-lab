import json
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path
import sys

TOOLS = Path(__file__).resolve().parents[1] / "tools"
ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT
sys.path.insert(0, str(TOOLS))

import selector_s4_confirmation_v2 as frozen  # noqa: E402
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
            "github.event.before == '0027d521a48701e504438a3ba750594647358d55'",
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
        self.assertIn("0027d521a48701e504438a3ba750594647358d55", text)
        self.assertIn("selector-s4-confirm-repeat.yml/dispatches", text)
        self.assertIn("selector-s4-confirm-evaluate.yml/dispatches", text)
        self.assertNotIn("rerun", text.lower())
        self.assertNotIn("re-run", text.lower())

    def test_all_runtime_paths_use_exact_v2_authority(self):
        autostart = self.read("selector-s4-confirm-autostart.yml")
        repeat = self.read("selector-s4-confirm-repeat.yml")
        evaluate = self.read("selector-s4-confirm-evaluate.yml")
        runtime = (REPO / ".work/tools/selector_s4_confirmation_runner.py").read_text(encoding="utf-8")
        for text in (repeat, evaluate, runtime):
            self.assertIn("0027d521a48701e504438a3ba750594647358d55", text)
            self.assertNotIn("abf6bd07540a132ddf2af4fa1001db103b27a9f8", text)
        for text in (repeat, evaluate):
            self.assertIn("selector_s4_confirmation_v2.py plan", text)
        self.assertIn("selector_s4_confirmation_v2.py evaluate", evaluate)
        self.assertIn("github.event.before == '0027d521a48701e504438a3ba750594647358d55'", autostart)
        self.assertNotIn("e1ee235fe08c7cc1f6e8ec8884b65439435adf92", autostart)

    def test_parity_precedes_any_chunkshift_measurement(self):
        # Exercise the runtime guard rather than text positions: the source file
        # contains an earlier *definition* of create_manifests, which is not a call.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cli = root / "chunkshift.dll"
            binary = root / "delsk-confirm"
            cli.write_bytes(b"test-cli")
            binary.write_bytes(b"test-rust")
            args = SimpleNamespace(
                plan=root / "plan.json",
                store=root,
                chunkshift_dll=cli,
                rust_binary=binary,
                out_dir=root / "out",
                repeat="A",
                protocol_root=root,
                protocol_authority=runner.PROTOCOL_SHA,
                implementation_sha="a" * 40,
            )
            mismatch = {
                "schema": runner.SELECTION_SCHEMA,
                "selector": "delsk.simple-selector.v1",
                "k": 2,
                "targets": [{
                    "target_occurrence_id": "synthetic",
                    "rust_k2": ["rust"],
                    "python_k2": ["python"],
                }],
            }
            with (
                patch.object(runner, "load_plan", return_value={}),
                patch.object(runner, "driver_input"),
                patch.object(runner, "run_rust_driver", return_value={}),
                patch.object(runner, "python_selection", return_value={}),
                patch.object(runner, "selection_record", return_value=mismatch),
                patch.object(runner, "rust_cost_record", return_value={}),
                patch.object(runner, "create_manifests") as manifests,
                patch.object(runner, "quality_table") as quality,
                patch.object(runner, "timing_rounds") as timing,
            ):
                self.assertEqual(runner.run(args), 0)
            manifests.assert_not_called()
            quality.assert_not_called()
            timing.assert_not_called()
            record = json.loads((root / "out" / "run.json").read_text(encoding="utf-8"))
            self.assertEqual(record["science_state"], "PARITY_FAILED")
            self.assertEqual((root / "out" / "measurements.jsonl").read_bytes(), b"")
            self.assertEqual((root / "out" / "manifests.jsonl").read_bytes(), b"")

    def test_evaluator_closes_provider_and_artifact_surface(self):
        text = self.read("selector-s4-confirm-evaluate.yml")
        self.assertIn("Wait for exact first-attempt repeat workflows to finish", text)
        self.assertIn("for attempt in $(seq 1 24)", text)
        self.assertIn('test "$conclusion" = "success"', text)
        self.assertIn("Require exactly two S4-C repeat runs for this implementation", text)
        self.assertIn("expected exact two-run provider set", text)
        self.assertIn('"run_attempt": 1', text)
        self.assertIn('"path": ".github/workflows/selector-s4-confirm-repeat.yml"', text)
        self.assertIn("artifact_digest", text)
        self.assertIn("unexpected repeat artifact files", text)
        self.assertIn("protocol/.work/tools/selector_s4_confirmation_v2.py evaluate", text)
        for name in (
            "admission.json", "measurements.jsonl", "manifests.jsonl",
            "selection.json", "rust-cost.json", "timing.json", "run.json",
        ):
            self.assertIn(name, text)


if __name__ == "__main__":
    unittest.main()
