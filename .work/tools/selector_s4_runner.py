"""DELSK-012 S4 GitHub-hosted shard runner.

Implementation-only tooling. The S4 plan and evaluator remain authoritative at
PR #52's merge commit; this file only executes one deterministic target shard
and emits the already-frozen measurement schema.

Usage:
  selector_s4_runner.py measure-shard PLAN PILOT_STORE X0_STORE CHUNKSHIFT_DLL \
      SHARD_INDEX OUT_DIR --protocol-authority SHA --implementation-sha SHA
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import tempfile
import time

SHARD_COUNT = 16
PROTOCOL_SHA = "ea35f16a0f52cd7c41df2763f0bd2794fbbdb476"
PLAN_SCHEMA = "delsk.chunkshift-s4.plan.v1"
MEASUREMENT_SCHEMA = "delsk.chunkshift-s4.measurement.v1"
SHARD_SCHEMA = "delsk.chunkshift-s4.shard.v1"
MANIFEST_SCHEMA = "delsk.chunkshift-s4.manifest.v1"
CONSUMER_SHA = "74bb301b6d8ecc52cf0bc0e00d86fa174093d91b"
HEX = frozenset("0123456789abcdef")


class RunnerError(Exception):
    pass


def check(ok, message):
    if not ok:
        raise RunnerError(message)


def is_hex(value, length):
    return isinstance(value, str) and len(value) == length and all(c in HEX for c in value)


def canonical_bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def file_sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while block := stream.read(1 << 20):
            h.update(block)
    return h.hexdigest()


def parse_kv(stdout):
    out = {}
    for line in stdout.splitlines():
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        check(key not in out, f"duplicate CLI output key {key!r}")
        out[key] = value
    return out


def run_process(argv):
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    started = time.monotonic_ns()
    completed = subprocess.run(argv, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    wall = time.monotonic_ns() - started
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu = int(
        ((after.ru_utime - before.ru_utime) + (after.ru_stime - before.ru_stime))
        * 1_000_000_000
    )
    return completed, wall, max(cpu, 0)


def load_plan(path):
    raw = Path(path).read_bytes()
    doc = json.loads(raw)
    check(doc.get("schema") == PLAN_SCHEMA, "foreign S4 plan")
    check(doc.get("consumer", {}).get("commit") == CONSUMER_SHA, "plan pins another ChunkShift commit")
    check(doc.get("consumer", {}).get("object_transform") == "none", "plan changes object bytes")
    manifest = doc.get("consumer", {}).get("manifest", {})
    check(manifest.get("hash_suite") == "blake3-256", "plan changes manifest hash suite")
    check(manifest.get("block_index") is False, "plan enables BIDX")
    check(doc.get("consumer", {}).get("cli_build", {}).get("configuration") == "Release",
          "plan changes ChunkShift build configuration")
    check(doc.get("consumer", {}).get("cli_build", {}).get("target_framework") == "net10.0",
          "plan changes ChunkShift target framework")
    targets = doc.get("targets")
    check(isinstance(targets, list) and targets, "empty S4 plan")
    ids = [t.get("target_occurrence_id") for t in targets]
    check(len(ids) == len(set(ids)), "duplicate target in S4 plan")
    return doc, hashlib.sha256(raw).hexdigest()


def shard_targets(plan, shard_index):
    check(0 <= shard_index < SHARD_COUNT, f"shard index must be 0..{SHARD_COUNT - 1}")
    ordered = sorted(plan["targets"], key=lambda t: t["target_occurrence_id"])
    return [target for ordinal, target in enumerate(ordered) if ordinal % SHARD_COUNT == shard_index]


def expected_rows(targets):
    return sum(1 + len(target["lanes"]["exhaustive"]) for target in targets)


def store_for(target, pilot_store, x0_store):
    population = target["population"]
    if population.startswith("pilot-"):
        return Path(pilot_store)
    if population.startswith("x0-"):
        return Path(x0_store)
    raise RunnerError(f"foreign S4 population: {population}")


def verify_object(path, object_id):
    check(path.is_file() and not path.is_symlink(), f"object missing: {object_id}")
    check(file_sha256(path) == object_id, f"object integrity failure: {object_id}")


def all_object_paths(plan, pilot_store, x0_store):
    out = {}
    for target in plan["targets"]:
        store = store_for(target, pilot_store, x0_store)
        ids = [target["target_object_id"], *target["lanes"]["exhaustive"]]
        for object_id in ids:
            path = store / object_id
            verify_object(path, object_id)
            if object_id in out:
                check(file_sha256(out[object_id]) == file_sha256(path),
                      f"same object id has inconsistent materialization: {object_id}")
            else:
                out[object_id] = path
    return out


def descriptor_cost(protocol_dir, plan, pilot_store, x0_store):
    protocol_dir = Path(protocol_dir)
    check(protocol_dir.is_dir(), "protocol checkout missing")
    objects = all_object_paths(plan, pilot_store, x0_store)
    tools = str(protocol_dir / ".work" / "tools")
    old_path = list(sys.path)
    sys.path.insert(0, tools)
    try:
        import simple_selector as ss
        started_wall = time.monotonic_ns()
        started_cpu = time.process_time_ns()
        descriptor_bytes = 0
        object_bytes = 0
        for object_id, object_path in sorted(objects.items()):
            data = object_path.read_bytes()
            object_bytes += len(data)
            descriptor_bytes += len(ss.descriptor(data)) * 8
        return {
            "schema": "delsk.chunkshift-s4.selector-cost.v1",
            "protocol_authority": PROTOCOL_SHA,
            "objects": len(objects),
            "object_bytes": object_bytes,
            "descriptor_bytes": descriptor_bytes,
            "wall_ns": time.monotonic_ns() - started_wall,
            "cpu_ns": time.process_time_ns() - started_cpu,
            "index_kind": "object-id-to-64-byte-descriptor-table",
        }
    finally:
        sys.path[:] = old_path
        sys.modules.pop("simple_selector", None)
        sys.modules.pop("baselines", None)


def create_manifest(cli, content_path, object_id, manifest_dir):
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest = manifest_dir / f"{object_id}.csm"
    completed, wall, cpu = run_process(
        ["dotnet", str(cli), "create", str(content_path), str(manifest), "--blake3"]
    )
    fields = parse_kv(completed.stdout)
    check(completed.returncode == 0, f"manifest create failed for {object_id}")
    check(manifest.is_file() and not manifest.is_symlink(), f"manifest not published: {object_id}")
    check(fields.get("bidx") == "false", f"manifest unexpectedly has BIDX: {object_id}")
    check(fields.get("content-bytes") == str(content_path.stat().st_size),
          f"manifest content size mismatch: {object_id}")
    manifest_id = fields.get("manifest-id")
    check(bool(manifest_id), f"manifest id missing: {object_id}")
    return {
        "schema": MANIFEST_SCHEMA,
        "object_id": object_id,
        "manifest_id": manifest_id,
        "manifest_sha256": file_sha256(manifest),
        "physical_bytes": manifest.stat().st_size,
        "wall_ns": wall,
        "cpu_ns": cpu,
    }, manifest


def classify_error(stderr, fallback):
    text = " ".join(stderr.strip().split())
    if not text:
        return fallback
    digest = hashlib.sha256(text.encode()).hexdigest()[:16]
    return f"{fallback}:{digest}"


def measure_pair(cli, target, base_id, store, manifests, work):
    tid = target["target_occurrence_id"]
    target_id = target["target_object_id"]
    target_path = store / target_id
    target_manifest = manifests[target_id][1]
    target_manifest_id = manifests[target_id][0]["manifest_id"]

    base_path = base_manifest = base_manifest_id = None
    if base_id is not None:
        base_path = store / base_id
        base_manifest = manifests[base_id][1]
        base_manifest_id = manifests[base_id][0]["manifest_id"]

    stem = hashlib.sha256(f"{tid}\0{base_id or 'standalone'}".encode()).hexdigest()
    patch = work / f"{stem}.csp"
    output = work / f"{stem}.out"

    create_args = [
        "dotnet", str(cli), "patch", "create",
        "--target-manifest", str(target_manifest),
        "--target", str(target_path),
        "-o", str(patch),
    ]
    if base_id is not None:
        create_args += ["--base-manifest", str(base_manifest), "--base", str(base_path)]

    created, create_wall, create_cpu = run_process(create_args)
    create_fields = parse_kv(created.stdout)
    patch_bytes = patch.stat().st_size if patch.is_file() else None
    patch_digest = file_sha256(patch) if patch.is_file() else None

    common = {
        "schema": MEASUREMENT_SCHEMA,
        "target_occurrence_id": tid,
        "target_object_id": target_id,
        "base_object_id": base_id,
        "chunkshift_commit": CONSUMER_SHA,
        "patch_bytes": patch_bytes,
        "create_wall_ns": create_wall,
        "create_cpu_ns": create_cpu,
        "apply_wall_ns": 0,
        "apply_cpu_ns": 0,
        "create_exit_code": created.returncode,
        "apply_exit_code": None,
        "target_manifest_id": target_manifest_id,
        "base_manifest_id": base_manifest_id,
        "patch_file_digest": patch_digest,
        "applied_sha256": None,
    }

    create_ok = (
        created.returncode == 0
        and patch_bytes is not None
        and patch_bytes > 0
        and create_fields.get("target-manifest-id") == target_manifest_id
        and create_fields.get("patch-bytes") == str(patch_bytes)
        and (
            (base_id is None and "base-manifest-id" not in create_fields)
            or (base_id is not None and create_fields.get("base-manifest-id") == base_manifest_id)
        )
    )
    if not create_ok:
        return {
            **common,
            "status": "create_failed",
            "error_class": classify_error(created.stderr, "CREATE_OR_BINDING"),
        }

    apply_args = ["dotnet", str(cli), "patch", "apply", str(patch), "-o", str(output)]
    if base_id is not None:
        apply_args += ["--base-manifest", str(base_manifest), "--base", str(base_path)]

    applied, apply_wall, apply_cpu = run_process(apply_args)
    common["apply_wall_ns"] = apply_wall
    common["apply_cpu_ns"] = apply_cpu
    common["apply_exit_code"] = applied.returncode

    if applied.returncode != 0 or not output.is_file() or output.is_symlink():
        return {
            **common,
            "status": "apply_failed",
            "error_class": classify_error(applied.stderr, "APPLY"),
        }

    applied_sha = file_sha256(output)
    common["applied_sha256"] = applied_sha
    if applied_sha != target_id:
        return {
            **common,
            "status": "verify_failed",
            "error_class": "SHA256_MISMATCH",
        }

    return {**common, "status": "ok", "error_class": None}


def write_jsonl(path, rows):
    with Path(path).open("wb") as stream:
        for row in rows:
            stream.write(canonical_bytes(row))


def measure_shard(args):
    protocol_sha = args.protocol_authority.lower()
    implementation_sha = args.implementation_sha.lower()
    check(is_hex(protocol_sha, 40), "invalid protocol authority")
    check(protocol_sha == PROTOCOL_SHA, "protocol authority differs from frozen S4 authority")
    check(is_hex(implementation_sha, 40), "invalid implementation SHA")

    plan, plan_sha = load_plan(args.plan)
    targets = shard_targets(plan, args.shard_index)
    check(targets, "empty deterministic shard")

    cli = Path(args.chunkshift_dll)
    check(cli.is_file() and not cli.is_symlink(), "ChunkShift CLI DLL missing")
    cli_sha256 = file_sha256(cli)
    dotnet, _, _ = run_process(["dotnet", "--version"])
    check(dotnet.returncode == 0 and dotnet.stdout.strip(), "dotnet --version failed")
    dotnet_version = dotnet.stdout.strip()

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=f"s4-{args.shard_index:02d}-"))
    manifests = {}
    manifest_rows = []
    rows = []
    selector_cost = None
    if args.shard_index == 0:
        selector_cost = descriptor_cost(args.protocol_dir, plan, args.pilot_store, args.x0_store)
        (out / "selector-cost.json").write_bytes(canonical_bytes(selector_cost))
    try:
        objects = {}
        for target in targets:
            store = store_for(target, args.pilot_store, args.x0_store)
            objects.setdefault(target["target_object_id"], store / target["target_object_id"])
            for base_id in target["lanes"]["exhaustive"]:
                objects.setdefault(base_id, store / base_id)

        manifest_dir = work / "manifests"
        for object_id, object_path in sorted(objects.items()):
            check(is_hex(object_id, 64), f"invalid object id in plan: {object_id!r}")
            verify_object(object_path, object_id)
            record, manifest = create_manifest(cli, object_path, object_id, manifest_dir)
            manifests[object_id] = (record, manifest)
            manifest_rows.append(record)

        for target in sorted(targets, key=lambda t: t["target_occurrence_id"]):
            store = store_for(target, args.pilot_store, args.x0_store)
            rows.append(measure_pair(cli, target, None, store, manifests, work))
            for base_id in target["lanes"]["exhaustive"]:
                rows.append(measure_pair(cli, target, base_id, store, manifests, work))
            for path in work.glob("*.csp"):
                path.unlink(missing_ok=True)
            for path in work.glob("*.out"):
                path.unlink(missing_ok=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    check(len(rows) == expected_rows(targets), "shard did not emit the exact planned row count")
    keys = [(r["target_occurrence_id"], r["base_object_id"] or "") for r in rows]
    check(len(keys) == len(set(keys)), "duplicate pair inside shard")
    rows.sort(key=lambda r: (r["target_occurrence_id"], r["base_object_id"] or ""))
    manifest_rows.sort(key=lambda r: r["object_id"])

    measurements = out / "measurements.jsonl"
    manifest_path = out / "manifests.jsonl"
    write_jsonl(measurements, rows)
    write_jsonl(manifest_path, manifest_rows)

    shard = {
        "schema": SHARD_SCHEMA,
        "protocol_authority": protocol_sha,
        "implementation_sha": implementation_sha,
        "chunkshift_commit": CONSUMER_SHA,
        "shard_index": args.shard_index,
        "shard_count": SHARD_COUNT,
        "plan_sha256": plan_sha,
        "targets": len(targets),
        "target_occurrence_ids": sorted(t["target_occurrence_id"] for t in targets),
        "expected_rows": expected_rows(targets),
        "actual_rows": len(rows),
        "ok_rows": sum(r["status"] == "ok" for r in rows),
        "failed_rows": sum(r["status"] != "ok" for r in rows),
        "measurement_sha256": file_sha256(measurements),
        "manifest_sha256": file_sha256(manifest_path),
        "chunkshift_cli_sha256": cli_sha256,
        "dotnet_version": dotnet_version,
        "selector_cost_sha256": file_sha256(out / "selector-cost.json") if selector_cost is not None else None,
        "runner": {
            "github_run_id": os.environ.get("GITHUB_RUN_ID"),
            "github_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
            "github_ref": os.environ.get("GITHUB_REF"),
            "runner_os": os.environ.get("RUNNER_OS"),
            "runner_arch": os.environ.get("RUNNER_ARCH"),
            "image_os": os.environ.get("ImageOS"),
            "image_version": os.environ.get("ImageVersion"),
        },
    }
    (out / "shard.json").write_bytes(canonical_bytes(shard))
    print(json.dumps({k: shard[k] for k in ("shard_index", "targets", "actual_rows", "ok_rows", "failed_rows")},
                     sort_keys=True))
    return 0


def parser():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="command", required=True)
    m = sub.add_parser("measure-shard")
    m.add_argument("plan")
    m.add_argument("pilot_store")
    m.add_argument("x0_store")
    m.add_argument("chunkshift_dll")
    m.add_argument("shard_index", type=int)
    m.add_argument("out_dir")
    m.add_argument("--protocol-dir", required=True)
    m.add_argument("--protocol-authority", required=True)
    m.add_argument("--implementation-sha", required=True)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    if args.command == "measure-shard":
        return measure_shard(args)
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
