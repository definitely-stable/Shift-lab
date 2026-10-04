"""DELSK-003 Slice B: production evaluator of delsk.oracle-contract.v1 (G1 primary oracle).

Independent implementation of contract sections 3-9 (.work/oracle/contract.md). Stdlib only; it imports neither the
runner (oracle_run.py) nor the test-only reference (.work/tests/oracle_reference.py), and never reads patch payloads:
everything is recomputed from retained rows, the committed locks and the codec lock.

    python3 oracle_eval.py finalize EVIDENCE_DIR PRIVATE_DIR      in-job: seal, derive targets, coverage, summary, evaluation
    python3 oracle_eval.py verify BUNDLE_DIR...                    recompute retained bundles byte for byte
    python3 oracle_eval.py bundle ARTIFACT_DIR [RESULTS_DIR]       verified transactional import (default .work/results)
    python3 oracle_eval.py g1 BUNDLE_DIR...                        G1 over all attempts of one pilot measurement identity

Output never contains a cost, size or digest of a sealed (evaluation split) row: messages carry only statuses,
counts and reasons.
"""

import collections
from fractions import Fraction
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unicodedata

TOOLS = Path(__file__).resolve().parent
WORK = TOOLS.parent
ROOT = WORK.parent
ORACLE = WORK / "oracle"
RESULTS = WORK / "results" / "DELSK-003-ORACLE"
CONTRACT_ID = "delsk.oracle-contract.v1"

BASE_REFERENCE_BYTES = 32  # raw SHA-256 object ID of the base, frame v1
CODEC_METADATA_BYTES = 0
TOLERANCE_FLOOR = 64
EPSILONS = (1, 2, 5)
INT_LIMIT = 1 << 63  # durable integers are signed 64-bit; anything larger is malformed evidence
BOUNDED = ("timeout", "codec_error", "resource_limit")
FATAL = {"decode_mismatch": "DECODE_MISMATCH", "input_integrity": "INPUT_INTEGRITY"}
DECODE_CLASSES = ("nonzero_exit", "signal", "missing_output", "length_mismatch", "bytes_mismatch", "sha256_mismatch")
# Contract section 5: the only (failure_phase, error_class) a failure status may carry. A decoder error on the encoder's
# own patch is decode_mismatch (A11), never a bounded codec_error, so a decode-phase codec_error is a laundered row.
FAILURE_MODES = {
    "timeout": {("encode", "wall_timeout"), ("decode", "wall_timeout")},
    "codec_error": {("encode", c) for c in ("nonzero_exit", "signal", "missing_output")},
    "resource_limit": {("encode", "address_space"), ("encode", "work_dir")},
    "decode_mismatch": {("decode", c) for c in DECODE_CLASSES},
    "input_integrity": {("materialize", "base_integrity"), ("materialize", "target_integrity")},
    "not_run": {("runner", "runner_abort")},
}
IDENTITY = ("measurement_identity_sha256", "measured_source_sha", "corpus_lock_sha256", "candidate_lock_sha256")
TIMING = ("encode_wall_ns", "decode_wall_ns", "encode_peak_rss_bytes", "decode_peak_rss_bytes")
RUN_SPECIFIC = frozenset((*TIMING, "compress_wall_ns", "decompress_wall_ns", "measurement_identity_sha256",
                          "measured_source_sha"))
PAIR, PAIR_SEALED = "delsk.oracle.pair.v1", "delsk.oracle.pair-sealed.v1"
SOLO, SOLO_SEALED = "delsk.oracle.standalone.v1", "delsk.oracle.standalone-sealed.v1"
TARGET, TARGET_SEALED = "delsk.oracle.target.v1", "delsk.oracle.target-sealed.v1"
SCHEMA_DEFS = {PAIR: "pair", PAIR_SEALED: "pair_sealed", SOLO: "standalone", SOLO_SEALED: "standalone_sealed",
               TARGET: "target", TARGET_SEALED: "target_sealed", "delsk.oracle.retrieval.v1": "retrieval"}
SEALED_PAIR_FIELDS = (*IDENTITY, "codec_id", "options_sha256", "pair_id", "target_occurrence_id", "base_object_id",
                      "split", "status", "failure_phase", "error_class", "decoded_sha256")
SEALED_SOLO_FIELDS = (*IDENTITY, "codec_id", "options_sha256", "target_occurrence_id", "split", "query_status",
                      "status", "failure_phase", "error_class", "decoded_sha256")
COUNTS = ("pairs_expected", "pairs_ok", "pairs_timeout", "pairs_codec_error", "pairs_resource_limit")
SEALED_TARGET_FIELDS = ("measurement_identity_sha256", "target_occurrence_id", "split", "query_status",
                        "candidate_count", *COUNTS, "standalone_status")
SPLITS = ("development", "calibration", "evaluation")
SELF_METHOD = "oracle-self"
HEX64, HEX40 = re.compile(r"[0-9a-f]{64}\Z"), re.compile(r"[0-9a-f]{40}\Z")
ROW_FILES = ("pairs.jsonl", "standalone.jsonl", "targets.jsonl")
DOC_FILES = ("coverage.json", "summary.json", "evaluation.json")
BUNDLE_FILES = ("run.json", "codec-lock.json", "tools.json", "conformance.json", *ROW_FILES, *DOC_FILES,
                "checksums.sha256")
SMOKE_LOCKS = ("candidate-lock.json", "corpus-lock.json")


class EvalError(Exception):
    pass


def check(condition, message):
    if not condition:
        raise EvalError(message)


# --- canonical JSON (compact form = Hc input; file form = sorted keys, 2-space indent, final LF) -----------------------

def _plain(value, where="$"):
    if value is None or type(value) is bool:
        return
    if type(value) is int:
        check(-INT_LIMIT <= value < INT_LIMIT, f"{where}: integer out of 64-bit range")
        return
    if type(value) is str:
        check(unicodedata.normalize("NFC", value) == value, f"{where}: string is not NFC")
        value.encode("utf-8")
        return
    if type(value) is list:
        for i, item in enumerate(value):
            _plain(item, f"{where}[{i}]")
        return
    if type(value) is dict:
        for key, item in value.items():
            check(type(key) is str and key.isascii(), f"{where}: keys must be ASCII strings")
            _plain(item, f"{where}.{key}")
        return
    raise EvalError(f"{where}: unsupported JSON value {type(value).__name__} (floats are forbidden)")


