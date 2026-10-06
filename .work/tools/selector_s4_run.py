"""DELSK-012 S4 ChunkShift measurement runner.

This is implementation plumbing only. The S4 plan and evaluator are executed
from the merged preregistration authority commit, never from this file.

Usage:
  selector_s4_run.py measure PLAN PROTOCOL_DIR PILOT_STORE X0_STORE X0_EVIDENCE \
      CHUNKSHIFT_REPO CHUNKSHIFT_DLL OUT_DIR
"""

import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import time

S4_AUTHORITY = "ea35f16a0f52cd7c41df2763f0bd2794fbbdb476"
CONSUMER_COMMIT = "74bb301b6d8ecc52cf0bc0e00d86fa174093d91b"
MEASUREMENT_SCHEMA = "delsk.chunkshift-s4.measurement.v1"
RUN_SCHEMA = "delsk.chunkshift-s4.run.v1"
X0_RETAINED = Path(".work/results/DELSK-002-X0/37449333091-1")


class RunnerError(Exception):
    pass


def check(ok, message):
    if not ok:
        raise RunnerError(message)


def sha256_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _child_cpu_ns():
    r = resource.getrusage(resource.RUSAGE_CHILDREN)
    return int((r.ru_utime + r.ru_stime) * 1_000_000_000)


def invoke(command, cwd=None, timeout=None):
    before_cpu = _child_cpu_ns()
    started = time.perf_counter_ns()
    try:
        done = subprocess.run(
            [str(x) for x in command],
            cwd=None if cwd is None else str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "returncode": done.returncode,
            "stdout": done.stdout,
            "stderr": done.stderr,
            "wall_ns": time.perf_counter_ns() - started,
            "cpu_ns": max(0, _child_cpu_ns() - before_cpu),
            "timeout": False,
        }
    except subprocess.TimeoutExpired as error:
        return {
            "returncode": None,
            "stdout": error.stdout or "",
            "stderr": error.stderr or "",
            "wall_ns": time.perf_counter_ns() - started,
            "cpu_ns": max(0, _child_cpu_ns() - before_cpu),
            "timeout": True,
        }


def parse_field(text, name):
    prefix = name + "="
    values = [line[len(prefix):] for line in text.splitlines() if line.startswith(prefix)]
    check(len(values) == 1 and values[0], f"missing or duplicate CLI field {name}")
    return values[0]


def git_head(path):
    done = invoke(["git", "-C", str(path), "rev-parse", "HEAD"], timeout=20)
    check(done["returncode"] == 0, "cannot read git HEAD")
    return done["stdout"].strip()


def tracked_clean(path):
    done = invoke(["git", "-C", str(path), "diff", "--quiet", "--ignore-submodules", "HEAD", "--"], timeout=20)
    return done["returncode"] == 0


def canonical_write(path, doc):
    Path(path).write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def locate_object(oid, stores):
    hits = [Path(store) / oid for store in stores if (Path(store) / oid).is_file()]
    check(hits, f"required object absent from materialized stores: {oid}")
    for path in hits:
        check(sha256_file(path) == oid, f"object digest mismatch: {oid}")
    if len(hits) > 1:
        first = hits[0].read_bytes()
        check(all(path.read_bytes() == first for path in hits[1:]), f"same object id has different bytes: {oid}")
    return hits[0]


def verify_x0(protocol_dir, fresh_x0):
    protocol_dir = Path(protocol_dir)
    fresh_x0 = Path(fresh_x0)
    retained = protocol_dir / X0_RETAINED
    files = ("corpus.json.gz", "candidates.json")
    out = {}
    for name in files:
        fresh = fresh_x0 / name
        reference = retained / name
        check(fresh.is_file() and reference.is_file(), f"missing X0 binding file: {name}")
        a, b = sha256_file(fresh), sha256_file(reference)
        check(a == b, f"fresh X0 materialization metadata differs from retained {name}")
        out[name] = a
    return out


