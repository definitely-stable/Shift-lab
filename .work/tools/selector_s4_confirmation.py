"""S4-C sealed-holdout plan and evaluator.

This file is frozen before the E1 evaluation split is materialized for Delsk.
It reads only already-sealed metadata while building the plan.

Usage:
  selector_s4_confirmation.py plan OUT.json --protocol-authority SHA
  selector_s4_confirmation.py evaluate PLAN.json REPEAT_A REPEAT_B OUT.json
"""

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

import baselines as bl  # noqa: E402
import oracle_materialize as om  # noqa: E402

WORK = TOOLS.parent
PLAN_SCHEMA = "delsk.chunkshift-s4-confirm.plan.v1"
MEASUREMENT_SCHEMA = "delsk.chunkshift-s4.measurement.v1"
SELECTION_SCHEMA = "delsk.chunkshift-s4-confirm.selection.v1"
COST_SCHEMA = "delsk.chunkshift-s4-confirm.rust-cost.v1"
TIMING_SCHEMA = "delsk.chunkshift-s4-confirm.timing.v1"
RUN_SCHEMA = "delsk.chunkshift-s4-confirm.run.v1"
RESULT_SCHEMA = "delsk.chunkshift-s4-confirm.result.v1"

CONSUMER_SHA = "74bb301b6d8ecc52cf0bc0e00d86fa174093d91b"
CANDIDATE_LOCK_SHA256 = "cb16d53b164ff393187e0115bdf31c52ac717a5172fb1e91889b5988ac019d2e"
COVERAGE_SHA256 = "fff71554f28fea2b1628ac9f430e4d542f0147e30bcdc43e64887265f6cade5c"
CORPUS_LOCK_SHA256 = "e5c288256bed284572a9f111186411517b4c73d097d13aea4cf48e2fb9f6fffa"
EXPECTED_TARGETS = 9
EXPECTED_PAIRS = 106
K = 2
ROUND_ORDERS = ("P-D", "D-P", "P-D", "D-P", "P-D", "D-P", "P-D")


class ConfirmError(Exception):
    pass


def check(ok, message):
    if not ok:
        raise ConfirmError(message)


def _hex(value, n):
    return isinstance(value, str) and len(value) == n and all(c in "0123456789abcdef" for c in value)


def _evaluation_universe():
    candidate, corpus, _, _ = om.load_natural()
    check(candidate["corpus_lock_sha256"] == CORPUS_LOCK_SHA256, "corpus lock drift")
    occurrences = {o["occurrence_id"]: o for o in corpus["occurrences"]}
    source_plan = json.loads((WORK / "corpus/source-plan.json").read_text(encoding="utf-8"))
    ordinal = {
        release["release_id"]: release["ordinal"]
        for family in source_plan["families"]
        for release in family["releases"]
    }

    def meta(occ):
        prov = occ["provenance"]
        return {
            "object_id": occ["object_id"],
            "bytes": occ["bytes"],
            "path": prov.get("member_path"),
            "offset": prov.get("offset"),
            "line": occ["family_id"],
            "version_rank": ordinal[occ["source_id"]],
        }

    rows = []
    pairs = 0
    for query in candidate["queries"]:
        target_occ = occurrences[query["target"]]
        if query["status"] != "near_duplicate" or target_occ["split"] != "evaluation":
            continue
        check(target_occ["family_id"] == "bzip2", "evaluation split family drift")
        bases = [meta(occurrences[b["representative"]]) for b in query["bases"]]
        check([b["object_id"] for b in bases] == [b["object_id"] for b in query["bases"]],
              "candidate representative drift")
        q = {
            "target_occurrence_id": query["target"],
            "family_id": target_occ["family_id"],
            "track": target_occ["track"],
            "target": meta(target_occ),
            "bases": bases,
            "previous1": bl.rank_previous_version({"target": meta(target_occ), "bases": bases})[:1],
            "size1": bl.rank_size_closest({"target": meta(target_occ), "bases": bases})[:1],
        }
        rows.append(q)
        pairs += len(bases)

    rows.sort(key=lambda q: q["target_occurrence_id"])
    check(len(rows) == EXPECTED_TARGETS, f"evaluation target count drift: {len(rows)}")
    check(pairs == EXPECTED_PAIRS, f"evaluation pair count drift: {pairs}")
    check({q["family_id"] for q in rows} == {"bzip2"}, "evaluation family set drift")
    return rows


