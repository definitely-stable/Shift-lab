"""DELSK-003A C1-A: G1 v2 engine (oracle_g1_v2.py) against the frozen delsk.oracle-contract.v2, synthetic only.

1. exact reproduction of R01-R24: core verdict and the full test record (hence record_sha256) of every identity;
2. production/test API separation (R17, V2_NOT_ACTIVE);
3. classification (PRE / BUNDLE / MISSING / violations), unbound attempts, series state machine;
4. adversarial paths of the C1-A self-review and deletion monotonicity;
5. runner-level register/bind decisions (R12, R21), KAT v2 gate, evidence root and bundle projection.
No registry, provider, network or natural byte is touched.
"""
import copy
import inspect
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import oracle_v2_vectors as V
from oracle_v2_vectors import BY_ID, CASES, VECTORS
import oracle_attempts as oa
import oracle_eval as ev
import oracle_g1_v2 as g1
import oracle_registry_v2 as reg

A, C, D = ('a77f420c89c111651682e0b015fde143d5119b1f', '085bbd6c728fa0e1ce82af37eb73027436bc34c4',
           '921f3b8c44251a24c9bd63cae943b444c0856cf2')
MAIN = VECTORS['environment']['main_head']
OFF_MAIN = 'ed787d5c809f13f6d8f0a348fa4dec56472500a1'
REF = 'definitely-stable/Shift-lab/.github/workflows/oracle-pilot.yml@refs/heads/main'
PASSING = ('SCIENTIFIC_PASS',)
SOURCES = {s['sha']: s['measurement_identity'] for s in VECTORS['environment']['sources']}
S1, S2, S3 = (ev.hc(reg.science_identity(SOURCES[s])) for s in (A, D, 'f8f6a7c54fd1673dc3a53125c4e6379b85a9930f'))


def run(case):
    """{identity: (core verdict, record)} for every expected identity of a (possibly modified) case."""
    x = V.evaluation(case)
    a = g1.analyze(x)
    return {e['measurement_identity_sha256']: g1.g1_test(e['measurement_identity_sha256'], x, a)
            for e in case['expect']}


def first(case):
    return run(case)[case['expect'][0]['measurement_identity_sha256']]


def key(doc):
    return doc['run_id'], doc['run_attempt']


def drop(case, kind, k):
    """Delete the provider observation / bundle / binding of run key k."""
    if kind == 'provider':
        case['provider'] = [o for o in case['provider'] if key(o) != k]
    else:
        case['evidence'][kind] = [d for d in case['evidence'][kind] if key(d) != k]
    return case


def rebind(binding, **changes):
    b = {**binding, **changes}
    return {**b, 'binding_sha256': ev.hc(reg.without(b, 'binding_sha256'))}


class ExactVectors(unittest.TestCase):
    """Main acceptance criterion: the implementation recomputes every frozen record byte for byte."""

    def test_r01_r24_records_byte_for_byte(self):
        self.assertEqual(len(CASES), 51)
        count = 0
        for case in CASES:
            for exp, verdict, record in V.results(case):
                count += 1
                with self.subTest(case['id'], identity=exp['measurement_identity_sha256'][:12]):
                    want = exp['record']
                    self.assertEqual(verdict, exp['core_verdict'])
                    for field in ('verdict', 'blockers', 'attempts', 'unbound_attempts', 'series', 'transitions',
                                  'main_head_sha', 'registry_head', 'genesis_sha256', 'science_identity_sha256'):
                        self.assertEqual(record[field], want[field], field)
                    self.assertEqual(record, want)
                    self.assertEqual(record['record_sha256'], want['record_sha256'])
                    self.assertEqual(ev.hc(reg.without(record, 'record_sha256')), record['record_sha256'])
                    self.assertTrue(reg.valid(record, 'g1_record'))
        self.assertEqual(count, 60)
        self.assertEqual(V.mismatches(), [])

    def test_runner_expectations(self):
        for cid in ('R12.a', 'R21.a', 'R21.b'):
            case = BY_ID[cid]
            r, genesis, entries = case['runner'], case['registry']['genesis'], case['registry']['entries']
            git = V.git_snapshot(V.environment(case))
            mine = [e for e in entries if key(e) == key(r)]
            with self.subTest(cid):
                if r['register'] != 'NOT_RUN':  # register sees the registry as it was before the run's own entry
                    prefix = entries[:mine[0]['sequence'] - 1]
                    self.assertEqual(g1.register_check(genesis, prefix, execution(key(r), mine[0]['measured_source_sha']),
                                                       git, VECTORS['environment']['pull_requests'])[0], r['register'])
                else:  # failed-job rerun: register does not run, there is no entry, bind refuses before B
                    self.assertEqual(mine, [])
                    self.assertEqual(g1.bind_check(genesis, entries, execution(key(r), A), git, '0' * 64)[0],
                                     r['bind'])
                self.assertFalse(r['crosses_boundary'])

    def test_input_order_and_ids_do_not_matter(self):
        for case in CASES:
            shuffled = copy.deepcopy(case)
            shuffled['provider'].reverse()
            for k in ('bundles', 'bindings'):
                shuffled['evidence'][k].reverse()
            shuffled['id'] = 'X'
            shuffled['description'] = 'renamed'
            with self.subTest(case['id']):
                self.assertEqual({i: r['record_sha256'] for i, (_, r) in run(shuffled).items()},
                                 {e['measurement_identity_sha256']: e['record']['record_sha256']
                                  for e in case['expect']})

    def test_core_does_not_mutate_its_inputs(self):
        for case in CASES:
            x = V.evaluation(case)
            before = repr(x)
            for e in case['expect']:
                g1.g1_test(e['measurement_identity_sha256'], x)
            self.assertEqual(repr(x), before, case['id'])

    def test_implementation_never_reads_expectations(self):
        for module in (g1, reg):
            source = Path(module.__file__).read_text(encoding='utf-8')
            for needle in ('registry-vectors', "'expect'", 'record_sha256\']', 'oracle_v2_vectors', 'unittest',
                           "'R0", "'R1", "'R2"):
                self.assertNotIn(needle, source, (module.__name__, needle))


def execution(k, sha, **changes):
    return {'event': 'workflow_dispatch', 'repository': reg.REPOSITORY, 'run_id': k[0], 'run_attempt': k[1],
            'sha': sha, 'workflow_sha': sha, 'workflow_ref': REF, **changes}