def compact(value):
    _plain(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical(value):
    _plain(value)
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def hc(value):
    return hashlib.sha256(compact(value).encode("utf-8")).hexdigest()


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def _pairs_hook(pairs):
    out = {}
    for key, value in pairs:
        check(key not in out, f"duplicate JSON key {key!r}")
        out[key] = value
    return out


def _no_number(token):
    raise EvalError(f"forbidden JSON number {token}")


def _decode(text):
    return json.loads(text, object_pairs_hook=_pairs_hook, parse_float=_no_number, parse_constant=_no_number)


def parse_doc(data):
    """Strict parse of a canonical JSON file: no BOM, floats, duplicate keys or non-canonical bytes."""
    check(not data.startswith(b"\xef\xbb\xbf"), "UTF-8 BOM")
    value = _decode(data.decode("utf-8"))
    check(canonical(value) == data, "bytes are not canonical JSON")
    return value


def parse_jsonl(data):
    """Strict parse of canonical JSONL: one compact canonical object per LF-terminated line."""
    if not data:
        return []
    check(data.endswith(b"\n"), "JSONL does not end with LF")
    rows = []
    for number, line in enumerate(data[:-1].split(b"\n"), 1):
        row = _decode(line.decode("utf-8"))
        check(type(row) is dict, f"line {number}: not an object")
        check(compact(row).encode("utf-8") == line, f"line {number}: not compact canonical JSON")
        rows.append(row)
    return rows


def row_key(row):
    return (row["target_occurrence_id"], row.get("base_object_id", ""), row["schema"])


def jsonl(rows, drop=()):
    """Canonical JSONL bytes: rows sorted by (target, base or "", schema), optional fields dropped."""
    rows = sorted(({k: v for k, v in r.items() if k not in drop} for r in rows), key=row_key)
    return "".join(compact(r) + "\n" for r in rows).encode("utf-8")


# --- closed JSON Schema subset of .work/oracle/schemas.json ----------------------------------------------------------

_SCHEMAS = {}


def schemas():
    if not _SCHEMAS:
        _SCHEMAS.update(parse_doc((ORACLE / "schemas.json").read_bytes()))
    return _SCHEMAS


def _same(a, b):
    return type(a) is type(b) and a == b


def schema_errors(value, node, root=None, where="$"):
    """Errors of value against node. Keywords: $ref type const enum pattern minimum required properties
    additionalProperties items minItems uniqueItems oneOf if/then/else. bool is never an integer."""
    root = root or schemas()
    if "$ref" in node:
        target = root
        for part in node["$ref"][2:].split("/"):
            target = target[part]
        return schema_errors(value, target, root, where)
    kinds = {"object": dict, "array": list, "string": str, "integer": int, "null": type(None), "boolean": bool}
    if "type" in node:
        wanted = node["type"] if type(node["type"]) is list else [node["type"]]
        if type(value) not in [kinds[k] for k in wanted]:
            return [f"{where}: type"]
    errors = []
    if "const" in node and not _same(value, node["const"]):
        errors.append(f"{where}: const")
    if "enum" in node and not any(_same(value, e) for e in node["enum"]):
        errors.append(f"{where}: enum")
    if type(value) is str and "pattern" in node and not re.search(node["pattern"], value):
        errors.append(f"{where}: pattern")
    if type(value) is int and "minimum" in node and value < node["minimum"]:
        errors.append(f"{where}: minimum")
    if type(value) is dict:
        props = node.get("properties", {})
        errors += [f"{where}: missing {k}" for k in node.get("required", ()) if k not in value]
        if node.get("additionalProperties") is False:
            errors += [f"{where}: unexpected {k}" for k in value if k not in props]
        for key, sub in props.items():
            if key in value:
                errors += schema_errors(value[key], sub, root, f"{where}.{key}")
    if type(value) is list:
        if len(value) < node.get("minItems", 0):
            errors.append(f"{where}: minItems")
        if node.get("uniqueItems") and len({compact(v) for v in value}) != len(value):
            errors.append(f"{where}: uniqueItems")
        for i, item in enumerate(value if "items" in node else ()):
            errors += schema_errors(item, node["items"], root, f"{where}[{i}]")
    if "oneOf" in node and sum(not schema_errors(value, sub, root) for sub in node["oneOf"]) != 1:
        errors.append(f"{where}: oneOf")
    if "if" in node:
        branch = node.get("then" if not schema_errors(value, node["if"], root) else "else")
        if branch:
            errors += schema_errors(value, branch, root, where)
    return errors


def valid_row(row, allowed):
    """True when row carries one of the allowed schema IDs and satisfies that closed schema."""
    kind = row.get("schema") if type(row) is dict else None
    return kind in allowed and not schema_errors(row, schemas()["$defs"][SCHEMA_DEFS[kind]])


# --- frame v1 accounting (contract section 3) ------------------------------------------------------------------------

def uleb128_len(n):
    return max(1, (n.bit_length() + 6) // 7)


def wrapper_bytes(payload):
    return 1 + uleb128_len(payload)


def raw_total(n):
    return n + wrapper_bytes(n)


def compressed_total(payload):
    return payload + wrapper_bytes(payload) + CODEC_METADATA_BYTES


def delta_total(payload):
    return payload + wrapper_bytes(payload) + BASE_REFERENCE_BYTES + CODEC_METADATA_BYTES


def pair_id(codec_id, target, base):
    return hc(["delsk.oracle.pair.v1", codec_id, target, base])


# --- sealing (contract section 9.1) ----------------------------------------------------------------------------------

def commitment(row):
    """row_sha256 of a sealed row: Hc of the full row without run-specific fields."""
    return hc({k: v for k, v in row.items() if k not in RUN_SPECIFIC})


def seal_pair(row):
    return {"schema": PAIR_SEALED, **{k: row[k] for k in SEALED_PAIR_FIELDS}, "row_sha256": commitment(row)}


def seal_standalone(row):
    return {"schema": SOLO_SEALED, **{k: row[k] for k in SEALED_SOLO_FIELDS}, "row_sha256": commitment(row)}


def seal_target(row):
    return {"schema": TARGET_SEALED, **{k: row[k] for k in SEALED_TARGET_FIELDS}, "row_sha256": commitment(row)}


# --- world: expected universe from the locks, never from rows (contract sections 4, 8) ------------------------------

def world_from_locks(candidate_lock, corpus_lock, identity, codec_lock):
    """Evaluator world from a candidate lock, the corpus lock it binds and the run's measurement identity."""
    occurrences = {}
    for occ in corpus_lock["occurrences"]:
        check(occ["occurrence_id"] not in occurrences, "corpus lock: duplicate occurrence")
        occurrences[occ["occurrence_id"]] = occ
    queries, facts, base_bytes = {}, {}, {}
    for q in candidate_lock["queries"]:
        t = q["target"]
        check(t in occurrences and t not in queries, "candidate lock: unknown or repeated target")
        check(q["status"] in ("near_duplicate", "identity_only"), "candidate lock: query status")
        bases = []
        for b in q["bases"]:
            rep = occurrences.get(b["representative"])
            check(rep is not None and rep["object_id"] == b["object_id"], "candidate lock: base representative")
            check(base_bytes.setdefault(b["object_id"], rep["bytes"]) == rep["bytes"], "corpus lock: object size")
            bases.append((b["object_id"], b["representative"]))
        ids = [b for b, _ in bases]
        check(ids == sorted(set(ids)), "candidate lock: bases not unique and sorted")
        check(q["status"] == "near_duplicate" or not ids, "candidate lock: identity query with bases")
        check(q.get("candidate_list_sha256", hc(ids)) == hc(ids), "candidate lock: candidate_list_sha256")
        occ = occurrences[t]
        facts[t] = {k: occ[k] for k in ("object_id", "bytes", "split", "family_id", "track")}
        queries[t] = {"status": q["status"], "bases": bases}
    check(list(queries) == sorted(queries), "candidate lock: queries not in canonical order")
    codecs = codec_lock["codecs"]
    return {"identity": {k: identity[k] for k in IDENTITY},
            "delta": {k: codecs["delta"][k] for k in ("codec_id", "options_sha256")},
            "standalone": {k: codecs["standalone"][k] for k in ("codec_id", "options_sha256")},
            "sealed_splits": list(identity["sealed_splits"]), "queries": queries, "facts": facts,
            "base_bytes": base_bytes}


def expected_pairs(world):
    """Expected (target, base) universe in canonical order (contract section 4)."""
    return [(t, b) for t in sorted(world["queries"]) if world["queries"][t]["status"] == "near_duplicate"
            for b, _ in world["queries"][t]["bases"]]


# --- oracle derivation (contract sections 6, 8.1) ---------------------------------------------------------------------

def pair_counts(world, t, rows):
    """Target counts from its pair rows {base: row} (sealed or full)."""
    statuses = [rows[b]["status"] for b, _ in world["queries"][t]["bases"] if b in rows]
    return {"pairs_expected": len(world["queries"][t]["bases"]),
            **{f"pairs_{s}": statuses.count(s) for s in ("ok", *BOUNDED)}}


def derive_target(world, t, rows, srow):
    """Full delsk.oracle.target.v1 row of target t from its full standalone row and full pair rows {base: row}."""
    q, fact = world["queries"][t], world["facts"][t]
    raw = srow["raw_total_bytes"]
    comp = srow["compressed_total_bytes"] if srow["status"] == "ok" else None
    s, choice = (comp, "compressed") if comp is not None and comp < raw else (raw, "raw")
    finite = {b: rows[b]["delta_total_bytes"] for b, _ in q["bases"] if rows[b]["status"] == "ok"}
    best = min(finite.values()) if finite else None
    useful = best is not None and best < s
    if q["status"] == "identity_only":
        delta_status = "identity_only"
    elif finite:
        delta_status = "finite"
    else:
        delta_status = "all_pairs_failed" if q["bases"] else "empty_candidate_set"
    return {"schema": TARGET, "measurement_identity_sha256": world["identity"]["measurement_identity_sha256"],
            "target_occurrence_id": t, "target_object_id": fact["object_id"], "family_id": fact["family_id"],
            "split": fact["split"], "track": fact["track"], "query_status": q["status"], "target_bytes": fact["bytes"],
            "candidate_count": len(q["bases"]), "candidate_list_sha256": hc([b for b, _ in q["bases"]]),
            **pair_counts(world, t, rows), "raw_total_bytes": raw, "standalone_status": srow["status"],
            "standalone_compressed_total_bytes": comp, "standalone_total_bytes": s, "standalone_choice": choice,
            "oracle_delta_total_bytes": best, "oracle_delta_status": delta_status,
            "oracle_tie_bases": sorted(b for b, c in finite.items() if c == best),
            "oracle_total_bytes": best if useful else s, "oracle_choice": "delta" if useful else "standalone",
            "useful_delta": useful}


# --- evaluation (contract sections 7, 8, 9.1) ------------------------------------------------------------------------

def ratio(num, den):
    return None if den == 0 else Fraction(num, den)


def quantile7(values, p):
    """Hyndman-Fan type 7 on exact rationals."""
    xs = sorted(values)
    h = (len(xs) - 1) * p
    lo = h.numerator // h.denominator
    nxt = xs[min(lo + 1, len(xs) - 1)]
    return xs[lo] + (h - lo) * (nxt - xs[lo])


def evaluate(world, pairs, standalone, targets, retrieval=None):
    """Validate retained rows against the locks and derive the oracle; returns a plain result dict.

    retrieval: list of delsk.oracle.retrieval.v1 rows, or None. Rows may arrive in any order."""
    reasons = set()
    ident, queries, facts = world["identity"], world["queries"], world["facts"]
    sealed_splits = set(world["sealed_splits"])
    near = [t for t in sorted(queries) if queries[t]["status"] == "near_duplicate"]
    expected = {(t, b): rep for t in near for b, rep in queries[t]["bases"]}

    def common(row, codec, t):
        if any(row[k] != ident[k] for k in IDENTITY) or row["codec_id"] != codec["codec_id"]:
            reasons.add("IDENTITY_MISMATCH")
        elif row["options_sha256"] != codec["options_sha256"]:
            reasons.add("OPTIONS_MISMATCH")
        if row["split"] != facts[t]["split"]:
            reasons.add("LOCK_FIELD_MISMATCH")
        if row["schema"].endswith("-sealed.v1") != (facts[t]["split"] in sealed_splits):
            reasons.add("SEALING_VIOLATION")
        status = row["status"]
        if status in FATAL:
            reasons.add(FATAL[status])
        if status != "ok" and (row["failure_phase"], row["error_class"]) not in FAILURE_MODES[status]:
            reasons.add("INCONSISTENT_ROW")
        if status == "ok" and row["decoded_sha256"] != facts[t]["object_id"]:
            reasons.add("DECODE_MISMATCH")

    seen = {}
    for row in pairs:
        if not valid_row(row, (PAIR, PAIR_SEALED)):
            reasons.add("SCHEMA")
            continue
        key = (row["target_occurrence_id"], row["base_object_id"])
        if key not in expected:
            reasons.add("FOREIGN_PAIR")
            continue
        if key in seen:
            reasons.add("DUPLICATE_PAIR")
            continue
        seen[key] = row
        t, b = key
        if row["pair_id"] != pair_id(world["delta"]["codec_id"], t, b):
            reasons.add("PAIR_ID_MISMATCH")
        common(row, world["delta"], t)
        if row["schema"] == PAIR_SEALED:
            continue
        fact = facts[t]
        if (row["target_object_id"], row["target_bytes"], row["base_representative"], row["base_bytes"]) != \
                (fact["object_id"], fact["bytes"], expected[key], world["base_bytes"][b]):
            reasons.add("LOCK_FIELD_MISMATCH")
        if row["status"] == "ok":
            p = row["patch_payload_bytes"]
            if (row["wrapper_bytes"], row["base_reference_bytes"], row["codec_metadata_bytes"],
                    row["delta_total_bytes"]) != (wrapper_bytes(p), BASE_REFERENCE_BYTES, CODEC_METADATA_BYTES,
                                                  delta_total(p)):
                reasons.add("ACCOUNTING_MISMATCH")
            if row["decoded_bytes"] != fact["bytes"]:
                reasons.add("DECODE_MISMATCH")
            if (row["encode_exit"], row["decode_exit"], row["encode_signal"], row["decode_signal"]) != (0, 0, None, None):
                reasons.add("INCONSISTENT_ROW")

    solo = {}
    for row in standalone:
        if not valid_row(row, (SOLO, SOLO_SEALED)):
            reasons.add("SCHEMA")
            continue
        t = row["target_occurrence_id"]
        if t not in queries:
            reasons.add("FOREIGN_STANDALONE")
            continue
        if t in solo:
            reasons.add("DUPLICATE_STANDALONE")
            continue
        solo[t] = row
        common(row, world["standalone"], t)
        if row["query_status"] != queries[t]["status"]:
            reasons.add("LOCK_FIELD_MISMATCH")
        if row["schema"] == SOLO_SEALED:
            continue
        if (row["target_object_id"], row["target_bytes"]) != (facts[t]["object_id"], facts[t]["bytes"]):
            reasons.add("LOCK_FIELD_MISMATCH")
        if row["raw_total_bytes"] != raw_total(row["target_bytes"]):
            reasons.add("ACCOUNTING_MISMATCH")
        if row["status"] == "ok":
            c = row["compressed_payload_bytes"]
            if (row["compressed_wrapper_bytes"], row["compressed_total_bytes"]) != (wrapper_bytes(c), compressed_total(c)):
                reasons.add("ACCOUNTING_MISMATCH")
            if (row["compress_exit"], row["decompress_exit"], row["compress_signal"], row["decompress_signal"]) != \
                    (0, 0, None, None):
                reasons.add("INCONSISTENT_ROW")

    def rows_of(t):
        return {k[1]: r for k, r in seen.items() if k[0] == t}

    published = {}
    for row in targets:
        if not valid_row(row, (TARGET, TARGET_SEALED)):
            reasons.add("SCHEMA")
            continue
        t = row["target_occurrence_id"]
        if t not in queries:
            reasons.add("FOREIGN_TARGET")
            continue
        if t in published:
            reasons.add("DUPLICATE_TARGET")
            continue
        published[t] = row
        if row["measurement_identity_sha256"] != ident["measurement_identity_sha256"]:
            reasons.add("IDENTITY_MISMATCH")
        is_sealed = row["schema"] == TARGET_SEALED
        if is_sealed != (facts[t]["split"] in sealed_splits):
            reasons.add("SEALING_VIOLATION")
        elif is_sealed:
            claim = {"split": facts[t]["split"], "query_status": queries[t]["status"],
                     "candidate_count": len(queries[t]["bases"]), **pair_counts(world, t, rows_of(t)),
                     "standalone_status": solo[t]["status"] if t in solo else None}
            if any(row[k] != v for k, v in claim.items()):
                reasons.add("INCONSISTENT_ROW")

    result = {"run_status": "INVALID", "invalid_reasons": sorted(reasons), "coverage": None, "oracle_kind": None,
              "targets": None, "digests": None, "retrieval_status": "NOT_EVALUATED", "retrieval_reasons": [],
              "metrics": None, "per_target": [], "retrieval": None,
              "populations": {"near": sum(facts[t]["split"] not in sealed_splits for t in near), "finite": 0,
                              "useful": 0, "sealed_excluded": sum(facts[t]["split"] in sealed_splits for t in near)}}
    if reasons:
        return result

    status = collections.Counter(r["status"] for r in seen.values())
    sealed_targets = [t for t in sorted(queries) if facts[t]["split"] in sealed_splits]
    coverage = {"expected_pairs": len(expected), "ok": status["ok"], "timeout": status["timeout"],
                "codec_error": status["codec_error"], "resource_limit": status["resource_limit"],
                "missing": len(expected) - len(seen) + status["not_run"],
                "sealed_pairs": sum(r["schema"] == PAIR_SEALED for r in seen.values()),
                "near_targets": len(near), "identity_targets": len(queries) - len(near),
                "sealed_targets": len(sealed_targets),
                "standalone_missing": sum(t not in solo or solo[t]["status"] == "not_run" for t in queries),
                "standalone_failed": sum(solo[t]["status"] in BOUNDED for t in solo),
                "targets_missing": sum(t not in published for t in queries)}
    result["coverage"] = coverage
    if coverage["missing"] or coverage["standalone_missing"] or coverage["targets_missing"]:
        result["run_status"] = "INCOMPLETE"
        return result
    failures = coverage["timeout"] + coverage["codec_error"] + coverage["resource_limit"] + coverage["standalone_failed"]

    derived = {}
    for t in sorted(queries):
        if t in sealed_targets:
            continue
        derived[t] = derive_target(world, t, rows_of(t), solo[t])
        if published[t] != derived[t]:  # a published full target row must equal the recomputation (K41)
            return {**result, "invalid_reasons": ["INCONSISTENT_ROW"], "coverage": None}
    result.update(run_status="COMPLETE_WITH_FAILURES" if failures else "COMPLETE",
                  oracle_kind="bounded" if failures else "exhaustive", targets=derived)
    scored = [t for t in near if t not in sealed_targets]
    coverage.update(near_empty=sum(derived[t]["oracle_delta_status"] == "empty_candidate_set" for t in scored),
                    near_all_failed=sum(derived[t]["oracle_delta_status"] == "all_pairs_failed" for t in scored),
                    near_finite=sum(derived[t]["oracle_delta_status"] == "finite" for t in scored),
                    near_useful=sum(derived[t]["useful_delta"] for t in scored))
    open_pairs = [r for r in pairs if r["schema"] == PAIR]
    result["digests"] = {
        "pairs_canonical_sha256": sha256(jsonl(open_pairs)),
        "standalone_canonical_sha256": sha256(jsonl([r for r in standalone if r["schema"] == SOLO])),
        "cost_projection_sha256": sha256(jsonl(open_pairs, TIMING)),
        "targets_canonical_sha256": sha256(jsonl(derived.values())),
        "sealed_commitments_sha256": sha256(jsonl([r for r in (*pairs, *standalone, *targets)
                                                    if r["schema"].endswith("-sealed.v1")], RUN_SPECIFIC))}
    result["populations"].update(finite=coverage["near_finite"], useful=coverage["near_useful"])
    if retrieval is not None:
        score_retrieval(result, world, scored, {t: rows_of(t) for t in scored}, retrieval)
    return result


def score_retrieval(result, world, scored, rows, retrieval):
    """Retrieval validation and metrics over the unsealed near population N (contract section 8)."""
    targets, queries, reasons = result["targets"], world["queries"], set()
    if any(not valid_row(r, ("delsk.oracle.retrieval.v1",)) for r in retrieval) or \
            len({(r["method_id"], r["K"]) for r in retrieval}) > 1:
        result.update(retrieval_status="INVALID", retrieval_reasons=["SCHEMA"])
        return
    k = retrieval[0]["K"] if retrieval else 1
    by_target = {}
    for row in retrieval:
        t = row["target_occurrence_id"]
        if t in by_target:
            reasons.add("RETRIEVAL_COVERAGE")
        by_target[t] = row
    if set(by_target) != set(scored):
        reasons.add("RETRIEVAL_COVERAGE")
    for t, row in by_target.items():
        allowed = {b for b, _ in queries[t]["bases"]} if t in queries else set()
        bases = row["bases"]
        if len(set(bases)) != len(bases):
            reasons.add("RETRIEVAL_DUPLICATE_BASE")
        if not set(bases) <= allowed:
            reasons.add("RETRIEVAL_FOREIGN_BASE")
        if len(bases) > k:
            reasons.add("RETRIEVAL_OVER_K")
        if row["encode_calls"] < len(bases):
            reasons.add("RETRIEVAL_CALLS")
    result["retrieval"] = {"K": k, "method_id": retrieval[0]["method_id"] if retrieval else SELF_METHOD,
                           "retrieval_sha256": sha256(jsonl(retrieval))}
    if reasons:
        result.update(retrieval_status="INVALID", retrieval_reasons=sorted(reasons))
        return
    finite = [t for t in scored if targets[t]["oracle_delta_status"] == "finite"]
    useful = [t for t in finite if targets[t]["useful_delta"]]
    hits, eps, achieved, regret, nregret = {}, dict.fromkeys(EPSILONS, 0), {}, {}, {}
    for t in scored:
        tr = targets[t]
        costs = [rows[t][b]["delta_total_bytes"] for b in by_target[t]["bases"] if rows[t][b]["status"] == "ok"]
        achieved[t] = min([tr["standalone_total_bytes"], *costs])
        regret[t] = achieved[t] - tr["oracle_total_bytes"]
        nregret[t] = Fraction(regret[t], max(tr["oracle_total_bytes"], TOLERANCE_FLOOR))
        if t in finite:
            od = tr["oracle_delta_total_bytes"]
            hits[t] = bool(set(by_target[t]["bases"]) & set(tr["oracle_tie_bases"]))
            for e in EPSILONS:
                eps[e] += any(100 * c <= 100 * od + max(100 * TOLERANCE_FLOOR, e * od) for c in costs)

    def dist(population, values):
        xs = [values[t] for t in population]
        if not xs:
            return dict.fromkeys(("sum", "p50", "p95", "max"))
        return {"sum": sum(xs, Fraction(0)), "p50": quantile7(xs, Fraction(1, 2)),
                "p95": quantile7(xs, Fraction(19, 20)), "max": max(xs)}

    result["metrics"] = {
        "strict": ratio(sum(hits[t] for t in finite), len(finite)),
        "useful": ratio(sum(hits[t] for t in useful), len(useful)),
        **{f"eps{e}": ratio(eps[e], len(finite)) for e in EPSILONS},
        "savings_capture": ratio(sum(targets[t]["standalone_total_bytes"] - achieved[t] for t in scored),
                                 sum(targets[t]["standalone_total_bytes"] - targets[t]["oracle_total_bytes"]
                                     for t in scored)),
        "call_reduction": ratio(sum(targets[t]["candidate_count"] for t in scored),
                                sum(by_target[t]["encode_calls"] for t in scored)),
        "regret_near": dist(scored, regret), "nregret_near": dist(scored, nregret),
        "regret_useful": dist(useful, regret), "nregret_useful": dist(useful, nregret)}
    result["per_target"] = [{"target_occurrence_id": t, "retrieved": by_target[t]["bases"],
                             "achieved_total_bytes": achieved[t], "byte_regret": regret[t],
                             "normalized_regret": nregret[t], "strict_hit": hits.get(t)} for t in scored]
    result["retrieval_status"] = "OK"


def g1(runs):
    """G1 over all attempts of one measurement identity (contract section 7). runs: dicts with github_run_id,
    run_status, cost_projection_sha256, targets_sha256, sealed_commitments_sha256, conformance, bundle_verified."""
    if any(r["run_status"] == "INVALID" for r in runs):
        return "INVALID", ["RUN_INVALID"]
    complete = [r for r in runs if r["run_status"] == "COMPLETE"]
    repeat = {(r["cost_projection_sha256"], r["targets_sha256"], r["sealed_commitments_sha256"]) for r in complete}
    if len(repeat) > 1:
        return "INVALID", ["REPEAT_MISMATCH"]
    blockers = sorted({f"RUN_{r['run_status']}" for r in runs if r["run_status"] != "COMPLETE"})
    verified = [r for r in complete if r["conformance"] is True and r["bundle_verified"] is True]
    if len(verified) < len(complete):
        blockers.append("CONFORMANCE_OR_BUNDLE")
    if len({r["github_run_id"] for r in verified}) < 2:
        blockers.append("REPEAT_MISSING")
    return ("NOT_PASSED", blockers) if blockers else ("PASS", [])


# --- durable documents ------------------------------------------------------------------------------------------------

def rational(value):
    if value is None:
        return "N/A"
    value = Fraction(value)
    return {"num": value.numerator, "den": value.denominator}


def self_retrieval(result, world):
    """Oracle self-retrieval sanity rows (R_K = ties) for evaluation.json; empty when targets are withheld."""
    if result["targets"] is None:
        return None
    scored = [t for t, v in result["targets"].items() if v["query_status"] == "near_duplicate"]
    k = max([1, *(len(result["targets"][t]["oracle_tie_bases"]) for t in scored)])
    return [{"schema": "delsk.oracle.retrieval.v1", "method_id": SELF_METHOD, "K": k, "target_occurrence_id": t,
             "bases": result["targets"][t]["oracle_tie_bases"],
             "encode_calls": len(result["targets"][t]["oracle_tie_bases"])} for t in scored]


def documents(result, world, evaluator):
    """coverage.json, summary.json, evaluation.json of one evaluation. evaluator: {evaluator_sha256, evaluator_source_sha}."""
    ident = world["identity"]["measurement_identity_sha256"]
    counts, invalid = result["coverage"], result["run_status"] == "INVALID"
    failed = None if counts is None else counts["timeout"] + counts["codec_error"] + counts["resource_limit"]
    coverage = {"schema": "delsk.oracle.coverage.v1", "measurement_identity_sha256": ident,
                "run_status": result["run_status"], "invalid_reasons": result["invalid_reasons"], "counts": counts,
                "pair_failure_rate": rational(None if invalid else ratio(failed, counts["expected_pairs"])),
                "standalone_failure_rate": rational(None if invalid else ratio(counts["standalone_failed"],
                                                                                len(world["queries"])))}
    digests = result["digests"] or dict.fromkeys(("pairs_canonical_sha256", "standalone_canonical_sha256",
                                                  "cost_projection_sha256", "targets_canonical_sha256",
                                                  "sealed_commitments_sha256"))
    per_split = []
    if result["targets"] is not None:
        sealed = set(world["sealed_splits"])
        for split in SPLITS:
            near = [t for t, q in world["queries"].items()
                    if q["status"] == "near_duplicate" and world["facts"][t]["split"] == split]
            rows = [result["targets"][t] for t in near if split not in sealed]
            per_split.append({"split": split, "sealed": split in sealed, "near_targets": len(near),
                              "near_useful": None if split in sealed else sum(r["useful_delta"] for r in rows),
                              "oracle_total_bytes_sum": None if split in sealed else
                              sum(r["oracle_total_bytes"] for r in rows),
                              "standalone_total_bytes_sum": None if split in sealed else
                              sum(r["standalone_total_bytes"] for r in rows)})
    summary = {"schema": "delsk.oracle.summary.v1", "measurement_identity_sha256": ident,
               "run_status": result["run_status"], "invalid_reasons": result["invalid_reasons"],
               "oracle_kind": result["oracle_kind"], **digests, "coverage_sha256": sha256(canonical(coverage)),
               **evaluator, "per_split": per_split}
    metrics = None if result["metrics"] is None else {
        k: {kk: rational(vv) for kk, vv in v.items()} if type(v) is dict else rational(v)
        for k, v in result["metrics"].items()}
    if result["run_status"] == "INVALID":
        metrics_status = "WITHHELD_INVALID"
    elif result["run_status"] == "INCOMPLETE":
        metrics_status = "WITHHELD_INCOMPLETE"
    else:
        metrics_status = "COMPUTED" if result["retrieval_status"] == "OK" else "WITHHELD_RETRIEVAL_INVALID"
    evaluation = {"schema": "delsk.oracle.evaluation.v1", "measurement_identity_sha256": ident, **evaluator,
                  "oracle_status": result["run_status"], "oracle_kind": result["oracle_kind"],
                  "metrics_status": metrics_status, "metrics": metrics,
                  "per_target": [{**p, "normalized_regret": rational(p["normalized_regret"])}
                                 for p in result["per_target"]],
                  "populations": result["populations"],
                  "retrieval": result["retrieval"] or {"K": 1, "method_id": SELF_METHOD,
                                                       "retrieval_sha256": sha256(b"")},
                  "retrieval_status": result["retrieval_status"], "retrieval_reasons": result["retrieval_reasons"],
                  "pairs_canonical_sha256": digests["pairs_canonical_sha256"],
                  "standalone_canonical_sha256": digests["standalone_canonical_sha256"]}
    d = schemas()["$defs"]
    for name, doc in (("coverage", coverage), ("summary", summary), ("evaluation", evaluation)):
        check(not schema_errors(doc, d[name]), f"{name}.json would violate its schema")
    return {"coverage.json": coverage, "summary.json": summary, "evaluation.json": evaluation}


# --- bundles ----------------------------------------------------------------------------------------------------------

def evaluator_identity(source_sha):
    check(bool(HEX40.match(source_sha or "")), "evaluator source SHA must be a 40-hex commit")
    return {"evaluator_sha256": sha256(Path(__file__).read_bytes()), "evaluator_source_sha": source_sha}


def committed(name):
    return (ORACLE / name).read_bytes()


def load_locks(directory, identity):
    """Candidate and corpus locks bound by the run identity: committed natural locks for pilot, bundled synthetic
    locks for smoke. Raises EvalError on any binding mismatch."""
    freeze = parse_doc(committed("freeze.json"))
    if identity["phase"] == "smoke":
        candidate_data, corpus_data = ((directory / n).read_bytes() for n in SMOKE_LOCKS)
        check(sha256(candidate_data) != freeze["bindings"]["candidate_lock_sha256"],
              "smoke run bound to the natural candidate lock")
    else:
        check(identity["phase"] == "pilot", f"phase {identity['phase']!r} is not evaluated by this slice")
        candidate_data = (WORK / "corpus" / "e1" / "candidate-lock.json").read_bytes()
        corpus_data = gzip.decompress((WORK / "corpus" / "pilot-v1" / "corpus-lock.json.gz").read_bytes())
        check((sha256(candidate_data), sha256(corpus_data)) == (freeze["bindings"]["candidate_lock_sha256"],
                                                                freeze["bindings"]["corpus_lock_sha256"]),
              "committed locks differ from the oracle freeze bindings")
    check(sha256(candidate_data) == identity["candidate_lock_sha256"], "candidate lock differs from run identity")
    check(sha256(corpus_data) == identity["corpus_lock_sha256"], "corpus lock differs from run identity")
    candidate, corpus = parse_doc(candidate_data), parse_doc(corpus_data)
    check(candidate["corpus_lock_sha256"] == identity["corpus_lock_sha256"], "candidate lock binds another corpus")
    return candidate, corpus


def check_identity(run, codec_lock_data):
    """Run identity against the committed contract bindings (BINDING_MISMATCH otherwise)."""
    errors = schema_errors(run, schemas()["$defs"]["run"])
    check(not errors, f"run.json schema: {errors[:3]}")
    ident = run["measurement_identity"]
    lock = parse_doc(codec_lock_data)
    check(codec_lock_data == committed("codec-lock.json"), "codec-lock.json differs from the committed codec lock")
    check(hc(ident) == run["measurement_identity_sha256"], "measurement_identity_sha256 != Hc(measurement_identity)")
    check(ident["contract_id"] == CONTRACT_ID and ident["contract_freeze_sha256"] == sha256(committed("freeze.json")),
          "contract freeze binding")
    check(ident["codec_lock_sha256"] == sha256(codec_lock_data), "codec lock binding")
    for role in ("delta", "standalone"):
        check(ident[role] == {k: lock["codecs"][role][k] for k in ("codec_id", "options_sha256")}, f"{role} codec ref")
    check(ident["sealed_splits"] == ["evaluation"], "sealed splits must be exactly the evaluation split")
    check(ident["measured_source_sha"] == run["github"]["sha"] == run["github"]["workflow_sha"],
          "measured source, GitHub and workflow SHA differ")
    check(run["github"]["run_id"] > 0 and run["github"]["run_attempt"] > 0, "run.json: GitHub run ID and attempt")
    return lock


def read_rows(directory, name, reasons):
    try:
        rows = parse_jsonl((directory / name).read_bytes())
    except (EvalError, ValueError, UnicodeDecodeError):
        reasons.add("SCHEMA")
        return []
    if any(type(r.get("target_occurrence_id")) is not str or type(r.get("schema")) is not str
           or type(r.get("base_object_id", "")) is not str for r in rows):
        reasons.add("SCHEMA")
        return []
    if [row_key(r) for r in rows] != sorted(row_key(r) for r in rows):
        reasons.add("NONCANONICAL")
    return rows


def evaluate_bundle(directory):
    """(run, world, result) of an evidence directory; file-level defects become INVALID reasons."""
    directory = Path(directory)
    run = parse_doc((directory / "run.json").read_bytes())
    lock = check_identity(run, (directory / "codec-lock.json").read_bytes())
    world = world_from_locks(*load_locks(directory, run["measurement_identity"]),
                             {**run["measurement_identity"], "measurement_identity_sha256":
                              run["measurement_identity_sha256"]}, lock)
    file_reasons = set()
    rows = {name: read_rows(directory, name, file_reasons) for name in ROW_FILES}
    if file_reasons:
        result = evaluate(world, [], [], [])
        return run, world, {**result, "run_status": "INVALID", "coverage": None, "targets": None, "digests": None,
                            "invalid_reasons": sorted(file_reasons | set(result["invalid_reasons"]))}
    result = evaluate(world, rows["pairs.jsonl"], rows["standalone.jsonl"], rows["targets.jsonl"])
    retrieval = self_retrieval(result, world)
    if retrieval is not None:
        result = evaluate(world, rows["pairs.jsonl"], rows["standalone.jsonl"], rows["targets.jsonl"], retrieval)
    return run, world, result


def checksums(directory):
    files = sorted(p for p in Path(directory).rglob("*") if p.is_file() and p.name != "checksums.sha256")
    return "".join(f"{sha256(p.read_bytes())}  {p.relative_to(directory).as_posix()}\n" for p in files)


def read_private(path):
    """Full rows the runner appended; a torn final line (crash mid-write) was never durable and is dropped."""
    data = Path(path).read_bytes() if Path(path).exists() else b""
    if data and not data.endswith(b"\n"):
        data = data[:data.rfind(b"\n") + 1]
    return [_decode(line.decode("utf-8")) for line in data.splitlines()]


def finalize(evidence, private, source_sha=None):
    """In-job step after the runner: seal the evaluation split, derive and seal target rows from the full rows,
    write pairs/standalone/targets JSONL, coverage/summary/evaluation and checksums. Returns the run status."""
    evidence, private = Path(evidence), Path(private)
    run = parse_doc((evidence / "run.json").read_bytes())
    lock = check_identity(run, (evidence / "codec-lock.json").read_bytes())
    ident = {**run["measurement_identity"], "measurement_identity_sha256": run["measurement_identity_sha256"]}
    world = world_from_locks(*load_locks(evidence, run["measurement_identity"]), ident, lock)
    sealed = set(world["sealed_splits"])
    full_pairs, full_solo = read_private(private / "pairs.full.jsonl"), read_private(private / "standalone.full.jsonl")

    def publish(row, seal):
        return seal(row) if world["facts"].get(row.get("target_occurrence_id"), {}).get("split") in sealed else row

    pairs = [publish(r, seal_pair) for r in full_pairs]
    standalone = [publish(r, seal_standalone) for r in full_solo]
    by_pair = collections.defaultdict(list)
    for r in full_pairs:
        by_pair[(r["target_occurrence_id"], r["base_object_id"])].append(r)
    by_solo = collections.defaultdict(list)
    for r in full_solo:
        by_solo[r["target_occurrence_id"]].append(r)
    targets = []
    for t, q in world["queries"].items():
        rows = {b: by_pair[(t, b)][0] for b, _ in q["bases"] if len(by_pair[(t, b)]) == 1}
        srow = by_solo[t][0] if len(by_solo[t]) == 1 else None
        if srow is None or srow["status"] == "not_run" or len(rows) != len(q["bases"]) or \
                any(r["status"] == "not_run" for r in rows.values()):
            continue  # not derivable: the evaluator counts it as a missing target row
        row = derive_target(world, t, rows, srow)
        targets.append(seal_target(row) if world["facts"][t]["split"] in sealed else row)
    for name, rows in (("pairs.jsonl", pairs), ("standalone.jsonl", standalone), ("targets.jsonl", targets)):
        (evidence / name).write_bytes(jsonl(rows))
    _, world, result = evaluate_bundle(evidence)
    evaluator = evaluator_identity(source_sha or run["measurement_identity"]["measured_source_sha"])
    for name, doc in documents(result, world, evaluator).items():
        (evidence / name).write_bytes(canonical(doc))
    (evidence / "checksums.sha256").write_text(checksums(evidence), encoding="utf-8")
    return result


def _bundle_errors(directory):
    directory = Path(directory)
    run = parse_doc((directory / "run.json").read_bytes())
    smoke = run["measurement_identity"]["phase"] == "smoke"
    wanted = set(BUNDLE_FILES) | (set(SMOKE_LOCKS) if smoke else set())
    entries = list(directory.rglob("*"))
    check(not any(p.is_symlink() for p in entries), "bundle contains a symlink")
    present = {p.relative_to(directory).as_posix() for p in entries if p.is_file()}
    check(present == wanted, f"files: missing {sorted(wanted - present)}, unexpected {sorted(present - wanted)}")
    check((directory / "checksums.sha256").read_text(encoding="utf-8") == checksums(directory),
          "checksums differ or the bundle is truncated")
    validate_tools(parse_doc((directory / "tools.json").read_bytes()), run)
    conformance = parse_doc((directory / "conformance.json").read_bytes())
    validate_conformance(conformance, run)
    _, world, result = evaluate_bundle(directory)
    recorded = parse_doc((directory / "evaluation.json").read_bytes())
    evaluator = {k: recorded[k] for k in ("evaluator_sha256", "evaluator_source_sha")}
    for name, doc in documents(result, world, evaluator).items():
        check((directory / name).read_bytes() == canonical(doc), f"{name} differs from the recomputation")
    return run, result, conformance


def verify(directory):
    """Errors for one evidence bundle; [] means every file recomputes byte for byte. Never prints sealed values."""
    try:
        _bundle_errors(directory)
    except (EvalError, KeyError, TypeError, ValueError, AttributeError, IndexError, OSError) as error:
        return [f"{Path(directory).name}: {type(error).__name__}: {str(error)[:300]}"]
    return []


def validate_tools(tools, run):
    """tools.json (delsk.oracle.tools.v1): build provenance of both codecs bound to run.json codec_builds."""
    check(tools["schema"] == "delsk.oracle.tools.v1" and set(tools) == TOOLS_KEYS, "tools.json: schema")
    check(tools["codec_lock_sha256"] == run["measurement_identity"]["codec_lock_sha256"], "tools.json: codec lock")
    builds = {b["codec_id"]: b for b in run["codec_builds"]}
    check(len(builds) == len(run["codec_builds"]) == 2, "run.json: codec_builds")
    for role in ("delta", "standalone"):
        c = tools["codecs"][role]
        check(set(c) == TOOLS_CODEC_KEYS, f"tools.json: {role} fields")
        b = builds.get(c["codec_id"])
        check(b is not None and (b["archive_sha256"], b["executable_sha256"], b["self_report_sha256"],
                                 b["build_argv_sha256"]) == (c["archive_sha256"], c["executable_sha256"],
                                                             sha256(c["self_report"].encode("utf-8")),
                                                             hc(c["build_argv"])), f"tools.json: {role} binding")


def validate_conformance(conformance, run):
    """conformance.json (delsk.oracle.conformance.v1) bound to run.json; PASS needs the committed golden record."""
    check(conformance["schema"] == "delsk.oracle.conformance.v1" and set(conformance) == CONFORMANCE_KEYS,
          "conformance.json: schema")
    check(conformance["codec_lock_sha256"] == run["measurement_identity"]["codec_lock_sha256"],
          "conformance.json: codec lock")
    checks = conformance["checks"]
    check(sorted(checks) == [f"C{i:02d}" for i in range(1, 15)], "conformance.json: checks C01-C14")
    verdict = "PASS" if all(c["status"] == "PASS" for c in checks.values()) else \
        "FAIL" if any(c["status"] == "FAIL" for c in checks.values()) else "CANDIDATE"
    check(conformance["verdict"] == verdict, "conformance.json: verdict")
    if verdict == "PASS":
        golden = parse_doc(committed("conformance.json"))
        check(conformance["golden"] == golden["golden"] and conformance["inputs_sha256"] == golden["inputs_sha256"],
              "conformance.json: PASS without the committed golden digests")
    executables = {b["codec_id"]: b["executable_sha256"] for b in run["codec_builds"]}
    check(set(executables.values()) == set(conformance["executables"].values()), "conformance.json: executables")
    check(all(b["conformance"] == ("PASS" if verdict == "PASS" else "FAIL") for b in run["codec_builds"]),
          "run.json: conformance status differs from conformance.json")


TOOLS_KEYS = {"schema", "codec_lock_sha256", "compiler", "make", "codecs", "source"}
TOOLS_CODEC_KEYS = {"codec_id", "archive_url", "archive_bytes", "archive_sha256", "archive_root", "archive_path",
                    "extracted_files",
                    "extracted_tree_sha256", "skipped_members", "build_argv", "build_cwd", "build_env",
                    "executable", "executable_bytes", "executable_sha256", "self_report"}
CONFORMANCE_KEYS = {"schema", "codec_lock_sha256", "executables", "inputs_sha256", "golden", "checks", "verdict"}


def bundle(artifact, results=RESULTS):
    """Retain a downloaded evidence artifact: copy into a staging sibling, write checksums, verify, rename.
    A missing, partial or invalid artifact leaves nothing under results."""
    artifact, results = Path(artifact), Path(results)
    run = parse_doc((artifact / "run.json").read_bytes())
    if results == RESULTS:
        check(run["measurement_identity"]["phase"] == "pilot", "only pilot runs are retained in the repository")
    dest = results / f"{run['github']['run_id']}-{run['github']['run_attempt']}"
    check(not dest.exists(), f"{dest.name} is already retained")
    results.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{dest.name}.", dir=results))
    try:
        names = set(BUNDLE_FILES) - {"checksums.sha256"}
        if run["measurement_identity"]["phase"] == "smoke":
            names |= set(SMOKE_LOCKS)
        for name in sorted(names):
            src = artifact / name
            check(src.is_file() and not src.is_symlink(), f"artifact lacks {name}")
            shutil.copyfile(src, stage / name)
        (stage / "checksums.sha256").write_text(checksums(stage), encoding="utf-8")
        check((artifact / "checksums.sha256").read_bytes() == (stage / "checksums.sha256").read_bytes(),
              "artifact checksums differ from its files")
        errors = verify(stage)
        check(not errors, "; ".join(errors))
        stage.rename(dest)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    return dest


def g1_bundles(directories):
    """G1 over retained pilot bundles of one measurement identity; unverifiable bundles count as not verified."""
    records, identities = [], set()
    for d in map(Path, directories):
        run = parse_doc((d / "run.json").read_bytes())
        summary = parse_doc((d / "summary.json").read_bytes())
        check(run["measurement_identity"]["phase"] == "pilot", "G1 is defined only for pilot runs")
        identities.add(run["measurement_identity_sha256"])
        conformance = parse_doc((d / "conformance.json").read_bytes())
        records.append({"github_run_id": run["github"]["run_id"], "run_status": summary["run_status"],
                        "cost_projection_sha256": summary["cost_projection_sha256"],
                        "targets_sha256": summary["targets_canonical_sha256"],
                        "sealed_commitments_sha256": summary["sealed_commitments_sha256"],
                        "conformance": conformance["verdict"] == "PASS", "bundle_verified": not verify(d)})
    check(len(identities) == 1, "G1 needs the attempts of exactly one measurement identity")
    return g1(records)


def main(argv):
    command, args = (argv[0], argv[1:]) if argv else (None, [])
    try:
        if command == "finalize" and len(args) in (2, 3):
            result = finalize(*args)
            print(f"oracle run status: {result['run_status']} {' '.join(result['invalid_reasons'])}".rstrip())
        elif command == "verify" and args:
            errors = [e for d in args for e in verify(d)]
            print("\n".join(errors) or f"verified {len(args)} bundle(s)")
            return 1 if errors else 0
        elif command == "bundle" and len(args) in (1, 2):
            print(f"retained {bundle(*args)}")
        elif command == "g1" and args:
            verdict, blockers = g1_bundles(args)
            print(f"G1: {verdict} {' '.join(blockers)}".rstrip())
            return 0 if verdict == "PASS" else 1
        else:
            print(__doc__, file=sys.stderr)
            return 2
    except (EvalError, KeyError, TypeError, ValueError, OSError) as error:
        print(f"{type(error).__name__}: {str(error)[:300]}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
