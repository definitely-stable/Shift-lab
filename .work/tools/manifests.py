"""DELSK-002 corpus and candidate manifest contracts (schemas *.v1).

Private research interfaces, not a Delsk public API. Stdlib only, no I/O
besides strict JSON loading. Validators return a list of error strings; an
empty list means valid. Contract prose: .work/corpus/README.md.
"""

import datetime as dt
import fnmatch
import hashlib
import json
import re
import unicodedata

SHA256 = re.compile(r"[0-9a-f]{64}\Z")
IDENT = re.compile(r"[a-z0-9][a-z0-9._-]*\Z")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
SPLITS = ("development", "calibration", "evaluation")
ARCHIVE_FORMATS = {"tar.gz", "tar.xz", "tar.bz2", "zip"}
MEMBER_TYPES = {"file", "dir", "symlink", "hardlink", "other"}
# Lock exclusions remove occurrences from eligibility, so each kind allows only
# reasons with a checkable predicate or, for manual reasons, recorded evidence.
# Per-query outcomes (self, exact target bytes, time, split, track, category cap)
# are consequences of the candidate rules and are never lock exclusions.
LOCK_EXCLUSIONS = {
    "source": {"license_blocked", "unknown_time"},
    "member": {"license_blocked", "non_regular_member", "not_source_suffix", "vendor_or_shared_origin_path"},
    "object": {"cross_split_content"},
    "occurrence": {"license_blocked"},
}
MANUAL_REASONS = {"license_blocked", "non_regular_member"}
PROVENANCE_KEYS = {"member_path", "transform", "options", "offset", "length"}
CANDIDATE_CATEGORIES = ("same_path_historical", "same_family_decoy", "foreign_family_decoy")
# P1 hard ceilings; a policy may be stricter, never looser.
P1_CAPS = {"acquired_bytes_max": 256 << 20, "materialized_bytes_max": 1 << 30,
           "planned_pairs_per_codec_max": 4096}
P1_FILE_RANGE = (64 << 10, 16 << 20)
P1_CHUNK_RANGE = (4 << 10, 64 << 10)
DAY = 86400


# --- canonical JSON -------------------------------------------------------

def _check_value(value, where="$"):
    if value is None or type(value) in (bool, int):
        return
    if type(value) is str:
        if unicodedata.normalize("NFC", value) != value:
            raise ValueError(f"{where}: string is not NFC")
        value.encode("utf-8")  # rejects lone surrogates
        return
    if type(value) is list:
        for i, item in enumerate(value):
            _check_value(item, f"{where}[{i}]")
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str or not key.isascii():
                raise ValueError(f"{where}: keys must be ASCII strings")
            _check_value(item, f"{where}.{key}")
        return
    raise ValueError(f"{where}: unsupported JSON value {type(value).__name__} (floats are forbidden)")


def canonical_bytes(value):
    """Exact file form: sorted ASCII keys, 2-space indent, UTF-8, LF, final newline."""
    _check_value(value)
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def file_sha256(value):
    """SHA-256 of the exact canonical file bytes of a manifest/policy."""
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def digest(value):
    """SHA-256 of compact canonical JSON; used for IDs, ranks and list hashes."""
    _check_value(value)
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject(token):
    raise ValueError(f"forbidden JSON number: {token}")


def loads_strict(data):
    """Parse manifest bytes; they must already be in canonical form."""
    if data.startswith(b"\xef\xbb\xbf"):
        raise ValueError("UTF-8 BOM is forbidden")
    value = json.loads(data.decode("utf-8"), object_pairs_hook=_no_duplicate_keys,
                       parse_float=_reject, parse_constant=_reject)
    if canonical_bytes(value) != data:
        raise ValueError("bytes are not in canonical form")
    return value


def rank(purpose, seed, *parts):
    """Deterministic, score-free ordering key."""
    return digest([purpose, seed, *parts])


# --- identities and paths -------------------------------------------------

def valid_member_path(path):
    """Normalized POSIX path relative to the archive root (top directory stripped)."""
    if type(path) is not str or not path or path != unicodedata.normalize("NFC", path):
        return False
    if path.startswith("/") or "\\" in path or re.match(r"[A-Za-z]:", path):
        return False
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in path):
        return False
    return all(part not in ("", ".", "..") for part in path.split("/"))


