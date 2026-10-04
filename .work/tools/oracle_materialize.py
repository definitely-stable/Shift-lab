"""Slice C0 pinned acquisition adapter. No encoder, scorer or evaluation costs.

The production loader validates metadata only. Call materialize_store solely
inside the admitted pilot workload; tests supply synthetic archives/fetchers.
Archives are expanded in memory. Only required content IDs enter the store.
"""
import bz2
from contextlib import contextmanager
import gzip
import hashlib
import io
import lzma
import os
from pathlib import Path
import re
import stat
import sys
import tarfile
from urllib.parse import urlsplit
import zipfile
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import manifests as m
import materialize
import recompute_foundation as foundation

WORK = Path(__file__).resolve().parents[1]
ROOT = WORK.parent
HEX = re.compile(r"[0-9a-f]{64}\Z")
GOLDEN_SHA256 = "69a95cc87e4731d264bc2873873715dff65d93cb90b3f93114e9afc49179bd1b"
ORACLE_FREEZE_SHA256 = "c56fc053b103cecd38446b3791db104a12b9fafabacdfc6b71f6f23c0bf7f729"
FAILURES = frozenset({"SOURCE_FETCH_FAILED", "SOURCE_IDENTITY_MISMATCH", "ARCHIVE_UNSAFE",
                      "EXPANSION_CAP", "OBJECT_INTEGRITY", "OBJECT_SET_MISMATCH", "FROZEN_BINDING"})


class MaterializationError(Exception):
    """Closed failure vocabulary; exception text never includes input bytes."""
    def __init__(self, failure_class):
        self.failure_class = failure_class if failure_class in FAILURES else "FROZEN_BINDING"
        super().__init__(self.failure_class)


def check(condition, failure="FROZEN_BINDING"):
    if not condition:
        raise MaterializationError(failure)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def _doc(path):
    return m.loads_strict(path.read_bytes())


def validate_frozen():
    """Validate the complete D/E0/E1 graph, E1 code, oracle bindings and C14."""
    try:
        pins, accounting, _ = foundation.account()
        seal = _doc(WORK / "corpus/e1/seal.json")
        for name, digest in seal["code_sha256"].items():
            check(Path(name).name == name and sha((WORK / "tools" / name).read_bytes()) == digest)
            pins[f".work/tools/{name}"] = digest
        check(sha((WORK / "oracle/freeze.json").read_bytes()) == ORACLE_FREEZE_SHA256)
        freeze = _doc(WORK / "oracle/freeze.json")
        check(freeze["status"] == "FROZEN_ON_MERGE" and freeze["natural_measurements"] == "NOT_RUN")
        for name, digest in freeze["files"].items():
            check(m.valid_member_path(name) and sha((ROOT / name).read_bytes()) == digest)
            check(pins.setdefault(name, digest) == digest)
        bindings = freeze["bindings"]
        files = {"candidate_lock_sha256": WORK / "corpus/e1/candidate-lock.json",
                 "codec_lock_sha256": WORK / "oracle/codec-lock.json",
                 "protocol_sha256": WORK / "protocol.md", "seal_sha256": WORK / "corpus/e1/seal.json"}
        for key, path in files.items():
            check(sha(path.read_bytes()) == bindings[key])
        check(bindings["corpus_lock_sha256"] == seal["bindings"]["corpus_lock_sha256"])
        counts = accounting["candidates"]
        check(freeze["pair_universe"] == {"queries": counts["queries"], "identity_only": counts["identity_queries"],
                                        "near_duplicate": counts["near_queries"],
                                        "planned_pairs_per_codec": counts["planned_pairs_per_codec"]})
        golden_path = WORK / "oracle/conformance.json"
        check(sha(golden_path.read_bytes()) == GOLDEN_SHA256)
        golden = _doc(golden_path)
        check(golden["schema"] == "delsk.oracle.conformance-golden.v1"
              and golden["contract_id"] == freeze["contract_id"]
              and golden["codec_lock_sha256"] == bindings["codec_lock_sha256"])
        pins[".work/oracle/conformance.json"] = GOLDEN_SHA256
        pins[".work/oracle/freeze.json"] = sha((WORK / "oracle/freeze.json").read_bytes())
        return {"hashes": dict(sorted(pins.items())), "bindings": bindings,
                "counts": {key: counts[key] for key in ("queries", "near_queries", "identity_queries", "planned_pairs_per_codec")}}
    except MaterializationError:
        raise
    except Exception:
        raise MaterializationError("FROZEN_BINDING") from None


