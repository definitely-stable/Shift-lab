"""DELSK-002 E1 independent verifier of delsk.candidate.lock.v2 (construction-spec §7.2).

Does not import candidates.py and shares no selection, category or schedule code
with it (A09). From manifests.py only the strict loader and the canonical file
serializer are used; hashes, intervals, member rules, splits and every E rule are
re-derived here with a deliberately different, slower structure (full-U scans,
flat round list). Two layers:

1. source -> U: the exact expected position set from source-lock retained members,
   policy and plan, compared with the corpus lock as sets plus bindings and bytes;
2. U -> queries: T_all, identity, A02 traversal and every full category pool,
   compared with the lock (all fields and canonical bytes) and the builder evidence.

    verify(inputs, lock_bytes, selection) -> report (status "ok" only if every check passed)
    derive(world, params)                 -> independent queries + selection evidence
"""

import fnmatch
import gzip
import hashlib
import json
import datetime as dt

from manifests import canonical_bytes, loads_strict

# The adopted E0 freeze record is the authority for every expected input hash.
E0_FREEZE = (".work/corpus/e0/freeze.json", "95394c10f4b3711641740873b832a9b6cdc7555fba6af5bd10462c602c51b19b")
PATHS = {"plan": ".work/corpus/source-plan.json", "policy": ".work/corpus/selection-policy.json",
         "source_lock": ".work/corpus/pilot-v1/source-lock.json",
         "corpus_lock": ".work/corpus/pilot-v1/corpus-lock.json.gz",
         "acquisition_freeze": ".work/corpus/pilot-v1/freeze.json",
         "ancestry_audit": ".work/corpus/e0/ancestry-audit.json",
         "historical_bytes": ".work/corpus/e0/historical-bytes.json",
         "construction_spec": ".work/corpus/e0/construction-spec.md", "protocol": ".work/protocol.md"}
CATS = ("same_path_historical", "same_family_decoy", "foreign_family_decoy")


def hc(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def interval(time):
    """Independent copy of the D time rule: date -> [day-14h, day+36h]; timestamp -> [s, s]."""
    value = (time or {}).get("value")
    if value is None:
        return None
    if len(value) == 10:
        day = int(dt.datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc).timestamp())
        return [day - 50400, day + 129600]
    moment = dt.datetime.fromisoformat(value)
    if moment.tzinfo is None or moment.microsecond:
        raise ValueError(f"bad timestamp {value}")
    return [int(moment.timestamp())] * 2


# --- layer 1: source -> U --------------------------------------------------------

def split_assignment(plan, policy):
    families = sorted(f["family_id"] for f in plan["families"])
    comp = {f: {f} for f in families}
    for edge in plan.get("ancestry_edges", []):
        if edge["resolution"] == "merge":
            merged = comp[edge["a"]] | comp[edge["b"]]
            for f in merged:
                comp[f] = merged
    components = sorted({tuple(sorted(c)) for c in comp.values()})
    if len(components) != sum(n for _, n in policy["splits"]["counts"]):
        raise ValueError("component count differs from the policy split counts")
    ranked = sorted(components, key=lambda c: hc(["split", policy["seed"], c[0]]))
    split, i = {}, 0
    for name, n in policy["splits"]["counts"]:
        for c in ranked[i:i + n]:
            split.update({f: name for f in c})
        i += n
    return components, split


