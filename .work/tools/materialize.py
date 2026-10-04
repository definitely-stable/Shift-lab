"""DELSK-002 Slice D: safe acquisition and deterministic materialization (pilot-v1).

Stdlib only. Runs only in GitHub Actions as the foundation.yml workloads
`materialize-discover` and `materialize-verify`: natural data is never
downloaded on a workstation. Payload bytes stay in memory and are never
written; every output is a manifest.

    python3 materialize.py discover OUT_DIR   # plan URLs -> proposed locks
    python3 materialize.py verify OUT_DIR     # committed locks -> exact re-materialization

discover fetches every planned archive (https plan URLs only, streamed under
the acquired-bytes cap), expands it in memory with path, link, duplicate and
expansion checks, applies the selection policy and transforms, validates the
full delsk.corpus.lock.v1 and writes source-lock.json, licenses.json,
materialization.json and corpus-lock.json.gz. verify repeats the pipeline
against the committed pilot-v1 files: archive size and SHA-256 must equal the
source lock, and the three committed files must be reproduced byte for byte.
report.json is written in every case. Contract prose: .work/corpus/README.md.
"""

import bz2
import collections
import datetime as dt
import gzip
import hashlib
import http.client
import io
import json
import lzma
import os
from pathlib import Path
import platform
import re
import stat
import sys
import tarfile
import time
import traceback
import unicodedata
import urllib.error
import urllib.request
import zipfile
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import manifests as m  # noqa: E402

CORPUS = Path(__file__).resolve().parents[1] / "corpus"
PILOT = CORPUS / "pilot-v1"
LOCK_FILES = ("source-lock.json", "licenses.json", "materialization.json")
READ_BLOCK = 1 << 20
ATTEMPTS = 3
TIMEOUT_SECONDS = 60
USER_AGENT = "delsk-materialize/1 (+https://github.com/definitely-stable/Shift-lab)"
LICENSE_FILE = re.compile(r"(?i)(licen[cs]e|copying|copyright)([._-][^/]*)?\Z")
NOTICE = re.compile(r"(?i)copyright")
SPDX = re.compile(r"SPDX-License-Identifier:\s*([A-Za-z0-9.+()-]+(?:\s+(?:OR|AND|WITH)\s+[A-Za-z0-9.+()-]+)*)")
NOTICES_PER_FAMILY = 100
NOTICE_PATHS = 5
NOTICE_CHARS = 200
EXPANDERS = {"tar.gz": gzip.open, "tar.xz": lzma.open, "tar.bz2": bz2.open}


class MaterializeError(Exception):
    """Acquisition or materialization stops; nothing is substituted or trimmed."""


class Transient(Exception):
    """Retryable transfer failure (truncated body)."""


def sha256(data):
    return hashlib.sha256(data).hexdigest()


# --- acquisition ------------------------------------------------------------

