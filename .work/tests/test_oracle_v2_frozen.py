"""DELSK-003A gate 1: frozen v1/v2/v3/v4 bytes are unchanged and nothing is activated beyond the enable record.

Runs before the v4 implementation tests (module names keep the _v2 suffix of the registered-attempt model). Hashes are
spelled out here (not read from the freeze records) so that an edit of a freeze record together with the file it pins
is caught as well. Offline; reads no natural byte.
"""
import gzip
import hashlib
import sys
import unittest
from pathlib import Path

WORK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORK / 'tools'))
import oracle_activation_v2 as activation
import oracle_eval as ev
import oracle_g1_v2 as g1
import oracle_pilot
import oracle_registry_v2 as reg

FROZEN = {
    # measurement layer delsk.oracle-contract.v1 (v1 freeze.json and the files it pins)
    'oracle/freeze.json': 'c56fc053b103cecd38446b3791db104a12b9fafabacdfc6b71f6f23c0bf7f729',
    'oracle/contract.md': 'd3bde26f6abf642dacc1ea8b767c0d3262928a9d27547d0e311c682b542c8387',
    'oracle/codec-lock.json': '9823e4c933c27fb4116bfce5add59ef6e926e43d2f0ebae258d7bb869a38f7b1',
    'oracle/schemas.json': 'bdd46170b426161e7b455cc4b93545de7e46354df1a5fe072c9af46168698124',
    'oracle/known-answer.json': '911eab6897a72fd9bf3cd27bed8ce9733b4da45a2bebc8f974a9a2e3c8fab3d6',
    'tests/oracle_reference.py': 'be84b37e66916b1172a575b842b327a018fbac2c24154b06e6ffef8caaed338f',
    'tests/test_oracle_contract.py': '2b5e60c69829588f502575cf45175e3d13ecc58192ac176cb2e80fb11937d8f1',
    'oracle/conformance.json': '69a95cc87e4731d264bc2873873715dff65d93cb90b3f93114e9afc49179bd1b',
    # provenance layer delsk.oracle-contract.v2 (freeze-v2.json and the files it pins)
    'oracle/freeze-v2.json': 'd8e3c33a8eeaed7c112189b98bd8bd7f7d2a422aa8efca6733528738f2a34b57',
    'oracle/contract-v2.md': '92452fd59150a3957a131fce84f0dd0d311dfb40fdafeb8b22f416016538b677',
    'oracle/schemas-v2.json': '3ee790cf8d9b0a68c553aec673194c3f781f61ed704ee5c43479b0f5a41120b0',
    'oracle/registry-vectors.json': '5aef8456216da54ef4de4363369b92b6dc65ed29c4c46c864c15f198f8473484',
    'tests/test_oracle_contract_v2.py': '5b1d7b104705becb7bc2f8f200ce011c260c0bb07c4a8221391c578a39893f50',
    # provenance layer delsk.oracle-contract.v3 (freeze-v3.json and the files it pins; v2 above is its base text)
    'oracle/freeze-v3.json': '39dede91e9ed6e12d298f5bd72f9d94fda9e0ac5c92f7a478815d210a0eb1c85',
    'oracle/contract-v3.md': '469e8f1487cd24a6c23f9431cd766c1cf7c3208251d44488df9ea87527c28366',
    'oracle/schemas-v3.json': 'b958f9d26708829c29591c35c353f135ee611059298c4d8badb858360877a751',
    'oracle/registry-vectors-v3.json': '0b53aa03f46bcb4be43c59dbb8bad65ebdc16a4d5173c811850cc606491111d4',
    'tests/test_oracle_contract_v3.py': '1bff11dff24ef6b48eb873c6dba5f5462db9b2569573a0e1a5e7e91fa825a584',
    # provenance layer delsk.oracle-contract.v4 (freeze-v4.json and the files it pins; v3 above is its base text)
    'oracle/freeze-v4.json': '9507f045abd13155a20d938381ea0391e9e094f713d18a143c0a136445cbbb61',
    'oracle/contract-v4.md': '3c14a9fd14439ddaa2288c95fc7a01d6dc26633c8fadab1406d9e3facd6a456b',
    'oracle/schemas-v4.json': 'dfd881da9807eb49550449e693dfe3911e14907cfa780baa4019cd5fb70f272b',
    'oracle/registry-vectors-v4.json': '74760dfd5cb6b20151b843beaa149f566eef24fc4c234b8edc170f3a38af2cf2',
    'tests/test_oracle_contract_v4.py': '85b1c944c00cbba5889ef794d87aa80cf21ea6aca77f706600e8fb90e8888d96',
    # corpus / candidate / source / protocol / seal locks bound by the v1 freeze
    'corpus/e1/candidate-lock.json': 'cb16d53b164ff393187e0115bdf31c52ac717a5172fb1e91889b5988ac019d2e',
    'corpus/pilot-v1/corpus-lock.json.gz': '86009552183230ab13f9366684eedb4fcfcea746b25cbbed10ab2aabceb8f56b',
    'corpus/pilot-v1/source-lock.json': '2154224d9b8af255f4f48662b7f03a6b9865c3e976079dbad33c939eb3a5903c',
    'corpus/pilot-v1/freeze.json': '8814ce0221b2b890f1710476da0c1a31771e7528d81cfc3a99ffa10acc88e8da',
    'corpus/e1/seal.json': '0c87fd5c96279c377d6031051d0cf990cb0afc6041212fc973b1ef35a8be73ef',
    'protocol.md': 'a0c518247d111e8ad1294562d65eb34c28da87c7027c009efb64a39e6f4e0038',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FrozenBytes(unittest.TestCase):
    def test_frozen_files_are_byte_identical(self):
        for name, digest in FROZEN.items():
            with self.subTest(name):
                self.assertEqual(sha(WORK / name), digest)

    def test_freeze_records_pin_exactly_these_bytes(self):
        v1 = ev.parse_doc((WORK / 'oracle/freeze.json').read_bytes())
        v2 = ev.parse_doc((WORK / 'oracle/freeze-v2.json').read_bytes())
        v3 = ev.parse_doc((WORK / 'oracle/freeze-v3.json').read_bytes())
        v4 = ev.parse_doc((WORK / 'oracle/freeze-v4.json').read_bytes())
        for files in (v1['files'], v2['measurement_layer']['files'], v2['provenance_layer']['files'],
                      v3['measurement_layer']['files'], v3['base_layer']['files'], v3['provenance_layer']['files'],
                      v4['measurement_layer']['files'], v4['base_layer']['files'], v4['provenance_layer']['files']):
            for name, digest in files.items():
                self.assertEqual(FROZEN[name.removeprefix('.work/')], digest, name)
        self.assertEqual(v2['measurement_layer_sha256'], FROZEN['oracle/freeze.json'])
        self.assertEqual(v2['provenance_layer_sha256'], ev.hc(v2['provenance_layer']['files']))
        self.assertEqual(v3['measurement_layer_sha256'], FROZEN['oracle/freeze.json'])
        self.assertEqual(v3['base_layer']['freeze_sha256'], FROZEN['oracle/freeze-v2.json'])
        self.assertEqual(v3['provenance_layer_sha256'], ev.hc(v3['provenance_layer']['files']))
        self.assertEqual(v4['measurement_layer_sha256'], FROZEN['oracle/freeze.json'])
        self.assertEqual(v4['base_layer']['freeze_sha256'], FROZEN['oracle/freeze-v3.json'])
        self.assertEqual(v4['provenance_layer_sha256'], ev.hc(v4['provenance_layer']['files']))
        self.assertEqual(reg.G1_FREEZE_SHA256, FROZEN['oracle/freeze-v4.json'])
        self.assertEqual(reg.G1_CONTRACT, v4['contract_id'])
        self.assertEqual(v1['bindings']['corpus_lock_sha256'], ev.sha256(gzip.decompress(
            (WORK / 'corpus/pilot-v1/corpus-lock.json.gz').read_bytes())))
        for key, name in (('candidate_lock_sha256', 'corpus/e1/candidate-lock.json'),
                          ('seal_sha256', 'corpus/e1/seal.json'), ('protocol_sha256', 'protocol.md'),
                          ('codec_lock_sha256', 'oracle/codec-lock.json')):
            self.assertEqual(v1['bindings'][key], FROZEN[name], key)
        for freeze in (v2, v3, v4):
            self.assertEqual((freeze['status'], freeze['implementation'], freeze['g1'], freeze['natural_measurements']),
                             ('FROZEN_ON_MERGE', 'NOT_ACTIVE', 'NOT_RUN', 'NOT_RUN'))

    def test_v2_tooling_is_outside_the_v1_code_manifest(self):
        for module in (reg, g1):
            self.assertNotIn(Path(module.__file__).name, ev.CODE_FILES)  # contract 6: never changes a science identity


class NotActivated(unittest.TestCase):
    def test_no_retired_evidence_and_v4_evidence_only_when_active(self):
        # v2 and v3 never retain evidence or a transition record (their frozen tests forbid it, contract-v4 0.1)
        self.assertFalse((WORK / 'results' / 'DELSK-003-ORACLE-V2').exists())
        self.assertFalse((WORK / 'results' / 'DELSK-003-ORACLE-V3').exists())
        self.assertFalse((WORK / 'oracle' / 'series-transition.json').exists())
        self.assertFalse(list(WORK.rglob('genesis.json')))
        # contract-v4 2: the code constant names the enable record by the digest of its exact bytes, or nothing
        record = WORK.parent / activation.ACTIVATION_FILE
        if g1.ACTIVATION_RECORD is None:
            self.assertFalse(record.exists())
            self.assertFalse((WORK.parent / reg.RESULTS_ROOT).exists())
            self.assertFalse((WORK.parent / reg.TRANSITION_FILE).exists())
        else:
            self.assertEqual(ev.sha256(record.read_bytes()), g1.ACTIVATION_RECORD)

    def test_v4_evidence_root_is_well_formed(self):
        # Contract 8.1 offline: only bundles/<run>-<attempt>/ and bindings/<run>-<attempt>.json, every bundle a verified
        # v1 bundle with its binding, no v4 run key in the v1 root. Registry membership is checked live by production.
        root = WORK.parent / reg.RESULTS_ROOT
        if not root.exists():
            self.skipTest('no v4 evidence retained yet')
        evidence = g1.read_evidence_root(root)
        self.assertEqual(evidence.foreign_paths, ())
        bundles = {reg.run_key(b): b for b in evidence.bundles}
        bindings = {reg.run_key(b): b for b in evidence.bindings}
        self.assertLessEqual(set(bundles), set(bindings))
        self.assertFalse(set(bindings) & set(evidence.v1_root_keys))
        for key, bundle in bundles.items():
            self.assertTrue(bundle['bundle_verified'], key)
            self.assertEqual(bundle['measurement_identity_sha256'], bindings[key]['measurement_identity_sha256'], key)
        for binding in bindings.values():
            self.assertTrue(reg.valid(binding, 'attempt_binding'))
            self.assertTrue(reg.self_digest_ok(binding, 'binding_sha256'))

    def test_natural_path_needs_a_verified_v4_admission(self):
        # Contract-v4 2 (contract-v3 5) replaced the C0 refusal: without the admission that step initialize writes after
        # verifying the v4 activation live (before bind and the boundary), the worker and the runner gate refuse.
        with self.assertRaises(oracle_pilot.PilotError) as blocked:
            oracle_pilot.require_v4_active({'GITHUB_SHA': '0' * 40, 'GITHUB_RUN_ID': '1', 'GITHUB_RUN_ATTEMPT': '1'},
                                           WORK / 'no-such-admission.json')
        self.assertEqual(blocked.exception.failure_class, 'V4_NOT_ACTIVE')
        # The only write-capable job is `register`; no registry ref or credential is spelled out in the workflow.
        workflow = (WORK.parent / '.github/workflows/oracle-pilot.yml').read_text(encoding='utf-8')
        self.assertEqual(activation.check_pilot_workflow(workflow), [])
        self.assertNotIn('delsk/registry', workflow)
        self.assertEqual(workflow.count('contents: write'), 1)


if __name__ == '__main__':
    unittest.main()
