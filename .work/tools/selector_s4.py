"""S4 preregistered ChunkShift consumer plan and evaluator.

No ChunkShift process is executed here. This module freezes which Delsk bases a
future runner must try and how retained ChunkShift measurements are reduced to
one of the S4 development-screen verdicts in .work/selector/s4.md.

    selector_s4.py plan OUT.json
    selector_s4.py evaluate PLAN.json MEASUREMENTS.jsonl OUT.json
"""

import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

import baselines as bl  # noqa: E402
import simple_selector as ss  # noqa: E402
import x0_screen as xs  # noqa: E402

WORK = TOOLS.parent
CONSUMER_PIN = WORK / "selector" / "chunkshift-consumer.json"
PLAN_SCHEMA = "delsk.chunkshift-s4.plan.v1"
MEASUREMENT_SCHEMA = "delsk.chunkshift-s4.measurement.v1"
RESULT_SCHEMA = "delsk.chunkshift-s4.result.v1"
LANES = ("previous1", "size1", "delsk2", "delsk4", "exhaustive")
MEASUREMENT_KEYS = {
    "schema", "target_occurrence_id", "target_object_id", "base_object_id",
    "chunkshift_commit", "status", "error_class", "patch_bytes",
    "create_wall_ns", "create_cpu_ns", "apply_wall_ns", "apply_cpu_ns",
    "create_exit_code", "apply_exit_code", "target_manifest_id",
    "base_manifest_id", "patch_file_digest", "applied_sha256",
}
MEASUREMENT_STATUSES = {"ok", "create_failed", "apply_failed", "verify_failed"}


class S4Error(Exception):
    pass


def check(ok, message):
    if not ok:
        raise S4Error(message)


def _ranking_map(path):
    rows = bl.jsonl(path)
    out = {}
    for row in rows:
        key = (row["target_occurrence_id"], row["method"], row.get("budget_bytes"))
        check(key not in out, f"duplicate ranking: {key}")
        out[key] = row["ranking"]
    return out


def _delsk_map(items):
    out = {}
    for item in items:
        tid = item["target_occurrence_id"]
        check(tid not in out, f"duplicate Delsk order: {tid}")
        out[tid] = item["order"]
    return out


def _lane_bases(q, delsk_order, previous_order, size_order):
    universe = [b["object_id"] for b in q["bases"]]
    expected = sorted(universe)
    for name, order in (
        ("delsk", delsk_order),
        ("previous", previous_order),
        ("size", size_order),
    ):
        check(sorted(order) == expected and len(order) == len(set(order)),
              f"{name} ranking is not exactly C_t: {q['target_occurrence_id']}")
    return {
        "previous1": previous_order[:1],
        "size1": size_order[:1],
        "delsk2": delsk_order[:2],
        "delsk4": delsk_order[:4],
        "exhaustive": delsk_order,
    }


def _pilot_rows():
    queries = {q["target_occurrence_id"]: q for q in bl.natural_universe()}
    items, _ = ss.pilot_population()
    delsk = _delsk_map(items)
    rankings = _ranking_map(ss.PILOT_RANKINGS)
    out = []
    for tid, q in sorted(queries.items()):
        check(tid in delsk, f"pilot Delsk order missing: {tid}")
        previous = rankings[(tid, "previous_version", None)]
        size = rankings[(tid, "size_closest", None)]
        out.append({
            "population": f"pilot-{q['split']}",
            "family_id": q["family_id"],
            "track": q["track"],
            "target_occurrence_id": tid,
            "target_object_id": q["target"]["object_id"],
            "target_bytes": q["target"]["bytes"],
            "lanes": _lane_bases(q, delsk[tid], previous, size),
        })
    return out


def _x0_rows():
    corpus, candidates = xs.load(ss.X0_RUN)
    queries = {q["target_occurrence_id"]: q for q in xs.queries_for_ranking(corpus, candidates)}
    items, _ = ss.x0_population()
    delsk = _delsk_map(items)
    rankings = _ranking_map(ss.X0_RUN / "rankings.jsonl")
    out = []
    for tid, q in sorted(queries.items()):
        check(tid in delsk, f"X0 Delsk order missing: {tid}")
        previous = rankings[(tid, "version_previous", None)]
        size = rankings[(tid, "size_closest", None)]
        out.append({
            "population": f"x0-{q['cell']}",
            "family_id": q["family_id"],
            "track": q["track"],
            "target_occurrence_id": tid,
            "target_object_id": q["target"]["object_id"],
            "target_bytes": q["target"]["bytes"],
            "lanes": _lane_bases(q, delsk[tid], previous, size),
        })
    return out


