"""DELSK-005 foundation runner: frozen-identity dispatch check and a bounded workload.

Linux only (setrlimit, process groups). Stdlib only. The runner validates the
dispatch, runs one allowlisted workload under wall-time, address-space and
work-directory byte limits, and always writes run.json — also when the
workload fails or a limit kills it — so failure evidence is kept.

    python3 foundation_run.py OUT_DIR WORK_DIR ADMISSION_JSON

Dispatch values come only through env (WORKLOAD, SOURCE_SHA); they are never
interpolated into shell code. Workload evidence written to WORK_DIR/evidence is
copied to OUT_DIR/workload. Contract prose: .work/ci-plan.md.
"""

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import subprocess
import sys
import time

WORKFLOW_PATH = ".github/workflows/foundation.yml"
# Workload time limit leaves room inside the 30-minute job for evidence upload.
LIMITS = {"wall_seconds": 22 * 60, "address_space_bytes": 8 << 30, "work_dir_bytes": 1280 << 20}
FREE_DISK_MARGIN = 2  # free disk must be >= margin * work_dir_bytes before start
POLL_SECONDS = 1.0
TAIL_BYTES = 4096
SELFTEST_BYTES = 64 << 20


def selftest():
    """Service workload: SHA-256 over a deterministic 64 MiB stream. Not a Delsk measurement."""
    stream, block = hashlib.sha256(), bytearray()
    for i in range(SELFTEST_BYTES // 32):
        block += hashlib.sha256(i.to_bytes(8, "little")).digest()
        if len(block) >= 1 << 20:
            stream.update(block)
            block.clear()
    stream.update(block)
    print(json.dumps({"selftest_sha256": stream.hexdigest(), "bytes": SELFTEST_BYTES}))


MATERIALIZE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "materialize.py")
# Workloads run with cwd = work dir and write evidence only to ./evidence (inside
# the polled work dir); main copies it next to run.json after the run.
WORKLOAD_EVIDENCE = "evidence"
WORKLOADS = {"selftest": [sys.executable, os.path.abspath(__file__), "--selftest"],
             "materialize-discover": [sys.executable, MATERIALIZE, "discover", WORKLOAD_EVIDENCE],
             "materialize-verify": [sys.executable, MATERIALIZE, "verify", WORKLOAD_EVIDENCE]}


def validate_dispatch(env):
    """Errors for a dispatch that is not a frozen, allowlisted x64 foundation run."""
    errors = []
    sha = env.get("SOURCE_SHA", "")
    if env.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        errors.append(f"event {env.get('GITHUB_EVENT_NAME')!r} is not workflow_dispatch")
    if env.get("WORKLOAD") not in WORKLOADS:
        errors.append(f"workload {env.get('WORKLOAD')!r} is not allowlisted")
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        errors.append("source_sha must be a full lowercase 40-hex commit")
    elif env.get("GITHUB_SHA") != sha:
        errors.append(f"checked-out commit {env.get('GITHUB_SHA')} is not source_sha {sha}")
    if env.get("GITHUB_WORKFLOW_SHA") != env.get("GITHUB_SHA"):
        errors.append("workflow file commit differs from source commit")
    if not env.get("GITHUB_WORKFLOW_REF", "").startswith(f"{env.get('GITHUB_REPOSITORY')}/{WORKFLOW_PATH}@"):
        errors.append(f"unexpected workflow ref {env.get('GITHUB_WORKFLOW_REF')!r}")
    if env.get("RUNNER_ARCH") != "X64":
        errors.append(f"runner arch {env.get('RUNNER_ARCH')!r}: R0 foundation scope is x64")
    return errors


def dir_bytes(path):
    total = 0
    for root, _, files in os.walk(path):
        for name in files:
            try:
                total += os.lstat(os.path.join(root, name)).st_size
            except FileNotFoundError:
                pass
    return total


def mem_available():
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) * 1024
    return None


