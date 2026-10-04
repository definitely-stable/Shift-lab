"""E1 candidate builder and independent verifier: adversarial cases V01-V56 and properties P01-P18.

Expected outcomes come from the E0 research specification (sections 13-14) and the adopted construction
spec (rulings A01-A10). Worlds are tiny synthetic metadata projections (no payload, no real corpus lock);
every selection case runs the builder (candidates.construct) and the independent derivation
(candidate_verify.derive) and requires identical queries and selection evidence. Synthetic caps and quotas
exist only in fixtures; production caps/seed are used wherever the case does not need small pools.
Every `test_*` line carries its case ids in a trailing comment; test_matrix_complete enforces V01-V56, P01-P18.
"""
import ast
import copy
import datetime as dt
import functools
import gzip
import hashlib
import io
import json
import random
import re
import sys
import tarfile
import unittest
import unittest.mock
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(HERE))
import candidate_verify as cv
import candidates as c
import manifests as m
import materialize as mz
import test_manifests as tm

SEED = 20261004
CAPS = {'same_path_historical': 2, 'same_family_decoy': 30, 'foreign_family_decoy': 32}
SMALL = {'same_path_historical': 2, 'same_family_decoy': 3, 'foreign_family_decoy': 4}
CATS = c.CATEGORIES
SIZE = 4096
TRACKS = {'file': ('member_v1', None, {}), 'chunk-4k': ('chunk_v1', 4096, {'unit_bytes': 4096}),
          'chunk-8k': ('chunk_v1', 8192, {'unit_bytes': 8192}), 'chunk-64k': ('chunk_v1', 65536, {'unit_bytes': 65536}),
          'tar': ('canonical_tar_v1', None, {}),
          'tar-gz': ('canonical_tar_gzip_v1', None, {'compresslevel': 9, 'zlib_runtime': '1.3'})}
PER_ARCHIVE = ('tar', 'tar-gz')
BIND = {k: tm.h('binding', k) for k in c.BINDING_KEYS}


def hc(value):
    """Independent compact hash (no manifests import)."""
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


def obj(content):
    return hashlib.sha256(content.encode()).hexdigest()


def P(**kw):
    return {**{'caps': dict(CAPS), 'max_targets': 64, 'pairs_max': 4096, 'release_ordinals': [2, 3], 'seed': SEED}, **kw}


def prov(track, path, offset=0):
    transform, unit, options = TRACKS[track]
    return {'length': unit, 'member_path': None if track in PER_ARCHIVE else path,
            'offset': offset if unit else None, 'options': dict(options), 'transform': transform}


def mk(sid, fam, path, content, track='chunk-4k', offset=0, split='development'):
    p = prov(track, path, offset)
    return {'bytes': SIZE, 'family_id': fam, 'object_id': obj(content), 'occurrence_id': m.occurrence_id(sid, p),
            'parent_bytes': 65536 if TRACKS[track][1] else None,
            'parent_object_id': obj('parent:' + str(path)) if TRACKS[track][1] else None,
            'provenance': p, 'source_id': sid, 'split': split, 'stratum': 'f064k' if track == 'file' else None,
            'track': track}


def pick_path(sid, pred, track='chunk-4k', offset=0, prefix='z'):
    """A path whose occurrence ID satisfies pred (fixture control over ID order)."""
    for i in range(20000):
        path = f'{prefix}{i}.c'
        if pred(m.occurrence_id(sid, prov(track, path, offset))):
            return path
    raise AssertionError('no path found')


def excl(kind, subject, reason='license_blocked'):
    return {'detail': 'fixture', 'evidence_url': 'https://example.org/e' if reason in m.MANUAL_REASONS else None,
            'kind': kind, 'reason': reason, 'subject': subject}


class Fx:
    """Builder of synthetic worlds."""

    def __init__(self):
        self.sources, self.occs, self.exclusions = {}, [], []

    def src(self, sid, fam, ordinal, lo, hi=None):
        interval = None if lo is None else [lo, lo if hi is None else hi]
        self.sources[sid] = {'availability_interval_utc_seconds': interval, 'family_id': fam, 'ordinal': ordinal,
                             'source_id': sid}
        return self

    def std(self, *fams):
        """Per family three releases at [100n + 10 fam_index] (points), ordinals 1..3."""
        for i, fam in enumerate(fams):
            for n in (1, 2, 3):
                self.src(f'{fam}{n}', fam, n, 100 * (n - 1) + 10 * i)
        return self

    def add(self, sid, path, content, track='chunk-4k', offset=0, split='development'):
        self.occs.append(mk(sid, self.sources[sid]['family_id'], path, content, track, offset, split))
        return self.occs[-1]

    def world(self):
        return copy.deepcopy({'exclusions': self.exclusions, 'occurrences': self.occs,
                              'sources': list(self.sources.values())})


def ident(t, dup):
    return {'bases': [], 'candidate_count': 0, 'candidate_list_sha256': hc([]), 'duplicate_of': dup,
            'status': 'identity_only', 'target': t}


def query(res, rec):
    tid = rec if type(rec) is str else rec['occurrence_id']
    return next(q for q in res['queries'] if q['target'] == tid)


def cats(q):
    return {b['object_id']: b['category'] for b in q['bases']}


def evid(res, rec):
    tid = rec if type(rec) is str else rec['occurrence_id']
    return next(r for r in res['selection']['near_queries'] if r['target'] == tid)['categories']


def ckey(tid, x, seed=SEED):
    return hc(['candidate', seed, tid, x]), x


def lock_of(res, params=None):
    return m.loads_strict(c.make_lock(BIND, res, params or P()))


class Base(unittest.TestCase):
    def both(self, world, params=None):
        """Builder result, asserted equal to the independent derivation (queries, pair sum, selection)."""
        params = params or P()
        got, ref = c.construct(world, params), cv.derive(world, params)
        for key in ('queries', 'planned_pairs_per_codec', 'selection'):
            self.assertEqual(got[key], ref[key], key)
        return got

    def has(self, errors, text):
        self.assertTrue(any(text in e for e in errors), f'{text!r} not found in {errors}')

    def refused(self, world, params=None, text=None):
        with self.assertRaises(c.CandidateError) as cm:
            c.construct(world, params or P())
        if text:
            self.assertIn(text, str(cm.exception))


# --- synthetic documents for admission (tiny valid plan/policy/lock from test_manifests) -------------------

def synth_docs():
    w = tm.World()
    for o in w.lock['occurrences']:  # a real D lock carries explicit nulls
        o.setdefault('parent_object_id', None), o.setdefault('parent_bytes', None)
        o.setdefault('stratum', None)
    sha = {n: tm.h('sha', n) for n in ('plan', 'policy', 'source_lock', 'corpus_lock', 'corpus_lock_canonical',
                                       'acquisition_freeze', 'ancestry_audit', 'historical_bytes',
                                       'construction_spec', 'protocol')}
    docs = {'plan': w.plan, 'policy': w.policy, 'corpus_lock': w.lock,
            'source_lock': {'source_plan_sha256': sha['plan'], 'selection_policy_sha256': sha['policy'],
                            'sources': [{'source_id': s['source_id'], 'archive_sha256': s['archive_sha256'],
                                         'archive_bytes': s['archive_bytes']} for s in w.lock['sources']]},
            'acquisition_freeze': {'status': 'FROZEN_ACQUISITION',
                                   'corpus_lock_canonical_sha256': sha['corpus_lock_canonical'],
                                   'files': {'corpus-lock.json.gz': sha['corpus_lock'],
                                             'source-lock.json': sha['source_lock']}},
            'ancestry_audit': {'status': 'REVIEWED_FOR_PILOT', 'bindings': {'source_lock_sha256': sha['source_lock']},
                               'result': {'unresolved': 0, 'merges': 0, 'new_path_exclusions': 0,
                                          'components': [x['families'] for x in w.lock['components']]}},
            'historical_bytes': {'source_lock_sha256': sha['source_lock'],
                                 'source_pairs': {'total': 2, 'pairs': [
                                     {'base_bytes_attested_before_target_release': True}] * 2}}}
    return docs, sha


# --- layer 1 fixture: a closed source -> U fixture (real policy tracks, 6 families x 3 releases) -------------

@functools.lru_cache(maxsize=None)
def _closed(sizes):
    plan, policy = tm.make_plan(), copy.deepcopy(tm.POLICY)
    comps = m.ancestry_components(tm.FAMILIES, plan['ancestry_edges'])
    split = m.assign_splits(comps, policy['splits']['counts'], policy['seed'])
    occs, sources = [], []
    for f in plan['families']:
        for r in f['releases']:
            sid, members = r['release_id'], []
            for i, size in enumerate(sizes):
                data = random.Random(f'{sid}{i}').randbytes(size)
                members.append({'source_id': sid, 'family_id': f['family_id'], 'path': f'lib/m{i}.c', 'size': size,
                                'type': 'file', 'data': data, 'sha256': hashlib.sha256(data).hexdigest()})
            chosen = m.select_members(members, policy, m.family_globs(plan))
            recs, _ = mz.representations({'source_id': sid, 'family_id': f['family_id']}, split[f['family_id']],
                                         chosen['retained'], chosen['selected'], policy, {'zlib_runtime': '1.3'})
            occs += recs
            sources.append({'source_id': sid, 'family_id': f['family_id'],
                            'retained': [{'bytes': x['size'], 'object_id': x['sha256'], 'path': x['path']}
                                         for x in chosen['retained']]})
    lock = {'components': [{'families': list(x), 'split': split[x[0]]} for x in comps],
            'toolchain': {'zlib_runtime': '1.3'}, 'exclusions': [], 'occurrences': sorted(occs, key=lambda o: o['occurrence_id']),
            'materialized_bytes': sum(o['bytes'] for o in occs)}
    return plan, policy, {'sources': sources}, lock


def closed(sizes=(65536, 8195)):
    return copy.deepcopy(_closed(tuple(sizes)))


def l1(plan, policy, sl, lock):
    return cv.check_source_closure(plan, policy, sl, lock)


# --- random worlds for the metamorphic properties --------------------------------------------------------

PATHS = [f'p{i}.c' for i in range(4)]


def rand_world(seed, exclusions=True):
    rng = random.Random(seed)
    split = {'a': 'development', 'b': 'development', 'c': rng.choice(('development', 'evaluation'))}
    fx = Fx()
    contents = [f'c{i}' for i in range(rng.randint(5, 12))]
    for fam in 'abc':
        base = rng.randint(0, 80)
        for n in (1, 2, 3):
            lo = base + 100 * n + rng.randint(-40, 40)
            fx.src(f'{fam}{n}', fam, n, None if rng.random() < 0.07 else lo, lo + rng.choice((0, 0, 30, 90)))
    for sid in list(fx.sources):
        fam, used = sid[0], set()
        for k in range(rng.randint(3, 9)):
            track, path, offset = rng.choice(('chunk-4k', 'chunk-4k', 'file', 'tar')), rng.choice(PATHS), rng.choice((0, 4096))
            pos = (track, None if track in PER_ARCHIVE else path, offset if TRACKS[track][1] else None)
            if pos in used:
                continue
            used.add(pos)
            fx.add(sid, path, rng.choice(contents) if rng.random() < 0.8 else f'u-{sid}-{k}', track, offset, split[fam])
    if exclusions and rng.random() < 0.3:
        for o in rng.sample([o for o in fx.occs if o['provenance']['member_path']], 2):
            fx.exclusions.append(excl('member', f"{o['source_id']}:{o['provenance']['member_path']}",
                                      'vendor_or_shared_origin_path'))
    caps = {'same_path_historical': rng.randint(1, 3), 'same_family_decoy': rng.randint(1, 4),
            'foreign_family_decoy': rng.randint(1, 4)}
    return fx.world(), P(caps=caps, max_targets=rng.choice((2, 3, 5, 8, 1000)), seed=rng.choice((SEED, 7)))