class ApiSeparation(unittest.TestCase):
    """R17 and contract 11: production takes only the identity; the core never says PASS."""

    def test_production_signature(self):
        api = BY_ID['R17']['api']
        params = list(inspect.signature(g1.g1_production).parameters)
        self.assertEqual(params, api['production_parameters'])
        self.assertEqual(api['production_entry_point'], g1.g1_production.__name__)
        self.assertFalse(set(params) & set(api['forbidden_production_parameters']))
        with self.assertRaises(TypeError):
            g1.g1_production(BY_ID['R17']['expect'][0]['measurement_identity_sha256'], provider=None)

    def test_production_is_not_active_and_reads_nothing(self):
        identity = BY_ID['R17']['expect'][0]['measurement_identity_sha256']

        def forbidden(*args, **kwargs):
            raise AssertionError('production read before activation')
        with patch('subprocess.run', forbidden), patch('urllib.request.urlopen', forbidden), \
                patch.object(oa, '_git_show', forbidden), patch.object(g1, 'read_evidence_root', forbidden), \
                patch.dict(os.environ, {'GITHUB_API_URL': 'https://evil.invalid', 'GITHUB_REPOSITORY': 'evil/x'}):
            self.assertEqual(g1.g1_production(identity), ('NOT_PASSED', ['V2_NOT_ACTIVE']))
        for bad in ('0' * 63, identity.upper(), identity + '\n', None, 1):
            with self.subTest(bad=bad), self.assertRaises(ev.EvalError):
                g1.g1_production(bad)
        self.assertEqual(dict(reg.AUTHORITY)['provider_api'], 'https://api.github.com')

    def test_fake_provider_core_never_becomes_production_pass(self):
        case = BY_ID['R17']
        x = V.evaluation(case)  # injected registry/provider/evidence/KAT, all green
        identity = case['expect'][0]['measurement_identity_sha256']
        verdict, body = g1._g1_core(identity, x)
        self.assertEqual(verdict, 'SCIENTIFIC_PASS')
        _, test_record = g1.g1_test(identity, x)
        self.assertEqual((test_record['verdict'], test_record['authority'], test_record['evaluator']),
                         ('TEST_ONLY_PASS', None, None))
        self.assertEqual(test_record, case['expect'][0]['record'])
        prod = g1._production_record(verdict, body, MAIN)
        self.assertEqual((prod['verdict'], prod['blockers']), ('NOT_PASSED', ['V2_NOT_ACTIVE']))
        self.assertEqual(prod['authority'], dict(reg.AUTHORITY))
        self.assertTrue(reg.valid(prod, 'g1_record') and reg.self_digest_ok(prod, 'record_sha256'))
        self.assertTrue(reg.schema_errors({**test_record, 'verdict': 'PASS'}, 'g1_record'))  # schema forbids it

    def test_production_record_before_activation(self):
        seen = set()
        for case in CASES:
            x = V.evaluation(case)
            for e in case['expect']:
                verdict, body = g1._g1_core(e['measurement_identity_sha256'], x)
                prod = g1._production_record(verdict, body, MAIN)
                seen.add(verdict)
                with self.subTest(case['id'], verdict=verdict):
                    self.assertNotEqual(prod['verdict'], 'PASS')
                    self.assertTrue(reg.valid(prod, 'g1_record'))
                    if verdict in ('SCIENTIFIC_PASS', 'NOT_PASSED'):
                        self.assertEqual(prod['verdict'], 'NOT_PASSED')
                        self.assertIn('V2_NOT_ACTIVE', prod['blockers'])
                        self.assertEqual(set(prod['blockers']) - {'V2_NOT_ACTIVE'}, set(body['blockers']))
                    else:  # INVALID keeps only INVALID-class codes; NOT_RUN / NO_VERDICT skip the gates
                        self.assertEqual((prod['verdict'], prod['blockers']), (verdict, body['blockers']))
        self.assertEqual(seen, set(g1.CORE_VERDICTS))

    def test_core_vocabulary_has_no_pass(self):
        for case in CASES:
            x = V.evaluation(case)
            for e in case['expect']:
                self.assertIn(g1._g1_core(e['measurement_identity_sha256'], x)[0], g1.CORE_VERDICTS)
        for fn in (g1._g1_core, g1.analyze, g1.combine, g1.classify, g1.series_codes, g1.series_machine, g1.g1_test):
            self.assertNotIn("'PASS'", inspect.getsource(fn), fn.__name__)
        production = [n for n, f in vars(g1).items() if callable(f) and "'PASS'" in
                      (inspect.getsource(f) if inspect.isfunction(f) else '')]
        self.assertEqual(production, ['_production_record'])

    def test_production_module_imports_no_test_code(self):
        for module in (g1, reg):
            source = Path(module.__file__).read_text(encoding='utf-8')
            imports = [line for line in source.splitlines() if line.startswith(('import ', 'from '))]
            self.assertFalse([i for i in imports if 'test' in i or 'reference' in i or 'vectors' in i], imports)

    def test_tampered_record_is_detected(self):
        record = BY_ID['R05']['expect'][0]['record']
        forged = {**record, 'verdict': 'TEST_ONLY_PASS', 'blockers': []}
        self.assertFalse(reg.self_digest_ok(forged, 'record_sha256'))
        self.assertTrue(reg.schema_errors(reg.without(record, 'main_head_sha'), 'g1_record'))


