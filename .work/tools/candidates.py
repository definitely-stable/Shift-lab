"""DELSK-002 E1 candidate construction: builder of delsk.candidate.lock.v2.

Normative contract: .work/corpus/e0/construction-spec.md (rulings A01-A10, total
orders §4, E1 contract §7) over the research specification §§3-4, 6-7, 10-11.
Private research code, stdlib only. Inputs are closed frozen metadata (A10): no
payload, score, patch cost, codec, encoder result, callback, clock or
environment read. The independent check is candidate_verify.py; neither module
imports the other.

    admit(inputs)               exact frozen bytes -> world, params, bindings, layout
    construct(world, params)    full-U selection: T_all, identities, A02 schedule, C_t
    make_lock(bindings, result) canonical lock bytes (refuses no-near / over-cap)
    coverage(world, params, result, layout)  §17.2 coverage evidence
"""

import collections
import gzip
import hashlib

import manifests as m

SCHEMA = "delsk.candidate.lock.v2"
CATEGORIES = m.CANDIDATE_CATEGORIES
EMPTY_LIST_SHA256 = m.digest([])
# name -> (repository path, SHA-256 of the exact repository bytes); construction-spec §2, e0/freeze.json.
INPUTS = {
    "plan": (".work/corpus/source-plan.json",
             "75d879fd50ba8d7c749694ab091a61fa59c20ddc5fa3689a0e592692ae221074"),
    "policy": (".work/corpus/selection-policy.json",
               "539642ffb9a65f4fe49f42ea99d26b416c2ab40583021b3fe8d2aa8d415cbd50"),
    "source_lock": (".work/corpus/pilot-v1/source-lock.json",
                    "2154224d9b8af255f4f48662b7f03a6b9865c3e976079dbad33c939eb3a5903c"),
    "corpus_lock": (".work/corpus/pilot-v1/corpus-lock.json.gz",
                    "86009552183230ab13f9366684eedb4fcfcea746b25cbbed10ab2aabceb8f56b"),
    "acquisition_freeze": (".work/corpus/pilot-v1/freeze.json",
                           "8814ce0221b2b890f1710476da0c1a31771e7528d81cfc3a99ffa10acc88e8da"),
    "ancestry_audit": (".work/corpus/e0/ancestry-audit.json",
                       "99d6c4142c0e3a1796d6e877af456f7683ebdf32cbf9519004152b3b59b6b04f"),
    "historical_bytes": (".work/corpus/e0/historical-bytes.json",
                         "bf48bb970327a53be751cffe7d60ef0e142da7414f2539cdc332a3ce2a0a0b0c"),
    "construction_spec": (".work/corpus/e0/construction-spec.md",
                          "b91e54d62aae22ed9cc898abb65e62dd78e47505f63a51a929d445947abf54f8"),
    # Not listed in spec §7.1, but A06 binds protocol_sha256, so its bytes are admitted too.
    "protocol": (".work/protocol.md", "a0c518247d111e8ad1294562d65eb34c28da87c7027c009efb64a39e6f4e0038"),
}
CORPUS_LOCK_CANONICAL_SHA256 = "e5c288256bed284572a9f111186411517b4c73d097d13aea4cf48e2fb9f6fffa"
BINDING_KEYS = ("acquisition_freeze_sha256", "ancestry_audit_sha256", "construction_spec_sha256",
                "corpus_lock_sha256", "historical_bytes_sha256", "protocol_sha256", "selection_policy_sha256")
LOCK_KEYS = {"schema", "planned_pairs_per_codec", "queries", *BINDING_KEYS}
QUERY_KEYS = {"bases", "candidate_count", "candidate_list_sha256", "duplicate_of", "status", "target"}
BASE_KEYS = {"category", "object_id", "representative"}
WORLD_KEYS = {"exclusions", "occurrences", "sources"}
SOURCE_KEYS = {"availability_interval_utc_seconds", "family_id", "ordinal", "source_id"}
OCCURRENCE_KEYS = {"bytes", "family_id", "object_id", "occurrence_id", "parent_bytes", "parent_object_id",
                   "provenance", "source_id", "split", "stratum", "track"}