def build_plan():
    pin = json.loads(CONSUMER_PIN.read_text(encoding="utf-8"))
    check(pin.get("schema") == "delsk.chunkshift-consumer-pin.v1", "foreign ChunkShift consumer pin")
    check(pin.get("candidate_unit") == "one prior base object from the frozen Delsk C_t",
          "S4 consumer pin changed candidate unit")
    check(pin.get("internal_chunkshift_candidate_policy") == "CspEncoderPolicy.Default",
          "S4 consumer pin changed the internal ChunkShift policy")
    rows = sorted(_pilot_rows() + _x0_rows(), key=lambda r: r["target_occurrence_id"])
    ids = [r["target_occurrence_id"] for r in rows]
    check(len(ids) == len(set(ids)), "duplicate target occurrence across S4 populations")
    check(rows, "empty S4 population")
    return {
        "schema": PLAN_SCHEMA,
        "status": "PREREGISTERED_NOT_RUN",
        "consumer": {
            "repository": pin["repository"],
            "commit": pin["commit"],
            "candidate_unit": pin["candidate_unit"],
            "internal_chunkshift_candidate_policy": pin["internal_chunkshift_candidate_policy"],
        },
        "selector": ss.SPEC,
        "s3_abstention_level": 0,
        "lanes": list(LANES),
        "targets": rows,
    }


def _is_hex(value, length):
    return (
        isinstance(value, str) and len(value) == length
        and all(ch in "0123456789abcdef" for ch in value)
    )


def _measurements(path):
    out = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        row = json.loads(line)
        check(set(row) == MEASUREMENT_KEYS, "S4 measurement has missing or unknown fields")
        check(row["schema"] == MEASUREMENT_SCHEMA, "foreign S4 measurement schema")
        check(row["status"] in MEASUREMENT_STATUSES, "foreign S4 measurement status")
        check(_is_hex(row["target_object_id"], 64), "invalid target object id")
        check(
            row["base_object_id"] is None or _is_hex(row["base_object_id"], 64),
            "invalid base object id",
        )
        check(_is_hex(row["chunkshift_commit"], 40), "invalid ChunkShift commit")
        check(isinstance(row["target_manifest_id"], str) and row["target_manifest_id"],
              "invalid target manifest id")
        check(
            (row["base_object_id"] is None and row["base_manifest_id"] is None)
            or (row["base_object_id"] is not None
                and isinstance(row["base_manifest_id"], str)
                and bool(row["base_manifest_id"])),
            "base manifest id does not match base-object presence",
        )
        for field in ("create_wall_ns", "create_cpu_ns", "apply_wall_ns", "apply_cpu_ns"):
            check(isinstance(row[field], int) and row[field] >= 0, f"invalid {field}")
        check(row["create_exit_code"] is None or isinstance(row["create_exit_code"], int),
              "invalid create exit code")
        check(row["apply_exit_code"] is None or isinstance(row["apply_exit_code"], int),
              "invalid apply exit code")
        check(row["error_class"] is None or isinstance(row["error_class"], str),
              "invalid error class")

        if row["status"] == "ok":
            check(isinstance(row["patch_bytes"], int) and row["patch_bytes"] > 0,
                  "successful S4 measurement has invalid patch bytes")
            check(row["create_exit_code"] == 0 and row["apply_exit_code"] == 0,
                  "successful S4 measurement has non-zero exit code")
            check(row["error_class"] is None, "successful S4 measurement carries an error")
            check(_is_hex(row["patch_file_digest"], 64), "invalid patch file digest")
            check(_is_hex(row["applied_sha256"], 64), "invalid applied SHA-256")
        else:
            check(row["error_class"], "failed S4 measurement must retain an error class")
            check(row["patch_bytes"] is None or (isinstance(row["patch_bytes"], int) and row["patch_bytes"] > 0),
                  "failed S4 measurement has invalid patch bytes")
            check(row["patch_file_digest"] is None or _is_hex(row["patch_file_digest"], 64),
                  "failed S4 measurement has invalid patch digest")
            check(row["applied_sha256"] is None or _is_hex(row["applied_sha256"], 64),
                  "failed S4 measurement has invalid applied SHA-256")

        key = (row["target_occurrence_id"], row["base_object_id"])
        check(key not in out, f"duplicate S4 measurement: {key}")
        out[key] = row
    return out