def occurrence_id(source_id, provenance):
    """Provenance identity; independent of content bytes and local paths."""
    return digest(["delsk.occurrence.v1", source_id, provenance])


def chunk_spans(size, unit):
    """Fixed-offset full chunks and the short-tail length (excluded, never padded)."""
    return [(offset, unit) for offset in range(0, size - unit + 1, unit)], size % unit


# --- time -----------------------------------------------------------------

def availability(time):
    """UTC epoch-second interval (lo, hi) of first public availability, or None.

    A date without zone may be any local day: UTC-12..UTC+14, so the interval
    is [day-14h, day+1d+12h]. Acquisition time and file mtimes are never used.
    """
    value = (time or {}).get("value")
    if value is None:
        return None
    if DATE.match(value):
        day = dt.datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
        start = int(day.timestamp())
        return start - 14 * 3600, start + DAY + 12 * 3600
    moment = dt.datetime.fromisoformat(value)
    if moment.tzinfo is None or moment.microsecond:
        raise ValueError(f"timestamp needs an explicit offset and whole seconds: {value}")
    second = int(moment.timestamp())
    return second, second


def time_eligible(base, target):
    """Base must be available strictly before the target could have appeared."""
    return base is not None and target is not None and base[1] < target[0]


# --- ancestry, splits and member selection --------------------------------

def ancestry_components(family_ids, edges):
    """Families joined by `merge` edges form one split unit; sorted tuples."""
    parent = {family: family for family in family_ids}

    def root(family):
        while parent[family] != family:
            parent[family] = parent[parent[family]]
            family = parent[family]
        return family

    for edge in edges:
        if edge["a"] not in parent or edge["b"] not in parent:
            raise ValueError(f"ancestry edge names unknown family: {edge['a']}-{edge['b']}")
        if edge["resolution"] == "merge":
            a, b = root(edge["a"]), root(edge["b"])
            parent[max(a, b)] = min(a, b)
    groups = {}
    for family in parent:
        groups.setdefault(root(family), []).append(family)
    return sorted(tuple(sorted(group)) for group in groups.values())


def assign_splits(components, split_counts, seed):
    """Map family -> split by hash order of component IDs (the smallest family ID).

    A component count other than the policy count stops sealing: no silent
    redistribution, the source policy must be reviewed.
    """
    expected = sum(count for _, count in split_counts)
    if len(components) != expected:
        raise ValueError(f"{len(components)} ancestry components, policy expects {expected}; review source policy")
    ordered = sorted(components, key=lambda component: rank("split", seed, component[0]))
    result, start = {}, 0
    for split, count in split_counts:
        for component in ordered[start:start + count]:
            for family in component:
                result[family] = split
        start += count
    return result


def stratum_of(size, strata):
    """Half-open [min_bytes, max_bytes) file strata."""
    for stratum in strata:
        if stratum["min_bytes"] <= size < stratum["max_bytes"]:
            return stratum["id"]
    return None


def family_globs(plan):
    return {f["family_id"]: [rule["glob"] for rule in f.get("exclude_globs", [])] for f in plan["families"]}


def path_exclusion(path, family_id, policy, globs):
    """(reason, detail) if a regular member path is not retained, else None."""
    rules = policy["member_rules"]
    if not path.endswith(tuple(rules["include_suffixes"])):
        return "not_source_suffix", ""
    for glob in [*rules["global_exclude_globs"], *globs.get(family_id, [])]:
        if fnmatch.fnmatchcase(path, glob):
            return "vendor_or_shared_origin_path", glob
    return None