PARAM_KEYS = {"caps", "max_targets", "pairs_max", "release_ordinals", "seed"}
TARGET_EXCLUSION_ORDER =("source", "member", "object", "occurrence", "unknown_time", "target_ordinal")
BASE_OUTCOME_ORDER = ("lock_excluded", "self", "split", "track_unit", "unknown_time", "temporal",
                      "exact_target_class", "category_truncation", "selected_class")


class CandidateError(ValueError):
    """Refusal: no partial world, selection or lock exists."""


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _fail(errors):
    if errors:
        raise CandidateError("; ".join(sorted(errors)[:50]))


# --- admission (spec §7.1, A06, A09, A10) ------------------------------------

def admit(inputs):
    """Strict admission of the closed frozen input set; returns (world, params, bindings, layout)."""
    if type(inputs) is not dict or set(inputs) != set(INPUTS):
        extra, missing = sorted(set(inputs or ()) - set(INPUTS)), sorted(set(INPUTS) - set(inputs or ()))
        raise CandidateError(f"closed inputs: unexpected {extra}, missing {missing}")
    errors = [f"{name}: SHA-256 differs from the adopted bytes" for name, (_, expected) in INPUTS.items()
              if type(inputs[name]) is not bytes or _sha(inputs[name]) != expected]
    _fail(errors)
    raw_lock = gzip.decompress(inputs["corpus_lock"])
    if _sha(raw_lock) != CORPUS_LOCK_CANONICAL_SHA256:
        raise CandidateError("corpus_lock: decompressed canonical SHA-256 differs")
    docs = {name: m.loads_strict(inputs[name]) for name in
            ("plan", "policy", "source_lock", "acquisition_freeze", "ancestry_audit", "historical_bytes")}
    docs["corpus_lock"] = m.loads_strict(raw_lock)
    sha = {name: _sha(inputs[name]) for name in INPUTS}
    sha["corpus_lock_canonical"] = _sha(raw_lock)
    return admit_documents(docs, sha)


def admit_documents(docs, sha):
    """Semantic admission of parsed frozen documents whose exact-byte SHA-256 values are `sha`."""
    plan, policy, lock = docs["plan"], docs["policy"], docs["corpus_lock"]
    errors = m.validate_corpus_lock(lock, plan, policy)
    _fail(errors)
    sl, freeze, audit, history = (docs[name] for name in
                                  ("source_lock", "acquisition_freeze", "ancestry_audit", "historical_bytes"))
    err = errors.append
    if (sl["source_plan_sha256"], sl["selection_policy_sha256"]) != (sha["plan"], sha["policy"]):
        err("source_lock: plan/policy binding differs")
    if {(s["source_id"], s["archive_sha256"], s["archive_bytes"]) for s in sl["sources"]} != \
            {(s["source_id"], s["archive_sha256"], s["archive_bytes"]) for s in lock["sources"]}:
        err("source_lock: sources differ from the corpus lock")
    if freeze["status"] != "FROZEN_ACQUISITION" or freeze["corpus_lock_canonical_sha256"] != sha["corpus_lock_canonical"] \
            or freeze["files"].get("corpus-lock.json.gz") != sha["corpus_lock"] \
            or freeze["files"].get("source-lock.json") != sha["source_lock"]:
        err("acquisition_freeze: not the frozen D record of these locks")
    result = audit["result"]
    if audit["status"] != "REVIEWED_FOR_PILOT" or audit["bindings"]["source_lock_sha256"] != sha["source_lock"] \
            or result["unresolved"] or result["merges"] or result["new_path_exclusions"] \
            or result["components"] != [c["families"] for c in lock["components"]]:
        err("ancestry_audit: unresolved, merged or not bound to these components (A08)")
    pairs = history["source_pairs"]
    if history["source_lock_sha256"] != sha["source_lock"] or pairs["total"] != len(pairs["pairs"]) \
            or not all(p["base_bytes_attested_before_target_release"] for p in pairs["pairs"]):
        err("historical_bytes: pairwise no-future-base ordering not established (A07)")
    _fail(errors)

    world = {"exclusions": lock["exclusions"], "occurrences": lock["occurrences"],
             "sources": [{"availability_interval_utc_seconds": _interval(r), "family_id": f["family_id"],
                          "ordinal": r["ordinal"], "source_id": r["release_id"]}
                         for f in plan["families"] for r in f["releases"]]}
    bindings = {"acquisition_freeze_sha256": sha["acquisition_freeze"], "ancestry_audit_sha256": sha["ancestry_audit"],
                "construction_spec_sha256": sha["construction_spec"], "corpus_lock_sha256": sha["corpus_lock_canonical"],
                "historical_bytes_sha256": sha["historical_bytes"], "protocol_sha256": sha["protocol"],
                "selection_policy_sha256": sha["policy"]}
    layout = {"components": {fam: (c["families"][0], c["split"]) for c in lock["components"] for fam in c["families"]},
              "lanes": {t["id"]: t["lane"] for t in policy["tracks"]},
              "strata": [s["id"] for s in policy["file_strata"]]}
    return world, params(policy), bindings, layout


