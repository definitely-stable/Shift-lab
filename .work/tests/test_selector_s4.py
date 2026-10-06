import json
import sys
import tempfile
import unittest
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
        bases = [f"b{i:02d}" for i in range(15)]
        return {
            "schema": s4.PLAN_SCHEMA,
            "status": "PREREGISTERED_NOT_RUN",
            "consumer": {"commit": "x"},
            "selector": "delsk.simple-selector.v1",
            "s3_abstention_level": 0,
            "lanes": list(s4.LANES),
            "targets": [{
                "population": "p",
                "family_id": "f",
                "track": "file",
                "target_occurrence_id": "t",
                "target_object_id": "target",
                "target_bytes": 1000,
                "lanes": {
                    "previous1": ["b00"],
                    "size1": ["b01"],
                    "delsk2": ["b02", "b03"],
                    "delsk4": ["b02", "b03", "b04", "b05"],
                    "exhaustive": bases,
                },
            }],
        }

    def write_measurements(self, base_bytes, bad=None, extra=False):
        rows = []
        values = {None: 1000, **base_bytes}
        for base, patch_bytes in values.items():
            rows.append({
                "schema": s4.MEASUREMENT_SCHEMA,
                "target_occurrence_id": "t",
                "base_object_id": base,
                "patch_bytes": patch_bytes,
                "create_wall_ns": 10,
                "create_cpu_ns": 9,
                "apply_wall_ns": 4,
                "apply_cpu_ns": 3,
                "reconstruction_ok": base != bad,
            })
        if extra:
            rows.append({
                "schema": s4.MEASUREMENT_SCHEMA,
                "target_occurrence_id": "t",
                "base_object_id": "not-in-plan",
                "patch_bytes": 1,
                "create_wall_ns": 1,
                "create_cpu_ns": 1,
                "apply_wall_ns": 1,
                "apply_cpu_ns": 1,
                "reconstruction_ok": True,
            })
        tmp = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False)
        with tmp:
            for row in rows:
                tmp.write(json.dumps(row, sort_keys=True) + "\n")
        self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True))
        return tmp.name

    def complete_bytes(self, **changes):
        values = {f"b{i:02d}": 940 + i for i in range(15)}
        values.update({"b00": 900, "b01": 920, "b02": 862, "b03": 870, "b14": 860})
        values.update(changes)
        return values

    def test_k2_opens_confirmation_only_when_preregistered_gates_pass(self):
        path = self.write_measurements(self.complete_bytes())
        result = s4.evaluate(self.synthetic_plan(), path)
        self.assertEqual(result["verdict"], "OPEN_CONFIRMATION_K2")
        self.assertTrue(result["eligibility"]["delsk2"]["eligible"])
        self.assertEqual(result["best_one_base_control"], "previous1")
        self.assertGreaterEqual(result["aggregate"]["delsk2"]["savings_capture"], 0.98)
        self.assertGreaterEqual(
            result["aggregate"]["exhaustive"]["calls"],
            4 * result["aggregate"]["delsk2"]["calls"],
        )

    def test_no_signal_when_delsk_does_not_beat_the_cheap_control(self):
        values = self.complete_bytes(b02=899, b03=910, b14=860)
        path = self.write_measurements(values)
        result = s4.evaluate(self.synthetic_plan(), path)
        self.assertEqual(result["verdict"], "NO_SYSTEM_SIGNAL")
        self.assertFalse(result["eligibility"]["delsk2"]["eligible"])

    def test_reconstruction_failure_is_invalid(self):
        path = self.write_measurements(self.complete_bytes(), bad="b02")
        self.assertEqual(s4.evaluate(self.synthetic_plan(), path)["verdict"], "INVALID")

    def test_missing_or_extra_measurement_fails_closed(self):
        values = self.complete_bytes()
        values.pop("b14")
        with self.assertRaises(s4.S4Error):
            s4.evaluate(self.synthetic_plan(), self.write_measurements(values))
        with self.assertRaises(s4.S4Error):
            s4.evaluate(
                self.synthetic_plan(),
                self.write_measurements(self.complete_bytes(), extra=True),
            )


if __name__ == "__main__":
    unittest.main()