class Classification(unittest.TestCase):
    OBS = BY_ID['R01']['provider'][0]
    ENTRY = BY_ID['R01']['registry']['entries'][0]

    def observation(self, **run_changes):
        o = copy.deepcopy(self.OBS)
        o['run'].update(run_changes)
        return o

    def measure(self, steps, started=True, conclusion='failure'):
        return [self.OBS['run']['jobs'][0], {'name': 'measure', 'started': started, 'conclusion': conclusion,
                                             'steps': [{'number': n, 'role': role, 'started': s,
                                                        'conclusion': c} for n, role, s, c in steps]}]

    def test_pre_needs_live_complete_provider_proof(self):
        pre_steps = [(1, 'other', True, 'success'), (2, 'bind', True, 'failure'), (3, 'boundary', False, 'skipped')]
        yes = {'bind failed, boundary not started': self.observation(jobs=self.measure(pre_steps)),
               'measure never started': self.observation(jobs=self.measure([], started=False)),
               'no measure job': self.observation(jobs=self.OBS['run']['jobs'][:1])}
        no = {'run deleted': {**self.OBS, 'run': None}, 'not obtained': None,
              'in progress': self.observation(status='in_progress', jobs=self.measure(pre_steps)),
              'queued': self.observation(status='queued', jobs=[]),
              'unknown job': self.observation(jobs=self.measure(pre_steps) + [{**self.OBS['run']['jobs'][0],
                                                                                'name': 'debug'}]),
              'two measure jobs': self.observation(jobs=self.measure(pre_steps) + self.measure(pre_steps)[1:]),
              'boundary started': self.observation(jobs=self.measure(pre_steps[:2] + [(3, 'boundary', True, None)])),
              'later step started': self.observation(jobs=self.measure(pre_steps + [(4, 'other', True, 'failure')])),
              'no boundary step': self.observation(jobs=self.measure(pre_steps[:2])),
              'two boundary steps': self.observation(jobs=self.measure(pre_steps + [(4, 'boundary', False, None)])),
              'other head sha': self.observation(head_sha=C, jobs=self.measure(pre_steps)),
              'push event': self.observation(event='push', jobs=self.measure(pre_steps)),
              'other branch': self.observation(head_branch='dev', jobs=self.measure(pre_steps)),
              'other workflow': self.observation(workflow_path='.github/workflows/foundation.yml',
                                                 jobs=self.measure(pre_steps))}
        for label, o in yes.items():
            with self.subTest(label):
                self.assertTrue(g1.pre_proven(o, self.ENTRY))
        for label, o in no.items():
            with self.subTest(label):
                self.assertFalse(g1.pre_proven(o, self.ENTRY))

    def test_bundle_needs_every_binding(self):
        case = BY_ID['R01']
        e, obs = case['registry']['entries'][1], case['provider'][1]
        bundle, binding = case['evidence']['bundles'][1], case['evidence']['bindings'][1]
        self.assertEqual(g1.classify(e, obs, bundle, binding, False), ('BUNDLE', set()))
        run = bundle['run']
        checks = {
            'bundle repository': ({**bundle, 'run': {**run, 'repository': 'fork/x'}}, binding, obs, 'BINDING_MISMATCH'),
            'bundle run id': ({**bundle, 'run': {**run, 'run_id': 7}}, binding, obs, 'BINDING_MISMATCH'),
            'bundle attempt': ({**bundle, 'run': {**run, 'run_attempt': 2}}, binding, obs, 'BINDING_MISMATCH'),
            'bundle sha': ({**bundle, 'run': {**run, 'sha': C}}, binding, obs, 'BINDING_MISMATCH'),
            'bundle workflow sha': ({**bundle, 'run': {**run, 'workflow_sha': C}}, binding, obs, 'BINDING_MISMATCH'),
            'bundle workflow ref': ({**bundle, 'run': {**run, 'workflow_ref': REF.replace('main', 'dev')}}, binding,
                                    obs, 'BINDING_MISMATCH'),
            'bundle identity': ({**bundle, 'measurement_identity_sha256': '0' * 64}, binding, obs, 'BINDING_MISMATCH'),
            'sidecar source': (bundle, rebind(binding, measured_source_sha=C), obs, 'BINDING_MISMATCH'),
            'sidecar identity': (bundle, rebind(binding, measurement_identity_sha256='0' * 64), obs,
                                 'BINDING_MISMATCH'),
            'sidecar sequence': (bundle, rebind(binding, entry_sequence=1), obs, 'BINDING_MISMATCH'),
            'sidecar entry': (bundle, rebind(binding, entry_sha256='0' * 64), obs, 'BINDING_MISMATCH'),
            'sidecar repository': (bundle, {**binding, 'repository': 'fork/x'}, obs, 'BINDING_MISMATCH'),
            'provider head sha': (bundle, binding, {**obs, 'run': {**obs['run'], 'head_sha': C}}, 'BINDING_MISMATCH'),
            'provider event': (bundle, binding, {**obs, 'run': {**obs['run'], 'event': 'push'}}, 'BINDING_MISMATCH'),
            'no sidecar': (bundle, None, obs, 'UNBOUND_MEASUREMENT'),
            'sidecar before its entry': (bundle, rebind(binding, observed_head={'sequence': 1, 'entry_sha256': '1' * 64}),
                                         obs, 'UNBOUND_MEASUREMENT'),
        }
        jobs = obs['run']['jobs']

        def steps(*changes):
            measure = copy.deepcopy(jobs[1])
            for number, change in changes:
                measure['steps'][number - 1].update(change)
            return {**obs, 'run': {**obs['run'], 'jobs': [jobs[0], measure]}}
        checks.update({
            'bind failed': (bundle, binding, steps((2, {'conclusion': 'failure'})), 'UNBOUND_MEASUREMENT'),
            'bind not started': (bundle, binding, steps((2, {'started': False})), 'UNBOUND_MEASUREMENT'),
            'bind after boundary': (bundle, binding, steps((2, {'role': 'boundary'}), (3, {'role': 'bind'})),
                                    'UNBOUND_MEASUREMENT'),
            'boundary not started': (bundle, binding, steps((3, {'started': False})), 'BINDING_MISMATCH'),
        })
        for label, (b, s, o, code) in checks.items():
            with self.subTest(label):
                cls, violations = g1.classify(e, o, b, s, False)
                self.assertEqual(cls, 'MISSING')
                self.assertIn(code, violations)
        self.assertEqual(g1.classify(e, obs, bundle, binding, True), ('MISSING', {'DUPLICATE_EXECUTION'}))
        unverified = {**bundle, 'bundle_verified': False}
        self.assertEqual(g1.classify(e, obs, unverified, binding, False), ('MISSING', set()))
        self.assertEqual(g1.classify(e, {**obs, 'run': None}, bundle, binding, False), ('MISSING', set()))
        self.assertEqual(g1.classify(e, None, bundle, binding, False), ('MISSING', set()))
        self.assertEqual(g1.classify(e, obs, None, binding, False), ('MISSING', set()))  # crossed B, nothing kept

    def test_unbound_attempts_of_registered_runs(self):
        case = copy.deepcopy(BY_ID['R12.b'])
        entries, provider = case['registry']['entries'], {key(o): o for o in case['provider']}
        self.assertEqual([key(u) for u in g1.unbound_attempts(entries, provider)], [(24000000001, 2)])
        pre = copy.deepcopy(BY_ID['R12.a']['provider'][2])
        self.assertEqual(g1.unbound_attempts(entries, {**provider, key(pre): pre}), ())
        del provider[(24000000001, 2)]  # deleting the rerun's provider data does not hide it
        self.assertEqual([key(u) for u in g1.unbound_attempts(entries, provider)], [(24000000001, 2)])
        third = copy.deepcopy(provider[(24000000001, 1)])
        third['run']['latest_run_attempt'] = 3
        out = g1.unbound_attempts(entries, {**provider, (24000000001, 1): third, key(pre): pre})
        self.assertEqual([key(u) for u in out], [(24000000001, 3)])
        gone = {k: {**o, 'run': None} for k, o in provider.items()}  # whole run deleted: entries MISSING instead
        self.assertEqual(g1.unbound_attempts(entries, gone), ())

    def test_invalid_and_missing_cannot_be_outvoted(self):
        for cid, verdict, code in (('R06', 'INVALID', 'RUN_INVALID'), ('R05', 'NOT_PASSED', 'RESULT_MISSING'),
                                   ('R16.b', 'INVALID', 'UNBOUND_MEASUREMENT'), ('R12.b', 'INVALID', 'UNBOUND_MEASUREMENT'),
                                   ('R15.b', 'NOT_PASSED', 'SERIES_FAILURE')):
            case = copy.deepcopy(BY_ID[cid])
            for run_id in (24000000011, 24000000012, 24000000013):
                add_complete_attempt(case, run_id)
            with self.subTest(cid):
                got, record = first(case)
                self.assertEqual(got, verdict)
                self.assertIn(code, record['blockers'])
                self.assertEqual(len(record['attempts']), len(BY_ID[cid]['registry']['entries']) + 3)


def add_complete_attempt(case, run_id, source=A, template=0):
    """Append a registered, bound, verified COMPLETE attempt (entry, sidecar, bundle, provider run) to a case."""
    entries = case['registry']['entries']
    sources = {s['sha']: s['measurement_identity'] for s in VECTORS['environment']['sources']}
    e = reg.make_entry(case['registry']['genesis'], entries, run_id=run_id, run_attempt=1, measured_source_sha=source,
                       workflow_ref=REF, measurement_identity=sources[source])
    entries.append(e)
    base = BY_ID['R01']
    bundle = copy.deepcopy(base['evidence']['bundles'][template])
    bundle.update(run_id=run_id, run_attempt=1, measurement_identity_sha256=e['measurement_identity_sha256'])
    bundle['run'].update(run_id=run_id, run_attempt=1, sha=source, workflow_sha=source)
    obs = copy.deepcopy(base['provider'][template])
    obs.update(run_id=run_id)
    obs['run'].update(head_sha=source)
    binding = rebind(base['evidence']['bindings'][template], run_id=run_id, run_attempt=1, measured_source_sha=source,
                     measurement_identity_sha256=e['measurement_identity_sha256'], entry_sequence=e['sequence'],
                     entry_sha256=e['entry_sha256'], observed_head={'sequence': e['sequence'],
                                                                    'entry_sha256': e['entry_sha256']})
    case['evidence']['bundles'].append(bundle)
    case['evidence']['bindings'].append(binding)
    case['provider'].append(obs)
    case['registry_remote_head'] = reg.head(case['registry']['genesis'], entries)
    return e