def _interval(release):
    interval = m.availability(release.get("time"))
    return list(interval) if interval else None


def params(policy):
    cand = policy["candidates"]
    return {"caps": {k: cand[f"{k}_max"] for k in CATEGORIES}, "max_targets": policy["targets"]["max_targets"],
            "pairs_max": policy["caps"]["planned_pairs_per_codec_max"],
            "release_ordinals": list(policy["targets"]["release_ordinals"]), "seed": policy["seed"]}


# --- world structure (I35) ---------------------------------------------------

def _closed(name, value, keys):
    if type(value) is not dict or set(value) != keys:
        raise CandidateError(f"{name}: closed key set {sorted(keys)} required, got {sorted(value or ())}")


def _index(world):
    """Validated view: sources, occurrences by ID, global exclusions. Any inconsistency -> refusal.

    Key sets are closed (A10): a score, codec, patch-cost or result field anywhere is an error.
    """
    _closed("world", world, WORLD_KEYS)
    errors = []
    sources = {}
    for s in world["sources"]:
        _closed("source", s, SOURCE_KEYS)
        interval = s["availability_interval_utc_seconds"]
        if s["source_id"] in sources:
            errors.append(f"source {s['source_id']}: duplicate")
        if interval is not None and not (type(interval) is list and len(interval) == 2
                                         and all(type(v) is int for v in interval) and interval[0] <= interval[1]):
            errors.append(f"source {s['source_id']}: malformed interval")
        if type(s["ordinal"]) is not int:
            errors.append(f"source {s['source_id']}: ordinal must be an integer")
        sources[s["source_id"]] = s
    occ, positions, sizes, splits = {}, set(), {}, collections.defaultdict(set)
    for o in world["occurrences"]:
        _closed("occurrence", o, OCCURRENCE_KEYS)
        _closed("provenance", o["provenance"], m.PROVENANCE_KEYS)
        oid, prov = o["occurrence_id"], o["provenance"]
        if oid in occ:
            errors.append(f"occurrence {oid}: duplicate ID")
        occ[oid] = o
        position = (o["source_id"], o["track"], prov["member_path"], prov["offset"])
        if position in positions:
            errors.append(f"occurrence {oid}: duplicate provenance position")
        positions.add(position)
        if oid != m.occurrence_id(o["source_id"], prov):
            errors.append(f"occurrence {oid}: ID does not match provenance")
        source = sources.get(o["source_id"])
        if source is None or source["family_id"] != o["family_id"]:
            errors.append(f"occurrence {oid}: unknown source or family mismatch")
        if sizes.setdefault(o["object_id"], o["bytes"]) != o["bytes"]:
            errors.append(f"object {o['object_id']}: one content ID with different sizes")
        splits[o["object_id"]].add(o["split"])
    _fail(errors)
    cross_split = {x for x, s in splits.items() if len(s) > 1}  # X_U on the raw universe (A01)
    flags = collections.defaultdict(set)
    subjects = {(e["kind"], e["subject"]) for e in world["exclusions"]}
    for oid, o in occ.items():
        if ("source", o["source_id"]) in subjects:
            flags[oid].add("source")
        if ("member", f"{o['source_id']}:{o['provenance']['member_path']}") in subjects:
            flags[oid].add("member")
        if ("object", o["object_id"]) in subjects or o["object_id"] in cross_split:
            flags[oid].add("object")
        if ("occurrence", oid) in subjects:
            flags[oid].add("occurrence")
    # I33: a member/occurrence exclusion after D cannot clean bytes already inside that source's tar.
    blocked = {occ[e["subject"]]["source_id"] if e["kind"] == "occurrence" else e["subject"].partition(":")[0]
               for e in world["exclusions"] if e["kind"] in ("member", "occurrence") and e["reason"] == "license_blocked"
               and (e["kind"] == "member" or e["subject"] in occ)}
    errors = [f"occurrence {oid}: composite of {o['source_id']} retains a license-excluded member"
              for oid, o in occ.items() if o["source_id"] in blocked and o["provenance"]["member_path"] is None
              and not flags[oid]]
    _fail(errors)
    return sources, occ, cross_split, flags


