"""DELSK-003A: integrity of the frozen provenance/G1 contract delsk.oracle-contract.v2.

Offline, synthetic and payload-free: no registry, no provider call, no corpus bytes. Checks that freeze-v2 pins the
v2 files and the unchanged v1 measurement layer, that the v2 schemas are closed and fail closed, that the
science_identity reference vectors follow the frozen construction (SI01 through git_source on a real commit), and that
the R01-R24 / XC01-XC05 vector document is internally consistent: hash chains, digests, identities, records and code classes.
It does not implement or run G1 v2; activation needs an independent implementation that reproduces the records.
"""
import copy
import hashlib
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = HERE.parent
ROOT = WORK.parent
ORACLE = WORK / 'oracle'
sys.path[:0] = [str(WORK / 'tools')]
import oracle_attempts as oa
import oracle_eval as ev

FREEZE_V1_PATH = ORACLE / 'freeze.json'
FREEZE = ev.parse_doc((ORACLE / 'freeze-v2.json').read_bytes())
FREEZE_V1 = ev.parse_doc(FREEZE_V1_PATH.read_bytes())
SCHEMAS = ev.parse_doc((ORACLE / 'schemas-v2.json').read_bytes())
VECTORS = ev.parse_doc((ORACLE / 'registry-vectors.json').read_bytes())
D = SCHEMAS['$defs']
V2 = 'delsk.oracle-contract.v2'
END = '(?![\\s\\S])'
SUPPORTED = {'$ref', 'type', 'const', 'enum', 'pattern', 'minimum', 'required', 'properties', 'additionalProperties',
             'items', 'minItems', 'uniqueItems', 'oneOf', 'if', 'then', 'else', 'description'}
CODES = {
    'NO_VERDICT': {'REGISTRY_INVALID', 'REGISTRY_DUPLICATE', 'REGISTRY_STALE', 'MAIN_STALE', 'REGISTRY_ROLLBACK',
                   'EVIDENCE_ROOT_INVALID'},
    'INVALID': {'RUN_INVALID', 'REPEAT_MISMATCH', 'BINDING_MISMATCH', 'UNBOUND_MEASUREMENT', 'DUPLICATE_EXECUTION',
                'SERIES_INVALID', 'SERIES_REPEAT_MISMATCH', 'SERIES_TRANSITION_MISMATCH', 'SERIES_FORK',
                'SERIES_REENTRY'},
    'NOT_PASSED': {'RUN_INCOMPLETE', 'RUN_COMPLETE_WITH_FAILURES', 'CONFORMANCE_OR_BUNDLE', 'REPEAT_MISSING',
                   'RESULT_MISSING', 'SERIES_FAILURE', 'SERIES_TRANSITION_MISSING', 'SERIES_SUPERSEDED',
                   'KAT_NOT_VERIFIED', 'V2_NOT_ACTIVE'},
}
CASES = [c for v in VECTORS['vectors'] for c in v['cases']]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def errors(value, name):
    return ev.schema_errors(value, D[name], SCHEMAS)


def without(record, key):
    return {k: v for k, v in record.items() if k != key}


def science(mi):
    return {**without(mi, 'measured_source_sha'), 'schema': 'delsk.oracle.science-identity.v1'}


def environment(case):
    env = dict(VECTORS['environment'])
    env.update(case['environment_override'] or {})
    return env