class SeriesMachine(unittest.TestCase):
    ENV = VECTORS['environment']
    GIT = V.git_snapshot(ENV)
    PRS = {p['number']: p for p in ENV['pull_requests']}
    SOURCES = SOURCES
    S1, S2, S3 = S1, S2, S3

    def chain(self, *runs, prs=None):
        """runs = [(source, transition or None)] -> (series, transitions, current) of the machine."""
        genesis, entries = BY_ID['R01']['registry']['genesis'], []
        for n, (source, t) in enumerate(runs, 1):
            entries.append(reg.make_entry(genesis, entries, run_id=n, run_attempt=1, measured_source_sha=source,
                                          workflow_ref=REF, measurement_identity=self.SOURCES[source], transition=t))
        reg.validate(genesis, entries, self.GIT)
        return g1.series_machine(entries, self.GIT, prs or self.PRS)

    def t(self, previous, new, reason='BUG_FIX', pr=101, merge='c64080c36580d5b937d3f86f4e3b5f53000368a1'):
        return reg.make_transition('pilot', previous, new, reason, pr, merge)

    def states(self, series):
        return {s: (i['state'], i['codes']) for s, i in series.items()}

    def test_first_series_and_carry_over_within_series(self):
        series, transitions, current = self.chain((A, None), (C, None), (A, None))
        self.assertEqual(self.states(series), {self.S1: ('CURRENT', [])})
        self.assertEqual((transitions, current), ((), {'pilot': self.S1}))

    def test_valid_transitions_retire_linearly(self):
        s2_to_s3 = self.t(self.S2, self.S3, 'IMPLEMENTATION_CHANGE', 102, '442683cae1762a7d549a87479baa377287b2cdc2')
        series, transitions, current = self.chain((A, None), (D, self.t(self.S1, self.S2)),
                                                  ('f8f6a7c54fd1673dc3a53125c4e6379b85a9930f', s2_to_s3))
        self.assertEqual(self.states(series), {self.S1: ('RETIRED', []), self.S2: ('RETIRED', []),
                                               self.S3: ('CURRENT', [])})
        self.assertEqual([t['status'] for t in transitions], ['VALID', 'VALID'])
        self.assertEqual(current, {'pilot': self.S3})

    def test_invalid_transitions(self):
        good = self.t(self.S1, self.S2)
        prs = {**self.PRS, 101: {**self.PRS[101], 'base_ref': 'refs/heads/dev'}}
        cases = {
            'missing': ((A, None), (D, None), 'ORPHAN', 'SERIES_TRANSITION_MISSING', None),
            'stale previous': ((A, None), (D, self.t(self.S3, self.S2)), 'ORPHAN', 'SERIES_TRANSITION_MISMATCH',
                               'MISMATCH'),
            'semantic change under v1': ((A, None), (D, self.t(self.S1, self.S2, 'SEMANTIC_CHANGE')), 'ORPHAN',
                                         'SERIES_TRANSITION_MISMATCH', 'MISMATCH'),
            'merge commit of another series (V4)': ((A, None), (D, self.t(
                self.S1, self.S2, merge='442683cae1762a7d549a87479baa377287b2cdc2', pr=102)), 'ORPHAN',
                'SERIES_TRANSITION_MISMATCH', 'MISMATCH'),
            'PR unknown': ((A, None), (D, self.t(self.S1, self.S2, pr=999)), 'ORPHAN', 'SERIES_TRANSITION_MISMATCH',
                           'MISMATCH'),
            'transition on first entry': ((D, good), 'CURRENT', 'SERIES_TRANSITION_MISMATCH', 'MISMATCH'),
            'transition into current': ((A, None), (A, self.t(self.S2, self.S1)), 'CURRENT',
                                        'SERIES_TRANSITION_MISMATCH', 'MISMATCH'),
        }
        for label, spec in cases.items():
            *runs, state, code, status = spec
            with self.subTest(label):
                series, transitions, _ = self.chain(*runs)
                target = runs[-1][0]
                s = ev.hc(reg.science_identity(self.SOURCES[target]))
                self.assertEqual(self.states(series)[s], (state, [code]))
                self.assertEqual([t['status'] for t in transitions][-1:], [status] if status else [])
        series, transitions, _ = self.chain((A, None), (D, good), prs=prs)
        self.assertEqual((self.states(series)[self.S2], transitions[0]['status']),
                         (('ORPHAN', ['SERIES_TRANSITION_MISMATCH']), 'MISMATCH'))  # PR base not main (V2)

    def test_orphan_reentry_fork(self):
        series, _, _ = self.chain((A, None), (D, None), (D, None))           # orphan stays orphan, one code
        self.assertEqual(self.states(series)[self.S2], ('ORPHAN', ['SERIES_TRANSITION_MISSING']))
        series, transitions, current = self.chain((A, None), (D, self.t(self.S1, self.S2)), (C, None))
        self.assertEqual(self.states(series)[self.S1], ('RETIRED', ['SERIES_REENTRY']))
        self.assertEqual(current, {'pilot': self.S2})
        fork = self.t(self.S1, self.S3, pr=102, merge='442683cae1762a7d549a87479baa377287b2cdc2')
        series, transitions, _ = self.chain((A, None), (D, self.t(self.S1, self.S2)),
                                            ('f8f6a7c54fd1673dc3a53125c4e6379b85a9930f', fork))
        self.assertEqual(self.states(series)[self.S3], ('ORPHAN', ['SERIES_FORK']))
        self.assertEqual([t['status'] for t in transitions], ['VALID', 'FORK'])
        back = self.t(self.S2, self.S1)
        series, transitions, _ = self.chain((A, None), (D, self.t(self.S1, self.S2)), (C, back))
        self.assertEqual(transitions[-1]['status'], 'REENTRY')
        self.assertEqual(self.states(series)[self.S1], ('RETIRED', ['SERIES_REENTRY']))

    def test_series_codes_for_r15_r21_r22(self):
        expect = {'R15.a': {'SERIES_INVALID'}, 'R15.b': {'SERIES_FAILURE'}, 'R15.c': {'SERIES_REPEAT_MISMATCH'},
                  'R15.d': set(), 'R21.a': {'SERIES_TRANSITION_MISSING'}, 'R22.c': {'SERIES_FORK'},
                  'R22.d': {'SERIES_REENTRY', 'SERIES_SUPERSEDED'}}
        for cid, codes in expect.items():
            case = BY_ID[cid]
            a = g1.analyze(V.evaluation(case))
            identity = case['expect'][0]['measurement_identity_sha256']
            science = [e for e in a.entries if e['measurement_identity_sha256'] == identity][0]['science_identity_sha256']
            with self.subTest(cid):
                self.assertEqual(g1.series_codes(a, science, identity), codes)

    def test_sibling_outcomes_carry_over(self):
        base = BY_ID['R15.a']  # sibling C (other identity, same science) is entry 1
        for outcome, conformance, code in (('INCOMPLETE', True, 'SERIES_FAILURE'),
                                           ('COMPLETE_WITH_FAILURES', True, 'SERIES_FAILURE'),
                                           ('COMPLETE', False, 'SERIES_FAILURE'), ('INVALID', True, 'SERIES_INVALID')):
            case = copy.deepcopy(base)
            c = case['evidence']['bundles'][0]
            c.update(run_status=outcome, conformance=conformance)
            if outcome != 'INVALID':
                c.update({k: v for k, v in case['evidence']['bundles'][1].items() if k.endswith('_sha256')
                          and k != 'measurement_identity_sha256'})
            with self.subTest(outcome=outcome, conformance=conformance):
                verdict, record = first(case)
                self.assertNotIn(verdict, PASSING)
                self.assertIn(code, record['blockers'])
        case = copy.deepcopy(base)  # sibling unbound attempt (rerun of C crossed B)
        rerun = copy.deepcopy(BY_ID['R12.b']['provider'][2])
        rerun.update(run_id=24000000003)
        rerun['run']['head_sha'] = C
        for o in case['provider']:
            if key(o) == (24000000003, 1):
                o['run']['latest_run_attempt'] = 2
        case['provider'].append(rerun)
        case['evidence']['bundles'][0].update({k: v for k, v in case['evidence']['bundles'][1].items()
                                               if k in ('run_status', 'cost_projection_sha256', 'targets_sha256',
                                                        'sealed_commitments_sha256', 'series_projection_sha256')})
        verdict, record = first(case)
        self.assertEqual((verdict, record['blockers']), ('INVALID', ['SERIES_INVALID']))
        self.assertEqual([key(u) for u in record['unbound_attempts']], [(24000000003, 2)])