# --- construction (spec §4 steps 2-12) -----------------------------------------

def construct(world, params):
    """Deterministic selection over the complete world; independent of every input iteration order."""
    _closed("params", params, PARAM_KEYS)
    _closed("caps", params["caps"], set(CATEGORIES))
    sources, occ, cross_split, flags = _index(world)
    seed, caps = params["seed"], params["caps"]

    def interval(o):
        return sources[o["source_id"]]["availability_interval_utc_seconds"]

    def eligible(b, t):  # E(b, t), spec §3
        ib, it = interval(b), interval(t)
        return (not flags[b["occurrence_id"]] and b["occurrence_id"] != t["occurrence_id"]
                and b["split"] == t["split"] and b["track"] == t["track"]
                and b["provenance"]["options"] == t["provenance"]["options"]
                and ib is not None and it is not None and ib[1] < it[0])

    universe = [occ[oid] for oid in sorted(occ)]
    by_object = collections.defaultdict(list)
    buckets = collections.defaultdict(list)
    for oid in sorted(occ):
        o = occ[oid]
        by_object[o["object_id"]].append(o)
        buckets[o["split"], o["track"]].append(o)

    targets = [occ[oid] for oid in sorted(occ) if not flags[oid]
               and sources[occ[oid]["source_id"]]["ordinal"] in params["release_ordinals"]
               and interval(occ[oid]) is not None]
    duplicate_of = {}
    for t in targets:  # identity classification of all T_all (A03)
        dups = [b["occurrence_id"] for b in by_object[t["object_id"]] if eligible(b, t)]
        if dups:
            duplicate_of[t["occurrence_id"]] = min(dups)

    groups = collections.defaultdict(list)
    for t in targets:
        groups[t["family_id"], t["track"], t["stratum"] or ""].append(t["occurrence_id"])
    order = sorted(groups, key=lambda g: (m.rank("target-group", seed, *g), g))
    queues = {g: collections.deque(sorted(groups[g], key=lambda tid: (m.rank("target", seed, tid), tid)))
              for g in order}

    trace, queries, selection, near, rnd = [], [], [], 0, 0
    while near < params["max_targets"] and any(queues.values()):  # A02
        rnd += 1
        for g in order:
            if near >= params["max_targets"]:
                break
            if not queues[g]:
                continue
            tid = queues[g].popleft()
            if tid in duplicate_of:
                queries.append(_query(tid, "identity_only", duplicate_of[tid], []))
            else:
                bases, evidence, witnesses = _select(occ[tid], buckets[occ[tid]["split"], occ[tid]["track"]],
                                                     eligible, seed, caps)
                queries.append(_query(tid, "near_duplicate", None, bases))
                selection.append({"accounting": _accounting(occ[tid], universe, flags, interval, bases),
                                  "categories": evidence, "target": tid, "witnesses": witnesses})
                near += 1
            trace.append({"group": list(g), "near_count_after": near, "round": rnd,
                          "status": queries[-1]["status"], "target": tid})
    queries.sort(key=lambda q: q["target"])
    selection.sort(key=lambda s: s["target"])
    unvisited = [{"count": len(queues[g]), "group": list(g), "target_ids_sha256": m.digest(sorted(queues[g]))}
                 for g in order]
    return {
        "queries": queries,
        "planned_pairs_per_codec": sum(q["candidate_count"] for q in queries if q["status"] == "near_duplicate"),
        "selection": {
            "schedule": {"group_order": [list(g) for g in order], "rounds": rnd,
                         "stop_reason": "near_quota" if near >= params["max_targets"] else "exhausted",
                         "traversal": trace, "unvisited": unvisited},
            "targets": {"all": len(targets), "identity": len(duplicate_of),
                        "near_opportunity": len(targets) - len(duplicate_of),
                        "all_target_ids_sha256": m.digest([t["occurrence_id"] for t in targets]),
                        "identity_target_ids_sha256": m.digest(sorted(duplicate_of))},
            "near_queries": selection},
        "_duplicate_of": duplicate_of,
    }


