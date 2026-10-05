"""DELSK-003A: integrity of the frozen provenance/G1 contract delsk.oracle-contract.v3.

v3 is the v2 text (contract-v2.md, pinned by freeze-v2.json) with the substitutions and replacements of contract-v3.md.
Offline, synthetic and payload-free: no registry, no provider call, no corpus bytes. This module is the normative
definition of the two derivations of contract-v3 section 4 and checks them byte for byte:

    schemas-v3.json        = D(schemas-v2.json)
    registry-vectors-v3.json = T(registry-vectors.json) + R25 + PM13-PM17

It also checks that freeze-v3 pins the v3 files, the unchanged v2 base text and the unchanged v1 measurement layer;
that T preserves every v2 outcome (reference PRE predicates of v2 and v3 agree on every R01-R24 observation); that each
R25 case is its base case with only the named provider observations replaced and the base expectation; and the same
internal consistency of the vector document as the v2 test. It does not implement or run G1 v3.
"""
import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = HERE.parent
ROOT = WORK.parent
ORACLE = WORK / 'oracle'
sys.path[:0] = [str(WORK / 'tools')]
import oracle_eval as ev

V2, V3 = 'delsk.oracle-contract.v2', 'delsk.oracle-contract.v3'
FREEZE_V1 = ev.parse_doc((ORACLE / 'freeze.json').read_bytes())
FREEZE_V2_PATH = ORACLE / 'freeze-v2.json'
FREEZE_V2 = ev.parse_doc(FREEZE_V2_PATH.read_bytes())
FREEZE_PATH = ORACLE / 'freeze-v3.json'
FREEZE = ev.parse_doc(FREEZE_PATH.read_bytes()) if FREEZE_PATH.exists() else None
SCHEMAS_V2 = ev.parse_doc((ORACLE / 'schemas-v2.json').read_bytes())
VECTORS_V2 = ev.parse_doc((ORACLE / 'registry-vectors.json').read_bytes())
SCHEMAS_PATH, VECTORS_PATH = ORACLE / 'schemas-v3.json', ORACLE / 'registry-vectors-v3.json'
SCHEMAS = ev.parse_doc(SCHEMAS_PATH.read_bytes()) if SCHEMAS_PATH.exists() else None
VECTORS = ev.parse_doc(VECTORS_PATH.read_bytes()) if VECTORS_PATH.exists() else None

# --- contract-v3 section 0.2: substitutions of exact string values ----------------------------------------------------

REGISTRY_REF_V2, REGISTRY_REF_V3 = 'refs/heads/delsk/registry', 'refs/heads/delsk/registry-v3'
RESULTS_V2, RESULTS_V3 = '.work/results/DELSK-003-ORACLE-V2/', '.work/results/DELSK-003-ORACLE-V3/'
OBSERVATION_V1, OBSERVATION_V2 = 'delsk.oracle.provider-observation.v1', 'delsk.oracle.provider-observation.v2'
SUBSTITUTIONS = {V2: V3, REGISTRY_REF_V2: REGISTRY_REF_V3, RESULTS_V2: RESULTS_V3, OBSERVATION_V1: OBSERVATION_V2,
                 'V2_NOT_ACTIVE': 'V3_NOT_ACTIVE'}
ROLES_V3 = ['bind', 'boundary', 'provider', 'other']
SCHEMAS_DESCRIPTION = (
    'delsk.oracle-contract.v3 provenance/G1 layer: closed schemas (contract-v3.md; D(schemas-v2.json), '
    'test_oracle_contract_v3.py). Keywords are the subset of the v1 validator oracle_eval.schema_errors; patterns end '
    'with (?![\\s\\S]) = end of string in ECMA-262 and Python.')
VECTORS_DESCRIPTION = (
    'Normative reference vectors of delsk.oracle-contract.v3 (contract-v3.md section 4): R01-R24 = T(registry-vectors.'
    'json), R25 = real GitHub Actions job shapes over R08/R10/R12, PM01-PM17. Synthetic only: no natural corpus, no '
    'real registry. Genesis g1_freeze_sha256 is synthetic; the test core does not check it (production does). Expected '
    'records are test records (authority null, TEST_ONLY_PASS for SCIENTIFIC_PASS).')
