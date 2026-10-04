"""Tests for tools/recompute_foundation.py (Slice F): handoff recomputation, bundle verification, R0 gate.

Offline and payload-free. Bundles are synthetic: run.json is built here, handoff.json comes from the tool.
"""

import copy
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unittest
import unittest.mock

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / ".work"
sys.path.insert(0, str(WORK / "tools"))
import foundation_run as fr  # noqa: E402
import manifests as m  # noqa: E402
import recompute_foundation as rf  # noqa: E402

SHA = "a" * 40


def run_record(run_id, attempt, **override):
    g = {"GITHUB_RUN_ID": str(run_id), "GITHUB_RUN_ATTEMPT": str(attempt), "GITHUB_SHA": SHA,
         "GITHUB_WORKFLOW_SHA": SHA, "RUNNER_ARCH": "X64"}
    run = {"schema": "delsk.ci.foundation-run.v1", "evidence_scope": "foundation", "oracle": "NOT_RUN",
           "quality_verdict": "N/A", "workload": rf.WORKLOAD, "source_sha": SHA, "status": "ok", "exit_code": 0,
           "admission": {"admitted": True}, "environment": {"github": g}}
    return {**run, **override}


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = rf.handoff_doc()
        cls.patch = unittest.mock.patch.object(rf, "handoff_doc", lambda: copy.deepcopy(cls.doc))
        cls.patch.start()

    @classmethod
    def tearDownClass(cls):
        cls.patch.stop()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "results"
        self.root.mkdir()
        self.scratch = Path(self.tmp.name) / "scratch"
        self.addCleanup(self.tmp.cleanup)

    def bundle(self, run_id=1, attempt=1, doc=None, run=None, seal=True):
        d = self.root / f"{run_id}-{attempt}"
        (d / "workload").mkdir(parents=True)
        (d / "run.json").write_text(json.dumps(run or run_record(run_id, attempt)))
        (d / "workload" / "handoff.json").write_bytes(m.canonical_bytes(doc or self.doc))
        rf.handoff(self.scratch)
        (d / "workload" / "timings.jsonl").write_bytes((self.scratch / "timings.jsonl").read_bytes())
        if seal:
            (d / "checksums.sha256").write_text(rf.checksums(d))
        return d


class HandoffTests(Base):
    def test_accounting_matches_the_sealed_pilot(self):
        a = self.doc["accounting"]
        self.assertEqual((a["content"]["occurrences"], a["content"]["content_classes"], a["content"]["cross_split_classes"]),
                         (32391, 28477, 0))
        self.assertEqual((a["candidates"]["queries"], a["candidates"]["near_queries"], a["candidates"]["planned_pairs_per_codec"]),
                         (79, 64, 1961))
        self.assertEqual({c["split"] for c in a["lineage"]["components"]}, set(m.SPLITS))
        self.assertEqual((self.doc["oracle"], self.doc["quality_verdict"]), ("NOT_RUN", "N/A"))

    def test_recomputation_reads_only_committed_records(self):
        seen = []
        real = Path.read_bytes
        with unittest.mock.patch.object(Path, "read_bytes", lambda p: seen.append(p) or real(p)):
            rf.account()
        self.assertTrue(seen)
        self.assertTrue(all(WORK in p.parents and WORK / "tmp" not in p.parents for p in seen), [str(p) for p in seen])

    def test_unpinned_lock_is_refused(self):
        real = Path.read_bytes
        lock = (WORK / "corpus" / "e1" / "candidate-lock.json").resolve()
        with unittest.mock.patch.object(Path, "read_bytes", lambda p: real(p) + b" " if p.resolve() == lock else real(p)):
            with self.assertRaisesRegex(rf.FoundationError, "differs from its pinned"):
                rf.account()

    def tampered(self, path, edit=None):
        """Path.read_bytes patch: `edit` rewrites the canonical JSON document at `path`; no edit = file is gone."""
        real, target = Path.read_bytes, path.resolve()

        def read(p):
            if p.resolve() != target:
                return real(p)
            if edit is None:
                raise FileNotFoundError(p)
            doc = m.loads_strict(real(p))
            edit(doc)
            return m.canonical_bytes(doc)
        return unittest.mock.patch.object(Path, "read_bytes", read)

    def test_root_records_are_part_of_the_identity(self):
        edits = {WORK / "corpus" / "e0" / "freeze.json": lambda d: d.update(adopted_on="2026-10-05"),
                 WORK / "corpus" / "e1" / "seal.json": lambda d: d.update(sealed_on="2026-10-05")}
        for path, edit in edits.items():
            with self.subTest(path.name), self.tampered(path, edit):
                changed = rf.freeze_graph()[0]
                self.assertNotEqual(changed[rf.rel(path)], self.doc["locks"][rf.rel(path)])

    def test_pinned_members_of_the_chain_are_checked(self):
        pilot = WORK / "corpus" / "pilot-v1" / "freeze.json"
        with self.tampered(pilot, lambda d: d["license_review"][0].update(finding="changed")):
            with self.assertRaisesRegex(rf.FoundationError, "freeze.json: two records pin different"):
                rf.account()
        with self.tampered(WORK / "corpus" / "e0" / "construction-spec.md"):
            with self.assertRaises(OSError):
                rf.account()
        with self.tampered(WORK / "corpus" / "e0" / "freeze.json", lambda d: d.update(status="DRAFT")):
            with self.assertRaisesRegex(rf.FoundationError, "freeze chain"):
                rf.account()

    def test_chain_locks_cover_every_record(self):
        for path in ("corpus/pilot-v1/freeze.json", "corpus/e0/freeze.json", "corpus/e1/seal.json", "protocol.md",
                     "corpus/source-plan.json", "corpus/selection-policy.json", "corpus/e0/construction-spec.md",
                     "corpus/e0/ancestry-audit.json", "corpus/e0/historical-bytes.json"):
            self.assertIn(f".work/{path}", self.doc["locks"])

    def test_workload_output_is_deterministic_except_timings(self):
        a, b = self.scratch / "a", self.scratch / "b"
        rf.handoff(a)
        rf.handoff(b)
        self.assertEqual((a / "handoff.json").read_bytes(), (b / "handoff.json").read_bytes())
        rf.check_timings((a / "timings.jsonl").read_text())
        rows = [json.loads(line) for line in (a / "timings.jsonl").read_text().splitlines()]
        self.assertEqual((len(rows), sum(r["warmup"] for r in rows)), (14, 4))  # 2 warmups + 5 blocks, two arms each

    def test_workload_is_allowlisted_everywhere(self):
        self.assertIn("foundation-handoff", fr.WORKLOADS)
        workflow = (ROOT / ".github" / "workflows" / "foundation.yml").read_text()
        options = re.search(r"options: \[(.*?)\]", workflow).group(1).replace(" ", "").split(",")
        self.assertEqual(set(options), set(fr.WORKLOADS))