class Freeze(unittest.TestCase):
    def test_record_layers(self):
        self.assertEqual(FREEZE['schema'], 'delsk.oracle-contract.freeze.v2')
        self.assertEqual(FREEZE['contract_id'], V2)
        self.assertEqual(FREEZE['layering'], {'measurement_contract': 'delsk.oracle-contract.v1',
                                              'g1_provenance_contract': V2})
        self.assertEqual((FREEZE['natural_measurements'], FREEZE['g1'], FREEZE['implementation']),
                         ('NOT_RUN', 'NOT_RUN', 'NOT_ACTIVE'))

    def test_measurement_layer_is_v1_unchanged(self):
        layer = FREEZE['measurement_layer']
        self.assertEqual(layer['contract_id'], 'delsk.oracle-contract.v1')
        self.assertEqual(layer['freeze_path'], '.work/oracle/freeze.json')
        self.assertEqual(FREEZE['measurement_layer_sha256'], sha(FREEZE_V1_PATH))
        self.assertEqual(FREEZE['measurement_layer_sha256'],
                         'c56fc053b103cecd38446b3791db104a12b9fafabacdfc6b71f6f23c0bf7f729')
        self.assertEqual(layer['files'], FREEZE_V1['files'])
        self.assertEqual(layer['bindings'], FREEZE_V1['bindings'])
        for name, digest in FREEZE_V1['files'].items():
            with self.subTest(name):
                self.assertEqual(sha(ROOT / name), digest)

    def test_provenance_layer_files(self):
        files = FREEZE['provenance_layer']['files']
        self.assertEqual(set(files), {'.work/oracle/contract-v2.md', '.work/oracle/schemas-v2.json',
                                      '.work/oracle/registry-vectors.json', '.work/tests/test_oracle_contract_v2.py'})
        for name, digest in files.items():
            with self.subTest(name):
                self.assertEqual(sha(ROOT / name), digest)
        self.assertEqual(FREEZE['provenance_layer_sha256'], ev.hc(files))
        self.assertNotIn('.work/oracle/attempt-v2-proposal.md', files)

    def test_contract_states_layering_and_status(self):
        text = (ORACLE / 'contract-v2.md').read_text(encoding='utf-8')
        for needle in (V2, 'measurement_contract   = delsk.oracle-contract.v1',
                       'g1_provenance_contract = delsk.oracle-contract.v2', 'DELSK-003A PROTOCOL V2 FROZEN',
                       'V2 IMPLEMENTATION NOT_ACTIVE', FREEZE['measurement_layer_sha256'], 'MISSING ⇒ NOT_PASSED'):
            self.assertIn(needle, text)
        for n in range(1, 25):
            self.assertIn(f'R{n:02d}', text)
        self.assertIn('XC01–XC05', text)
        for n in range(1, 13):
            self.assertIn(f'PM{n:02d}', text)

    def test_no_v2_evidence_or_registry_exists(self):
        self.assertFalse((WORK / 'results' / 'DELSK-003-ORACLE-V2').exists())
        self.assertFalse((ORACLE / 'series-transition.json').exists())


class Schemas(unittest.TestCase):
    def walk(self, node, where='#'):
        if isinstance(node, dict):
            yield where, node
            for k, v in node.items():
                yield from self.walk(v, f'{where}/{k}')
        elif isinstance(node, list):
            for i, v in enumerate(node):
                yield from self.walk(v, f'{where}[{i}]')

    def test_closed_and_supported(self):
        for where, node in self.walk(D):
            if where == '#' or where.endswith('/properties'):
                continue  # name -> schema maps, not schemas
            with self.subTest(where):
                self.assertLessEqual(set(node), SUPPORTED)
            if node.get('type') == 'object' and 'properties' in node:
                with self.subTest(closed=where):
                    self.assertIs(node.get('additionalProperties'), False)
                    self.assertLessEqual(set(node['required']), set(node['properties']))
            if 'pattern' in node:
                with self.subTest(pattern=where):
                    self.assertTrue(node['pattern'].startswith('^') and node['pattern'].endswith(END))
        for name in ('registry_genesis', 'registry_entry', 'series_transition', 'registry_head', 'science_identity',
                     'attempt_binding', 'provider_observation', 'bundle_projection', 'g1_record'):
            self.assertIn(name, D)

    def test_fail_closed(self):
        entry = CASES[0]['registry']['entries'][0]
        record = CASES[0]['expect'][0]['record']
        transition = next(e['transition'] for c in CASES for e in c['registry']['entries'] if e['transition'])
        for label, name, value in (
                ('unknown field', 'registry_entry', {**entry, 'note': 'x'}),
                ('missing field', 'registry_entry', without(entry, 'transition')),
                ('bool as integer', 'registry_entry', {**entry, 'run_attempt': True}),
                ('zero sequence', 'registry_entry', {**entry, 'sequence': 0}),
                ('uppercase hash', 'registry_entry', {**entry, 'entry_sha256': entry['entry_sha256'].upper()}),
                ('hash + LF', 'registry_entry', {**entry, 'entry_sha256': entry['entry_sha256'] + '\n'}),
                ('short commit', 'registry_entry', {**entry, 'measured_source_sha': entry['measured_source_sha'][:39]}),
                ('other workflow', 'registry_entry', {**entry, 'workflow_path': '.github/workflows/foundation.yml'}),
                ('other contract', 'registry_entry', {**entry, 'g1_contract': 'delsk.oracle-contract.v1'}),
                ('phase smoke', 'registry_entry', {**entry, 'phase': 'smoke'}),
                ('bad reason', 'series_transition', {**transition, 'reason': 'OTHER'}),
                ('pull request as URL', 'series_transition',
                 {**transition, 'change_review': {**transition['change_review'], 'pull_request': '101'}}),
                ('test PASS', 'g1_record', {**record, 'verdict': 'PASS'}),
                ('production TEST_ONLY_PASS', 'g1_record',
                 {**record, 'authority': {'repository': 'definitely-stable/Shift-lab',
                                          'registry_remote': 'https://github.com/definitely-stable/Shift-lab.git',
                                          'registry_ref': 'refs/heads/delsk/registry',
                                          'provider_api': 'https://api.github.com',
                                          'results_root': '.work/results/DELSK-003-ORACLE-V2/'},
                  'evaluator': {'g1_code_sha256': '0' * 64, 'evaluator_source_sha': '0' * 40}}),
                ('unknown code', 'g1_record', {**record, 'blockers': ['DISPATCH_HISTORY_UNVERIFIED']}),
                ('record without main snapshot', 'g1_record', without(record, 'main_head_sha'))):
            with self.subTest(label):
                self.assertTrue(errors(value, name))
        self.assertEqual(errors(record, 'g1_record'), [])
        with self.assertRaises(ev.EvalError):
            ev.parse_doc(b'{"sequence": 1.0}\n')

    def test_code_vocabulary(self):
        self.assertEqual(set(D['code']['enum']), set().union(*CODES.values()))
        self.assertEqual(sum(map(len, CODES.values())), len(D['code']['enum']))