SELF_DIGESTS = ('entry_sha256', 'transition_sha256', 'binding_sha256', 'record_sha256')
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
                   'KAT_NOT_VERIFIED', 'V3_NOT_ACTIVE'},
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def without(doc, key):
    return {k: v for k, v in doc.items() if k != key}


def substitute(value):
    """Section 0.2 on one JSON value: every string equal to a left-hand side becomes the right-hand side."""
    if isinstance(value, dict):
        return {k: substitute(v) for k, v in value.items()}
    if isinstance(value, list):
        return [substitute(v) for v in value]
    return SUBSTITUTIONS.get(value, value) if isinstance(value, str) else value


# --- D: schemas-v3 = D(schemas-v2) (contract-v3 section 4.1) ----------------------------------------------------------

def derive_schemas(schemas_v2):
    s = substitute(copy.deepcopy(schemas_v2))
    s['$id'] = 'delsk.oracle.schemas.v3'
    s['description'] = SCHEMAS_DESCRIPTION
    s['$defs']['provider_step']['properties']['role']['enum'] = list(ROLES_V3)
    d = s['$defs']
    d['mutant']['properties']['id']['pattern'] = '^PM(0[1-9]|1[0-7])' + END
    d['vector']['properties']['id']['pattern'] = '^R(0[1-9]|1[0-9]|2[0-5])' + END
    case_id = '^R(0[1-9]|1[0-9]|2[0-5])(\\.[a-i])?' + END
    d['vector_case']['properties']['id']['pattern'] = case_id
    d['mutant']['properties']['killed_by']['items']['pattern'] = case_id
    return s


# --- T: R01-R24 of v3 = T(R01-R24 of v2) (contract-v3 section 4.2) ----------------------------------------------------

class Transform:
    """Digest remapping. INDEX maps the old digest of every v2 object whose self digest is correct (genesis: Hc;
    entry, transition: their own field) to the object; new(old) is Hc of the transformed object. A digest that is not
    the correct digest of such an object (a deliberately broken value) is kept literally, so every fault survives."""

    def __init__(self, doc):
        self.index, self.memo = {}, {}
        for case in (c for v in doc['vectors'] for c in v['cases']):
            genesis = case['registry']['genesis']
            self.index[ev.hc(genesis)] = (genesis, None)
            for e in case['registry']['entries']:
                if e['transition'] is not None and e['transition']['transition_sha256'] == ev.hc(
                        without(e['transition'], 'transition_sha256')):
                    self.index[e['transition']['transition_sha256']] = (e['transition'], 'transition_sha256')
                if e['entry_sha256'] == ev.hc(without(e, 'entry_sha256')):
                    self.index[e['entry_sha256']] = (e, 'entry_sha256')

    def new(self, old):
        if old not in self.memo:
            obj, key = self.index[old]
            self.memo[old] = ev.hc(self.value(obj if key is None else without(obj, key)))
        return self.memo[old]

    def value(self, x):
        """Substitutions, digest remapping, and a fresh self digest for bindings and records whose v2 digest held."""
        if isinstance(x, dict):
            out = {k: self.value(v) for k, v in x.items()}
            for key in ('binding_sha256', 'record_sha256'):
                if key in x and x[key] == ev.hc(without(x, key)):
                    out[key] = ev.hc(without(out, key))
            return out
        if isinstance(x, list):
            return [self.value(v) for v in x]
        if isinstance(x, str):
            return self.new(x) if x in self.index else SUBSTITUTIONS.get(x, x)
        return x


def transform_vectors(doc_v2):
    t = Transform(doc_v2)
    doc = {**t.value(without(doc_v2, 'description')), 'description': VECTORS_DESCRIPTION}
    return doc, t


# --- R25: real GitHub Actions job shapes (contract-v3 section 4.3) ----------------------------------------------------

def step(number, role, conclusion):
    """Normalized step as GitHub reports it: started unless never reached (skipped) or still queued (None)."""
    return {'number': number, 'role': role, 'started': conclusion not in ('skipped', None), 'conclusion': conclusion}


