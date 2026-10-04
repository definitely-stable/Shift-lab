"""Tests for tools/manifests.py (DELSK-002 corpus/candidate manifest contracts).

Run: python -m unittest discover -s .work/tests -v
Fixtures are built in memory: a tiny valid plan/lock/candidate lock, and each
test mutates one thing. No network, no file writes.
"""

import copy
import datetime as dt
import hashlib
import json
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import manifests as m  # noqa: E402

CORPUS = Path(__file__).resolve().parents[1] / "corpus"
POLICY_PATH = CORPUS / "selection-policy.json"
PLAN_PATH = CORPUS / "source-plan.json"
POLICY = m.loads_strict(POLICY_PATH.read_bytes())
FAMILIES = ["fa", "fb", "fc", "fd", "fe", "ff"]
FILE_SIZE = 70000  # stratum f064k
OBJ0 = "0" * 64


def h(*parts):
    return hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()


def make_plan():
    families = []
    for i, fid in enumerate(FAMILIES):
        releases = []
        for n, year in enumerate((2020, 2021, 2022), 1):
            day = dt.date(year, 1, 1) + dt.timedelta(days=i)  # cross-family times differ
            releases.append({
                "release_id": f"{fid}-{n}", "ordinal": n,
                "archive": {"url": f"https://example.org/{fid}-{n}.tar.gz", "format": "tar.gz", "sha256": None},
                "time": {"value": day.isoformat(), "evidence_url": "https://example.org/tags"}})
        families.append({
            "family_id": fid, "exclude_globs": [], "releases": releases,
            "license": {"spdx": "MIT", "evidence_url": "https://example.org/license",
                        "status": "PENDING_SNAPSHOT_REVIEW"}})
    return {"schema": "delsk.corpus.source-plan.v1", "status": "PROPOSED", "families": families,
            "ancestry_edges": [{"a": "fa", "b": "fb", "resolution": "no_shared_payload",
                                "evidence": "https://example.org/history"}]}


def category(target, base):
    if (base["family_id"], base["provenance"]["member_path"], base["provenance"].get("offset")) == \
            (target["family_id"], target["provenance"]["member_path"], target["provenance"].get("offset")):
        return "same_path_historical"
    return "same_family_decoy" if base["family_id"] == target["family_id"] else "foreign_family_decoy"


class World:
    """A valid tiny plan + policy + corpus lock + candidate lock; tests mutate then seal()."""

    def __init__(self):
        self.plan = make_plan()
        self.policy = copy.deepcopy(POLICY)
        comps = m.ancestry_components(FAMILIES, self.plan["ancestry_edges"])
        self.split = m.assign_splits(comps, self.policy["splits"]["counts"], self.policy["seed"])
        self.dev = [f for f in FAMILIES if self.split[f] == "development"]
        self.cal = next(f for f in FAMILIES if self.split[f] == "calibration")
        d0, d1 = self.dev[:2]
        self.lock = {
            "schema": "delsk.corpus.lock.v1", "materialized_bytes": 12345,
            "toolchain": {"python": "3.12.3", "zlib_runtime": "1.3", "materializer_sha256": h("materializer")}, "exclusions": [], "occurrences": [],
            "components": [{"families": list(c), "split": self.split[c[0]]} for c in comps],
            "sources": [{"source_id": r["release_id"], "family_id": f["family_id"], "url": r["archive"]["url"],
                         "archive_sha256": h("archive", r["release_id"]), "archive_bytes": 1000}
                        for f in self.plan["families"] for r in f["releases"]]}
        for fam in FAMILIES:
            for n in (1, 2, 3):
                for path in ("lib/a.c", "lib/b.c"):
                    self.add(f"{fam}-{n}", path, h(fam, n, path))
        self.add(f"{d0}-1", "lib/alias.c", h(d0, 1, "lib/a.c"))  # duplicate content alias
        for off in (0, 4096):
            self.add(f"{d0}-1", "lib/a.c", h("chunk", off), "chunk-4k", off, h(d0, 1, "lib/a.c"))
        self.target = self.find(f"{d0}-3", "lib/a.c")
        self.bases = [self.find(f"{d0}-1", "lib/a.c"), self.find(f"{d0}-2", "lib/a.c"),
                      self.find(f"{d0}-2", "lib/b.c"), self.find(f"{d1}-2", "lib/a.c")]
        self.cand = {"schema": "delsk.candidate.lock.v1"}
        self.requery()

    def add(self, sid, path, obj, track="file", offset=0, parent=None):
        t = next(t for t in self.policy["tracks"] if t["id"] == track)
        fam = sid.rsplit("-", 1)[0]
        prov = {"transform": t["transform"], "member_path": path, "options": {}, "offset": None, "length": None}
        occ = {"source_id": sid, "family_id": fam, "split": self.split[fam], "track": track, "object_id": obj}
        if t["unit_bytes"] is None:
            occ.update(bytes=FILE_SIZE, stratum="f064k")
        else:
            prov.update(offset=offset, length=t["unit_bytes"], options={"unit_bytes": t["unit_bytes"]})
            occ.update(bytes=t["unit_bytes"], parent_object_id=parent, parent_bytes=FILE_SIZE)
        occ.update(provenance=prov, occurrence_id=m.occurrence_id(sid, prov))
        self.lock["occurrences"].append(occ)
        return occ

    def find(self, sid, path, track="file", offset=None):
        return next(o for o in self.lock["occurrences"] if o["source_id"] == sid and o["track"] == track
                    and o["provenance"]["member_path"] == path and o["provenance"].get("offset") == offset)

    def reid(self, occ):
        occ["occurrence_id"] = m.occurrence_id(occ["source_id"], occ["provenance"])

    def exclude(self, kind, subject, reason, detail="", evidence_url=None):
        if reason in m.MANUAL_REASONS and not detail:
            detail, evidence_url = "fixture evidence", "https://example.org/evidence"
        self.lock["exclusions"].append({"kind": kind, "subject": subject, "reason": reason, "detail": detail,
                                        "evidence_url": evidence_url})

    def query(self, target, bases, status="near_duplicate", dup=None):
        entries = sorted(({"object_id": b["object_id"], "category": category(target, b),
                           "representative": min(o["occurrence_id"] for o in self.lock["occurrences"]
                                                 if o["object_id"] == b["object_id"])} for b in bases),
                         key=lambda e: e["object_id"])
        return {"target": target["occurrence_id"], "status": status, "duplicate_of": dup, "bases": entries}

    def requery(self, target=None, bases=None, **kw):
        self.cand["queries"] = [self.query(target or self.target, self.bases if bases is None else bases, **kw)]
        return self.seal()

    def seal(self):
        """Recompute derived fields (sorting, counts, hashes); tamper tests set fields after this."""
        lock, cand = self.lock, self.cand
        lock["occurrences"].sort(key=lambda o: o["occurrence_id"])
        lock["exclusions"].sort(key=lambda e: (e["kind"], e["subject"], e["reason"]))
        lock["source_plan_sha256"] = m.file_sha256(self.plan)
        lock["selection_policy_sha256"] = m.file_sha256(self.policy)
        cand["queries"].sort(key=lambda q: q["target"])
        for q in cand["queries"]:
            ids = [b["object_id"] for b in q["bases"]]
            q["candidate_count"], q["candidate_list_sha256"] = len(ids), m.digest(ids)
        cand["planned_pairs_per_codec"] = sum(len(q["bases"]) for q in cand["queries"]
                                              if q["status"] == "near_duplicate")
        cand["corpus_lock_sha256"] = m.file_sha256(lock)
        cand["selection_policy_sha256"] = m.file_sha256(self.policy)
        return self

    def corpus_errors(self):
        return m.validate_corpus_lock(self.lock, self.plan, self.policy)

    def cand_errors(self):
        return m.validate_candidate_lock(self.cand, self.lock, self.plan, self.policy)


