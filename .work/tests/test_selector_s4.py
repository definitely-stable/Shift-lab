import json
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

import selector_s4 as s4  # noqa: E402


class Plan(unittest.TestCase):
    def test_preregistered_plan_is_closed(self):
        plan = s4.build_plan()
        self.assertEqual(plan["schema"], s4.PLAN_SCHEMA)
        self.assertEqual(plan["status"], "PREREGISTERED_NOT_RUN")
        self.assertEqual(plan["s3_abstention_level"], 0)
        self.assertEqual(tuple(plan["lanes"]), s4.LANES)
        self.assertEqual(
            plan["consumer"]["commit"],
            "74bb301b6d8ecc52cf0bc0e00d86fa174093d91b",
        )
        # Same natural population retained by S3: 119 targets.
        self.assertEqual(len(plan["targets"]), 119)
        self.assertEqual(
            sum(len(t["lanes"]["exhaustive"]) for t in plan["targets"]),
            3696,
        )
        self.assertEqual(
            119 + sum(len(t["lanes"]["exhaustive"]) for t in plan["targets"]),
            3815,
        )
        self.assertEqual(
            {t["population"] for t in plan["targets"]},
            {
                "pilot-development",
                "pilot-calibration",
                "x0-H1-file",
                "x0-H1-cdc",
                "x0-H4-file",
                "x0-H4-cdc",
            },
        )
        for target in plan["targets"]:
            lanes = target["lanes"]
            exhaustive = lanes["exhaustive"]
            self.assertEqual(len(exhaustive), len(set(exhaustive)))
            self.assertLessEqual(len(lanes["delsk2"]), 2)
            self.assertLessEqual(len(lanes["delsk4"]), 4)
            for lane in ("previous1", "size1", "delsk2", "delsk4"):
                self.assertTrue(set(lanes[lane]).issubset(set(exhaustive)))

    def test_plan_is_deterministic(self):
        self.assertEqual(s4.build_plan(), s4.build_plan())