# Real register job: Set up job, anonymous source fetch, optional hold (skipped), register, Complete job.
REGISTER_JOB = {'name': 'register', 'started': True, 'conclusion': 'success',
                'steps': [step(1, 'other', 'success'), step(2, 'other', 'success'), step(3, 'other', 'skipped'),
                          step(4, 'other', 'success'), step(5, 'provider', 'success')]}


def measure_job(conclusion, *workflow, provider='success'):
    """Real measure job of the reviewed shape: 1 Set up job, 2 named checkout, 3 hold or admission, 4 bind, 5 binding
    sidecar, 6 last step before the boundary, 7 boundary, 8 a workflow step after the boundary, then the provider steps
    14 Post <checkout> and 15 Complete job. workflow = conclusions of steps 3-8."""
    roles = ('other', 'bind', 'other', 'other', 'boundary', 'other')
    steps = [step(1, 'other', 'success'), step(2, 'other', 'success')]
    steps += [step(n, role, c) for n, role, c in zip(range(3, 9), roles, workflow)]
    steps += [step(14, 'provider', provider), step(15, 'provider', provider)]
    return {'name': 'measure', 'started': True, 'conclusion': conclusion, 'steps': steps}


A2, C1 = (24000000001, 2), (24000000003, 1)
R25 = (
    # id, base case, replaced run key, measure job, description
    ('R25.a', 'R08.a', C1, measure_job('failure', 'skipped', 'success', 'success', 'failure', 'skipped', 'skipped'),
     'C stopped before B on real GitHub: bind and sidecar succeeded, the last step before the boundary failed, '
     'boundary and the workflow step after it skipped; provider steps Post <checkout> and Complete job ran -> PRE'),
    ('R25.b', 'R10.a', C1, measure_job('failure', 'skipped', 'success', 'success', 'failure', 'skipped', 'success'),
     'as R25.a, but a step after the boundary that is not in the closed provider set started (a workflow step, a '
     'renamed provider step or a post step of a post-boundary action) -> not PRE, MISSING'),
    ('R25.c', 'R10.a', C1, measure_job('success', 'skipped', 'success', 'success', 'skipped', 'success', 'success'),
     'C crossed B on real GitHub (boundary succeeded), nothing retained; provider steps ran -> MISSING'),
    ('R25.d', 'R12.a', A2, measure_job('failure', 'skipped', 'failure', 'skipped', 'skipped', 'skipped', 'skipped'),
     'failed-job rerun (RA,2) on real GitHub: register job reused, bind refused, boundary skipped, provider steps ran '
     '-> PRE-proven, not an unbound attempt'),
    ('R25.e', 'R12.b', A2, measure_job('failure', 'skipped', 'failure', 'skipped', 'skipped', 'success', 'success'),
     'failed-job rerun (RA,2) without entry crossed B (implementation defect); provider steps ran -> unbound attempt'),
    ('R25.f', 'R08.b', C1, {'name': 'measure', 'started': True, 'conclusion': 'cancelled', 'steps': []},
     'C cancelled while the measure job waited for a runner: GitHub reports it completed/cancelled with no steps '
     '-> PRE'),
    ('R25.g', 'R08.a', C1, measure_job('cancelled', 'cancelled', 'skipped', 'skipped', 'skipped', 'skipped', 'skipped'),
     'C cancelled after register, during the hold before bind: bind..boundary skipped, provider steps ran -> PRE'),
    ('R25.h', 'R10.a', C1, measure_job('cancelled', 'skipped', 'success', 'success', 'skipped', 'cancelled', 'skipped'),
     'C cancelled after the boundary started (boundary completed/cancelled) -> not PRE, MISSING'),
    ('R25.i', 'R10.a', C1, {'name': 'measure', 'started': True, 'conclusion': 'failure', 'steps': []},
     'C measure job failed with no steps reported (incomplete provider data) -> not PRE, MISSING'),
)

