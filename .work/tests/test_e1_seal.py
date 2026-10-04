"""Offline integrity of the E1 candidate seal (no downloads, no scorer, no encoder).

The committed lock must equal a fresh builder recomputation from the frozen
inputs, pass the independent verifier, and match both retained Actions runs.
"""
import copy
import hashlib
from pathlib import Path
import re
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


def schema_errors(value, schema, root, where='$'):
    """Test-only evaluator of the JSON Schema 2020-12 keywords used by candidate-lock-v2.schema.json."""
    if '$ref' in schema:
        target = root
        for part in schema['$ref'].lstrip('#/').split('/'):
            target = target[part]
        return schema_errors(value, target, root, where)
    errors = []
    kinds = {'object': dict, 'array': list, 'string': str, 'integer': int, 'null': type(None)}
    if 'type' in schema and type(value) is not kinds[schema['type']]:  # bool is not integer
        return [f'{where}: not {schema["type"]}']
    if 'const' in schema and (type(value), value) != (type(schema['const']), schema['const']):
        errors.append(f'{where}: not const')
    if 'enum' in schema and value not in schema['enum']:
        errors.append(f'{where}: not in enum')
    if isinstance(value, str):
        if not schema.get('minLength', 0) <= len(value) <= schema.get('maxLength', len(value))                 or ('pattern' in schema and not re.search(schema['pattern'], value)):
            errors.append(f'{where}: string shape')
    if type(value) is int and not schema.get('minimum', value) <= value <= schema.get('maximum', value):
        errors.append(f'{where}: out of range')
    if isinstance(value, dict):
        props = schema.get('properties', {})
        errors += [f'{where}: missing {k}' for k in schema.get('required', []) if k not in value]
        if schema.get('additionalProperties') is False:
            errors += [f'{where}: extra {k}' for k in value if k not in props]
        for k, sub in props.items():
            if k in value:
                errors += schema_errors(value[k], sub, root, f'{where}.{k}')
    if isinstance(value, list):
        if not schema.get('minItems', 0) <= len(value) <= schema.get('maxItems', len(value)):
            errors.append(f'{where}: item count')
        if schema.get('uniqueItems') and len({m.digest(v) for v in value}) != len(value):
            errors.append(f'{where}: items not unique')
        for i, item in enumerate(value):
            if 'items' in schema:
                errors += schema_errors(item, schema['items'], root, f'{where}[{i}]')
        if 'contains' in schema:
            n = sum(not schema_errors(item, schema['contains'], root) for item in value)
            if not schema.get('minContains', 1) <= n <= schema.get('maxContains', n):
                errors.append(f'{where}: contains count {n}')
    for sub in schema.get('allOf', []):
        errors += schema_errors(value, sub, root, where)
    if 'oneOf' in schema and sum(not schema_errors(value, sub, root) for sub in schema['oneOf']) != 1:
        errors.append(f'{where}: not exactly one of oneOf')
    if 'if' in schema:
        branch = 'then' if not schema_errors(value, schema['if'], root) else 'else'
        if branch in schema:
            errors += schema_errors(value, schema[branch], root, where)
    return errors


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


    def test_lock_satisfies_closed_v2_schema(self):
        schema = load(WORK / 'corpus' / 'e0' / 'candidate-lock-v2.schema.json')
        lock = load(E1 / 'candidate-lock.json')
        self.assertEqual(schema_errors(lock, schema, schema), [])
        near = next(i for i, q in enumerate(lock['queries']) if q['status'] == 'near_duplicate' and q['bases'])
        ident = next(i for i, q in enumerate(lock['queries']) if q['status'] == 'identity_only')
        for name, mutate in (('extra key', lambda d: d.update(score=1)),
                             ('bool count', lambda d: d['queries'][near].update(candidate_count=True)),
                             ('identity without duplicate', lambda d: d['queries'][ident].update(duplicate_of=None)),
                             ('three same-path bases', lambda d: d['queries'][near].update(bases=[
                                 {**d['queries'][near]['bases'][0], 'category': 'same_path_historical',
                                  'object_id': f'{i:064x}'} for i in range(3)])),
                             ('no near query', lambda d: d.update(queries=[d['queries'][ident]]))):
            bad = copy.deepcopy(lock)
            mutate(bad)
            with self.subTest(name):
                self.assertTrue(schema_errors(bad, schema, schema))

if __name__ == '__main__':
    unittest.main()