class Evaluate(unittest.TestCase):
    def synthetic_plan(self):
        bases = [f"{i + 1:064x}" for i in range(15)]
        return {
            "schema": s4.PLAN_SCHEMA,
            "status": "PREREGISTERED_NOT_RUN",
            "consumer": {"commit": "b" * 40},
            "selector": "delsk.simple-selector.v1",
            "s3_abstention_level": 0,
            "lanes": list(s4.LANES),
            "targets": [{
                "population": "p",
                "family_id": "f",
                "track": "file",
                "target_occurrence_id": "t",
                "target_object_id": "a" * 64,
                "target_bytes": 1000,
                "lanes": {
                    "previous1": [bases[0]],
                    "size1": [bases[1]],
                    "delsk2": [bases[2], bases[3]],
                    "delsk4": [bases[2], bases[3], bases[4], bases[5]],
                    "exhaustive": bases,
                },
            }],
        }

    def write_measurements(self, base_bytes, bad=None, extra=False):
        rows = []
        values = {None: 1000, **base_bytes}
        for base, patch_bytes in values.items():
            ok = bad is None or base != bad
            rows.append({
                "schema": s4.MEASUREMENT_SCHEMA,
                "target_occurrence_id": "t",
                "target_object_id": "a" * 64,
                "base_object_id": base,
                "chunkshift_commit": "b" * 40,
                "status": "ok" if ok else "verify_failed",
                "error_class": None if ok else "SHA256_MISMATCH",
                "patch_bytes": patch_bytes,
                "create_wall_ns": 10,
                "create_cpu_ns": 9,
                "apply_wall_ns": 4,
                "apply_cpu_ns": 3,
                "create_exit_code": 0,
                "apply_exit_code": 0,
                "target_manifest_id": "target-manifest",
                "base_manifest_id": None if base is None else f"manifest-{base}",
                "patch_file_digest": "c" * 64,
                "applied_sha256": "a" * 64 if ok else "d" * 64,
            })
        if extra:
            rows.append({
                "schema": s4.MEASUREMENT_SCHEMA,
                "target_occurrence_id": "t",
                "target_object_id": "a" * 64,
                "base_object_id": "e" * 64,
                "chunkshift_commit": "b" * 40,
                "status": "ok",
                "error_class": None,
                "patch_bytes": 1,
                "create_wall_ns": 1,
                "create_cpu_ns": 1,
                "apply_wall_ns": 1,
                "apply_cpu_ns": 1,
                "create_exit_code": 0,
                "apply_exit_code": 0,
                "target_manifest_id": "target-manifest",
                "base_manifest_id": "manifest-extra",
                "patch_file_digest": "c" * 64,
                "applied_sha256": "a" * 64,
            })
        tmp = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False)
        with tmp:
            for row in rows:
                tmp.write(json.dumps(row, sort_keys=True) + "\n")
        self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True))
        return tmp.name

    def complete_bytes(self, **changes):
        bases = [f"{i + 1:064x}" for i in range(15)]
        values = {base: 940 + i for i, base in enumerate(bases)}
        values.update({bases[0]: 900, bases[1]: 920, bases[2]: 862, bases[3]: 870, bases[14]: 860})
        values.update(changes)
        return values

    def test_k2_opens_confirmation_only_when_preregistered_gates_pass(self):
        path = self.write_measurements(self.complete_bytes())
        plan = self.synthetic_plan()
        with unittest.mock.patch.object(s4, "build_plan", return_value=plan):
            result = s4.evaluate(plan, path)
        self.assertEqual(result["verdict"], "OPEN_CONFIRMATION_K2")
        self.assertTrue(result["eligibility"]["delsk2"]["eligible"])
        self.assertEqual(result["best_one_base_control"], "previous1")
        self.assertGreaterEqual(result["aggregate"]["delsk2"]["savings_capture"], 0.98)
        self.assertGreaterEqual(
            result["aggregate"]["exhaustive"]["calls"],
            4 * result["aggregate"]["delsk2"]["calls"],
        )

    def test_no_signal_when_delsk_does_not_beat_the_cheap_control(self):
        bases = [f"{i + 1:064x}" for i in range(15)]
        values = self.complete_bytes(**{bases[2]: 899, bases[3]: 910, bases[14]: 860})
        path = self.write_measurements(values)
        plan = self.synthetic_plan()
        with unittest.mock.patch.object(s4, "build_plan", return_value=plan):
            result = s4.evaluate(plan, path)
        self.assertEqual(result["verdict"], "NO_SYSTEM_SIGNAL")
        self.assertFalse(result["eligibility"]["delsk2"]["eligible"])

    def test_reconstruction_failure_is_invalid(self):
        bases = [f"{i + 1:064x}" for i in range(15)]
        path = self.write_measurements(self.complete_bytes(), bad=bases[2])
        plan = self.synthetic_plan()
        with unittest.mock.patch.object(s4, "build_plan", return_value=plan):
            self.assertEqual(s4.evaluate(plan, path)["verdict"], "INVALID")

    def test_missing_or_extra_measurement_fails_closed(self):
        values = self.complete_bytes()
        values.pop(f"{15:064x}")
        plan = self.synthetic_plan()
        with unittest.mock.patch.object(s4, "build_plan", return_value=plan):
            with self.assertRaises(s4.S4Error):
                s4.evaluate(plan, self.write_measurements(values))
            with self.assertRaises(s4.S4Error):
                s4.evaluate(
                    plan,
                    self.write_measurements(self.complete_bytes(), extra=True),
                )

    def test_modified_plan_is_rejected(self):
        plan = self.synthetic_plan()
        path = self.write_measurements(self.complete_bytes())
        frozen = json.loads(json.dumps(plan))
        frozen["targets"][0]["lanes"]["delsk2"] = [f"{15:064x}", f"{14:064x}"]
        with unittest.mock.patch.object(s4, "build_plan", return_value=frozen):
            with self.assertRaises(s4.S4Error):
                s4.evaluate(plan, path)


    def test_unknown_measurement_field_is_rejected(self):
        plan = self.synthetic_plan()
        path = self.write_measurements(self.complete_bytes())
        rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()]
        rows[0]["surprise"] = True
        bad = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False)
        with bad:
            for row in rows:
                bad.write(json.dumps(row, sort_keys=True) + "\n")
        self.addCleanup(lambda: Path(bad.name).unlink(missing_ok=True))
        with unittest.mock.patch.object(s4, "build_plan", return_value=plan):
            with self.assertRaises(s4.S4Error):
                s4.evaluate(plan, bad.name)

    def test_measurement_must_bind_target_and_consumer(self):
        plan = self.synthetic_plan()
        path = self.write_measurements(self.complete_bytes())
        rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()]
        rows[0]["chunkshift_commit"] = "f" * 40
        bad = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False)
        with bad:
            for row in rows:
                bad.write(json.dumps(row, sort_keys=True) + "\n")
        self.addCleanup(lambda: Path(bad.name).unlink(missing_ok=True))
        with unittest.mock.patch.object(s4, "build_plan", return_value=plan):
            with self.assertRaises(s4.S4Error):
                s4.evaluate(plan, bad.name)


if __name__ == "__main__":
    unittest.main()
