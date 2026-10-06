"""DELSK-003A: integrity of the frozen provenance/G1 contract delsk.oracle-contract.v4.

v4 is the v3 text (contract-v3.md, pinned by freeze-v3.json) with the substitutions of contract-v4.md section 0.2 and
the activation of section 2. Offline, synthetic and payload-free: no registry, no provider call, no corpus bytes. This
module is the normative definition of the two derivations of contract-v4 section 1 and checks them byte for byte:

    schemas-v4.json          = D4(schemas-v3.json)
    registry-vectors-v4.json = T4(registry-vectors-v3.json)

T4 is the substitution of section 0.2 with every correct digest remapped, so every v3 outcome (verdict, blockers up to
the renamed activation code, classes, violations, unbound attempts, series) is preserved; R01-R25, XC01-XC05, SI01-SI05
and PM01-PM20 keep their ids. It also checks that freeze-v4 pins the v4 files, the unchanged v3 base text (which pins
v2) and the unchanged v1 measurement layer. Unlike the v1 and v3 tests it asserts nothing about the state of the working
tree (evidence root, transition record): those exist by design once v4 is active (contract-v4 0.1).
"""
import copy
import hashlib
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = HERE.parent
ROOT = WORK.parent
ORACLE = WORK / 'oracle'
sys.path[:0] = [str(WORK / 'tools'), str(HERE)]
import oracle_eval as ev
import test_oracle_contract_v3 as v3   # frozen v3 test: its helpers are part of the v3 base text

V3, V4 = 'delsk.oracle-contract.v3', 'delsk.oracle-contract.v4'
FREEZE_V3_PATH = ORACLE / 'freeze-v3.json'
FREEZE_V3 = ev.parse_doc(FREEZE_V3_PATH.read_bytes())
SCHEMAS_V3 = ev.parse_doc((ORACLE / 'schemas-v3.json').read_bytes())
VECTORS_V3 = ev.parse_doc((ORACLE / 'registry-vectors-v3.json').read_bytes())
FREEZE_PATH = ORACLE / 'freeze-v4.json'
FREEZE = ev.parse_doc(FREEZE_PATH.read_bytes()) if FREEZE_PATH.exists() else None
SCHEMAS_PATH, VECTORS_PATH = ORACLE / 'schemas-v4.json', ORACLE / 'registry-vectors-v4.json'
SCHEMAS = ev.parse_doc(SCHEMAS_PATH.read_bytes()) if SCHEMAS_PATH.exists() else None
VECTORS = ev.parse_doc(VECTORS_PATH.read_bytes()) if VECTORS_PATH.exists() else None

# --- contract-v4 section 0.2: substitutions of exact string values ----------------------------------------------------

REGISTRY_REF_V3, REGISTRY_REF_V4 = 'refs/heads/delsk/registry-v3', 'refs/heads/delsk/registry-v4'
RESULTS_V3, RESULTS_V4 = '.work/results/DELSK-003-ORACLE-V3/', '.work/results/ORACLE-G1-V4/'
TRANSITION_V3, TRANSITION_V4 = '.work/oracle/series-transition.json', '.work/oracle/series-transition-v4.json'
SUBSTITUTIONS = {V3: V4, REGISTRY_REF_V3: REGISTRY_REF_V4, RESULTS_V3: RESULTS_V4, 'V3_NOT_ACTIVE': 'V4_NOT_ACTIVE'}
SCHEMAS_DESCRIPTION = (
    'delsk.oracle-contract.v4 provenance/G1 layer: closed schemas (contract-v4.md; D4(schemas-v3.json), '
    'test_oracle_contract_v4.py). Keywords are the subset of the v1 validator oracle_eval.schema_errors; patterns end '
    'with (?![\\s\\S]) = end of string in ECMA-262 and Python.')
VECTORS_DESCRIPTION = (
    'Normative reference vectors of delsk.oracle-contract.v4 (contract-v4.md section 1): T4(registry-vectors-v3.json), '
    'R01-R25 and PM01-PM20 with the v3 outcomes. Synthetic only: no natural corpus, no real registry. Genesis '
    'g1_freeze_sha256 is synthetic; the test core does not check it (production does). Expected records are test '
    'records (authority null, TEST_ONLY_PASS for SCIENTIFIC_PASS).')