def load_natural():
    """Return validated frozen metadata, without fetching any natural bytes."""
    validate_frozen()
    try:
        candidate = _doc(WORK / "corpus/e1/candidate-lock.json")
        corpus = m.loads_strict(gzip.decompress((WORK / "corpus/pilot-v1/corpus-lock.json.gz").read_bytes()))
        sources = _doc(WORK / "corpus/pilot-v1/source-lock.json")
        policy = _doc(WORK / "corpus/selection-policy.json")
        expected_objects(candidate, corpus)
        return candidate, corpus, sources, policy
    except MaterializationError:
        raise
    except Exception:
        raise MaterializationError("FROZEN_BINDING") from None


def _required(candidate, corpus):
    synthetic = corpus.get("schema") == "delsk.oracle.synthetic-corpus.v1"
    if synthetic:
        check(candidate.get("schema") == "delsk.oracle.synthetic-candidates.v1"
              and candidate["corpus_lock_sha256"] == m.file_sha256(corpus))
    occurrences, lengths = {}, {}
    for occ in corpus["occurrences"]:
        oid, cid, size = occ["occurrence_id"], occ["object_id"], occ["bytes"]
        check(HEX.fullmatch(oid) and HEX.fullmatch(cid) and type(size) is int and size >= 0)
        check(oid not in occurrences)
        if not synthetic:
            check(oid == m.occurrence_id(occ["source_id"], occ["provenance"]))
        check(lengths.setdefault(cid, size) == size)
        occurrences[oid] = occ
    required, targets = {}, set()
    for query in candidate["queries"]:
        tid = query["target"]
        check(tid not in targets and tid in occurrences)
        targets.add(tid)
        target = occurrences[tid]
        required[tid] = target
        check(query["status"] in ("near_duplicate", "identity_only"))
        bases = query["bases"]
        ids = [b["object_id"] for b in bases]
        check(ids == sorted(set(ids)) and query["candidate_count"] == len(ids)
              and query["candidate_list_sha256"] == m.digest(ids))
        if query["status"] == "identity_only":
            duplicate = occurrences.get(query["duplicate_of"])
            check(not bases and duplicate is not None and duplicate["occurrence_id"] != tid
                  and duplicate["object_id"] == target["object_id"] and duplicate["bytes"] == target["bytes"]
                  and duplicate["track"] == target["track"] and duplicate["split"] == target["split"])
            required[duplicate["occurrence_id"]] = duplicate
        else:
            check(query["duplicate_of"] is None)
        for base in bases:
            rep = occurrences.get(base["representative"])
            check(rep is not None and rep["object_id"] == base["object_id"])
            if not synthetic:
                check(rep["object_id"] != target["object_id"]
                      and rep["track"] == target["track"] and rep["split"] == target["split"])
            required[rep["occurrence_id"]] = rep
    return required


def expected_objects(candidate, corpus):
    """Exact oracle object ID -> length mapping, including identity witnesses.

    The explicit runner synthetic schema has test-only occurrence IDs and
    intentionally ineligible/self bases; it still requires exact representatives
    and consistent content sizes. It cannot enter natural materialization.
    """
    try:
        return dict(sorted({o["object_id"]: o["bytes"] for o in _required(candidate, corpus).values()}.items()))
    except MaterializationError:
        raise
    except Exception:
        raise MaterializationError("FROZEN_BINDING") from None


def _https(url):
    parsed = urlsplit(url)
    return parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username and not parsed.password