class Adversarial(unittest.TestCase):
    """The C1-A self-review attack list: each path is closed by a code, never by silence."""

    def verdict(self, case):
        v, record = first(case)
        return v, record['blockers']

    def test_delete_failed_entry(self):
        case = copy.deepcopy(BY_ID['R15.a'])
        del case['registry']['entries'][0]
        self.assertEqual(self.verdict(case), ('NO_VERDICT', ['REGISTRY_INVALID']))      # chain broken
        drop(drop(drop(case, 'provider', (24000000003, 1)), 'bundles', (24000000003, 1)), 'bindings',
             (24000000003, 1))
        V.redigest(case, sidecars=False)                                                  # rehash the registry
        self.assertEqual(self.verdict(case), ('NO_VERDICT', ['REGISTRY_ROLLBACK']))     # retained witnesses

    def test_delete_provider_bundle_or_sidecar(self):
        for cid, k in (('R06', (24000000003, 1)), ('R15.a', (24000000003, 1)), ('R01', (24000000002, 1))):
            for kind in ('provider', 'bundles', 'bindings'):
                with self.subTest(cid, kind=kind):
                    self.assertNotIn(self.verdict(drop(copy.deepcopy(BY_ID[cid]), kind, k))[0], PASSING)

    def test_unregistered_evidence(self):
        for kind, doc in (('bundles', {**BY_ID['R01']['evidence']['bundles'][0], 'run_id': 9}),
                          ('bindings', rebind(BY_ID['R01']['evidence']['bindings'][0], run_id=9))):
            case = copy.deepcopy(BY_ID['R01'])
            case['evidence'][kind].append(doc)
            self.assertEqual(self.verdict(case), ('NO_VERDICT', ['EVIDENCE_ROOT_INVALID']), kind)
        for change in ({'foreign_paths': ['notes.txt']}, {'v1_root_keys': [{'run_id': 24000000002, 'run_attempt': 1}]}):
            case = copy.deepcopy(BY_ID['R01'])
            case['evidence'].update(change)
            self.assertEqual(self.verdict(case), ('NO_VERDICT', ['EVIDENCE_ROOT_INVALID']), change)
        case = copy.deepcopy(BY_ID['R01'])
        case['evidence']['bindings'][1] = {**case['evidence']['bindings'][1], 'entry_sequence': 1}  # stale digest
        self.assertEqual(self.verdict(case), ('NO_VERDICT', ['EVIDENCE_ROOT_INVALID']))
        case = copy.deepcopy(BY_ID['R01'])
        case['evidence']['bundles'].append(copy.deepcopy(case['evidence']['bundles'][1]))  # duplicate bundle key
        self.assertEqual(self.verdict(case), ('NO_VERDICT', ['EVIDENCE_ROOT_INVALID']))

    def test_substituted_sidecar(self):
        case = copy.deepcopy(BY_ID['R01'])
        case['evidence']['bindings'][1] = rebind(case['evidence']['bindings'][1], measured_source_sha=C)
        self.assertEqual(self.verdict(case), ('INVALID', ['BINDING_MISMATCH', 'RUN_INVALID']))

    def test_pre_from_sidecar_or_deleted_provider(self):
        case = drop(copy.deepcopy(BY_ID['R08.a']), 'provider', (24000000003, 1))
        case['evidence']['bindings'].append(rebind(BY_ID['R09.a']['evidence']['bindings'][2]))
        self.assertEqual(self.verdict(case), ('NOT_PASSED', ['RESULT_MISSING']))
        self.assertEqual(first(case)[1]['attempts'][2]['class'], 'MISSING')

    def test_same_run_id_reruns_never_repeat(self):
        case = copy.deepcopy(BY_ID['R11'])
        e = add_complete_attempt(case, 24000000001)
        e.update(run_attempt=3)
        case['evidence']['bundles'][-1].update(run_attempt=3)
        case['evidence']['bundles'][-1]['run'].update(run_attempt=3)
        case['provider'][-1].update(run_attempt=3)
        case['evidence']['bindings'][-1] = rebind(case['evidence']['bindings'][-1], run_attempt=3)
        for o in case['provider']:
            o['run']['latest_run_attempt'] = 3
        V.redigest(case)
        self.assertEqual(self.verdict(case), ('NOT_PASSED', ['REPEAT_MISSING']))

    def test_identity_and_science_swaps(self):
        case = copy.deepcopy(BY_ID['R01'])
        case['registry']['entries'][1]['measurement_identity_sha256'] = BY_ID['R13.a']['evidence']['bundles'][1][
            'measurement_identity_sha256']
        V.redigest(case)
        self.assertEqual(self.verdict(case), ('NO_VERDICT', ['REGISTRY_INVALID']))      # != git_source
        case = copy.deepcopy(BY_ID['R15.e'])
        case['registry']['entries'][3]['transition'] = None                               # remove the transition
        V.redigest(case)
        got = {i: (v, r['blockers']) for i, (v, r) in run(case).items()}
        self.assertEqual(got[case['expect'][0]['measurement_identity_sha256']],
                         ('NOT_PASSED', ['SERIES_TRANSITION_MISSING']))
        self.assertEqual(got[case['expect'][1]['measurement_identity_sha256']], ('INVALID', ['SERIES_INVALID']))

    def test_truncation_and_rehash(self):
        case = copy.deepcopy(BY_ID['R06'])
        case['registry']['entries'].pop()
        V.redigest(case, sidecars=False)
        self.assertEqual(self.verdict(case), ('NO_VERDICT', ['REGISTRY_ROLLBACK']))     # witness of C
        add_complete_attempt(case, 24000000009)                                           # rehash with a new tail
        self.assertEqual(self.verdict(case), ('NO_VERDICT', ['REGISTRY_ROLLBACK']))
        old = BY_ID['R06']
        truncated = copy.deepcopy(old)
        truncated['registry']['entries'].pop()
        for kind in ('provider', 'bundles', 'bindings'):
            drop(truncated, kind, (24000000003, 1))
        V.redigest(truncated, sidecars=False)
        # Residual level-1 window (contract 13.1): truncation plus deletion of every trace is invisible to the core;
        # the registry ruleset closes it against non-admins, and a checkpoint taken before it no longer lies on the
        # truncated chain.
        self.assertEqual(self.verdict(truncated)[0], 'SCIENTIFIC_PASS')
        checkpoint_head = old['registry_remote_head']
        self.assertFalse(reg.on_history(checkpoint_head, reg.history(truncated['registry']['genesis'],
                                                                     truncated['registry']['entries'])))

    def test_stale_registry_main_and_subset(self):
        case = copy.deepcopy(BY_ID['R05'])
        case['registry']['entries'].pop()                                 # caller-selected subset, true remote head
        self.assertEqual(self.verdict(case), ('NO_VERDICT', ['REGISTRY_STALE']))
        case = copy.deepcopy(BY_ID['R01'])
        case['main_remote_head'] = 'eea4b5164ff9407dc75fccfbf215a81205e83dec'                 # main A -> B
        self.assertEqual(self.verdict(case), ('NO_VERDICT', ['MAIN_STALE']))
        self.assertEqual(first(case)[1]['main_head_sha'], MAIN)
        self.assertEqual(self.verdict(BY_ID['R01'])[0], 'SCIENTIFIC_PASS')                   # main A -> A

    def test_kat_on_both_commits(self):
        green = set(VECTORS['environment']['kat_green'])
        for label, kat, evaluator in (('measured only', green - {MAIN}, MAIN), ('evaluator only', green - {A}, MAIN),
                                      ('evaluator off main', green | {OFF_MAIN}, OFF_MAIN), ('neither', set(), MAIN)):
            case = copy.deepcopy(BY_ID['R01'])
            case['environment_override'] = {'kat_green': sorted(kat), 'evaluator_source_sha': evaluator}
            with self.subTest(label):
                self.assertEqual(self.verdict(case), ('NOT_PASSED', ['KAT_NOT_VERIFIED']))

    def test_ambiguous_provider_or_pull_request_data_is_never_chosen(self):
        case = copy.deepcopy(BY_ID['R08.a'])                  # C proven PRE by its only observation
        crossed = copy.deepcopy(BY_ID['R10.a']['provider'][2])  # same key, boundary started
        case['provider'].append(crossed)
        self.assertEqual(self.verdict(case), ('NOT_PASSED', ['RESULT_MISSING']))
        case = copy.deepcopy(BY_ID['R15.e'])
        prs = copy.deepcopy(VECTORS['environment']['pull_requests'])
        case['environment_override'] = {'pull_requests': prs + [{**prs[0], 'merged': False}]}
        got = {i: (v, r['blockers']) for i, (v, r) in run(case).items()}
        self.assertEqual(got[case['expect'][0]['measurement_identity_sha256']],
                         ('INVALID', ['SERIES_TRANSITION_MISMATCH']))

    def test_check_order_first_failure_only(self):
        case = copy.deepcopy(BY_ID['R03.a'])
        case['main_remote_head'] = OFF_MAIN
        self.assertEqual(self.verdict(case), ('NO_VERDICT', ['MAIN_STALE']))       # item 4 before item 5
        case['registry_remote_head'] = {'sequence': 9, 'entry_sha256': '9' * 64}
        self.assertEqual(self.verdict(case), ('NO_VERDICT', ['REGISTRY_STALE']))   # item 3 before item 4
        case = copy.deepcopy(BY_ID['R07.a'])
        case['evidence']['bindings'][2] = rebind(case['evidence']['bindings'][2],
                                                 observed_head={'sequence': 5, 'entry_sha256': '5' * 64})
        self.assertEqual(self.verdict(case), ('NO_VERDICT', ['REGISTRY_ROLLBACK']))  # item 5 before item 6