MUTANTS_V3 = (
    {'id': 'PM13', 'defect': 'every step after the boundary is exempt, whatever its role',
     'killed_by': ['R25.b'], 'survives_as': 'a started workflow step after B is hidden and the entry becomes PRE'},
    {'id': 'PM14', 'defect': 'provider steps are not exempt (the v2 rule of section 8.3 item 4)',
     'killed_by': ['R25.a', 'R25.d', 'R25.g'],
     'survives_as': 'PRE is never provable on real provider data; a failed-job rerun stopped before B is unbound'},
    {'id': 'PM15', 'defect': 'a cancelled measure job without steps is not treated as never started',
     'killed_by': ['R25.f'], 'survives_as': 'cancelling a queued measure job loses the PRE proof'},
    {'id': 'PM16', 'defect': 'every cancelled measure job is treated as never started',
     'killed_by': ['R25.h'], 'survives_as': 'cancelling after the boundary started yields PRE'},
    {'id': 'PM17', 'defect': 'every measure job without steps is treated as never started, whatever its conclusion',
     'killed_by': ['R25.i'], 'survives_as': 'incomplete provider data (no steps) yields PRE'},
)


def r25_case(base, cid, key, measure, description):
    case = copy.deepcopy(base)
    case.update(id=cid, description=description)
    replaced = 0
    for o in case['provider']:
        if (o['run_id'], o['run_attempt']) == key:
            o['run']['jobs'] = [copy.deepcopy(REGISTER_JOB), copy.deepcopy(measure)]
            replaced += 1
    assert replaced == 1, cid
    return case


def build_vectors(doc_v2):
    doc, _ = transform_vectors(doc_v2)
    by = {c['id']: c for v in doc['vectors'] for c in v['cases']}
    cases = [r25_case(by[base], cid, key, measure, text) for cid, base, key, measure, text in R25]
    doc['vectors'].append({'id': 'R25', 'title': 'Real GitHub Actions job shapes (provider steps, cancellation)',
                           'cases': cases})
    doc['mutants'] = doc['mutants'] + [dict(m) for m in MUTANTS_V3]
    return doc


# --- reference predicates of section 8.3 item 4 (v2 text and v3 replacement), for the outcome-preservation proof -----

def _measure(observation):
    run = observation['run']
    if run is None or run['status'] != 'completed':
        return False, None
    names = [j['name'] for j in run['jobs']]
    if not set(names) <= {'register', 'measure'} or names.count('measure') > 1:
        return False, None
    jobs = [j for j in run['jobs'] if j['name'] == 'measure']
    return True, jobs[0] if jobs else None


def pre_v2(observation):
    ok, m = _measure(observation)
    if not ok or m is None or not m['started']:
        return ok
    b = [s for s in m['steps'] if s['role'] == 'boundary']
    return len(b) == 1 and not any(s['started'] for s in m['steps'] if s['number'] >= b[0]['number'])


def pre_v3(observation):
    ok, m = _measure(observation)
    if not ok or m is None or not m['started'] or (m['conclusion'] == 'cancelled' and m['steps'] == []):
        return ok
    b = [s for s in m['steps'] if s['role'] == 'boundary']
    return len(b) == 1 and not any(s['started'] for s in m['steps']
                                   if s['number'] >= b[0]['number'] and s['role'] != 'provider')


# --- checks -----------------------------------------------------------------------------------------------------------

def cases(doc):
    return [c for v in doc['vectors'] for c in v['cases']]


def environment(doc, case):
    env = dict(doc['environment'])
    env.update(case['environment_override'] or {})
    return env


def science(mi):
    return {**without(mi, 'measured_source_sha'), 'schema': 'delsk.oracle.science-identity.v1'}


