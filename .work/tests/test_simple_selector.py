"""delsk.simple-selector.v1 (tools/simple_selector.py): descriptor, order, and the committed in-sample evaluation."""
import json
from pathlib import Path
import random
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import baselines as bl
import simple_selector as ss

DEV_EVAL = Path(__file__).resolve().parents[1] / 'selector' / 'dev-eval.json'
VECTORS = Path(__file__).resolve().parents[1] / 'selector' / 'vectors.txt'


def obj(oid, size, path=None, line=None, version=0, offset=None):
    return {'object_id': oid, 'bytes': size, 'path': path, 'line': line, 'version_rank': version, 'offset': offset}


class Descriptor(unittest.TestCase):
    def test_is_64_bytes_and_nested_in_the_slice_a_sketch(self):
        data = random.Random(3).randbytes(50000)
        d = ss.descriptor(data)
        self.assertEqual(len(d) * 8, 64)
        self.assertEqual(d, bl.sketch(data)[:8])

    def test_short_and_empty_objects(self):
        self.assertEqual(ss.descriptor(b''), [])
        self.assertEqual(len(ss.descriptor(b'abc')), 1)

    def test_resemblance_bounds(self):
        a = ss.descriptor(random.Random(4).randbytes(20000))
        b = ss.descriptor(random.Random(5).randbytes(20000))
        self.assertEqual(ss.resemblance(a, a), 1.0)
        self.assertLess(ss.resemblance(a, b), 0.5)


class Order(unittest.TestCase):
    def setUp(self):
        rng = random.Random(9)
        self.data = {n: rng.randbytes(30000) for n in 'tabcd'}
        self.data['near'] = self.data['t'][:29000] + b'x' * 1000
        self.desc = {k: ss.descriptor(v) for k, v in self.data.items()}
        self.t = obj('t', 30000, 'src/a.c', '1.x', 5)
        self.bases = [obj('a', 30000, 'src/a.c', '1.x', 3), obj('b', 30000, 'src/a.c', '1.x', 4),
                      obj('c', 30000, 'src/a.c', '2.x', 6), obj('d', 30000, 'src/b.c', '1.x', 4),
                      obj('near', 30000, None, None, 0)]

    def test_metadata_prefers_same_line_latest_earlier_version(self):
        self.assertEqual(ss.metadata_order(self.t, self.bases), ['b', 'a'])

    def test_k1_and_k2(self):
        self.assertEqual(ss.select(self.t, self.bases, self.desc, 1), ['b'])
        self.assertEqual(ss.select(self.t, self.bases, self.desc, 2), ['b', 'near'])

    def test_without_path_only_content(self):
        t = dict(self.t, path=None)
        self.assertEqual(ss.select(t, self.bases, self.desc, 1), ['near'])

    def test_full_order_is_a_permutation(self):
        order = ss.select(self.t, self.bases, self.desc, 99)
        self.assertEqual(sorted(order), sorted(b['object_id'] for b in self.bases))

    def test_interleave(self):
        self.assertEqual(ss.interleave(['a', 'b'], ['b', 'c', 'a', 'd']), ['a', 'b', 'c', 'd'])
        self.assertEqual(ss.interleave([], ['x', 'y']), ['x', 'y'])


class Vectors(unittest.TestCase):
    def test_committed_parity_vectors_are_reproduced(self):
        self.assertEqual(VECTORS.read_text(), '\n'.join(ss.vector_lines()) + '\n')

    def test_vectors_discriminate(self):
        lines = ss.vector_lines()
        descs = {l.split()[-1] for l in lines if l.startswith('O ')}
        self.assertGreater(len(descs), 10)  # related objects must not share one descriptor


class Abstention(unittest.TestCase):
    def row(self, pop, useful, has_meta, shared, s=1000, o=100, n=10):
        return {'population': pop, 'useful_delta': useful, 'has_meta': has_meta, 'best_shared': shared,
                'standalone_bytes': s, 'oracle_bytes': o if useful else s, 'candidates': n}

    def test_levels_and_preregistered_choice(self):
        rows = [self.row('p', True, True, 0) for _ in range(150)]          # metadata: never abstained
        rows += [self.row('p', True, False, 8) for _ in range(50)]          # strong content signal
        rows += [self.row('p', False, False, 0) for _ in range(40)]         # nothing to gain
        rows += [self.row('p', True, False, 1, s=1000, o=999)]              # weak and nearly useless
        rows += [self.row('adv', None, False, 0)]                           # adversarial: no oracle
        r = ss.abstention(rows)
        by = {l['level']: l for l in r['levels']}
        self.assertEqual(by[0]['saved_calls'], 0)
        self.assertEqual(by[1]['saved_calls'], 80)                           # 40 targets x min(2, 10)
        self.assertEqual(by[2]['useful_abstained'], 1)
        self.assertLessEqual(by[2]['lost_savings_share'], 0.005)
        self.assertEqual(r['chosen_level'], 2)       # FN 1/201 <= 1 %, 82 calls; levels 3-4 tie, smaller wins
        self.assertEqual(by[1]['populations']['adv']['abstained'], 1)
        rows += [self.row('p', True, False, 1, s=1000, o=999) for _ in range(2)]   # FN 3/203 > 1 %
        self.assertEqual(ss.abstention(rows)['chosen_level'], 1)

    def test_no_level_qualifies_keeps_always_encode(self):
        rows = [self.row('p', True, False, 0) for _ in range(10)]
        self.assertEqual(ss.abstention(rows)['chosen_level'], 0)

    def test_feature_row(self):
        d = {'t': [1, 2, 3, 4, 5, 6, 7, 8], 'a': [1, 2, 3, 4, 9, 10, 11, 12], 'b': [20, 21]}
        t = obj('t', 100, 'x', '1', 2)
        bases = [obj('a', 100, 'y', '1', 1), obj('b', 50, None, None, 0)]
        r = ss._feature_row('p', 't', t, bases, d, None)
        self.assertEqual((r['has_meta'], r['best_shared'], r['per_base']['a']), (False, 4, [4, 8]))


@unittest.skipUnless(DEV_EVAL.is_file() and ss.X0_RUN.is_dir(), 'retained inputs missing')
class InSample(unittest.TestCase):
    def test_committed_evaluation_is_reproduced(self):
        self.assertEqual(ss.evaluate(), json.loads(DEV_EVAL.read_text()))

    def test_k2_is_never_worse_than_k1(self):
        by = {(s['population'], s['k']): s['savings_capture'] for s in json.loads(DEV_EVAL.read_text())['summary']}
        for (pop, k), sc in by.items():
            if k == 2:
                self.assertGreaterEqual(sc, by[(pop, 1)])


if __name__ == '__main__':
    unittest.main()
