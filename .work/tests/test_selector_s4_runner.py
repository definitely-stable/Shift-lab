import importlib.util
import json
import sys
import tempfile
import unittest
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

    def test_plan_rejects_wrong_consumer(self):
        plan = protocol.build_plan()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plan.json"
            bad = json.loads(json.dumps(plan))
            bad["consumer"]["commit"] = "0" * 40
            path.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaises(runner.RunnerError):
                runner.load_plan(path)


if __name__ == "__main__":
    unittest.main()