def select_members(members, policy, family_globs):
    """Retain project-owned C/H members and pick one file-track member per stratum.

    members: dicts {source_id, family_id, path, size, type}; family_globs:
    {family_id: [glob, ...]}. Globs use fnmatch semantics (`*` crosses `/`).
    Selection key is rank("member", seed, family, path): it ignores the
    release, so the same path is preferred in every release, and never reads
    bytes, patch costs or scores.
    """
    seen, retained, exclusions = set(), [], []
    for member in sorted(members, key=lambda m: (m["source_id"], m["path"])):
        key = (member["source_id"], member["path"])
        if key in seen:
            raise ValueError(f"duplicate member path: {key}")
        seen.add(key)
        if not valid_member_path(member["path"]) or member["type"] not in MEMBER_TYPES:
            raise ValueError(f"unsafe member: {key}")
        if member["type"] == "dir":
            continue
        reason, detail = ("non_regular_member", "") if member["type"] != "file" else \
            path_exclusion(member["path"], member["family_id"], policy, family_globs) or (None, "")
        if reason:
            exclusions.append({"source_id": key[0], "path": key[1], "reason": reason, "detail": detail})
        else:
            retained.append(member)
    best = {}
    for member in retained:
        stratum = stratum_of(member["size"], policy["file_strata"])
        if stratum is None:
            continue
        slot = (member["source_id"], stratum)
        score = rank("member", policy["seed"], member["family_id"], member["path"])
        if slot not in best or score < best[slot][0]:
            best[slot] = (score, {**member, "stratum": stratum})
    selected = [best[slot][1] for slot in sorted(best)]
    return {"retained": retained, "selected": selected, "exclusions": exclusions}


# --- validators -----------------------------------------------------------

def _https(url):
    return type(url) is str and url.startswith("https://") and " " not in url


def _sorted_unique(items):
    return all(a < b for a, b in zip(items, items[1:]))


def _robust(validator):
    """Malformed input yields an error string instead of an exception."""
    def wrapper(*args):
        try:
            return validator(*args)
        except (AttributeError, KeyError, TypeError, ValueError, IndexError) as error:
            return [f"{validator.__name__}: malformed input: {error!r}"]
    wrapper.__name__, wrapper.__doc__ = validator.__name__, validator.__doc__
    return wrapper


@_robust
def validate_source_plan(plan):
    errors = []
    err = errors.append
    if plan.get("schema") != "delsk.corpus.source-plan.v1":
        err("source plan: unexpected schema")
    if plan.get("status") != "PROPOSED":
        err("source plan: status must be PROPOSED (a plan is never a frozen corpus)")
    families = plan.get("families", [])
    ids = [family.get("family_id") for family in families]
    if not ids or len(set(ids)) != len(ids) or not all(type(i) is str and IDENT.match(i) for i in ids):
        err("source plan: family IDs must be unique lowercase identifiers")
    if ids != sorted(ids):
        err("source plan: families must be sorted by family_id")
    globs = {}
    release_ids = []
    for family in families:
        fid = family.get("family_id")
        license_ = family.get("license", {})
        if not license_.get("spdx") or not _https(license_.get("evidence_url")):
            err(f"{fid}: license needs spdx and https evidence_url")
        if license_.get("status") not in {"PENDING_SNAPSHOT_REVIEW", "REVIEWED"}:
            err(f"{fid}: unknown license status")
        globs[fid] = set()
        for rule in family.get("exclude_globs", []):
            glob = rule.get("glob")
            if type(glob) is not str or not glob or glob.startswith("/") or not rule.get("reason"):
                err(f"{fid}: exclude glob needs a relative pattern and a reason")
            globs[fid].add(glob)
        releases = family.get("releases", [])
        ordinals = [r.get("ordinal") for r in releases]
        if any(type(o) is not int for o in ordinals) or ordinals != list(range(1, len(releases) + 1)):
            err(f"{fid}: release ordinals must be 1..n in order")
        previous = None
        for release in releases:
            rid = release.get("release_id")
            release_ids.append(rid)
            archive = release.get("archive", {})
            if not _https(archive.get("url")) or archive.get("format") not in ARCHIVE_FORMATS:
                err(f"{rid}: archive needs https url and known format")
            if archive.get("sha256") is not None:
                err(f"{rid}: a plan carries no acquisition hash; hashes come only from a CI lock")
            time = release.get("time")
            try:
                interval = availability(time)
            except (TypeError, ValueError) as error:
                err(f"{rid}: bad time: {error}")
                interval = None
            if interval and not _https(time.get("evidence_url")):
                err(f"{rid}: release time needs https evidence_url")
            if previous and interval and not time_eligible(previous, interval):
                err(f"{rid}: release interval does not follow the previous release")
            previous = interval or previous
    if len(set(release_ids)) != len(release_ids) or not all(type(r) is str and IDENT.match(r) for r in release_ids):
        err("source plan: release IDs must be unique lowercase identifiers")
    for edge in plan.get("ancestry_edges", []):
        if edge.get("a") not in globs or edge.get("b") not in globs:
            err(f"ancestry edge with unknown family: {edge.get('a')}-{edge.get('b')}")
            continue
        if edge.get("resolution") not in {"merge", "path_excluded", "no_shared_payload"} or not edge.get("evidence"):
            err(f"ancestry edge {edge['a']}-{edge['b']}: needs resolution and evidence")
        if edge.get("resolution") == "path_excluded":
            listed = set(edge.get("globs", []))
            if not listed or not listed <= globs[edge["a"]] | globs[edge["b"]]:
                err(f"ancestry edge {edge['a']}-{edge['b']}: path_excluded must name existing exclude globs")
    return errors