class Base(unittest.TestCase):
    def has(self, errors, text):
        self.assertTrue(any(text in e for e in errors), f"{text!r} not found in {errors}")


class CanonicalJson(Base):
    VALUE = {"b": [1, None, True], "a": "x", "c": {"z": 0, "y": "é"}}

    def test_roundtrip_bytes_canonical(self):
        data = m.canonical_bytes(self.VALUE)
        self.assertEqual(m.loads_strict(data), self.VALUE)
        self.assertEqual(m.canonical_bytes(m.loads_strict(data)), data)
        self.assertTrue(data.endswith(b"}\n"))
        self.assertNotIn(b"\r", data)

    def test_noncanonical_variants_rejected(self):
        v = self.VALUE
        variants = {
            "compact": json.dumps(v, sort_keys=True).encode(),
            "key order": (json.dumps(v, indent=2) + "\n").encode(),
            "indent 4": (json.dumps(v, sort_keys=True, indent=4, ensure_ascii=False) + "\n").encode(),
            "ascii escapes": (json.dumps(v, sort_keys=True, indent=2) + "\n").encode(),
            "no final newline": m.canonical_bytes(v)[:-1],
            "crlf": m.canonical_bytes(v).replace(b"\n", b"\r\n"),
            "extra blank line": m.canonical_bytes(v) + b"\n",
        }
        for name, data in variants.items():
            with self.subTest(name), self.assertRaisesRegex(ValueError, "canonical"):
                m.loads_strict(data)

    def test_duplicate_key_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            m.loads_strict(b'{\n  "a": 1,\n  "a": 2\n}\n')

    def test_floats_rejected(self):
        for text in (b'{\n  "a": 1.5\n}\n', b'{"a": 1e2}', b'{"a": 1.0}'):
            with self.subTest(text), self.assertRaisesRegex(ValueError, "forbidden JSON number"):
                m.loads_strict(text)
        with self.assertRaisesRegex(ValueError, "floats are forbidden"):
            m.canonical_bytes({"a": 1.0})

    def test_nan_and_infinity_rejected(self):
        for text in (b'{"a": NaN}', b'{"a": Infinity}', b'{"a": -Infinity}'):
            with self.subTest(text), self.assertRaisesRegex(ValueError, "forbidden JSON number"):
                m.loads_strict(text)

    def test_bom_rejected(self):
        with self.assertRaisesRegex(ValueError, "BOM"):
            m.loads_strict(b"\xef\xbb\xbf" + m.canonical_bytes({"a": 1}))

    def test_non_nfc_string_rejected(self):
        data = ('{\n  "a": "é"\n}\n').encode()
        with self.assertRaisesRegex(ValueError, "NFC"):
            m.loads_strict(data)
        with self.assertRaisesRegex(ValueError, "NFC"):
            m.canonical_bytes({"a": "é"})

    def test_non_ascii_key_rejected(self):
        with self.assertRaisesRegex(ValueError, "ASCII"):
            m.loads_strict('{\n  "é": 1\n}\n'.encode())

    def test_digest_differs_from_file_sha256_and_is_stable(self):
        v = {"a": 1}
        self.assertEqual(m.digest(v), hashlib.sha256(b'{"a":1}').hexdigest())
        self.assertEqual(m.digest(v), m.digest(copy.deepcopy(v)))
        self.assertNotEqual(m.digest(v), m.file_sha256(v))
        self.assertEqual(m.file_sha256(v), hashlib.sha256(m.canonical_bytes(v)).hexdigest())

    def test_rank_is_deterministic_and_part_sensitive(self):
        self.assertEqual(m.rank("p", 1, "x"), m.rank("p", 1, "x"))
        self.assertNotEqual(m.rank("p", 1, "x"), m.rank("p", 2, "x"))
        self.assertNotEqual(m.rank("p", 1, "x"), m.rank("q", 1, "x"))


class IdentitiesAndPaths(Base):
    def test_valid_member_path(self):
        for path in ("lib/a.c", "a.h", "a b/c.c"):
            self.assertTrue(m.valid_member_path(path), path)

    def test_invalid_member_paths(self):
        for path in ("", "/abs", "../x", "a/../b", "a//b", "./a", "a\\b", "C:x", "a\x01b", "a\x7fb",
                     "é.c", "a/", "a/.", None, 5):
            with self.subTest(path=path):
                self.assertFalse(m.valid_member_path(path))

    def test_occurrence_id_changes_with_every_field(self):
        prov = {"transform": "chunk_v1", "member_path": "lib/a.c", "offset": 0, "length": 4096,
                "options": {"unit_bytes": 4096}}
        base = m.occurrence_id("s1", prov)
        self.assertEqual(base, m.occurrence_id("s1", copy.deepcopy(prov)))
        self.assertNotEqual(base, m.occurrence_id("s2", prov))
        changes = {"transform": "member_v1", "member_path": "lib/b.c", "offset": 4096, "length": 8192,
                   "options": {"unit_bytes": 8192}}
        for key, value in changes.items():
            with self.subTest(key):
                self.assertNotEqual(base, m.occurrence_id("s1", {**prov, key: value}))
        self.assertNotEqual(base, m.occurrence_id("s1", {k: v for k, v in prov.items() if k != "options"}))

    def test_occurrence_id_independent_of_insertion_order(self):
        prov = {"transform": "chunk_v1", "member_path": "a.c", "offset": 0}
        self.assertEqual(m.occurrence_id("s", prov), m.occurrence_id("s", dict(reversed(list(prov.items())))))

    def test_chunk_spans(self):
        self.assertEqual(m.chunk_spans(10000, 4096), ([(0, 4096), (4096, 4096)], 1808))

    def test_chunk_spans_smaller_than_unit_and_exact(self):
        self.assertEqual(m.chunk_spans(1000, 4096), ([], 1000))
        self.assertEqual(m.chunk_spans(4096, 4096), ([(0, 4096)], 0))


