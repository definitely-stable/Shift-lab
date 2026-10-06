"""DELSK-005 experimental compute admission (R0 foundation).

Stdlib only. Standard hosted runners are free for this public repository, so
the 600 runner-minute rolling 7x24h UTC budget is project policy, not a GitHub
quota. Before compute the job records a ledger of every runner minute the
experimental workflows used in the window — all runs, all attempts, failed and
cancelled jobs included — plus the full cap of the current run.

Budget mode comes from env BUDGET_MODE (repository variable DELSK_BUDGET_MODE):
- `warn` (default): the ledger is telemetry; over-budget or incomplete
  accounting only adds warnings, compute proceeds.
- `enforce`: emergency guardrail; compute is refused when over budget or when
  the API account is incomplete.
Gaps in run history (deleted runs) and jobs without an end time never block:
each is counted as a full run cap, a conservative estimate, with a warning.

Artifact storage is a hard cap in every mode: checked before compute (per-run
reservation) and before upload (actual size). Nothing is deleted to make room.

    python3 budget.py admit OUT.json          # exit 0 admitted, 1 refused
    python3 budget.py artifact-check DIR      # exit 0 fits, 1 over cap

Contract prose: .work/ci-plan.md.
"""

import datetime as dt
import json
import math
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

BUDGET_MINUTES = 600
BUDGET_MODES = ("warn", "enforce")
WINDOW = dt.timedelta(days=7)
# GitHub allows re-running a run up to 30 days after it was created, so a run
# created earlier than window + 30 days cannot have jobs inside the window
# (one extra day covers a re-run started on day 30 that finishes later).
RERUN_HORIZON = dt.timedelta(days=31)
EXPERIMENTAL_WORKFLOWS = ("foundation.yml", "oracle-pilot.yml", "delsk-baselines.yml", "delsk-screening.yml",
                          "selector-bench.yml", "selector-s3.yml")
# Full cap of one experimental run: the single job's timeout-minutes in
# foundation.yml (test_foundation checks they match).
RUN_RESERVATION_MINUTES = 30
ARTIFACT_TOTAL_CAP = 256 << 20
RUN_ARTIFACT_CAP = 16 << 20
MAX_PAGES = 50


class Incomplete(Exception):
    """The API did not give a complete, consistent list."""


def ts(value):
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def paged(get, path, key):
    """All items of a paginated list endpoint; total_count must match exactly."""
    items, seen, total = [], set(), None
    for page in range(1, MAX_PAGES + 1):
        sep = "&" if "?" in path else "?"
        body = get(f"{path}{sep}per_page=100&page={page}")
        if total is None:
            total = body["total_count"]
        elif body["total_count"] != total:
            raise Incomplete(f"{path}: total_count changed during pagination")
        batch = body[key]
        for item in batch:
            if item["id"] in seen:
                raise Incomplete(f"{path}: duplicate id {item['id']} across pages")
            seen.add(item["id"])
            items.append(item)
        if len(items) >= total or not batch:
            break
    if len(items) != total:
        raise Incomplete(f"{path}: got {len(items)} of total_count {total}")
    return items


def job_minutes(job, window_start, warnings):
    """Billing-style minutes of a completed job: ceil, at least 1 once started; 0 if it ended before the window."""
    started, completed = job.get("started_at"), job.get("completed_at")
    if not started:
        return 0  # never got a runner (skipped, cancelled while queued, startup failure)
    if not completed or ts(completed) < ts(started):
        warnings.append(f"job {job['id']}: no valid end time, counted as a full run cap")
        return RUN_RESERVATION_MINUTES
    if ts(completed) < window_start:
        return 0
    return max(1, math.ceil((ts(completed) - ts(started)).total_seconds() / 60))


def missing_runs(runs, current_number, horizon_start):
    """run_numbers absent from the history that may hold in-window minutes (deleted runs)."""
    by_number = {run["run_number"]: run for run in runs}
    top = max([current_number or 0, *by_number])
    missing = []
    for number in range(1, top + 1):
        if number in by_number or number == current_number:
            continue
        later = [ts(r["created_at"]) for n, r in by_number.items() if n > number]
        if not later or min(later) >= horizon_start:
            missing.append(number)
    return missing


