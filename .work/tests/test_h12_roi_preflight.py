"""H12 descriptive accounting only: adversarial boundary and sealed provenance tests."""
import importlib.util
from decimal import Decimal
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1] / "tools" / "h12_roi_preflight.py"
spec = importlib.util.spec_from_file_location("h12_roi_preflight", PATH)
roi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(roi)

class H12PreflightTests(unittest.TestCase):
    def test_original_archived_immutable_evidence(self):
        x = roi.sealed_evidence()
        self.assertEqual(x["saved_aggregate_physical_csp_bytes"], 1936)
        self.assertEqual(set(x["repeat"]), {"A", "B"})
        for v in x["repeat"].values():
            self.assertGreater(v["extra_create_cpu_seconds"], 0)
            self.assertGreater(v["extra_create_wall_seconds"], 0)

    def test_tampered_original_file_fails_closed(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as d:
            root = Path(d)
            (root / "evaluation").mkdir()
            (root / "A").mkdir()
            (root / "B").mkdir()
            for k in roi.DIGESTS:
                out = root / k
                out.write_bytes((roi.ROOT / k).read_bytes())
            with (root / "A" / "timing.json").open("ab") as f:
                f.write(b" ")
            with self.assertRaisesRegex(ValueError, "digest drift"):
                roi.sealed_evidence(root)

    def test_break_even_strict_inequality(self):
        self.assertEqual(roi.min_deliveries(Decimal("0"), Decimal("2")), 1)
        self.assertEqual(roi.min_deliveries(Decimal("20"), Decimal("2")), 11)
        self.assertEqual(roi.min_deliveries(Decimal("19.99"), Decimal("2")), 10)
        self.assertIsNone(roi.min_deliveries(Decimal("0"), Decimal("0")))
        self.assertIsNone(roi.min_deliveries(Decimal("1"), Decimal("-2")))

    def test_invalid_inputs_fail(self):
        for wrong in ["nan", "Infinity", "-1", "not-a-price"]:
            with self.assertRaises(ValueError):
                roi.nonnegative(wrong)
        with self.assertRaises(ValueError):
            roi.model(roi.sealed_evidence(), "1", "1", "0", "0", "fictional-mode")

    def test_distribution_modes_do_not_amortize_custom_encoder_cost(self):
        x = roi.sealed_evidence()
        shared = roi.model(x, "1", "0.001", "0", "0", "shared-release")
        customized = roi.model(x, "1", "0.001", "0", "0", "customized-per-recipient")
        for role in ["A", "B"]:
            self.assertIsNotNone(shared["repeat_sensitivity"][role]["strictly_positive_roi_first_integer_delivery"])
            self.assertIsNone(customized["repeat_sensitivity"][role]["strictly_positive_roi_first_integer_delivery"])
        self.assertEqual(shared["scope_verdict"], "DESCRIPTIVE_ONLY_NOT_H12_ROI_ACCEPTANCE")

    def test_zero_network_price_does_not_invent_benefit(self):
        x = roi.model(roi.sealed_evidence(), "0", "0", "0", "0", "shared-release")
        self.assertIsNone(x["repeat_sensitivity"]["A"]["strictly_positive_roi_first_integer_delivery"])

if __name__ == "__main__":
    unittest.main()
