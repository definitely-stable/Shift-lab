"""DELSK-004 Slice A (tools/baselines.py) on synthetic data only: universe, methods, sketches and the evaluator."""
import hashlib
import json
from pathlib import Path
import random
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import baselines as bl


def oid(data):
    return hashlib.sha256(data).hexdigest()


def occ(occurrence_id, data, family, split, source, path=None, offset=None, track='file'):
    return {'occurrence_id': occurrence_id, 'object_id': oid(data), 'bytes': len(data), 'family_id': family,
            'split': split, 'source_id': source, 'track': track,
            'provenance': {'member_path': path, 'offset': offset, 'transform': 'member_v1'}}


class Universe(unittest.TestCase):
    def setUp(self):
        self.blobs = {n: bytes([n]) * (100 + n) for n in range(8)}
        b = self.blobs
        self.corpus = {'occurrences': [
            occ('t1', b[0], 'f', 'development', 'f-3', 'a.c'), occ('b1', b[1], 'f', 'development', 'f-1', 'a.c'),
            occ('b2', b[2], 'f', 'development', 'f-2', 'b.c'),
            occ('te', b[3], 'g', 'evaluation', 'g-3', 'x.c'), occ('be', b[4], 'g', 'evaluation', 'g-1', 'x.c'),
            occ('ti', b[5], 'f', 'calibration', 'f-3', 'c.c'), occ('di', b[5], 'f', 'calibration', 'f-2', 'c.c')]}
        base = lambda o, cat: {'object_id': oid(b[o]), 'representative': f'b{o}', 'category': cat}
        self.candidate = {'queries': [
            {'target': 't1', 'status': 'near_duplicate', 'bases': [base(1, 'same_path_historical'), base(2, 'decoy')]},
            {'target': 'te', 'status': 'near_duplicate',
             'bases': [{'object_id': oid(b[4]), 'representative': 'be', 'category': 'x'}]},
            {'target': 'ti', 'status': 'identity_only', 'bases': []}]}
        self.plan = {'families': [{'releases': [{'release_id': f'{f}-{i}', 'ordinal': i} for i in (1, 2, 3)]}
                                  for f in 'fg']}

    def test_only_evaluated_near_duplicates_without_category(self):
        qs = bl.universe(self.candidate, self.corpus, self.plan)
        self.assertEqual([q['target_occurrence_id'] for q in qs], ['t1'])
        self.assertNotIn('category', json.dumps(qs))
        self.assertEqual([b['ordinal'] for b in qs[0]['bases']], [1, 2])

    def test_metadata_methods_are_permutations_and_deterministic(self):
        q = bl.universe(self.candidate, self.corpus, self.plan)[0]
        for name, fn in bl.METADATA_METHODS.items():
            with self.subTest(name):
                self.assertEqual(sorted(fn(q)), sorted(b['object_id'] for b in q['bases']))
                self.assertEqual(fn(q), fn(q))
        self.assertEqual(bl.rank_previous_version(q)[0], oid(self.blobs[1]))   # same path a.c
        self.assertEqual(bl.rank_size_closest(q)[0], oid(self.blobs[1]))       # 101 B vs 102 B to a 100 B target

    def test_git_name_hash_matches_git_v1(self):
        # pack_name_hash of git (name-hash version 1): hash = (hash >> 2) + (c << 24), whitespace skipped
        h = 0
        for c in b'dir/file.c':
            h = ((h >> 2) + (c << 24)) & 0xffffffff
        self.assertEqual(bl.git_name_hash('dir/file.c'), h)
        self.assertEqual(bl.git_name_hash('a b'), bl.git_name_hash('ab'))


class Sketches(unittest.TestCase):
    def test_nested_and_deterministic(self):
        data = random.Random(1).randbytes(20000)
        full = bl.sketch(data, k=128)
        self.assertEqual(full, sorted(full))
        self.assertEqual(len(full), 128)
        self.assertEqual(bl.sketch(data, k=16), full[:16])
        self.assertEqual(bl.sketch(data, k=128), full)

    def test_estimates(self):
        rng = random.Random(2)
        a = rng.randbytes(50000)
        b = rng.randbytes(50000)
        sa, sb, ss = bl.sketch(a), bl.sketch(b), bl.sketch(a[:25000])
        self.assertEqual(bl.resemblance(sa, sa, 128), 1.0)
        self.assertLess(bl.resemblance(sa, sb, 128), 0.05)
        self.assertGreater(bl.containment(ss, sa, 128), 0.7)   # the half is contained in the whole
        self.assertLess(bl.containment(sa, ss, 128), 0.75)
        self.assertEqual(bl.distinct_estimate(bl.sketch(b'abcdefghij'), 128), 3.0)
        self.assertGreater(bl.distinct_estimate(sa, 128), 20000)

    def test_short_and_empty_objects(self):
        self.assertEqual(len(bl.sketch(b'abc')), 1)
        self.assertEqual(bl.sketch(b''), [])
        self.assertEqual(bl.containment([], [], 8), 0.0)