class Time(Base):
    def iv(self, day):
        return m.availability({"value": day})

    def test_date_only_interval(self):
        start = int(dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc).timestamp())
        self.assertEqual(self.iv("2020-01-01"), (start - 14 * 3600, start + 86400 + 12 * 3600))

    def test_date_adjacency_eligibility(self):
        d = lambda n: self.iv((dt.date(2020, 1, 1) + dt.timedelta(days=n)).isoformat())  # noqa: E731
        self.assertFalse(m.time_eligible(d(0), d(1)))
        self.assertFalse(m.time_eligible(d(0), d(2)))
        self.assertTrue(m.time_eligible(d(0), d(3)))
        self.assertFalse(m.time_eligible(d(1), d(0)))
        self.assertFalse(m.time_eligible(d(0), d(0)))

    def test_rfc3339_is_point_interval(self):
        ts = 1577836800  # 2020-01-01T00:00:00Z
        self.assertEqual(self.iv("2020-01-01T00:00:00Z"), (ts, ts))
        self.assertEqual(self.iv("2020-01-01T02:00:00+02:00"), (ts, ts))
        self.assertEqual(self.iv("2019-12-31T19:00:00-05:00"), (ts, ts))

    def test_naive_and_fractional_rejected(self):
        for value in ("2020-01-01T00:00:00", "2020-01-01T00:00:00.5Z", "2020-01-01T00:00:00.123456+00:00"):
            with self.subTest(value), self.assertRaises(ValueError):
                self.iv(value)

    def test_unknown_time(self):
        for time in (None, {}, {"value": None}):
            self.assertIsNone(m.availability(time))
        known = self.iv("2020-01-01")
        self.assertFalse(m.time_eligible(None, known))
        self.assertFalse(m.time_eligible(known, None))
        self.assertFalse(m.time_eligible(None, None))


class AncestryAndSplits(Base):
    def edge(self, a, b, resolution):
        return {"a": a, "b": b, "resolution": resolution}

    def test_merge_joins_families(self):
        self.assertEqual(m.ancestry_components(["a", "b", "c"], [self.edge("a", "b", "merge")]),
                         [("a", "b"), ("c",)])
        chain = [self.edge("c", "b", "merge"), self.edge("b", "a", "merge")]
        self.assertEqual(m.ancestry_components(["a", "b", "c"], chain), [("a", "b", "c")])

    def test_other_resolutions_do_not_join(self):
        edges = [self.edge("a", "b", "path_excluded"), self.edge("b", "c", "no_shared_payload")]
        self.assertEqual(m.ancestry_components(["a", "b", "c"], edges), [("a",), ("b",), ("c",)])

    def test_unknown_family_in_edge_raises(self):
        with self.assertRaisesRegex(ValueError, "unknown family"):
            m.ancestry_components(["a", "b"], [self.edge("a", "zzz", "no_shared_payload")])

    def test_assign_splits_deterministic_and_order_independent(self):
        comps = [(f,) for f in FAMILIES]
        counts, seed = POLICY["splits"]["counts"], POLICY["seed"]
        result = m.assign_splits(comps, counts, seed)
        self.assertEqual(result, m.assign_splits(list(comps), counts, seed))
        for shuffle_seed in range(5):
            shuffled = random.Random(shuffle_seed).sample(comps, len(comps))
            self.assertEqual(result, m.assign_splits(shuffled, counts, seed))
        self.assertEqual([list(result.values()).count(s) for s in m.SPLITS], [4, 1, 1])

    def test_assign_splits_keeps_merged_component_together(self):
        comps = [("fa", "fb")] + [(f,) for f in FAMILIES[2:]]
        result = m.assign_splits(comps, [["development", 3], ["calibration", 1], ["evaluation", 1]], 7)
        self.assertEqual(result["fa"], result["fb"])

    def test_component_count_mismatch_raises(self):
        counts, seed = POLICY["splits"]["counts"], POLICY["seed"]
        for n in (5, 7):
            with self.subTest(n), self.assertRaisesRegex(ValueError, "review"):
                m.assign_splits([(f"f{i}",) for i in range(n)], counts, seed)


