import importlib.util
import hashlib
import json
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

import selector_s4 as protocol  # noqa: E402
import selector_s4_runner as runner  # noqa: E402


class Sharding(unittest.TestCase):
    def test_protocol_plan_partitions_exactly_once(self):
        plan = protocol.build_plan()
        seen = []
        rows = 0
        for index in range(runner.SHARD_COUNT):
            targets = runner.shard_targets(plan, index)
            seen.extend(t["target_occurrence_id"] for t in targets)
            rows += runner.expected_rows(targets)
        expected = sorted(t["target_occurrence_id"] for t in plan["targets"])
        self.assertEqual(sorted(seen), expected)
        self.assertEqual(len(seen), len(set(seen)))
        self.assertEqual(len(seen), 119)
        self.assertEqual(rows, 3815)

    def test_shard_mapping_is_deterministic(self):
        plan = protocol.build_plan()
        a = [[t["target_occurrence_id"] for t in runner.shard_targets(plan, i)]
             for i in range(runner.SHARD_COUNT)]
        b = [[t["target_occurrence_id"] for t in runner.shard_targets(plan, i)]
             for i in range(runner.SHARD_COUNT)]
        self.assertEqual(a, b)
        self.assertTrue(all(a))


class Parsing(unittest.TestCase):
    def test_cli_key_values(self):
        self.assertEqual(
            runner.parse_kv("manifest-id=x\nphysical-bytes=12\n"),
            {"manifest-id": "x", "physical-bytes": "12"},
        )

    def test_duplicate_cli_key_fails_closed(self):
        with self.assertRaises(runner.RunnerError):
            runner.parse_kv("manifest-id=x\nmanifest-id=y\n")

    def test_object_verification_is_content_addressed(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = b"S4-object"
            import hashlib
            oid = hashlib.sha256(data).hexdigest()
            path = Path(tmp) / oid
            path.write_bytes(data)
            runner.verify_object(path, oid)
            path.write_bytes(data + b"!")
            with self.assertRaises(runner.RunnerError):
                runner.verify_object(path, oid)


    def test_measure_pair_deletes_patch_and_output_immediately(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            target_bytes = b"target-bytes"
            target_id = hashlib.sha256(target_bytes).hexdigest()
            target = {
                "target_occurrence_id": "t",
                "target_object_id": target_id,
            }
            store = work / "store"
            store.mkdir()
            (store / target_id).write_bytes(target_bytes)
            manifest = work / "target.csm"
            manifest.write_bytes(b"manifest")
            manifests = {
                target_id: ({"manifest_id": "target-manifest"}, manifest),
            }

            def fake_run(argv):
                if "create" in argv:
                    patch = Path(argv[argv.index("-o") + 1])
                    patch.write_bytes(b"patch")
                    return (
                        type("P", (), {
                            "returncode": 0,
                            "stdout": "target-manifest-id=target-manifest\npatch-bytes=5\n",
                            "stderr": "",
                        })(),
                        10,
                        9,
                    )
                output = Path(argv[argv.index("-o") + 1])
                output.write_bytes(target_bytes)
                return (
                    type("P", (), {"returncode": 0, "stdout": "applied=true\n", "stderr": ""})(),
                    4,
                    3,
                )

            with unittest.mock.patch.object(runner, "run_process", side_effect=fake_run):
                row = runner.measure_pair(Path("cli.dll"), target, None, store, manifests, work)

            self.assertEqual(row["status"], "ok")
            self.assertEqual(row["applied_sha256"], target_id)
            self.assertFalse(list(work.glob("*.csp")))
            self.assertFalse(list(work.glob("*.out")))

    def test_plan_rejects_wrong_consumer(self):
        plan = protocol.build_plan()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plan.json"
            bad = json.loads(json.dumps(plan))
            bad["consumer"]["commit"] = "0" * 40
            path.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaises(runner.RunnerError):
                runner.load_plan(path)


class WorkflowBoundary(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[2]
    SHARD = ROOT / ".github/workflows/selector-s4-shard.yml"
    COST = ROOT / ".github/workflows/selector-s4-cost.yml"
    EVALUATE = ROOT / ".github/workflows/selector-s4-evaluate.yml"
    AUTOSTART = ROOT / ".github/workflows/selector-s4-autostart.yml"

    def test_measurement_workflows_are_main_and_workflow_sha_bound(self):
        for path in (self.SHARD, self.COST):
            text = path.read_text(encoding="utf-8")
            self.assertIn('runs-on: ubuntu-24.04', text)
            self.assertNotIn("self-hosted", text)
            self.assertIn('test "$GITHUB_REF" = "refs/heads/main"', text)
            self.assertIn('test "$SOURCE_SHA" = "$GITHUB_SHA"', text)
            self.assertIn('test "$GITHUB_WORKFLOW_SHA" = "$GITHUB_SHA"', text)
            self.assertIn(runner.PROTOCOL_SHA, text)

    def test_evaluator_is_authority_and_workflow_sha_bound(self):
        text = self.EVALUATE.read_text(encoding="utf-8")
        self.assertIn('runs-on: ubuntu-24.04', text)
        self.assertNotIn("self-hosted", text)
        self.assertIn('test "$GITHUB_REF" = "refs/heads/main"', text)
        self.assertIn('test "$SOURCE_SHA" = "$GITHUB_SHA"', text)
        self.assertIn('test "$GITHUB_WORKFLOW_SHA" = "$GITHUB_SHA"', text)
        self.assertIn(runner.PROTOCOL_SHA, text)
        self.assertIn(".work/tools/selector_s4.py evaluate", text)


    def test_automatic_chain_is_one_shot_and_source_bound(self):
        auto = self.AUTOSTART.read_text(encoding="utf-8")
        cost = self.COST.read_text(encoding="utf-8")
        shard = self.SHARD.read_text(encoding="utf-8")
        evaluate = self.EVALUATE.read_text(encoding="utf-8")

        self.assertIn(
            "github.event.before == 'd8bcbb5207702baf69b748edd4bafef7950d08ce'",
            auto,
        )
        self.assertIn("actions: write", auto)
        self.assertIn("selector-s4-cost.yml/dispatches", auto)
        self.assertIn("--arg batch_id \"$BATCH_ID\"", auto)

        for text in (cost, shard):
            self.assertIn("actions: write", text)
            self.assertIn("batch_id:", text)
            self.assertIn('test "$BATCH_ID" = "$SOURCE_SHA"', text)

        self.assertIn("selector-s4-shard.yml/dispatches", cost)
        self.assertIn("cost_run_id:", shard)
        self.assertIn("prior_run_ids:", shard)
        self.assertIn('len(ids) != index', shard)
        self.assertIn("selector-s4-shard.yml/dispatches", shard)
        self.assertIn("selector-s4-evaluate.yml/dispatches", shard)
        self.assertIn("len(ids) != 16", shard)

        self.assertIn("batch_id:", evaluate)
        self.assertIn('test "$BATCH_ID" = "$SOURCE_SHA"', evaluate)


if __name__ == "__main__":
    unittest.main()