def _select(t, bucket, eligible, seed, caps):
    """Full F_t, existential category (A04), first-N per category, minimum representative."""
    pool = collections.defaultdict(list)
    for b in bucket:
        if eligible(b, t):
            pool[b["object_id"]].append(b)
    if t["object_id"] in pool:  # a near target has empty D_t by construction
        raise CandidateError(f"target {t['occurrence_id']}: exact class reached base selection")
    position = (t["family_id"], t["provenance"]["member_path"], t["provenance"]["offset"])
    by_category = {k: [] for k in CATEGORIES}
    for x, aliases in pool.items():
        if any((b["family_id"], b["provenance"]["member_path"], b["provenance"]["offset"]) == position
               for b in aliases):
            by_category["same_path_historical"].append(x)
        elif any(b["family_id"] == t["family_id"] for b in aliases):
            by_category["same_family_decoy"].append(x)
        else:
            by_category["foreign_family_decoy"].append(x)
    witness = {"same_path_historical": lambda b: (b["family_id"], b["provenance"]["member_path"],
                                                  b["provenance"]["offset"]) == position,
               "same_family_decoy": lambda b: b["family_id"] == t["family_id"],
               "foreign_family_decoy": lambda b: True}
    bases, evidence, witnesses = [], {}, []
    for k in CATEGORIES:
        keyed = sorted((m.rank("candidate", seed, t["occurrence_id"], x), x) for x in by_category[k])
        chosen = keyed[:caps[k]]
        bases += [{"category": k, "object_id": x,
                   "representative": min(b["occurrence_id"] for b in pool[x])} for _, x in chosen]
        witnesses += [{"category": k, "category_witness": min(b["occurrence_id"] for b in pool[x] if witness[k](b)),
                       "eligible_aliases": len(pool[x]), "object_id": x,
                       "representative": min(b["occurrence_id"] for b in pool[x])} for _, x in chosen]
        evidence[k] = {"cap": caps[k], "last_selected_key": list(chosen[-1]) if chosen else None,
                       "pool_object_ids_sha256": m.digest(sorted(by_category[k])), "pool_size": len(keyed),
                       "selected_object_ids": sorted(x for _, x in chosen),
                       "shortage": max(0, caps[k] - len(keyed)), "truncation": max(0, len(keyed) - caps[k])}
    return (sorted(bases, key=lambda b: b["object_id"]), evidence,
            sorted(witnesses, key=lambda w: w["object_id"]))


def _accounting(t, universe, flags, interval, bases):
    """Per-stage base accounting over all of U for one near target (research spec §17.2 "Bases per target").

    Each occurrence gets the first failing stage of BASE_OUTCOME_ORDER (diagnostic attribution only).
    """
    selected = {b["object_id"] for b in bases}
    counts = dict.fromkeys(BASE_OUTCOME_ORDER, 0)
    classes, it = set(), interval(t)
    for b in universe:
        ib = interval(b)
        if flags[b["occurrence_id"]]:
            outcome = "lock_excluded"
        elif b["occurrence_id"] == t["occurrence_id"]:
            outcome = "self"
        elif b["split"] != t["split"]:
            outcome = "split"
        elif b["track"] != t["track"] or b["provenance"]["options"] != t["provenance"]["options"]:
            outcome = "track_unit"
        elif ib is None:
            outcome = "unknown_time"
        elif not ib[1] < it[0]:
            outcome = "temporal"
        else:
            classes.add(b["object_id"])
            outcome = ("exact_target_class" if b["object_id"] == t["object_id"]
                       else "selected_class" if b["object_id"] in selected else "category_truncation")
        counts[outcome] += 1
    eligible = counts["exact_target_class"] + counts["category_truncation"] + counts["selected_class"]
    return {"eligible_aliases": eligible, "exact_duplicates": counts["exact_target_class"],
            "full_pool_classes": len(classes - {t["object_id"]}), "outcomes": counts,
            "universe_occurrences": len(universe)}