def check_source_closure(plan, policy, source_lock, lock):
    """Errors of the exact source -> U closure; counts only as diagnostics."""
    errors = []
    releases = {r["release_id"]: f for f in plan["families"] for r in f["releases"]}
    components, split = split_assignment(plan, policy)
    if [{"families": list(c), "split": split[c[0]]} for c in components] != lock["components"]:
        errors.append("components/splits differ from an independent assignment")
    tracks = {t["id"]: t for t in policy["tracks"]}
    rules = policy["member_rules"]
    zlib = lock["toolchain"]["zlib_runtime"]
    expected = {}
    if sorted(s["source_id"] for s in source_lock["sources"]) != sorted(releases):
        errors.append("source lock does not cover exactly the planned releases")
    for s in source_lock["sources"]:
        family = releases.get(s["source_id"])
        if family is None or family["family_id"] != s["family_id"]:
            errors.append(f"source {s['source_id']}: not a planned release of its family")
            continue
        globs = rules["global_exclude_globs"] + [g["glob"] for g in family.get("exclude_globs", [])]
        best = {}
        for member in s["retained"]:
            path = member["path"]
            if not path.endswith(tuple(rules["include_suffixes"])) or any(fnmatch.fnmatchcase(path, g) for g in globs):
                errors.append(f"source {s['source_id']}: retained member {path} violates member rules")
            for track in tracks.values():
                unit = track["unit_bytes"]
                if unit:
                    for offset in range(0, member["bytes"] - unit + 1, unit):
                        expected[s["source_id"], track["id"], path, offset, unit, hc({"unit_bytes": unit})] = \
                            {"bytes": unit, "parent": (member["object_id"], member["bytes"]), "stratum": None}
            stratum = next((x["id"] for x in policy["file_strata"]
                            if x["min_bytes"] <= member["bytes"] < x["max_bytes"]), None)
            if stratum is not None:
                key = (hc(["member", policy["seed"], s["family_id"], path]), path)
                if stratum not in best or key < best[stratum][0]:
                    best[stratum] = (key, member)
        for stratum, (_, member) in best.items():
            expected[s["source_id"], "file", member["path"], None, None, hc({})] = \
                {"bytes": member["bytes"], "object": member["object_id"], "parent": None, "stratum": stratum}
        for track in tracks.values():
            if track["transform"] == "canonical_tar_v1":
                expected[s["source_id"], track["id"], None, None, None, hc({})] = {"parent": None, "stratum": None}
            elif track["transform"] == "canonical_tar_gzip_v1":
                options = {"compresslevel": track["compresslevel"], "zlib_runtime": zlib}
                expected[s["source_id"], track["id"], None, None, None, hc(options)] = {"parent": None, "stratum": None}
    actual, total, object_splits = {}, 0, {}
    for o in lock["occurrences"]:
        p = o["provenance"]
        key = (o["source_id"], o["track"], p["member_path"], p["offset"], p["length"], hc(p["options"]))
        if key in actual:
            errors.append(f"duplicate position {key[:4]}")
        actual[key] = o
        total += o["bytes"]
        object_splits.setdefault(o["object_id"], set()).add(o["split"])
        family = releases.get(o["source_id"])
        if o["occurrence_id"] != hc(["delsk.occurrence.v1", o["source_id"], p]):
            errors.append(f"occurrence {o['occurrence_id']}: ID is not its provenance hash")
        if family is None or o["family_id"] != family["family_id"] or o["split"] != split[family["family_id"]] \
                or tracks.get(o["track"], {}).get("transform") != p["transform"]:
            errors.append(f"occurrence {o['occurrence_id']}: family/split/transform binding wrong")
        want = expected.get(key)
        if want is None:
            continue
        parent = (o["parent_object_id"], o["parent_bytes"]) if o["parent_object_id"] else None
        if parent != want["parent"] or o["stratum"] != want["stratum"] \
                or ("bytes" in want and o["bytes"] != want["bytes"]) or ("object" in want and o["object_id"] != want["object"]):
            errors.append(f"occurrence {o['occurrence_id']}: object/parent/stratum/bytes differ from the source lock")
    missing, extra = expected.keys() - actual.keys(), actual.keys() - expected.keys()
    errors += [f"missing expected position {k[:4]}" for k in sorted(missing, key=repr)[:20]]
    errors += [f"position not derived from the source lock {k[:4]}" for k in sorted(extra, key=repr)[:20]]
    if total != lock["materialized_bytes"]:
        errors.append("materialized_bytes differs from the occurrence byte sum")
    cross = sorted(x for x, s in object_splits.items() if len(s) > 1)
    if cross != sorted(e["subject"] for e in lock["exclusions"] if e["kind"] == "object"):
        errors.append("object exclusions differ from the raw cross-split content set")
    return errors, {"expected_positions": len(expected), "actual_positions": len(actual),
                    "missing": len(missing), "extra": len(extra), "materialized_bytes": total,
                    "sources": len(source_lock["sources"]), "cross_split_objects": len(cross)}


# --- layer 2: U -> queries ---------------------------------------------------------