@_robust
def validate_selection_policy(policy):
    errors = []
    err = errors.append
    if policy.get("schema") != "delsk.corpus.selection-policy.v1":
        err("selection policy: unexpected schema")
    if type(policy.get("seed")) is not int:
        err("selection policy: seed must be an integer")
    strata = policy.get("file_strata", [])
    bounds = [(s.get("min_bytes"), s.get("max_bytes")) for s in strata]
    if not strata or any(type(lo) is not int or type(hi) is not int or lo >= hi for lo, hi in bounds):
        err("selection policy: file strata need integer min < max")
    elif bounds[0][0] < P1_FILE_RANGE[0] or bounds[-1][1] > P1_FILE_RANGE[1] or \
            any(a[1] > b[0] for a, b in zip(bounds, bounds[1:])):
        err("selection policy: file strata must be ascending, disjoint and inside the P1 file range")
    tracks = policy.get("tracks", [])
    track_ids = [t.get("id") for t in tracks]
    if len(set(track_ids)) != len(track_ids) or "file" not in track_ids:
        err("selection policy: track IDs must be unique and include file")
    for track in tracks:
        if track.get("lane") not in {"historical", "modeled"} or not track.get("transform"):
            err(f"track {track.get('id')}: needs lane and transform")
        if (track.get("transform") == "canonical_tar_gzip_v1") != (type(track.get("compresslevel")) is int):
            err(f"track {track.get('id')}: compresslevel exactly on canonical_tar_gzip_v1")
        unit = track.get("unit_bytes")
        if track.get("per_member") is not (track.get("id") == "file" or unit is not None):
            err(f"track {track.get('id')}: per_member must be true exactly for file and chunk tracks")
        if unit is not None and not (type(unit) is int and P1_CHUNK_RANGE[0] <= unit <= P1_CHUNK_RANGE[1]):
            err(f"track {track.get('id')}: chunk unit outside P1 chunk range")
    counts = policy.get("splits", {}).get("counts", [])
    if [name for name, _ in counts] != list(SPLITS) or any(type(n) is not int or n < 1 for _, n in counts):
        err("selection policy: split counts must list development, calibration, evaluation with n >= 1")
    caps = policy.get("caps", {})
    for name, ceiling in P1_CAPS.items():
        if type(caps.get(name)) is not int or not 0 < caps[name] <= ceiling:
            err(f"selection policy: cap {name} missing or above the P1 ceiling")
    cand = policy.get("candidates", {})
    per_target = sum(cand.get(f"{c}_max", -1) for c in CANDIDATE_CATEGORIES)
    max_targets = policy.get("targets", {}).get("max_targets")
    if any(type(cand.get(f"{c}_max")) is not int or cand[f"{c}_max"] < 0 for c in CANDIDATE_CATEGORIES):
        err("selection policy: candidate category caps must be non-negative integers")
    elif type(max_targets) is not int or max_targets < 1:
        err("selection policy: max_targets must be a positive integer")
    elif max_targets * per_target > caps.get("planned_pairs_per_codec_max", 0):
        err("selection policy: max_targets x candidate caps can exceed the pair cap")
    ordinals = policy.get("targets", {}).get("release_ordinals")
    if not ordinals or any(type(o) is not int or o < 2 for o in ordinals) or not _sorted_unique(ordinals):
        err("selection policy: target release ordinals must be sorted unique integers >= 2")
    if any(cand.get(flag) is not True for flag in ("same_split", "same_track", "temporal")):
        err("selection policy: candidates must require same_split, same_track and temporal eligibility")
    if cand.get("pad_missing_categories") is not False:
        err("selection policy: missing candidate categories must never be padded")
    forbidden = set(policy.get("forbidden_selection_inputs", []))
    if not {"patch_bytes", "encoder_output", "scorer_output", "compressibility"} <= forbidden:
        err("selection policy: score/encoder-derived inputs must be explicitly forbidden")
    return errors