def _expected_keys(plan):
    keys = set()
    for target in plan["targets"]:
        tid = target["target_occurrence_id"]
        keys.add((tid, None))
        for oid in target["lanes"]["exhaustive"]:
            keys.add((tid, oid))
    return keys


def _lane_rows(plan, measured, lane):
    rows = []
    for target in plan["targets"]:
        tid = target["target_occurrence_id"]
        bases = target["lanes"][lane]
        candidates = [measured[(tid, None)], *[measured[(tid, b)] for b in bases]]
        best = min(candidates, key=lambda r: (r["patch_bytes"], r.get("base_object_id") or ""))
        rows.append({
            "target_occurrence_id": tid,
            "population": target["population"],
            "patch_bytes": best["patch_bytes"],
            "selected_base_object_id": best.get("base_object_id"),
            "calls": len(candidates),
            "create_wall_ns": sum(r["create_wall_ns"] for r in candidates),
            "create_cpu_ns": sum(r["create_cpu_ns"] for r in candidates),
            "apply_wall_ns": sum(r["apply_wall_ns"] for r in candidates),
            "apply_cpu_ns": sum(r["apply_cpu_ns"] for r in candidates),
        })
    return rows


def _aggregate(rows, standalone, oracle):
    b = sum(r["patch_bytes"] for r in rows)
    s = sum(r["patch_bytes"] for r in standalone)
    o = sum(r["patch_bytes"] for r in oracle)
    denominator = s - o
    savings = s - b
    return {
        "targets": len(rows),
        "physical_patch_bytes": b,
        "standalone_patch_bytes": s,
        "oracle_patch_bytes": o,
        "oracle_savings_bytes": denominator,
        "captured_savings_bytes": savings,
        "savings_capture": None if denominator == 0 else savings / denominator,
        "calls": sum(r["calls"] for r in rows),
        "create_wall_ns": sum(r["create_wall_ns"] for r in rows),
        "create_cpu_ns": sum(r["create_cpu_ns"] for r in rows),
        "apply_wall_ns": sum(r["apply_wall_ns"] for r in rows),
        "apply_cpu_ns": sum(r["apply_cpu_ns"] for r in rows),
    }


def _population_aggregates(lane_rows, standalone, oracle):
    populations = sorted({r["population"] for r in lane_rows})
    out = {}
    for pop in populations:
        lr = [r for r in lane_rows if r["population"] == pop]
        sr = [r for r in standalone if r["population"] == pop]
        orows = [r for r in oracle if r["population"] == pop]
        out[pop] = _aggregate(lr, sr, orows)
    return out


def _eligible(candidate, best_control, exhaustive, cand_pop, control_pop):
    den = candidate["oracle_savings_bytes"]
    if den <= 0:
        return False, ["zero-oracle-savings"]

    reasons = []
    # SC >= .98, exact integer boundary.
    if candidate["captured_savings_bytes"] * 100 < den * 98:
        reasons.append("savings-capture<0.98")

    # No worse than +0.5% AND at least 0.5% better than the best one-base control.
    if candidate["physical_patch_bytes"] * 1000 > best_control["physical_patch_bytes"] * 1005:
        reasons.append("bytes>control+0.5%")
    if candidate["physical_patch_bytes"] * 1000 > best_control["physical_patch_bytes"] * 995:
        reasons.append("bytes-improvement<0.5%")

    if exhaustive["calls"] < candidate["calls"] * 4:
        reasons.append("call-reduction<4x")

    for pop, c in cand_pop.items():
        bc = control_pop[pop]
        pden = c["oracle_savings_bytes"]
        if pden <= 0:
            continue
        # Same denominator for all lanes in a population:
        # SC(candidate) + .02 >= SC(control).
        if c["captured_savings_bytes"] * 50 + pden < bc["captured_savings_bytes"] * 50:
            reasons.append(f"population-regression>2pp:{pop}")

    return not reasons, reasons