class ScienceIdentity(unittest.TestCase):
    def test_construction(self):
        v1_mi = ev.schemas()['$defs']['run']['properties']['measurement_identity']
        ids = [v['id'] for v in VECTORS['science_identity_vectors']]
        self.assertEqual(ids, ['SI01', 'SI02', 'SI03', 'SI04', 'SI05'])
        for v in VECTORS['science_identity_vectors']:
            with self.subTest(v['id']):
                self.assertEqual(ev.schema_errors(v['measurement_identity'], v1_mi), [])
                self.assertEqual(ev.hc(v['measurement_identity']), v['measurement_identity_sha256'])
                self.assertEqual(science(v['measurement_identity']), v['science_identity'])
                self.assertEqual(errors(v['science_identity'], 'science_identity'), [])
                self.assertEqual(ev.hc(v['science_identity']), v['science_identity_sha256'])
                self.assertNotEqual(v['science_identity_sha256'], v['measurement_identity_sha256'])
        by = {v['id']: v['science_identity_sha256'] for v in VECTORS['science_identity_vectors']}
        self.assertEqual(by['SI02'], by['SI03'])  # measured_source_sha is not part of science
        self.assertEqual(len({by['SI02'], by['SI04'], by['SI05']}), 3)  # oracle code and phase are

    def test_real_identity_through_git_source(self):
        v = VECTORS['science_identity_vectors'][0]
        source = oa.git_source(v['git_source_commit'], 'refs/heads/main')
        self.assertEqual(source['measurement_identity_sha256'], v['measurement_identity_sha256'])
        self.assertEqual(v['measurement_identity_sha256'],
                         '07416d16d4e6dc972e6d43ecb79394458804d8afbe77266696e251b2cfd85b02')
        text = (ORACLE / 'contract-v2.md').read_text(encoding='utf-8')
        self.assertIn(v['science_identity_sha256'], text)