def build_plan(protocol_authority):
    check(_hex(protocol_authority, 40), "invalid protocol authority")
    targets = _evaluation_universe()
    return {
        "schema": PLAN_SCHEMA,
        "status": "PREREGISTERED_NOT_RUN",
        "protocol_authority": protocol_authority,
        "consumer_commit": CONSUMER_SHA,
        "candidate_lock_sha256": CANDIDATE_LOCK_SHA256,
        "coverage_sha256": COVERAGE_SHA256,
        "corpus_lock_sha256": CORPUS_LOCK_SHA256,
        "split": "evaluation",
        "family": "bzip2",
        "k": K,
        "abstention_level": 0,
        "expected_targets": EXPECTED_TARGETS,
        "expected_base_pairs": EXPECTED_PAIRS,
        "round_orders": list(ROUND_ORDERS),
        "targets": targets,
    }


def _json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line]


def _repeat_paths(root):
    root = Path(root)
    return {
        "measurements": root / "measurements.jsonl",
        "selection": root / "selection.json",
        "cost": root / "rust-cost.json",
        "timing": root / "timing.json",
        "run": root / "run.json",
    }


def _expected_keys(plan):
    out = set()
    for target in plan["targets"]:
        tid = target["target_occurrence_id"]
        out.add((tid, None))
        out.update((tid, b["object_id"]) for b in target["bases"])
    return out


def _measurement_map(plan, path):
    rows = _jsonl(path)
    out = {}
    targets = {t["target_occurrence_id"]: t for t in plan["targets"]}
    for row in rows:
        check(row.get("schema") == MEASUREMENT_SCHEMA, "foreign measurement schema")
        key = (row.get("target_occurrence_id"), row.get("base_object_id"))
        check(key not in out, f"duplicate measurement: {key}")
        check(key[0] in targets, f"foreign target: {key[0]}")
        target = targets[key[0]]
        check(row.get("target_object_id") == target["target"]["object_id"], f"target object drift: {key[0]}")
        check(row.get("chunkshift_commit") == CONSUMER_SHA, f"consumer drift: {key}")
        check(row.get("status") == "ok", f"measurement failure: {key}")
        check(row.get("create_exit_code") == 0 and row.get("apply_exit_code") == 0, f"CLI failure: {key}")
        check(row.get("applied_sha256") == target["target"]["object_id"], f"reconstruction mismatch: {key}")
        check(isinstance(row.get("patch_bytes"), int) and row["patch_bytes"] > 0, f"bad patch bytes: {key}")
        out[key] = row
    check(set(out) == _expected_keys(plan), "measurement pair universe is incomplete or contains extras")
    return out


def _selection(plan, path):
    doc = _json(path)
    check(doc.get("schema") == SELECTION_SCHEMA, "foreign selection schema")
    check(doc.get("selector") == "delsk.simple-selector.v1" and doc.get("k") == K, "selector identity drift")
    rows = doc.get("targets")
    check(isinstance(rows, list) and len(rows) == EXPECTED_TARGETS, "selection target count drift")
    by_plan = {t["target_occurrence_id"]: t for t in plan["targets"]}
    out = {}
    for row in rows:
        tid = row.get("target_occurrence_id")
        check(tid in by_plan and tid not in out, "selection target mismatch")
        rust = row.get("rust_k2")
        python = row.get("python_k2")
        check(rust == python, f"Rust/Python parity failure: {tid}")
        check(isinstance(rust, list) and len(rust) == min(K, len(by_plan[tid]["bases"])), f"K2 width drift: {tid}")
        universe = {b["object_id"] for b in by_plan[tid]["bases"]}
        check(len(rust) == len(set(rust)) and set(rust) <= universe, f"K2 outside C_t: {tid}")
        out[tid] = rust
    check(set(out) == set(by_plan), "selection population incomplete")
    return out


def _lane_rows(plan, measured, selected, lane):
    rows = []
    for target in plan["targets"]:
        tid = target["target_occurrence_id"]
        if lane == "previous1":
            bases = target["previous1"]
        elif lane == "size1":
            bases = target["size1"]
        elif lane == "delsk2":
            bases = selected[tid]
        elif lane == "exhaustive":
            bases = [b["object_id"] for b in target["bases"]]
        else:
            raise ConfirmError(f"unknown lane {lane}")
        candidates = [measured[(tid, None)], *[measured[(tid, base)] for base in bases]]
        best = min(candidates, key=lambda row: (row["patch_bytes"], row.get("base_object_id") or ""))
        rows.append({
            "target_occurrence_id": tid,
            "track": target["track"],
            "patch_bytes": best["patch_bytes"],
            "base_object_id": best.get("base_object_id"),
            "calls": len(candidates),
        })
    return rows