def _family_splits(plan, policy):
    families = [f["family_id"] for f in plan["families"]]
    components = ancestry_components(families, plan.get("ancestry_edges", []))
    return components, assign_splits(components, policy["splits"]["counts"], policy["seed"])


def _track_options(track, toolchain):
    """Non-chunk provenance options: compressor identity enters the occurrence ID."""
    if track["transform"] == "canonical_tar_gzip_v1":
        return {"compresslevel": track["compresslevel"], "zlib_runtime": toolchain.get("zlib_runtime")}
    return {}


@_robust
def validate_corpus_lock(lock, plan, policy):
    errors = []
    err = errors.append
    if lock.get("schema") != "delsk.corpus.lock.v1":
        return ["corpus lock: unexpected schema"]
    upstream = validate_source_plan(plan) + validate_selection_policy(policy)
    if upstream:
        return [f"corpus lock: invalid input: {e}" for e in upstream]
    if lock.get("source_plan_sha256") != file_sha256(plan):
        err("corpus lock: source plan hash mismatch")
    if lock.get("selection_policy_sha256") != file_sha256(policy):
        err("corpus lock: selection policy hash mismatch")
    try:
        components, family_split = _family_splits(plan, policy)
    except ValueError as error:
        return errors + [f"corpus lock: {error}"]
    expected_components = [{"families": list(c), "split": family_split[c[0]]} for c in components]
    if lock.get("components") != expected_components:
        err("corpus lock: components/splits differ from the deterministic assignment")

    planned = {r["release_id"]: (f["family_id"], r) for f in plan["families"] for r in f["releases"]}
    sources = {}
    if not _sorted_unique([s.get("source_id") for s in lock.get("sources", [])]):
        err("corpus lock: sources must be sorted by unique source_id")
    for source in lock.get("sources", []):
        sid = source.get("source_id")
        if sid in sources or sid not in planned:
            err(f"source {sid}: duplicate or not in source plan")
            continue
        family, release = planned[sid]
        if source.get("family_id") != family or source.get("url") != release["archive"]["url"]:
            err(f"source {sid}: family/url differ from source plan")
        size = source.get("archive_bytes")
        if not SHA256.match(str(source.get("archive_sha256"))) or type(size) is not int or size <= 0:
            err(f"source {sid}: needs archive_sha256 and positive archive_bytes")
        sources[sid] = {**source, "interval": availability(release.get("time")),
                        "ordinal": release["ordinal"]}
    if set(sources) != set(planned):
        err("corpus lock: every planned release needs a source record (failures stop the lock)")
    acquired = sum(s["archive_bytes"] for s in sources.values() if type(s.get("archive_bytes")) is int)
    if acquired > policy["caps"]["acquired_bytes_max"]:
        err("corpus lock: acquired bytes exceed cap")
    materialized = lock.get("materialized_bytes")
    if type(materialized) is not int or not 0 <= materialized <= policy["caps"]["materialized_bytes_max"]:
        err("corpus lock: materialized_bytes missing or above cap")

    tracks = {t["id"]: t for t in policy["tracks"]}
    globs = family_globs(plan)
    toolchain = lock.get("toolchain")
    if type(toolchain) is not dict or set(toolchain) != {"python", "zlib_runtime", "materializer_sha256"} \
            or not all(type(v) is str and v for v in toolchain.values()) \
            or not SHA256.match(toolchain["materializer_sha256"]):
        err("corpus lock: toolchain needs python, zlib_runtime and materializer_sha256")
        toolchain = {}
    occurrences = lock.get("occurrences", [])
    if not occurrences:
        err("corpus lock: no occurrences; an empty corpus cannot be sealed")
    ids = [o.get("occurrence_id") for o in occurrences]
    if not _sorted_unique(ids):
        err("corpus lock: occurrences must be sorted by unique occurrence_id")
    by_id, sizes, splits_by_object, file_objects, positions = {}, {}, {}, {}, set()
    for occ in occurrences:
        oid, source = occ.get("occurrence_id"), sources.get(occ.get("source_id"))
        prov, track = occ.get("provenance", {}), tracks.get(occ.get("track"))
        by_id[oid] = occ
        if source is None or track is None:
            err(f"occurrence {oid}: unknown source or track")
            continue
        if not SHA256.match(str(occ.get("object_id"))) or type(occ.get("bytes")) is not int or occ["bytes"] < 0:
            err(f"occurrence {oid}: invalid object_id or bytes")
            continue
        if type(prov) is not dict or set(prov) != PROVENANCE_KEYS:
            err(f"occurrence {oid}: provenance must have exactly {sorted(PROVENANCE_KEYS)}")
            continue
        position = (occ["source_id"], occ["track"], prov["member_path"], prov["offset"])
        if position in positions:
            err(f"occurrence {oid}: duplicate (source, track, member_path, offset)")
        positions.add(position)
        if oid != occurrence_id(occ["source_id"], prov):
            err(f"occurrence {oid}: id does not match provenance")
        if occ.get("family_id") != source["family_id"]:
            err(f"occurrence {oid}: family differs from its source")
        if occ.get("split") != family_split.get(source["family_id"]):
            err(f"occurrence {oid}: split differs from its ancestry component")
        if prov.get("transform") != track["transform"]:
            err(f"occurrence {oid}: transform does not match track")
        path = prov.get("member_path")
        if (path is not None) != bool(track.get("per_member")) or (path is not None and not valid_member_path(path)):
            err(f"occurrence {oid}: member_path invalid for track")
        elif path is not None and path_exclusion(path, source["family_id"], policy, globs):
            err(f"occurrence {oid}: member_path is not a retained member (suffix/vendor/shared-origin rules)")
        unit = track.get("unit_bytes")
        if unit is not None:
            offset = prov.get("offset")
            if prov.get("options") != {"unit_bytes": unit} or prov.get("length") != unit or occ["bytes"] != unit \
                    or type(offset) is not int or offset < 0 or offset % unit:
                err(f"occurrence {oid}: chunk span invalid")
            parent_bytes = occ.get("parent_bytes")
            if not SHA256.match(str(occ.get("parent_object_id"))) or type(parent_bytes) is not int:
                err(f"occurrence {oid}: chunk needs parent_object_id and parent_bytes")
            elif type(offset) is int and offset + unit > parent_bytes:
                err(f"occurrence {oid}: chunk span exceeds parent_bytes")
        elif prov["options"] != _track_options(track, toolchain) or prov["offset"] is not None or prov["length"] is not None \
                or occ.get("parent_object_id") is not None or occ.get("parent_bytes") is not None:
            err(f"occurrence {oid}: options must match the track/toolchain; span/parent only on chunk tracks")
        if occ["track"] == "file":
            if occ.get("stratum") != stratum_of(occ["bytes"], policy["file_strata"]) or occ.get("stratum") is None:
                err(f"occurrence {oid}: stratum does not match size")
            file_objects[(occ["source_id"], path)] = (occ["object_id"], occ["bytes"])
        elif occ.get("stratum") is not None:
            err(f"occurrence {oid}: stratum only allowed on file track")
        if sizes.setdefault(occ["object_id"], occ["bytes"]) != occ["bytes"]:
            err(f"object {occ['object_id']}: same content id with different sizes")
        splits_by_object.setdefault(occ["object_id"], set()).add(occ.get("split"))
    for occ in occurrences:
        parent = file_objects.get((occ.get("source_id"), (occ.get("provenance") or {}).get("member_path")))
        if occ.get("parent_object_id") and parent and parent != (occ["parent_object_id"], occ.get("parent_bytes")):
            err(f"occurrence {occ['occurrence_id']}: parent_object_id/parent_bytes differ from the file occurrence")

    exclusions = lock.get("exclusions", [])
    keys = [(e.get("kind"), e.get("subject"), e.get("reason")) for e in exclusions]
    if not _sorted_unique(keys):
        err("corpus lock: exclusions must be sorted and unique by (kind, subject, reason)")
    for exclusion in exclusions:
        err_exclusion = _exclusion_error(exclusion, by_id, sources, splits_by_object, policy, globs)
        if err_exclusion:
            err(f"exclusion {exclusion.get('subject')}: {err_exclusion}")
    excluded_objects = {s for k, s, r in keys if k == "object" and r == "cross_split_content"}
    for object_id, splits in sorted(splits_by_object.items()):
        if len(splits) > 1 and object_id not in excluded_objects:
            err(f"object {object_id}: occurs in splits {sorted(splits)} without cross_split_content exclusion")
    return errors