class MemberSelection(Base):
    def mem(self, sid, path, size=FILE_SIZE, type="file", fam="fa"):
        return {"source_id": sid, "family_id": fam, "path": path, "size": size, "type": type}

    def select(self, members, family_globs=None):
        return m.select_members(members, POLICY, family_globs or {})

    def test_input_permutation_gives_identical_output(self):
        members = [self.mem(s, p, sz) for s in ("s1", "s2") for p, sz in
                   (("a.c", 70000), ("b.c", 70000), ("c.h", 300000), ("d.c", 300000), ("x/contrib/e.c", 9),
                    ("notes.txt", 5))] + [self.mem("s1", "lib", 0, "dir")]
        expected = self.select(members)
        for seed in range(20):
            self.assertEqual(self.select(random.Random(seed).sample(members, len(members))), expected)

    def test_duplicate_member_path_raises(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.select([self.mem("s1", "a.c"), self.mem("s1", "a.c")])
        self.select([self.mem("s1", "a.c"), self.mem("s2", "a.c")])  # same path in another source is fine

    def test_unsafe_member_raises(self):
        for member in (self.mem("s1", "../x.c"), self.mem("s1", "/x.c"), self.mem("s1", "a.c", type="device")):
            with self.subTest(member), self.assertRaisesRegex(ValueError, "unsafe"):
                self.select([member])

    def test_exclusion_reasons(self):
        out = self.select([self.mem("s1", "docs/readme.md"), self.mem("s1", "lib/l.c", type="symlink"),
                           self.mem("s1", "lib/h.c", type="hardlink"), self.mem("s1", "lib", 0, "dir")])
        reasons = {e["path"]: e["reason"] for e in out["exclusions"]}
        self.assertEqual(reasons, {"docs/readme.md": "not_source_suffix", "lib/l.c": "non_regular_member",
                                   "lib/h.c": "non_regular_member"})
        self.assertEqual(out["retained"], [])  # dirs are skipped silently

    def test_global_and_family_glob_exclusion(self):
        out = self.select([self.mem("s1", "contrib/x.c"), self.mem("s1", "a/vendor/y.h"),
                           self.mem("s1", "gen/z.c"), self.mem("s2", "gen/z.c", fam="fb"),
                           self.mem("s1", "lib/contrib.c")], {"fa": ["gen/*"]})
        got = {e["path"]: (e["reason"], e["detail"]) for e in out["exclusions"]}
        origin = "vendor_or_shared_origin_path"
        self.assertEqual(got, {"contrib/x.c": (origin, "contrib/*"), "a/vendor/y.h": (origin, "*/vendor/*"),
                               "gen/z.c": (origin, "gen/*")})
        self.assertEqual([(r["source_id"], r["path"]) for r in out["retained"]],
                         [("s1", "lib/contrib.c"), ("s2", "gen/z.c")])  # family glob is per family

    def test_one_member_per_release_and_stratum_by_smallest_rank(self):
        paths = {"a.c": 70000, "b.c": 70000, "c.c": 70000, "d.c": 300000, "e.h": 300000, "f.h": 2000000}
        members = [self.mem(s, p, sz) for s in ("s1", "s2") for p, sz in paths.items()]
        members += [self.mem("s1", "tiny.c", 100), self.mem("s1", "huge.c", 20 << 20)]
        out = self.select(members)
        want = {"f064k": ["a.c", "b.c", "c.c"], "f256k": ["d.c", "e.h"], "f001m": ["f.h"]}
        pick = {st: min(ps, key=lambda p: m.rank("member", POLICY["seed"], "fa", p)) for st, ps in want.items()}
        got = {(s["source_id"], s["stratum"]): s["path"] for s in out["selected"]}
        self.assertEqual(got, {(src, st): p for src in ("s1", "s2") for st, p in pick.items()})
        self.assertNotIn("f004m", {s["stratum"] for s in out["selected"]})  # empty strata stay empty
        retained = {r["path"] for r in out["retained"]}
        self.assertLessEqual({"tiny.c", "huge.c"}, retained)  # retained but never selected
        self.assertFalse({"tiny.c", "huge.c"} & {s["path"] for s in out["selected"]})
        self.assertEqual(out["exclusions"], [])


class SourcePlanValidator(Base):
    def setUp(self):
        self.plan = make_plan()

    def errors(self):
        return m.validate_source_plan(self.plan)

    def test_valid_fixture(self):
        self.assertEqual(self.errors(), [])

    def test_archive_hash_rejected(self):
        self.plan["families"][0]["releases"][0]["archive"]["sha256"] = h("x")
        self.has(self.errors(), "no acquisition hash")

    def test_status_must_be_proposed(self):
        self.plan["status"] = "FROZEN"
        self.has(self.errors(), "status must be PROPOSED")

    def test_release_ordinal_gap(self):
        self.plan["families"][0]["releases"][1]["ordinal"] = 3
        self.has(self.errors(), "ordinals must be 1..n")

    def test_same_day_releases_rejected(self):
        releases = self.plan["families"][0]["releases"]
        releases[1]["time"]["value"] = releases[0]["time"]["value"]
        self.has(self.errors(), "does not follow the previous release")

    def test_missing_evidence_urls(self):
        del self.plan["families"][0]["releases"][0]["time"]["evidence_url"]
        self.has(self.errors(), "release time needs https evidence_url")
        del self.plan["families"][1]["license"]["evidence_url"]
        self.has(self.errors(), "license needs spdx and https evidence_url")

    def test_unsorted_families(self):
        self.plan["families"].reverse()
        self.has(self.errors(), "sorted by family_id")

    def test_bad_archive_url_and_format(self):
        self.plan["families"][0]["releases"][0]["archive"].update(url="http://example.org/x", format="rar")
        self.has(self.errors(), "archive needs https url and known format")

    def test_path_excluded_edge_needs_existing_globs(self):
        edge = {"a": "fa", "b": "fb", "resolution": "path_excluded", "evidence": "x", "globs": ["gen/*"]}
        self.plan["ancestry_edges"] = [edge]
        self.has(self.errors(), "must name existing exclude globs")
        edge["globs"] = []
        self.has(self.errors(), "must name existing exclude globs")
        self.plan["families"][0]["exclude_globs"] = [{"glob": "gen/*", "reason": "generated"}]
        edge["globs"] = ["gen/*"]
        self.assertEqual(self.errors(), [])

    def test_edge_with_unknown_family(self):
        self.plan["ancestry_edges"] = [{"a": "fa", "b": "nope", "resolution": "merge", "evidence": "x"}]
        self.has(self.errors(), "unknown family")


class SelectionPolicyValidator(Base):
    def setUp(self):
        self.policy = copy.deepcopy(POLICY)

    def errors(self):
        return m.validate_selection_policy(self.policy)

    def test_committed_policy_is_valid_and_canonical(self):
        self.assertEqual(self.errors(), [])
        self.assertEqual(POLICY_PATH.read_bytes(), m.canonical_bytes(POLICY))

    def test_cap_above_p1_ceiling(self):
        for name, ceiling in m.P1_CAPS.items():
            with self.subTest(name):
                policy = copy.deepcopy(POLICY)
                policy["caps"][name] = ceiling + 1
                self.has(m.validate_selection_policy(policy), "above the P1 ceiling")

    def test_max_targets_overflows_pair_cap(self):
        self.policy["targets"]["max_targets"] = 65  # 65 x (2+30+32) > 4096
        self.has(self.errors(), "can exceed the pair cap")
        self.policy["targets"]["max_targets"] = 64
        self.assertEqual(self.errors(), [])

    def test_padding_rejected(self):
        self.policy["candidates"]["pad_missing_categories"] = True
        self.has(self.errors(), "never be padded")

    def test_missing_forbidden_input(self):
        self.policy["forbidden_selection_inputs"].remove("patch_bytes")
        self.has(self.errors(), "explicitly forbidden")

    def test_overlapping_strata(self):
        strata = self.policy["file_strata"]
        strata[1]["min_bytes"] = strata[0]["max_bytes"] - 1
        self.has(self.errors(), "ascending, disjoint")

    def test_strata_outside_p1_file_range(self):
        self.policy["file_strata"][0]["min_bytes"] = 1024
        self.has(self.errors(), "inside the P1 file range")

    def test_chunk_unit_outside_range(self):
        for unit in (128 << 10, 1024):
            with self.subTest(unit):
                policy = copy.deepcopy(POLICY)
                next(t for t in policy["tracks"] if t["id"] == "chunk-64k")["unit_bytes"] = unit
                self.has(m.validate_selection_policy(policy), "chunk unit outside P1 chunk range")

    def test_bad_split_counts(self):
        self.policy["splits"]["counts"][1][1] = 0
        self.has(self.errors(), "split counts")


@unittest.skipUnless(PLAN_PATH.exists(), "source-plan.json not committed yet")
class CommittedSourcePlan(Base):
    def test_plan_loads_strictly_and_validates(self):
        plan = m.loads_strict(PLAN_PATH.read_bytes())
        self.assertEqual(m.validate_source_plan(plan), [])

    def test_plan_component_count_matches_policy(self):
        plan = m.loads_strict(PLAN_PATH.read_bytes())
        comps = m.ancestry_components([f["family_id"] for f in plan["families"]], plan.get("ancestry_edges", []))
        m.assign_splits(comps, POLICY["splits"]["counts"], POLICY["seed"])  # raises on mismatch


class CorpusLockValidator(Base):
    def setUp(self):
        self.w = World()

    def test_fixture_shape(self):
        w = self.w
        self.assertEqual(len(w.dev), 4)
        self.assertEqual(m.validate_source_plan(w.plan), [])
        self.assertEqual(m.validate_selection_policy(w.policy), [])

    def test_valid(self):
        self.assertEqual(self.w.corpus_errors(), [])

    def test_wrong_schema(self):
        self.w.lock["schema"] = "nope"
        self.assertEqual(self.w.corpus_errors(), ["corpus lock: unexpected schema"])

    def test_tampered_plan_hash(self):
        self.w.lock["source_plan_sha256"] = OBJ0
        self.has(self.w.corpus_errors(), "source plan hash mismatch")

    def test_tampered_policy_hash(self):
        self.w.lock["selection_policy_sha256"] = OBJ0
        self.has(self.w.corpus_errors(), "selection policy hash mismatch")

    def test_changed_plan_without_resealing(self):
        self.w.plan["families"][0]["license"]["spdx"] = "GPL-2.0-only"
        self.has(self.w.corpus_errors(), "source plan hash mismatch")

    def test_wrong_component_split(self):
        comp = self.w.lock["components"][0]
        comp["split"] = next(s for s in m.SPLITS if s != comp["split"])
        self.has(self.w.corpus_errors(), "components/splits differ")

    def test_occurrence_id_not_matching_provenance(self):
        self.w.lock["occurrences"][0]["provenance"]["member_path"] = "lib/zzz.c"
        self.has(self.w.corpus_errors(), "id does not match provenance")

    def test_occurrences_unsorted(self):
        self.w.lock["occurrences"].reverse()
        self.has(self.w.corpus_errors(), "sorted by unique occurrence_id")

    def test_duplicate_occurrence_id(self):
        self.w.lock["occurrences"].append(copy.deepcopy(self.w.lock["occurrences"][-1]))
        self.has(self.w.corpus_errors(), "sorted by unique occurrence_id")

    def test_chunk_split_differs_from_family_split(self):  # transform across split
        chunk = self.w.find(f"{self.w.dev[0]}-1", "lib/a.c", "chunk-4k", 0)
        chunk["split"] = "evaluation"
        self.has(self.w.corpus_errors(), "split differs from its ancestry component")

    def test_chunk_misaligned_offset(self):
        w = self.w
        chunk = w.find(f"{w.dev[0]}-1", "lib/a.c", "chunk-4k", 4096)
        chunk["provenance"]["offset"] = 100
        w.reid(chunk)
        w.seal()
        self.has(w.corpus_errors(), "chunk span invalid")

    def test_chunk_missing_parent(self):
        chunk = self.w.find(f"{self.w.dev[0]}-1", "lib/a.c", "chunk-4k", 0)
        del chunk["parent_object_id"]
        self.has(self.w.corpus_errors(), "chunk needs parent_object_id")

    def test_chunk_parent_differs_from_file_occurrence(self):
        chunk = self.w.find(f"{self.w.dev[0]}-1", "lib/a.c", "chunk-4k", 0)
        chunk["parent_object_id"] = h("other parent")
        self.has(self.w.corpus_errors(), "parent_object_id/parent_bytes differ from the file occurrence")

    def test_file_with_parent_or_span_rejected(self):
        self.w.lock["occurrences"][0]["parent_object_id"] = OBJ0
        self.has(self.w.corpus_errors(), "span/parent only on chunk tracks")

    def test_stratum_mismatch(self):
        self.w.find(f"{self.w.dev[0]}-1", "lib/b.c")["stratum"] = "f256k"
        self.has(self.w.corpus_errors(), "stratum does not match size")

    def test_same_object_different_bytes(self):
        self.w.find(f"{self.w.dev[0]}-1", "lib/alias.c")["bytes"] = FILE_SIZE + 1
        self.has(self.w.corpus_errors(), "same content id with different sizes")

    def test_duplicate_content_aliases_accepted(self):
        w = self.w
        a, alias = w.find(f"{w.dev[0]}-1", "lib/a.c"), w.find(f"{w.dev[0]}-1", "lib/alias.c")
        self.assertEqual(a["object_id"], alias["object_id"])
        self.assertNotEqual(a["occurrence_id"], alias["occurrence_id"])
        self.assertEqual(w.corpus_errors(), [])

    def test_cross_split_content(self):
        w = self.w
        occ = w.find(f"{w.cal}-1", "lib/a.c")
        occ["object_id"] = w.find(f"{w.dev[0]}-1", "lib/a.c")["object_id"]
        self.has(w.corpus_errors(), "without cross_split_content exclusion")
        w.exclude("object", occ["object_id"], "cross_split_content")
        w.seal()
        self.assertEqual(w.corpus_errors(), [])

    def test_unknown_exclusion_reason_or_kind(self):
        for kind, reason in (("object", "because"), ("banana", "self")):
            with self.subTest(kind, reason=reason):
                w = World()
                w.exclude(kind, OBJ0, reason)
                self.has(w.corpus_errors(), "not allowed for kind")

    def test_unsorted_exclusions_and_unknown_occurrence(self):
        w = self.w
        w.exclude("source", w.lock["sources"][1]["source_id"], "license_blocked")
        w.exclude("source", w.lock["sources"][0]["source_id"], "license_blocked")
        self.has(w.corpus_errors(), "exclusions must be sorted and unique")
        w.lock["exclusions"] = []
        w.exclude("occurrence", OBJ0, "license_blocked")
        self.has(w.corpus_errors(), "unknown occurrence")

    def test_invalid_sha256(self):
        oid = self.w.lock["occurrences"][0]["object_id"]
        for bad in (oid.upper(), oid[:10], "g" * 64):
            with self.subTest(bad):
                w = World()
                w.lock["occurrences"][0]["object_id"] = bad
                self.has(w.corpus_errors(), "invalid object_id or bytes")
                w = World()
                w.lock["sources"][0]["archive_sha256"] = bad
                self.has(w.corpus_errors(), "needs archive_sha256")

    def test_materialized_bytes_above_cap(self):
        self.w.lock["materialized_bytes"] = self.w.policy["caps"]["materialized_bytes_max"] + 1
        self.has(self.w.corpus_errors(), "materialized_bytes missing or above cap")

    def test_acquired_bytes_above_cap(self):
        self.w.lock["sources"][0]["archive_bytes"] = self.w.policy["caps"]["acquired_bytes_max"] + 1
        self.has(self.w.corpus_errors(), "acquired bytes exceed cap")

    def test_source_not_in_plan(self):
        self.w.lock["sources"].append({**self.w.lock["sources"][0], "source_id": "zz-1"})
        self.has(self.w.corpus_errors(), "not in source plan")

    def test_source_url_differs_from_plan(self):
        self.w.lock["sources"][0]["url"] = "https://example.org/other.tar.gz"
        self.has(self.w.corpus_errors(), "family/url differ from source plan")


class CandidateLockValidator(Base):
    def setUp(self):
        self.w = World()

    @property
    def q(self):
        return self.w.cand["queries"][0]

    def test_valid(self):
        w = self.w
        self.assertEqual(w.cand_errors(), [])
        self.assertEqual(sorted(b["category"] for b in self.q["bases"]),
                         ["foreign_family_decoy", "same_family_decoy", "same_path_historical", "same_path_historical"])

    def test_wrong_schema(self):
        self.w.cand["schema"] = "nope"
        self.assertEqual(self.w.cand_errors(), ["candidate lock: unexpected schema"])

    def test_bases_unsorted(self):
        self.q["bases"].reverse()
        self.w.seal()
        self.has(self.w.cand_errors(), "bases must be sorted unique content IDs")

    def test_duplicate_base(self):
        self.q["bases"].append(copy.deepcopy(self.q["bases"][-1]))
        self.w.seal()
        self.has(self.w.cand_errors(), "bases must be sorted unique content IDs")

    def test_count_and_hash_mismatch(self):
        self.q["candidate_count"] += 1
        self.has(self.w.cand_errors(), "candidate count/hash mismatch")
        self.w.seal()
        self.q["candidate_list_sha256"] = OBJ0
        self.has(self.w.cand_errors(), "candidate count/hash mismatch")

    def test_self_bytes_in_candidate_list(self):
        w = self.w
        self.q["bases"].append({"object_id": w.target["object_id"], "representative": w.target["occurrence_id"],
                                "category": "same_path_historical"})
        self.q["bases"].sort(key=lambda b: b["object_id"])
        w.seal()
        self.has(w.cand_errors(), "self or exact target bytes in C_t")

    def test_future_base(self):
        w, d0 = self.w, self.w.dev[0]
        w.requery(target=w.find(f"{d0}-2", "lib/a.c"), bases=[w.find(f"{d0}-3", "lib/a.c")])
        self.has(w.cand_errors(), "is not eligible")

    def test_same_release_base(self):
        w, d0 = self.w, self.w.dev[0]
        w.requery(target=w.find(f"{d0}-2", "lib/a.c"), bases=[w.find(f"{d0}-2", "lib/b.c")])
        self.has(w.cand_errors(), "is not eligible")

    def test_base_from_other_split(self):
        w = self.w
        w.requery(bases=[w.find(f"{w.cal}-1", "lib/a.c")])
        self.has(w.cand_errors(), "is not eligible")

    def test_base_from_other_track(self):
        w = self.w
        w.requery(bases=[w.find(f"{w.dev[0]}-1", "lib/a.c", "chunk-4k", 0)])
        self.has(w.cand_errors(), "is not eligible")

    def test_excluded_base(self):
        w = self.w
        w.exclude("object", w.bases[0]["object_id"], "cross_split_content")
        w.seal()
        self.has(w.cand_errors(), "is not eligible")

    def test_representative_not_smallest_eligible(self):
        w = self.w
        obj = w.bases[0]["object_id"]  # has an alias occurrence
        ids = sorted(o["occurrence_id"] for o in w.lock["occurrences"] if o["object_id"] == obj)
        self.assertEqual(len(ids), 2)
        next(b for b in self.q["bases"] if b["object_id"] == obj)["representative"] = ids[-1]
        self.has(w.cand_errors(), "representative is not the smallest eligible occurrence")

    def test_representative_with_other_content(self):
        self.q["bases"][0]["representative"] = self.w.target["occurrence_id"]
        self.has(self.w.cand_errors(), "representative missing or has other content")

    def test_wrong_audit_category(self):
        cats = ("same_path_historical", "same_family_decoy", "foreign_family_decoy")
        for good, bad in zip(cats, cats[1:] + cats[:1]):
            with self.subTest(good=good, bad=bad):
                w = World()
                next(b for b in w.cand["queries"][0]["bases"] if b["category"] == good)["category"] = bad
                self.has(w.cand_errors(), f"audit category must be {good}")

    def test_category_over_cap(self):
        for cat, cap in (("same_path_historical", 1), ("same_family_decoy", 0), ("foreign_family_decoy", 0)):
            with self.subTest(cat):
                w = World()
                w.policy["candidates"][f"{cat}_max"] = cap
                w.seal()
                self.has(w.cand_errors(), f"{cat} exceeds cap")

    def dup_world(self):
        w, d0 = self.w, self.w.dev[0]
        dup = w.add(f"{d0}-2", "lib/dup.c", w.target["object_id"])  # eligible identical bytes
        return w, dup

    def test_identity_only_with_eligible_duplicate(self):
        w, dup = self.dup_world()
        w.requery(status="identity_only", dup=dup["occurrence_id"], bases=[])
        self.assertEqual(w.cand["planned_pairs_per_codec"], 0)
        # identity-only targets alone are a degenerate universe
        self.assertEqual(w.cand_errors(), ["candidate lock: no near_duplicate target; an empty universe cannot be sealed"])

    def test_identity_only_with_bases_rejected(self):
        w, dup = self.dup_world()
        w.requery(status="identity_only", dup=dup["occurrence_id"])
        self.has(w.cand_errors(), "identity_only target must not plan encoder pairs")

    def test_identity_only_needs_eligible_duplicate(self):
        w, dup = self.dup_world()
        w.requery(status="identity_only", dup=None, bases=[])
        self.has(w.cand_errors(), "identity_only needs duplicate_of")
        w.requery(status="identity_only", dup=w.find(f"{w.dev[0]}-1", "lib/b.c")["occurrence_id"], bases=[])
        self.has(w.cand_errors(), "identity_only needs duplicate_of")

    def test_near_duplicate_with_eligible_identical_base_rejected(self):
        w, dup = self.dup_world()
        w.requery()  # status stays near_duplicate
        self.has(w.cand_errors(), "an eligible identical base exists")

    def test_unknown_status(self):
        self.q["status"] = "maybe"
        self.has(self.w.cand_errors(), "unknown status")

    def test_target_from_release_ordinal_1(self):
        w = self.w
        w.requery(target=w.find(f"{w.dev[0]}-1", "lib/a.c"), bases=[])
        self.has(w.cand_errors(), "target release not allowed")

    def test_excluded_target(self):
        w = self.w
        w.exclude("occurrence", w.target["occurrence_id"], "self")
        w.seal()
        self.has(w.cand_errors(), "target is excluded")

    def test_unknown_target_and_unsorted_queries(self):
        w = self.w
        w.cand["queries"].append({**copy.deepcopy(self.q), "target": OBJ0})
        self.has(w.cand_errors(), "unknown target occurrence")
        w.cand["queries"] = [{**copy.deepcopy(self.q), "target": "f" * 64}, copy.deepcopy(self.q)]
        self.has(w.cand_errors(), "queries must be sorted by unique target")

    def test_planned_pairs_mismatch(self):
        self.w.cand["planned_pairs_per_codec"] += 1
        self.has(self.w.cand_errors(), "planned_pairs_per_codec differs")

    def test_planned_pairs_above_cap(self):
        self.w.policy["caps"]["planned_pairs_per_codec_max"] = 3
        self.w.seal()
        self.has(self.w.cand_errors(), "planned pairs exceed cap")

    def test_too_many_targets(self):
        self.w.policy["targets"]["max_targets"] = 0
        self.w.seal()
        self.has(self.w.cand_errors(), "too many near-duplicate targets")

    def test_corpus_and_policy_hash_tampered(self):
        self.w.cand["corpus_lock_sha256"] = OBJ0
        self.has(self.w.cand_errors(), "corpus lock hash mismatch")
        self.w.seal()
        self.w.cand["selection_policy_sha256"] = OBJ0
        self.has(self.w.cand_errors(), "selection policy hash mismatch")

    def test_candidate_identity_independent_of_scores(self):
        w = self.w
        ids = [b["object_id"] for b in self.q["bases"]]
        digest = self.q["candidate_list_sha256"]
        self.assertEqual(digest, m.digest(ids))
        for i, base in enumerate(self.q["bases"]):
            base["score"] = 100 - i  # extra, ignored field
        self.assertEqual(w.cand_errors(), [])
        w.seal()
        self.assertEqual(self.q["candidate_list_sha256"], digest)
        for i, base in enumerate(self.q["bases"]):
            base["score"] = i
        w.seal()
        self.assertEqual(self.q["candidate_list_sha256"], digest)
        self.assertEqual(w.cand_errors(), [])


class ReviewRegressions(Base):
    """Holes found by the independent review of the first contract draft."""

    def setUp(self):
        self.w = World()
        self.d0 = self.w.dev[0]

    def test_vendor_contrib_and_suffix_paths_rejected_in_lock(self):
        for path, plan_glob in (("contrib/x.c", None), ("zlibWrapper/gzlib.c", "zlibWrapper/*"), ("lib/a.txt", None)):
            w = World()
            if plan_glob:
                fam = next(f for f in w.plan["families"] if f["family_id"] == w.dev[0])
                fam["exclude_globs"] = [{"glob": plan_glob, "reason": "shared origin"}]
            w.add(f"{w.dev[0]}-1", path, h("vendored", path))
            w.seal()
            self.has(w.corpus_errors(), "not a retained member")

    def test_duplicate_member_position_rejected(self):
        self.w.add(f"{self.d0}-1", "lib/b.c", h("other bytes"))
        self.w.seal()
        self.has(self.w.corpus_errors(), "duplicate (source, track, member_path, offset)")

    def test_extra_or_missing_provenance_key_rejected(self):
        occ = self.w.find(f"{self.d0}-1", "lib/b.c")
        occ["provenance"]["extra"] = 1
        self.w.reid(occ)
        self.w.seal()
        self.has(self.w.corpus_errors(), "provenance must have exactly")

    def test_file_track_options_rejected(self):
        occ = self.w.find(f"{self.d0}-1", "lib/b.c")
        occ["provenance"]["options"] = {"x": 1}
        self.w.reid(occ)
        self.w.seal()
        self.has(self.w.corpus_errors(), "span/parent only on chunk tracks")

    def test_negative_archive_bytes_cannot_offset_cap(self):
        self.w.lock["sources"][0]["archive_bytes"] = -(10 ** 12)
        self.w.lock["sources"][1]["archive_bytes"] = 10 ** 12
        self.w.seal()
        self.has(self.w.corpus_errors(), "positive archive_bytes")

    def test_missing_source_record_rejected(self):
        del self.w.lock["sources"][-1]
        self.w.seal()
        self.has(self.w.corpus_errors(), "every planned release needs a source record")

    def test_unsorted_sources_rejected(self):
        self.w.lock["sources"].reverse()
        self.w.seal()
        self.has(self.w.corpus_errors(), "sources must be sorted")

    def test_chunk_beyond_parent_rejected(self):
        self.w.add(f"{self.d0}-1", "lib/a.c", h("far chunk"), "chunk-4k", 4096 * 1000, h(self.d0, 1, "lib/a.c"))
        self.w.seal()
        self.has(self.w.corpus_errors(), "chunk span exceeds parent_bytes")

    def test_source_and_member_exclusions_remove_bases(self):
        for kind, subject in (("source", f"{self.d0}-2"), ("member", f"{self.d0}-2:lib/b.c")):
            w = World()
            w.exclude(kind, subject, "license_blocked")
            w.seal()
            self.assertEqual(w.corpus_errors(), [])
            self.has(w.cand_errors(), "is not eligible")

    def test_bool_counts_rejected(self):
        w = self.w
        w.requery(bases=[w.find(f"{self.d0}-1", "lib/a.c")])
        w.cand["queries"][0]["candidate_count"] = True
        self.has(w.cand_errors(), "candidate count/hash mismatch")
        w.seal()
        w.cand["planned_pairs_per_codec"] = True
        self.has(w.cand_errors(), "planned_pairs_per_codec differs")

    def test_policy_pins(self):
        for path, value, text in ((("targets", "release_ordinals"), [1, 2, 3], "release ordinals"),
                                  (("candidates", "same_split"), False, "same_split"),
                                  (("candidates", "temporal"), False, "same_split")):
            policy = copy.deepcopy(POLICY)
            policy[path[0]][path[1]] = value
            self.has(m.validate_selection_policy(policy), text)
        policy = copy.deepcopy(POLICY)
        policy["tracks"][0]["per_member"] = False
        self.has(m.validate_selection_policy(policy), "per_member")

    def test_corpus_lock_rejects_invalid_policy(self):
        self.w.policy["caps"]["acquired_bytes_max"] = 10 ** 13
        self.w.seal()
        self.has(self.w.corpus_errors(), "invalid input")


class SecondReviewRegressions(Base):
    """Holes found by the PR verification review of a14cd62."""

    def setUp(self):
        self.w = World()

    def test_reason_kind_matrix(self):
        sid = self.w.lock["sources"][0]["source_id"]
        for kind, subject, reason in (("source", sid, "category_cap"), ("object", OBJ0, "temporal_ineligible"),
                                      ("member", f"{sid}:lib/a.c", "short_tail"), ("occurrence", OBJ0, "self")):
            w = World()
            w.exclude(kind, subject, reason)
            w.seal()
            self.has(w.corpus_errors(), "not allowed for kind")

    def test_deterministic_reasons_need_true_predicates(self):
        w, sid = self.w, self.w.lock["sources"][0]["source_id"]
        cases = (("source", sid, "unknown_time", "", "known release time"),
                 ("object", "a" * 64, "cross_split_content", "", "more than one split"),
                 ("member", f"{sid}:lib/x.c", "vendor_or_shared_origin_path", "contrib/*", "path rules give"),
                 ("member", f"{sid}:contrib/x.c", "vendor_or_shared_origin_path", "contrib/*", None))
        for kind, subject, reason, detail, text in cases:
            w = World()
            w.exclude(kind, subject, reason, detail)
            w.seal()
            if text:
                self.has(w.corpus_errors(), text)
            else:
                self.assertEqual(w.corpus_errors(), [])

    def test_manual_reason_needs_evidence(self):
        sid = self.w.lock["sources"][0]["source_id"]
        self.w.exclude("source", sid, "license_blocked", detail="x", evidence_url=None)
        self.w.seal()
        self.has(self.w.corpus_errors(), "needs detail and https evidence_url")

    def test_toolchain_required(self):
        del self.w.lock["toolchain"]
        self.w.seal()
        self.has(self.w.corpus_errors(), "toolchain needs")

    def test_tar_gz_options_bind_zlib_runtime(self):
        w = self.w
        sid = w.lock["sources"][0]["source_id"]
        track = next(t for t in w.policy["tracks"] if t["id"] == "tar-gz")
        prov = {"transform": track["transform"], "member_path": None, "offset": None, "length": None,
                "options": {"compresslevel": 9, "zlib_runtime": "1.3"}}
        occ = {"source_id": sid, "family_id": sid.rsplit("-", 1)[0], "split": w.split[sid.rsplit("-", 1)[0]],
               "track": "tar-gz", "object_id": h("targz"), "bytes": 5000, "provenance": prov,
               "occurrence_id": m.occurrence_id(sid, prov)}
        w.lock["occurrences"].append(occ)
        w.seal()
        self.assertEqual(w.corpus_errors(), [])
        before = occ["occurrence_id"]
        w.lock["toolchain"]["zlib_runtime"] = "1.3.1"
        w.seal()
        self.has(w.corpus_errors(), "options must match the track/toolchain")
        prov["options"]["zlib_runtime"] = "1.3.1"
        w.reid(occ)
        w.seal()
        self.assertEqual(w.corpus_errors(), [])
        self.assertNotEqual(before, occ["occurrence_id"])

    def test_max_targets_must_be_positive(self):
        for value in (0, -3):
            policy = copy.deepcopy(POLICY)
            policy["targets"]["max_targets"] = value
            self.has(m.validate_selection_policy(policy), "max_targets must be a positive integer")

    def test_empty_locks_cannot_be_sealed(self):
        w = self.w
        w.cand["queries"] = []
        w.seal()
        self.has(w.cand_errors(), "no near_duplicate target")
        w.lock["occurrences"] = []
        w.seal()
        self.has(w.corpus_errors(), "no occurrences")

    def test_malformed_input_returns_errors(self):
        plan = copy.deepcopy(self.w.plan)
        del plan["families"][0]["family_id"]
        self.assertTrue(m.validate_source_plan(plan))
        for occ in self.w.lock["occurrences"][:2]:
            del occ["occurrence_id"]
        errors = self.w.corpus_errors()
        self.assertTrue(errors and all(isinstance(e, str) for e in errors))


if __name__ == "__main__":
    unittest.main()