def account(get, repo, now, current_run_id=None, current_attempt=None):
    """Ledger of experimental minutes in the window ending at `now`; raises Incomplete on bad lists."""
    window_start = now - WINDOW
    horizon_start = window_start - RERUN_HORIZON
    ledger, used, warnings = [], 0, []
    for workflow in EXPERIMENTAL_WORKFLOWS:
        runs = paged(get, f"/repos/{repo}/actions/workflows/{workflow}/runs", "workflow_runs")
        current_number = next((r["run_number"] for r in runs if r["id"] == current_run_id), None)
        missing = missing_runs(runs, current_number, horizon_start)
        if missing:
            warnings.append(f"{workflow}: runs {missing} missing from history, each counted as a full run cap")
            used += RUN_RESERVATION_MINUTES * len(missing)
        for run in sorted(runs, key=lambda r: r["run_number"]):
            if ts(run["created_at"]) < horizon_start:
                continue
            minutes = 0
            for attempt in range(1, run["run_attempt"] + 1):
                if run["id"] == current_run_id and attempt == current_attempt:
                    continue  # reserved in full below
                jobs = paged(get, f"/repos/{repo}/actions/runs/{run['id']}/attempts/{attempt}/jobs", "jobs")
                for job in jobs:
                    if job["status"] == "completed":
                        minutes += job_minutes(job, window_start, warnings)
                    elif job.get("started_at"):
                        minutes += RUN_RESERVATION_MINUTES  # running elsewhere: assume full cap
            if minutes:
                ledger.append({"workflow": workflow, "run_id": run["id"], "run_number": run["run_number"],
                               "attempts": run["run_attempt"], "minutes": minutes})
            used += minutes
    reserved = RUN_RESERVATION_MINUTES if current_run_id is not None else 0
    return {
        "schema": "delsk.ci.admission.v1",
        "window_start": window_start.isoformat(), "window_end": now.isoformat(),
        "budget_minutes": BUDGET_MINUTES, "used_minutes": used, "reserved_minutes": reserved,
        "within_budget": used + reserved <= BUDGET_MINUTES, "accounting_complete": True,
        "warnings": warnings, "ledger": ledger,
    }


def admit(get, repo, now, mode, current_run_id=None, current_attempt=None):
    """Admission record: budget per `mode`, artifact storage always hard."""
    if mode not in BUDGET_MODES:
        return {"schema": "delsk.ci.admission.v1", "admitted": False,
                "reason": f"unknown budget mode {mode!r}; expected one of {BUDGET_MODES}"}
    try:
        record = account(get, repo, now, current_run_id, current_attempt)
    except Exception as error:  # telemetry failure; blocks only in enforce mode
        record = {"schema": "delsk.ci.admission.v1", "budget_minutes": BUDGET_MINUTES,
                  "within_budget": None, "accounting_complete": False,
                  "warnings": [f"incomplete accounting: {type(error).__name__}: {error}"]}
    record.update(budget_mode=mode, admitted=True)
    if record["within_budget"] is False:
        record["warnings"].append(f"over budget: {record['used_minutes']} used + "
                                  f"{record['reserved_minutes']} reserved > {BUDGET_MINUTES}")
    if mode == "enforce" and record["within_budget"] is not True:
        record.update(admitted=False, reason="enforced runner-minute budget: over budget or incomplete accounting")
    try:
        stored = artifact_bytes(get, repo)
    except Exception as error:  # the pre-upload check stays hard; here only telemetry
        record["warnings"].append(f"artifact storage unknown before compute: {type(error).__name__}: {error}")
    else:
        record.update(artifact_bytes=stored, artifact_total_cap=ARTIFACT_TOTAL_CAP,
                      run_artifact_cap=RUN_ARTIFACT_CAP)
        if stored + RUN_ARTIFACT_CAP > ARTIFACT_TOTAL_CAP:
            record.update(admitted=False, reason="artifact storage cap")
    return record


def artifact_bytes(get, repo):
    return sum(a["size_in_bytes"] for a in paged(get, f"/repos/{repo}/actions/artifacts", "artifacts")
               if not a["expired"])


def dir_bytes(path):
    return sum(p.lstat().st_size for p in Path(path).rglob("*") if p.is_file() and not p.is_symlink())


def github_get(path, attempts=3):
    """GET with retries on 5xx/network errors."""
    request = urllib.request.Request(
        os.environ.get("GITHUB_API_URL", "https://api.github.com") + path,
        headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
                 "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.URLError as error:  # HTTPError is a subclass
            if attempt == attempts or getattr(error, "code", 500) < 500:
                raise
        time.sleep(2 ** attempt)


def main(argv):
    repo = os.environ["GITHUB_REPOSITORY"]
    if argv[:1] == ["admit"] and len(argv) == 2:
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        record = admit(github_get, repo, now, os.environ.get("BUDGET_MODE") or "warn",
                       int(os.environ["GITHUB_RUN_ID"]), int(os.environ["GITHUB_RUN_ATTEMPT"]))
        Path(argv[1]).write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        for warning in record.get("warnings", []):
            print(f"::warning title=Experimental budget::{warning}")
        print(json.dumps({k: v for k, v in record.items() if k not in ("ledger", "warnings")}, sort_keys=True))
        return 0 if record["admitted"] else 1
    if argv[:1] == ["artifact-check"] and len(argv) == 2:
        size, stored = dir_bytes(argv[1]), artifact_bytes(github_get, repo)
        ok = size <= RUN_ARTIFACT_CAP and stored + size <= ARTIFACT_TOTAL_CAP
        print(json.dumps({"run_bytes": size, "stored_bytes": stored, "run_cap": RUN_ARTIFACT_CAP,
                          "total_cap": ARTIFACT_TOTAL_CAP, "fits": ok}, sort_keys=True))
        return 0 if ok else 1
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