def _exclusion_error(exclusion, by_id, sources, splits_by_object, policy, globs):
    kind, subject, reason = exclusion.get("kind"), exclusion.get("subject"), exclusion.get("reason")
    if set(exclusion) != {"kind", "subject", "reason", "detail", "evidence_url"}:
        return "needs exactly kind, subject, reason, detail, evidence_url"
    if reason not in LOCK_EXCLUSIONS.get(kind, ()):
        return f"reason {reason} not allowed for kind {kind}"
    if reason in MANUAL_REASONS:
        if not exclusion["detail"] or not _https(exclusion["evidence_url"]):
            return f"manual reason {reason} needs detail and https evidence_url"
    elif exclusion["evidence_url"] is not None:
        return "evidence_url only for manual reasons"
    if kind == "source":
        if subject not in sources:
            return "unknown source"
        if reason == "unknown_time" and sources[subject]["interval"] is not None:
            return "source has a known release time"
    elif kind == "occurrence" and subject not in by_id:
        return "unknown occurrence"
    elif kind == "object" and len(splits_by_object.get(subject, ())) < 2:
        return "cross_split_content needs an object present in more than one split"
    elif kind == "member":
        source_id, _, path = str(subject).partition(":")
        if source_id not in sources or not valid_member_path(path):
            return "member subject must be source_id:member_path"
        if reason in {"not_source_suffix", "vendor_or_shared_origin_path"}:
            found = path_exclusion(path, sources[source_id]["family_id"], policy, globs)
            if found is None or found[0] != reason or found[1] != exclusion["detail"]:
                return f"path rules give {found}, not ({reason}, {exclusion['detail']!r})"
    return None


