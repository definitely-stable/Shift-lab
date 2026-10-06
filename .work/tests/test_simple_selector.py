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
