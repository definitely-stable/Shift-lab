"""Tests for tools/materialize.py (DELSK-002 Slice D safe acquisition and materialization).

Run: python -m unittest discover -s .work/tests -v
Every archive is built in memory from a synthetic 6-family plan and the real
selection policy; downloads are faked. No network, no payload written to disk.
"""

import bz2
import contextlib
import copy
import datetime as dt
import gzip
import hashlib
import io
import json
import lzma
import random
import sys
import tarfile
import tempfile
import unittest
import unittest.mock
import urllib.error
import warnings
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import manifests as m  # noqa: E402
import materialize as mz  # noqa: E402

POLICY = m.loads_strict((mz.CORPUS / "selection-policy.json").read_bytes())
FAMILIES = ["fa", "fb", "fc", "fd", "fe", "ff"]
FORMATS = ["tar.gz", "tar.xz", "zip", "tar.gz", "tar.bz2", "tar.gz"]
MARKER = b"PAYLOAD-MARKER-7f3a"
LIMIT = 1 << 20
COMPRESS = {"tar.gz": gzip.compress, "tar.xz": lzma.compress, "tar.bz2": bz2.compress}


def blob(seed, n):
    return random.Random(seed).randbytes(n)


def make_plan():
    families = []
    for i, fid in enumerate(FAMILIES):
        releases = []
        for n, year in enumerate((2020, 2021, 2022), 1):
            day = dt.date(year, 1, 1) + dt.timedelta(days=i)
            releases.append({
                "release_id": f"{fid}-{n}", "ordinal": n,
                "archive": {"url": f"https://example.org/{fid}-{n}.{FORMATS[i]}", "format": FORMATS[i],
                            "sha256": None},
                "time": {"value": day.isoformat(), "evidence_url": "https://example.org/tags"}})
        families.append({
            "family_id": fid, "exclude_globs": [{"glob": "vend/*", "reason": "vendored"}] if fid == "fa" else [],
            "releases": releases,
            "license": {"spdx": "MIT", "evidence_url": "https://example.org/license",
                        "status": "PENDING_SNAPSHOT_REVIEW"}})
    return {"schema": "delsk.corpus.source-plan.v1", "status": "PROPOSED", "plan_id": "t",
            "families": families, "ancestry_edges": []}


def pack(entries, fmt):
    """Archive bytes from (name, kind, payload) entries; kind file|dir|symlink|hardlink, payload data/linkname."""
    buffer = io.BytesIO()
    if fmt == "zip":
        with warnings.catch_warnings(), zipfile.ZipFile(buffer, "w") as archive:
            warnings.simplefilter("ignore")
            for name, kind, payload in entries:
                archive.writestr(name, payload if kind == "file" else b"")
        return buffer.getvalue()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for name, kind, payload in entries:
            info = tarfile.TarInfo(name)
            info.type = {"file": tarfile.REGTYPE, "dir": tarfile.DIRTYPE, "symlink": tarfile.SYMTYPE,
                         "hardlink": tarfile.LNKTYPE}[kind]
            if kind == "file":
                info.size = len(payload)
            elif kind != "dir":
                info.linkname = payload
            archive.addfile(info, io.BytesIO(payload) if kind == "file" else None)
    return COMPRESS[fmt](buffer.getvalue()) if fmt in COMPRESS else buffer.getvalue()


def release_archive(fid, n, fmt, extra=()):
    base = blob(fid, 70000)
    top = f"{fid}-{n}"
    files = {"src/a.c": b"/* Copyright (c) 2020 Test */\n" + base[:66000] + blob(f"{fid}{n}", n * 37),
             "src/b.h": blob(fid + "h", 9000), "README": b"x", "LICENSE": b"MIT", "vend/v.c": b"vendored" * 10}
    entries = [(f"{top}/{p}", "file", d) for p, d in files.items()]
    if fmt != "zip":
        entries.append((f"{top}/bin/link", "symlink", "../x"))
    return pack(entries + [(f"{top}/{p}", k, d) for p, k, d in extra], fmt)