class Freeze(unittest.TestCase):
    def test_record_layers(self):
        self.assertEqual(FREEZE['schema'], 'delsk.oracle-contract.freeze.v3')
        self.assertEqual(FREEZE['contract_id'], V3)
        self.assertEqual(FREEZE['layering'], {'measurement_contract': 'delsk.oracle-contract.v1',
                                              'base_text': V2, 'g1_provenance_contract': V3})
        self.assertEqual((FREEZE['status'], FREEZE['natural_measurements'], FREEZE['g1'], FREEZE['implementation']),
                         ('FROZEN_ON_MERGE', 'NOT_RUN', 'NOT_RUN', 'NOT_ACTIVE'))

    def test_measurement_layer_is_v1_unchanged(self):
        self.assertEqual(FREEZE['measurement_layer'], FREEZE_V2['measurement_layer'])
        self.assertEqual(FREEZE['measurement_layer_sha256'], sha(ORACLE / 'freeze.json'))
        self.assertEqual(FREEZE['measurement_layer_sha256'],
                         'c56fc053b103cecd38446b3791db104a12b9fafabacdfc6b71f6f23c0bf7f729')
        for name, digest in FREEZE_V1['files'].items():
            with self.subTest(name):
                self.assertEqual(sha(ROOT / name), digest)

    def test_base_text_is_v2_unchanged(self):
        base = FREEZE['base_layer']
        self.assertEqual(base['contract_id'], V2)
        self.assertEqual(base['freeze_path'], '.work/oracle/freeze-v2.json')
        self.assertEqual(base['freeze_sha256'], sha(FREEZE_V2_PATH))
        self.assertEqual(base['freeze_sha256'], 'd8e3c33a8eeaed7c112189b98bd8bd7f7d2a422aa8efca6733528738f2a34b57')
        self.assertEqual(base['files'], FREEZE_V2['provenance_layer']['files'])
        for name, digest in base['files'].items():
            with self.subTest(name):
                self.assertEqual(sha(ROOT / name), digest)

    def test_provenance_layer_files(self):
        files = FREEZE['provenance_layer']['files']
        self.assertEqual(set(files), {'.work/oracle/contract-v3.md', '.work/oracle/schemas-v3.json',
                                      '.work/oracle/registry-vectors-v3.json',
                                      '.work/tests/test_oracle_contract_v3.py'})
        for name, digest in files.items():
            with self.subTest(name):
                self.assertEqual(sha(ROOT / name), digest)
        self.assertEqual(FREEZE['provenance_layer_sha256'], ev.hc(files))
        self.assertNotIn('.work/oracle/activation-c1b-log.md', files)

    def test_contract_states_layering_and_status(self):
        text = (ORACLE / 'contract-v3.md').read_text(encoding='utf-8')
        for needle in (V3, 'measurement_contract   = delsk.oracle-contract.v1',
                       'g1_provenance_contract = delsk.oracle-contract.v3',
                       'base_text              = delsk.oracle-contract.v2', 'DELSK-003A PROTOCOL V3 FROZEN',
                       'V3 IMPLEMENTATION NOT_ACTIVE', FREEZE['measurement_layer_sha256'],
                       FREEZE['base_layer']['freeze_sha256'], REGISTRY_REF_V3, RESULTS_V3, OBSERVATION_V2,
                       'Complete job', 'MISSING ⇒ NOT_PASSED'):
            self.assertIn(needle, text)
        for needle in ('R01–R24', 'R01–R25', 'PM01–PM12', 'PM01–PM17', 'XC01–XC05'):
            self.assertIn(needle, text)
        for m in MUTANTS_V3:
            self.assertIn(m['id'], text)
        for cid, *_ in R25:
            self.assertIn(cid, text)

    def test_no_v3_evidence_or_registry_exists(self):
        self.assertFalse((WORK / 'results' / 'DELSK-003-ORACLE-V3').exists())
        self.assertFalse((ORACLE / 'series-transition.json').exists())


