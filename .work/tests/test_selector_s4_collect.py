import json
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

import selector_s4_collect as collect  # noqa: E402


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


class Collector(unittest.TestCase):
    def build_fixture(self, root, *, rerun_index=None, duplicate_index=None):
        root = Path(root)
        plan = {
            "schema": "delsk.chunkshift-s4.plan.v1",
            "consumer": {"commit": collect.CONSUMER_SHA},
            "targets": [
                {
                    "target_occurrence_id": f"t{i:02d}",
                    "lanes": {"exhaustive": []},
                }
                for i in range(collect.SHARD_COUNT)
            ],
        }
        plan_path = root / "plan.json"
        plan_path.write_bytes(canonical(plan))
        plan_sha = collect.file_sha256(plan_path)
        artifacts = []
        shards = root / "shards"
        shards.mkdir()
        implementation = "a" * 40

        for i in range(collect.SHARD_COUNT):
            actual_index = duplicate_index if i == collect.SHARD_COUNT - 1 and duplicate_index is not None else i
            run_id = 1000 + i
            directory = shards / f"run-{run_id}"
            directory.mkdir()
            row = {"target_occurrence_id": f"t{i:02d}", "base_object_id": None, "status": "ok"}
            measurements = directory / "measurements.jsonl"
            measurements.write_bytes(canonical(row))
            manifests = directory / "manifests.jsonl"
            manifests.write_bytes(canonical({"object_id": f"{i:064x}"}))
            attempt = 2 if i == rerun_index else 1
            shard = {
                "schema": collect.SHARD_SCHEMA,
                "protocol_authority": collect.PROTOCOL_SHA,
                "implementation_sha": implementation,
                "chunkshift_commit": collect.CONSUMER_SHA,
                "shard_index": actual_index,
                "shard_count": collect.SHARD_COUNT,
                "plan_sha256": plan_sha,
                "targets": 1,
                "target_occurrence_ids": [f"t{actual_index:02d}"],
                "expected_rows": 1,
                "actual_rows": 1,
                "ok_rows": 1,
                "failed_rows": 0,
                "measurement_sha256": collect.file_sha256(measurements),
                "manifest_sha256": collect.file_sha256(manifests),
                "chunkshift_cli_sha256": "c" * 64,
                "dotnet_version": "10.0.204",
            }
            (directory / "shard.json").write_bytes(canonical(shard))
            run = {
                "schema": collect.RUN_SCHEMA,
                "protocol_authority": collect.PROTOCOL_SHA,
                "chunkshift_commit": collect.CONSUMER_SHA,
                "shard_index": actual_index,
                "shard_count": collect.SHARD_COUNT,
                "github_sha": implementation,
                "github_workflow_sha": implementation,
                "github_ref": "refs/heads/main",
                "github_run_attempt": str(attempt),
                "github_run_id": str(run_id),
            }
            (directory / "run.json").write_bytes(canonical(run))
            (directory / "admission.json").write_bytes(canonical({
                "schema": "delsk.ci.admission.v1",
                "admitted": True,
            }))
            artifacts.append({
                "run_id": run_id,
                "run_attempt": attempt,
                "head_sha": implementation,
                "workflow_path": ".github/workflows/selector-s4-shard.yml",
                "artifact_id": 2000 + i,
                "artifact_name": f"delsk-s4-shard-{actual_index}-of-16-{run_id}-{attempt}",
                "artifact_digest": "sha256:" + f"{i + 1:064x}",
                "artifact_size": 100 + i,
            })

        artifact_path = root / "artifacts.jsonl"
        with artifact_path.open("wb") as stream:
            for row in artifacts:
                stream.write(canonical(row))
        return plan_path, artifact_path, shards

    def test_exact_sixteen_shards_merge(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan, artifacts, shards = self.build_fixture(root)
            out = root / "out"
            self.assertEqual(collect.merge(plan, artifacts, shards, out), 0)
            record = json.loads((out / "collection.json").read_text())
            self.assertEqual(record["rows"], 16)
            self.assertEqual(record["failed_rows"], 0)
            self.assertEqual([s["shard_index"] for s in record["shards"]], list(range(16)))
            self.assertEqual(len((out / "measurements.jsonl").read_text().splitlines()), 16)



    def test_toolchain_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan, artifacts, shards = self.build_fixture(root)
            second = sorted(shards.iterdir())[1] / "shard.json"
            shard = json.loads(second.read_text(encoding="utf-8"))
            shard["chunkshift_cli_sha256"] = "d" * 64
            second.write_bytes(canonical(shard))
            with self.assertRaises(collect.CollectError):
                collect.merge(plan, artifacts, shards, root / "out")

    def test_workflow_sha_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan, artifacts, shards = self.build_fixture(root)
            first = sorted(shards.iterdir())[0] / "run.json"
            run = json.loads(first.read_text(encoding="utf-8"))
            run["github_workflow_sha"] = "b" * 40
            first.write_bytes(canonical(run))
            with self.assertRaises(collect.CollectError):
                collect.merge(plan, artifacts, shards, root / "out")

    def test_rerun_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan, artifacts, shards = self.build_fixture(root, rerun_index=3)
            with self.assertRaises(collect.CollectError):
                collect.merge(plan, artifacts, shards, root / "out")

    def test_duplicate_shard_index_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan, artifacts, shards = self.build_fixture(root, duplicate_index=0)
            with self.assertRaises(collect.CollectError):
                collect.merge(plan, artifacts, shards, root / "out")


if __name__ == "__main__":
    unittest.main()
