"""DELSK-003A C1-A gate 1: frozen v1/v2 bytes are unchanged and nothing is activated.

Runs before the v2 implementation tests. Hashes are spelled out here (not read from the freeze records) so that an
edit of a freeze record together with the file it pins is caught as well. Offline; reads no natural byte.
"""
import gzip
import hashlib
import sys
import unittest
from pathlib import Path

WORK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORK / 'tools'))
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
        for files in (v1['files'], v2['measurement_layer']['files'], v2['provenance_layer']['files']):
            for name, digest in files.items():
                self.assertEqual(FROZEN[name.removeprefix('.work/')], digest, name)
        self.assertEqual(v2['measurement_layer_sha256'], FROZEN['oracle/freeze.json'])
        self.assertEqual(v2['provenance_layer_sha256'], ev.hc(v2['provenance_layer']['files']))
        self.assertEqual(reg.G1_FREEZE_SHA256, FROZEN['oracle/freeze-v2.json'])
        self.assertEqual(v1['bindings']['corpus_lock_sha256'], ev.sha256(gzip.decompress(
            (WORK / 'corpus/pilot-v1/corpus-lock.json.gz').read_bytes())))
        for key, name in (('candidate_lock_sha256', 'corpus/e1/candidate-lock.json'),
                          ('seal_sha256', 'corpus/e1/seal.json'), ('protocol_sha256', 'protocol.md'),
                          ('codec_lock_sha256', 'oracle/codec-lock.json')):
            self.assertEqual(v1['bindings'][key], FROZEN[name], key)
        self.assertEqual((v2['status'], v2['implementation'], v2['g1'], v2['natural_measurements']),
                         ('FROZEN_ON_MERGE', 'NOT_ACTIVE', 'NOT_RUN', 'NOT_RUN'))

    def test_v2_tooling_is_outside_the_v1_code_manifest(self):
        for module in (reg, g1):
            self.assertNotIn(Path(module.__file__).name, ev.CODE_FILES)  # contract 6: never changes a science identity


class NotActivated(unittest.TestCase):
    def test_no_registry_genesis_transition_or_v2_evidence(self):
        self.assertFalse((WORK / 'results' / 'DELSK-003-ORACLE-V2').exists())
        self.assertFalse((WORK / 'oracle' / 'series-transition.json').exists())
        self.assertFalse(list(WORK.rglob('genesis.json')))
        self.assertIsNone(g1.ACTIVATION_RECORD)

    def test_c0_natural_path_stays_closed(self):
        with self.assertRaises(oracle_pilot.PilotError) as blocked:
            oracle_pilot.require_dispatch_history()
        self.assertEqual(blocked.exception.failure_class, 'DISPATCH_HISTORY_UNVERIFIED')
        workflow = (WORK.parent / '.github/workflows/oracle-pilot.yml').read_text(encoding='utf-8')
        self.assertNotIn('delsk/registry', workflow)
        self.assertNotIn('contents: write', workflow)


if __name__ == '__main__':
    unittest.main()