def _expand(data, source, limit):
    """Bound expansion and enumeration before any member payload can escape."""
    entries, expanded = [], 0
    # Metadata records occupy at least a tar header or a ZIP central header.
    count_cap = source["member_count"] + source["expanded_bytes"] // 512 + source["archive_bytes"] // 30 + 1
    try:
        if source["format"] == "zip":
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                check(len(archive.infolist()) <= count_cap, "EXPANSION_CAP")
                for info in archive.infolist():
                    mode = info.external_attr >> 16
                    check(not info.flag_bits & 1, "ARCHIVE_UNSAFE")
                    if info.is_dir():
                        entries.append((info.filename.rstrip("/"), "dir", None))
                        continue
                    if stat.S_ISLNK(mode):
                        entries.append((info.filename, "symlink", None))
                        continue
                    check(not stat.S_IFMT(mode) or stat.S_ISREG(mode), "ARCHIVE_UNSAFE")
                    check(info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED), "ARCHIVE_UNSAFE")
                    check(info.file_size <= limit - expanded, "EXPANSION_CAP")
                    with archive.open(info) as stream:
                        content = stream.read(limit - expanded + 1)
                    expanded += len(content)
                    check(expanded <= limit, "EXPANSION_CAP")
                    entries.append((info.filename, "file", content))
        else:
            opener = {"tar.gz": gzip.open, "tar.xz": lzma.open, "tar.bz2": bz2.open}.get(source["format"])
            check(opener is not None, "ARCHIVE_UNSAFE")
            with opener(io.BytesIO(data)) as stream:
                raw = stream.read(limit + 1)
            expanded = len(raw)
            check(expanded <= limit, "EXPANSION_CAP")
            with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
                for info in archive:
                    check(len(entries) < count_cap, "EXPANSION_CAP")
                    check(not info.issparse() and (info.isreg() or info.isdir() or info.issym() or info.islnk()), "ARCHIVE_UNSAFE")
                    content = None
                    if info.isreg():
                        check(0 <= info.size <= limit, "EXPANSION_CAP")
                        content = archive.extractfile(info).read(info.size + 1)
                        check(len(content) == info.size, "ARCHIVE_UNSAFE")
                    kind = "dir" if info.isdir() else "file" if info.isreg() else "symlink" if info.issym() else "hardlink"
                    entries.append((info.name.rstrip("/") if info.isdir() else info.name, kind, content))
        tops, seen, members = set(), set(), []
        for name, kind, content in entries:
            check(m.valid_member_path(name), "ARCHIVE_UNSAFE")
            top, sep, path = name.partition("/")
            tops.add(top)
            check(sep or kind == "dir", "ARCHIVE_UNSAFE")
            if kind == "dir":
                continue
            check(path not in seen, "ARCHIVE_UNSAFE")
            seen.add(path)
            if kind != "file":
                check({"path": path, "reason": "non_regular_member", "detail": kind} in source.get("excluded", []),
                      "ARCHIVE_UNSAFE")
            members.append({"path": path, "type": kind, "data": content,
                            "size": len(content) if content is not None else 0,
                            "sha256": sha(content) if content is not None else None})
        check(len(tops) == 1, "ARCHIVE_UNSAFE")
        members.sort(key=lambda item: item["path"])
        check(next(iter(tops)) == source["top_dir"] and expanded == source["expanded_bytes"]
              and len(members) == source["member_count"]
              and m.digest([[v["path"], v["type"], v["size"], v["sha256"]] for v in members]) == source["inventory_sha256"],
              "SOURCE_IDENTITY_MISMATCH")
        return members, expanded
    except MaterializationError:
        raise
    except Exception:
        raise MaterializationError("ARCHIVE_UNSAFE") from None


def _retained(members, source, policy):
    excluded = {e["path"] for e in source.get("excluded", []) if e["reason"] == "vendor_or_shared_origin_path"}
    retained = [v for v in members if v["type"] == "file" and v["path"] not in excluded
                and m.path_exclusion(v["path"], source["family_id"], policy, {}) is None]
    check([{"bytes": v["size"], "object_id": v["sha256"], "path": v["path"]} for v in retained] == source["retained"],
          "SOURCE_IDENTITY_MISMATCH")
    return retained


def _tar(members):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for item in sorted(members, key=lambda v: v["path"]):
            info = tarfile.TarInfo(item["path"])
            info.size, info.mode, info.mtime = item["size"], 0o644, 0
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            archive.addfile(info, io.BytesIO(item["data"]))
    return buffer.getvalue()


def _reparse(st):
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_file_attributes", 0) & 0x400)