class _HttpsOnlyRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.startswith("https://"):
            raise MaterializeError(f"redirect to a non-https URL refused: {newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def read_capped(response, max_bytes):
    """Stream a body; stop past max_bytes; a declared Content-Length must match exactly."""
    declared = response.headers.get("Content-Length")
    if declared is not None and int(declared) > max_bytes:
        raise MaterializeError(f"declared size {declared} exceeds the cap {max_bytes}")
    body = bytearray()
    while block := response.read(READ_BLOCK):
        body += block
        if len(body) > max_bytes:
            raise MaterializeError(f"body exceeds the cap {max_bytes}")
    if declared is not None and len(body) != int(declared):
        raise Transient(f"truncated body: {len(body)} of {declared} bytes")
    return bytes(body)


def fetch(url, max_bytes, open_url=None, sleep=time.sleep):
    """GET an https plan URL under a byte cap: (body, final_url, attempts).

    Retries only network errors, 5xx and truncated bodies; 4xx, caps and
    non-https redirects stop at once.
    """
    if not url.startswith("https://"):
        raise MaterializeError(f"not an https URL: {url}")
    open_url = open_url or urllib.request.build_opener(_HttpsOnlyRedirect).open
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"})
    for attempt in range(1, ATTEMPTS + 1):
        try:
            with open_url(request, timeout=TIMEOUT_SECONDS) as response:
                return read_capped(response, max_bytes), response.geturl(), attempt
        except urllib.error.HTTPError as error:
            if error.code < 500 or attempt == ATTEMPTS:
                raise MaterializeError(f"{url}: HTTP {error.code}") from None
        except (Transient, OSError, http.client.HTTPException) as error:
            if attempt == ATTEMPTS:
                raise MaterializeError(f"{url}: {type(error).__name__}: {error}") from None
        sleep(2 ** attempt)


# --- safe expansion -----------------------------------------------------------

def expand(data, fmt, limit):
    """Members of an archive as (name, kind, data|None); kind file/dir/symlink/hardlink/other.

    Decompression and member reads are bounded by `limit` expanded bytes.
    Nothing is written to disk, so links are never followed.
    """
    entries, expanded = [], 0
    if fmt == "zip":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                for info in archive.infolist():
                    mode = info.external_attr >> 16
                    if info.flag_bits & 0x1:
                        raise MaterializeError(f"encrypted zip member: {info.filename!r}")
                    if info.is_dir():
                        entries.append((info.filename.rstrip("/"), "dir", None))
                    elif stat.S_ISLNK(mode):
                        entries.append((info.filename, "symlink", None))
                    elif stat.S_IFMT(mode) and not stat.S_ISREG(mode):
                        entries.append((info.filename, "other", None))
                    else:
                        if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                            raise MaterializeError(f"unsupported zip compression: {info.filename!r}")
                        with archive.open(info) as member:
                            content = member.read(limit - expanded + 1)
                        expanded += len(content)
                        if expanded > limit:
                            raise MaterializeError(f"expansion exceeds the cap {limit}")
                        entries.append((info.filename, "file", content))
        except (zipfile.BadZipFile, zlib.error, EOFError) as error:
            raise MaterializeError(f"corrupt zip: {error}") from None
        return entries, expanded
    if fmt not in EXPANDERS:
        raise MaterializeError(f"unknown archive format: {fmt}")
    try:
        with EXPANDERS[fmt](io.BytesIO(data)) as stream:
            raw = stream.read(limit + 1)
    except (EOFError, OSError, lzma.LZMAError, zlib.error) as error:
        raise MaterializeError(f"corrupt or truncated {fmt} stream: {error}") from None
    if len(raw) > limit:
        raise MaterializeError(f"expansion exceeds the cap {limit}")
    try:
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
            for info in archive:
                if info.issparse() or not (info.isreg() or info.isdir() or info.issym() or info.islnk()):
                    entries.append((info.name, "other", None))
                elif info.isreg():
                    entries.append((info.name, "file", archive.extractfile(info).read()))
                else:
                    entries.append((info.name, "dir" if info.isdir() else "symlink" if info.issym() else "hardlink",
                                    None))
    except tarfile.TarError as error:
        raise MaterializeError(f"corrupt tar: {error}") from None
    return entries, len(raw)


def normalize(entries):
    """(top_dir, members) with exactly one top-level directory stripped.

    Unsafe or unnormalized paths, members outside the single top directory and
    duplicate non-directory paths stop materialization (hostile archive).
    """
    tops, members, seen = set(), [], set()
    for name, kind, data in entries:
        if kind == "dir":
            name = name.rstrip("/")
        top, sep, rest = name.partition("/")
        tops.add(top)
        if not sep:
            if kind != "dir":
                raise MaterializeError(f"member outside the top-level directory: {name!r}")
            continue
        if not m.valid_member_path(rest):
            raise MaterializeError(f"unsafe member path: {name!r}")
        if kind == "dir":
            continue
        if rest in seen:
            raise MaterializeError(f"duplicate member path: {rest!r}")
        seen.add(rest)
        members.append({"path": rest, "type": kind, "data": data,
                        "size": len(data) if data is not None else 0,
                        "sha256": sha256(data) if data is not None else None})
    if len(tops) != 1 or not m.valid_member_path(next(iter(tops))):
        raise MaterializeError(f"archive must have exactly one top-level directory, found {sorted(tops)}")
    return tops.pop(), sorted(members, key=lambda member: member["path"])


# --- transforms ---------------------------------------------------------------

def canonical_tar(members):
    """canonical_tar_v1: ustar, sorted paths, mode 0644, uid/gid 0, empty names, mtime 0, no directories."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for member in sorted(members, key=lambda item: item["path"]):
            info = tarfile.TarInfo(member["path"])
            info.size, info.mode, info.mtime, info.type = member["size"], 0o644, 0, tarfile.REGTYPE
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            archive.addfile(info, io.BytesIO(member["data"]))
    return buffer.getvalue()


def canonical_gzip(data, level):
    """canonical_tar_gzip_v1 compression: Python gzip, mtime 0, no file name."""
    return gzip.compress(data, compresslevel=level, mtime=0)


def toolchain():
    tools = [Path(__file__).resolve(), Path(m.__file__).resolve()]
    return {"materializer_sha256": m.digest([sha256(path.read_bytes()) for path in tools]),
            "python": platform.python_version(), "zlib_runtime": zlib.ZLIB_RUNTIME_VERSION}


# --- materialization ------------------------------------------------------------

def _record(source, split, track, content, provenance, stratum=None, parent=None):
    object_id, size = (sha256(content), len(content)) if isinstance(content, bytes) else content
    return {"bytes": size, "family_id": source["family_id"], "object_id": object_id,
            "occurrence_id": m.occurrence_id(source["source_id"], provenance),
            "parent_bytes": parent["size"] if parent else None,
            "parent_object_id": parent["sha256"] if parent else None,
            "provenance": provenance, "source_id": source["source_id"], "split": split,
            "stratum": stratum, "track": track["id"]}


def _provenance(transform, path=None, options=None, offset=None, length=None):
    return {"length": length, "member_path": path, "offset": offset, "options": options or {},
            "transform": transform}


def representations(source, split, retained, selected, policy, tools):
    """Occurrence records of one release for every policy track, plus short-tail coverage."""
    records, tails, tar = [], {}, None
    for track in policy["tracks"]:
        transform, unit = track["transform"], track.get("unit_bytes")
        if track["id"] == "file":
            for member in selected:
                records.append(_record(source, split, track, (member["sha256"], member["size"]),
                                       _provenance(transform, member["path"]), stratum=member["stratum"]))
        elif unit is not None and transform == "chunk_v1":
            tails[track["id"]] = [0, 0]
            for member in retained:
                spans, tail = m.chunk_spans(member["size"], unit)
                for offset, length in spans:
                    records.append(_record(source, split, track, member["data"][offset:offset + length],
                                           _provenance(transform, member["path"], {"unit_bytes": unit},
                                                       offset, length), parent=member))
                if tail:
                    tails[track["id"]][0] += 1
                    tails[track["id"]][1] += tail
        elif transform in ("canonical_tar_v1", "canonical_tar_gzip_v1"):
            tar = tar if tar is not None else canonical_tar(retained)
            if transform == "canonical_tar_v1":
                records.append(_record(source, split, track, tar, _provenance(transform)))
            else:
                options = {"compresslevel": track["compresslevel"], "zlib_runtime": tools["zlib_runtime"]}
                records.append(_record(source, split, track, canonical_gzip(tar, track["compresslevel"]),
                                       _provenance(transform, options=options)))
        else:
            raise MaterializeError(f"track {track['id']}: no materializer for transform {transform}")
    return records, tails


def _notice_lines(data):
    for raw in data.decode("utf-8", "backslashreplace").splitlines():
        if NOTICE.search(raw):
            line = " ".join(raw.strip().strip("/*#;!-").split())
            if line:
                yield unicodedata.normalize("NFC", line[:NOTICE_CHARS])


def build(plan, policy, fetcher, locked=None, log=None):
    """Materialize every planned release; returns the output manifests.

    fetcher(url, max_bytes) -> (bytes, final_url, attempts). With `locked`
    (a committed source lock) each archive must match its locked URL, size
    and SHA-256 before anything is derived from it.
    """
    log = log if log is not None else []
    caps, globs, tools = policy["caps"], m.family_globs(plan), toolchain()
    components, family_split = m._family_splits(plan, policy)
    locked_sources = {s["source_id"]: s for s in locked["sources"]} if locked else None
    acquired = expanded_total = materialized = 0
    sources, lock_sources, occurrences, coverage = [], [], [], []
    # notices/spdx: family -> line or tag -> {(source_id, path)} of retained members
    license_files = collections.defaultdict(list)
    notices = collections.defaultdict(lambda: collections.defaultdict(set))
    spdx = collections.defaultdict(lambda: collections.defaultdict(set))
    for family in plan["families"]:
        fid = family["family_id"]
        for release in family["releases"]:
            sid, url, fmt = release["release_id"], release["archive"]["url"], release["archive"]["format"]
            cap = caps["acquired_bytes_max"] - acquired
            if locked_sources is not None:
                pinned = locked_sources.get(sid)
                if pinned is None or pinned["url"] != url or pinned["format"] != fmt:
                    raise MaterializeError(f"{sid}: not in the source lock with this URL and format")
                cap = min(cap, pinned["archive_bytes"])
            started = time.monotonic()
            data, final_url, attempts = fetcher(url, cap)
            digest_ = sha256(data)
            log.append({"source_id": sid, "bytes": len(data), "sha256": digest_, "attempts": attempts,
                        "final_host": final_url.split("/")[2] if "://" in final_url else final_url,
                        "seconds": round(time.monotonic() - started, 3)})
            if locked_sources is not None and (digest_, len(data)) != (pinned["archive_sha256"],
                                                                        pinned["archive_bytes"]):
                raise MaterializeError(f"{sid}: archive differs from the source lock (changed download)")
            acquired += len(data)
            entries, expanded = expand(data, fmt, caps["materialized_bytes_max"] - expanded_total)
            expanded_total += expanded
            top, members = normalize(entries)
            selection = m.select_members([{"source_id": sid, "family_id": fid, **member} for member in members],
                                         policy, globs)
            excluded = []
            for exclusion in selection["exclusions"]:
                if exclusion["reason"] == "non_regular_member":
                    if m.path_exclusion(exclusion["path"], fid, policy, globs) is None:
                        raise MaterializeError(f"{sid}: non-regular member at a retained source path: "
                                               f"{exclusion['path']!r}")
                    kind = next(mb["type"] for mb in members if mb["path"] == exclusion["path"])
                    excluded.append({"detail": kind, "path": exclusion["path"], "reason": "non_regular_member"})
                elif exclusion["reason"] == "vendor_or_shared_origin_path":
                    excluded.append({"detail": exclusion["detail"], "path": exclusion["path"],
                                     "reason": exclusion["reason"]})
            source = {"source_id": sid, "family_id": fid}
            records, tails = representations(source, family_split[fid], selection["retained"],
                                             selection["selected"], policy, tools)
            materialized += sum(record["bytes"] for record in records)
            if materialized > caps["materialized_bytes_max"]:
                raise MaterializeError(f"materialized bytes exceed the cap after {sid}")
            occurrences += records
            coverage.append((sid, records, tails))
            for member in members:
                if member["type"] == "file" and LICENSE_FILE.match(member["path"].rsplit("/", 1)[-1]):
                    license_files[fid].append({"bytes": member["size"], "path": member["path"],
                                               "sha256": member["sha256"], "source_id": sid})
            for member in selection["retained"]:
                text = member["data"].decode("utf-8", "backslashreplace")
                for line in _notice_lines(member["data"]):
                    notices[fid][line].add((sid, member["path"]))
                for tag in SPDX.findall(text):
                    spdx[fid][tag].add((sid, member["path"]))
            lock_sources.append({"archive_bytes": len(data), "archive_sha256": digest_, "family_id": fid,
                                 "source_id": sid, "url": url})
            sources.append({
                "archive_bytes": len(data), "archive_sha256": digest_, "excluded": excluded,
                "excluded_counts": dict(sorted(collections.Counter(e["reason"] for e in selection["exclusions"])
                                               .items())),
                "expanded_bytes": expanded, "family_id": fid, "format": fmt,
                "inventory_sha256": m.digest([[mb["path"], mb["type"], mb["size"], mb["sha256"]] for mb in members]),
                "member_count": len(members),
                "retained": [{"bytes": mb["size"], "object_id": mb["sha256"], "path": mb["path"]}
                             for mb in selection["retained"]],
                "source_id": sid, "top_dir": top, "url": url})

    splits_by_object = collections.defaultdict(set)
    for record in occurrences:
        splits_by_object[record["object_id"]].add(record["split"])
    exclusions = [{"detail": "", "evidence_url": None, "kind": "object", "reason": "cross_split_content",
                   "subject": oid} for oid, splits in sorted(splits_by_object.items()) if len(splits) > 1]
    corpus_lock = {
        "components": [{"families": list(c), "split": family_split[c[0]]} for c in components],
        "exclusions": exclusions, "materialized_bytes": materialized,
        "occurrences": sorted(occurrences, key=lambda record: record["occurrence_id"]),
        "schema": "delsk.corpus.lock.v1", "selection_policy_sha256": m.file_sha256(policy),
        "source_plan_sha256": m.file_sha256(plan), "sources": sorted(lock_sources, key=lambda s: s["source_id"]),
        "toolchain": tools}
    errors = m.validate_corpus_lock(corpus_lock, plan, policy)
    if errors:
        raise MaterializeError("corpus lock invalid: " + "; ".join(errors[:20]))

    source_lock = {"acquired_bytes": acquired, "expanded_bytes": expanded_total, "plan_id": plan["plan_id"],
                   "schema": "delsk.corpus.source-lock.v1", "selection_policy_sha256": m.file_sha256(policy),
                   "source_plan_sha256": m.file_sha256(plan), "sources": sources}
    licenses = {"families": [], "schema": "delsk.corpus.license-evidence.v1",
                "scope": "license files of every release and copyright/SPDX lines of retained members; "
                         "review status is recorded in pilot-v1/README.md, never here"}
    for family in plan["families"]:
        fid = family["family_id"]
        def where(found):
            return {"members": len(found), "paths": sorted({path for _, path in found})[:NOTICE_PATHS]}
        top = sorted(notices[fid].items(), key=lambda item: (-len(item[1]), item[0]))
        licenses["families"].append({
            "family_id": fid, "license_files": license_files[fid], "notice_lines": len(top),
            "notices": [{"line": line, **where(found)} for line, found in top[:NOTICES_PER_FAMILY]],
            "notices_truncated": len(top) > NOTICES_PER_FAMILY, "plan_license": family["license"],
            "spdx_tags": [{"tag": tag, **where(found)} for tag, found in sorted(spdx[fid].items())]})
    tracks = []
    for sid, records, tails in coverage:
        by_track = collections.defaultdict(list)
        for record in records:
            by_track[record["track"]].append(record)
        for track in policy["tracks"]:
            items = sorted(by_track[track["id"]], key=lambda record: record["occurrence_id"])
            tail_members, tail_bytes = tails.get(track["id"], (None, None))
            tracks.append({"bytes": sum(r["bytes"] for r in items),
                           "digest": m.digest([[r["occurrence_id"], r["object_id"]] for r in items]),
                           "occurrences": len(items), "short_tail_bytes": tail_bytes,
                           "short_tail_members": tail_members, "source_id": sid, "track": track["id"]})
    summary = {
        "corpus_lock_sha256": m.file_sha256(corpus_lock), "cross_split_objects": len(exclusions),
        "file_track": sorted(({"bytes": r["bytes"], "member_path": r["provenance"]["member_path"],
                               "object_id": r["object_id"], "source_id": r["source_id"], "stratum": r["stratum"]}
                              for r in occurrences if r["track"] == "file"),
                             key=lambda r: (r["source_id"], r["stratum"])),
        "licenses_sha256": m.file_sha256(licenses), "materialized_bytes": materialized,
        "objects": len(splits_by_object), "occurrences": len(occurrences), "plan_id": plan["plan_id"],
        "schema": "delsk.corpus.materialization.v1", "source_lock_sha256": m.file_sha256(source_lock),
        "toolchain": tools, "tracks": tracks}
    return {"source-lock.json": source_lock, "licenses.json": licenses, "materialization.json": summary,
            "corpus-lock.json": corpus_lock}


def validate_committed(files, plan, policy):
    """Errors for committed pilot-v1 files: canonical, pinned to the current plan/policy, mutually pinned."""
    errors = []
    try:
        source_lock, licenses, summary = (m.loads_strict(files[name]) for name in LOCK_FILES)
    except (KeyError, ValueError) as error:
        return [f"pilot lock files unreadable or not canonical: {error}"]
    if source_lock.get("schema") != "delsk.corpus.source-lock.v1":
        errors.append("source lock: unexpected schema")
    if source_lock.get("source_plan_sha256") != m.file_sha256(plan):
        errors.append("source lock: source plan changed after discovery; a new discovery run is required")
    if source_lock.get("selection_policy_sha256") != m.file_sha256(policy):
        errors.append("source lock: selection policy changed after discovery; a new discovery run is required")
    planned = [(r["release_id"], r["archive"]["url"]) for f in plan["families"] for r in f["releases"]]
    if [(s.get("source_id"), s.get("url")) for s in source_lock.get("sources", [])] != planned:
        errors.append("source lock: sources differ from the planned releases")
    for source in source_lock.get("sources", []):
        if not m.SHA256.match(str(source.get("archive_sha256"))):
            errors.append(f"source {source.get('source_id')}: archive_sha256 is not a SHA-256 hex digest")
    if summary.get("source_lock_sha256") != hashlib.sha256(files["source-lock.json"]).hexdigest():
        errors.append("materialization: source_lock_sha256 does not pin source-lock.json")
    if summary.get("licenses_sha256") != hashlib.sha256(files["licenses.json"]).hexdigest():
        errors.append("materialization: licenses_sha256 does not pin licenses.json")
    if licenses.get("schema") != "delsk.corpus.license-evidence.v1" or \
            summary.get("schema") != "delsk.corpus.materialization.v1":
        errors.append("pilot lock files: unexpected schema")
    return errors


# --- entry point ----------------------------------------------------------------

def main(argv, env=os.environ, fetcher=fetch, pilot=PILOT):
    if len(argv) != 2 or argv[0] not in ("discover", "verify"):
        print(__doc__, file=sys.stderr)
        return 2
    mode, out = argv[0], Path(argv[1])
    out.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    report = {"schema": "delsk.corpus.materialization-report.v1", "mode": mode, "status": "error", "errors": [],
              "downloads": [], "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
              "run": {key: env.get(key) for key in ("GITHUB_REPOSITORY", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT",
                                                    "GITHUB_SHA", "GITHUB_WORKFLOW_SHA", "SOURCE_SHA")}}
    try:
        plan = m.loads_strict((CORPUS / "source-plan.json").read_bytes())
        policy = m.loads_strict((CORPUS / "selection-policy.json").read_bytes())
        upstream = m.validate_source_plan(plan) + m.validate_selection_policy(policy)
        if upstream:
            raise MaterializeError("invalid plan/policy: " + "; ".join(upstream))
        committed = None
        if mode == "verify":
            committed = {name: (pilot / name).read_bytes() for name in LOCK_FILES}
            errors = validate_committed(committed, plan, policy)
            if errors:
                raise MaterializeError("committed pilot-v1 files: " + "; ".join(errors))
        outputs = build(plan, policy, fetcher, m.loads_strict(committed["source-lock.json"]) if committed else None,
                        report["downloads"])
        report["outputs"] = {}
        for name, value in outputs.items():
            data = m.canonical_bytes(value)
            report["outputs"][name] = {"bytes": len(data), "sha256": sha256(data)}
            if name == "corpus-lock.json":
                (out / "corpus-lock.json.gz").write_bytes(gzip.compress(data, mtime=0))
            else:
                (out / name).write_bytes(data)
        report["status"] = "ok"
        if committed:
            report["matches"] = {name: committed[name] == m.canonical_bytes(outputs[name]) for name in LOCK_FILES}
            if not all(report["matches"].values()):
                report["status"] = "mismatch"
                report["errors"].append("re-materialization differs from the committed lock files")
    except MaterializeError as error:
        report.update(status="failed", errors=[str(error)])
    except Exception as error:  # evidence is written even when the materializer itself breaks
        report.update(status="error", errors=[f"{type(error).__name__}: {error}",
                                              traceback.format_exc(limit=5)])
    finally:
        report["seconds"] = round(time.monotonic() - started, 3)
        (out / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"mode": mode, "status": report["status"], "errors": report["errors"][:1]}))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
