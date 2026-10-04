"""Offline Slice C0 adapter tests: synthetic bytes and faults only."""
import bz2
import copy
import gzip
import hashlib
import io
import lzma
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest import mock
import urllib.error
import zipfile
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import manifests as m
import materialize as legacy
import oracle_materialize as om
import oracle_run as runner


def sha(data):
    return hashlib.sha256(data).hexdigest()


def archive_bytes(files, fmt="tar.gz", extra=None):
    raw = io.BytesIO()
    if fmt == "zip":
        with zipfile.ZipFile(raw, "w") as archive:
            for path, data in files.items():
                archive.writestr("root/" + path, data)
        return raw.getvalue()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for path, data in files.items():
            info = tarfile.TarInfo("root/" + path)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
        if extra:
            archive.addfile(extra)
    return {"tar.gz": gzip.compress, "tar.xz": lzma.compress, "tar.bz2": bz2.compress}[fmt](raw.getvalue())


def fixture(fmt="tar.gz", extra=None):
    files = {"b.c": b"abcdefgh", "a.h": b"12345", "README": b"ignored"}
    data = archive_bytes(files, fmt, extra)
    top, members = legacy.normalize(legacy.expand(data, fmt, 1 << 20)[0])
    retained = [item for item in members if item["path"].endswith((".c", ".h"))]
    policy = {"caps": {"acquired_bytes_max": 1 << 20, "materialized_bytes_max": 1 << 20},
              "member_rules": {"include_suffixes": [".c", ".h"], "global_exclude_globs": []},
              "tracks": [{"id": "file", "transform": "member_v1"},
                         {"id": "chunk", "transform": "chunk_v1", "unit_bytes": 4},
                         {"id": "tar", "transform": "canonical_tar_v1"},
                         {"id": "gz", "transform": "canonical_tar_gzip_v1", "compresslevel": 9}]}
    source = {"source_id": "synthetic-1", "family_id": "synthetic", "format": fmt,
              "url": "https://synthetic.invalid/archive", "archive_bytes": len(data),
              "archive_sha256": sha(data), "top_dir": top, "expanded_bytes": legacy.expand(data, fmt, 1 << 20)[1],
              "member_count": len(members),
              "inventory_sha256": m.digest([[v["path"], v["type"], v["size"], v["sha256"]] for v in members]),
              "retained": [{"path": v["path"], "bytes": v["size"], "object_id": v["sha256"]} for v in retained]}
    tar = legacy.canonical_tar(retained)
    payloads = [("file", legacy._provenance("member_v1", "b.c"), files["b.c"], None),
                ("chunk", legacy._provenance("chunk_v1", "b.c", {"unit_bytes": 4}, 4, 4), b"efgh", retained[1]),
                ("tar", legacy._provenance("canonical_tar_v1"), tar, None),
                ("gz", legacy._provenance("canonical_tar_gzip_v1", options={"compresslevel": 9, "zlib_runtime": zlib.ZLIB_RUNTIME_VERSION}),
                 zlib.compress(tar, 9, wbits=31), None)]
    occurrences = [legacy._record(source, "development", {"id": track}, content, prov, parent=parent)
                   for track, prov, content, parent in payloads]
    corpus = {"occurrences": occurrences, "sources": [{k: source[k] for k in
              ("source_id", "family_id", "url", "archive_bytes", "archive_sha256")}],
              "toolchain": {"zlib_runtime": zlib.ZLIB_RUNTIME_VERSION}}
    candidate = {"queries": [{"target": o["occurrence_id"], "status": "near_duplicate", "duplicate_of": None,
                               "bases": [], "candidate_count": 0, "candidate_list_sha256": m.digest([])} for o in occurrences]}
    return candidate, corpus, {"sources": [source]}, policy, data, {sha(v[2]): v[2] for v in payloads}


class MaterializationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=om.WORK)
        self.addCleanup(self.temp.cleanup)
        self.store = Path(self.temp.name) / "store"
        self.candidate, self.corpus, self.sources, self.policy, self.data, self.payloads = fixture()

    def run_store(self, fetcher=None):
        return om.materialize_store(self.store, self.candidate, self.corpus, self.sources, self.policy,
                                    fetcher=fetcher or (lambda url, cap: (self.data, url, 1)))

    def fails(self, failure, call):
        with self.assertRaises(om.MaterializationError) as caught:
            call()
        self.assertEqual(caught.exception.failure_class, failure)
        self.assertEqual(str(caught.exception), failure)
        self.assertNotIn("abcdefgh", repr(caught.exception))

    def test_all_transforms_exact_and_deterministic(self):
        for fmt in ("zip", "tar.gz", "tar.xz", "tar.bz2"):
            with self.subTest(fmt=fmt):
                c, o, s, p, data, payloads = fixture(fmt)
                store = Path(self.temp.name) / fmt
                result = om.materialize_store(store, c, o, s, p, fetcher=lambda u, cap: (data, u, 1))
                self.assertEqual({v.name: v.read_bytes() for v in store.iterdir()}, payloads)
                self.assertEqual(result["verification"]["objects"], len(payloads))
                self.assertEqual(om.expected_objects(c, o), {k: len(v) for k, v in payloads.items()})

    def test_fetch_404_5xx_are_bounded(self):
        for code in (404, 503):
            def fetch(url, cap):
                raise urllib.error.HTTPError(url, code, "abcdefgh", {}, None)
            self.fails("SOURCE_FETCH_FAILED", lambda: self.run_store(fetch))

    def test_archive_size_and_hash_checked_before_expansion(self):
        for bad in (self.data[:-1], b"x" * len(self.data)):
            self.fails("SOURCE_IDENTITY_MISMATCH", lambda: self.run_store(lambda u, cap: (bad, u, 1)))

    def test_traversal_and_links_rejected(self):
        for name, kind in (("root/../escape.c", tarfile.REGTYPE), ("root/link.c", tarfile.SYMTYPE),
                           ("root/hard.c", tarfile.LNKTYPE)):
            info = tarfile.TarInfo(name)
            info.type, info.linkname = kind, "a.h"
            data = archive_bytes({"a.h": b"safe"}, extra=info)
            self.sources["sources"][0].update(archive_bytes=len(data), archive_sha256=sha(data), expanded_bytes=10240)
            self.corpus["sources"][0].update(archive_bytes=len(data), archive_sha256=sha(data))
            self.fails("ARCHIVE_UNSAFE", lambda: self.run_store(lambda u, cap: (data, u, 1)))

    def test_expansion_cap(self):
        self.policy["caps"]["materialized_bytes_max"] = 10
        self.fails("EXPANSION_CAP", self.run_store)

    def test_inventory_and_retained_mismatch(self):
        self.sources["sources"][0]["inventory_sha256"] = "0" * 64
        self.fails("SOURCE_IDENTITY_MISMATCH", self.run_store)
        self.sources["sources"][0]["inventory_sha256"] = fixture()[2]["sources"][0]["inventory_sha256"]
        self.sources["sources"][0]["retained"] = self.sources["sources"][0]["retained"][:1]
        self.fails("SOURCE_IDENTITY_MISMATCH", self.run_store)

    def test_object_wrong_sha_and_size(self):
        for field, value in (("object_id", "0" * 64), ("bytes", 999)):
            self.store = Path(self.temp.name) / field
            self.corpus = copy.deepcopy(fixture()[1])
            self.corpus["occurrences"][0][field] = value
            self.fails("OBJECT_INTEGRITY", self.run_store)

    def test_verify_missing_extra_nonregular_and_wrong_bytes(self):
        self.run_store()
        expected = om.expected_objects(self.candidate, self.corpus)
        item = self.store / next(iter(expected))
        original = item.read_bytes()
        item.unlink()
        self.fails("OBJECT_SET_MISMATCH", lambda: om.verify_store(self.store, expected))
        item.write_bytes(original)
        extra = self.store / ".ignored"
        extra.write_bytes(b"")
        self.fails("OBJECT_SET_MISMATCH", lambda: om.verify_store(self.store, expected))
        extra.unlink()
        item.write_bytes(b"x" * len(original))
        self.fails("OBJECT_INTEGRITY", lambda: om.verify_store(self.store, expected))
        item.unlink()
        item.mkdir()
        self.fails("OBJECT_SET_MISMATCH", lambda: om.verify_store(self.store, expected))

    def test_verify_wrong_length_and_hardlink(self):
        self.run_store()
        expected = om.expected_objects(self.candidate, self.corpus)
        item = self.store / next(iter(expected))
        original = item.read_bytes()
        item.write_bytes(original + b"extra")
        self.fails("OBJECT_INTEGRITY", lambda: om.verify_store(self.store, expected))
        item.write_bytes(original)
        alias = Path(self.temp.name) / "alias"
        try:
            os.link(item, alias)
        except OSError:
            self.skipTest("hardlinks unavailable")
        self.fails("OBJECT_SET_MISMATCH", lambda: om.verify_store(self.store, expected))

    def test_duplicate_member_and_zip_traversal(self):
        info = tarfile.TarInfo("root/a.h")
        self.data = archive_bytes({"a.h": b"safe"}, extra=info)
        self.sources["sources"][0].update(archive_bytes=len(self.data), archive_sha256=sha(self.data), expanded_bytes=10240)
        self.corpus["sources"][0].update(archive_bytes=len(self.data), archive_sha256=sha(self.data))
        self.fails("ARCHIVE_UNSAFE", self.run_store)
        self.store = Path(self.temp.name) / "zip-traversal"
        self.data = archive_bytes({"../outside.c": b"bad"}, fmt="zip")
        self.sources["sources"][0].update(format="zip", archive_bytes=len(self.data), archive_sha256=sha(self.data), expanded_bytes=10)
        self.corpus["sources"][0].update(archive_bytes=len(self.data), archive_sha256=sha(self.data))
        self.fails("ARCHIVE_UNSAFE", self.run_store)

    def test_missing_source_and_conflicting_content_size(self):
        self.sources["sources"] = []
        self.fails("FROZEN_BINDING", self.run_store)
        extra = copy.deepcopy(self.corpus["occurrences"][0])
        extra["source_id"] = "synthetic-2"
        extra["occurrence_id"] = m.occurrence_id(extra["source_id"], extra["provenance"])
        extra["bytes"] += 1
        self.corpus["occurrences"].append(extra)
        self.fails("FROZEN_BINDING", lambda: om.expected_objects(self.candidate, self.corpus))

    def test_frozen_code_and_golden_binding_fail_closed(self):
        original = om._doc
        def changed_code(path):
            doc = original(path)
            if path.name == "seal.json":
                doc["code_sha256"]["manifests.py"] = "0" * 64
            return doc
        with mock.patch.object(om, "_doc", side_effect=changed_code):
            self.fails("FROZEN_BINDING", om.validate_frozen)
        with mock.patch.object(om, "GOLDEN_SHA256", "0" * 64):
            self.fails("FROZEN_BINDING", om.validate_frozen)

    def test_stale_store_rejected_before_fetch(self):
        self.store.mkdir()
        (self.store / "stale").write_bytes(b"")
        with mock.patch.object(legacy, "fetch", side_effect=AssertionError("network")):
            self.fails("OBJECT_SET_MISMATCH", self.run_store)

    def test_parent_symlink_escape(self):
        link = Path(self.temp.name) / "link"
        try:
            link.symlink_to(Path(self.temp.name), target_is_directory=True)
        except OSError:
            self.skipTest("symlinks unavailable on this Windows account")
        self.store = link / "store"
        self.fails("OBJECT_SET_MISMATCH", self.run_store)

    def test_zlib_mismatch_before_fetch(self):
        self.corpus["toolchain"]["zlib_runtime"] = "wrong"
        self.fails("FROZEN_BINDING", lambda: self.run_store(lambda *a: self.fail("fetch invoked")))

    def test_runner_synthetic_store_independent_verification(self):
        directory = Path(self.temp.name) / "runner"
        candidate = runner.synthetic(directory)
        corpus = m.loads_strict((directory / "corpus-lock.json").read_bytes())
        expected = om.expected_objects(candidate, corpus)
        self.assertEqual(om.verify_store(directory / "store", expected)["objects"], 11)

    def test_frozen_excluded_link_is_inventory_only(self):
        info = tarfile.TarInfo("root/tools/link")
        info.type, info.linkname = tarfile.SYMTYPE, "../../outside"
        self.candidate, self.corpus, self.sources, self.policy, self.data, payloads = fixture(extra=info)
        self.sources["sources"][0]["excluded"] = [{"path": "tools/link", "reason": "non_regular_member", "detail": "symlink"}]
        self.run_store()
        self.assertEqual({p.name: p.read_bytes() for p in self.store.iterdir()}, payloads)

    def test_identity_witness_occurrence_is_reconstructed(self):
        target = self.corpus["occurrences"][0]
        duplicate = copy.deepcopy(target)
        duplicate["source_id"] = "synthetic-2"
        duplicate["occurrence_id"] = m.occurrence_id(duplicate["source_id"], duplicate["provenance"])
        self.corpus["occurrences"].append(duplicate)
        source = copy.deepcopy(self.sources["sources"][0])
        source["source_id"] = "synthetic-2"
        self.sources["sources"].append(source)
        corpus_source = copy.deepcopy(self.corpus["sources"][0])
        corpus_source["source_id"] = "synthetic-2"
        self.corpus["sources"].append(corpus_source)
        self.candidate["queries"][0].update(status="identity_only", duplicate_of=duplicate["occurrence_id"])
        calls = []
        def fetch(url, cap):
            calls.append(url)
            return self.data, url, 1
        provenance = self.run_store(fetch)
        self.assertEqual(len(calls), 2)
        self.assertEqual(provenance["required_occurrences"], 5)
        self.assertEqual(provenance["verification"]["objects"], 4)

    def test_bad_duplicate_witness(self):
        self.candidate["queries"][0].update(status="identity_only", duplicate_of=self.corpus["occurrences"][1]["occurrence_id"])
        self.fails("FROZEN_BINDING", lambda: om.expected_objects(self.candidate, self.corpus))

    def test_non_https_source_and_redirect(self):
        self.sources["sources"][0]["url"] = "http://synthetic.invalid/archive"
        self.fails("FROZEN_BINDING", self.run_store)
        self.sources = fixture()[2]
        self.fails("SOURCE_IDENTITY_MISMATCH", lambda: self.run_store(lambda u, cap: (self.data, "http://bad.invalid", 1)))

    def test_occurrence_identity_representative_and_duplicate(self):
        occ = self.corpus["occurrences"][0]
        self.candidate["queries"][0]["bases"] = [{"object_id": occ["object_id"], "representative": "0" * 64}]
        self.fails("FROZEN_BINDING", lambda: om.expected_objects(self.candidate, self.corpus))
        self.candidate = fixture()[0]
        occ["occurrence_id"] = "0" * 64
        self.fails("FROZEN_BINDING", lambda: om.expected_objects(self.candidate, self.corpus))

    def test_natural_metadata_only(self):
        with mock.patch.object(legacy, "fetch", side_effect=AssertionError("natural fetch prohibited")):
            bound = om.validate_frozen()
            candidate, corpus, sources, policy = om.load_natural()
            self.assertEqual(bound["counts"]["queries"], 79)
            self.assertEqual(bound["counts"]["planned_pairs_per_codec"], 1961)
            self.assertGreater(len(om.expected_objects(candidate, corpus)), 0)


if __name__ == "__main__":
    unittest.main()
