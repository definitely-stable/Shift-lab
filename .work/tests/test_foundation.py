"""Tests for tools/budget.py and tools/foundation_run.py (DELSK-005 R0 foundation).

Run: python -m unittest discover -s .work/tests -v
The GitHub API is faked in memory; resource-limit tests need Linux and run in
the docs workflow on ubuntu-24.04.
"""

import datetime as dt
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
import unittest
import unittest.mock
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import budget as b  # noqa: E402
import foundation_run as fr  # noqa: E402

REPO = "o/r"
NOW = dt.datetime(2026, 10, 4, 12, 0, tzinfo=dt.timezone.utc)
WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/foundation.yml"


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def job(jid, minutes=None, *, end=NOW - dt.timedelta(hours=1), status="completed", conclusion="success"):
    started = None if minutes is None else end - dt.timedelta(minutes=minutes)
    return {"id": jid, "status": status, "conclusion": conclusion,
            "started_at": iso(started) if started else None,
            "completed_at": iso(end) if status == "completed" and started else None}


class FakeAPI:
    """Serves runs, per-attempt jobs and artifacts with real page/per_page semantics."""

    def __init__(self, page_size=100):
        self.runs, self.jobs, self.artifacts, self.page_size = [], {}, [], page_size

    def add_run(self, rid, number, attempts, created=NOW - dt.timedelta(days=1)):
        self.runs.append({"id": rid, "run_number": number, "run_attempt": len(attempts),
                          "created_at": iso(created)})
        for n, jobs in enumerate(attempts, 1):
            self.jobs[(rid, n)] = jobs

    def __call__(self, path):
        url = urlsplit(path)
        query = parse_qs(url.query)
        page, size = int(query["page"][0]), min(int(query["per_page"][0]), self.page_size)
        if url.path == f"/repos/{REPO}/actions/workflows/foundation.yml/runs":
            key, items = "workflow_runs", self.runs
        elif url.path == f"/repos/{REPO}/actions/workflows/oracle-pilot.yml/runs":
            key, items = "workflow_runs", getattr(self, 'pilot_runs', [])
        elif url.path == f"/repos/{REPO}/actions/artifacts":
            key, items = "artifacts", self.artifacts
        else:
            match = re.fullmatch(rf"/repos/{REPO}/actions/runs/(\d+)/attempts/(\d+)/jobs", url.path)
            key, items = "jobs", self.jobs[(int(match[1]), int(match[2]))]
        return {"total_count": len(items), key: items[(page - 1) * size: page * size]}