@functools.lru_cache(maxsize=None)
def _worlds(exclusions):
    return tuple(rand_world(s, exclusions) for s in range(36))


def worlds(exclusions=True):
    return [copy.deepcopy(x) for x in _worlds(exclusions)]


def shuffled(w, rng):
    out = copy.deepcopy(w)
    for key in w:
        rng.shuffle(out[key])
    return out


def elig(w, b, t):
    """Test-side E(b, t) for worlds without exclusions: split, track, options, strict time."""
    src = {s['source_id']: s for s in w['sources']}
    ib, it = (src[x['source_id']]['availability_interval_utc_seconds'] for x in (b, t))
    return (b['occurrence_id'] != t['occurrence_id'] and b['split'] == t['split'] and b['track'] == t['track']
            and b['provenance']['options'] == t['provenance']['options'] and ib and it and ib[1] < it[0])


def add_source(w, sid, fam, lo, ordinal=1):
    w['sources'].append({'availability_interval_utc_seconds': lo, 'family_id': fam, 'ordinal': ordinal, 'source_id': sid})


def near_targets(res, w):
    occ = {o['occurrence_id']: o for o in w['occurrences']}
    return [(occ[q['target']], q) for q in res['queries']
            if q['status'] == 'near_duplicate' and occ[q['target']]['provenance']['member_path'] is not None]


def sources_of(w):
    return {s['source_id']: s for s in w['sources']}


# =============================================================================================================
# V01-V08, V55, V56: identity, aliases, eligibility
# =============================================================================================================

class IdentityAndAliases(Base):
    def test_identity_same_path(self):  # V01
        fx = Fx().std('a')
        old, t = fx.add('a1', 'p0.c', 'X'), fx.add('a2', 'p0.c', 'X')
        res = self.both(fx.world())
        self.assertEqual(res['queries'], [ident(t['occurrence_id'], old['occurrence_id'])])
        self.assertEqual(res['planned_pairs_per_codec'], 0)

    def test_identity_other_path(self):  # V02
        fx = Fx().std('a')
        old, t = fx.add('a1', 'other.c', 'X'), fx.add('a2', 'p0.c', 'X')
        res = self.both(fx.world())
        self.assertEqual(res['queries'], [ident(t['occurrence_id'], old['occurrence_id'])])

    def test_identity_other_family_same_split(self):  # V03
        fx = Fx().std('a', 'b')
        old, t = fx.add('b1', 'p0.c', 'X'), fx.add('a2', 'p0.c', 'X')
        res = self.both(fx.world())
        self.assertEqual(res['queries'], [ident(t['occurrence_id'], old['occurrence_id'])])

    def test_identity_other_split_is_cross_split_exclusion(self):  # V04
        fx = Fx().std('a', 'c')
        fx.add('a1', 'p0.c', 'X'), fx.add('a2', 'p0.c', 'X'), fx.add('c2', 'p0.c', 'X', split='evaluation')
        t = fx.add('a2', 'p1.c', 'Y')
        fx.add('a1', 'p1.c', 'Z')
        w = fx.world()
        res = self.both(w)
        self.assertEqual([q['target'] for q in res['queries']], [t['occurrence_id']])  # no X target, no X role
        cov = c.coverage(w, P(), res)
        self.assertEqual(cov['universe']['cross_split_classes'], 1)
        self.assertEqual(cov['universe']['cross_split_occurrences'], 3)
        self.assertEqual(cov['target_exclusions']['flags']['object'], 3)

    def test_future_duplicate_is_not_identity(self):  # V05
        fx = Fx().std('a')
        t = fx.add('a2', 'p0.c', 'X')
        fut = fx.add('a3', pick_path('a3', lambda i: i < t['occurrence_id']), 'X')
        fx.add('a1', 'y.c', 'Y')
        res = self.both(fx.world())
        q = query(res, t)
        self.assertEqual((q['status'], q['duplicate_of'], list(cats(q))), ('near_duplicate', None, [obj('Y')]))
        self.assertLess(fut['occurrence_id'], t['occurrence_id'])
        self.assertEqual(query(res, fut)['duplicate_of'], t['occurrence_id'])

    def test_future_alias_not_representative_nor_category_witness(self):  # V06
        fx = Fx().std('a')
        t = fx.add('a2', 'p0.c', 'T')
        fut = fx.add('a3', 'p0.c', 'X')  # future alias at the target position
        old = fx.add('a1', pick_path('a1', lambda i: i > fut['occurrence_id']), 'X')
        res = self.both(fx.world())
        q = query(res, t)
        self.assertEqual(q['bases'], [{'category': 'same_family_decoy', 'object_id': obj('X'),
                                       'representative': old['occurrence_id']}])

    def test_base_with_future_other_split_alias_is_globally_excluded(self):  # V07
        fx = Fx().std('a', 'c')
        t = fx.add('a2', 'p0.c', 'T')
        fx.add('a1', 'x.c', 'X'), fx.add('a1', 'y.c', 'Y')
        fx.add('c3', 'p0.c', 'X', split='evaluation')
        res = self.both(fx.world())
        self.assertEqual(list(cats(query(res, t))), [obj('Y')])
        self.assertEqual(evid(res, t)['same_family_decoy']['pool_size'], 1)

    def test_class_with_only_ineligible_aliases_is_absent(self):  # V08
        fx = Fx().std('a').src('a0', 'a', 1, None)
        t = fx.add('a2', 'p0.c', 'T')
        fx.add('a3', 'x.c', 'X'), fx.add('a1', 'x.c', 'X', track='chunk-8k'), fx.add('a0', 'x.c', 'X')
        res = self.both(fx.world())
        q = query(res, t)
        self.assertEqual((q['bases'], q['candidate_count']), ([], 0))
        self.assertEqual([evid(res, t)[k]['pool_size'] for k in CATS], [0, 0, 0])

    def test_same_bytes_in_wrong_track_is_not_identity(self):  # V55
        fx = Fx().std('a')
        t = fx.add('a2', 'p0.c', 'X')
        fx.add('a1', 'p0.c', 'X', track='chunk-8k'), fx.add('a1', 'y.c', 'Y')
        res = self.both(fx.world())
        q = query(res, t)
        self.assertEqual((q['status'], q['duplicate_of'], list(cats(q))), ('near_duplicate', None, [obj('Y')]))

    def test_two_target_aliases_in_one_release_both_scheduled(self):  # V56
        fx = Fx().std('a')
        t1, t2 = fx.add('a2', 'p0.c', 'X'), fx.add('a2', 'p1.c', 'X')
        fx.add('a1', 'y.c', 'Y')
        res = self.both(fx.world())
        for t in (t1, t2):
            q = query(res, t)
            self.assertEqual((q['status'], q['duplicate_of'], list(cats(q))), ('near_duplicate', None, [obj('Y')]))
        self.assertEqual(res['selection']['targets']['all'], 2)  # not collapsed by object ID
        self.assertEqual(res['selection']['targets']['identity'], 0)


# =============================================================================================================
# V09-V16, V33-V35: plan, ancestry, split, time (D-level validators and E eligibility)
# =============================================================================================================

class PlanAncestryTime(Base):
    def test_merge_edge_changes_component_count_stop(self):  # V09
        plan = tm.make_plan()
        plan['ancestry_edges'] = [{'a': 'fa', 'b': 'fb', 'resolution': 'merge', 'evidence': 'https://example.org/h'}]
        comps = m.ancestry_components(tm.FAMILIES, plan['ancestry_edges'])
        self.assertEqual(len(comps), 5)
        with self.assertRaises(ValueError):
            m.assign_splits(comps, tm.POLICY['splits']['counts'], tm.POLICY['seed'])
        with self.assertRaises(ValueError):
            cv.split_assignment(plan, tm.POLICY)

    def test_vendored_member_not_retained(self):  # V10
        w = tm.World()
        w.add(f'{w.dev[0]}-1', 'vendor/x.c', tm.h('v')), w.seal()
        self.has(w.corpus_errors(), 'not a retained member')
        plan, policy, sl, lock = closed()
        sl['sources'][0]['retained'].append({'bytes': 100, 'object_id': tm.h('v'), 'path': 'vendor/v.c'})
        self.has(l1(plan, policy, sl, lock)[0], 'violates member rules')

    def test_unresolved_relation_is_error(self):  # V11
        plan = tm.make_plan()
        plan['ancestry_edges'].append({'a': 'fa', 'b': 'fc', 'resolution': 'unresolved', 'evidence': 'x'})
        self.has(m.validate_source_plan(plan), 'needs resolution and evidence')
        plan['ancestry_edges'][-1] = {'a': 'fa', 'b': 'fc', 'resolution': 'no_shared_payload', 'evidence': ''}
        self.has(m.validate_source_plan(plan), 'needs resolution and evidence')
        docs, sha = synth_docs()
        docs['ancestry_audit']['result']['unresolved'] = 1
        with self.assertRaisesRegex(c.CandidateError, 'ancestry_audit'):
            c.admit_documents(docs, sha)

    def test_build_dependency_no_merge(self):  # V12
        plan = tm.make_plan()
        self.assertEqual(plan['ancestry_edges'][0]['resolution'], 'no_shared_payload')
        self.assertEqual(m.validate_source_plan(plan), [])
        comps, split = cv.split_assignment(plan, tm.POLICY)
        self.assertEqual(len(comps), 6)
        self.assertEqual(split, m.assign_splits(m.ancestry_components(tm.FAMILIES, plan['ancestry_edges']),
                                                tm.POLICY['splits']['counts'], tm.POLICY['seed']))

    def test_overlapping_intervals_are_ineligible(self):  # V13
        fx = Fx().std('a')
        fx.src('bo', 'b', 1, 50, 150).src('bt', 'b', 1, 0, 100).src('bk', 'b', 1, 0, 99)
        t = fx.add('a2', 'p0.c', 'T')
        for sid in ('bo', 'bt', 'bk'):
            fx.add(sid, 'x.c', 'X' + sid)
        res = self.both(fx.world())
        self.assertEqual(list(cats(query(res, t))), [obj('Xbk')])  # overlap and touching intervals excluded

    def test_same_family_reversed_or_overlapping_plan_is_invalid(self):  # V13, V16
        for patch in ({'value': '2020-01-01'}, {'value': '2019-12-01'}, {'value': '2019-12-31'}):
            plan = tm.make_plan()
            plan['families'][0]['releases'][1]['time'] = {**patch, 'evidence_url': 'https://example.org/t'}
            self.has(m.validate_source_plan(plan), 'does not follow the previous release')
        self.assertEqual(m.validate_source_plan(tm.make_plan()), [])

    def test_unknown_target_time_is_not_a_target(self):  # V14
        fx = Fx().std('a').src('a2', 'a', 2, None)
        fx.add('a1', 'x.c', 'X'), fx.add('a2', 'p0.c', 'T'), fx.add('a2', 'p1.c', 'U')
        w = fx.world()
        res = self.both(w)
        self.assertEqual(res['queries'], [])  # no ordinal fallback
        cov = c.coverage(w, P(), res)
        self.assertEqual(cov['target_exclusions']['flags']['unknown_time'], 2)
        self.assertEqual(cov['target_exclusions']['primary']['unknown_time'], 2)

    def test_unknown_base_time_drops_only_that_alias(self):  # V15
        fx = Fx().std('a').src('a0', 'a', 1, None)
        t = fx.add('a2', 'p0.c', 'T')
        known = fx.add('a1', 'k.c', 'X')
        fx.add('a0', pick_path('a0', lambda i: i < known['occurrence_id']), 'X')
        res = self.both(fx.world())
        self.assertEqual(query(res, t)['bases'], [{'category': 'same_family_decoy', 'object_id': obj('X'),
                                                   'representative': known['occurrence_id']}])

    def test_later_published_lower_ordinal_base_is_ineligible(self):  # V16
        fx = Fx().std('a').src('bl', 'b', 1, 300)
        t = fx.add('a2', 'p0.c', 'T')
        fx.add('bl', 'x.c', 'XL'), fx.add('a1', 'y.c', 'Y')
        res = self.both(fx.world())
        self.assertEqual(list(cats(query(res, t))), [obj('Y')])  # version/ordinal is not a clock

    def test_split_mismatch_is_corpus_error(self):  # V34
        w = tm.World()
        w.find(f'{w.dev[0]}-2', 'lib/a.c')['split'] = 'evaluation'
        self.has(w.corpus_errors(), 'split differs from its ancestry component')
        plan, policy, sl, lock = closed()
        o = next(o for o in lock['occurrences'] if o['track'] == 'file')
        o['split'] = 'evaluation' if o['split'] != 'evaluation' else 'calibration'
        self.has(l1(plan, policy, sl, lock)[0], 'family/split/transform binding wrong')

    def test_transform_cannot_change_split(self):  # V35
        w = tm.World()
        chunk = w.find(f'{w.dev[0]}-1', 'lib/a.c', 'chunk-4k', 0)
        chunk['split'] = w.cal if chunk['split'] != w.cal else 'evaluation'
        self.has(w.corpus_errors(), 'split differs from its ancestry component')
        plan, policy, sl, lock = closed()
        o = next(o for o in lock['occurrences'] if o['track'] == 'chunk-8k')
        o['split'] = 'calibration' if o['split'] != 'calibration' else 'evaluation'
        self.has(l1(plan, policy, sl, lock)[0], 'family/split/transform binding wrong')

    def test_unknown_or_conflicting_ancestry_is_error(self):  # V33
        plan = tm.make_plan()
        plan['ancestry_edges'].append({'a': 'fa', 'b': 'nope', 'resolution': 'merge', 'evidence': 'x'})
        with self.assertRaises(ValueError):
            m.ancestry_components(tm.FAMILIES, plan['ancestry_edges'])
        self.has(m.validate_source_plan(plan), 'unknown family')
        with self.assertRaises((KeyError, ValueError)):
            cv.split_assignment(plan, tm.POLICY)
        docs, sha = synth_docs()  # conflicting relation: the audit records a merge -> not admissible (A08)
        docs['ancestry_audit']['result']['merges'] = 1
        with self.assertRaisesRegex(c.CandidateError, 'ancestry_audit'):
            c.admit_documents(docs, sha)
        docs, sha = synth_docs()
        docs['ancestry_audit']['result']['components'][0] = ['nope']
        with self.assertRaisesRegex(c.CandidateError, 'ancestry_audit'):
            c.admit_documents(docs, sha)

    def test_historical_scope_unestablished_is_refused(self):  # V51
        docs, sha = synth_docs()
        docs['historical_bytes']['source_pairs']['pairs'][1]['base_bytes_attested_before_target_release'] = False
        with self.assertRaisesRegex(c.CandidateError, 'historical_bytes'):
            c.admit_documents(docs, sha)
        docs, sha = synth_docs()
        docs['historical_bytes']['source_pairs']['total'] = 3
        with self.assertRaisesRegex(c.CandidateError, 'historical_bytes'):
            c.admit_documents(docs, sha)

    def test_valid_synthetic_documents_admit_and_seal(self):  # P18 positive control
        docs, sha = synth_docs()
        world, params, bindings, layout = c.admit_documents(docs, sha)
        self.assertEqual(params, P())
        self.assertEqual(set(bindings), set(c.BINDING_KEYS))
        res = self.both(world, params)
        self.assertTrue(any(q['status'] == 'near_duplicate' for q in res['queries']))
        self.assertEqual(m.loads_strict(c.make_lock(bindings, res, params))['schema'], 'delsk.candidate.lock.v2')
        cov = c.coverage(world, params, res, layout)
        self.assertEqual(sum(r['targets_all'] for r in cov['cells']), res['selection']['targets']['all'])