class Monotonicity(unittest.TestCase):
    """Contract 9.4: deleting provider data or retained evidence of a registered attempt never yields a pass."""

    def deletions(self, case):
        keys = {key(e) for e in case['registry']['entries']}
        for kind, docs in (('provider', case['provider']), ('bundles', case['evidence']['bundles']),
                           ('bindings', case['evidence']['bindings'])):
            for k in sorted({key(d) for d in docs} & keys | ({key(d) for d in docs} if kind == 'provider' else set())):
                yield (kind,), k
        for k in sorted(keys):
            yield ('provider', 'bundles', 'bindings'), k

    def test_deletion_never_creates_a_pass(self):
        checked = 0
        for case in CASES:
            before = run(case)
            series_of = {e['measurement_identity_sha256']: e['science_identity_sha256']
                         for e in case['registry']['entries']}
            for kinds, k in self.deletions(case):
                changed = copy.deepcopy(case)
                for kind in kinds:
                    drop(changed, kind, k)
                after = run(changed)
                owner = [e for e in case['registry']['entries'] if key(e) == k]
                for identity, (verdict, _) in after.items():
                    checked += 1
                    with self.subTest(case['id'], kinds=kinds, key=k, identity=identity[:8]):
                        if before[identity][0] not in PASSING:
                            self.assertNotIn(verdict, PASSING)
                        elif owner and owner[0]['science_identity_sha256'] == series_of.get(identity):
                            self.assertNotIn(verdict, PASSING)  # anything of the identity's own series was removed
        self.assertGreater(checked, 300)