def derive(world, params):
    """Slow independent derivation; returns {"queries", "planned_pairs_per_codec", "selection"}."""
    src = {s["source_id"]: s for s in world["sources"]}
    occs = sorted(world["occurrences"], key=lambda o: o["occurrence_id"])
    seen = set()
    for o in occs:
        if o["occurrence_id"] in seen:
            raise ValueError(f"duplicate occurrence {o['occurrence_id']}")
        seen.add(o["occurrence_id"])
    splits = {}
    for o in occs:
        splits.setdefault(o["object_id"], set()).add(o["split"])
    dead = set()
    for e in world["exclusions"]:
        for o in occs:
            subject = {"source": o["source_id"], "object": o["object_id"], "occurrence": o["occurrence_id"],
                       "member": f"{o['source_id']}:{o['provenance']['member_path']}"}.get(e["kind"])
            if subject == e["subject"]:
                dead.add(o["occurrence_id"])
    dead |= {o["occurrence_id"] for o in occs if len(splits[o["object_id"]]) > 1}
    # I33: a license exclusion of a member or occurrence leaves its bytes inside that source's tar.
    by_id = {o["occurrence_id"]: o for o in occs}
    tainted = set()
    for e in world["exclusions"]:
        if e["reason"] == "license_blocked" and e["kind"] == "member":
            tainted.add(e["subject"].split(":", 1)[0])
        elif e["reason"] == "license_blocked" and e["kind"] == "occurrence" and e["subject"] in by_id:
            tainted.add(by_id[e["subject"]]["source_id"])
    for o in occs:
        if o["source_id"] in tainted and o["provenance"]["member_path"] is None and o["occurrence_id"] not in dead:
            raise ValueError(f"composite {o['occurrence_id']} keeps a license-excluded member of {o['source_id']}")

    def iv(o):
        return src[o["source_id"]]["availability_interval_utc_seconds"]

    def base_ok(b, t):
        return (b["occurrence_id"] not in dead and b["occurrence_id"] != t["occurrence_id"]
                and (b["split"], b["track"], hc(b["provenance"]["options"])) ==
                (t["split"], t["track"], hc(t["provenance"]["options"]))
                and iv(b) is not None and iv(b)[1] < iv(t)[0])

    T = [t for t in occs if t["occurrence_id"] not in dead and iv(t) is not None
         and src[t["source_id"]]["ordinal"] in params["release_ordinals"]]
    same_content = {}
    for o in occs:
        same_content.setdefault(o["object_id"], []).append(o)
    dup = {}
    for t in T:
        ids = sorted(b["occurrence_id"] for b in same_content[t["object_id"]] if base_ok(b, t))
        if ids:
            dup[t["occurrence_id"]] = ids[0]

    queues = {}
    for t in T:
        queues.setdefault((t["family_id"], t["track"], t["stratum"] if t["stratum"] else ""), []).append(t)
    order = sorted(queues, key=lambda g: (hc(["target-group", params["seed"], g[0], g[1], g[2]]), g))
    for g in order:
        queues[g].sort(key=lambda t: (hc(["target", params["seed"], t["occurrence_id"]]), t["occurrence_id"]))
    flat = [(r + 1, g) for r in range(max((len(q) for q in queues.values()), default=0))
            for g in order if r < len(queues[g])]

    queries, trace, near_rows, near, taken, last_round = [], [], [], 0, {g: 0 for g in order}, 0
    for rnd, g in flat:
        if near == params["max_targets"]:
            break
        t = queues[g][taken[g]]
        taken[g] += 1
        last_round = rnd
        tid = t["occurrence_id"]
        if tid in dup:
            q = {"bases": [], "candidate_count": 0, "candidate_list_sha256": hc([]), "duplicate_of": dup[tid],
                 "status": "identity_only", "target": tid}
        else:
            q, row = near_query(t, occs, base_ok, params, dead, iv)
            near_rows.append(row)
            near += 1
        queries.append(q)
        trace.append({"group": list(g), "near_count_after": near, "round": rnd, "status": q["status"], "target": tid})
    left = {g: [t["occurrence_id"] for t in queues[g][taken[g]:]] for g in order}
    return {"queries": sorted(queries, key=lambda q: q["target"]),
            "planned_pairs_per_codec": sum(q["candidate_count"] for q in queries if q["status"] == "near_duplicate"),
            "selection": {
                "near_queries": sorted(near_rows, key=lambda r: r["target"]),
                "schedule": {"group_order": [list(g) for g in order], "rounds": last_round,
                             "stop_reason": "near_quota" if near == params["max_targets"] else "exhausted",
                             "traversal": trace,
                             "unvisited": [{"count": len(left[g]), "group": list(g),
                                            "target_ids_sha256": hc(sorted(left[g]))} for g in order]},
                "targets": {"all": len(T), "all_target_ids_sha256": hc([t["occurrence_id"] for t in T]),
                            "identity": len(dup), "identity_target_ids_sha256": hc(sorted(dup)),
                            "near_opportunity": len(T) - len(dup)}}}


