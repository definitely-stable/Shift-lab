"""Offline integrity of the E1 candidate seal (no downloads, no scorer, no encoder).

The committed lock must equal a fresh builder recomputation from the frozen
inputs, pass the independent verifier, and match both retained Actions runs.
"""
import hashlib
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / '.work'
E1 = WORK / 'corpus' / 'e1'
sys.path.insert(0, str(WORK / 'tools'))
import candidate_verify
import candidates
import manifests as m


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return m.loads_strict(path.read_bytes())


class E1SealTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.seal = load(E1 / 'seal.json')
        cls.inputs = {name: (ROOT / path).read_bytes() for name, (path, _) in candidates.INPUTS.items()}
        world, cls.params, cls.bindings, layout = candidates.admit(cls.inputs)
        cls.result = candidates.construct(world, cls.params)
        cls.lock = candidates.make_lock(cls.bindings, cls.result, cls.params)
        cls.coverage = m.canonical_bytes(candidates.coverage(world, cls.params, cls.result, layout))

    def test_status_and_pinned_files(self):
        self.assertEqual(self.seal['schema'], 'delsk.e1.candidate-seal.v1')
        self.assertEqual(self.seal['status'], 'SEALED')
        for name, digest in self.seal['files'].items():
            self.assertEqual(sha(ROOT / name), digest, name)
        self.assertEqual(self.seal['candidate_lock_sha256'], sha(E1 / 'candidate-lock.json'))

    def test_bindings_are_the_e0_bindings(self):
        e0 = load(WORK / 'corpus' / 'e0' / 'freeze.json')
        lock = load(E1 / 'candidate-lock.json')
        self.assertEqual(self.bindings, e0['candidate_lock_bindings'])
        self.assertEqual({k: lock[k] for k in candidates.BINDING_KEYS}, e0['candidate_lock_bindings'])
        self.assertEqual(set(lock), candidates.LOCK_KEYS)

    def test_builder_recomputes_committed_bytes(self):
        self.assertEqual(self.lock, (E1 / 'candidate-lock.json').read_bytes())
        self.assertEqual(m.canonical_bytes(self.result['selection']), (E1 / 'selection.json').read_bytes())
        self.assertEqual(self.coverage, (E1 / 'coverage.json').read_bytes())

    def test_independent_verifier_accepts(self):
        report = candidate_verify.verify(self.inputs, (ROOT / candidate_verify.E0_FREEZE[0]).read_bytes(),
                                         (E1 / 'candidate-lock.json').read_bytes(), load(E1 / 'selection.json'))
        self.assertEqual((report['status'], report['errors']), ('ok', []))
        self.assertEqual(report['checks']['source_to_u']['missing'] + report['checks']['source_to_u']['extra'], 0)

    def test_two_actions_runs_agree_under_different_orders(self):
        runs = [load(E1 / 'runs' / name) for name in self.seal['runs']]
        self.assertEqual(len(runs), 2)
        for run in runs:
            self.assertEqual((run['status'], run['verification']), ('ok', 'ok'))
            self.assertEqual(run['bindings'], self.bindings)
            for key, name in (('candidate_lock_sha256', 'candidate-lock.json'), ('selection_sha256', 'selection.json'),
                              ('coverage_sha256', 'coverage.json')):
                self.assertEqual(run[key], sha(E1 / name), key)
            self.assertEqual(run['code_sha256'], self.seal['code_sha256'])
        self.assertNotEqual(runs[0]['order_key'], runs[1]['order_key'])
        self.assertNotEqual(runs[0]['builder_iteration_order_sha256'], runs[1]['builder_iteration_order_sha256'])
        for name, digest in self.seal['code_sha256'].items():
            self.assertEqual(sha(WORK / 'tools' / name), digest, name)

    def test_lock_accounting(self):
        lock = load(E1 / 'candidate-lock.json')
        near = [q for q in lock['queries'] if q['status'] == 'near_duplicate']
        self.assertEqual(len(near), self.params['max_targets'])
        self.assertEqual(lock['planned_pairs_per_codec'], sum(q['candidate_count'] for q in near))
        self.assertLessEqual(lock['planned_pairs_per_codec'], self.params['pairs_max'])
        self.assertEqual([q['target'] for q in lock['queries']], sorted(q['target'] for q in lock['queries']))
        for q in lock['queries']:
            counts = {k: sum(b['category'] == k for b in q['bases']) for k in candidates.CATEGORIES}
            self.assertTrue(all(counts[k] <= self.params['caps'][k] for k in counts))
            self.assertEqual(q['candidate_list_sha256'], m.digest([b['object_id'] for b in q['bases']]))


if __name__ == '__main__':
    unittest.main()