class ChunkShiftCli:
    def __init__(self, prefix, manifest_dir, work_dir, timeout_seconds=120):
        self.prefix = [str(x) for x in prefix]
        self.manifest_dir = Path(manifest_dir)
        self.work_dir = Path(work_dir)
        self.timeout_seconds = timeout_seconds
        self.manifest_dir.mkdir(parents=True, exist_ok=True)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.manifests = {}
        self.manifest_wall_ns = 0
        self.manifest_cpu_ns = 0

    def _run(self, args):
        return invoke([*self.prefix, *args], timeout=self.timeout_seconds)

    def manifest_for(self, oid, content_path):
        if oid in self.manifests:
            return self.manifests[oid]
        path = self.manifest_dir / f"{oid}.csm"
        result = self._run(["create", str(content_path), str(path), "--blake3"])
        self.manifest_wall_ns += result["wall_ns"]
        self.manifest_cpu_ns += result["cpu_ns"]
        check(not result["timeout"] and result["returncode"] == 0, f"ChunkShift manifest create failed: {oid}")
        check(path.is_file() and path.stat().st_size > 0, f"ChunkShift manifest missing: {oid}")
        manifest_id = parse_field(result["stdout"], "manifest-id")
        self.manifests[oid] = (path, manifest_id)
        return path, manifest_id

    def measure_pair(self, target_oid, target_path, base_oid=None, base_path=None):
        target_manifest, target_mid = self.manifest_for(target_oid, target_path)
        base_manifest = base_mid = None
        if base_oid is not None:
            check(base_path is not None, "base path missing")
            base_manifest, base_mid = self.manifest_for(base_oid, base_path)

        patch = self.work_dir / "pair.csp"
        applied = self.work_dir / "applied.bin"
        patch.unlink(missing_ok=True)
        applied.unlink(missing_ok=True)

        create_args = [
            "patch", "create",
            "--target-manifest", str(target_manifest),
            "--target", str(target_path),
            "-o", str(patch),
        ]
        if base_oid is not None:
            create_args += ["--base-manifest", str(base_manifest), "--base", str(base_path)]

        create = self._run(create_args)
        row = {
            "schema": MEASUREMENT_SCHEMA,
            "target_occurrence_id": None,
            "target_object_id": target_oid,
            "base_object_id": base_oid,
            "chunkshift_commit": CONSUMER_COMMIT,
            "status": None,
            "error_class": None,
            "patch_bytes": None,
            "create_wall_ns": create["wall_ns"],
            "create_cpu_ns": create["cpu_ns"],
            "apply_wall_ns": 0,
            "apply_cpu_ns": 0,
            "create_exit_code": create["returncode"],
            "apply_exit_code": None,
            "target_manifest_id": target_mid,
            "base_manifest_id": base_mid,
            "patch_file_digest": None,
            "applied_sha256": None,
        }

        if create["timeout"]:
            row.update(status="create_failed", error_class="CREATE_TIMEOUT")
            return row
        if create["returncode"] != 0 or not patch.is_file():
            row.update(status="create_failed", error_class=f"CREATE_EXIT_{create['returncode']}")
            return row

        row["patch_bytes"] = patch.stat().st_size
        row["patch_file_digest"] = sha256_file(patch)

        apply_args = ["patch", "apply", str(patch), "-o", str(applied)]
        if base_oid is not None:
            apply_args += ["--base-manifest", str(base_manifest), "--base", str(base_path)]
        apply = self._run(apply_args)
        row["apply_wall_ns"] = apply["wall_ns"]
        row["apply_cpu_ns"] = apply["cpu_ns"]
        row["apply_exit_code"] = apply["returncode"]

        if apply["timeout"]:
            row.update(status="apply_failed", error_class="APPLY_TIMEOUT")
            return row
        if apply["returncode"] != 0 or not applied.is_file():
            row.update(status="apply_failed", error_class=f"APPLY_EXIT_{apply['returncode']}")
            return row

        row["applied_sha256"] = sha256_file(applied)
        if row["applied_sha256"] != target_oid:
            row.update(status="verify_failed", error_class="SHA256_MISMATCH")
            return row

        row.update(status="ok", error_class=None)
        return row


def _required_object_ids(plan):
    ids = set()
    for target in plan["targets"]:
        ids.add(target["target_object_id"])
        ids.update(target["lanes"]["exhaustive"])
    return sorted(ids)


def descriptor_cost(protocol_dir, object_paths):
    tools = str(Path(protocol_dir) / ".work" / "tools")
    old = list(sys.path)
    sys.path.insert(0, tools)
    try:
        import simple_selector as ss
        started_wall = time.perf_counter_ns()
        started_cpu = time.process_time_ns()
        descriptors = {}
        object_bytes = 0
        for oid, path in sorted(object_paths.items()):
            data = Path(path).read_bytes()
            object_bytes += len(data)
            descriptors[oid] = ss.descriptor(data)
        return {
            "objects": len(descriptors),
            "object_bytes": object_bytes,
            "descriptor_bytes": sum(len(v) * 8 for v in descriptors.values()),
            "wall_ns": time.perf_counter_ns() - started_wall,
            "cpu_ns": time.process_time_ns() - started_cpu,
        }
    finally:
        sys.path[:] = old
        sys.modules.pop("simple_selector", None)
        sys.modules.pop("baselines", None)