def run_bounded(argv, work_dir, limits):
    """Run argv in work_dir under limits; returns a record, never raises on workload failure.

    Address space is capped per process with RLIMIT_AS (an allocation failure
    ends the child with a nonzero exit, status `failed`); a multi-process
    workload can exceed it in total. Wall time and work_dir + captured
    stdout/stderr bytes are polled; a breach kills the whole process group.
    """
    # ponytail: work_dir is polled, so a burst between polls or unlinked-open files
    # can briefly exceed the cap; switch to a sized loop filesystem if that matters.
    import resource

    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    record = {"argv": argv[1:], "limits": dict(limits),
              "limit_methods": {"wall_seconds": "poll+SIGKILL process group",
                                "address_space_bytes": "RLIMIT_AS",
                                "work_dir_bytes": "poll+SIGKILL process group"}}
    free = shutil.disk_usage(work_dir).free
    available = mem_available()
    record["precheck"] = {"free_disk_bytes": free, "mem_available_bytes": available}
    if free < FREE_DISK_MARGIN * limits["work_dir_bytes"]:
        record.update(status="precheck_failed", reason="free disk below margin x work_dir_bytes")
        return record
    if available is not None and available < limits["address_space_bytes"]:
        record.update(status="precheck_failed", reason="MemAvailable below address-space limit")
        return record

    def preexec():
        cap = limits["address_space_bytes"]
        resource.setrlimit(resource.RLIMIT_AS, (cap, cap))

    started = time.monotonic()
    record["started_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    out_path, err_path = work_dir.parent / "workload.stdout", work_dir.parent / "workload.stderr"
    with open(out_path, "wb") as out, open(err_path, "wb") as err:
        child = subprocess.Popen(argv, cwd=work_dir, stdout=out, stderr=err,
                                 start_new_session=True, preexec_fn=preexec)
        def used():
            return dir_bytes(work_dir) + out_path.stat().st_size + err_path.stat().st_size

        status, peak = None, 0
        while child.poll() is None:
            time.sleep(POLL_SECONDS)
            peak = max(peak, used())
            if time.monotonic() - started > limits["wall_seconds"]:
                status = "time_limit"
            elif peak > limits["work_dir_bytes"]:
                status = "disk_limit"
            if status:
                break
        try:  # also after a normal exit: no background process outlives the workload
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        child.wait()
    peak = max(peak, used())
    if status is None and peak > limits["work_dir_bytes"]:
        status = "disk_limit"
    rc = child.returncode
    record.update(
        status=status or ("ok" if rc == 0 else "failed"),
        exit_code=rc if rc >= 0 else None, signal=-rc if rc < 0 else None,
        wall_seconds=round(time.monotonic() - started, 3),
        completed_at=dt.datetime.now(dt.timezone.utc).isoformat(),
        peak_work_dir_bytes=peak,
        # RUSAGE_CHILDREN: max over all reaped children of this runner, not only the workload.
        peak_children_rss_bytes=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss * 1024,
        stdout_tail=out_path.read_bytes()[-TAIL_BYTES:].decode("utf-8", "replace"),
        stderr_tail=err_path.read_bytes()[-TAIL_BYTES:].decode("utf-8", "replace"))
    return record


def environment(env):
    keys = ("GITHUB_REPOSITORY", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_SHA", "GITHUB_WORKFLOW_SHA",
            "GITHUB_WORKFLOW_REF", "GITHUB_REF", "GITHUB_ACTOR", "RUNNER_OS", "RUNNER_ARCH",
            "ImageOS", "ImageVersion")
    cpu = next((line.split(":", 1)[1].strip() for line in Path("/proc/cpuinfo").read_text().splitlines()
                if line.startswith("model name")), "unavailable")
    return {"github": {k: env.get(k) for k in keys}, "python": sys.version, "platform": platform.platform(),
            "cpu_model": cpu, "logical_cpus": os.cpu_count()}


def main(argv, env):
    if argv == ["--selftest"]:
        selftest()
        return 0
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    out_dir, work_dir, admission_path = Path(argv[0]), Path(argv[1]), Path(argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    record = {"schema": "delsk.ci.foundation-run.v1", "evidence_scope": "foundation",
              "oracle": "NOT_RUN", "quality_verdict": "N/A",
              "workload": env.get("WORKLOAD"), "source_sha": env.get("SOURCE_SHA"), "status": "runner_error"}
    try:
        record["environment"] = environment(env)
        try:
            record["admission"] = json.loads(admission_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            record["admission"] = {"admitted": False, "reason": f"unreadable admission record: {error}"}
        errors = validate_dispatch(env)
        if errors:
            record.update(status="dispatch_rejected", errors=errors)
        elif not isinstance(record["admission"], dict) or record["admission"].get("admitted") is not True:
            record.update(status="not_admitted")
        else:
            record.update(run_bounded(WORKLOADS[env["WORKLOAD"]], work_dir, LIMITS))
            produced = work_dir / WORKLOAD_EVIDENCE
            if produced.is_dir():  # also after a failure: partial evidence is kept
                shutil.copytree(produced, out_dir / "workload", symlinks=True, dirs_exist_ok=True)
    except BaseException as error:  # evidence is written even when the runner itself breaks
        record.update(status="runner_error", error=f"{type(error).__name__}: {error}")
    finally:
        (out_dir / "run.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": record["status"], "errors": record.get("errors", [])}))
    return 0 if record["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:], os.environ))
