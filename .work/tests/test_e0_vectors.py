"""E0 golden vectors: hash consistency plus a slow test-only reference evaluator.

The reference evaluator below is a direct transcription of the adopted E0
predicates (construction-spec.md) over tiny synthetic worlds. It is not the E1
selector and must not be imported by one. Expected values in golden-vectors.json
were prescribed by hand before this evaluator existed; this test checks that the
adopted rules reproduce them exactly.
"""
import collections
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import manifests as m

E0 = ROOT / 'corpus' / 'e0'
SEED = 20261004
CAPS = {'same_path_historical': 2, 'same_family_decoy': 30, 'foreign_family_decoy': 32}
QUERY_KEYS = {'target', 'status', 'duplicate_of', 'bases', 'candidate_count', 'candidate_list_sha256'}
BASE_KEYS = {'object_id', 'representative', 'category'}
LOCK_KEYS = {'schema', 'corpus_lock_sha256', 'selection_policy_sha256', 'construction_spec_sha256',
             'protocol_sha256', 'ancestry_audit_sha256', 'acquisition_freeze_sha256', 'historical_bytes_sha256',
             'planned_pairs_per_codec', 'queries'}


def compact(value):
    """Independent stdlib form of the compact hash encoding (no manifests import)."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def hc(value):
    return hashlib.sha256(compact(value)).hexdigest()


def hf(value):
    return hashlib.sha256(m.canonical_bytes(value)).hexdigest()


def load_vectors():
    return m.loads_strict((E0 / 'golden-vectors.json').read_bytes())


class World:
    """Reference E predicates over one synthetic projection (exclusions are empty)."""

    # Rule knobs exist only so MutantTests can show the vectors reject wrong rules; defaults are the adopted ones.
    pick, strict_time, identity_takes_quota, same_family_precedence = min, True, False, True

    def __init__(self, world):
        self.sources = {s['source_id']: s for s in world['sources']}
        self.occ = world['occurrences']
        splits = collections.defaultdict(set)
        for o in self.occ:
            splits[o['object_id']].add(o['split'])
        self.cross_split = {x for x, s in splits.items() if len(s) > 1}  # X_U on raw U

    def interval(self, o):
        return self.sources[o['source_id']]['availability_interval_utc_seconds']

    def is_target(self, t):
        return t['object_id'] not in self.cross_split and self.sources[t['source_id']]['ordinal'] in (2, 3)

    def eligible(self, b, t):
        return (b['object_id'] not in self.cross_split and b['occurrence_id'] != t['occurrence_id']
                and b['split'] == t['split'] and b['track'] == t['track']
                and b['provenance']['options'] == t['provenance']['options']
                and (self.interval(b)[1] < self.interval(t)[0] if self.strict_time
                     else self.interval(b)[1] <= self.interval(t)[0]))

    def query(self, t):
        pool = collections.defaultdict(list)  # A_t: object -> eligible occurrences
        for b in self.occ:
            if self.eligible(b, t):
                pool[b['object_id']].append(b)
        dup = pool.pop(t['object_id'], None)
        if dup:
            return {'target': t['occurrence_id'], 'status': 'identity_only',
                    'duplicate_of': self.pick(b['occurrence_id'] for b in dup), 'bases': [],
                    'candidate_count': 0, 'candidate_list_sha256': hc([])}
        pos = (t['family_id'], t['provenance']['member_path'], t['provenance']['offset'])
        by_category = collections.defaultdict(list)
        for x, aliases in pool.items():
            if any((b['family_id'], b['provenance']['member_path'], b['provenance']['offset']) == pos
                   for b in aliases):
                k = 'same_path_historical'
            elif self.same_family_precedence and any(b['family_id'] == t['family_id'] for b in aliases):
                k = 'same_family_decoy'
            else:
                k = 'foreign_family_decoy'
            by_category[k].append(x)
        bases = []
        for k, xs in by_category.items():
            xs.sort(key=lambda x: (hc(['candidate', SEED, t['occurrence_id'], x]), x))
            bases += [{'object_id': x, 'category': k,
                       'representative': self.pick(b['occurrence_id'] for b in pool[x])} for x in xs[:CAPS[k]]]
        bases.sort(key=lambda v: v['object_id'])
        ids = [v['object_id'] for v in bases]
        return {'target': t['occurrence_id'], 'status': 'near_duplicate', 'duplicate_of': None,
                'bases': bases, 'candidate_count': len(bases), 'candidate_list_sha256': hc(ids)}

    def schedule(self, quota):
        """A02: identities stay in groups and consume a turn, not near quota."""
        groups = collections.defaultdict(list)
        for t in self.occ:
            if self.is_target(t):
                groups[(t['family_id'], t['track'], t['stratum'] or '')].append(t)
        order = sorted(groups, key=lambda g: (hc(['target-group', SEED, *g]), g))
        for g in order:
            groups[g].sort(key=lambda t: (hc(['target', SEED, t['occurrence_id']]), t['occurrence_id']))
        visited, near = [], 0
        while near < quota and any(groups.values()):
            for g in order:
                if not groups[g] or near >= quota:
                    continue
                q = self.query(groups[g].pop(0))
                visited.append((g, q))
                near += self.identity_takes_quota or q['status'] == 'near_duplicate'
        return visited, [t['occurrence_id'] for g in order for t in groups[g]]


class VectorHashTests(unittest.TestCase):
    def setUp(self):
        self.v = load_vectors()

    def test_file_is_canonical_and_adopted(self):
        self.assertEqual(self.v['schema'], 'delsk.e0.golden-vectors.v1')
        self.assertEqual(self.v['seed'], SEED)

    def test_payload_recipes(self):
        for r in self.v['payload_recipes']:
            data = bytes([r['recipe']['ascii_byte_decimal']]) * r['recipe']['repeat_count']
            self.assertEqual((len(data), hashlib.sha256(data).hexdigest()), (r['byte_length'], r['object_id']))

    def test_compact_and_rank_vectors(self):
        rows = list(self.v['canonical_vectors']['compact_lists'])
        rows.append(self.v['canonical_vectors']['unicode_and_types_compact'])
        rows += self.v['real_candidate_rank_vectors']['vectors']
        for c in self.v['cases']:
            for kind in ('groups', 'targets'):
                rows += c.get('rank_vectors', {}).get(kind, [])
        for r in rows:
            self.assertEqual(compact(r['input']).decode('utf-8'), r['compact_utf8'])
            self.assertEqual(hc(r['input']), r['sha256'])
            self.assertEqual(m.digest(r['input']), r['sha256'])
        rv = self.v['real_candidate_rank_vectors']
        ordered = sorted(rv['vectors'], key=lambda r: (r['sha256'], r['input'][3]))
        self.assertEqual([r['input'][3] for r in ordered], rv['expected_rank_order'])

    def test_rank_order_list_hash_differs_from_sorted_list_hash(self):  # V47
        ids = self.v['real_candidate_rank_vectors']['expected_rank_order']
        self.assertNotEqual(hc(ids), hc(sorted(ids)))

    def test_digest_ties_use_secondary_identity(self):  # V52
        for case in self.v['synthetic_digest_collision_vectors']:
            for keys in (case['keys'], list(reversed(case['keys']))):
                self.assertEqual([k[1] for k in sorted(keys)], case['expected_secondary_order'])

    def test_canonical_file_vectors(self):
        for name, r in self.v['canonical_vectors'].items():
            if 'canonical_utf8' not in r:
                continue
            raw = m.canonical_bytes(r['value'])
            self.assertEqual(raw.decode('utf-8'), r['canonical_utf8'], name)
            self.assertEqual((len(raw), hashlib.sha256(raw).hexdigest()), (r['byte_length'], r['sha256']), name)

    def test_lock_vector_bindings_and_closed_keys(self):
        r = self.v['canonical_vectors']['candidate_lock_file']
        lock, b = r['value'], r['binding_values']
        self.assertEqual(set(lock), LOCK_KEYS)
        for key, name in (('corpus_lock_sha256', 'corpus_projection'), ('protocol_sha256', 'protocol'),
                          ('selection_policy_sha256', 'selection_policy'),
                          ('construction_spec_sha256', 'construction_spec'),
                          ('ancestry_audit_sha256', 'ancestry_audit'),
                          ('acquisition_freeze_sha256', 'acquisition_freeze'),
                          ('historical_bytes_sha256', 'historical_bytes')):
            self.assertEqual(lock[key], hf(b[name]), key)
        schema = m.loads_strict((E0 / 'candidate-lock-v2.schema.json').read_bytes())
        self.assertEqual(set(schema['required']), LOCK_KEYS)
        self.assertEqual(set(schema['$defs']['query']['required']), QUERY_KEYS)
        self.assertEqual(set(schema['$defs']['base']['required']), BASE_KEYS)

    def test_case_inputs(self):
        for c in self.v['cases']:
            world = c['input']
            self.assertEqual(hf(world), c['input_canonical_file_sha256'], c['id'])
            ids = [o['occurrence_id'] for o in world['occurrences']]
            self.assertEqual(ids, sorted(set(ids)), c['id'])
            for o in world['occurrences']:
                self.assertEqual(m.occurrence_id(o['source_id'], o['provenance']), o['occurrence_id'])
                self.assertEqual(hc(['delsk.occurrence.v1', o['source_id'], o['provenance']]), o['occurrence_id'])


class ReferenceEvaluatorTests(unittest.TestCase):
    world = World

    def setUp(self):
        self.cases = {c['id']: c for c in load_vectors()['cases']}

    def queries(self, case):
        w = self.world(case['input'])
        return w, {o['occurrence_id']: w.query(o) for o in w.occ if w.is_target(o)}

    def assert_query_shape(self, q):
        self.assertEqual(set(q), QUERY_KEYS)
        for b in q['bases']:
            self.assertEqual(set(b), BASE_KEYS)

    def test_minimum_eligible_alias(self):  # V01, V23, V39
        c = self.cases['minimum-eligible-alias']
        _, got = self.queries(c)
        for q in c['expected']['queries_for_requested_targets']:
            self.assert_query_shape(q)
            self.assertEqual(got[q['target']], q)
        self.assertNotEqual(c['expected']['identity_duplicate_of'], c['roles']['smaller_future_alias'])

    def test_identity_consumes_group_turn(self):  # V28, V40
        c = self.cases['identity-consumes-group-turn']
        e = c['expected']
        for permute in (False, True):
            world = dict(c['input'])
            if permute:
                world['occurrences'] = list(reversed(world['occurrences']))
            visited, unvisited = self.world(world).schedule(c['fixture_only_near_quota'])
            self.assertEqual([q['target'] for _, q in visited], e['visited_target_ids'])
            self.assertEqual(unvisited, e['unvisited_target_ids'])
            self.assertEqual([list(g) for g, _ in visited], [t['group'] for t in e['traversal']])
            queries = sorted((q for _, q in visited), key=lambda q: q['target'])
            self.assertEqual(queries, e['queries_sorted_by_target'])
            self.assertEqual(sum(q['candidate_count'] for q in queries if q['status'] == 'near_duplicate'),
                             e['planned_pairs_per_codec'])
        self.assertNotEqual(sorted(e['visited_target_ids']), sorted(e['incorrect_prefilter_identity_result']))

    def test_class_category_independent_of_representative(self):  # V23, V38
        c = self.cases['class-category-independent-of-representative']
        _, got = self.queries(c)
        q = c['expected']['query']
        self.assert_query_shape(q)
        self.assertEqual(got[q['target']], q)
        self.assertEqual(q['bases'][0]['representative'], c['roles']['foreign_representative'])



class MutantTests(unittest.TestCase):
    """Each wrong rule makes at least one golden vector fail, so the vectors discriminate."""

    MUTANTS = {'max duplicate/representative': {'pick': max},
               'non-strict time boundary': {'strict_time': False},
               'identity consumes near quota': {'identity_takes_quota': True},
               'no same-family precedence': {'same_family_precedence': False}}

    def test_vectors_reject_mutants(self):
        tests = [n for n in dir(ReferenceEvaluatorTests) if n.startswith('test_')]
        for name, knobs in self.MUTANTS.items():
            mutant = type('Mutant', (World,), {k: (staticmethod(v) if callable(v) else v) for k, v in knobs.items()})
            case = type('Case', (ReferenceEvaluatorTests,), {'world': mutant})
            result = unittest.TestResult()
            unittest.TestSuite(case(n) for n in tests).run(result)
            with self.subTest(mutant=name):
                self.assertEqual(result.errors, [])
                self.assertTrue(result.failures, name + ' passed all golden vectors')


if __name__ == '__main__':
    unittest.main()