class Derivations(unittest.TestCase):
    def test_schemas_are_d_of_v2(self):
        self.assertEqual(SCHEMAS, derive_schemas(SCHEMAS_V2))
        self.assertEqual(SCHEMAS_PATH.read_bytes(), ev.canonical(SCHEMAS))

    def test_vectors_are_t_of_v2_plus_r25(self):
        self.assertEqual(VECTORS, build_vectors(VECTORS_V2))
        self.assertEqual(VECTORS_PATH.read_bytes(), ev.canonical(VECTORS))

    def test_t_keeps_every_v2_fault_and_remaps_every_correct_digest(self):
        doc, t = transform_vectors(VECTORS_V2)
        old_cases, new_cases = cases(VECTORS_V2), cases(doc)
        self.assertEqual([c['id'] for c in old_cases], [c['id'] for c in new_cases])
        for old, new in zip(old_cases, new_cases):
            with self.subTest(old['id']):
                self.assertEqual(Vectors.chain_faults(new), Vectors.chain_faults(old))
                self.assertEqual([x['core_verdict'] for x in new['expect']], [x['core_verdict'] for x in old['expect']])
                for xo, xn in zip(old['expect'], new['expect']):
                    ro, rn = xo['record'], xn['record']
                    self.assertEqual(rn['g1_contract'], V3)
                    self.assertEqual(rn['blockers'], ro['blockers'])
                    self.assertEqual([(a['class'], a['violations']) for a in rn['attempts']],
                                     [(a['class'], a['violations']) for a in ro['attempts']])
                    self.assertEqual(rn['unbound_attempts'], ro['unbound_attempts'])
                    self.assertEqual(rn['series'], ro['series'])
                    if ro['genesis_sha256'] is not None:
                        self.assertNotEqual(rn['genesis_sha256'], ro['genesis_sha256'])
        self.assertTrue(t.index)
        for old in t.index:
            self.assertNotEqual(t.new(old), old)
        text = ev.canonical(doc).decode()
        self.assertNotIn(V2, text)
        self.assertNotIn(f'"{REGISTRY_REF_V2}"', text)
        self.assertNotIn(OBSERVATION_V1, text)
        self.assertEqual([(x['id'], x['expected']) for x in doc['external_checkpoint_vectors']],
                         [(x['id'], x['expected']) for x in VECTORS_V2['external_checkpoint_vectors']])
        self.assertEqual(doc['science_identity_vectors'], VECTORS_V2['science_identity_vectors'])
        self.assertEqual(doc['environment'], VECTORS_V2['environment'])

    def test_t_preserves_outcomes(self):
        # v3 changes only section 8.3 item 4. Every v2 observation has no provider role and no cancelled measure job
        # without steps, so both predicates agree on all of them and every R01-R24 record keeps its classes.
        for case in cases(VECTORS_V2):
            for o in case['provider']:
                with self.subTest(case['id'], key=(o['run_id'], o['run_attempt'])):
                    self.assertEqual(pre_v3(o), pre_v2(o))

    def test_r25_changes_only_the_named_observation(self):
        by_v3 = {c['id']: c for c in cases(transform_vectors(VECTORS_V2)[0])}
        by = {c['id']: c for c in cases(VECTORS)}
        for cid, base, key, measure, _ in R25:
            with self.subTest(cid):
                case, ref = by[cid], by_v3[base]
                self.assertEqual(without(without(without(case, 'id'), 'description'), 'provider'),
                                 without(without(without(ref, 'id'), 'description'), 'provider'))
                self.assertEqual(case['expect'], ref['expect'])
                changed = [o for o, r in zip(case['provider'], ref['provider']) if o != r]
                self.assertEqual([(o['run_id'], o['run_attempt']) for o in changed], [key])
                self.assertEqual(changed[0]['run']['jobs'], [REGISTER_JOB, measure])

    def test_r25_intent_by_reference_predicates(self):
        by = {c['id']: c for c in cases(VECTORS)}
        new_pre = {'R25.a', 'R25.d', 'R25.f', 'R25.g'}
        for cid, base, key, _, _ in R25:
            o = next(o for o in by[cid]['provider'] if (o['run_id'], o['run_attempt']) == key)
            with self.subTest(cid):
                self.assertEqual(pre_v3(o), cid in new_pre)
                self.assertFalse(pre_v2(o))  # every R25 shape is a v2 non-PRE: v3 differs exactly on new_pre
        expect = {'R25.a': 'PRE', 'R25.b': 'MISSING', 'R25.c': 'MISSING', 'R25.f': 'PRE', 'R25.g': 'PRE',
                  'R25.h': 'MISSING', 'R25.i': 'MISSING'}
        for cid, cls in expect.items():
            attempts = by[cid]['expect'][0]['record']['attempts']
            self.assertEqual(next(a['class'] for a in attempts if (a['run_id'], a['run_attempt']) == C1), cls, cid)
        self.assertEqual(by['R25.d']['expect'][0]['record']['unbound_attempts'], [])
        self.assertEqual([(u['run_id'], u['run_attempt']) for u in by['R25.e']['expect'][0]['record'][
            'unbound_attempts']], [A2])

    def test_reference_predicates_on_recorded_github_responses(self):
        # The real smoke runs of 2026-10-05 (tests/fixtures), normalized with the v2 step names of that workflow and
        # the provider steps of its checkout: stop/cancel before B and the refused failed-job rerun are v3 PRE and
        # were v2 non-PRE; the crossing is neither.
        path = HERE / 'fixtures' / 'github-actions-smoke-2026-10-05.json'  # recorded once; pinned below
        self.assertEqual(sha(path), '4d4c4c2a16e0f26f429d64abeb0128f34701c56255f70349ca2c6cb06150a6a9')
        fixture = json.loads(path.read_text())
        names = {'Bind registry entry before the measurement boundary (contract v2 bind)': 'bind',
                 'Measurement boundary (contract v2 boundary)': 'boundary', 'Complete job': 'provider',
                 'Post Run actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1': 'provider'}
        responses, base = fixture['responses'], '/repos/definitely-stable/Shift-lab/actions/runs/'
        expected = {'stop-before-boundary': True, 'rerun-all': True, 'rerun-failed': True, 'cross-boundary': False,
                    'cancel-before-register': True, 'cancel-after-register': True}
        for scenario, (run_id, attempt) in fixture['scenarios'].items():
            jobs = responses[f'{base}{run_id}/attempts/{attempt}/jobs?per_page=100&page=1']['jobs']
            run = responses[f'{base}{run_id}/attempts/{attempt}']

            def started(x):
                return x['status'] in ('in_progress', 'completed') and x['conclusion'] != 'skipped'
            o = {'run': {'status': run['status'], 'jobs': [
                {'name': j['name'], 'started': started(j), 'conclusion': j['conclusion'],
                 'steps': [{'number': s['number'], 'role': names.get(s['name'], 'other'), 'started': started(s),
                            'conclusion': s['conclusion']} for s in j['steps']]} for j in jobs]}}
            with self.subTest(scenario):
                self.assertEqual(pre_v3(o), expected[scenario])
                self.assertFalse(pre_v2(o))


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
        d = SCHEMAS['$defs']
        for where, node in self.walk(d):
            if where == '#' or where.endswith('/properties'):
                continue
            with self.subTest(where):
                self.assertLessEqual(set(node), SUPPORTED)
            if node.get('type') == 'object' and 'properties' in node:
                self.assertIs(node.get('additionalProperties'), False, where)
            if 'pattern' in node:
                self.assertTrue(node['pattern'].startswith('^') and node['pattern'].endswith(END), where)

    def test_v3_constants_and_fail_closed(self):
        d = SCHEMAS['$defs']
        for name in ('attempt_binding', 'g1_record', 'registry_entry', 'registry_genesis', 'registry_vectors',
                     'series_transition'):
            self.assertEqual(d[name]['properties']['g1_contract']['const'], V3, name)
        self.assertEqual(d['registry_genesis']['properties']['registry_ref']['const'], REGISTRY_REF_V3)
        self.assertEqual(d['authority']['properties']['registry_ref']['const'], REGISTRY_REF_V3)
        self.assertEqual(d['authority']['properties']['results_root']['const'], RESULTS_V3)
        self.assertEqual(d['provider_observation']['properties']['schema']['const'], OBSERVATION_V2)
        self.assertEqual(d['provider_step']['properties']['role']['enum'], ROLES_V3)
        self.assertEqual(set(d['code']['enum']), set().union(*CODES.values()))
        case = cases(VECTORS)[0]
        entry, record = case['registry']['entries'][0], case['expect'][0]['record']
        binding, genesis = case['evidence']['bindings'][0], case['registry']['genesis']

        def errors(value, name):
            return ev.schema_errors(value, d[name], SCHEMAS)
        for label, name, value in (
                ('v2 entry', 'registry_entry', {**entry, 'g1_contract': V2}),
                ('v2 genesis', 'registry_genesis', {**genesis, 'g1_contract': V2}),
                ('v2 registry ref', 'registry_genesis', {**genesis, 'registry_ref': REGISTRY_REF_V2}),
                ('v2 binding', 'attempt_binding', {**binding, 'g1_contract': V2}),
                ('v2 record', 'g1_record', {**record, 'g1_contract': V2}),
                ('v2 activation code', 'g1_record', {**record, 'blockers': ['V2_NOT_ACTIVE']}),
                ('v1 observation tag', 'provider_observation', {**case['provider'][0], 'schema': OBSERVATION_V1}),
                ('unknown role', 'provider_step', {'number': 1, 'role': 'cleanup', 'started': True,
                                                    'conclusion': 'success'})):
            with self.subTest(label):
                self.assertTrue(errors(value, name))
        for name, value in (('registry_entry', entry), ('g1_record', record), ('attempt_binding', binding),
                            ('registry_genesis', genesis)):
            self.assertEqual(errors(value, name), [], name)