def make_store(plan, extra=()):
    return {r["archive"]["url"]: release_archive(f["family_id"], r["ordinal"], r["archive"]["format"], extra)
            for f in plan["families"] for r in f["releases"]}


def fetcher_for(store):
    def fetcher(url, cap):
        data = store[url]
        if len(data) > cap:
            raise mz.MaterializeError(f"{url}: exceeds the cap {cap}")
        return data, url, 1
    return fetcher


PLAN = make_plan()
STORE = make_store(PLAN)
OUTPUTS = mz.build(PLAN, POLICY, fetcher_for(STORE))


def lock_files(outputs):
    return {name: m.canonical_bytes(outputs[name]) for name in mz.LOCK_FILES}


def tweak_policy(**caps):
    policy = copy.deepcopy(POLICY)
    policy["caps"].update(caps)
    return policy


class FakeResponse:
    def __init__(self, body, length="auto", url="https://example.org/f"):
        self.body, self.reads, self.url = io.BytesIO(body), 0, url
        self.headers = {} if length is None else {"Content-Length": str(len(body) if length == "auto" else length)}

    def read(self, n):
        self.reads += 1
        return self.body.read(n)

    def geturl(self):
        return self.url

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def opener(*outcomes):
    """open_url fake: each call consumes one outcome (exception instance raised, else returned)."""
    calls = []

    def open_url(request, timeout):
        calls.append(request.full_url)
        outcome = outcomes[min(len(calls), len(outcomes)) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
    open_url.calls = calls
    return open_url


class HostileArchiveTests(unittest.TestCase):
    def assertHostile(self, entries, fmt="tar.gz"):
        with self.assertRaises(mz.MaterializeError):
            mz.normalize(mz.expand(pack(entries, fmt), fmt, LIMIT)[0])

    def test_hostile_members_rejected(self):
        cases = {
            "traversal": [("top/../x.c", "file", b"x")],
            "absolute": [("/etc/x.c", "file", b"x")],
            "backslash": [("top/a\\b.c", "file", b"x")],
            "control_char": [("top/a\x01.c", "file", b"x")],
            "two_tops": [("a/x.c", "file", b"x"), ("b/y.c", "file", b"y")],
            "top_level_file": [("x.c", "file", b"x")],
            "duplicate": [("top/x.c", "file", b"1"), ("top/x.c", "file", b"2")],
        }
        for fmt in ("tar.gz", "zip"):
            for name, entries in cases.items():
                if fmt == "zip" and name in ("backslash", "absolute", "control_char"):
                    continue  # zipfile rewrites os.sep / strips these names on Windows
                with self.subTest(fmt=fmt, case=name):
                    self.assertHostile(entries, fmt)

    def test_link_at_retained_source_path_fails_in_build(self):
        for kind, target in (("symlink", "../x"), ("hardlink", "fa-1/src/a.c")):
            with self.subTest(kind=kind):
                store = make_store(PLAN, extra=[("src/evil.c", kind, target)])
                entries, _ = mz.expand(store[PLAN["families"][0]["releases"][0]["archive"]["url"]], "tar.gz", LIMIT)
                mz.normalize(entries)  # not a normalize error: build rejects it
                with self.assertRaisesRegex(mz.MaterializeError, "retained source path"):
                    mz.build(PLAN, POLICY, fetcher_for(store))

    def test_link_at_non_source_path_is_recorded_not_fatal(self):
        source = next(s for s in OUTPUTS["source-lock.json"]["sources"] if s["source_id"] == "fa-1")
        self.assertIn({"detail": "symlink", "path": "bin/link", "reason": "non_regular_member"}, source["excluded"])
        self.assertIn({"detail": "vend/*", "path": "vend/v.c", "reason": "vendor_or_shared_origin_path"},
                      source["excluded"])

    def test_zip_attacks(self):
        plain = bytearray(pack([("top/a.c", "file", b"x")], "zip"))
        for signature, offset in ((b"PK", 6), (b"PK", 8)):  # local and central flag_bits
            plain[plain.index(signature) + offset] |= 0x1
        bzip2 = io.BytesIO()
        with zipfile.ZipFile(bzip2, "w") as archive:
            archive.writestr("top/a.c", b"x" * 100, compress_type=zipfile.ZIP_BZIP2)
        good = pack([("top/a.c", "file", b"abc" * 100)], "zip")
        cases = {"encrypted": bytes(plain), "bzip2": bzip2.getvalue(), "garbage": b"PK\x03\x04garbage",
                 "truncated": good[:len(good) // 2], "empty": b""}
        for name, data in cases.items():
            with self.subTest(case=name), self.assertRaises(mz.MaterializeError):
                mz.expand(data, "zip", LIMIT)

    def test_unknown_format(self):
        with self.assertRaises(mz.MaterializeError):
            mz.expand(b"", "rar", LIMIT)

    def test_zip_writestr_members_are_regular_files(self):
        for attr in (0o600 << 16, 0o644 << 16, 0o755 << 16, 0):
            with self.subTest(attr=oct(attr >> 16)):
                buffer = io.BytesIO()
                info = zipfile.ZipInfo("top/src/a.c")
                info.external_attr = attr
                with zipfile.ZipFile(buffer, "w") as archive:
                    archive.writestr(info, b"int a;\n")
                self.assertEqual(mz.expand(buffer.getvalue(), "zip", LIMIT)[0],
                                 [("top/src/a.c", "file", b"int a;\n")])
        entries, _ = mz.expand(STORE[PLAN["families"][2]["releases"][0]["archive"]["url"]], "zip", LIMIT)
        self.assertTrue(entries and all(kind == "file" for _, kind, _ in entries))


class ExpansionTests(unittest.TestCase):
    def test_expansion_caps(self):
        bomb = [("top/z.c", "file", bytes(4 << 20))]
        for fmt in ("tar.gz", "tar.xz", "zip"):
            with self.subTest(fmt=fmt), self.assertRaisesRegex(mz.MaterializeError, "cap"):
                mz.expand(pack(bomb, fmt), fmt, LIMIT)

    def test_zip_member_over_remaining_limit(self):
        data = pack([("top/a.c", "file", bytes(600_000)), ("top/b.c", "file", bytes(600_000))], "zip")
        with self.assertRaisesRegex(mz.MaterializeError, "cap"):
            mz.expand(data, "zip", LIMIT)
        self.assertEqual(mz.expand(data, "zip", 1_200_000)[1], 1_200_000)

    def test_truncated_streams(self):
        raw = [("top/a.c", "file", blob("t", 50000))]
        for fmt in ("tar.gz", "tar.xz", "tar.bz2"):
            data = pack(raw, fmt)
            with self.subTest(fmt=fmt), self.assertRaises(mz.MaterializeError):
                mz.expand(data[:len(data) // 2], fmt, LIMIT)

    def test_corrupt_tar_body(self):
        with self.assertRaises(mz.MaterializeError):
            mz.expand(gzip.compress(b"not a tar archive" * 100), "tar.gz", LIMIT)


class FetchTests(unittest.TestCase):
    URL = "https://example.org/a.tar.gz"

    def fetch(self, open_url, cap=1000):
        return mz.fetch(self.URL, cap, open_url=open_url, sleep=lambda s: None)

    def test_read_capped(self):
        self.assertEqual(mz.read_capped(FakeResponse(b"abc"), 3), b"abc")
        self.assertEqual(mz.read_capped(FakeResponse(b"abc", length=None), 3), b"abc")
        with self.assertRaisesRegex(mz.MaterializeError, "cap"):
            mz.read_capped(FakeResponse(b"x" * 100, length=None), 10)
        response = FakeResponse(b"x" * 100, length=10_000)
        with self.assertRaisesRegex(mz.MaterializeError, "cap"):
            mz.read_capped(response, 1000)
        self.assertEqual(response.reads, 0)  # declared size refused before any read
        with self.assertRaises(mz.Transient):
            mz.read_capped(FakeResponse(b"x" * 50, length=100), 1000)

    def test_fetch_success(self):
        body, final, attempts = self.fetch(opener(FakeResponse(b"data", url="https://cdn.example.org/a")))
        self.assertEqual((body, final, attempts), (b"data", "https://cdn.example.org/a", 1))

    def test_cap_exceeded_is_not_retried(self):
        open_url = opener(FakeResponse(b"x" * 100, length=None))
        with self.assertRaisesRegex(mz.MaterializeError, "cap"):
            self.fetch(open_url, cap=10)
        self.assertEqual(len(open_url.calls), 1)

    def test_truncated_body_retried_then_fails(self):
        open_url = opener(*[FakeResponse(b"x" * 50, length=100) for _ in range(mz.ATTEMPTS)])
        with self.assertRaisesRegex(mz.MaterializeError, "truncated"):
            self.fetch(open_url)
        self.assertEqual(len(open_url.calls), mz.ATTEMPTS)

    def test_http_404_fails_immediately(self):
        open_url = opener(urllib.error.HTTPError(self.URL, 404, "nf", {}, None))
        with self.assertRaisesRegex(mz.MaterializeError, "404"):
            self.fetch(open_url)
        self.assertEqual(len(open_url.calls), 1)

    def test_http_503_retried_then_succeeds(self):
        sleeps = []
        open_url = opener(urllib.error.HTTPError(self.URL, 503, "busy", {}, None), FakeResponse(b"ok"))
        self.assertEqual(mz.fetch(self.URL, 100, open_url=open_url, sleep=sleeps.append),
                         (b"ok", "https://example.org/f", 2))
        self.assertEqual(sleeps, [2])

    def test_http_503_gives_up(self):
        open_url = opener(urllib.error.HTTPError(self.URL, 503, "busy", {}, None))
        with self.assertRaisesRegex(mz.MaterializeError, "503"):
            self.fetch(open_url)
        self.assertEqual(len(open_url.calls), mz.ATTEMPTS)

    def test_network_error_retried(self):
        open_url = opener(ConnectionResetError("reset"), FakeResponse(b"ok"))
        self.assertEqual(self.fetch(open_url)[2], 2)

    def test_non_https_rejected(self):
        for url in ("http://example.org/a.tar.gz", "ftp://example.org/a", "file:///etc/passwd"):
            with self.subTest(url=url):
                open_url = opener(FakeResponse(b"x"))
                with self.assertRaisesRegex(mz.MaterializeError, "https"):
                    mz.fetch(url, 100, open_url=open_url, sleep=lambda s: None)
                self.assertEqual(open_url.calls, [])


class DeterminismTests(unittest.TestCase):
    def test_rebuild_is_byte_identical(self):
        again = mz.build(copy.deepcopy(PLAN), copy.deepcopy(POLICY), fetcher_for(dict(STORE)))
        self.assertEqual(sorted(again), sorted(OUTPUTS))
        for name in OUTPUTS:
            with self.subTest(name=name):
                self.assertEqual(m.canonical_bytes(again[name]), m.canonical_bytes(OUTPUTS[name]))

    def test_canonical_tar(self):
        members = [{"path": p, "size": len(d), "data": d} for p, d in
                   (("z/b.c", b"bb"), ("a.c", b"aaa"), ("m/x.h", b""))]
        data = mz.canonical_tar(members)
        self.assertEqual(data, mz.canonical_tar(members))
        self.assertEqual(data, mz.canonical_tar(list(reversed(members))))
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            infos = archive.getmembers()
            self.assertEqual([i.name for i in infos], ["a.c", "m/x.h", "z/b.c"])
            for info in infos:
                self.assertEqual((info.mtime, info.uid, info.gid, info.mode, info.uname, info.gname, info.type),
                                 (0, 0, 0, 0o644, "", "", tarfile.REGTYPE))
            self.assertEqual(archive.extractfile("z/b.c").read(), b"bb")

    def test_canonical_gzip(self):
        raw = blob("g", 5000)
        data = mz.canonical_gzip(raw, 9)
        self.assertEqual(data[4:8], b"\0\0\0\0")
        self.assertEqual(data[3] & 0x8, 0)  # no FNAME
        self.assertEqual(gzip.decompress(data), raw)
        self.assertEqual(data, mz.canonical_gzip(raw, 9))


class CorpusLockTests(unittest.TestCase):
    def test_lock_valid(self):
        self.assertEqual(m.validate_corpus_lock(OUTPUTS["corpus-lock.json"], PLAN, POLICY), [])

    def test_counts_and_bytes(self):
        lock, summary = OUTPUTS["corpus-lock.json"], OUTPUTS["materialization.json"]
        retained = [r for s in OUTPUTS["source-lock.json"]["sources"] for r in s["retained"]]
        self.assertTrue(summary["file_track"])  # the 66000-byte member lands in stratum f064k
        for track in POLICY["tracks"]:
            unit = track["unit_bytes"]
            if track["transform"] != "chunk_v1":
                continue
            with self.subTest(track=track["id"]):
                count = sum(1 for o in lock["occurrences"] if o["track"] == track["id"])
                self.assertEqual(count, sum(r["bytes"] // unit for r in retained))
                rows = [t for t in summary["tracks"] if t["track"] == track["id"]]
                self.assertEqual(sum(t["short_tail_members"] for t in rows),
                                 sum(1 for r in retained if r["bytes"] % unit))
                self.assertEqual(sum(t["short_tail_bytes"] for t in rows), sum(r["bytes"] % unit for r in retained))
        self.assertEqual(lock["materialized_bytes"], sum(o["bytes"] for o in lock["occurrences"]))
        self.assertEqual(summary["materialized_bytes"], lock["materialized_bytes"])
        self.assertEqual(summary["occurrences"], len(lock["occurrences"]))

    def test_caps(self):
        acquired = tweak_policy(acquired_bytes_max=sum(map(len, STORE.values())) // 2)
        with self.assertRaisesRegex(mz.MaterializeError, "cap"):
            mz.build(PLAN, acquired, fetcher_for(STORE))
        materialized = tweak_policy(materialized_bytes_max=300_000)
        with self.assertRaisesRegex(mz.MaterializeError, "materialized bytes exceed"):
            mz.build(PLAN, materialized, fetcher_for(STORE))

    def test_no_payload_leak(self):
        store = make_store(PLAN, extra=[("src/marked.c", "file", b"int x;\n/* " + MARKER + b" */\n")])
        outputs = mz.build(PLAN, POLICY, fetcher_for(store))
        self.assertTrue(any(s["retained"] and "src/marked.c" in [r["path"] for r in s["retained"]]
                            for s in outputs["source-lock.json"]["sources"]))
        for name, value in outputs.items():
            with self.subTest(name=name):
                self.assertNotIn(MARKER, m.canonical_bytes(value))


class LockedBuildTests(unittest.TestCase):
    URL = PLAN["families"][0]["releases"][1]["archive"]["url"]

    def test_locked_build_reproduces(self):
        again = mz.build(PLAN, POLICY, fetcher_for(STORE), locked=OUTPUTS["source-lock.json"])
        self.assertEqual(m.canonical_bytes(again["source-lock.json"]), m.canonical_bytes(OUTPUTS["source-lock.json"]))

    def test_changed_download(self):
        data = bytearray(STORE[self.URL])
        data[len(data) // 2] ^= 0xFF  # same size, different bytes
        store = {**STORE, self.URL: bytes(data)}
        with self.assertRaisesRegex(mz.MaterializeError, "changed download"):
            mz.build(PLAN, POLICY, fetcher_for(store), locked=OUTPUTS["source-lock.json"])

    def test_larger_download_hits_locked_cap(self):
        store = {**STORE, self.URL: STORE[self.URL] + b"\0"}
        with self.assertRaises(mz.MaterializeError):
            mz.build(PLAN, POLICY, fetcher_for(store), locked=OUTPUTS["source-lock.json"])

    def test_url_or_format_not_in_lock(self):
        for field, value in (("url", "https://example.org/other.tar.gz"), ("format", "tar.xz")):
            with self.subTest(field=field):
                plan = copy.deepcopy(PLAN)
                plan["families"][0]["releases"][1]["archive"][field] = value
                with self.assertRaisesRegex(mz.MaterializeError, "not in the source lock"):
                    mz.build(plan, POLICY, fetcher_for(STORE), locked=OUTPUTS["source-lock.json"])
        lock = copy.deepcopy(OUTPUTS["source-lock.json"])
        lock["sources"] = [s for s in lock["sources"] if s["source_id"] != "fa-2"]
        with self.assertRaisesRegex(mz.MaterializeError, "not in the source lock"):
            mz.build(PLAN, POLICY, fetcher_for(STORE), locked=lock)

    def test_unavailable_url(self):
        def fetcher(url, cap):
            if url == self.URL:
                raise mz.MaterializeError(f"{url}: HTTP 404")
            return fetcher_for(STORE)(url, cap)
        with self.assertRaisesRegex(mz.MaterializeError, self.URL):
            mz.build(PLAN, POLICY, fetcher)


class ValidateCommittedTests(unittest.TestCase):
    def setUp(self):
        self.files = lock_files(OUTPUTS)

    def validate(self, files=None, plan=PLAN):
        return mz.validate_committed(files or self.files, plan, POLICY)

    def test_clean(self):
        self.assertEqual(self.validate(), [])

    def test_plan_changed(self):
        plan = copy.deepcopy(PLAN)
        plan["status"] = "CHANGED"
        self.assertTrue(any("source plan changed" in e for e in self.validate(plan=plan)))
        plan = copy.deepcopy(PLAN)
        plan["families"][0]["releases"][0]["archive"]["url"] = "https://example.org/moved.tar.gz"
        errors = self.validate(plan=plan)
        self.assertTrue(any("source plan changed" in e for e in errors))
        self.assertTrue(any("differ from the planned releases" in e for e in errors))

    def test_policy_changed(self):
        errors = mz.validate_committed(self.files, PLAN, tweak_policy(planned_pairs_per_codec_max=1))
        self.assertTrue(any("selection policy changed" in e for e in errors))

    def test_tampered_source_lock(self):
        lock = copy.deepcopy(OUTPUTS["source-lock.json"])
        lock["sources"][0]["archive_sha256"] = "not-hex"
        errors = self.validate({**self.files, "source-lock.json": m.canonical_bytes(lock)})
        self.assertTrue(any("does not pin source-lock.json" in e for e in errors))
        self.assertTrue(any("not a SHA-256 hex digest" in e for e in errors))

    def test_non_canonical_or_missing(self):
        pretty = json.dumps(OUTPUTS["source-lock.json"], indent=2).encode()
        errors = self.validate({**self.files, "source-lock.json": pretty})
        self.assertTrue(any("not canonical" in e for e in errors))
        errors = self.validate({k: v for k, v in self.files.items() if k != "licenses.json"})
        self.assertTrue(any("unreadable" in e for e in errors))

    def test_missing_member_is_a_rematerialization_mismatch(self):
        lock = copy.deepcopy(OUTPUTS["source-lock.json"])
        lock["sources"][0]["retained"].append({"bytes": 1, "object_id": "0" * 64, "path": "src/ghost.c"})
        committed = m.canonical_bytes(lock)
        summary = copy.deepcopy(OUTPUTS["materialization.json"])
        summary["source_lock_sha256"] = hashlib.sha256(committed).hexdigest()
        files = {**self.files, "source-lock.json": committed, "materialization.json": m.canonical_bytes(summary)}
        self.assertEqual(self.validate(files), [])  # pins are consistent; only re-materialization notices
        self.assertNotEqual(files["source-lock.json"], m.canonical_bytes(OUTPUTS["source-lock.json"]))


class MainTests(unittest.TestCase):
    def run_main(self, argv, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return mz.main(argv, env={}, **kwargs)

    def test_bad_argv(self):
        for argv in ([], ["discover"], ["bogus", "x"], ["discover", "x", "y"]):
            with self.subTest(argv=argv):
                self.assertEqual(self.run_main(argv), 2)

    def test_unavailable_url_writes_failed_report_and_no_locks(self):
        def fetcher(url, cap):
            raise mz.MaterializeError(f"{url}: HTTP 404")
        with tempfile.TemporaryDirectory() as out:
            self.assertEqual(self.run_main(["discover", out], fetcher=fetcher), 1)
            report = json.loads((Path(out) / "report.json").read_text(encoding="utf-8"))
            self.assertEqual([p.name for p in Path(out).iterdir()], ["report.json"])
        self.assertEqual(report["status"], "failed")
        self.assertIn("https://", report["errors"][0])
        self.assertIn("HTTP 404", report["errors"][0])

    def test_build_failure_via_patch(self):
        with tempfile.TemporaryDirectory() as out, unittest.mock.patch.object(
                mz, "build", side_effect=mz.MaterializeError("https://example.org/x.tar.gz: HTTP 404")):
            self.assertEqual(self.run_main(["discover", out]), 1)
            report = json.loads((Path(out) / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(sorted(p.name for p in Path(out).iterdir()), ["report.json"])
        self.assertEqual(report["status"], "failed")
        self.assertIn("https://example.org/x.tar.gz", report["errors"][0])

    def test_discover_writes_outputs(self):
        with tempfile.TemporaryDirectory() as out, unittest.mock.patch.object(mz, "build", return_value=OUTPUTS):
            self.assertEqual(self.run_main(["discover", out]), 0)
            written = {p.name: p.read_bytes() for p in Path(out).iterdir()}
        self.assertEqual(sorted(written), ["corpus-lock.json.gz", "licenses.json", "materialization.json",
                                           "report.json", "source-lock.json"])
        self.assertEqual(gzip.decompress(written["corpus-lock.json.gz"]), m.canonical_bytes(OUTPUTS["corpus-lock.json"]))
        report = json.loads(written["report.json"])
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["outputs"]["licenses.json"]["sha256"], hashlib.sha256(written["licenses.json"]).hexdigest())

    def test_verify_with_foreign_pilot_files_fails(self):
        with tempfile.TemporaryDirectory() as out, tempfile.TemporaryDirectory() as pilot:
            for name, data in lock_files(OUTPUTS).items():
                (Path(pilot) / name).write_bytes(data)
            self.assertEqual(self.run_main(["verify", out], pilot=Path(pilot)), 1)
            report = json.loads((Path(out) / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "failed")
        self.assertIn("source plan changed", report["errors"][0])


class CommittedPilotTests(unittest.TestCase):
    def test_committed_pilot_files_validate(self):
        if not (mz.PILOT / "source-lock.json").exists():
            self.skipTest("pilot-v1 has not been discovered/committed yet")
        plan = m.loads_strict((mz.CORPUS / "source-plan.json").read_bytes())
        policy = m.loads_strict((mz.CORPUS / "selection-policy.json").read_bytes())
        files = {name: (mz.PILOT / name).read_bytes() for name in mz.LOCK_FILES}
        self.assertEqual(mz.validate_committed(files, plan, policy), [])


if __name__ == "__main__":
    unittest.main()