CODES = {k: {SUBSTITUTIONS.get(c, c) for c in v} for k, v in v3.CODES.items()}
without, cases, environment = v3.without, v3.cases, v3.environment


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def substitute(value):
    if isinstance(value, dict):
        return {k: substitute(v) for k, v in value.items()}
    if isinstance(value, list):
        return [substitute(v) for v in value]
    return SUBSTITUTIONS.get(value, value) if isinstance(value, str) else value


# --- D4: schemas-v4 = D4(schemas-v3) (contract-v4 section 1) ----------------------------------------------------------

def derive_schemas(schemas_v3):
    s = substitute(copy.deepcopy(schemas_v3))
    s['$id'] = 'delsk.oracle.schemas.v4'
    s['description'] = SCHEMAS_DESCRIPTION
    return s


# --- T4: registry-vectors-v4 = T4(registry-vectors-v3) (contract-v4 section 1) ---------------------------------------

class Transform:
    """Digest remapping as T of contract-v3 4.2: INDEX maps the old digest of every v3 object whose self digest is
    correct (genesis: Hc; entry, transition: their own field) to the object; new(old) is Hc of the transformed object.
    A digest that is not the correct digest of such an object (a deliberately broken value) is kept literally."""

    def __init__(self, doc):
        self.index, self.memo = {}, {}
        for case in cases(doc):
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


def build_vectors(doc_v3):
    t = Transform(doc_v3)
    return {**t.value(without(doc_v3, 'description')), 'description': VECTORS_DESCRIPTION}, t


class Freeze(unittest.TestCase):
    def test_record_layers(self):
        self.assertEqual(FREEZE['schema'], 'delsk.oracle-contract.freeze.v4')
        self.assertEqual(FREEZE['contract_id'], V4)
        self.assertEqual(FREEZE['layering'], {'measurement_contract': 'delsk.oracle-contract.v1',
                                              'base_text': V3, 'g1_provenance_contract': V4})
        self.assertEqual((FREEZE['status'], FREEZE['natural_measurements'], FREEZE['g1'], FREEZE['implementation']),
                         ('FROZEN_ON_MERGE', 'NOT_RUN', 'NOT_RUN', 'NOT_ACTIVE'))

    def test_measurement_layer_is_v1_unchanged(self):
        self.assertEqual(FREEZE['measurement_layer'], FREEZE_V3['measurement_layer'])
        self.assertEqual(FREEZE['measurement_layer_sha256'], sha(ORACLE / 'freeze.json'))
        self.assertEqual(FREEZE['measurement_layer_sha256'],
                         'c56fc053b103cecd38446b3791db104a12b9fafabacdfc6b71f6f23c0bf7f729')
        for name, digest in FREEZE['measurement_layer']['files'].items():
            with self.subTest(name):
                self.assertEqual(sha(ROOT / name), digest)

    def test_base_text_is_v3_unchanged(self):
        base = FREEZE['base_layer']
        self.assertEqual(base['contract_id'], V3)
        self.assertEqual(base['freeze_path'], '.work/oracle/freeze-v3.json')
        self.assertEqual(base['freeze_sha256'], sha(FREEZE_V3_PATH))
        self.assertEqual(base['freeze_sha256'], '39dede91e9ed6e12d298f5bd72f9d94fda9e0ac5c92f7a478815d210a0eb1c85')
        self.assertEqual(base['files'], FREEZE_V3['provenance_layer']['files'])
        for layer in (base['files'], FREEZE_V3['base_layer']['files']):
            for name, digest in layer.items():
                with self.subTest(name):
                    self.assertEqual(sha(ROOT / name), digest)

    def test_provenance_layer_files(self):
        files = FREEZE['provenance_layer']['files']
        self.assertEqual(set(files), {'.work/oracle/contract-v4.md', '.work/oracle/schemas-v4.json',
                                      '.work/oracle/registry-vectors-v4.json',
                                      '.work/tests/test_oracle_contract_v4.py'})
        for name, digest in files.items():
            with self.subTest(name):
                self.assertEqual(sha(ROOT / name), digest)
        self.assertEqual(FREEZE['provenance_layer_sha256'], ev.hc(files))

    def test_contract_states_layering_substitutions_and_activation(self):
        text = (ORACLE / 'contract-v4.md').read_text(encoding='utf-8')
        for needle in (V4, 'measurement_contract   = delsk.oracle-contract.v1',
                       'g1_provenance_contract = delsk.oracle-contract.v4',
                       'base_text              = delsk.oracle-contract.v3', 'DELSK-003A PROTOCOL V4 FROZEN',
                       'V4 IMPLEMENTATION NOT_ACTIVE', FREEZE['measurement_layer_sha256'],
                       FREEZE['base_layer']['freeze_sha256'], REGISTRY_REF_V4, RESULTS_V4, TRANSITION_V4,
                       'V4_NOT_ACTIVE', 'delsk.oracle.v4-activation.v1', '.work/oracle/activation-v4.json',
                       'R01–R25', 'PM01–PM20', 'XC01–XC05', 'MISSING ⇒ NOT_PASSED'):
            self.assertIn(needle, text)

    def test_v4_paths_are_outside_the_frozen_state_checks(self):
        # contract-v4 0.1: the v1 test forbids .work/results/DELSK-003*, the v2 and v3 tests forbid their results
        # roots and .work/oracle/series-transition.json. The v4 paths are none of them.
        self.assertFalse(RESULTS_V4.removeprefix('.work/results/').startswith('DELSK-003'))
        self.assertNotIn(TRANSITION_V4, (TRANSITION_V3,))
        self.assertNotIn(RESULTS_V4, ('.work/results/DELSK-003-ORACLE-V2/', RESULTS_V3))