class Vectors(unittest.TestCase):
    @staticmethod
    def chain_faults(case):
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

    def errors(self, value, name):
        return ev.schema_errors(value, SCHEMAS['$defs'][name], SCHEMAS)

    def test_document(self):
        self.assertEqual(self.errors(VECTORS, 'registry_vectors'), [])
        self.assertEqual([v['id'] for v in VECTORS['vectors']], [f'R{n:02d}' for n in range(1, 26)])
        ids = [c['id'] for c in cases(VECTORS)]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual([m['id'] for m in VECTORS['mutants']], [f'PM{n:02d}' for n in range(1, 18)])
        for m in VECTORS['mutants']:
            self.assertLessEqual(set(m['killed_by']), set(ids), m['id'])

    def test_registries(self):
        for case in cases(VECTORS):
            with self.subTest(case['id']):
                sources = {s['sha']: s['measurement_identity'] for s in environment(VECTORS, case)['sources']}
                faults = self.chain_faults(case)
                if case['registry_fault'] is None:
                    self.assertEqual(faults, set())
                else:
                    self.assertIn(case['registry_fault'], faults)
                for e in case['registry']['entries']:
                    mi = sources[e['measured_source_sha']]
                    self.assertEqual(ev.hc(mi), e['measurement_identity_sha256'])
                    self.assertEqual(ev.hc(science(mi)), e['science_identity_sha256'])
                    if e['transition'] is not None:
                        t = e['transition']
                        self.assertEqual(ev.hc(without(t, 'transition_sha256')), t['transition_sha256'])
                for b in case['evidence']['bindings']:
                    self.assertEqual(ev.hc(without(b, 'binding_sha256')), b['binding_sha256'])
                for o in case['provider']:
                    self.assertEqual(self.errors(o, 'provider_observation'), [])

    def test_expected_records(self):
        mapping = {'SCIENTIFIC_PASS': 'TEST_ONLY_PASS'}
        for case in cases(VECTORS):
            entries = case['registry']['entries']
            for x in case['expect']:
                r = x['record']
                with self.subTest(case['id'], identity=x['measurement_identity_sha256'][:12]):
                    self.assertEqual(self.errors(r, 'g1_record'), [])
                    self.assertEqual(ev.hc(without(r, 'record_sha256')), r['record_sha256'])
                    self.assertEqual(r['verdict'], mapping.get(x['core_verdict'], x['core_verdict']))
                    self.assertIsNone(r['authority'])
                    self.assertEqual(r['main_head_sha'], environment(VECTORS, case)['main_head'])
                    verdict = x['core_verdict']
                    if verdict in CODES:
                        self.assertLessEqual(set(r['blockers']), CODES[verdict])
                    if verdict == 'NO_VERDICT':
                        continue
                    self.assertEqual(r['genesis_sha256'], ev.hc(case['registry']['genesis']))
                    self.assertEqual(r['registry_head'], {'sequence': len(entries),
                                                          'entry_sha256': entries[-1]['entry_sha256']})
                    self.assertEqual([a['entry_sha256'] for a in r['attempts']], [e['entry_sha256'] for e in entries])

    def test_external_checkpoint_vectors(self):  # remapped digests keep every prefix relation (T is injective)
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

    def test_vectors_are_not_vacuous(self):
        classes = {a['class'] for c in cases(VECTORS) for x in c['expect'] for a in x['record']['attempts']}
        self.assertEqual(classes, {'PRE', 'BUNDLE', 'MISSING'})
        roles = {s['role'] for c in cases(VECTORS) for o in c['provider'] if o['run']
                 for j in o['run']['jobs'] for s in j['steps']}
        self.assertEqual(roles, set(ROLES_V3))
        self.assertEqual({x['record']['verdict'] for c in cases(VECTORS) for x in c['expect']} & {'PASS'}, set())


if __name__ == '__main__':
    unittest.main()