class VerifyTests(Base):
    def test_good_bundle_verifies(self):
        self.assertEqual(rf.verify(self.bundle()), [])

    def assertRejected(self, directory, text):
        errors = rf.verify(directory)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn(text, errors[0])

    def test_tampered_file(self):
        d = self.bundle()
        (d / "workload" / "timings.jsonl").write_text("{}\n")
        self.assertRejected(d, "checksums differ")

    def test_truncated_bundle(self):
        d = self.bundle()
        path = d / "workload" / "handoff.json"
        path.write_bytes(path.read_bytes()[:-100])
        self.assertRejected(d, "checksums differ")

    def test_missing_record(self):
        d = self.bundle()
        (d / "workload" / "timings.jsonl").unlink()
        self.assertRejected(d, "missing ['workload/timings.jsonl']")

    def test_unexpected_file(self):
        d = self.bundle()
        (d / "extra.txt").write_text("x")
        self.assertRejected(d, "unexpected ['extra.txt']")

    def test_mismatched_lock(self):
        doc = copy.deepcopy(self.doc)
        doc["locks"][next(iter(doc["locks"]))] = "0" * 64
        self.assertRejected(self.bundle(doc=doc), "locks differs from recomputation")

    def test_changed_accounting(self):
        doc = copy.deepcopy(self.doc)
        doc["accounting"]["candidates"]["planned_pairs_per_codec"] += 1
        self.assertRejected(self.bundle(doc=doc), "accounting differs from recomputation")

    def test_tampered_tool_digest(self):
        for tool in rf.CODE:
            with self.subTest(tool):
                doc = copy.deepcopy(self.doc)
                doc["tools"][tool] = "0" * 64
                d = self.bundle(doc=doc)  # checksums are consistent: only the recomputation can catch it
                self.assertRejected(d, "tools differs from recomputation")
                shutil.rmtree(d)

    def test_timing_order_is_proved(self):
        good = [json.loads(line) for line in (self.bundle() / "workload" / "timings.jsonl").read_text().splitlines()]
        mutations = {"position": lambda r: r[3].update(position=99),
                     "order not alternating": lambda r: (r[2].update(arm="A1"), r[3].update(arm="A2")),
                     "warmup flag": lambda r: r[0].update(warmup=False),
                     "swapped rows": lambda r: r.insert(0, r.pop(1)),
                     "extra key": lambda r: r[0].update(x=1)}
        for name, mutate in mutations.items():
            rows = copy.deepcopy(good)
            mutate(rows)
            with self.subTest(name), self.assertRaises(rf.FoundationError):
                rf.check_timings("".join(json.dumps(r) + chr(10) for r in rows))

    def test_unexpected_schema(self):
        doc = {**self.doc, "oracle_rows": []}
        self.assertRejected(self.bundle(doc=doc), "unexpected schema")

    def test_cancelled_or_failed_attempt(self):
        for status, code in (("failed", 1), ("time_limit", None), ("not_admitted", None)):
            with self.subTest(status):
                d = self.root / f"1-{status}"
                self.bundle(run=run_record(1, 1, status=status, exit_code=code)).rename(d)
                (d / "checksums.sha256").write_text(rf.checksums(d))
                self.assertRejected(d, "failed or cancelled attempt")

    def test_dispatch_identities(self):
        for name, run in {"sha": run_record(1, 1, source_sha="b" * 40),
                          "scope": run_record(1, 1, oracle="RUN"),
                          "arm": {**run_record(1, 1), "environment": {"github": {**run_record(1, 1)["environment"]["github"], "RUNNER_ARCH": "ARM64"}}},
                          "workload": run_record(1, 1, workload="selftest")}.items():
            with self.subTest(name):
                d = self.bundle(run=run)
                self.assertNotEqual(rf.verify(d), [])
                shutil.rmtree(d)

    def test_directory_must_name_run_and_attempt(self):
        d = self.bundle(run_id=1, attempt=1)
        e = d.rename(self.root / "2-1")
        self.assertRejected(e, "directory name differs")


