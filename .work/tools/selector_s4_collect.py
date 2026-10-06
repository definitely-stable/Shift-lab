"""DELSK-012 S4 shard evidence collector.

This tool does not decide S4. It verifies and merges the 16 shard evidence
bundles. The final result must be produced by selector_s4.py from the immutable
protocol-authority checkout.

Usage:
  selector_s4_collect.py merge PLAN ARTIFACT_INDEX_JSONL SHARDS_ROOT OUT_DIR
"""

import hashlib
import json
from pathlib import Path
import sys

SHARD_COUNT = 16
PROTOCOL_SHA = "ea35f16a0f52cd7c41df2763f0bd2794fbbdb476"
CONSUMER_SHA = "74bb301b6d8ecc52cf0bc0e00d86fa174093d91b"
SHARD_SCHEMA = "delsk.chunkshift-s4.shard.v1"
RUN_SCHEMA = "delsk.chunkshift-s4.run.v1"
COLLECTION_SCHEMA = "delsk.chunkshift-s4.collection.v1"
HEX = frozenset("0123456789abcdef")


class CollectError(Exception):
    pass


def check(ok, message):
    if not ok:
        raise CollectError(message)


def is_hex(value, length):
    return isinstance(value, str) and len(value) == length and all(ch in HEX for ch in value)


def canonical_bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def file_sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while block := stream.read(1 << 20):
            h.update(block)
    return h.hexdigest()


def jsonl(path):
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line:
            rows.append(json.loads(line))
    return rows


def load_artifact_index(path):
    rows = jsonl(path)
    check(len(rows) == SHARD_COUNT, f"artifact index must contain {SHARD_COUNT} rows")
    out = {}
    for row in rows:
        check(set(row) == {
            "run_id", "run_attempt", "head_sha", "workflow_path",
            "artifact_id", "artifact_name", "artifact_digest", "artifact_size",
        }, "artifact-index row shape changed")
        run_id = row["run_id"]
        check(isinstance(run_id, int) and run_id > 0, "invalid shard run id")
        check(run_id not in out, f"duplicate shard run id: {run_id}")
        check(row["run_attempt"] == 1, f"selected shard run {run_id} is a rerun")
        check(row["workflow_path"] == ".github/workflows/selector-s4-shard.yml",
              f"wrong workflow for run {run_id}")
        check(
            isinstance(row["artifact_digest"], str)
            and row["artifact_digest"].startswith("sha256:")
            and len(row["artifact_digest"]) == 71,
            f"missing GitHub artifact digest for run {run_id}",
        )
        check(isinstance(row["artifact_size"], int) and row["artifact_size"] > 0,
              f"invalid artifact size for run {run_id}")
        out[run_id] = row
    return out