# =============================================================================================================
# V17-V23, V44, V53, V54: categories, caps, shortage, aliases
# =============================================================================================================

def pool_world(n):
    fx = Fx().std('a', 'b')
    for i in range(n[0]):
        fx.src(f'ap{i}', 'a', 1, i).add(f'ap{i}', 't.c', f'sp{i}')  # distinct earlier releases at the target position
    for i in range(n[1]):
        fx.add('a1', f'd{i}.c', f'sf{i}')
    for i in range(n[2]):
        fx.add('b1', f'f{i}.c', f'ff{i}')
    return fx, fx.add('a2', 't.c', 'T')


class Categories(Base):
    NAMES = ('sp', 'sf', 'ff')

    def check_pools(self, n, caps):
        fx, t = pool_world(n)
        res = self.both(fx.world(), P(caps=caps))
        tid, q, ev, want = t['occurrence_id'], None, evid(res, t), []
        q = query(res, t)
        for k, name, size in zip(CATS, self.NAMES, n):
            pool = [obj(f'{name}{i}') for i in range(size)]
            chosen = sorted(ckey(tid, x) for x in pool)[:caps[k]]
            want += [(x, k) for _, x in chosen]
            self.assertEqual(ev[k], {'cap': caps[k], 'last_selected_key': list(chosen[-1]) if chosen else None,
                                     'pool_object_ids_sha256': hc(sorted(pool)), 'pool_size': size,
                                     'selected_object_ids': sorted(x for _, x in chosen),
                                     'shortage': max(0, caps[k] - size), 'truncation': max(0, size - caps[k])}, k)
        self.assertEqual([(b['object_id'], b['category']) for b in q['bases']], sorted(want))
        self.assertEqual(q['candidate_list_sha256'], hc(sorted(x for x, _ in want)))
        return q, res

    def test_pool_sizes_zero_one_cap_capplus1(self):  # V17, V18, V19, V20
        for i, k in enumerate(CATS):
            for size in (0, 1, SMALL[k], SMALL[k] + 1):
                with self.subTest(category=k, size=size):
                    n = [0, 0, 0]
                    n[i] = size
                    q, _ = self.check_pools(n, SMALL)
                    self.assertEqual(q['candidate_count'], min(size, SMALL[k]))

    def test_all_categories_short_no_padding(self):  # V21
        q, res = self.check_pools((1, 1, 1), SMALL)
        self.assertEqual(q['candidate_count'], 3)  # sum of the pools, not the sum of the caps
        self.assertEqual([evid(res, q['target'])[k]['shortage'] for k in CATS], [1, 2, 3])

    def test_empty_near_query_consumes_slot_and_is_sealable(self):  # V22
        fx = Fx().std('a')
        t1, t2 = fx.add('a2', 'p0.c', 'T'), fx.add('a2', 'p1.c', 'U')
        w = fx.world()
        res = self.both(w, P(max_targets=1))
        self.assertEqual(len(res['queries']), 1)
        q = res['queries'][0]
        self.assertEqual((q['bases'], q['candidate_count'], q['candidate_list_sha256'], q['duplicate_of'], q['status']),
                         ([], 0, hc([]), None, 'near_duplicate'))
        self.assertEqual(res['selection']['schedule']['stop_reason'], 'near_quota')
        self.assertEqual(sum(u['count'] for u in res['selection']['schedule']['unvisited']), 1)
        self.assertEqual(lock_of(res, P(max_targets=1))['planned_pairs_per_codec'], 0)

    def test_aliases_of_one_class_select_one_object(self):  # V23
        fx = Fx().std('a')
        t = fx.add('a2', 'p0.c', 'T')
        i1, i2, i3 = (fx.add('a1', f'x{i}.c', 'X') for i in range(3))
        res = self.both(fx.world())
        q = query(res, t)
        self.assertEqual(q['bases'], [{'category': 'same_family_decoy', 'object_id': obj('X'),
                                       'representative': min(o['occurrence_id'] for o in (i1, i2, i3))}])
        self.assertEqual(q['candidate_count'], 1)

    def test_foreign_pool_empty_decoys_overflow_production_caps(self):  # V44
        n = (0, 35, 0)
        fx = Fx().std('a')
        for i in range(n[1]):
            fx.add('a1', f'd{i}.c', f'sf{i}')
        t = fx.add('a2', 't.c', 'T')
        res = self.both(fx.world())
        ev, q = evid(res, t), query(res, t)
        self.assertEqual((ev['foreign_family_decoy']['pool_size'], ev['foreign_family_decoy']['shortage']), (0, 32))
        self.assertEqual((q['candidate_count'], ev['same_family_decoy']['truncation']), (30, 5))
        self.assertEqual({b['category'] for b in q['bases']}, {'same_family_decoy'})

    def test_new_same_path_alias_promotes_class_count_30_to_31(self):  # V53
        def build(promote):
            fx = Fx().std('a')
            names = [f'sf{i}' for i in range(31)]
            for i, name in enumerate(names):
                fx.add('a1', f'd{i}.c', name)
            t = fx.add('a2', 't.c', 'T')
            x = min((ckey(t['occurrence_id'], obj(n)) for n in names))[1]  # x is first by rank
            if promote:
                fx.add('a1', 't.c', next(n for n in names if obj(n) == x))  # historical alias at the target position
            return self.both(fx.world()), t, x
        (before, t, x), (after, _, _) = build(False), build(True)
        self.assertEqual(query(before, t)['candidate_count'], 30)
        q = query(after, t)
        self.assertEqual(q['candidate_count'], 31)
        self.assertEqual([b['category'] for b in q['bases'] if b['object_id'] == x], ['same_path_historical'])
        self.assertEqual(len({b['object_id'] for b in q['bases']}), 31)

    def test_smaller_alias_changes_rep_not_ids_nor_lock_hash(self):  # V54
        def build(extra):
            fx = Fx().std('a')
            t = fx.add('a2', 'p0.c', 'T')
            old = fx.add('a1', 'x.c', 'X')
            if extra:
                fx.add('a1', pick_path('a1', lambda i: i < old['occurrence_id']), 'X')
            return self.both(fx.world()), t
        (r1, t), (r2, _) = build(False), build(True)
        q1, q2 = query(r1, t), query(r2, t)
        self.assertEqual(cats(q1), cats(q2))
        self.assertLess(q2['bases'][0]['representative'], q1['bases'][0]['representative'])
        self.assertNotEqual(c.make_lock(BIND, r1, P()), c.make_lock(BIND, r2, P()))

    def test_mixed_aliases_single_category_same_path_rep_may_be_foreign(self):  # V38
        fx = Fx().std('a', 'b')
        t = fx.add('a2', 't.c', 'T')
        s = fx.add('a1', 't.c', 'X')
        f = fx.add('a1', 'o.c', 'X')
        g = fx.add('b1', pick_path('b1', lambda i: i < min(s['occurrence_id'], f['occurrence_id'])), 'X')
        res = self.both(fx.world())
        q = query(res, t)
        self.assertEqual(q['bases'], [{'category': 'same_path_historical', 'object_id': obj('X'),
                                       'representative': g['occurrence_id']}])
        self.assertEqual([evid(res, t)[k]['pool_size'] for k in CATS], [1, 0, 0])  # disjoint partition

    def test_tar_and_targz_same_source_are_distinct_tracks(self):  # V36
        fx = Fx().std('a', 'b')
        t = fx.add('a2', None, 'X', 'tar')
        fx.add('a1', None, 'X', 'tar-gz'), fx.add('a1', None, 'Y', 'tar'), fx.add('b1', None, 'Z', 'tar')
        gz_t = fx.add('a2', None, 'W', 'tar-gz')
        res = self.both(fx.world())
        q = query(res, t)
        self.assertEqual(q['status'], 'near_duplicate')  # a1 tar-gz with equal bytes is no identity base
        self.assertEqual(cats(q), {obj('Y'): 'same_path_historical', obj('Z'): 'foreign_family_decoy'})
        self.assertEqual(evid(res, t)['same_family_decoy']['pool_size'], 0)
        gz = query(res, gz_t)  # earlier tar-gz of the same family is its only base (same path)
        self.assertEqual(cats(gz), {obj('X'): 'same_path_historical'})