@contextmanager
def _store(path, create=False):
    """Anchor every ancestor against symlink replacement; writes use O_EXCL.

    POSIX uses openat/no-follow descriptors. Windows holds directory handles
    without FILE_SHARE_DELETE, preventing ancestor replacement while in use.
    """
    path = Path(os.path.abspath(path))
    handles, dirs = [], []
    try:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            open_dir = kernel.CreateFileW
            open_dir.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                 wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
            open_dir.restype = wintypes.HANDLE
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            for current in [*reversed(path.parents), path]:
                if current == path and create and not current.exists():
                    current.mkdir()
                st = current.lstat()
                check(stat.S_ISDIR(st.st_mode) and not _reparse(st), "OBJECT_SET_MISMATCH")
                handle = open_dir(str(current), 0x80, 3, None, 3, 0x02200000, None)
                check(handle != wintypes.HANDLE(-1).value, "OBJECT_SET_MISMATCH")
                handles.append(handle)
                check(not _reparse(current.lstat()), "OBJECT_SET_MISMATCH")
            yield path, None
        else:
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            fd = os.open(path.anchor, flags)
            dirs.append(fd)
            for index, part in enumerate(path.parts[1:]):
                if create and index == len(path.parts[1:]) - 1:
                    try:
                        os.mkdir(part, dir_fd=fd)
                    except FileExistsError:
                        pass
                fd = os.open(part, flags, dir_fd=fd)
                dirs.append(fd)
            yield path, fd
    except MaterializationError:
        raise
    except OSError:
        raise MaterializationError("OBJECT_SET_MISMATCH") from None
    finally:
        for fd in reversed(dirs):
            os.close(fd)
        for handle in reversed(handles):
            kernel.CloseHandle(handle)


def _names(path, fd):
    return os.listdir(fd if fd is not None else path)


def _open(path, fd, name, flags):
    return os.open(name if fd is not None else path / name,
                   flags | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0),
                   0o600, **({"dir_fd": fd} if fd is not None else {}))


def _verify(path, fd, expected):
    check(set(_names(path, fd)) == set(expected), "OBJECT_SET_MISMATCH")
    for oid, size in sorted(expected.items()):
        check(type(oid) is str and HEX.fullmatch(oid) and type(size) is int and size >= 0, "FROZEN_BINDING")
        try:
            before = os.stat(oid, dir_fd=fd, follow_symlinks=False) if fd is not None else (path / oid).lstat()
            check(stat.S_ISREG(before.st_mode) and not _reparse(before) and before.st_nlink == 1, "OBJECT_SET_MISMATCH")
            file_fd = _open(path, fd, oid, os.O_RDONLY)
            with os.fdopen(file_fd, "rb") as stream:
                opened = os.fstat(stream.fileno())
                check(stat.S_ISREG(opened.st_mode) and (before.st_dev, before.st_ino) == (opened.st_dev, opened.st_ino),
                      "OBJECT_SET_MISMATCH")
                check(opened.st_size == size, "OBJECT_INTEGRITY")
                digest, total = hashlib.sha256(), 0
                while block := stream.read(min(1 << 20, size - total + 1)):
                    total += len(block)
                    check(total <= size, "OBJECT_INTEGRITY")
                    digest.update(block)
                check(total == size and digest.hexdigest() == oid, "OBJECT_INTEGRITY")
        except OSError:
            raise MaterializationError("OBJECT_SET_MISMATCH") from None
    check(set(_names(path, fd)) == set(expected), "OBJECT_SET_MISMATCH")
    return {"schema": "delsk.oracle.store-verification.v1", "verified": True, "objects": len(expected),
            "object_set_sha256": m.digest(sorted(expected)), "expected_manifest_sha256": m.digest(expected)}


def verify_store(store, expected):
    """Independent enumeration and streamed length/SHA verification; ignore nothing."""
    with _store(store) as (path, fd):
        return _verify(path, fd, expected)