def _aggregate(rows, standalone, oracle):
    b = sum(r["patch_bytes"] for r in rows)
    s = sum(r["patch_bytes"] for r in standalone)
    o = sum(r["patch_bytes"] for r in oracle)
    den = s - o
    return {
        "targets": len(rows),
        "physical_patch_bytes": b,
        "standalone_patch_bytes": s,
        "oracle_patch_bytes": o,
        "oracle_savings_bytes": den,
        "captured_savings_bytes": s - b,
        "savings_capture": None if den == 0 else (s - b) / den,
        "calls": sum(r["calls"] for r in rows),
    }


def _cost(path):
    doc = _json(path)
    check(doc.get("schema") == COST_SCHEMA, "foreign Rust cost schema")
    objects = doc.get("objects")
    scanned = doc.get("object_bytes_scanned")
    descriptor_bytes = doc.get("descriptor_bytes")
    index_bytes = doc.get("index_bytes")
    wall = doc.get("descriptor_wall_ns")
    lat = doc.get("query_ns")
    check(all(isinstance(x, int) and x > 0 for x in (objects, scanned, wall)), "invalid Rust cost counters")
    check(descriptor_bytes == objects * 64, "descriptor width drift")
    check(isinstance(index_bytes, int) and 0 <= index_bytes <= objects * 64, "index bytes/object > 64")
    check(isinstance(lat, list) and len(lat) == EXPECTED_TARGETS and all(isinstance(x, int) and x >= 0 for x in lat),
          "query latency vector drift")
    throughput_mib_s = scanned / (wall / 1_000_000_000) / (1024 * 1024)
    ordered = sorted(lat)
    p95 = ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)] / 1000
    return {
        "objects": objects,
        "object_bytes_scanned": scanned,
        "descriptor_bytes": descriptor_bytes,
        "index_bytes": index_bytes,
        "descriptor_throughput_mib_s": throughput_mib_s,
        "query_p95_us": p95,
        "eligible": throughput_mib_s >= 250.0 and p95 <= 50.0,
    }


def _timing(path):
    doc = _json(path)
    check(doc.get("schema") == TIMING_SCHEMA, "foreign timing schema")
    rounds = doc.get("rounds")
    check(isinstance(rounds, list) and len(rounds) == 7, "paired timing requires seven rounds")
    wall, cpu, apply = [], [], []
    for i, row in enumerate(rounds):
        check(row.get("order") == ROUND_ORDERS[i], f"round order drift: {i}")
        p = row.get("previous1")
        d = row.get("delsk2")
        check(isinstance(p, dict) and isinstance(d, dict), f"timing lane missing: {i}")
        for lane in (p, d):
            for field in ("create_wall_ns", "create_cpu_ns", "apply_wall_ns"):
                check(isinstance(lane.get(field), int) and lane[field] > 0, f"invalid timing {field}: {i}")
        wall.append(d["create_wall_ns"] / p["create_wall_ns"])
        cpu.append(d["create_cpu_ns"] / p["create_cpu_ns"])
        apply.append(d["apply_wall_ns"] / p["apply_wall_ns"])
    out = {
        "wall_ratio_median": statistics.median(wall),
        "cpu_ratio_median": statistics.median(cpu),
        "apply_ratio_median": statistics.median(apply),
    }
    out["eligible"] = (
        out["wall_ratio_median"] <= 1.80
        and out["cpu_ratio_median"] <= 1.80
        and out["apply_ratio_median"] <= 1.10
    )
    return out


