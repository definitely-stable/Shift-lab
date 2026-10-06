"""DELSK-012 S4 descriptive selector construction cost on the exact S4-D population.

The S4-D decision does not use these timings. This records cold descriptor
construction and index accounting once, outside the 16 ChunkShift shard runs.

Usage:
  selector_s4_cost.py PROTOCOL_ROOT PILOT_STORE X0_STORE OUT.json \
      --protocol-authority SHA --implementation-sha SHA
"""

import argparse
import importlib
import json
import os
from pathlib import Path
import resource
import sys
import time

SCHEMA = "delsk.chunkshift-s4.selector-cost.v1"
PROTOCOL_SHA = "ea35f16a0f52cd7c41df2763f0bd2794fbbdb476"
HEX = frozenset("0123456789abcdef")


class CostError(Exception):
    pass


def check(ok, message):
    if not ok:
        raise CostError(message)


def is_hex(value, length):
    return isinstance(value, str) and len(value) == length and all(ch in HEX for ch in value)


def load_protocol(protocol_root):
    tools = Path(protocol_root) / ".work" / "tools"
    check(tools.is_dir(), "protocol tools directory missing")
    sys.path.insert(0, str(tools))
    bl = importlib.import_module("baselines")
    ss = importlib.import_module("simple_selector")
    xs = importlib.import_module("x0_screen")
    return bl, ss, xs


def collect_population(bl, ss, xs, pilot_store, x0_store):
    objects = {}
    path_entries = {}

    def add(meta, line, store):
        oid = meta["object_id"]
        size = meta["bytes"]
        existing = objects.get(oid)
        if existing is None:
            objects[oid] = {"bytes": size, "store": str(store)}
        else:
            check(existing["bytes"] == size, f"content size mismatch for {oid}")
        path = meta.get("path")
        if path is not None:
            path_entries.setdefault((path, line), set()).add(oid)

    for q in bl.natural_universe():
        line = q["family_id"]
        add(q["target"], line, pilot_store)
        for base in q["bases"]:
            add(base, line, pilot_store)

    corpus, candidates = xs.load(ss.X0_RUN)
    for q in xs.queries_for_ranking(corpus, candidates):
        t = q["target"]
        add(t, t.get("branch"), x0_store)
        for base in q["bases"]:
            add(base, base.get("branch"), x0_store)

    return objects, path_entries


def peak_rss_bytes():
    # Linux ru_maxrss is KiB.
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)


def run(args):
    check(args.protocol_authority == PROTOCOL_SHA, "selector-cost protocol authority drift")
    check(is_hex(args.implementation_sha, 40), "invalid selector-cost implementation SHA")
    bl, ss, xs = load_protocol(args.protocol_root)
    objects, path_entries = collect_population(bl, ss, xs, args.pilot_store, args.x0_store)

    descriptors = {}
    bytes_scanned = 0
    cpu0 = time.process_time_ns()
    wall0 = time.monotonic_ns()
    for oid, meta in sorted(objects.items()):
        data = bl.read_object(meta["store"], oid, meta["bytes"])
        bytes_scanned += len(data)
        descriptors[oid] = ss.descriptor(data)
    descriptor_wall = time.monotonic_ns() - wall0
    descriptor_cpu = time.process_time_ns() - cpu0

    cpu0 = time.process_time_ns()
    wall0 = time.monotonic_ns()
    postings = {}
    for ordinal, (oid, descriptor) in enumerate(sorted(descriptors.items())):
        for h in descriptor:
            postings.setdefault(h, []).append(ordinal)
    # Match Rust Catalog::index_bytes accounting: posting/path u32 ids plus
    # u64 posting keys. String keys and allocator overhead are intentionally
    # excluded, exactly as in S2.
    posting_ids = sum(len(v) for v in postings.values())
    path_ids = sum(len(v) for v in path_entries.values())
    index_bytes = posting_ids * 4 + len(postings) * 8 + path_ids * 4
    index_wall = time.monotonic_ns() - wall0
    index_cpu = time.process_time_ns() - cpu0

    record = {
        "schema": SCHEMA,
        "protocol_authority": args.protocol_authority,
        "implementation_sha": args.implementation_sha,
        "selector": ss.SPEC,
        "population": "S4-D exact objects; development+calibration pilot and all X0 cells",
        "decision_endpoint": False,
        "accounting": "Rust Catalog::index_bytes compatible; excludes string keys and allocator overhead",
        "objects": len(objects),
        "object_bytes_scanned": bytes_scanned,
        "descriptor_bytes": sum(len(d) * 8 for d in descriptors.values()),
        "descriptor_wall_ns": descriptor_wall,
        "descriptor_cpu_ns": descriptor_cpu,
        "posting_keys": len(postings),
        "posting_ids": posting_ids,
        "metadata_path_keys": len(path_entries),
        "metadata_path_ids": path_ids,
        "index_bytes": index_bytes,
        "index_wall_ns": index_wall,
        "index_cpu_ns": index_cpu,
        "peak_rss_bytes": peak_rss_bytes(),
        "runner": {
            "github_sha": os.environ.get("GITHUB_SHA"),
            "github_workflow_sha": os.environ.get("GITHUB_WORKFLOW_SHA"),
            "github_run_id": os.environ.get("GITHUB_RUN_ID"),
            "github_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
            "github_ref": os.environ.get("GITHUB_REF"),
            "runner_os": os.environ.get("RUNNER_OS"),
            "runner_arch": os.environ.get("RUNNER_ARCH"),
            "image_os": os.environ.get("ImageOS"),
            "image_version": os.environ.get("ImageVersion"),
        },
    }
    Path(args.out).write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: record[k] for k in ("objects", "object_bytes_scanned", "index_bytes")}, sort_keys=True))
    return 0


def parser():
    p = argparse.ArgumentParser()
    p.add_argument("protocol_root")
    p.add_argument("pilot_store")
    p.add_argument("x0_store")
    p.add_argument("out")
    p.add_argument("--protocol-authority", required=True)
    p.add_argument("--implementation-sha", required=True)
    return p


if __name__ == "__main__":
    raise SystemExit(run(parser().parse_args()))