def materialize_store(store, candidate, corpus, source_lock, policy, fetcher=materialize.fetch):
    """Fetch only sources needed by pinned oracle occurrences; write only required IDs."""
    try:
        check(corpus.get("schema") != "delsk.oracle.synthetic-corpus.v1")
        required = _required(candidate, corpus)
        expected = expected_objects(candidate, corpus)
        sources = {v["source_id"]: v for v in source_lock["sources"]}
        check(len(sources) == len(source_lock["sources"]))
        corpus_sources = {v["source_id"]: v for v in corpus["sources"]}
        groups = {}
        tracks = {v["id"]: v for v in policy["tracks"]}
        for occ in required.values():
            check(occ["source_id"] in sources and occ["source_id"] in corpus_sources)
            check(occ["track"] in tracks and occ["provenance"]["transform"] == tracks[occ["track"]]["transform"])
            check(occ["family_id"] == sources[occ["source_id"]]["family_id"])
            if occ["provenance"]["transform"] == "canonical_tar_gzip_v1":
                check(occ["provenance"]["options"]["zlib_runtime"] == corpus["toolchain"]["zlib_runtime"] == zlib.ZLIB_RUNTIME_VERSION)
            groups.setdefault(occ["source_id"], []).append(occ)
        acquired = expanded_total = written_bytes = 0
        written = set()
        with _store(store, create=True) as (path, fd):
            check(not _names(path, fd), "OBJECT_SET_MISMATCH")
            for sid, occurrences in sorted(groups.items()):
                source = sources[sid]
                check(_https(source["url"]) and HEX.fullmatch(source["archive_sha256"])
                      and type(source["archive_bytes"]) is int and source["archive_bytes"] > 0)
                check(all(source[k] == corpus_sources[sid][k] for k in
                          ("family_id", "url", "archive_bytes", "archive_sha256")))
                cap = min(source["archive_bytes"], policy["caps"]["acquired_bytes_max"] - acquired)
                check(cap == source["archive_bytes"], "EXPANSION_CAP")
                try:
                    data, final_url, _ = fetcher(source["url"], cap)
                except Exception:
                    raise MaterializationError("SOURCE_FETCH_FAILED") from None
                check(type(data) is bytes and len(data) == source["archive_bytes"] and sha(data) == source["archive_sha256"]
                      and _https(final_url), "SOURCE_IDENTITY_MISMATCH")
                acquired += len(data)
                limit = min(source["expanded_bytes"], policy["caps"]["materialized_bytes_max"] - expanded_total)
                check(limit >= 0, "EXPANSION_CAP")
                members, expanded = _expand(data, source, limit)
                expanded_total += expanded
                retained = _retained(members, source, policy)
                by_path = {v["path"]: v for v in retained}
                tar = None
                for occ in sorted(occurrences, key=lambda v: v["occurrence_id"]):
                    prov, track = occ["provenance"], tracks[occ["track"]]
                    transform = prov["transform"]
                    if transform in ("member_v1", "chunk_v1"):
                        member = by_path.get(prov["member_path"])
                        check(member is not None, "OBJECT_INTEGRITY")
                        if transform == "member_v1":
                            check(prov["options"] == {} and prov["offset"] is None and prov["length"] is None)
                            content = member["data"]
                        else:
                            unit, offset = track["unit_bytes"], prov["offset"]
                            check(type(unit) is int and unit > 0 and type(offset) is int and offset >= 0
                                  and offset % unit == 0 and prov["length"] == unit and prov["options"] == {"unit_bytes": unit}
                                  and offset + unit <= member["size"]
                                  and (occ["parent_bytes"], occ["parent_object_id"]) == (member["size"], member["sha256"]), "OBJECT_INTEGRITY")
                            content = member["data"][offset:offset + unit]
                    elif transform in ("canonical_tar_v1", "canonical_tar_gzip_v1"):
                        check(prov["member_path"] is None and prov["offset"] is None and prov["length"] is None)
                        tar = tar if tar is not None else _tar(retained)
                        if transform == "canonical_tar_v1":
                            check(prov["options"] == {})
                            content = tar
                        else:
                            check(prov["options"] == {"compresslevel": track["compresslevel"], "zlib_runtime": zlib.ZLIB_RUNTIME_VERSION})
                            # Python 3.12 gzip.compress(mtime=0) delegates to zlib.
                            # Direct gzip framing preserves its native OS byte on
                            # later Python versions that changed gzip.compress.
                            content = zlib.compress(tar, track["compresslevel"], wbits=31)
                    else:
                        raise MaterializationError("FROZEN_BINDING")
                    oid = occ["object_id"]
                    check(len(content) == occ["bytes"] and sha(content) == oid, "OBJECT_INTEGRITY")
                    if oid not in written:
                        written_bytes += len(content)
                        check(written_bytes <= policy["caps"]["materialized_bytes_max"], "EXPANSION_CAP")
                        file_fd = _open(path, fd, oid, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
                        with os.fdopen(file_fd, "wb") as stream:
                            stream.write(content)
                        written.add(oid)
            verification = _verify(path, fd, expected)
        return {"schema": "delsk.oracle.materialization-provenance.v1", "verification": verification,
                "required_occurrences": len(required), "required_sources": len(groups),
                "candidate_lock_sha256": m.file_sha256(candidate), "corpus_lock_sha256": m.file_sha256(corpus),
                "source_lock_sha256": m.file_sha256(source_lock), "selection_policy_sha256": m.file_sha256(policy)}
    except MaterializationError:
        raise
    except Exception:
        raise MaterializationError("FROZEN_BINDING") from None