def merge(plan_path, artifact_index_path, shards_root, out_dir):
    plan_raw = Path(plan_path).read_bytes()
    plan_sha = hashlib.sha256(plan_raw).hexdigest()
    plan = json.loads(plan_raw)
    check(plan.get("schema") == "delsk.chunkshift-s4.plan.v1", "foreign S4 plan")
    check(plan.get("consumer", {}).get("commit") == CONSUMER_SHA, "plan binds another consumer")

    artifacts = load_artifact_index(artifact_index_path)
    root = Path(shards_root)
    dirs = sorted(p for p in root.iterdir() if p.is_dir())
    check(len(dirs) == SHARD_COUNT, f"expected {SHARD_COUNT} shard directories")

    seen_indices = set()
    implementation_sha = None
    rows = []
    row_keys = set()
    shard_records = []

    for directory in dirs:
        for name in ("shard.json", "run.json", "admission.json", "measurements.jsonl", "manifests.jsonl"):
            check((directory / name).is_file(), f"{directory.name}: missing {name}")

        shard = json.loads((directory / "shard.json").read_text(encoding="utf-8"))
        run = json.loads((directory / "run.json").read_text(encoding="utf-8"))
        admission = json.loads((directory / "admission.json").read_text(encoding="utf-8"))

        check(shard.get("schema") == SHARD_SCHEMA, f"{directory.name}: foreign shard schema")
        index = shard.get("shard_index")
        check(isinstance(index, int) and 0 <= index < SHARD_COUNT, f"{directory.name}: bad shard index")
        check(index not in seen_indices, f"duplicate shard index: {index}")
        seen_indices.add(index)
        check(shard.get("shard_count") == SHARD_COUNT, f"shard {index}: shard count changed")
        check(shard.get("protocol_authority") == PROTOCOL_SHA, f"shard {index}: wrong protocol")
        check(shard.get("chunkshift_commit") == CONSUMER_SHA, f"shard {index}: wrong consumer")
        check(shard.get("plan_sha256") == plan_sha, f"shard {index}: wrong plan digest")
        check(shard.get("measurement_sha256") == file_sha256(directory / "measurements.jsonl"),
              f"shard {index}: measurements digest mismatch")
        check(shard.get("manifest_sha256") == file_sha256(directory / "manifests.jsonl"),
              f"shard {index}: manifests digest mismatch")

        current_impl = shard.get("implementation_sha")
        check(is_hex(current_impl, 40), f"shard {index}: bad implementation SHA")
        if implementation_sha is None:
            implementation_sha = current_impl
        check(current_impl == implementation_sha, f"shard {index}: implementation SHA drift")

        check(run.get("schema") == RUN_SCHEMA, f"shard {index}: foreign run schema")
        check(run.get("protocol_authority") == PROTOCOL_SHA, f"shard {index}: run protocol drift")
        check(run.get("chunkshift_commit") == CONSUMER_SHA, f"shard {index}: run consumer drift")
        check(run.get("shard_index") == index and run.get("shard_count") == SHARD_COUNT,
              f"shard {index}: run shard binding mismatch")
        check(run.get("github_sha") == implementation_sha, f"shard {index}: run head drift")
        check(run.get("github_workflow_sha") == implementation_sha,
              f"shard {index}: workflow bytes came from another commit")
        check(run.get("github_ref") == "refs/heads/main", f"shard {index}: run was not dispatched from main")
        check(str(run.get("github_run_attempt")) == "1", f"shard {index}: run attempt is not 1")
        run_id_text = str(run.get("github_run_id") or "")
        check(run_id_text.isdigit(), f"shard {index}: invalid run id")
        run_id = int(run_id_text)
        check(run_id in artifacts, f"shard {index}: run missing from artifact index")
        artifact = artifacts[run_id]
        check(artifact["head_sha"] == implementation_sha, f"shard {index}: API head SHA drift")
        expected_name = f"delsk-s4-shard-{index}-of-{SHARD_COUNT}-{run_id}-1"
        check(artifact["artifact_name"] == expected_name, f"shard {index}: artifact name mismatch")

        check(admission.get("schema") == "delsk.ci.admission.v1", f"shard {index}: foreign admission")
        check(admission.get("admitted") is True, f"shard {index}: compute was not admitted")

        shard_rows = jsonl(directory / "measurements.jsonl")
        check(len(shard_rows) == shard.get("actual_rows") == shard.get("expected_rows"),
              f"shard {index}: row count mismatch")
        check(sum(row.get("status") == "ok" for row in shard_rows) == shard.get("ok_rows"),
              f"shard {index}: ok-row count mismatch")
        check(sum(row.get("status") != "ok" for row in shard_rows) == shard.get("failed_rows"),
              f"shard {index}: failed-row count mismatch")

        for row in shard_rows:
            key = (row.get("target_occurrence_id"), row.get("base_object_id"))
            check(key not in row_keys, f"duplicate measurement across shards: {key}")
            row_keys.add(key)
            rows.append(row)

        shard_records.append({
            "shard_index": index,
            "run_id": run_id,
            "artifact_id": artifact["artifact_id"],
            "artifact_digest": artifact["artifact_digest"],
            "artifact_size": artifact["artifact_size"],
            "rows": len(shard_rows),
            "failed_rows": shard.get("failed_rows"),
        })

    check(seen_indices == set(range(SHARD_COUNT)), "shard index set is incomplete")

    rows.sort(key=lambda row: (row["target_occurrence_id"], row["base_object_id"] or ""))
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    measurements = out / "measurements.jsonl"
    with measurements.open("wb") as stream:
        for row in rows:
            stream.write(canonical_bytes(row))

    record = {
        "schema": COLLECTION_SCHEMA,
        "protocol_authority": PROTOCOL_SHA,
        "implementation_sha": implementation_sha,
        "chunkshift_commit": CONSUMER_SHA,
        "shard_count": SHARD_COUNT,
        "plan_sha256": plan_sha,
        "rows": len(rows),
        "failed_rows": sum(row.get("status") != "ok" for row in rows),
        "measurements_sha256": file_sha256(measurements),
        "shards": sorted(shard_records, key=lambda row: row["shard_index"]),
    }
    (out / "collection.json").write_bytes(canonical_bytes(record))
    print(json.dumps({k: record[k] for k in ("rows", "failed_rows", "implementation_sha")}, sort_keys=True))
    return 0


def main(argv):
    if argv[:1] == ["merge"] and len(argv) == 5:
        return merge(*argv[1:])
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