class RunnerDecisions(unittest.TestCase):
    CASE = BY_ID['R01']
    GENESIS, ENTRIES = CASE['registry']['genesis'], CASE['registry']['entries']
    GIT = V.git_snapshot(VECTORS['environment'])
    PRS = VECTORS['environment']['pull_requests']

    def register(self, entries, k, sha=A, transition=None, **changes):
        return g1.register_check(self.GENESIS, entries, execution(k, sha, **changes), self.GIT, self.PRS, transition)

    def test_register_reproduces_frozen_entries_and_bind_frozen_sidecars(self):
        for n, e in enumerate(self.ENTRIES):
            code, entry = self.register(self.ENTRIES[:n], key(e))
            self.assertEqual((code, entry), ('APPENDED', e))
            status, binding = g1.bind_check(self.GENESIS, self.ENTRIES[:n + 1], execution(key(e), A), self.GIT,
                                            e['entry_sha256'])
            self.assertEqual((status, binding), ('BOUND', self.CASE['evidence']['bindings'][n]))

    def test_register_refusals(self):
        self.assertEqual(self.register([], (1, 1), event='push')[0], 'DISPATCH_REJECTED')
        self.assertEqual(self.register([], (1, 1), workflow_sha=C)[0], 'DISPATCH_REJECTED')
        self.assertEqual(self.register([], (1, 1), workflow_ref=REF.replace('heads', 'tags'))[0], 'DISPATCH_REJECTED')
        self.assertEqual(self.register([], (1, 1), repository='fork/Shift-lab')[0], 'DISPATCH_REJECTED')
        self.assertEqual(self.register([], (1, 1), sha=OFF_MAIN, workflow_sha=OFF_MAIN)[0], 'SOURCE_NOT_ON_MAIN')
        self.assertEqual(self.register([], (0, 1))[0], 'DISPATCH_REJECTED')
        self.assertEqual(self.register([], (1, True))[0], 'DISPATCH_REJECTED')
        self.assertEqual(g1.register_check(BY_ID['R02.a']['registry']['genesis'], BY_ID['R02.a']['registry']['entries'],
                                           execution((9, 1), A), self.GIT, self.PRS)[0], 'REGISTRY_INVALID')
        self.assertEqual(self.register(BY_ID['R04']['registry']['entries'], (9, 1))[0], 'REGISTRY_DUPLICATE')
        self.assertEqual(self.register(self.ENTRIES, key(self.ENTRIES[0])), ('APPENDED', self.ENTRIES[0]))  # retry
        self.assertEqual(self.register(self.ENTRIES, key(self.ENTRIES[0]), sha=C, workflow_sha=C)[0],
                         'REGISTRY_DUPLICATE')

    def test_transition_required_and_checked(self):
        k = (24000000004, 1)
        self.assertEqual(self.register(self.ENTRIES, k, sha=D, workflow_sha=D)[0], 'TRANSITION_REQUIRED')
        t = BY_ID['R15.e']['registry']['entries'][3]['transition']
        code, entry = self.register(self.ENTRIES, k, D, ev.canonical(t), workflow_sha=D)
        self.assertEqual((code, entry['transition']), ('APPENDED', t))
        reg.validate(self.GENESIS, [*self.ENTRIES, entry], self.GIT)
        bad = {'digest': {**t, 'reason': 'IMPLEMENTATION_CHANGE'},
               'stale previous': reg.make_transition('pilot', '0' * 64, t['new_science_identity_sha256'], 'BUG_FIX',
                                                     101, t['change_review']['merge_commit_sha']),
               'other series': reg.make_transition('pilot', t['previous_science_identity_sha256'], '0' * 64,
                                                   'BUG_FIX', 101, t['change_review']['merge_commit_sha']),
               'merge not ancestor': reg.make_transition('pilot', t['previous_science_identity_sha256'],
                                                         t['new_science_identity_sha256'], 'BUG_FIX', 103,
                                                         '72ea0c2caf82d7b0f312a5fc9cd6d05850188aa5')}
        for label, doc in bad.items():
            with self.subTest(label):
                self.assertEqual(self.register(self.ENTRIES, k, D, ev.canonical(doc), workflow_sha=D)[0],
                                 'TRANSITION_INVALID')
        self.assertEqual(self.register(self.ENTRIES, k, D, ev.compact(t).encode(), workflow_sha=D)[0],
                         'TRANSITION_INVALID')  # not canonical file form
        self.assertEqual(self.register(self.ENTRIES, (9, 1), C, ev.canonical(t), workflow_sha=C)[1]['transition'],
                         None)  # same series: transition not required, file ignored

    def test_bind_refusals(self):
        e = self.ENTRIES[1]
        for label, args in (('wrong register output', (self.ENTRIES, execution(key(e), A), '0' * 64)),
                            ('other source', (self.ENTRIES, execution(key(e), C, workflow_sha=C), e['entry_sha256'])),
                            ('no entry', (self.ENTRIES[:1], execution(key(e), A), e['entry_sha256'])),
                            ('invalid registry', (BY_ID['R02.b']['registry']['entries'], execution(key(e), A),
                                                  e['entry_sha256'])),
                            ('duplicate', (BY_ID['R04']['registry']['entries'], execution((24000000001, 1), A),
                                           BY_ID['R04']['registry']['entries'][0]['entry_sha256']))):
            with self.subTest(label):
                self.assertEqual(g1.bind_check(self.GENESIS, *args[:2], self.GIT, args[2]), ('REGISTRY_UNBOUND', None))


class ProviderNormalization(unittest.TestCase):
    def test_api_documents_to_observation(self):
        run_doc = {'id': 24000000003, 'run_attempt': 1}
        attempt = {'head_sha': A, 'head_branch': 'main', 'path': reg.WORKFLOW_PATH, 'event': 'workflow_dispatch',
                   'status': 'completed'}
        jobs = [{'name': 'register', 'status': 'completed', 'conclusion': 'success',
                 'steps': [{'number': 1, 'name': 'Register', 'status': 'completed', 'conclusion': 'success'}]},
                {'name': 'measure', 'status': 'completed', 'conclusion': 'failure',
                 'steps': [{'number': 1, 'name': 'Checkout', 'status': 'completed', 'conclusion': 'success'},
                           {'number': 2, 'name': 'Bind', 'status': 'completed', 'conclusion': 'failure'},
                           {'number': 3, 'name': 'Boundary', 'status': 'completed', 'conclusion': 'skipped'},
                           {'number': 4, 'name': 'Measure', 'status': 'completed', 'conclusion': 'skipped'}]}]
        roles = {'Bind': 'bind', 'Boundary': 'boundary'}
        doc = g1.provider_observation(24000000003, 1, run_doc, attempt, jobs, roles)
        self.assertEqual(doc, BY_ID['R08.a']['provider'][2])  # the frozen PRE observation
        self.assertTrue(reg.valid(doc, 'provider_observation'))
        self.assertIsNone(g1.provider_observation(24000000003, 1, run_doc, None, [], roles)['run'])
        self.assertIsNone(g1.provider_observation(24000000003, 1, None, attempt, jobs, roles)['run'])
        unnamed = g1.provider_observation(24000000003, 1, run_doc, attempt, jobs, {})  # roles unknown: never PRE
        self.assertFalse(g1.pre_proven(unnamed, BY_ID['R08.a']['registry']['entries'][2]))


class SmokeAPI:
    """oracle-smoke.yml runs for exactly one commit; attempts: [(status, conclusion, KAT step conclusion)]."""

    def __init__(self, sha, attempts, step='KAT v2'):
        self.sha, self.attempts, self.step = sha, attempts, step

    def __call__(self, path):
        repo = reg.REPOSITORY
        if path.endswith('/actions/workflows/oracle-smoke.yml'):
            return {'id': 9, 'path': oa.SMOKE_WORKFLOW}
        if '/runs?head_sha=' in path:
            ok = f'head_sha={self.sha}' in path
            runs = [{'id': 100, 'event': 'push', 'head_sha': self.sha, 'workflow_id': 9,
                     'run_attempt': len(self.attempts), 'repository': {'full_name': repo},
                     'head_repository': {'full_name': repo}}] if ok and self.attempts else []
            return {'total_count': len(runs), 'workflow_runs': runs}
        tail = path.split('/actions/runs/')[1].split('?')[0].split('/')
        status, conclusion, step = self.attempts[int(tail[2]) - 1]
        if len(tail) == 3:
            return {'id': 100, 'run_attempt': int(tail[2]), 'head_sha': self.sha, 'status': status,
                    'conclusion': conclusion}
        return {'total_count': 1, 'jobs': [{'id': 1000 + int(tail[2]), 'name': oa.KAT_JOB, 'run_attempt': int(tail[2]),
                                            'head_sha': self.sha, 'steps': [{'name': self.step, 'conclusion': step}]}]}