def _query(tid, status, duplicate, bases):
    ids = [b["object_id"] for b in bases]
    return {"bases": bases, "candidate_count": len(bases), "candidate_list_sha256": m.digest(ids),
            "duplicate_of": duplicate, "status": status, "target": tid}


# --- lock (A06) --------------------------------------------------------------

def make_lock(bindings, result, params):
    """Canonical v2 lock bytes. Refuses a universe without near queries or above the pair cap."""
    if set(bindings) != set(BINDING_KEYS) or not all(type(v) is str and m.SHA256.match(v) for v in bindings.values()):
        raise CandidateError("bindings: closed v2 binding set required")
    queries = result["queries"]
    errors = [] if [q["target"] for q in queries] == sorted({q["target"] for q in queries}) \
        else ["queries must be sorted by unique target"]
    for q in queries:
        errors += [f"query {q.get('target')}: {e}" for e in _query_errors(q, params["caps"])]
    _fail(errors)
    near = [q for q in queries if q["status"] == "near_duplicate"]
    if not near:
        raise CandidateError("no near_duplicate target; identity-only or empty universe is not sealable")
    pairs = sum(q["candidate_count"] for q in near)
    if type(result["planned_pairs_per_codec"]) is not int or pairs != result["planned_pairs_per_codec"] or pairs > params["pairs_max"] or len(near) > params["max_targets"]:
        raise CandidateError("planned pairs differ from the near-query sum or exceed the cap")
    lock = {"planned_pairs_per_codec": pairs, "queries": result["queries"], "schema": SCHEMA, **bindings}
    assert set(lock) == LOCK_KEYS
    return m.canonical_bytes(lock)


def _is_sha256(value):
    return type(value) is str and bool(m.SHA256.match(value))


def _query_errors(q, caps):
    """Closed query shape and internal agreement (V45); selection correctness is the verifier's job."""
    if type(q) is not dict or set(q) != QUERY_KEYS:
        return ["closed query key set required"]
    bases = q["bases"]
    if type(bases) is not list or any(type(b) is not dict or set(b) != BASE_KEYS or b["category"] not in caps
                                      or not _is_sha256(b["object_id"]) or not _is_sha256(b["representative"])
                                      for b in bases):
        return ["bases must be closed base records with SHA-256 IDs"]
    if not _is_sha256(q["target"]) or q["status"] not in ("identity_only", "near_duplicate"):
        return ["target must be a SHA-256 ID and status identity_only or near_duplicate"]
    ids = [b["object_id"] for b in bases]
    errors = []
    if ids != sorted(set(ids)):
        errors.append("bases must be sorted by unique object_id")
    if type(q["candidate_count"]) is not int or q["candidate_count"] != len(bases):
        errors.append("candidate_count must be the integer number of bases")
    if q["candidate_list_sha256"] != m.digest(ids):
        errors.append("candidate_list_sha256 differs from the sorted base IDs")
    if any(sum(b["category"] == k for b in bases) > caps[k] for k in caps):
        errors.append("category above cap")
    if q["status"] == "identity_only":
        if bases or not _is_sha256(q["duplicate_of"]):
            errors.append("identity_only needs duplicate_of and no bases")
    elif q["duplicate_of"] is not None:
        errors.append("near_duplicate needs duplicate_of null")
    return errors


# --- coverage (construction-spec §8, research spec §17.2) ----------------------

