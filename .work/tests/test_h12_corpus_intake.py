"""H12-B0 discovery-only intake fail-closed tests, stdlib and no network."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parents[1] / "tools"
MANIFEST = Path(__file__).resolve().parents[1] / "research" / "H12-B0-CANDIDATE-DISCOVERY.json"
spec = importlib.util.spec_from_file_location("h12_corpus_intake", TOOLS / "h12_corpus_intake.py")
intake = importlib.util.module_from_spec(spec)
spec.loader.exec_module(intake)

class DiscoveryIntakeTests(unittest.TestCase):
    def source(self):
        return json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_real_manifest_only_discovery(self):
        verdict = intake.validate_discovery(self.source())
        self.assertFalse(verdict["h12_decision_authorized"])
        self.assertEqual(verdict["candidate_families"], ["brotli", "libdeflate", "lz4"])
        self.assertFalse(verdict["archive_sha256_verified"])
        self.assertFalse(verdict["natural_corpus_frozen"])

    def test_exposed_families_not_fresh(self):
        for family in sorted(intake.EXPOSED_FAMILIES):
            doc = self.source()
            doc["entries"][0]["family"] = family
            with self.assertRaises(intake.IntakeError):
                intake.validate_discovery(doc)

    def test_fake_decision_or_license_status_rejected(self):
        doc = self.source()
        doc["stage"] = "FROZEN"
        with self.assertRaises(intake.IntakeError):
            intake.validate_discovery(doc)
        doc = self.source()
        doc["entries"][0]["candidate_status"] = "READY"
        with self.assertRaises(intake.IntakeError):
            intake.validate_discovery(doc)
        doc = self.source()
        doc["entries"][2]["license_review"] = "APPROVED"
        with self.assertRaises(intake.IntakeError):
            intake.validate_discovery(doc)

    def test_no_hidden_source_lock_or_decision_field(self):
        doc = self.source()
        doc["entries"][0]["archive_sha256"] = "0" * 64
        with self.assertRaises(intake.IntakeError):
            intake.validate_discovery(doc)
        doc = self.source()
        doc["quality_result"] = "PASS"
        with self.assertRaises(intake.IntakeError):
            intake.validate_discovery(doc)

    def test_duplicate_unsorted_and_bad_url(self):
        doc = self.source()
        doc["entries"][1]["family"] = "brotli"
        with self.assertRaises(intake.IntakeError):
            intake.validate_discovery(doc)
        doc = self.source()
        doc["entries"].reverse()
        with self.assertRaises(intake.IntakeError):
            intake.validate_discovery(doc)
        doc = self.source()
        doc["entries"][0]["upstream"] = "https://example.org/not-authoritative"
        with self.assertRaises(intake.IntakeError):
            intake.validate_discovery(doc)

    def test_source_only_cannot_claim_multimodal_coverage(self):
        doc = self.source()
        doc["unmet_modalities"] = []
        with self.assertRaises(intake.IntakeError):
            intake.validate_discovery(doc)
        doc = self.source()
        doc["entries"][0]["modality"] = "application-binary"
        with self.assertRaises(intake.IntakeError):
            intake.validate_discovery(doc)

    def test_duplicate_json_keys_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "duplicate.json"
            p.write_text('{"schema":"a","schema":"b"}', encoding="utf-8")
            with self.assertRaises(intake.IntakeError):
                intake.load_no_duplicate_keys(p)

if __name__ == "__main__":
    unittest.main()