def near_query(t, occs, base_ok, params, dead, iv):
    classes = {}
    for b in occs:  # full-U scan, no index
        if base_ok(b, t):
            classes.setdefault(b["object_id"], []).append(b)
    classes.pop(t["object_id"], None)
    here = (t["family_id"], t["provenance"]["member_path"], t["provenance"]["offset"])
    pools = {k: [] for k in CATS}
    for x, members in classes.items():
        positions = {(b["family_id"], b["provenance"]["member_path"], b["provenance"]["offset"]) for b in members}
        families = {b["family_id"] for b in members}
        pools[CATS[0] if here in positions else CATS[1] if t["family_id"] in families else CATS[2]].append(x)
    bases, row = [], {"categories": {}, "target": t["occurrence_id"], "witnesses": []}
    for k in CATS:
        cap = params["caps"][k]
        ranked = sorted(pools[k], key=lambda x: (hc(["candidate", params["seed"], t["occurrence_id"], x]), x))
        keep = ranked[:cap]
        for x in keep:
            ids = sorted(b["occurrence_id"] for b in classes[x])
            bases.append({"category": k, "object_id": x, "representative": ids[0]})
            proof = [b["occurrence_id"] for b in classes[x]
                     if k == CATS[2] or (k == CATS[1] and b["family_id"] == t["family_id"])
                     or (b["family_id"], b["provenance"]["member_path"], b["provenance"]["offset"]) == here]
            row["witnesses"].append({"category": k, "category_witness": sorted(proof)[0],
                                     "eligible_aliases": len(ids), "object_id": x, "representative": ids[0]})
        row["categories"][k] = {
            "cap": cap, "pool_size": len(ranked), "pool_object_ids_sha256": hc(sorted(ranked)),
            "selected_object_ids": sorted(keep), "shortage": cap - len(ranked) if len(ranked) < cap else 0,
            "truncation": len(ranked) - cap if len(ranked) > cap else 0,
            "last_selected_key": [hc(["candidate", params["seed"], t["occurrence_id"], keep[-1]]), keep[-1]]
            if keep else None}
    bases.sort(key=lambda b: b["object_id"])
    row["witnesses"].sort(key=lambda w: w["object_id"])
    row["accounting"] = accounting(t, occs, base_ok, dead, iv, {b["object_id"] for b in bases})
    ids = [b["object_id"] for b in bases]
    return ({"bases": bases, "candidate_count": len(ids), "candidate_list_sha256": hc(ids), "duplicate_of": None,
             "status": "near_duplicate", "target": t["occurrence_id"]}, row)


STAGES = ("lock_excluded", "self", "split", "track_unit", "unknown_time", "temporal")


def accounting(t, occs, base_ok, dead, iv, chosen):
    """First failed stage per occurrence; eligible ones split into exact / selected / truncated classes."""
    fails = (lambda b: b["occurrence_id"] in dead, lambda b: b["occurrence_id"] == t["occurrence_id"],
             lambda b: b["split"] != t["split"],
             lambda b: (b["track"], hc(b["provenance"]["options"])) != (t["track"], hc(t["provenance"]["options"])),
             lambda b: iv(b) is None, lambda b: iv(b)[1] >= iv(t)[0])
    outcomes = {name: 0 for name in STAGES + ("exact_target_class", "category_truncation", "selected_class")}
    eligible = [b for b in occs if base_ok(b, t)]
    for b in occs:
        failed = next((name for name, test in zip(STAGES, fails) if test(b)), None)
        if failed:
            outcomes[failed] += 1
    for b in eligible:
        outcomes["exact_target_class" if b["object_id"] == t["object_id"] else
                 "selected_class" if b["object_id"] in chosen else "category_truncation"] += 1
    if sum(outcomes.values()) != len(occs):
        raise ValueError("stage attribution does not partition U")
    return {"eligible_aliases": len(eligible), "exact_duplicates": outcomes["exact_target_class"],
            "full_pool_classes": len({b["object_id"] for b in eligible} - {t["object_id"]}),
            "outcomes": outcomes, "universe_occurrences": len(occs)}


ROW_KEYS = {"accounting", "categories", "target", "witnesses"}