class Vectors(unittest.TestCase):
    def test_document(self):
        self.assertEqual(errors(VECTORS, 'registry_vectors'), [])
        self.assertEqual([v['id'] for v in VECTORS['vectors']], [f'R{n:02d}' for n in range(1, 25)])
        ids = [c['id'] for c in CASES]
        self.assertEqual(len(ids), len(set(ids)))
        for v in VECTORS['vectors']:
            for c in v['cases']:
                self.assertTrue(c['id'] == v['id'] or c['id'].startswith(v['id'] + '.'))
        env = VECTORS['environment']
        v1_mi = ev.schemas()['$defs']['run']['properties']['measurement_identity']
        for s in env['sources']:
            self.assertEqual(ev.schema_errors(s['measurement_identity'], v1_mi), [])
            self.assertEqual(s['measurement_identity']['measured_source_sha'], s['sha'])

    def test_mutants(self):
        self.assertEqual([m['id'] for m in VECTORS['mutants']], [f'PM{n:02d}' for n in range(1, 13)])
        ids = {c['id'] for c in CASES}
        for m in VECTORS['mutants']:
            self.assertLessEqual(set(m['killed_by']), ids, m['id'])

    def chain_faults(self, case):
        genesis, entries = case['registry']['genesis'], case['registry']['entries']
        faults, prev = set(), ev.hc(genesis)
        seqs = [e['sequence'] for e in entries]
        for n, e in enumerate(entries, 1):
            if e['previous_entry_sha256'] != prev:
                faults.add('CHAIN_BREAK')
            if e['entry_sha256'] != ev.hc(without(e, 'entry_sha256')):
                faults.add('ENTRY_DIGEST')
            if e['sequence'] != n:
                faults.add('SEQUENCE_REPEAT' if seqs.count(e['sequence']) > 1 else 'SEQUENCE_GAP')
            prev = e['entry_sha256']
        return faults

    def test_registries(self):
        for case in CASES:
            with self.subTest(case['id']):
                env = environment(case)
                sources = {s['sha']: s['measurement_identity'] for s in env['sources']}
                faults = self.chain_faults(case)
                if case['registry_fault'] is None:
                    self.assertEqual(faults, set())
                else:
                    self.assertIn(case['registry_fault'], faults)
                for e in case['registry']['entries']:
                    mi = sources[e['measured_source_sha']]
                    self.assertEqual(e['workflow_sha'], e['measured_source_sha'])
                    self.assertEqual(ev.hc(mi), e['measurement_identity_sha256'])
                    self.assertEqual(ev.hc(science(mi)), e['science_identity_sha256'])
                    self.assertEqual(mi['phase'], e['phase'])
                    if e['transition'] is not None:
                        t = e['transition']
                        self.assertEqual(ev.hc(without(t, 'transition_sha256')), t['transition_sha256'])
                for b in case['evidence']['bindings']:
                    self.assertEqual(ev.hc(without(b, 'binding_sha256')), b['binding_sha256'])
                observed = {(o['run_id'], o['run_attempt']) for o in case['provider']}
                self.assertEqual(len(observed), len(case['provider']))

    def test_expected_records(self):
        mapping = {'SCIENTIFIC_PASS': 'TEST_ONLY_PASS'}
        for case in CASES:
            entries = case['registry']['entries']
            for x in case['expect']:
                r = x['record']
                with self.subTest(case['id'], identity=x['measurement_identity_sha256'][:12]):
                    self.assertEqual(errors(r, 'g1_record'), [])
                    self.assertEqual(ev.hc(without(r, 'record_sha256')), r['record_sha256'])
                    self.assertEqual(r['measurement_identity_sha256'], x['measurement_identity_sha256'])
                    self.assertEqual(r['verdict'], mapping.get(x['core_verdict'], x['core_verdict']))
                    self.assertIsNone(r['authority'])
                    self.assertIsNone(r['evaluator'])
                    self.assertIsNone(r['external_checkpoint'])
                    self.assertEqual(r['main_head_sha'], environment(case)['main_head'])
                    self.assertEqual(r['blockers'], sorted(set(r['blockers'])))
                    verdict = x['core_verdict']
                    if verdict in CODES:
                        self.assertTrue(r['blockers'])
                        self.assertLessEqual(set(r['blockers']), CODES[verdict])
                    else:
                        self.assertEqual(r['blockers'], [])
                    if verdict == 'NO_VERDICT':
                        self.assertEqual(len(r['blockers']), 1)
                        self.assertEqual((r['attempts'], r['unbound_attempts'], r['series'], r['transitions']),
                                         ([], [], [], []))
                        self.assertIsNone(r['science_identity_sha256'])
                        if r['blockers'] == ['REGISTRY_INVALID']:
                            self.assertIsNone(r['registry_head'])
                        continue
                    self.assertEqual(r['genesis_sha256'], ev.hc(case['registry']['genesis']))
                    self.assertEqual(r['registry_head'], {'sequence': len(entries),
                                                          'entry_sha256': entries[-1]['entry_sha256']})
                    self.assertEqual([(a['sequence'], a['entry_sha256'], a['run_id'], a['run_attempt'],
                                       a['measurement_identity_sha256'], a['science_identity_sha256'])
                                      for a in r['attempts']],
                                     [(e['sequence'], e['entry_sha256'], e['run_id'], e['run_attempt'],
                                       e['measurement_identity_sha256'], e['science_identity_sha256'])
                                      for e in entries])
                    for a in r['attempts']:
                        self.assertEqual(a['outcome'] is not None, a['class'] == 'BUNDLE')
                        self.assertEqual(a['conformance'] is not None, a['class'] == 'BUNDLE')
                        if a['violations']:
                            self.assertEqual(a['class'], 'MISSING')
                    self.assertEqual([t['sequence'] for t in r['transitions']],
                                     [e['sequence'] for e in entries if e['transition'] is not None])
                    if verdict == 'NOT_RUN':
                        self.assertNotIn(x['measurement_identity_sha256'],
                                         {e['measurement_identity_sha256'] for e in entries})
                    else:
                        mine = [e for e in entries if e['measurement_identity_sha256'] ==
                                x['measurement_identity_sha256']]
                        if mine:
                            self.assertEqual(r['science_identity_sha256'], mine[0]['science_identity_sha256'])

    def test_vectors_are_not_vacuous(self):
        verdicts = {x['core_verdict'] for c in CASES for x in c['expect']}
        self.assertEqual(verdicts, {'SCIENTIFIC_PASS', 'NOT_PASSED', 'INVALID', 'NOT_RUN', 'NO_VERDICT'})
        blockers = {b for c in CASES for x in c['expect'] for b in x['record']['blockers']}
        self.assertLessEqual(CODES['NO_VERDICT'], blockers)
        self.assertLessEqual({'BINDING_MISMATCH', 'UNBOUND_MEASUREMENT', 'DUPLICATE_EXECUTION', 'SERIES_INVALID',
                              'SERIES_REPEAT_MISMATCH', 'SERIES_TRANSITION_MISMATCH', 'SERIES_FORK',
                              'SERIES_REENTRY', 'RESULT_MISSING', 'SERIES_FAILURE', 'SERIES_TRANSITION_MISSING',
                              'SERIES_SUPERSEDED', 'REPEAT_MISSING', 'RUN_INVALID', 'KAT_NOT_VERIFIED'}, blockers)
        classes = {a['class'] for c in CASES for x in c['expect'] for a in x['record']['attempts']}
        self.assertEqual(classes, {'PRE', 'BUNDLE', 'MISSING'})
        statuses = {t['status'] for c in CASES for x in c['expect'] for t in x['record']['transitions']}
        self.assertLessEqual({'VALID', 'MISMATCH', 'FORK'}, statuses)
        self.assertEqual({x['record']['verdict'] for c in CASES for x in c['expect']} & {'PASS'}, set())

    def test_external_checkpoint_vectors(self):  # contract 13.2: record head must be a prefix of the checkpoint
        xcs = VECTORS['external_checkpoint_vectors']
        self.assertEqual([x['id'] for x in xcs], [f'XC{n:02d}' for n in range(1, 6)])
        for x in xcs:
            with self.subTest(x['id']):
                hist, head, rec = x['checkpoint_history'], x['checkpoint']['head'], x['record_head']
                self.assertEqual(head, {'sequence': len(hist),
                                        'entry_sha256': hist[-1] if hist else x['genesis_sha256']})
                n = rec['sequence']
                prefix = n <= len(hist) and (hist[n - 1] if n else x['genesis_sha256']) == rec['entry_sha256']
                self.assertEqual(x['expected'], 'ADMISSIBLE' if prefix else 'INADMISSIBLE')
        self.assertEqual({x['expected'] for x in xcs}, {'ADMISSIBLE', 'INADMISSIBLE'})

    def test_kat_and_snapshot_vectors(self):
        by = {c['id']: c for c in CASES}
        env = VECTORS['environment']
        self.assertEqual(env['evaluator_source_sha'], env['main_head'])
        for cid in ('R23.a', 'R23.b', 'R23.c'):
            self.assertEqual(by[cid]['expect'][0]['record']['blockers'], ['KAT_NOT_VERIFIED'])
        self.assertIn(env['main_head'], env['kat_green'])
        self.assertNotIn(env['main_head'], by['R23.a']['environment_override']['kat_green'])
        self.assertNotEqual(by['R24']['main_remote_head'], env['main_head'])
        self.assertEqual(by['R24']['expect'][0]['record']['blockers'], ['MAIN_STALE'])
        others = [c for c in CASES if c['id'] != 'R24']
        self.assertTrue(all(c['main_remote_head'] == environment(c)['main_head'] for c in others))

    def test_runner_and_api_expectations(self):
        by = {c['id']: c for c in CASES}
        self.assertEqual(by['R12.a']['runner']['bind'], 'REGISTRY_UNBOUND')
        self.assertFalse(by['R12.a']['runner']['crosses_boundary'])
        self.assertEqual(by['R21.a']['runner']['register'], 'TRANSITION_REQUIRED')
        api = by['R17']['api']
        self.assertEqual(api['production_parameters'], ['measurement_identity_sha256'])
        self.assertNotIn('measurement_identity_sha256', api['forbidden_production_parameters'])


if __name__ == '__main__':
    unittest.main()
