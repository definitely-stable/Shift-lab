import json
import tempfile
import unittest
import unittest.mock
from pathlib import Path
import sys

WORK = Path(__file__).resolve().parents[1]
REPO = WORK.parent
TOOLS = WORK / "tools"
sys.path.insert(0, str(TOOLS))

import selector_s4_confirmation as c  # noqa: E402


class FrozenPlan(unittest.TestCase):
    def test_sealed_evaluation_plan_is_exact(self):
        plan = c.build_plan("a" * 40)
        self.assertEqual(plan["schema"], c.PLAN_SCHEMA)
        self.assertEqual(plan["status"], "PREREGISTERED_NOT_RUN")
        self.assertEqual(plan["split"], "evaluation")
        self.assertEqual(plan["family"], "bzip2")
        self.assertEqual(plan["k"], 2)
        self.assertEqual(plan["abstention_level"], 0)
        self.assertEqual(len(plan["targets"]), 9)
        self.assertEqual(sum(len(t["bases"]) for t in plan["targets"]), 106)
        self.assertEqual(plan["expected_measurements"], 115)
        self.assertNotIn("file", {t["track"] for t in plan["targets"]})
        self.assertEqual(
            {t["track"] for t in plan["targets"]},
            {"chunk-4k", "chunk-8k", "chunk-16k", "chunk-32k", "tar", "tar-gz"},
        )
        for target in plan["targets"]:
            universe = {b["object_id"] for b in target["bases"]}
            self.assertTrue(set(target["previous1"]).issubset(universe))
            self.assertTrue(set(target["size1"]).issubset(universe))
            self.assertLessEqual(len(target["previous1"]), 1)
            self.assertLessEqual(len(target["size1"]), 1)

    def test_plan_is_deterministic(self):
        self.assertEqual(c.build_plan("b" * 40), c.build_plan("b" * 40))

    def test_protocol_has_no_k4_rescue(self):
        text = (WORK / "selector" / "s4-confirmation.md").read_text(encoding="utf-8")
        self.assertIn("K = 2 only", text)
        self.assertIn("There is no threshold tuning, K tuning or fallback to K4", text)
        self.assertIn("G5_SCOPED_PASS_K2", text)
        self.assertIn("G5_REJECT_K2", text)
        self.assertIn("No rerun and no replacement dispatch is admissible", text)