def measure(plan_path, protocol_dir, pilot_store, x0_store, x0_evidence,
            chunkshift_repo, chunkshift_dll, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    run_path = out_dir / "run.json"
    started = time.time_ns()
    run = {
        "schema": RUN_SCHEMA,
        "status": "running",
        "s4_authority": S4_AUTHORITY,
        "chunkshift_commit": CONSUMER_COMMIT,
        "implementation_sha": os.environ.get("GITHUB_SHA"),
        "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        "github_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "github_ref": os.environ.get("GITHUB_REF"),
        "github_workflow_sha": os.environ.get("GITHUB_WORKFLOW_SHA"),
        "runner_os": os.environ.get("RUNNER_OS"),
        "runner_arch": os.environ.get("RUNNER_ARCH"),
        "image_os": os.environ.get("ImageOS"),
        "image_version": os.environ.get("ImageVersion"),
        "kernel": invoke(["uname", "-srmo"], timeout=20)["stdout"].strip(),
    }
    canonical_write(run_path, run)

    try:
        protocol_dir = Path(protocol_dir)
        chunkshift_repo = Path(chunkshift_repo)
        check(git_head(protocol_dir) == S4_AUTHORITY, "protocol checkout is not the S4 authority")
        check(git_head(chunkshift_repo) == CONSUMER_COMMIT, "ChunkShift checkout differs from consumer pin")
        check(tracked_clean(protocol_dir), "protocol authority checkout has tracked modifications")
        check(tracked_clean(chunkshift_repo), "ChunkShift checkout has tracked modifications")

        plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
        check(plan["consumer"]["commit"] == CONSUMER_COMMIT, "plan binds another ChunkShift commit")
        check(plan["consumer"]["manifest"]["hash_suite"] == "blake3-256", "plan changed manifest hash suite")
        check(plan["consumer"]["manifest"]["block_index"] is False, "plan enabled BIDX")
        check(plan["consumer"]["object_transform"] == "none", "plan changed object bytes")

        x0_hashes = verify_x0(protocol_dir, x0_evidence)
        stores = (Path(pilot_store), Path(x0_store))
        object_paths = {oid: locate_object(oid, stores) for oid in _required_object_ids(plan)}
        for target in plan["targets"]:
            check(object_paths[target["target_object_id"]].stat().st_size == target["target_bytes"],
                  f"target size mismatch: {target['target_occurrence_id']}")

        descriptor = descriptor_cost(protocol_dir, object_paths)

        dll = Path(chunkshift_dll)
        check(dll.is_file(), "ChunkShift CLI assembly missing")
        cli_sha256 = sha256_file(dll)
        dotnet = invoke(["dotnet", "--version"], timeout=20)
        check(dotnet["returncode"] == 0, "dotnet --version failed")

        cli = ChunkShiftCli(
            ["dotnet", str(dll)],
            out_dir.parent / "manifests",
            out_dir.parent / "pair-work",
        )
        measurements_path = out_dir / "measurements.jsonl"
        expected = 0
        with measurements_path.open("w", encoding="utf-8") as stream:
            for target in sorted(plan["targets"], key=lambda t: t["target_occurrence_id"]):
                tid = target["target_occurrence_id"]
                target_oid = target["target_object_id"]
                target_path = object_paths[target_oid]
                pairs = [None, *target["lanes"]["exhaustive"]]
                for base_oid in pairs:
                    row = cli.measure_pair(
                        target_oid,
                        target_path,
                        base_oid,
                        None if base_oid is None else object_paths[base_oid],
                    )
                    row["target_occurrence_id"] = tid
                    stream.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                    expected += 1

        check(expected == 3815, f"unexpected S4 pair count: {expected}")
        check(tracked_clean(protocol_dir), "protocol authority changed during S4 run")
        check(tracked_clean(chunkshift_repo), "ChunkShift tracked source changed during S4 run")

        run.update(
            status="measured",
            measurement_rows=expected,
            unique_objects=len(object_paths),
            x0_binding_sha256=x0_hashes,
            descriptor=descriptor,
            manifest={
                "count": len(cli.manifests),
                "wall_ns": cli.manifest_wall_ns,
                "cpu_ns": cli.manifest_cpu_ns,
            },
            chunkshift_cli_sha256=cli_sha256,
            dotnet_version=dotnet["stdout"].strip(),
            elapsed_ns=time.time_ns() - started,
        )
        canonical_write(run_path, run)
        return 0
    except Exception as error:
        run.update(
            status="failed",
            error_class=type(error).__name__,
            error=str(error),
            elapsed_ns=time.time_ns() - started,
        )
        canonical_write(run_path, run)
        raise


def main(argv):
    if argv[:1] == ["measure"] and len(argv) == 9:
        return measure(*argv[1:])
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