def oracle_bundle(directory, targets, pairs):
    Path(directory).mkdir(parents=True, exist_ok=True)
    bl.write_jsonl(Path(directory) / 'targets.jsonl', targets)
    bl.write_jsonl(Path(directory) / 'pairs.jsonl', pairs)
    return directory


def target_row(tid, s, deltas, family='f', split='development'):
    finite = [v for v in deltas.values() if v is not None]
    od = min(finite) if finite else None
    return {'schema': 'delsk.oracle.target.v1', 'target_occurrence_id': tid, 'family_id': family, 'track': 'file',
            'split': split, 'query_status': 'near_duplicate', 'standalone_total_bytes': s,
            'oracle_delta_total_bytes': od, 'oracle_total_bytes': min(s, od) if od is not None else s,
            'oracle_tie_bases': sorted(b for b, v in deltas.items() if v is not None and v == od)}


def pair_rows(tid, deltas):
    return [{'schema': 'delsk.oracle.pair.v1', 'target_occurrence_id': tid, 'base_object_id': b,
             'status': 'ok' if v is not None else 'codec_error', 'delta_total_bytes': v} for b, v in deltas.items()]


class Evaluator(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.deltas = {'t1': {'a': 100, 'b': 100, 'c': 900}, 't2': {'d': 5000, 'e': None}}
        self.targets = [target_row('t1', 1000, self.deltas['t1']), target_row('t2', 2000, self.deltas['t2'])]
        self.pairs = pair_rows('t1', self.deltas['t1']) + pair_rows('t2', self.deltas['t2'])
        sealed = [{'schema': 'delsk.oracle.target-sealed.v1', 'target_occurrence_id': 'tx', 'split': 'evaluation'},
                  {'schema': 'delsk.oracle.pair-sealed.v1', 'target_occurrence_id': 'tx', 'base_object_id': 'z'}]
        self.bundle = oracle_bundle(self.tmp, self.targets + sealed[:1], self.pairs + sealed[1:])

    def ranking(self, tid, order, method='m'):
        return {'target_occurrence_id': tid, 'method': method, 'budget_bytes': None, 'ranking': order}

    def rows_for(self, order1, order2):
        rows, summary, _ = bl.evaluate([self.ranking('t1', order1), self.ranking('t2', order2)], self.bundle)
        return {(r['target_occurrence_id'], r['k']): r for r in rows}, {s['k']: s for s in summary}

    def test_protocol_definitions(self):
        rows, summary = self.rows_for(['c', 'b', 'a'], ['e', 'd'])
        r = rows[('t1', 1)]
        self.assertEqual((r['selected_bytes'], r['regret_bytes'], r['strict_hit']), (900, 800, False))
        self.assertEqual(r['normalized_regret'], 8.0)
        self.assertTrue(rows[('t1', 4)]['strict_hit'])                    # tie b counts as a hit
        self.assertEqual(rows[('t2', 1)]['selected_bytes'], 2000)         # codec error: standalone fallback
        self.assertFalse(rows[('t2', 1)]['useful_delta'])                # 5000 >= S: no useful delta
        s1 = summary[1]
        self.assertEqual((s1['finite_delta_targets'], s1['useful_delta_targets']), (2, 1))
        self.assertEqual(s1['strict_recall'], 0.0)
        self.assertEqual(s1['savings_capture'], 100 / 900)               # (1000-900 + 0) / (1000-100 + 0)
        self.assertEqual(summary[4]['savings_capture'], 1.0)
        self.assertEqual(s1['encoder_call_reduction'], 5 / 2)
        self.assertEqual(s1['epsilon_recall']['0.05'], 0.0)
        self.assertEqual(summary[4]['epsilon_recall']['0.01'], 1.0)

    def test_epsilon_floor(self):
        deltas = {'a': 100, 'b': 160}
        bundle = oracle_bundle(Path(self.tmp) / 'eps', [target_row('t', 1000, deltas)], pair_rows('t', deltas))
        rows, _, _ = bl.evaluate([self.ranking('t', ['b', 'a'])], bundle)
        self.assertTrue(next(r for r in rows if r['k'] == 1)['epsilon_hits']['0.01'])   # 160 <= 100 + 64

    def test_savings_capture_undefined_when_nothing_to_save(self):
        deltas = {'a': 5000}
        bundle = oracle_bundle(Path(self.tmp) / 'na', [target_row('t', 1000, deltas)], pair_rows('t', deltas))
        _, summary, _ = bl.evaluate([self.ranking('t', ['a'])], bundle)
        self.assertIsNone(summary[0]['savings_capture'])
        self.assertIsNone(summary[0]['useful_recall'])

    def test_fail_closed(self):
        cases = {
            'not a permutation': ([self.ranking('t1', ['a', 'b']), self.ranking('t2', ['d', 'e'])], self.bundle),
            'duplicate base': ([self.ranking('t1', ['a', 'a', 'b']), self.ranking('t2', ['d', 'e'])], self.bundle),
            'population incomplete': ([self.ranking('t1', ['a', 'b', 'c'])], self.bundle),
            'sealed target': ([self.ranking('tx', ['z'])], self.bundle),
        }
        bad = [dict(t) for t in self.targets]
        bad[0]['oracle_tie_bases'] = ['a']
        cases['tie set'] = ([self.ranking('t1', ['a', 'b', 'c']), self.ranking('t2', ['d', 'e'])],
                            oracle_bundle(Path(self.tmp) / 'bad', bad, self.pairs))
        for name, (rankings, bundle) in cases.items():
            with self.subTest(name):
                with self.assertRaises(bl.BaselineError):
                    bl.evaluate(rankings, bundle)

    def test_bootstrap_and_quantile(self):
        self.assertEqual(bl.quantile([1, 2, 3, 4], 0.5), 2.5)
        self.assertEqual(bl.quantile([10], 0.95), 10)
        self.assertIsNone(bl.quantile([], 0.5))
        rows, _, _ = bl.evaluate([self.ranking('t1', ['a', 'b', 'c']), self.ranking('t2', ['d', 'e'])], self.bundle)
        boot = bl.bootstrap([r for r in rows if r['k'] == 1], draws=50)
        self.assertEqual((boot['lineages'], boot['exploratory']), (1, True))
        self.assertEqual(boot['savings_capture']['ci95'], [1.0, 1.0])

    def test_best_on_calibration(self):
        summary = [{'split': 'calibration', 'k': 8, 'savings_capture': 0.9, 'budget_bytes': 64, 'method': 'm'},
                   {'split': 'calibration', 'k': 8, 'savings_capture': 0.9, 'budget_bytes': None, 'method': 'z'},
                   {'split': 'development', 'k': 8, 'savings_capture': 1.0, 'budget_bytes': None, 'method': 'd'}]
        self.assertEqual(bl.best_on_calibration(summary)['method'], 'z')


class RankStage(unittest.TestCase):
    def test_rank_reads_only_the_universe_and_verifies_bytes(self):
        with tempfile.TemporaryDirectory() as store:
            blobs = [random.Random(n).randbytes(3000) for n in range(3)]
            for data in blobs:
                (Path(store) / oid(data)).write_bytes(data)
            meta = lambda i: {'object_id': oid(blobs[i]), 'bytes': 3000, 'path': None, 'offset': None, 'ordinal': i}
            q = {'target_occurrence_id': 't', 'family_id': 'f', 'track': 'file', 'split': 'development',
                 'target': meta(0), 'bases': [meta(1), meta(2)]}
            rows, costs = bl.rank_all([q], store)
            self.assertEqual(len(rows), len(bl.METADATA_METHODS) + 2 * len(bl.PARAMS['budgets_bytes']))
            self.assertEqual(costs['objects'], 3)
            (Path(store) / oid(blobs[2])).write_bytes(b'tampered')
            with self.assertRaises(bl.BaselineError):
                bl.rank_all([q], store)


if __name__ == '__main__':
    unittest.main()