class Derivations(unittest.TestCase):
    def test_schemas_are_d4_of_v3(self):
        self.assertEqual(SCHEMAS, derive_schemas(SCHEMAS_V3))
        self.assertEqual(SCHEMAS_PATH.read_bytes(), ev.canonical(SCHEMAS))

    def test_vectors_are_t4_of_v3(self):
        self.assertEqual(VECTORS, build_vectors(VECTORS_V3)[0])
        self.assertEqual(VECTORS_PATH.read_bytes(), ev.canonical(VECTORS))

    def test_t4_preserves_every_outcome_and_fault(self):
        doc, t = build_vectors(VECTORS_V3)
        old_cases, new_cases = cases(VECTORS_V3), cases(doc)
        self.assertEqual([c['id'] for c in old_cases], [c['id'] for c in new_cases])
        for old, new in zip(old_cases, new_cases):
            with self.subTest(old['id']):
                self.assertEqual(v3.Vectors.chain_faults(new), v3.Vectors.chain_faults(old))
                self.assertEqual(new['provider'], old['provider'])
                self.assertEqual(new['environment_override'], old['environment_override'])
                for xo, xn in zip(old['expect'], new['expect'], strict=True):
                    ro, rn = xo['record'], xn['record']
                    self.assertEqual(xn['core_verdict'], xo['core_verdict'])
                    self.assertEqual(rn['g1_contract'], V4)
                    self.assertEqual(rn['blockers'], [SUBSTITUTIONS.get(b, b) for b in ro['blockers']])
                    self.assertEqual([(a['class'], a['violations']) for a in rn['attempts']],
                                     [(a['class'], a['violations']) for a in ro['attempts']])
                    self.assertEqual(rn['unbound_attempts'], ro['unbound_attempts'])
                    self.assertEqual(rn['series'], ro['series'])
        self.assertTrue(t.index)
        for old in t.index:
            self.assertNotEqual(t.new(old), old)
        text = ev.canonical(doc).decode()
        for gone in (f'"{V3}"', f'"{REGISTRY_REF_V3}"', '"V3_NOT_ACTIVE"'):
            self.assertNotIn(gone, text)
        self.assertEqual([m['id'] for m in doc['mutants']], [m['id'] for m in VECTORS_V3['mutants']])
        self.assertEqual([(x['id'], x['expected']) for x in doc['external_checkpoint_vectors']],
                         [(x['id'], x['expected']) for x in VECTORS_V3['external_checkpoint_vectors']])
        self.assertEqual(doc['science_identity_vectors'], VECTORS_V3['science_identity_vectors'])
        self.assertEqual(doc['environment'], VECTORS_V3['environment'])