def compare(expected, lock, selection):
    """Exact per-target and per-category mismatches between the derivation and the artifacts."""
    errors = []
    want = {q["target"]: q for q in expected["queries"]}
    listed = lock.get("queries")
    if type(listed) is not list or any(type(q) is not dict for q in listed):
        return ["lock queries must be a list of records"]
    got = {q.get("target"): q for q in listed}
    if len(got) != len(listed):
        errors.append("lock queries repeat a target")
    for tid in sorted(want.keys() - got.keys()):
        errors.append(f"target {tid}: scheduled but absent from the lock")
    for tid in sorted(got.keys() - want.keys(), key=str):
        errors.append(f"target {tid}: in the lock but not in the scheduled prefix")
    for tid in sorted(want.keys() & got.keys()):
        for field in sorted(set(want[tid]) | set(got[tid])):
            if hc([want[tid].get(field)]) != hc([got[tid].get(field)]):  # type-sensitive: True is not 1
                errors.append(f"target {tid}: field {field} differs")
    if hc([lock.get("planned_pairs_per_codec")]) != hc([expected["planned_pairs_per_codec"]]):
        errors.append("planned_pairs_per_codec differs")
    for part in ("targets", "schedule"):
        if hc([selection.get(part)]) != hc([expected["selection"][part]]):
            errors.append(f"selection evidence {part} differs")
    listed = selection.get("near_queries")
    if type(listed) is not list or any(type(r) is not dict or set(r) != ROW_KEYS for r in listed):
        return errors + ["near query evidence must be a list of closed rows"]
    rows = {r["target"]: r for r in listed}
    if len(rows) != len(listed) or len(listed) != len(expected["selection"]["near_queries"]):
        errors.append("near query evidence rows repeat a target or differ in count")
    for row in expected["selection"]["near_queries"]:
        for part in sorted(ROW_KEYS - {"target"}):
            if hc([rows.get(row["target"], {}).get(part)]) != hc([row[part]]):
                errors.append(f"target {row['target']}: {part} evidence differs")
    return errors


# --- full verification -----------------------------------------------------------

def verify(inputs, e0_freeze_bytes, lock_bytes, selection):
    """Independent report; never raises on mismatch. status is ok, mismatch or refused."""
    report = {"schema": "delsk.e1.verification.v1", "status": "refused", "errors": [], "checks": {}}
    try:
        if sha(e0_freeze_bytes) != E0_FREEZE[1]:
            raise ValueError("e0 freeze record is not the adopted bytes")
        freeze = loads_strict(e0_freeze_bytes)
        expected = {**freeze["inputs"], **freeze["files"]}
        if set(inputs) != set(PATHS):
            raise ValueError(f"closed inputs: got {sorted(inputs)}")
        for name, path in PATHS.items():
            if sha(inputs[name]) != expected[path]:
                raise ValueError(f"{name}: bytes differ from the E0 freeze record")
        raw = gzip.decompress(inputs["corpus_lock"])
        if sha(raw) != freeze["corpus_lock_canonical_sha256"]:
            raise ValueError("corpus lock canonical bytes differ")
        plan, policy, source_lock = (loads_strict(inputs[n]) for n in ("plan", "policy", "source_lock"))
        corpus = loads_strict(raw)
        lock = loads_strict(lock_bytes)
    except (ValueError, KeyError, TypeError, OSError) as error:
        report["errors"].append(f"admission: {error}")
        return report
    errors, counts = check_source_closure(plan, policy, source_lock, corpus)
    report["checks"]["source_to_u"] = counts
    if errors:
        report.update(status="mismatch", errors=[f"source->U: {e}" for e in errors])
        return report
    cand = policy["candidates"]
    params = {"caps": {k: cand[f"{k}_max"] for k in CATS}, "max_targets": policy["targets"]["max_targets"],
              "release_ordinals": policy["targets"]["release_ordinals"], "seed": policy["seed"]}
    world = {"exclusions": corpus["exclusions"], "occurrences": corpus["occurrences"],
             "sources": [{"availability_interval_utc_seconds": interval(r["time"]), "family_id": f["family_id"],
                          "ordinal": r["ordinal"], "source_id": r["release_id"]}
                         for f in plan["families"] for r in f["releases"]]}
    derived = derive(world, params)
    bindings = freeze["candidate_lock_bindings"]
    if bindings["corpus_lock_sha256"] != sha(raw):
        errors.append("E0 binding of the corpus lock differs from the admitted bytes")
    expected_lock = {"planned_pairs_per_codec": derived["planned_pairs_per_codec"], "queries": derived["queries"],
                     "schema": "delsk.candidate.lock.v2", **bindings}
    near = [q for q in derived["queries"] if q["status"] == "near_duplicate"]
    if not near:
        errors.append("no near_duplicate query: not sealable")
    if derived["planned_pairs_per_codec"] > policy["caps"]["planned_pairs_per_codec_max"]:
        errors.append("planned pairs exceed the policy cap")
    errors += compare(derived, lock, selection)
    if canonical_bytes(expected_lock) != lock_bytes:
        errors.append("candidate lock bytes differ from the independently derived canonical lock")
    report["checks"]["u_to_queries"] = {
        "targets_all": derived["selection"]["targets"]["all"], "queries": len(derived["queries"]),
        "near_queries": len(near), "planned_pairs_per_codec": derived["planned_pairs_per_codec"],
        "candidate_lock_sha256": sha(canonical_bytes(expected_lock))}
    report.update(status="mismatch" if errors else "ok", errors=errors)
    return report