def coverage(world, params, result, layout=None):
    """Stage denominators for all planned cells, zeros included; diagnostics, never eligibility."""
    sources, occ, cross_split, flags = _index(world)
    if layout is None:  # synthetic worlds: every observed family is its own component
        layout = {"components": {o["family_id"]: (o["family_id"], o["split"]) for o in occ.values()},
                  "lanes": {o["track"]: "modeled" for o in occ.values()},
                  "strata": sorted({o["stratum"] for o in occ.values() if o["stratum"]})}
    ordinals = params["release_ordinals"]
    duplicate_of = result["_duplicate_of"]
    visited = {q["target"]: q for q in result["queries"]}
    target_ids = set()
    primary, flag_counts = collections.Counter(), collections.Counter()
    for oid, o in occ.items():
        reasons = set(flags[oid])
        if sources[o["source_id"]]["availability_interval_utc_seconds"] is None:
            reasons.add("unknown_time")
        if sources[o["source_id"]]["ordinal"] not in ordinals:
            reasons.add("target_ordinal")
        flag_counts.update(reasons)
        if reasons:
            primary[next(r for r in TARGET_EXCLUSION_ORDER if r in reasons)] += 1
        else:
            target_ids.add(oid)

    def cell_key(o):
        component, split = layout["components"][o["family_id"]]
        return component, o["family_id"], split, o["track"], o["stratum"]

    zero = dict.fromkeys(("occurrences", "lock_excluded", "unknown_time", "target_release", "targets_all",
                          "identity_all", "near_opportunity_all", "visited_identity", "selected_near",
                          "selected_near_empty_pool", "unvisited", "planned_pairs"), 0)
    cells = {}
    for fam, (component, split) in layout["components"].items():
        for track in layout["lanes"]:
            for stratum in (layout["strata"] if track == "file" else [None]):
                cells[component, fam, split, track, stratum] = dict(zero)
    for oid, o in occ.items():
        c = cells.setdefault(cell_key(o), dict(zero))
        c["occurrences"] += 1
        c["lock_excluded"] += bool(flags[oid])
        c["unknown_time"] += sources[o["source_id"]]["availability_interval_utc_seconds"] is None
        c["target_release"] += sources[o["source_id"]]["ordinal"] in ordinals
        if oid in target_ids:
            c["targets_all"] += 1
            c["identity_all" if oid in duplicate_of else "near_opportunity_all"] += 1
            q = visited.get(oid)
            if q is None:
                c["unvisited"] += 1
            elif q["status"] == "identity_only":
                c["visited_identity"] += 1
            else:
                c["selected_near"] += 1
                c["selected_near_empty_pool"] += q["candidate_count"] == 0
                c["planned_pairs"] += q["candidate_count"]
    rows = [{"component": k[0], "family_id": k[1], "split": k[2], "track": k[3], "stratum": k[4],
             "lane": layout["lanes"].get(k[3]), **v}
            for k, v in sorted(cells.items(), key=lambda kv: tuple("" if p is None else p for p in kv[0]))]

    aliases = collections.Counter()
    for o in occ.values():
        aliases[o["object_id"]] += 1
    near = [q for q in result["queries"] if q["status"] == "near_duplicate"]
    identities = [q for q in result["queries"] if q["status"] == "identity_only"]
    population = result["selection"]["targets"]
    return {
        "schema": "delsk.e1.coverage.v1",
        "universe": {"occurrences": len(occ), "content_classes": len(aliases),
                     "alias_histogram": {str(n): c for n, c in sorted(collections.Counter(aliases.values()).items())},
                     "cross_split_classes": len(cross_split),
                     "cross_split_occurrences": sum(o["object_id"] in cross_split for o in occ.values())},
        "target_exclusions": {"precedence": list(TARGET_EXCLUSION_ORDER), "primary": dict(sorted(primary.items())),
                              "flags": dict(sorted(flag_counts.items()))},
        "rates": {"identity_all": [population["identity"], population["all"]],
                  "identity_visited": [len(identities), len(result["queries"])],
                  "empty_pool_selected_near": [sum(q["candidate_count"] == 0 for q in near), len(near)]},
        "cells": rows,
        "pair_plan": {"total": result["planned_pairs_per_codec"],
                      "by_track": _sum_by(rows, "track"), "by_component": _sum_by(rows, "component"),
                      "by_lane": _sum_by(rows, "lane")},
    }


def _sum_by(rows, key):
    totals = collections.Counter()
    for row in rows:
        totals[row[key]] += row["planned_pairs"]
    return dict(sorted(totals.items()))