# =============================================================================================================
# V24-V32, V45, V48, V50: refusals and closed contracts
# =============================================================================================================

def without_accounting(res):
    res = copy.deepcopy(res)
    for r in res['selection']['near_queries']:
        del r['accounting']
    return res


def valid_world():
    fx = Fx().std('a')
    fx.add('a1', 'x.c', 'X'), fx.add('a2', 'p0.c', 'T')
    return fx.world(), P()


class Refusals(Base):
    def test_duplicate_ids_and_positions_refused(self):  # V24
        w, p = valid_world()
        dup = copy.deepcopy(w)
        dup['occurrences'].append(copy.deepcopy(dup['occurrences'][0]))  # identical record
        self.refused(dup, p, 'duplicate ID')
        with self.assertRaises(ValueError):
            cv.derive(dup, p)
        pos = copy.deepcopy(w)
        again = copy.deepcopy(pos['occurrences'][0])
        again['provenance']['options'] = {'unit_bytes': 4096, 'extra': 1}
        again['occurrence_id'] = m.occurrence_id(again['source_id'], again['provenance'])
        pos['occurrences'].append(again)  # same (source, track, path, offset), new ID
        self.refused(pos, p, 'duplicate provenance position')
        plan, policy, sl, lock = closed()
        lock['occurrences'].append(copy.deepcopy(lock['occurrences'][0]))
        self.has(l1(plan, policy, sl, lock)[0], 'duplicate position')

    def test_id_must_match_provenance_and_one_object_one_size(self):  # V32
        w, p = valid_world()
        bad = copy.deepcopy(w)
        bad['occurrences'][0]['occurrence_id'] = '0' * 64
        self.refused(bad, p, 'ID does not match provenance')
        fx = Fx().std('a')
        fx.add('a1', 'x.c', 'X')['bytes'] = 4096
        fx.add('a2', 'p0.c', 'X')['bytes'] = 4097  # one object ID, two lengths
        self.refused(fx.world(), p, 'different sizes')
        # a same-length forced hash collision is undetectable from metadata alone (spec V32): materialization only

    def test_scores_rejected_by_closed_key_sets(self):  # V29, V30
        w, p = valid_world()
        for key, rng in (('score', 1), ('score', 2), ('scores', 3)):
            for where in ('world', 'occurrence', 'source', 'provenance', 'params', 'caps'):
                bad_w, bad_p = copy.deepcopy(w), copy.deepcopy(p)
                value = random.Random(rng).random()  # reversed or random mock scores
                {'world': bad_w, 'occurrence': bad_w['occurrences'][0], 'source': bad_w['sources'][0],
                 'provenance': bad_w['occurrences'][0]['provenance'], 'params': bad_p, 'caps': bad_p['caps']}[where][key] = value
                with self.subTest(where=where, key=key), self.assertRaises(c.CandidateError):
                    c.construct(bad_w, bad_p)
        inputs = {name: b'' for name in c.INPUTS}
        with self.assertRaisesRegex(c.CandidateError, 'closed inputs'):
            c.admit({**inputs, 'scores': b'{}'})

    def test_scores_attached_after_seal_do_not_change_lock(self):  # V29, V30
        w, p = valid_world()
        res = c.construct(w, p)
        sealed = c.make_lock(BIND, res, p)
        projection = [{'object_id': b['object_id'], 'bytes': SIZE} for q in res['queries'] for b in q['bases']]
        for seed in range(3):  # scorer sees only {object_id, bytes}; its output never flows back
            scores = {x['object_id']: random.Random(seed).random() for x in projection}
            self.assertEqual(c.make_lock(BIND, c.construct(w, p), p), sealed)
            self.assertEqual(set(scores), {x['object_id'] for x in projection})

    def test_encoder_and_codec_fields_rejected(self):  # V31
        w, p = valid_world()
        for key in ('gain', 'codec_options', 'patch_bytes', 'encoder'):
            for where in ('occurrence', 'source', 'params'):
                bad_w, bad_p = copy.deepcopy(w), copy.deepcopy(p)
                {'occurrence': bad_w['occurrences'][1], 'source': bad_w['sources'][1], 'params': bad_p}[where][key] = 1
                with self.subTest(where=where, key=key), self.assertRaises(c.CandidateError):
                    c.construct(bad_w, bad_p)

    def test_construction_imports_no_scorer_encoder_or_ambient_state(self):  # V29, V31, P06
        def imports(name):
            tree = ast.parse((ROOT / 'tools' / name).read_text(encoding='utf-8'))
            return {a.name.split('.')[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} | \
                   {n.module.split('.')[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        self.assertEqual(imports('candidates.py'), {'collections', 'gzip', 'hashlib', 'manifests'})
        self.assertLessEqual(imports('candidate_verify.py'), {'fnmatch', 'gzip', 'hashlib', 'json', 'datetime', 'manifests'})
        self.assertNotIn('candidates', imports('candidate_verify.py'))  # A09: no shared selector
        self.assertNotIn('candidate_verify', imports('candidates.py'))

    def test_make_lock_refuses_unsealable_and_over_cap(self):  # V41, V45
        fx = Fx().std('a')
        fx.add('a1', 'p0.c', 'X'), fx.add('a2', 'p0.c', 'X')
        res = self.both(fx.world())
        with self.assertRaisesRegex(c.CandidateError, 'no near_duplicate'):
            c.make_lock(BIND, res, P())
        w, p = valid_world()
        res = c.construct(w, p)
        tampered = {**res, 'planned_pairs_per_codec': res['planned_pairs_per_codec'] + 1}
        with self.assertRaisesRegex(c.CandidateError, 'planned pairs'):
            c.make_lock(BIND, tampered, p)
        with self.assertRaisesRegex(c.CandidateError, 'planned pairs'):
            c.make_lock(BIND, res, P(pairs_max=0))
        for bad in ({**BIND, 'extra': BIND['protocol_sha256']}, {k: v for k, v in BIND.items() if k != 'protocol_sha256'},
                    {**BIND, 'protocol_sha256': 'xyz'}):
            with self.assertRaisesRegex(c.CandidateError, 'bindings'):
                c.make_lock(bad, res, p)

    def test_identity_with_bases_and_wrong_count_refused_by_verifier(self):  # V45
        fx = Fx().std('a')
        fx.add('a1', 'p0.c', 'X'), fx.add('a2', 'p0.c', 'X'), fx.add('a1', 'y.c', 'Y'), fx.add('a2', 'q.c', 'Q')
        w = fx.world()
        res = self.both(w)
        lock, sel = lock_of(res), res['selection']
        ref = cv.derive(w, P())
        self.assertEqual(cv.compare(ref, lock, sel), [])
        for mutate in (lambda q: q.update(bases=[{'category': 'same_family_decoy', 'object_id': obj('Y'),
                                                  'representative': q['target']}]),
                       lambda q: q.update(candidate_count=7)):
            bad = copy.deepcopy(lock)
            mutate(next(q for q in bad['queries'] if q['status'] == 'identity_only'))
            self.assertTrue(cv.compare(ref, bad, sel))
        bad = {**lock, 'planned_pairs_per_codec': lock['planned_pairs_per_codec'] + 1}
        self.has(cv.compare(ref, bad, sel), 'planned_pairs_per_codec differs')

    def test_bool_count_changes_canonical_bytes(self):  # V45
        w, p = valid_world()
        res = c.construct(w, p)
        near = next(q for q in res['queries'] if q['status'] == 'near_duplicate' and q['candidate_count'] == 1)
        lock = lock_of(res, p)
        bad = copy.deepcopy(lock)
        next(q for q in bad['queries'] if q['target'] == near['target'])['candidate_count'] = True
        self.assertNotEqual(m.canonical_bytes(bad), m.canonical_bytes(lock))  # verify() ends on a byte comparison

    def test_compare_alone_rejects_bool_count(self):  # V45
        w, p = valid_world()
        res = c.construct(w, p)
        lock = lock_of(res, p)
        next(q for q in lock['queries'] if q['candidate_count'] == 1)['candidate_count'] = True
        self.has(cv.compare(cv.derive(w, p), lock, res['selection']), 'candidate_count')

    def test_make_lock_refuses_malformed_queries(self):  # V45
        fx = Fx().std('a')
        fx.add('a1', 'x.c', 'X'), fx.add('a2', 'p0.c', 'T'), fx.add('a1', 'd.c', 'D'), fx.add('a2', 'e.c', 'D')
        p = P()
        res = c.construct(fx.world(), p)
        near = next(q for q in res['queries'] if q['status'] == 'near_duplicate' and q['candidate_count'] >= 1)
        self.assertTrue(any(q['status'] == 'identity_only' for q in res['queries']))
        for name, status, mutate in (('identity_with_bases', 'identity_only', lambda q: q.update(bases=near['bases'])),
                                     ('bool_count', 'near_duplicate', lambda q: q.update(candidate_count=True)),
                                     ('hash_mismatch', 'near_duplicate', lambda q: q.update(candidate_list_sha256='0' * 64))):
            bad = copy.deepcopy(res)
            mutate(next(q for q in bad['queries'] if q['status'] == status and (status == 'identity_only' or q['target'] == near['target'])))
            with self.subTest(name), self.assertRaises(c.CandidateError):
                c.make_lock(BIND, bad, p)

    def test_license_blocked_member_with_retained_composite_is_refused(self):  # V50, V10
        fx = Fx().std('a')
        fx.add('a1', 'bad.c', 'B'), fx.add('a1', None, 'TAR', 'tar'), fx.add('a2', 'p0.c', 'T')
        fx.exclusions = [excl('member', 'a1:bad.c')]
        self.refused(fx.world(), P(), 'retains a license-excluded member')
        fx.exclusions = [excl('occurrence', fx.occs[0]['occurrence_id'])]
        self.refused(fx.world(), P(), 'retains a license-excluded member')
        fx.exclusions = [excl('source', 'a1')]  # reviewed conservative whole-source exclusion is the allowed route
        self.both(fx.world())
        fx.exclusions = [excl('member', 'a1:bad.c', 'vendor_or_shared_origin_path')]  # non-license reason
        self.both(fx.world())

    def test_changed_bytes_or_binding_refused_by_admission(self):  # V43, V48
        inputs = real_inputs()
        for name, data in inputs.items():
            with self.subTest(name=name), self.assertRaisesRegex(c.CandidateError, f'{name}: SHA-256 differs'):
                c.admit({**inputs, name: data + b' '})
        seed = inputs['policy'].replace(b'20261004', b'20261005')
        self.assertNotEqual(seed, inputs['policy'])
        with self.assertRaisesRegex(c.CandidateError, 'policy: SHA-256 differs'):
            c.admit({**inputs, 'policy': seed})
        with self.assertRaisesRegex(c.CandidateError, 'missing'):
            c.admit({k: v for k, v in inputs.items() if k != 'ancestry_audit'})

    def test_verifier_refuses_changed_inputs_and_freeze(self):  # V48
        inputs = real_inputs()
        freeze = (ROOT / 'corpus' / 'e0' / 'freeze.json').read_bytes()
        self.assertEqual(cv.verify(inputs, freeze + b' ', b'', {})['status'], 'refused')
        spec = {**inputs, 'construction_spec': inputs['construction_spec'] + b' '}
        report = cv.verify(spec, freeze, b'', {})
        self.assertEqual(report['status'], 'refused')
        self.has(report['errors'], 'construction_spec')
        self.assertEqual(cv.verify({k: v for k, v in inputs.items() if k != 'protocol'}, freeze, b'', {})['status'],
                         'refused')

    def test_changed_seed_or_cap_changes_lock_bytes(self):  # V48
        fx = pool_world((0, 8, 0))[0]
        w, p = fx.world(), P(caps=SMALL)
        base = c.make_lock(BIND, c.construct(w, p), p)
        for q in (P(caps=SMALL, seed=SEED + 1), P(caps={**SMALL, 'same_family_decoy': 4})):
            self.assertNotEqual(c.make_lock(BIND, c.construct(w, q), q), base)


@functools.lru_cache(maxsize=1)
def _real_inputs():
    return {name: (ROOT.parent / path).read_bytes() for name, (path, _) in c.INPUTS.items()}


def real_inputs():
    return dict(_real_inputs())


# =============================================================================================================
# V25-V28, V39-V41, V42-V43, V46-V47, V49, V52: ordering, schedule, tamper detection
# =============================================================================================================

def golden(case_id):
    v = m.loads_strict((ROOT / 'corpus' / 'e0' / 'golden-vectors.json').read_bytes())
    return next(x for x in v['cases'] if x['id'] == case_id)


class OrderingAndSchedule(Base):
    def test_iteration_permutations_do_not_change_result_or_bytes(self):  # V25, V27, V28
        for seed in (1, 4, 9):
            w, p = rand_world(seed)
            res = self.both(w, p)
            for k in range(3):
                perm = shuffled(w, random.Random(100 * seed + k))
                again = self.both(perm, p)
                self.assertEqual(again, res)
                self.assertEqual(again['selection']['schedule']['traversal'], res['selection']['schedule']['traversal'])
                self.assertEqual([q['target'] for q in again['queries']], sorted(q['target'] for q in again['queries']))
                if any(q['status'] == 'near_duplicate' for q in res['queries']):
                    self.assertEqual(c.make_lock(BIND, again, p), c.make_lock(BIND, res, p))

    def test_noncanonical_frozen_bytes_rejected_internal_view_accepted(self):  # V27
        w, p = valid_world()
        lock = lock_of(c.construct(w, p), p)
        for text in (json.dumps(lock), json.dumps(lock, indent=2), json.dumps(lock, indent=2, sort_keys=True)[:-1],
                     json.dumps(dict(reversed(list(lock.items()))), indent=2)):
            with self.subTest(text=text[:20]), self.assertRaises(ValueError):
                m.loads_strict(text.encode())
        self.assertEqual(m.loads_strict(m.canonical_bytes(lock)), lock)

    def test_canonical_tar_member_order_independent(self):  # V26
        members = [{'path': f'd/{n}.c', 'size': len(n), 'data': n.encode()} for n in ('b', 'a', 'cc', 'dd')]
        tar = mz.canonical_tar(members)
        for order in ([3, 2, 1, 0], [1, 3, 0, 2]):
            self.assertEqual(mz.canonical_tar([members[i] for i in order]), tar)
        self.assertEqual(mz.canonical_gzip(tar, 9), mz.canonical_gzip(mz.canonical_tar(members[::-1]), 9))
        with tarfile.open(fileobj=io.BytesIO(tar)) as t:
            self.assertEqual([i.name for i in t.getmembers()], sorted(x['path'] for x in members))
        retained = [{'source_id': 's', 'family_id': 'a', 'path': x['path'], 'size': len(x['data']) * SIZE, 'data': x['data'] * SIZE,
                     'sha256': hashlib.sha256(x['data'] * SIZE).hexdigest()} for x in members]
        records = [sorted(mz.representations({'source_id': 's', 'family_id': 'a'}, 'development', order, [], tm.POLICY,
                                             {'zlib_runtime': '1.3'})[0], key=lambda r: r['occurrence_id'])
                   for order in (retained, retained[::-1])]
        self.assertEqual(records[0], records[1])  # same representation records (IDs, objects) for any member order
        self.assertTrue(any(r['track'] == 'tar-gz' for r in records[0]))

    def test_golden_minimum_eligible_alias_and_class_category(self):  # V01, V23, V38, V39
        for name, key in (('minimum-eligible-alias', 'queries_for_requested_targets'),
                          ('class-category-independent-of-representative', 'query')):
            case = golden(name)
            res = self.both(case['input'])
            want = case['expected'][key]
            for q in want if type(want) is list else [want]:
                self.assertEqual(query(res, q['target']), q)

    def test_min_duplicate_and_representative_ignore_smaller_future_alias(self):  # V39, V01
        fx = Fx().std('a', 'b')
        i1, i2 = fx.add('a1', 'x1.c', 'X'), fx.add('b1', 'x2.c', 'X')
        i0 = fx.add('a3', pick_path('a3', lambda i: i < min(i1['occurrence_id'], i2['occurrence_id'])), 'X')
        t, other = fx.add('a2', 'p0.c', 'X'), fx.add('a2', 'q.c', 'Q')
        res = self.both(fx.world())
        self.assertEqual(query(res, t)['duplicate_of'], min(i1['occurrence_id'], i2['occurrence_id']))
        self.assertLess(i0['occurrence_id'], query(res, t)['duplicate_of'])
        self.assertEqual(query(res, other)['bases'][0]['representative'], min(i1['occurrence_id'], i2['occurrence_id']))

    def test_golden_identity_consumes_group_turn(self):  # V28, V40
        case = golden('identity-consumes-group-turn')
        e = case['expected']
        p = P(max_targets=case['fixture_only_near_quota'])
        w = case['input']
        for perm in (w, {k: list(reversed(v)) for k, v in w.items()}):
            res = self.both(perm, p)
            self.assertEqual(res['queries'], e['queries_sorted_by_target'])
            self.assertEqual([t['target'] for t in res['selection']['schedule']['traversal']], e['visited_target_ids'])
            self.assertEqual([t['group'] for t in res['selection']['schedule']['traversal']],
                             [t['group'] for t in e['traversal']])
            left = [u for u in res['selection']['schedule']['unvisited'] if u['count']]
            self.assertEqual([u['target_ids_sha256'] for u in left], [hc(sorted(e['unvisited_target_ids']))])
            self.assertEqual(res['planned_pairs_per_codec'], e['planned_pairs_per_codec'])
            self.assertEqual(res['selection']['schedule']['stop_reason'], 'near_quota')  # golden text is prose
            self.assertEqual({k: res['selection']['targets'][k] for k in ('all', 'identity', 'near_opportunity')},
                             {'all': e['all_target_count'], 'identity': e['all_identity_count'],
                              'near_opportunity': e['all_near_opportunity_count']})
        self.assertNotEqual(sorted(e['visited_target_ids']), sorted(e['incorrect_prefilter_identity_result']))

    def test_identity_does_not_consume_near_quota_and_stops_exactly(self):  # V40
        fx = Fx().std('a', 'b')
        fx.add('a1', 'p0.c', 'I'), fx.add('a2', 'p0.c', 'I')  # identity in group (a, chunk-4k)
        for i in range(3):
            fx.add('b2', f'n{i}.c', f'N{i}')
        fx.add('b1', 'y.c', 'Y')
        res = self.both(fx.world(), P(max_targets=2))
        near = [q for q in res['queries'] if q['status'] == 'near_duplicate']
        self.assertEqual(len(near), 2)
        self.assertEqual(res['selection']['schedule']['stop_reason'], 'near_quota')
        self.assertEqual([t['near_count_after'] for t in res['selection']['schedule']['traversal']][-1], 2)

    def test_only_identity_or_no_targets_not_sealable_but_coverage_kept(self):  # V41
        for build in (lambda f: (f.add('a1', 'p0.c', 'X'), f.add('a2', 'p0.c', 'X')), lambda f: f.add('a1', 'p0.c', 'X')):
            fx = Fx().std('a')
            build(fx)
            w = fx.world()
            res = self.both(w)
            with self.assertRaises(c.CandidateError):
                c.make_lock(BIND, res, P())
            cov = c.coverage(w, P(), res)
            self.assertEqual(cov['universe']['occurrences'], len(w['occurrences']))
            self.assertEqual(cov['rates']['empty_pool_selected_near'], [0, 0])
            self.assertTrue(cov['cells'])

    def test_tampered_lock_detected_by_independent_check(self):  # V42
        fx, t = pool_world((0, 4, 0))  # pool = cap + 1
        w, p = fx.world(), P(caps=SMALL)
        res = self.both(w, p)
        ref, sel, lock = cv.derive(w, p), res['selection'], lock_of(res, p)
        self.assertEqual(cv.compare(ref, lock, sel), [])

        def reseal(bad, bases):
            q = bad['queries'][0]
            q['bases'] = sorted(bases, key=lambda b: b['object_id'])
            ids = [b['object_id'] for b in q['bases']]
            q['candidate_count'], q['candidate_list_sha256'] = len(ids), hc(ids)
            bad['planned_pairs_per_codec'] = len(ids)
            return bad
        bases = lock['queries'][0]['bases']
        self.has(cv.compare(ref, reseal(copy.deepcopy(lock), bases[:-1]), sel), 'field bases differs')  # drop an eligible base
        ranked = sorted((ckey(t['occurrence_id'], obj(f'sf{i}')) for i in range(4)))
        last = ranked[3][1]  # rank cap + 1 replaces the lowest-ranked selected class
        rep = min(o['occurrence_id'] for o in fx.occs if o['object_id'] == last)
        swapped = [b for b in bases if b['object_id'] != ranked[2][1]] + \
                  [{'category': 'same_family_decoy', 'object_id': last, 'representative': rep}]
        self.has(cv.compare(ref, reseal(copy.deepcopy(lock), swapped), sel), 'field bases differs')

    def test_truncated_universe_detected_by_source_closure(self):  # V43
        plan, policy, sl, lock = closed()
        victim = next(o for o in lock['occurrences'] if o['track'] == 'chunk-4k')
        lock['occurrences'].remove(victim)
        lock['materialized_bytes'] -= victim['bytes']  # aggregate updated
        errors, counts = l1(plan, policy, sl, lock)
        self.has(errors, 'missing expected position')
        self.assertEqual(counts['missing'], 1)
        base_errors, base_counts = l1(*closed())
        self.assertEqual((base_errors, base_counts['missing'], base_counts['extra']), ([], 0, 0))

    def test_target_membership_tampering_detected(self):  # V46
        fx = Fx().std('a', 'b')
        for i in range(3):
            fx.add('a2', f'p{i}.c', f'T{i}'), fx.add('b2', f'p{i}.c', f'U{i}')
        fx.add('a1', 'y.c', 'Y'), fx.add('b1', 'y.c', 'Z')
        w, p = fx.world(), P(max_targets=2)
        res = self.both(w, p)
        ref, lock = cv.derive(w, p), lock_of(res, p)
        self.assertEqual(len(lock['queries']), 2)
        self.assertEqual(cv.compare(ref, lock, res['selection']), [])
        dropped = {**lock, 'queries': lock['queries'][1:]}
        self.has(cv.compare(ref, dropped, res['selection']), 'scheduled but absent')
        other = next(q for q in c.construct(w, P(max_targets=64))['queries'] if q['target'] not in ref_targets(ref))
        extra = {**lock, 'queries': sorted(lock['queries'] + [other], key=lambda q: q['target'])}
        self.has(cv.compare(ref, extra, res['selection']), 'not in the scheduled prefix')

    def test_list_hash_is_over_sorted_ids_and_rep_category_tampering_detected(self):  # V47
        fx = Fx().std('a')
        for i in range(8):
            fx.add('a1', f'd{i}.c', f'sf{i}')
        t = fx.add('a2', 't.c', 'T')
        w, p = fx.world(), P(caps={**CAPS, 'same_family_decoy': 6})
        res = self.both(w, p)
        q = query(res, t)
        by_rank = [x for _, x in sorted(ckey(t['occurrence_id'], obj(f'sf{i}')) for i in range(8))][:6]
        self.assertNotEqual(by_rank, sorted(by_rank))
        self.assertEqual(q['candidate_list_sha256'], hc(sorted(by_rank)))
        self.assertNotEqual(q['candidate_list_sha256'], hc(by_rank))
        ref, lock, sel = cv.derive(w, p), lock_of(res, p), res['selection']
        bad = copy.deepcopy(lock)
        bad['queries'][0]['candidate_list_sha256'] = hc(by_rank)
        self.has(cv.compare(ref, bad, sel), 'field candidate_list_sha256 differs')
        bad = copy.deepcopy(lock)
        bad['queries'][0]['bases'][0]['category'] = 'foreign_family_decoy'  # same list hash
        self.has(cv.compare(ref, bad, sel), 'field bases differs')
        bad = copy.deepcopy(lock)
        bad['queries'][0]['bases'][0]['representative'] = '0' * 64
        self.has(cv.compare(ref, bad, sel), 'field bases differs')
        self.assertNotEqual(m.canonical_bytes(bad), m.canonical_bytes(lock))

    def test_corrupted_parent_binding_detected(self):  # V49
        plan, policy, sl, lock = closed()
        chunk = next(o for o in lock['occurrences'] if o['track'] == 'chunk-8k')
        chunk['parent_object_id'] = '0' * 64
        self.has(l1(plan, policy, sl, lock)[0], 'differ from the source lock')

    def test_chunk_tail_and_misaligned_offsets(self):  # V37
        u = 4096
        spans, tail = m.chunk_spans(2 * u + 3, u)
        self.assertEqual((spans, tail), ([(0, u), (u, u)], 3))
        plan, policy, sl, lock = closed()
        path = 'lib/m1.c'  # 8195 bytes: exactly offsets 0 and u in chunk-4k, one chunk-8k
        offsets = lambda lk, tr: sorted(o['provenance']['offset'] for o in lk['occurrences']
                                        if o['track'] == tr and o['source_id'] == 'fa-1' and o['provenance']['member_path'] == path)
        self.assertEqual(offsets(lock, 'chunk-4k'), [0, u])
        self.assertEqual(offsets(lock, 'chunk-8k'), [0])
        self.assertEqual(l1(plan, policy, sl, lock)[0], [])
        template = next(o for o in lock['occurrences'] if o['track'] == 'chunk-4k' and o['source_id'] == 'fa-1'
                        and o['provenance']['member_path'] == path)
        for offset in (2 * u, 100):  # the short tail and a misaligned span
            bad = copy.deepcopy(lock)
            extra = copy.deepcopy(template)
            extra['provenance']['offset'] = offset
            extra['occurrence_id'] = m.occurrence_id(extra['source_id'], extra['provenance'])
            bad['occurrences'].append(extra)
            bad['occurrences'].sort(key=lambda o: o['occurrence_id'])
            bad['materialized_bytes'] += extra['bytes']
            self.has(l1(plan, policy, sl, bad)[0], 'position not derived from the source lock')
        w = tm.World()  # corpus validator: misaligned offset
        w.find(f'{w.dev[0]}-1', 'lib/a.c', 'chunk-4k', 4096)['provenance']['offset'] = 100
        w.reid(w.find(f'{w.dev[0]}-1', 'lib/a.c', 'chunk-4k', 100)), w.seal()
        self.has(w.corpus_errors(), 'chunk span invalid')

    def test_rank_ties_resolved_by_secondary_identity(self):  # V52
        fx = Fx().std('a', 'b')
        for i in range(4):
            fx.add('a1', f'd{i}.c', f'sf{i}'), fx.add('b2', f'g{i}.c', f'G{i}')
        for i in range(3):
            fx.add('a2', f'p{i}.c', f'T{i}')
        tie = 'f' * 64
        real_rank, real_hc = m.rank, cv.hc
        w, p = fx.world(), P(caps={**CAPS, 'same_family_decoy': 2})
        outcomes = []
        for permutation in (w, {k: list(reversed(v)) for k, v in w.items()}):
            with unittest.mock.patch.object(m, 'rank', lambda purpose, seed, *parts: tie), \
                    unittest.mock.patch.object(cv, 'hc', lambda v: tie if type(v) is list and v and v[0] in
                                               ('candidate', 'target', 'target-group') else real_hc(v)):
                outcomes.append(self.both(permutation, p))
        self.assertEqual(outcomes[0], outcomes[1])
        res = outcomes[0]
        self.assertEqual(res['selection']['schedule']['group_order'], [['a', 'chunk-4k', ''], ['b', 'chunk-4k', '']])  # group tie -> g
        a_targets = [t['target'] for t in res['selection']['schedule']['traversal'] if t['group'][0] == 'a']
        self.assertEqual(a_targets, sorted(a_targets))  # target tie -> occurrence ID
        q = query(res, a_targets[0])
        self.assertEqual([b['object_id'] for b in q['bases'] if b['category'] == 'same_family_decoy'],
                         sorted(obj(f'sf{i}') for i in range(4))[:2])  # candidate tie -> object ID
        self.assertEqual(real_rank, m.rank)


def ref_targets(ref):
    return {q['target'] for q in ref['queries']}


# =============================================================================================================
# Coverage reconciliation (construction-spec section 8, research spec 17.2)
# =============================================================================================================

class Coverage(Base):
    def test_cells_and_outcomes_reconcile(self):  # V41, V14, V15 (diagnostics), P16
        for w, p in worlds()[:12]:
            res = self.both(w, p)
            cov = c.coverage(w, p, res)
            t = res['selection']['targets']
            cells = cov['cells']
            near = [q for q in res['queries'] if q['status'] == 'near_duplicate']
            idq = [q for q in res['queries'] if q['status'] == 'identity_only']
            total = lambda key: sum(r[key] for r in cells)
            self.assertEqual(total('targets_all'), t['all'])
            self.assertEqual(total('identity_all') + total('near_opportunity_all'), t['all'])
            self.assertEqual((total('identity_all'), total('near_opportunity_all')), (t['identity'], t['near_opportunity']))
            self.assertEqual((total('selected_near'), total('visited_identity')), (len(near), len(idq)))
            self.assertEqual(total('unvisited'), t['all'] - len(res['queries']))
            self.assertEqual(total('planned_pairs'), res['planned_pairs_per_codec'])
            self.assertEqual(total('occurrences'), len(w['occurrences']))
            self.assertEqual(total('selected_near_empty_pool'), sum(q['candidate_count'] == 0 for q in near))
            pp = cov['pair_plan']
            self.assertEqual((sum(pp['by_track'].values()), sum(pp['by_component'].values()), sum(pp['by_lane'].values())),
                             (pp['total'],) * 3)
            self.assertEqual(sum(cov['target_exclusions']['primary'].values()) + t['all'], len(w['occurrences']))
            self.assertEqual(cov['rates']['identity_all'], [t['identity'], t['all']])
            self.assertEqual(cov['rates']['identity_visited'], [len(idq), len(res['queries'])])
            self.assertEqual(cov['rates']['empty_pool_selected_near'], [sum(q['candidate_count'] == 0 for q in near), len(near)])
            rows = res['selection']['near_queries']
            self.assertEqual([r['target'] for r in rows], [q['target'] for q in near])
            for row, q in zip(rows, near):  # exclusive attribution covers all of U
                a = row['accounting']
                self.assertEqual(sum(a['outcomes'].values()), len(w['occurrences']))
                self.assertEqual(a['eligible_aliases'], sum(a['outcomes'][k] for k in
                                                            ('exact_target_class', 'category_truncation', 'selected_class')))
                self.assertEqual(a['exact_duplicates'], 0)  # near: D_t is empty
                self.assertEqual(a['full_pool_classes'], sum(e['pool_size'] for e in row['categories'].values()))
                self.assertEqual([x['object_id'] for x in row['witnesses']], [b['object_id'] for b in q['bases']])

    def test_zero_rows_are_kept(self):  # V17, V21 (zero denominators retained)
        fx = Fx().std('a')
        fx.add('a1', 'x.c', 'X'), fx.add('a2', 'p0.c', 'T')
        w = fx.world()
        res = self.both(w)
        layout = {'components': {'a': ('a', 'development'), 'z': ('z', 'evaluation')},
                  'lanes': {'chunk-4k': 'modeled', 'file': 'historical'}, 'strata': ['f064k', 'f001m']}
        cells = c.coverage(w, P(), res, layout)['cells']
        keys = {(r['family_id'], r['track'], r['stratum']) for r in cells}
        self.assertIn(('z', 'chunk-4k', None), keys)
        self.assertIn(('a', 'file', 'f001m'), keys)
        self.assertEqual(next(r for r in cells if (r['family_id'], r['track']) == ('z', 'chunk-4k'))['targets_all'], 0)


# =============================================================================================================
# Properties P01-P18 over deterministic random worlds
# =============================================================================================================

class Properties(Base):
    def test_world_generator_is_not_vacuous(self):  # P16 (guard)
        seen = set()
        for w, p in worlds():
            res = c.construct(w, p)
            cov = c.coverage(w, p, res)
            seen |= {'identity'} if res['selection']['targets']['identity'] else set()
            for q in res['queries']:
                if q['status'] == 'near_duplicate':
                    seen |= {'near'} | ({'empty'} if not q['bases'] else set()) | {k for k in CATS if
                                                                                       any(b['category'] == k for b in q['bases'])}
            for r in res['selection']['near_queries']:
                for k, e in r['categories'].items():
                    seen |= ({'trunc'} if e['truncation'] else set()) | ({'short'} if e['shortage'] else set())
            seen |= {'cross'} if cov['universe']['cross_split_classes'] else set()
            seen |= {'unknown'} if cov['target_exclusions']['flags'].get('unknown_time') else set()
            seen |= {'quota'} if res['selection']['schedule']['stop_reason'] == 'near_quota' else set()
            seen |= {'excl'} if w['exclusions'] else set()
        self.assertEqual(seen, {'identity', 'near', 'empty', 'trunc', 'short', 'cross', 'unknown', 'quota', 'excl', *CATS})

    def test_input_permutation(self):  # P01
        for i, (w, p) in enumerate(worlds()):
            res = c.construct(w, p)
            for k in range(2):
                perm = shuffled(w, random.Random(i * 7 + k))
                with self.subTest(world=i):
                    self.assertEqual(c.construct(perm, p), res)
                    self.assertEqual(cv.derive(perm, p)['queries'], res['queries'])
                    if any(q['status'] == 'near_duplicate' for q in res['queries']):
                        self.assertEqual(c.make_lock(BIND, c.construct(perm, p), p), c.make_lock(BIND, res, p))

    def test_alias_permutation(self):  # P02
        for i, (w, p) in enumerate(worlds()):
            by = {}
            for o in w['occurrences']:
                by.setdefault(o['object_id'], []).append(o)
            flat = [o for group in by.values() for o in reversed(group)]  # reorder inside every class
            with self.subTest(world=i):
                self.assertEqual(c.construct({**w, 'occurrences': flat}, p), c.construct(w, p))
                dup = copy.deepcopy(w)
                dup['occurrences'].append(copy.deepcopy(dup['occurrences'][0]))  # a repeated record is invalid
                self.refused(dup, p, 'duplicate ID')

    def test_base_ineligible_alias(self):  # P03
        for i, (w, p) in enumerate(worlds()):
            rng = random.Random(i)
            res = c.construct(w, p)
            splits = {}
            for o in w['occurrences']:
                splits.setdefault(o['object_id'], set()).add(o['split'])
            fam_split = {o['family_id']: o['split'] for o in w['occurrences']}
            fam = rng.choice(sorted(fam_split))
            same = [x for x, s in splits.items() if s == {fam_split[fam]}] + [obj('brand-new')]
            for flavor in ('wrong_track', 'future', 'unknown_time', 'excluded'):
                w2 = copy.deepcopy(w)
                content = rng.choice(same)
                if flavor == 'wrong_track':
                    sid, rec, track = f'{fam}1', None, 'chunk-64k'
                else:
                    sid, track = f'z-{flavor}', 'chunk-4k'
                    add_source(w2, sid, fam, {'future': [10 ** 6] * 2, 'unknown_time': None, 'excluded': [0, 0]}[flavor])
                rec = mk(sid, fam, 'zz-new.c', 'x', track, 0, fam_split[fam])
                rec['object_id'] = content
                w2['occurrences'].append(rec)
                if flavor == 'excluded':
                    w2['exclusions'].append(excl('occurrence', rec['occurrence_id']))
                with self.subTest(world=i, flavor=flavor):
                    got = c.construct(w2, p)
                    # T_all and X_U unchanged -> identical selection; only per-stage U accounting sees the alias
                    self.assertEqual(without_accounting(got), without_accounting(res))
                    for r in got['selection']['near_queries']:
                        self.assertEqual(r['accounting']['universe_occurrences'], len(w2['occurrences']))
                    self.assertEqual(cv.derive(w2, p)['queries'], res['queries'])

    def pick(self, w, p, i, need_alias=True):
        """A near target (chunk/file) with a selected base having an ordinal-1 eligible alias."""
        res = c.construct(w, p)
        src = sources_of(w)
        rng = random.Random(i)
        options = []
        for t, q in near_targets(res, w):
            if t['track'] not in ('chunk-4k', 'file'):
                continue
            for b in q['bases']:
                for o in w['occurrences']:
                    if o['object_id'] == b['object_id'] and elig(w, o, t) and src[o['source_id']]['ordinal'] == 1:
                        options.append((t, q, b, o))
        return (res, *rng.choice(options)) if options else (res, None, None, None, None)

    def test_eligible_alias_stable_category(self):  # P04
        done = 0
        for i, (w, p) in enumerate(worlds(False)):
            p = {**p, 'max_targets': 1000}
            res, t, q, b, alias = self.pick(w, p, i)
            if t is None:
                continue
            w2 = copy.deepcopy(w)
            new = mk(alias['source_id'], alias['family_id'], 'zz-new.c', 'x', alias['track'], 0, alias['split'])
            new['object_id'] = b['object_id']
            w2['occurrences'].append(new)
            res2 = c.construct(w2, p)
            q2 = query(res2, t)
            with self.subTest(world=i):
                self.assertEqual(cats(q2), cats(q))
                for b1, b2 in zip(q['bases'], q2['bases']):
                    want = min(b1['representative'], new['occurrence_id']) if b1['object_id'] == b['object_id'] \
                        else b1['representative']
                    self.assertEqual(b2['representative'], want)
                self.assertEqual(cv.derive(w2, p)['queries'], res2['queries'])
            done += 1
        self.assertGreater(done, 5)

    def test_query_isolation(self):  # P05
        for i, (w, p) in enumerate(worlds()):
            full = c.construct(w, {**p, 'max_targets': 1000})
            for quota in (1, 2, 3):
                part = c.construct(w, {**p, 'max_targets': quota})
                with self.subTest(world=i, quota=quota):
                    for q in part['queries']:
                        self.assertEqual(q, query(full, q['target']))
                    for r in part['selection']['near_queries']:
                        self.assertEqual(r, next(x for x in full['selection']['near_queries'] if x['target'] == r['target']))

    def test_scorer_and_encoder_isolation(self):  # P06
        for i, (w, p) in enumerate(worlds()[:6]):
            sealed = c.construct(w, p)
            for where in ('occurrences', 'sources'):
                bad = copy.deepcopy(w)
                bad[where][0]['patch_cost'] = 1
                with self.subTest(world=i, where=where), self.assertRaises(c.CandidateError):
                    c.construct(bad, p)
            self.assertEqual(c.construct(w, p), sealed)  # scores/codec runs after seal cannot flow back
            with self.assertRaises(c.CandidateError):
                c.construct(w, {**p, 'codecs': ['zstd']})

    def test_category_locality(self):  # P07
        done = 0
        for i, (w, p) in enumerate(worlds(False)):
            p = {**p, 'max_targets': 1000}
            res = c.construct(w, p)
            src, rng = sources_of(w), random.Random(i)
            for t, q in near_targets(res, w)[:4]:
                if t['track'] not in ('chunk-4k', 'file'):
                    continue
                flavor = rng.choice(('same_path_historical', 'same_family_decoy', 'foreign_family_decoy'))
                path = t['provenance']['member_path'] if flavor == 'same_path_historical' else 'zz-new.c'
                offset = t['provenance']['offset'] or 0
                taken = {(o['source_id'], o['track'], o['provenance']['member_path'], o['provenance']['offset'])
                         for o in w['occurrences']}
                sites = [s for s in src.values() if s['ordinal'] == 1 and s['availability_interval_utc_seconds']
                         and (s['family_id'] == t['family_id']) == (flavor != 'foreign_family_decoy')
                         and s['availability_interval_utc_seconds'][1] < src[t['source_id']]['availability_interval_utc_seconds'][0]
                         and (s['source_id'], t['track'], path, t['provenance']['offset']) not in taken
                         and next(o['split'] for o in w['occurrences'] if o['family_id'] == s['family_id']) == t['split']]
                if not sites:
                    continue
                site = rng.choice(sites)
                new = mk(site['source_id'], site['family_id'], path, 'brand-new-class', t['track'], offset, t['split'])
                w2 = {**w, 'occurrences': w['occurrences'] + [new]}
                res2 = c.construct(w2, p)
                e1, e2 = evid(res, t), evid(res2, t)
                big = {**p, 'caps': {x: 10 ** 6 for x in CATS}}
                pool = next(r for r in c.construct(w2, big)['selection']['near_queries'] if r['target'] == t['occurrence_id'])
                want = sorted(ckey(t['occurrence_id'], x, p['seed']) for x in pool['categories'][flavor]['selected_object_ids'])[:p['caps'][flavor]]
                with self.subTest(world=i, target=t['occurrence_id'][:8], flavor=flavor):
                    for k in CATS:
                        if k != flavor:
                            self.assertEqual(e2[k], e1[k])
                    self.assertEqual(e2[flavor]['pool_size'], e1[flavor]['pool_size'] + 1)
                    self.assertEqual(e2[flavor]['selected_object_ids'], sorted(x for _, x in want))
                    self.assertIn(new['object_id'], pool['categories'][flavor]['selected_object_ids'])
                    self.assertEqual(cv.derive(w2, p)['selection']['near_queries'], res2['selection']['near_queries'])
                done += 1
        self.assertGreater(done, 10)

    def test_prefix_cap_relation(self):  # P08
        for i, (w, p) in enumerate(worlds()):
            p = {**p, 'max_targets': 1000}
            base = c.construct(w, p)
            for k in CATS:
                more = c.construct(w, {**p, 'caps': {**p['caps'], k: p['caps'][k] + 1}})
                with self.subTest(world=i, category=k):
                    for r1, r2 in zip(base['selection']['near_queries'], more['selection']['near_queries']):
                        for k2 in CATS:
                            s1, s2 = set(r1['categories'][k2]['selected_object_ids']), set(r2['categories'][k2]['selected_object_ids'])
                            if k2 == k:
                                self.assertTrue(s1 <= s2 and len(s2 - s1) <= 1)
                                self.assertEqual(len(s2 - s1), 1 if r1['categories'][k]['truncation'] else 0)
                            else:
                                self.assertEqual(s1, s2)

    def test_order_direction(self):  # P09
        for i, (w, p) in enumerate(worlds()):
            res = c.construct(w, p)
            big = c.construct(w, {**p, 'caps': {x: 10 ** 6 for x in CATS}})
            for r in res['selection']['near_queries']:
                full = next(x for x in big['selection']['near_queries'] if x['target'] == r['target'])['categories']
                for k in CATS:
                    pool = sorted(ckey(r['target'], x, p['seed']) for x in full[k]['selected_object_ids'])
                    with self.subTest(world=i, category=k):
                        self.assertEqual(r['categories'][k]['selected_object_ids'],
                                         sorted(x for _, x in pool[:p['caps'][k]]))  # if key(x)<key(y), y in => x in

    def test_identity_masking(self):  # P10
        done = 0
        for i, (w, p) in enumerate(worlds(False)):
            p = {**p, 'max_targets': 1000}
            res = c.construct(w, p)
            src, rng = sources_of(w), random.Random(i)
            for t, q in near_targets(res, w)[:3]:
                if t['track'] not in ('chunk-4k', 'file'):
                    continue
                sites = [s for s in src.values() if s['ordinal'] == 1 and s['availability_interval_utc_seconds']
                         and s['availability_interval_utc_seconds'][1] < src[t['source_id']]['availability_interval_utc_seconds'][0]
                         and next(o['split'] for o in w['occurrences'] if o['family_id'] == s['family_id']) == t['split']]
                if not sites:
                    continue
                site = rng.choice(sites)
                new = mk(site['source_id'], site['family_id'], 'zz-dup.c', 'x', t['track'], 0, t['split'])
                new['object_id'] = t['object_id']
                w2 = {**w, 'occurrences': w['occurrences'] + [new]}
                res2 = c.construct(w2, p)
                with self.subTest(world=i, target=t['occurrence_id'][:8]):
                    q2 = query(res2, t)
                    self.assertEqual((q2['status'], q2['duplicate_of'], q2['candidate_count']),
                                     ('identity_only', new['occurrence_id'], 0))
                    self.assertEqual(cv.derive(w2, p)['queries'], res2['queries'])
                future = copy.deepcopy(w)
                add_source(future, 'z-future', t['family_id'], [10 ** 6] * 2)
                fut = mk('z-future', t['family_id'], 'zz-dup.c', 'x', t['track'], 0, t['split'])
                fut['object_id'] = t['object_id']
                future['occurrences'].append(fut)
                with self.subTest(world=i, future=True):
                    self.assertEqual(query(c.construct(future, p), t), q)  # a future equal class never masks
                done += 1
        self.assertGreater(done, 8)

    def test_representative_robustness(self):  # P11
        done = 0
        for i, (w, p) in enumerate(worlds(False)):
            p = {**p, 'max_targets': 1000}
            res = c.construct(w, p)
            for t, q in near_targets(res, w)[:3]:
                if not q['bases']:
                    continue
                b = q['bases'][0]
                w2 = copy.deepcopy(w)
                add_source(w2, 'z-future', t['family_id'], [10 ** 6] * 2)
                small = pick_path('z-future', lambda x: x < b['representative'], t['track'], 0)
                low = mk('z-future', t['family_id'], small, 'x', t['track'], 0, t['split'])
                low['object_id'] = b['object_id']
                w2['occurrences'].append(low)
                with self.subTest(world=i, ineligible_smaller=True):
                    self.assertEqual(query(c.construct(w2, p), t), q)
                aliases = [o for o in w['occurrences'] if o['object_id'] == b['object_id'] and elig(w, o, t)
                           and o['occurrence_id'] != b['representative']]
                if aliases:
                    w3 = {**w, 'occurrences': [o for o in w['occurrences'] if o is not aliases[0]]}
                    q3 = query(c.construct(w3, p), t) if any(x['target'] == t['occurrence_id'] for x in
                                                            c.construct(w3, p)['queries']) else None
                    if q3 and cats(q3) == cats(q):  # stable category -> identical record
                        with self.subTest(world=i, removed_nonrep=True):
                            self.assertEqual(q3, q)
                done += 1
        self.assertGreater(done, 8)

    def test_time_zones(self):  # P12
        rng = random.Random(12)
        for _ in range(40):
            base = 1700000000 + rng.randint(0, 10 ** 7)
            utc = dt.datetime.fromtimestamp(base, dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            zone = dt.timezone(dt.timedelta(hours=rng.randint(-12, 14)))
            shifted = dt.datetime.fromtimestamp(base, zone).isoformat()
            ivs = [c._interval({'time': {'value': v}}) for v in (utc, shifted)]
            self.assertEqual(ivs[0], ivs[1])
            self.assertEqual(ivs[0], cv.interval({'value': shifted}))
            self.assertEqual(cv.interval({'value': utc}), [base, base])
        self.assertEqual(cv.interval({'value': '2024-01-02'}), list(m.availability({'value': '2024-01-02'})))
        w, p = worlds()[3]  # equivalent renderings of every point time give the same outcome
        res = c.construct(w, p)
        w2, zone = copy.deepcopy(w), dt.timezone(dt.timedelta(hours=5))
        for s in w2['sources']:
            iv = s['availability_interval_utc_seconds']
            if iv and iv[0] == iv[1]:
                s['availability_interval_utc_seconds'] = c._interval(
                    {'time': {'value': dt.datetime.fromtimestamp(iv[0], zone).isoformat()}})
        self.assertEqual(c.construct(w2, p), res)

    def test_unit_boundary(self):  # P13
        for u in (4096, 8192):
            for k in range(4):
                counts = {r: len(m.chunk_spans(k * u + r, u)[0]) for r in (0, 1, 3, u - 1)}
                self.assertEqual(set(counts.values()), {k})
        a, b = l1(*closed((65536, 2 * 4096 + 3)))[1], l1(*closed((65536, 2 * 4096 + 4000)))[1]
        self.assertEqual((a['missing'], a['extra'], b['missing'], b['extra']), (0, 0, 0, 0))
        self.assertEqual(a['expected_positions'], b['expected_positions'])  # r grows, no new full chunk
        e = l1(*closed((65536, 3 * 4096)))[1]
        self.assertGreater(e['expected_positions'], a['expected_positions'])  # crossing the boundary adds one

    def test_deterministic_failure(self):  # P14
        for i, (w, p) in enumerate(worlds()[:10]):
            bad = {'dup': copy.deepcopy(w), 'size': copy.deepcopy(w), 'key': copy.deepcopy(w)}
            bad['dup']['occurrences'].append(copy.deepcopy(bad['dup']['occurrences'][0]))
            o = next(o for o in bad['size']['occurrences'])
            twin = next((x for x in bad['size']['occurrences'] if x['object_id'] == o['object_id']
                         and x is not o), None) or mk(o['source_id'], o['family_id'], 'zz.c', 'x', o['track'], 0, o['split'])
            twin = copy.deepcopy(twin)
            twin['object_id'], twin['bytes'] = o['object_id'], o['bytes'] + 1
            twin['provenance']['member_path'] = 'zz-new.c'
            twin['occurrence_id'] = m.occurrence_id(twin['source_id'], twin['provenance'])
            bad['size']['occurrences'].append(twin)
            bad['key']['occurrences'][0]['bogus'] = 1
            for name, bw in bad.items():
                diag = set()
                for k in range(4):
                    with self.assertRaises(c.CandidateError) as cm:
                        c.construct(shuffled(bw, random.Random(k)) if name != 'key' else bw, p)
                    diag.add(frozenset(str(cm.exception).split('; ')))
                with self.subTest(world=i, case=name):  # same rejection and same distinct diagnostics for every order
                    self.assertEqual(len(diag), 1)

    def test_binding_sensitivity(self):  # P15
        w, p = next((w, p) for w, p in worlds() if any(q['status'] == 'near_duplicate' for q in c.construct(w, p)['queries']))
        res = c.construct(w, p)
        base = c.make_lock(BIND, res, p)
        for key in c.BINDING_KEYS:
            changed = {**BIND, key: ('0' if BIND[key][0] != '0' else '1') + BIND[key][1:]}
            with self.subTest(binding=key):
                self.assertNotEqual(c.make_lock(changed, res, p), base)
                self.assertEqual(m.loads_strict(c.make_lock(changed, res, p))['queries'], m.loads_strict(base)['queries'])
        moved = 0
        for w, p in worlds():
            res = c.construct(w, p)
            if not any(q['status'] == 'near_duplicate' for q in res['queries']):
                continue
            for q in ({**p, 'seed': p['seed'] + 1}, {**p, 'caps': {**p['caps'], 'same_family_decoy': p['caps']['same_family_decoy'] + 1}}):
                other = c.construct(w, q)
                if other['queries'] != res['queries']:
                    moved += 1
                    self.assertNotEqual(c.make_lock(BIND, other, q), c.make_lock(BIND, res, p))
        self.assertGreater(moved, 10)

    def test_two_independent_derivations(self):  # P16
        for i, (w, p) in enumerate(worlds()):
            with self.subTest(world=i):
                got, ref = c.construct(w, p), cv.derive(w, p)
                self.assertEqual(got['queries'], ref['queries'])
                self.assertEqual(got['planned_pairs_per_codec'], ref['planned_pairs_per_codec'])
                self.assertEqual(got['selection'], ref['selection'])
                self.assertEqual(m.canonical_bytes(got['queries']), m.canonical_bytes(ref['queries']))
                if any(q['status'] == 'near_duplicate' for q in ref['queries']):
                    lock = lock_of(got, p)
                    self.assertEqual(cv.compare(ref, lock, got['selection']), [])
                    self.assertEqual(m.canonical_bytes({'planned_pairs_per_codec': ref['planned_pairs_per_codec'],
                                                        'queries': ref['queries'], 'schema': c.SCHEMA, **BIND}),
                                     c.make_lock(BIND, got, p))

    def test_no_codec_dimension(self):  # P17
        sealed = 0
        for i, (w, p) in enumerate(worlds()):
            res = c.construct(w, p)
            if not any(q['status'] == 'near_duplicate' for q in res['queries']):
                continue
            lock = lock_of(res, p)
            sealed += 1
            with self.subTest(world=i):
                self.assertEqual(set(lock), c.LOCK_KEYS)
                self.assertEqual(lock['planned_pairs_per_codec'],
                                 sum(q['candidate_count'] for q in lock['queries'] if q['status'] == 'near_duplicate'))
                self.assertEqual([k for k in lock if 'codec' in k], ['planned_pairs_per_codec'])
                self.assertLessEqual(lock['planned_pairs_per_codec'], p['pairs_max'])
        self.assertGreater(sealed, 20)

    def test_corruption_fails_closed(self):  # P18, V43, V49
        plan, policy, sl, lock = closed()
        self.assertEqual(l1(plan, policy, sl, lock)[0], [])
        rng = random.Random(18)
        for k in range(6):  # any missing expected position
            bad = copy.deepcopy(lock)
            victim = rng.choice(bad['occurrences'])
            bad['occurrences'].remove(victim)
            bad['materialized_bytes'] -= victim['bytes']
            with self.subTest(missing=k):
                self.has(l1(plan, policy, sl, bad)[0], 'missing expected position')
        bad = copy.deepcopy(lock)  # a parent binding swapped to another valid object
        chunks = [o for o in bad['occurrences'] if o['track'] == 'chunk-16k']
        chunks[0]['parent_object_id'] = chunks[-1]['parent_object_id']
        self.has(l1(plan, policy, sl, bad)[0], 'differ from the source lock')
        bad = copy.deepcopy(lock)  # an unknown manual exclusion that is not the raw cross-split set
        bad['exclusions'].append(excl('object', '0' * 64, 'cross_split_content'))
        self.has(l1(plan, policy, sl, bad)[0], 'object exclusions differ')
        docs, sha = synth_docs()  # and at admission: an exclusion of an unknown occurrence/source
        docs['corpus_lock']['exclusions'].append(excl('occurrence', 'f' * 64))
        with self.assertRaises(c.CandidateError):
            c.admit_documents(docs, sha)
        docs, sha = synth_docs()
        docs['corpus_lock']['exclusions'].append(excl('source', 'nope-1'))
        with self.assertRaises(c.CandidateError):
            c.admit_documents(docs, sha)


# =============================================================================================================

class Matrix(unittest.TestCase):
    def test_matrix_complete(self):  # meta
        text = Path(__file__).read_text(encoding='utf-8')
        marked = [line for line in text.splitlines() if re.match(r'\s+def test_\w+\(self\):\s+#', line)]
        seen = set(re.findall(r'\b([VP]\d\d)\b', ' '.join(marked)))
        want = {f'V{i:02d}' for i in range(1, 57)} | {f'P{i:02d}' for i in range(1, 19)}
        self.assertEqual(sorted(want - seen), [])


class ReviewRegressions(Base):
    """PR #21 review: durable witnesses/accounting, closed v2 boundary, fail-closed evidence rows, verifier I33."""

    def test_category_witness_is_recorded_independently_of_representative(self):  # A04
        case = golden('class-category-independent-of-representative')
        res = self.both(case['input'])
        row = next(r for r in res['selection']['near_queries'] if r['target'] == case['roles']['target'])
        w, = row['witnesses']
        self.assertEqual((w['category'], w['category_witness'], w['representative']),
                         ('same_path_historical', case['roles']['same_path_witness'],
                          case['roles']['foreign_representative']))
        self.assertEqual(w['eligible_aliases'], 3)

    def test_witness_and_accounting_tampering_detected(self):
        w, p = valid_world()
        res = c.construct(w, p)
        lock = lock_of(res, p)
        for part, mutate in (('witnesses', lambda r: r['witnesses'][0].update(category_witness='0' * 64)),
                             ('accounting', lambda r: r['accounting']['outcomes'].update(temporal=99))):
            sel = copy.deepcopy(res['selection'])
            mutate(sel['near_queries'][0])
            with self.subTest(part):
                self.has(cv.compare(cv.derive(w, p), lock, sel), f'{part} evidence differs')

    def test_verifier_evidence_rows_fail_closed(self):
        w, p = valid_world()
        res = c.construct(w, p)
        lock, ref = lock_of(res, p), cv.derive(w, p)
        self.assertEqual(cv.compare(ref, lock, res['selection']), [])
        rows = res['selection']['near_queries']
        for name, value in (('duplicate row', rows + [copy.deepcopy(rows[-1])]),
                            ('open row', [{**rows[0], 'score': 1}] + rows[1:]),
                            ('missing row', rows[:-1]), ('not a list', {r['target']: r for r in rows})):
            with self.subTest(name):
                self.assertTrue(cv.compare(ref, lock, {**res['selection'], 'near_queries': value}))
        dup = {**lock, 'queries': lock['queries'] + [copy.deepcopy(lock['queries'][-1])]}
        self.has(cv.compare(ref, dup, res['selection']), 'repeat a target')

    def test_make_lock_enforces_v2_ids_status_and_types(self):
        w, p = valid_world()
        res = c.construct(w, p)
        q0 = next(i for i, q in enumerate(res['queries']) if q['bases'])
        for name, mutate in (('short target', lambda r: r['queries'][q0].update(target='ab')),
                             ('uppercase object', lambda r: r['queries'][q0]['bases'][0].update(
                                 object_id=r['queries'][q0]['bases'][0]['object_id'].upper())),
                             ('int representative', lambda r: r['queries'][q0]['bases'][0].update(representative=1)),
                             ('unknown status', lambda r: r['queries'][q0].update(status='near')),
                             ('bool pairs', lambda r: r.update(planned_pairs_per_codec=True)),
                             ('str pairs', lambda r: r.update(planned_pairs_per_codec='1'))):
            bad = copy.deepcopy(res)
            mutate(bad)
            with self.subTest(name), self.assertRaises(c.CandidateError):
                c.make_lock(BIND, bad, p)

    def test_verifier_independently_refuses_license_composite(self):  # I33, V50
        fx = Fx().std('a')
        fx.add('a1', 'bad.c', 'B'), fx.add('a1', None, 'TAR', 'tar'), fx.add('a2', 'p0.c', 'T')
        for exclusion in (excl('member', 'a1:bad.c'), excl('occurrence', fx.occs[0]['occurrence_id'])):
            fx.exclusions = [exclusion]
            with self.subTest(exclusion['kind']), self.assertRaisesRegex(ValueError, 'license-excluded member'):
                cv.derive(fx.world(), P())
        fx.exclusions = [excl('source', 'a1')]
        self.both(fx.world())


if __name__ == '__main__':
    unittest.main()