class AdmissionTests(unittest.TestCase):
    def test_pagination_attempts_failures_and_cancellations_all_count(self):
        api = FakeAPI(page_size=2)
        api.add_run(10, 1, [[job(1, 5, conclusion="failure"), job(2, 0.2), job(3, 7)],
                            [job(4, 4, conclusion="cancelled")]])
        api.add_run(11, 2, [[job(5, 10)]])
        record = b.account(api, REPO, NOW)
        self.assertEqual(record["used_minutes"], 5 + 1 + 7 + 4 + 10)  # ceil per job
        self.assertEqual([e["minutes"] for e in record["ledger"]], [17, 10])
        self.assertTrue(record["within_budget"])

    def test_budget_boundary_and_modes(self):
        api = FakeAPI()
        api.add_run(10, 1, [[job(1, b.BUDGET_MINUTES - b.RUN_RESERVATION_MINUTES)]])
        api.add_run(99, 2, [[job(2, status="in_progress")]])
        for mode in b.BUDGET_MODES:
            record = b.admit(api, REPO, NOW, mode, current_run_id=99, current_attempt=1)
            self.assertTrue(record["admitted"] and record["within_budget"], mode)
        api.jobs[(10, 1)].append(job(3, 1))
        warned = b.admit(api, REPO, NOW, "warn", current_run_id=99, current_attempt=1)
        self.assertTrue(warned["admitted"])  # telemetry by default: free public runners
        self.assertEqual((warned["used_minutes"], warned["reserved_minutes"]), (571, 30))
        self.assertTrue(any("over budget" in w for w in warned["warnings"]))
        enforced = b.admit(api, REPO, NOW, "enforce", current_run_id=99, current_attempt=1)
        self.assertFalse(enforced["admitted"])
        self.assertIn("enforced", enforced["reason"])

    def test_unknown_mode_refuses(self):
        record = b.admit(FakeAPI(), REPO, NOW, "off")
        self.assertFalse(record["admitted"])
        self.assertIn("unknown budget mode", record["reason"])

    def test_earlier_attempts_of_current_run_count(self):
        api = FakeAPI()
        api.add_run(99, 1, [[job(1, 12, conclusion="failure")], [job(2, status="in_progress")]])
        record = b.account(api, REPO, NOW, current_run_id=99, current_attempt=2)
        self.assertEqual(record["used_minutes"], 12)

    def test_running_job_elsewhere_counts_full_cap(self):
        api = FakeAPI()
        running = job(1, 3)
        running.update(status="in_progress", completed_at=None)
        api.add_run(10, 1, [[running]])
        self.assertEqual(b.account(api, REPO, NOW)["used_minutes"], b.RUN_RESERVATION_MINUTES)

    def test_window_edges(self):
        api = FakeAPI()
        old = NOW - b.WINDOW - dt.timedelta(minutes=1)
        api.add_run(10, 1, [[job(1, 9, end=old), job(2, 9, end=old + dt.timedelta(minutes=2))]],
                    created=old - dt.timedelta(days=20))  # re-run inside the window still counts
        self.assertEqual(b.account(api, REPO, NOW)["used_minutes"], 9)

    def test_missing_durations_are_estimated(self):
        api = FakeAPI()
        api.add_run(10, 1, [[job(1, conclusion="skipped"), job(2, conclusion="cancelled"), job(3, 0)]])
        self.assertEqual(b.account(api, REPO, NOW)["used_minutes"], 1)  # never started = 0; started >= 1
        broken = job(4, 3)
        broken["completed_at"] = None  # completed and started, but no end time
        api.jobs[(10, 1)].append(broken)
        record = b.account(api, REPO, NOW)
        self.assertEqual(record["used_minutes"], 1 + b.RUN_RESERVATION_MINUTES)
        self.assertTrue(any("no valid end time" in w for w in record["warnings"]))

    def test_truncated_or_inconsistent_pages(self):
        api = FakeAPI()
        api.add_run(10, 1, [[job(1, 3)]])
        lying = lambda path: {**api(path), "total_count": 5} if "/jobs" in path else api(path)
        with self.assertRaisesRegex(b.Incomplete, "total_count"):
            b.account(lying, REPO, NOW)
        warned = b.admit(lying, REPO, NOW, "warn")
        self.assertEqual((warned["admitted"], warned["accounting_complete"]), (True, False))
        self.assertFalse(b.admit(lying, REPO, NOW, "enforce")["admitted"])
        repeating = lambda path: api(path.replace("page=2", "page=1"))
        api.page_size = 1
        api.add_run(11, 2, [[job(2, 3)]])
        with self.assertRaisesRegex(b.Incomplete, "duplicate id"):
            b.account(repeating, REPO, NOW)

    def test_deleted_runs_are_estimated_not_blocking(self):
        api = FakeAPI()
        api.add_run(10, 1, [[job(1, 3)]])
        api.add_run(12, 3, [[job(2, 3)]])  # run #2 was deleted: could hide minutes
        record = b.account(api, REPO, NOW)
        self.assertEqual(record["used_minutes"], 3 + 3 + b.RUN_RESERVATION_MINUTES)
        self.assertTrue(any("[2]" in w for w in record["warnings"]))
        self.assertTrue(b.admit(api, REPO, NOW, "enforce")["admitted"])  # within budget, not a deadlock
        api.runs[1]["created_at"] = iso(NOW - b.WINDOW - b.RERUN_HORIZON - dt.timedelta(days=1))
        self.assertEqual(b.account(api, REPO, NOW)["warnings"], [])  # provably older than any re-run
        api.add_run(99, 5, [[job(3, status="in_progress")]])  # run #4 missing below the current run
        record = b.account(api, REPO, NOW, current_run_id=99, current_attempt=1)
        self.assertTrue(any("[4]" in w for w in record["warnings"]))

    def test_api_failure(self):
        def broken(path):
            raise OSError("HTTP 502")
        env = {"GITHUB_REPOSITORY": REPO, "GITHUB_RUN_ID": "1", "GITHUB_RUN_ATTEMPT": "1"}
        with tempfile.TemporaryDirectory() as tmp, unittest.mock.patch.object(b, "github_get", broken):
            out = Path(tmp) / "admission.json"
            for mode, code in (("", 0), ("warn", 0), ("enforce", 1)):
                with unittest.mock.patch.dict(os.environ, {**env, "BUDGET_MODE": mode}):
                    self.assertEqual(b.main(["admit", str(out)]), code, mode)
                record = json.loads(out.read_text(encoding="utf-8"))
                self.assertFalse(record["accounting_complete"])
                self.assertTrue(any("incomplete accounting" in w for w in record["warnings"]))

    def test_artifact_cap_is_hard_in_every_mode(self):
        api = FakeAPI()
        api.artifacts = [{"id": 1, "size_in_bytes": b.ARTIFACT_TOTAL_CAP - b.RUN_ARTIFACT_CAP + 1, "expired": False}]
        for mode in b.BUDGET_MODES:
            record = b.admit(api, REPO, NOW, mode)
            self.assertEqual((record["admitted"], record["reason"]), (False, "artifact storage cap"), mode)

    def test_artifact_storage(self):
        api = FakeAPI()
        api.artifacts = [{"id": 1, "size_in_bytes": b.ARTIFACT_TOTAL_CAP, "expired": True},
                         {"id": 2, "size_in_bytes": 5, "expired": False}]
        self.assertEqual(b.artifact_bytes(api, REPO), 5)