def _repeat(plan, root, role):
    paths = _repeat_paths(root)
    check(all(path.is_file() for path in paths.values()), f"repeat {role}: evidence file missing")
    run = _json(paths["run"])
    check(run.get("schema") == RUN_SCHEMA and run.get("repeat") == role, f"repeat {role}: run identity drift")
    check(run.get("protocol_authority") == plan["protocol_authority"], f"repeat {role}: protocol drift")
    check(run.get("chunkshift_commit") == CONSUMER_SHA, f"repeat {role}: consumer drift")
    check(run.get("run_attempt") == 1 and run.get("event") == "workflow_dispatch", f"repeat {role}: not first dispatch attempt")
    check(run.get("status") == "completed" and run.get("conclusion") == "success", f"repeat {role}: run not successful")
    check(isinstance(run.get("run_id"), int) and run["run_id"] > 0, f"repeat {role}: bad run id")
    check(isinstance(run.get("runner_name"), str) and run["runner_name"], f"repeat {role}: runner missing")

    measured = _measurement_map(plan, paths["measurements"])
    selected = _selection(plan, paths["selection"])
    standalone = []
    for target in plan["targets"]:
        row = measured[(target["target_occurrence_id"], None)]
        standalone.append({
            "target_occurrence_id": target["target_occurrence_id"],
            "track": target["track"],
            "patch_bytes": row["patch_bytes"],
            "base_object_id": None,
            "calls": 1,
        })
    lanes = {name: _lane_rows(plan, measured, selected, name) for name in ("previous1", "size1", "delsk2", "exhaustive")}
    agg = {name: _aggregate(rows, standalone, lanes["exhaustive"]) for name, rows in lanes.items()}
    d = agg["delsk2"]
    p = agg["previous1"]
    quality_ok = (
        d["oracle_savings_bytes"] > 0
        and d["captured_savings_bytes"] * 100 >= d["oracle_savings_bytes"] * 98
        and d["physical_patch_bytes"] * 1000 <= p["physical_patch_bytes"] * 995
        and d["calls"] * 2 <= p["calls"] * 3
    )
    cost = _cost(paths["cost"])
    timing = _timing(paths["timing"])
    pair_signature = [
        [tid, base or "", row["patch_bytes"], row["patch_file_digest"], row["applied_sha256"]]
        for (tid, base), row in sorted(measured.items(), key=lambda item: (item[0][0], item[0][1] or ""))
    ]
    selection_signature = [[tid, *selected[tid]] for tid in sorted(selected)]
    return {
        "run": run,
        "aggregate": agg,
        "quality_ok": quality_ok,
        "rust_cost": cost,
        "timing": timing,
        "eligible": quality_ok and cost["eligible"] and timing["eligible"],
        "pair_signature": pair_signature,
        "selection_signature": selection_signature,
    }


def evaluate(plan, a_root, b_root):
    check(plan.get("schema") == PLAN_SCHEMA, "foreign confirmation plan")
    check(plan == build_plan(plan.get("protocol_authority")), "confirmation plan differs from sealed metadata")
    a = _repeat(plan, a_root, "A")
    b = _repeat(plan, b_root, "B")

    check(a["run"]["run_id"] != b["run"]["run_id"], "repeats share one run id")
    check(a["run"]["runner_name"] != b["run"]["runner_name"], "repeats share one runner name")
    check(a["pair_signature"] == b["pair_signature"], "repeat quality tables differ")
    check(a["selection_signature"] == b["selection_signature"], "repeat K2 selections differ")

    verdict = "G5_SCOPED_PASS_K2" if a["eligible"] and b["eligible"] else "G5_REJECT_K2"
    return {
        "schema": RESULT_SCHEMA,
        "verdict": verdict,
        "scope": "pinned ChunkShift + sealed E1 bzip2 modeled evaluation split",
        "candidate": "delsk.simple-selector.v1/K2",
        "repeat_a": {k: a[k] for k in ("aggregate", "quality_ok", "rust_cost", "timing", "eligible")},
        "repeat_b": {k: b[k] for k in ("aggregate", "quality_ok", "rust_cost", "timing", "eligible")},
    }


def parser():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("out")
    plan.add_argument("--protocol-authority", required=True)
    ev = sub.add_parser("evaluate")
    ev.add_argument("plan")
    ev.add_argument("repeat_a")
    ev.add_argument("repeat_b")
    ev.add_argument("out")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    if args.command == "plan":
        Path(args.out).write_text(json.dumps(build_plan(args.protocol_authority), indent=2, sort_keys=True) + "\n",
                                  encoding="utf-8")
        return 0
    plan = _json(args.plan)
    try:
        result = evaluate(plan, args.repeat_a, args.repeat_b)
    except ConfirmError as exc:
        result = {"schema": RESULT_SCHEMA, "verdict": "INVALID", "reason": str(exc)}
    Path(args.out).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(result["verdict"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