def excluded_occurrences(lock):
    """Occurrence IDs removed by object, occurrence, source or member (`source_id:path`) exclusions."""
    subjects = {(e["kind"], e["subject"]) for e in lock.get("exclusions", [])}
    return {o["occurrence_id"] for o in lock["occurrences"]
            if ("occurrence", o["occurrence_id"]) in subjects or ("object", o["object_id"]) in subjects
            or ("source", o["source_id"]) in subjects
            or ("member", f"{o['source_id']}:{o['provenance']['member_path']}") in subjects}


def _eligible(base, target, sources, excluded):
    return (base["occurrence_id"] not in excluded
            and base["split"] == target["split"] and base["track"] == target["track"]
            and time_eligible(sources[base["source_id"]], sources[target["source_id"]]))


def _position(occ):
    prov = occ["provenance"]
    return occ["family_id"], prov.get("member_path"), prov.get("offset")


def _category(eligible, target):
    """Audit-only relatedness; never a scorer input."""
    if any(_position(o) == _position(target) for o in eligible):
        return "same_path_historical"
    if any(o["family_id"] == target["family_id"] for o in eligible):
        return "same_family_decoy"
    return "foreign_family_decoy"


@_robust
def validate_candidate_lock(clock, lock, plan, policy):
    """Precondition: validate_corpus_lock(lock, plan, policy) returned no errors."""
    errors = []
    err = errors.append
    if clock.get("schema") != "delsk.candidate.lock.v1":
        return ["candidate lock: unexpected schema"]
    if clock.get("corpus_lock_sha256") != file_sha256(lock):
        err("candidate lock: corpus lock hash mismatch")
    if clock.get("selection_policy_sha256") != file_sha256(policy):
        err("candidate lock: selection policy hash mismatch")
    sources = {r["release_id"]: availability(r.get("time")) for f in plan["families"] for r in f["releases"]}
    ordinals = {r["release_id"]: r["ordinal"] for f in plan["families"] for r in f["releases"]}
    occurrences = {o["occurrence_id"]: o for o in lock["occurrences"]}
    by_object = {}
    for occ in lock["occurrences"]:
        by_object.setdefault(occ["object_id"], []).append(occ)
    excluded = excluded_occurrences(lock)
    cand = policy["candidates"]
    queries = clock.get("queries", [])
    targets = [q.get("target") for q in queries]
    if not _sorted_unique(targets):
        err("candidate lock: queries must be sorted by unique target occurrence")
    near, pairs = 0, 0
    for query in queries:
        tid, target = query.get("target"), occurrences.get(query.get("target"))
        if target is None:
            err(f"query {tid}: unknown target occurrence")
            continue
        if target["occurrence_id"] in excluded:
            err(f"query {tid}: target is excluded")
        if ordinals[target["source_id"]] not in policy["targets"]["release_ordinals"]:
            err(f"query {tid}: target release not allowed")
        if sources[target["source_id"]] is None:
            err(f"query {tid}: target without known time")
        bases = query.get("bases", [])
        object_ids = [b.get("object_id") for b in bases]
        if not _sorted_unique(object_ids):
            err(f"query {tid}: bases must be sorted unique content IDs")
        if type(query.get("candidate_count")) is not int or query["candidate_count"] != len(bases) or query.get("candidate_list_sha256") != digest(object_ids):
            err(f"query {tid}: candidate count/hash mismatch")
        status, duplicate = query.get("status"), occurrences.get(query.get("duplicate_of"))
        identical = [o for o in by_object[target["object_id"]] if _eligible(o, target, sources, excluded)]
        if status == "identity_only":
            if duplicate is None or duplicate not in identical:
                err(f"query {tid}: identity_only needs duplicate_of = an eligible occurrence with identical bytes")
            if bases:
                err(f"query {tid}: identity_only target must not plan encoder pairs")
        elif status == "near_duplicate":
            if query.get("duplicate_of") is not None or identical:
                err(f"query {tid}: an eligible identical base exists; status must be identity_only")
        else:
            err(f"query {tid}: unknown status")
        counts = dict.fromkeys(CANDIDATE_CATEGORIES, 0)
        for base in bases:
            oid, rep = base.get("object_id"), occurrences.get(base.get("representative"))
            if oid == target["object_id"]:
                err(f"query {tid}: self or exact target bytes in C_t")
                continue
            if rep is None or rep["object_id"] != oid:
                err(f"query {tid}: base {oid} representative missing or has other content")
                continue
            eligible = sorted((o for o in by_object[oid] if _eligible(o, target, sources, excluded)),
                              key=lambda o: o["occurrence_id"])
            if not eligible:
                err(f"query {tid}: base {oid} is not eligible (split/track/time/exclusion)")
                continue
            if rep["occurrence_id"] != eligible[0]["occurrence_id"]:
                err(f"query {tid}: base {oid} representative is not the smallest eligible occurrence")
            category = _category(eligible, target)
            if base.get("category") != category:
                err(f"query {tid}: base {oid} audit category must be {category}")
            counts[category] += 1
        for category, count in counts.items():
            if count > cand[f"{category}_max"]:
                err(f"query {tid}: {category} exceeds cap")
        if status == "near_duplicate":
            near += 1
            pairs += len(bases)
    if near == 0:
        err("candidate lock: no near_duplicate target; an empty universe cannot be sealed")
    if near > policy["targets"]["max_targets"]:
        err("candidate lock: too many near-duplicate targets")
    if type(clock.get("planned_pairs_per_codec")) is not int or clock["planned_pairs_per_codec"] != pairs:
        err("candidate lock: planned_pairs_per_codec differs from the sum of |C_t|")
    if pairs > policy["caps"]["planned_pairs_per_codec_max"]:
        err("candidate lock: planned pairs exceed cap")
    return errors