class DispatchTests(unittest.TestCase):
    SHA = "a" * 40
    GOOD = {"GITHUB_EVENT_NAME": "workflow_dispatch", "WORKLOAD": "selftest", "SOURCE_SHA": SHA,
            "GITHUB_SHA": SHA, "GITHUB_WORKFLOW_SHA": SHA, "GITHUB_REPOSITORY": REPO,
            "GITHUB_WORKFLOW_REF": f"{REPO}/.github/workflows/foundation.yml@refs/heads/main",
            "RUNNER_ARCH": "X64"}

    def errors(self, **change):
        return fr.validate_dispatch({**self.GOOD, **change})

    def test_valid(self):
        self.assertEqual(self.errors(), [])

    def test_rejections(self):
        for change, needle in [
            ({"SOURCE_SHA": "A" * 40}, "40-hex"), ({"SOURCE_SHA": "a" * 39}, "40-hex"),
            ({"SOURCE_SHA": f"{'a' * 40}; rm -rf /"}, "40-hex"),
            ({"GITHUB_SHA": "b" * 40, "GITHUB_WORKFLOW_SHA": "b" * 40}, "is not source_sha"),
            ({"GITHUB_WORKFLOW_SHA": "b" * 40}, "workflow file commit"),
            ({"WORKLOAD": "materialize"}, "not allowlisted"), ({"WORKLOAD": None}, "not allowlisted"),
            ({"GITHUB_EVENT_NAME": "push"}, "not workflow_dispatch"),
            ({"GITHUB_WORKFLOW_REF": f"{REPO}/.github/workflows/other.yml@refs/heads/main"}, "workflow ref"),
            ({"RUNNER_ARCH": "ARM64"}, "x64")]:
            with self.subTest(change=change):
                self.assertTrue(any(needle in e for e in self.errors(**change)), self.errors(**change))

    def test_not_admitted_never_runs_workload(self):
        with tempfile.TemporaryDirectory() as tmp, \
                unittest.mock.patch.object(fr, "environment", lambda env: {}), \
                unittest.mock.patch.object(fr, "run_bounded", lambda *a: self.fail("compute ran")):
            admission = Path(tmp) / "admission.json"
            admission.write_text(json.dumps({"admitted": False}), encoding="utf-8")
            self.assertEqual(fr.main([tmp, f"{tmp}/work", str(admission)], self.GOOD), 1)
            self.assertEqual(json.loads((Path(tmp) / "run.json").read_text())["status"], "not_admitted")
            self.assertEqual(fr.main([tmp, f"{tmp}/work", f"{tmp}/missing.json"], self.GOOD), 1)
            record = json.loads((Path(tmp) / "run.json").read_text())
            self.assertEqual((record["status"], record["oracle"]), ("not_admitted", "NOT_RUN"))
            admission.write_text("[true]", encoding="utf-8")
            self.assertEqual(fr.main([tmp, f"{tmp}/work", str(admission)], self.GOOD), 1)
            self.assertEqual(json.loads((Path(tmp) / "run.json").read_text())["status"], "not_admitted")

    def test_workload_evidence_is_copied_next_to_run_record(self):
        def fake_run(argv, work_dir, limits):
            (Path(work_dir) / fr.WORKLOAD_EVIDENCE).mkdir(parents=True)
            (Path(work_dir) / fr.WORKLOAD_EVIDENCE / "report.json").write_text("{}", encoding="utf-8")
            return {"status": "failed"}
        with tempfile.TemporaryDirectory() as tmp, \
                unittest.mock.patch.object(fr, "environment", lambda env: {}), \
                unittest.mock.patch.object(fr, "run_bounded", fake_run):
            admission = Path(tmp) / "admission.json"
            admission.write_text(json.dumps({"admitted": True}), encoding="utf-8")
            env = {**self.GOOD, "WORKLOAD": "materialize-discover"}
            self.assertEqual(fr.main([f"{tmp}/out", f"{tmp}/work", str(admission)], env), 1)
            self.assertTrue((Path(tmp) / "out/workload/report.json").is_file())

    def test_runner_error_still_writes_evidence(self):
        def explode(*args):
            raise RuntimeError("boom")
        with tempfile.TemporaryDirectory() as tmp, \
                unittest.mock.patch.object(fr, "environment", lambda env: {}), \
                unittest.mock.patch.object(fr, "run_bounded", explode):
            admission = Path(tmp) / "admission.json"
            admission.write_text(json.dumps({"admitted": True}), encoding="utf-8")
            self.assertEqual(fr.main([tmp, f"{tmp}/work", str(admission)], self.GOOD), 1)
            record = json.loads((Path(tmp) / "run.json").read_text())
        self.assertEqual((record["status"], record["error"]), ("runner_error", "RuntimeError: boom"))