class Schemas(unittest.TestCase):
    def test_v4_constants_and_fail_closed(self):
        d = SCHEMAS['$defs']
        for name in ('attempt_binding', 'g1_record', 'registry_entry', 'registry_genesis', 'registry_vectors',
                     'series_transition'):
            self.assertEqual(d[name]['properties']['g1_contract']['const'], V4, name)
        self.assertEqual(d['registry_genesis']['properties']['registry_ref']['const'], REGISTRY_REF_V4)
        self.assertEqual(d['authority']['properties']['registry_ref']['const'], REGISTRY_REF_V4)
        self.assertEqual(d['authority']['properties']['results_root']['const'], RESULTS_V4)
        self.assertEqual(set(d['code']['enum']), set().union(*CODES.values()))
        case = cases(VECTORS)[0]
        entry, record = case['registry']['entries'][0], case['expect'][0]['record']
        binding, genesis = case['evidence']['bindings'][0], case['registry']['genesis']

        def errors(value, name):
            return ev.schema_errors(value, d[name], SCHEMAS)
        for label, name, value in (
                ('v3 entry', 'registry_entry', {**entry, 'g1_contract': V3}),
                ('v3 genesis', 'registry_genesis', {**genesis, 'g1_contract': V3}),
                ('v3 registry ref', 'registry_genesis', {**genesis, 'registry_ref': REGISTRY_REF_V3}),
                ('v3 binding', 'attempt_binding', {**binding, 'g1_contract': V3}),
                ('v3 record', 'g1_record', {**record, 'g1_contract': V3}),
                ('v3 activation code', 'g1_record', {**record, 'blockers': ['V3_NOT_ACTIVE']})):
            with self.subTest(label):
                self.assertTrue(errors(value, name))
        for name, value in (('registry_entry', entry), ('g1_record', record), ('attempt_binding', binding),
                            ('registry_genesis', genesis)):
            self.assertEqual(errors(value, name), [], name)


class Vectors(unittest.TestCase):
    def errors(self, value, name):
        return ev.schema_errors(value, SCHEMAS['$defs'][name], SCHEMAS)

    def test_document(self):
        self.assertEqual(self.errors(VECTORS, 'registry_vectors'), [])
        self.assertEqual([v['id'] for v in VECTORS['vectors']], [f'R{n:02d}' for n in range(1, 26)])
        self.assertEqual([m['id'] for m in VECTORS['mutants']], [f'PM{n:02d}' for n in range(1, 21)])

    def test_registries_and_records(self):
        mapping = {'SCIENTIFIC_PASS': 'TEST_ONLY_PASS'}
        for case in cases(VECTORS):
            with self.subTest(case['id']):
                faults = v3.Vectors.chain_faults(case)
                self.assertEqual(faults == set(), case['registry_fault'] is None)
                entries = case['registry']['entries']
                for b in case['evidence']['bindings']:
                    self.assertEqual(ev.hc(without(b, 'binding_sha256')), b['binding_sha256'])
                for x in case['expect']:
                    r = x['record']
                    self.assertEqual(self.errors(r, 'g1_record'), [])
                    self.assertEqual(ev.hc(without(r, 'record_sha256')), r['record_sha256'])
                    self.assertEqual(r['verdict'], mapping.get(x['core_verdict'], x['core_verdict']))
                    if x['core_verdict'] in CODES:
                        self.assertLessEqual(set(r['blockers']), CODES[x['core_verdict']])
                    if x['core_verdict'] != 'NO_VERDICT':
                        self.assertEqual(r['genesis_sha256'], ev.hc(case['registry']['genesis']))
                        self.assertEqual([a['entry_sha256'] for a in r['attempts']],
                                         [e['entry_sha256'] for e in entries])


if __name__ == '__main__':
    unittest.main()