class BundleTests(Base):
    def test_bundle_retains_an_artifact_and_refuses_a_bad_one(self):
        artifact = self.bundle(7, 1, seal=False)
        for name in ("workload/handoff.json", "workload/timings.jsonl", "run.json"):
            (self.scratch / "artifact" / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(artifact / name, self.scratch / "artifact" / name)
        results = self.scratch / "retained"
        with unittest.mock.patch.object(rf, "RESULTS", results):
            dest = rf.bundle(self.scratch / "artifact")
            self.assertEqual((dest.name, rf.verify(dest)), ("7-1", []))
            with self.assertRaisesRegex(rf.FoundationError, "already retained"):
                rf.bundle(self.scratch / "artifact")
            (self.scratch / "artifact" / "run.json").write_text(json.dumps(run_record(8, 1, status="cancelled", exit_code=None)))
            with self.assertRaisesRegex(rf.FoundationError, "failed or cancelled"):
                rf.bundle(self.scratch / "artifact")
            self.assertFalse((results / "8-1").exists())

    def test_failed_import_leaves_nothing_and_can_be_repeated(self):
        artifact = self.bundle(9, 1, seal=False)
        staged = self.scratch / "artifact"
        for name in ("run.json", "workload/handoff.json"):
            (staged / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(artifact / name, staged / name)  # timings.jsonl is missing
        results = self.scratch / "retained"
        with unittest.mock.patch.object(rf, "RESULTS", results):
            with self.assertRaises(OSError):
                rf.bundle(staged)
            self.assertEqual(list(results.iterdir()), [])
            shutil.copyfile(artifact / "workload" / "timings.jsonl", staged / "workload" / "timings.jsonl")
            self.assertEqual(rf.verify(rf.bundle(staged)), [])


class GateTests(Base):
    def gate(self):
        return rf.readiness(self.root)

    def test_no_bundles_is_not_ready(self):
        r = self.gate()
        self.assertFalse(r["ready"])
        self.assertIn("have 0 bundle", r["blockers"][0])

    def test_one_bundle_is_not_ready(self):
        self.bundle(1, 1)
        self.assertFalse(self.gate()["ready"])

    def test_two_attempts_of_one_run_are_not_independent(self):
        self.bundle(1, 1)
        self.bundle(1, 2)
        self.assertFalse(self.gate()["ready"])

    def test_two_distinct_runs_are_ready(self):
        self.bundle(1, 1)
        self.bundle(2, 1)
        r = self.gate()
        self.assertEqual((r["ready"], r["blockers"], r["bundles"]), (True, [], ["1-1", "2-1"]))

    def test_different_handoff_does_not_confirm(self):
        other = copy.deepcopy(self.doc)
        other["tools"]["manifests.py"] = "0" * 64
        self.bundle(1, 1)
        self.bundle(2, 1, doc=other)
        self.assertFalse(self.gate()["ready"])

    def test_invalid_bundle_blocks_even_with_two_good_ones(self):
        self.bundle(1, 1)
        self.bundle(2, 1)
        (self.bundle(3, 1) / "run.json").write_text("{}")
        r = self.gate()
        self.assertFalse(r["ready"])
        self.assertTrue(any(b.startswith("3-1") for b in r["blockers"]))


class CommittedStateTests(unittest.TestCase):
    def test_committed_bundles_verify(self):
        self.assertEqual([e for d in sorted(rf.RESULTS.glob("*")) for e in rf.verify(d)], [])

    def test_readiness_record_states_the_computed_gate(self):
        verdict = "READY" if rf.readiness()["ready"] else "NOT READY"
        record = (WORK / "research" / "R0-readiness.md").read_text(encoding="utf-8")
        self.assertIn(f"**Gate: {verdict}**", record)


if __name__ == "__main__":
    unittest.main()