def evaluate(plan, measurements):
    check(plan.get("schema") == PLAN_SCHEMA, "foreign S4 plan schema")
    check(plan.get("s3_abstention_level") == 0, "S4 plan violates S3 L=0")
    check(tuple(plan.get("lanes", ())) == LANES, "S4 lane set changed")
    check(plan == build_plan(), "S4 plan differs from the preregistered plan rebuilt from retained inputs")

    measured = _measurements(measurements)
    expected = _expected_keys(plan)
    check(set(measured) == expected, "S4 measurements differ from the preregistered target/base universe")

    targets = {t["target_occurrence_id"]: t for t in plan["targets"]}
    consumer_commit = plan["consumer"]["commit"]
    for (tid, _), row in measured.items():
        check(row["target_object_id"] == targets[tid]["target_object_id"],
              f"measurement binds another target object: {tid}")
        check(row["chunkshift_commit"] == consumer_commit,
              f"measurement binds another ChunkShift commit: {tid}")

    failed = [
        {
            "target_occurrence_id": tid,
            "base_object_id": base,
            "status": row["status"],
            "error_class": row["error_class"],
        }
        for (tid, base), row in measured.items()
        if row["status"] != "ok" or row["applied_sha256"] != row["target_object_id"]
    ]
    if failed:
        return {
            "schema": RESULT_SCHEMA,
            "verdict": "INVALID",
            "reason": "measurement-or-reconstruction-failure",
            "failures": sorted(
                failed,
                key=lambda item: (
                    item["target_occurrence_id"],
                    item["base_object_id"] or "",
                ),
            ),
        }

    rows = {lane: _lane_rows(plan, measured, lane) for lane in LANES}
    standalone = []
    for target in plan["targets"]:
        r = measured[(target["target_occurrence_id"], None)]
        standalone.append({
            "target_occurrence_id": target["target_occurrence_id"],
            "population": target["population"],
            "patch_bytes": r["patch_bytes"],
            "selected_base_object_id": None,
            "calls": 1,
            "create_wall_ns": r["create_wall_ns"],
            "create_cpu_ns": r["create_cpu_ns"],
            "apply_wall_ns": r["apply_wall_ns"],
            "apply_cpu_ns": r["apply_cpu_ns"],
        })

    agg = {}
    pops = {}
    oracle_rows = rows["exhaustive"]
    for lane in LANES:
        agg[lane] = _aggregate(rows[lane], standalone, oracle_rows)
        pops[lane] = _population_aggregates(rows[lane], standalone, oracle_rows)

    best_control_name = min(
        ("previous1", "size1"),
        key=lambda lane: (agg[lane]["physical_patch_bytes"], lane),
    )
    best_control = agg[best_control_name]
    control_pop = {}
    for pop in pops["previous1"]:
        control_pop[pop] = max(
            (pops["previous1"][pop], pops["size1"][pop]),
            key=lambda a: (-1 if a["savings_capture"] is None else a["savings_capture"],
                           -a["physical_patch_bytes"]),
        )

    eligibility = {}
    winner = None
    for lane in ("delsk2", "delsk4"):
        ok, reasons = _eligible(
            agg[lane],
            best_control,
            agg["exhaustive"],
            pops[lane],
            control_pop,
        )
        eligibility[lane] = {"eligible": ok, "reasons": reasons}
        if winner is None and ok:
            winner = lane

    verdict = {
        "delsk2": "OPEN_CONFIRMATION_K2",
        "delsk4": "OPEN_CONFIRMATION_K4",
        None: "NO_SYSTEM_SIGNAL",
    }[winner]

    return {
        "schema": RESULT_SCHEMA,
        "verdict": verdict,
        "confirmation_lane": winner,
        "best_one_base_control": best_control_name,
        "aggregate": agg,
        "populations": pops,
        "eligibility": eligibility,
    }


def main(argv):
    if argv[:1] == ["plan"] and len(argv) == 2:
        Path(argv[1]).write_text(
            json.dumps(build_plan(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return 0
    if argv[:1] == ["evaluate"] and len(argv) == 4:
        plan = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        result = evaluate(plan, argv[2])
        Path(argv[3]).write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(result["verdict"])
        return 0
    raise SystemExit("usage: selector_s4.py plan OUT | evaluate PLAN MEASUREMENTS OUT")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