class SyntheticEvaluator(unittest.TestCase):
    def plan(self):
        targets = []
        for i in range(9):
            tid = f"{1000 + i:064x}"
            target = f"{2000 + i:064x}"
            b0 = f"{3000 + 2 * i:064x}"
            b1 = f"{3001 + 2 * i:064x}"
            targets.append({
                "target_occurrence_id": tid,
                "family_id": "bzip2",
                "track": "chunk-4k",
                "target": {
                    "object_id": target,
                    "bytes": 1000,
                    "path": f"file-{i}",
                    "offset": i * 4096,
                    "line": "bzip2",
                    "version_rank": 3,
                },
                "bases": [
                    {"object_id": b0, "bytes": 995, "path": f"file-{i}", "offset": i * 4096,
                     "line": "bzip2", "version_rank": 2},
                    {"object_id": b1, "bytes": 990, "path": f"other-{i}", "offset": i * 4096,
                     "line": "bzip2", "version_rank": 1},
                ],
                "previous1": [b0],
                "size1": [b0],
            })
        return {
            "schema": c.PLAN_SCHEMA,
            "status": "PREREGISTERED_NOT_RUN",
            "protocol_authority": "a" * 40,
            "consumer_commit": c.CONSUMER_SHA,
            "candidate_lock_sha256": c.CANDIDATE_LOCK_SHA256,
            "coverage_sha256": c.COVERAGE_SHA256,
            "corpus_lock_sha256": c.CORPUS_LOCK_SHA256,
            "split": "evaluation",
            "family": "bzip2",
            "k": 2,
            "abstention_level": 0,
            "expected_targets": 9,
            "expected_base_pairs": 18,
            "expected_measurements": 27,
            "round_orders": list(c.ROUND_ORDERS),
            "targets": targets,
        }

    def make_repeat(self, root, plan, role, run_id, runner, better=890, parity=True, pair_delta=0):
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)

        measurements = []
        selections = []
        for target in plan["targets"]:
            tid = target["target_occurrence_id"]
            target_id = target["target"]["object_id"]
            bases = [b["object_id"] for b in target["bases"]]
            for base, patch in ((None, 1000), (bases[0], 900), (bases[1], better + pair_delta)):
                measurements.append({
                    "schema": c.MEASUREMENT_SCHEMA,
                    "target_occurrence_id": tid,
                    "target_object_id": target_id,
                    "base_object_id": base,
                    "chunkshift_commit": c.CONSUMER_SHA,
                    "status": "ok",
                    "patch_bytes": patch,
                    "create_exit_code": 0,
                    "apply_exit_code": 0,
                    "applied_sha256": target_id,
                    "patch_file_digest": f"{4000 + len(measurements):064x}",
                })
            selections.append({
                "target_occurrence_id": tid,
                "rust_k2": bases,
                "python_k2": bases if parity else list(reversed(bases)),
            })

        (root / "measurements.jsonl").write_text(
            "".join(json.dumps(r, sort_keys=True) + "\n" for r in measurements),
            encoding="utf-8",
        )
        (root / "selection.json").write_text(json.dumps({
            "schema": c.SELECTION_SCHEMA,
            "selector": "delsk.simple-selector.v1",
            "k": 2,
            "targets": selections,
        }), encoding="utf-8")
        (root / "rust-cost.json").write_text(json.dumps({
            "schema": c.COST_SCHEMA,
            "objects": 27,
            "object_bytes_scanned": 100 * 1024 * 1024,
            "descriptor_bytes": 27 * 64,
            "index_bytes": 27 * 48,
            "descriptor_wall_ns": 200_000_000,
            "query_ns": [10_000 + i for i in range(9)],
        }), encoding="utf-8")
        rounds = []
        for order in c.ROUND_ORDERS:
            rounds.append({
                "order": order,
                "previous1": {
                    "create_wall_ns": 100_000_000,
                    "create_cpu_ns": 100_000_000,
                    "apply_wall_ns": 100_000_000,
                },
                "delsk2": {
                    "create_wall_ns": 150_000_000,
                    "create_cpu_ns": 150_000_000,
                    "apply_wall_ns": 105_000_000,
                },
            })
        (root / "timing.json").write_text(json.dumps({
            "schema": c.TIMING_SCHEMA,
            "rounds": rounds,
        }), encoding="utf-8")
        (root / "run.json").write_text(json.dumps({
            "schema": c.RUN_SCHEMA,
            "repeat": role,
            "protocol_authority": plan["protocol_authority"],
            "chunkshift_commit": c.CONSUMER_SHA,
            "run_attempt": 1,
            "event": "workflow_dispatch",
            "status": "completed",
            "conclusion": "success",
            "run_id": run_id,
            "runner_name": runner,
            "implementation_sha": "f" * 40,
            "head_sha": "f" * 40,
            "workflow_sha": "f" * 40,
            "ref": "refs/heads/main",
        }), encoding="utf-8")

    def test_pass(self):
        plan = self.plan()
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            a, b = tmp / "a", tmp / "b"
            self.make_repeat(a, plan, "A", 1, "runner-a")
            self.make_repeat(b, plan, "B", 2, "runner-b")
            with unittest.mock.patch.object(c, "build_plan", return_value=plan):
                result = c.evaluate(plan, a, b)
        self.assertEqual(result["verdict"], "G5_SCOPED_PASS_K2")
        self.assertTrue(result["repeat_a"]["eligible"])
        self.assertTrue(result["repeat_b"]["eligible"])

    def test_quality_reject(self):
        plan = self.plan()
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            a, b = tmp / "a", tmp / "b"
            self.make_repeat(a, plan, "A", 1, "runner-a", better=899)
            self.make_repeat(b, plan, "B", 2, "runner-b", better=899)
            with unittest.mock.patch.object(c, "build_plan", return_value=plan):
                result = c.evaluate(plan, a, b)
        self.assertEqual(result["verdict"], "G5_REJECT_K2")
        self.assertFalse(result["repeat_a"]["quality_ok"])

    def test_parity_failure_is_invalid(self):
        plan = self.plan()
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            a, b = tmp / "a", tmp / "b"
            self.make_repeat(a, plan, "A", 1, "runner-a", parity=False)
            self.make_repeat(b, plan, "B", 2, "runner-b")
            with unittest.mock.patch.object(c, "build_plan", return_value=plan):
                with self.assertRaises(c.ConfirmError):
                    c.evaluate(plan, a, b)

    def test_repeat_quality_mismatch_is_invalid(self):
        plan = self.plan()
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            a, b = tmp / "a", tmp / "b"
            self.make_repeat(a, plan, "A", 1, "runner-a")
            self.make_repeat(b, plan, "B", 2, "runner-b", pair_delta=1)
            with unittest.mock.patch.object(c, "build_plan", return_value=plan):
                with self.assertRaises(c.ConfirmError):
                    c.evaluate(plan, a, b)


class RawRetention(unittest.TestCase):
    def test_retention_is_one_shot_and_digest_bound(self):
        text = (REPO / ".github/workflows/selector-s4-retain.yml").read_text(encoding="utf-8")
        self.assertIn("github.event.before == 'a7d2d1346c70cb72adb62fdb221288414ea2132a'", text)
        self.assertIn("37597358766", text)
        self.assertIn("11471047037", text)
        self.assertIn("55a018575eb7a87c5334500723d362555123057ead7dfc53f372062db0eabb4c", text)
        self.assertIn("e8e0c0fae1e373a074441c26e2efbf7cfc199b43ad11a1453ec5e4f694f9ce57", text)
        self.assertIn("gzip -n -9", text)
        self.assertIn("refusing replacement", text)


if __name__ == "__main__":
    unittest.main()