class KatV2(unittest.TestCase):
    SHA, PINNED = 'c' * 40, 'd' * 40
    GREEN = ('completed', 'success', 'success')

    def verified(self, attempts=(GREEN,), ancestor=True, changed=None, step='KAT v2'):
        root = ev.ROOT

        def show(r, sha, path):
            data = (Path(root) / path).read_bytes()
            return data + b'#' if sha == self.SHA and path == changed else data

        class Done:
            def __init__(self, code):
                self.returncode = code
        with patch.object(oa, '_git_show', side_effect=show), \
                patch.object(g1, '_git', return_value=Done(0 if ancestor else 1)):
            return g1.kat_verified_v2(SmokeAPI(self.SHA, list(attempts)), self.SHA, self.PINNED, step, root)

    def test_green_commit_on_pinned_main(self):
        self.assertEqual(reg.MEASUREMENT_FREEZE_SHA256, 'c56fc053b103cecd38446b3791db104a12b9fafabacdfc6b71f6f23c0bf7f729')
        self.assertTrue(self.verified())
        self.assertTrue(self.verified([('completed', 'cancelled', None), self.GREEN]))

    def test_not_green(self):
        v1_file = next(iter(ev.parse_doc((ev.ORACLE / 'freeze.json').read_bytes())['files']))
        v2_file = '.work/oracle/registry-vectors.json'
        for label, kwargs in (('off pinned main', {'ancestor': False}), ('no run', {'attempts': []}),
                              ('red attempt outvoted', {'attempts': [('completed', 'failure', 'failure'), self.GREEN]}),
                              ('pending', {'attempts': [self.GREEN, ('in_progress', None, None)]}),
                              ('KAT step skipped', {'attempts': [('completed', 'success', 'skipped')]}),
                              ('smoke workflow differs', {'changed': oa.SMOKE_WORKFLOW}),
                              ('v1 frozen file differs', {'changed': v1_file}),
                              ('v2 frozen file differs', {'changed': v2_file}),
                              ('freeze-v2 differs', {'changed': '.work/oracle/freeze-v2.json'}),
                              ('activation names no KAT step', {'step': None})):
            with self.subTest(label):
                self.assertFalse(self.verified(**kwargs))


class EvidenceRoot(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='v2-root-'))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root, self.v1 = self.tmp / 'v2', self.tmp / 'v1'

    def write_binding(self, doc, name=None):
        path = self.root / 'bindings' / f"{name or f'{doc['run_id']}-{doc['run_attempt']}'}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(ev.canonical(doc))
        return path

    def test_layout(self):
        self.assertEqual(g1.read_evidence_root(self.root, self.v1), g1.Evidence.build())
        b1, b2 = BY_ID['R01']['evidence']['bindings']
        self.write_binding(b1)
        (self.root / 'bundles' / '24000000001-1').mkdir(parents=True)
        (self.root / 'bundles' / '24000000001-1' / 'run.json').write_bytes(b'{}\n')
        x = g1.read_evidence_root(self.root, self.v1)
        self.assertEqual((x.bindings, x.foreign_paths), ((b1,), ()))
        self.assertEqual(x.bundles[0]['bundle_verified'], False)  # unverifiable bundle: never repaired
        self.assertTrue(reg.valid(x.bundles[0], 'bundle_projection'))
        self.write_binding(b2, '24000000009-1')                     # sidecar under another run's name
        (self.root / 'bindings' / '24000000003-1.json').write_bytes(ev.compact(b2).encode())  # not canonical
        (self.root / 'bundles' / 'x-1').mkdir()
        (self.root / 'README.md').write_text('x')
        (self.root / 'bindings' / 'nested').mkdir()
        x = g1.read_evidence_root(self.root, self.v1)
        self.assertEqual(set(x.foreign_paths), {'bindings/24000000009-1.json', 'bindings/24000000003-1.json',
                                                'bundles/x-1', 'README.md', 'bindings/nested'})

    def test_symlink_is_foreign(self):
        (self.root / 'bundles').mkdir(parents=True)
        try:
            os.symlink(self.tmp, self.root / 'bundles' / '1-1', target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest('symlinks unavailable')
        self.assertIn('bundles/1-1', g1.read_evidence_root(self.root, self.v1).foreign_paths)

    def test_v1_root_keys(self):
        (self.v1 / '.attempts' / '5-1').mkdir(parents=True)
        (self.v1 / '6-2').mkdir()
        (self.v1 / 'attempts.json').write_bytes(ev.canonical({'schema': 'delsk.oracle.attempts.v1', 'attempts': [
            {'measurement_identity_sha256': 'a' * 64, 'run_id': 7, 'run_attempt': 1}]}))
        self.assertEqual(g1.read_evidence_root(self.root, self.v1).v1_root_keys, ((5, 1), (6, 2), (7, 1)))
        (self.v1 / 'attempts.json').write_bytes(b'{"broken": ')
        self.assertEqual(g1.read_evidence_root(self.root, self.v1).foreign_paths, (self.v1.as_posix(),))


@unittest.skipUnless(sys.platform.startswith('linux'), 'synthetic bundle needs the Linux runner (shim codecs)')
class BundleProjection(unittest.TestCase):
    """bundle_projection = v1 attempt_record over a real verified (synthetic smoke) bundle + series projection."""

    def bundle(self, tmp, sha):
        import io
        from contextlib import redirect_stderr, redirect_stdout
        import oracle_run as orun
        import test_oracle_runner as tr
        if not (tmp / 'syn').exists():
            orun.synthetic(tmp / 'syn')
        env = {**tr.ENV, 'GITHUB_SHA': sha, 'GITHUB_WORKFLOW_SHA': sha}
        tools, conformance = tr.shim_tools(tmp / f'tools-{sha[0]}')
        ctx = orun.prepare('smoke', tools, conformance, tmp / 'syn', env)
        evidence, private = tmp / f'evidence-{sha[0]}', tmp / f'private-{sha[0]}'
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            orun.execute(ctx, tmp / 'syn' / 'store', evidence, private, env)
            ev.finalize(evidence, private)
        return ev.bundle(evidence, tmp / f'results-{sha[0]}')

    def test_projection_of_verified_bundle(self):
        tmp = Path(tempfile.mkdtemp(prefix='v2-bundle-'))
        self.addCleanup(shutil.rmtree, tmp, True)
        first_bundle, second = self.bundle(tmp, 'f' * 40), self.bundle(tmp, 'e' * 40)
        self.assertEqual(ev.verify(first_bundle), [])
        self.assertEqual(ev.verify(second), [])
        p, q = g1.bundle_projection(first_bundle), g1.bundle_projection(second)
        record = ev.attempt_record(first_bundle)
        self.assertTrue(p['bundle_verified'] and reg.valid(p, 'bundle_projection'))
        self.assertEqual((p['run_status'], p['cost_projection_sha256'], p['conformance']),
                         (record['run_status'], record['cost_projection_sha256'], record['conformance']))
        self.assertEqual(p['run']['sha'], 'f' * 40)
        if p['run_status'] == 'COMPLETE':
            # series projection is source-independent where the v1 cost projection is not (contract 7.4)
            self.assertNotEqual(p['cost_projection_sha256'], q['cost_projection_sha256'])
            self.assertEqual(p['series_projection_sha256'], q['series_projection_sha256'])
        renamed = first_bundle.parent / '99-1'
        shutil.copytree(first_bundle, renamed)
        self.assertFalse(g1.bundle_projection(renamed)['bundle_verified'])  # name != run.json run key
        (first_bundle / 'summary.json').write_bytes(b'{}\n')
        self.assertFalse(g1.bundle_projection(first_bundle)['bundle_verified'])


if __name__ == '__main__':
    unittest.main()