@unittest.skipUnless(sys.platform.startswith("linux"), "resource limits are enforced on Linux runners")
class LimitTests(unittest.TestCase):
    def run_child(self, code, **limits):
        return self.run_argv([sys.executable, "-c", code], **limits)

    def run_argv(self, argv, **limits):
        with tempfile.TemporaryDirectory() as tmp:
            record = fr.run_bounded(argv, Path(tmp) / "work",
                                    {**fr.LIMITS, "address_space_bytes": 1 << 30, "work_dir_bytes": 8 << 20,
                                     **limits})
        self.assertIn("limits", record)  # evidence is a full record even on failure
        return record

    def test_ok(self):
        record = self.run_child("print('done')")
        self.assertEqual((record["status"], record["exit_code"], record["stdout_tail"]), ("ok", 0, "done\n"))

    def test_time_limit_kills_process_group(self):
        record = self.run_child("import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',"
                                "'import time; time.sleep(60)']); time.sleep(60)", wall_seconds=2)
        self.assertEqual((record["status"], record["signal"]), ("time_limit", 9))
        self.assertLess(record["wall_seconds"], 10)

    def test_memory_limit(self):
        record = self.run_child("x = bytearray(1 << 30)", address_space_bytes=256 << 20)
        self.assertEqual(record["status"], "failed")
        self.assertIn("MemoryError", record["stderr_tail"])

    def test_output_counts_toward_disk_limit(self):
        record = self.run_child("import sys,time; sys.stdout.write('x' * (16 << 20)); sys.stdout.flush(); "
                                "time.sleep(30)")
        self.assertEqual(record["status"], "disk_limit")

    def test_background_process_does_not_outlive_workload(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "late"
            record = self.run_child("import subprocess,sys; subprocess.Popen([sys.executable,'-c',"
                                    f"'import time,pathlib; time.sleep(2); pathlib.Path({json.dumps(str(marker))}).touch()'])")
            self.assertEqual(record["status"], "ok")
            time.sleep(3)
            self.assertFalse(marker.exists())

    def test_disk_limit(self):
        record = self.run_child("import time\nwith open('blob', 'wb') as f:\n f.write(bytes(16 << 20)); f.flush()\n"
                                " time.sleep(30)")
        self.assertEqual(record["status"], "disk_limit")
        self.assertGreater(record["peak_work_dir_bytes"], 8 << 20)

    def test_selftest_is_deterministic(self):
        runs = [self.run_argv(fr.WORKLOADS["selftest"]) for _ in range(2)]
        self.assertEqual([r["status"] for r in runs], ["ok", "ok"])
        self.assertEqual(runs[0]["stdout_tail"], runs[1]["stdout_tail"])
        self.assertIn("selftest_sha256", runs[0]["stdout_tail"])


class WorkflowContractTests(unittest.TestCase):
    """foundation.yml is the enforcement point; check it textually (no YAML parser in stdlib)."""

    text = WORKFLOW.read_text(encoding="utf-8")

    def test_reservation_equals_job_timeout(self):
        self.assertEqual(re.findall(r"timeout-minutes:\s*(\d+)", self.text), [str(b.RUN_RESERVATION_MINUTES)])

    def test_permissions_concurrency_and_pins(self):
        permissions = re.search(r"^permissions:\n((?:  .*\n)+)", self.text, re.M)[1]
        self.assertEqual(sorted(permissions.split()), ["actions:", "contents:", "read", "read"])
        self.assertRegex(self.text, r"concurrency:\n  group: delsk-experimental\n"
                                    r"  cancel-in-progress: false\n  queue: max\n")
        uses = re.findall(r"uses:\s*(\S+)", self.text)
        self.assertTrue(uses)
        for ref in uses:
            self.assertRegex(ref, r"^[\w-]+/[\w-]+@[0-9a-f]{40}$")
        self.assertNotIn("actions/cache", self.text)  # cache disabled in R0
        self.assertNotIn("${{ inputs.", self.text.split("env:", 1)[1].split("steps:", 1)[1])

    def test_workload_choices_match_allowlist(self):
        options = re.search(r"options:\s*\[([^\]]*)\]", self.text)[1]
        self.assertEqual({o.strip() for o in options.split(",")}, set(fr.WORKLOADS))


if __name__ == "__main__":
    unittest.main()
