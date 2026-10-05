"""Slice C0 infrastructure gates. No natural archive or natural encode is used."""
import contextlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

WORK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORK / 'tools'))
try:
    import oracle_pilot as pilot
except ImportError:
    pilot = None

ENV = {'GITHUB_EVENT_NAME': 'workflow_dispatch', 'GITHUB_REPOSITORY': 'definitely-stable/Shift-lab',
       'GITHUB_SHA': 'a' * 40, 'SOURCE_SHA': 'a' * 40, 'GITHUB_WORKFLOW_SHA': 'a' * 40,
       'GITHUB_REF': 'refs/heads/reviewed-pilot',
       'GITHUB_WORKFLOW_REF': 'definitely-stable/Shift-lab/.github/workflows/oracle-pilot.yml@refs/heads/reviewed-pilot',
       'GITHUB_RUN_ID': '71', 'GITHUB_RUN_ATTEMPT': '1', 'RUNNER_ARCH': 'X64', 'RUNNER_OS': 'Linux'}


class Dispatch(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(pilot, 'production pilot gate is missing')

    def test_only_exact_dispatched_commit_and_ref(self):
        pilot.validate_dispatch(ENV)
        for change in ({'GITHUB_EVENT_NAME': 'push'}, {'SOURCE_SHA': 'A' * 40}, {'SOURCE_SHA': 'b' * 40},
                       {'GITHUB_WORKFLOW_SHA': 'b' * 40}, {'RUNNER_ARCH': 'ARM64'},
                       {'GITHUB_REF': 'refs/heads/main'}, {'GITHUB_RUN_ATTEMPT': '0'},
                       {'GITHUB_REPOSITORY': 'someone/else'}, {'SOURCE_SHA': '$(touch stolen)'},
                       {'GITHUB_WORKFLOW_REF': ENV['GITHUB_WORKFLOW_REF'] + '-other'}):
            with self.subTest(change=change), self.assertRaises(pilot.PilotError):
                pilot.validate_dispatch({**ENV, **change})

    def test_identity_before_codecs_equals_frozen_runner_identity(self):
        import oracle_build as build
        import manifests as m
        ident = pilot.measurement_identity(ENV)
        self.assertEqual(ident['phase'], 'pilot')
        self.assertEqual(ident['measured_source_sha'], ENV['SOURCE_SHA'])
        self.assertEqual(ident['oracle_code_sha256'], m.digest(build.code_manifest()))
        self.assertEqual(ident['sealed_splits'], ['evaluation'])
        self.assertEqual(pilot.measurement_identity({**ENV, 'GITHUB_RUN_ID': '72'}), ident)

    def test_admission_refusal_cannot_execute_any_setup(self):
        with tempfile.TemporaryDirectory() as t:
            out, work = Path(t) / 'out', Path(t) / 'work'
            out.mkdir(); work.mkdir()
            pilot.initialize(out, ENV)
            admission = Path(t) / 'admission.json'
            admission.write_text(json.dumps({'admitted': False}))
            with patch.object(pilot, 'run_bounded', side_effect=AssertionError('compute before admission')):
                self.assertEqual(pilot.supervise(out, work, admission, ENV), 1)
            record = json.loads((out / 'attempt.json').read_bytes())
            self.assertEqual(record['admission'], 'REFUSED')

    def test_missing_initial_artifact_receipt_blocks_measurement(self):
        with self.assertRaises(pilot.PilotError):
            pilot.validate_receipt(ENV)
        pilot.validate_receipt({**ENV, 'ATTEMPT_ARTIFACT_ID': '123'})
        for value in ('0', '-1', 'true', '$(echo token)'):
            with self.assertRaises(pilot.PilotError):
                pilot.validate_receipt({**ENV, 'ATTEMPT_ARTIFACT_ID': value})

    def test_codec_build_failure_leaves_attempt_and_never_fetches(self):
        import oracle_materialize as materializer
        with tempfile.TemporaryDirectory() as t:
            out, work = Path(t) / 'out', Path(t) / 'work'
            out.mkdir(); work.mkdir()
            pilot.initialize(out, ENV)
            admission = Path(t) / 'admission'
            admission.write_text(json.dumps({'admitted': True, 'within_budget': True, 'accounting_complete': True}))
            with patch.object(pilot, 'require_dispatch_history'), patch.object(pilot, 'resource_precheck'), \
                    patch.object(pilot.build, 'main', return_value=1), \
                    patch.object(materializer, 'load_natural', side_effect=AssertionError('natural fetch')):
                self.assertEqual(pilot.worker(out, work, admission,
                                            {**ENV, 'ATTEMPT_ARTIFACT_ID': '123'}), 1)
            attempt = json.loads((out / 'attempt.json').read_bytes())
            self.assertEqual(attempt['failure_class'], 'CODEC_BUILD_FAILED')

    def test_c14_failure_never_materializes_natural_store(self):
        import oracle_materialize as materializer
        with tempfile.TemporaryDirectory() as t:
            out, work = Path(t) / 'out', Path(t) / 'work'
            out.mkdir(); work.mkdir()
            pilot.initialize(out, ENV)
            admission = Path(t) / 'admission'
            admission.write_text(json.dumps({'admitted': True, 'within_budget': True, 'accounting_complete': True}))
            with patch.object(pilot, 'require_dispatch_history'), patch.object(pilot, 'resource_precheck'), \
                    patch.object(pilot.build, 'main', return_value=0), \
                    patch.object(pilot.runner, 'conformance_record', return_value=({'verdict': 'FAIL'}, {})), \
                    patch.object(materializer, 'materialize_store', side_effect=AssertionError('natural fetch')):
                self.assertEqual(pilot.worker(out, work, admission,
                                            {**ENV, 'ATTEMPT_ARTIFACT_ID': '123'}), 1)
            self.assertEqual(json.loads((out / 'attempt.json').read_bytes())['failure_class'], 'CONFORMANCE_FAILED')

    def test_natural_path_refuses_unprovable_all_dispatch_history(self):
        with self.assertRaises(pilot.PilotError) as blocked:
            pilot.require_dispatch_history()
        self.assertEqual(blocked.exception.failure_class, 'DISPATCH_HISTORY_UNVERIFIED')

    def test_direct_runner_gate_cannot_bypass_history_blocker(self):
        with patch.object(pilot, 'measurement_identity', side_effect=AssertionError('gate reached')):
            with self.assertRaises(pilot.PilotError) as blocked:
                pilot.validate_gate({**ENV, 'ATTEMPT_ARTIFACT_ID': '123'}, 'unused', 'unused')
        self.assertEqual(blocked.exception.failure_class, 'DISPATCH_HISTORY_UNVERIFIED')


class Safety(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(pilot, 'production supervisor is missing')

    def test_synthetic_supervisor_keeps_actual_smoke_workflow_identity(self):
        smoke_env = {**ENV, 'GITHUB_EVENT_NAME': 'pull_request', 'GITHUB_REF': 'refs/pull/26/merge',
                     'GITHUB_WORKFLOW_REF': 'definitely-stable/Shift-lab/.github/workflows/oracle-smoke.yml@refs/pull/26/merge'}
        # Store verification anchors every ancestor; the workspace is readable on Windows too.
        with tempfile.TemporaryDirectory(dir=WORK) as t, \
                patch.object(pilot.runner, 'prepare', return_value={'identity_sha256': 'c' * 64}), \
                patch.object(pilot.runner, 'execute'), patch.object(pilot, '_finalize', return_value=True):
            out, work = Path(t) / 'out', Path(t) / 'work'
            self.assertEqual(pilot.smoke('unused', 'unused', out, work, smoke_env), 0)
            self.assertEqual(json.loads((out / 'attempt.json').read_bytes())['workflow_ref'],
                             smoke_env['GITHUB_WORKFLOW_REF'])

    def test_relabelled_natural_locks_cannot_enter_smoke(self):
        import gzip
        import manifests as m
        candidate = m.loads_strict((WORK / 'corpus/e1/candidate-lock.json').read_bytes())
        corpus = m.loads_strict(gzip.decompress((WORK / 'corpus/pilot-v1/corpus-lock.json.gz').read_bytes()))
        candidate['schema'], corpus['schema'] = pilot.runner.SYNTHETIC
        corpus_data = m.canonical_bytes(corpus)
        candidate['corpus_lock_sha256'] = pilot.runner.sha256(corpus_data)
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / 'candidate-lock.json').write_bytes(m.canonical_bytes(candidate))
            (root / 'corpus-lock.json').write_bytes(corpus_data)
            freeze = m.loads_strict((WORK / 'oracle/freeze.json').read_bytes())
            with self.assertRaises(pilot.runner.RunError):
                pilot.runner.load_locks('smoke', root, freeze)

    def test_disk_refusal(self):
        usage = type('Usage', (), {'free': 1})()
        with tempfile.TemporaryDirectory() as t, patch.object(pilot.shutil, 'disk_usage', return_value=usage):
            with self.assertRaises(pilot.PilotError) as failure:
                pilot.resource_precheck(Path(t), require_tmpfs=False)
            self.assertEqual(failure.exception.failure_class, 'DISK_ADMISSION_REFUSED')

    def test_pilot_requires_hard_capped_filesystem(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(pilot.PilotError):
                pilot.resource_precheck(Path(t), require_tmpfs=True)

    def test_unknown_debug_files_and_oversized_export_fail_closed(self):
        with tempfile.TemporaryDirectory() as t:
            out = Path(t)
            (out / 'attempt.json').write_bytes(b'{}')
            (out / 'private-cost-debug.log').write_text('HIDDEN_COST_SENTINEL')
            with self.assertRaises(pilot.PilotError):
                pilot.check_export(out)
            (out / 'private-cost-debug.log').unlink()
            with patch.object(pilot, 'ARTIFACT_CAP', 1), self.assertRaises(pilot.PilotError):
                pilot.check_export(out)

    def test_untrusted_exception_is_never_printed_or_persisted(self):
        with tempfile.TemporaryDirectory() as t:
            out = Path(t)
            capture = io.StringIO()
            with patch.object(pilot, 'validate_dispatch', side_effect=ValueError('HIDDEN_COST_SENTINEL')), \
                    contextlib.redirect_stdout(capture), contextlib.redirect_stderr(capture):
                self.assertEqual(pilot.main(['initialize', str(out)], ENV), 1)
            self.assertNotIn('HIDDEN_COST_SENTINEL', capture.getvalue())
            self.assertNotIn(b'HIDDEN_COST_SENTINEL', (out / 'attempt.json').read_bytes())

    def test_upload_failure_has_bounded_machine_evidence(self):
        with tempfile.TemporaryDirectory() as t:
            out = Path(t)
            pilot.initialize(out, ENV)
            self.assertEqual(pilot.main(['finish', str(out), 'failure'], ENV), 0)
            doc = json.loads((out / 'attempt.json').read_bytes())
            self.assertEqual((doc['status'], doc['failure_class']), ('FAILED', 'ARTIFACT_UPLOAD_FAILED'))
            self.assertLess((out / 'attempt.json').stat().st_size, 8192)
            self.assertEqual(pilot.check_export(out), {'attempt.json', 'checksums.sha256'})

    @unittest.skipUnless(sys.platform.startswith('linux'), 'Linux process/resource supervision')
    def test_killed_process_is_classified_and_output_discarded(self):
        with tempfile.TemporaryDirectory() as t:
            result = pilot.run_bounded([sys.executable, '-c',
                'import os; print("HIDDEN_COST_SENTINEL", flush=True); os.kill(os.getpid(),9)'], Path(t),
                5, ENV)
            self.assertEqual(result, 'RUNNER_KILLED')
            self.assertFalse(list(Path(t).glob('*.log')))

    @unittest.skipUnless(sys.platform.startswith('linux'), 'Linux process/resource supervision')
    def test_hard_wall_timeout(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(pilot.run_bounded([sys.executable, '-c', 'import time; time.sleep(600)'],
                                              Path(t), 0.1, ENV), 'PROCESS_WALL_TIMEOUT')


class Workflow(unittest.TestCase):
    def test_dispatch_workflow_security_and_bootstrap(self):
        path = WORK.parent / '.github/workflows/oracle-pilot.yml'
        self.assertTrue(path.exists(), 'manual pilot workflow is missing')
        text = path.read_text()
        self.assertIn('workflow_dispatch:', text)
        self.assertNotRegex(text, r'^  (push|pull_request|schedule|workflow_run):')
        self.assertIn('runs-on: ubuntu-24.04', text)
        self.assertIn('timeout-minutes: 30', text)
        self.assertIn('group: delsk-experimental', text)
        self.assertIn('cancel-in-progress: false', text)
        self.assertIn('contents: read', text)
        self.assertIn('actions: read', text)
        # contract v2 12.2: the only write is the register job's contents: write (oracle_activation_v2 checks it)
        self.assertEqual(text.count(': write'), 1)
        self.assertLess(text.index('contents: write'), text.index('  measure:'))
        self.assertNotIn('secrets.', text)
        self.assertNotIn('github.event.inputs', text)
        self.assertNotIn('${{ inputs.source_sha }}', '\n'.join(
            l for l in text.splitlines() if not l.strip().startswith('SOURCE_SHA:')))
        for action in re.findall(r'uses: ([^\s]+)', text):
            self.assertRegex(action, r'@[0-9a-f]{40}$')
        measure = text.index('  measure:')  # C0 bootstrap order inside the measuring job
        self.assertLess(text.index('id: dispatch_record'), text.index('uses: actions/checkout@', measure))
        self.assertLess(text.index('id: attempt_record'), text.index('name: Measurement boundary (contract v2 boundary)'))
        self.assertIn('steps.attempt_record.outputs.artifact-id', text)
        self.assertNotIn('private', text.split('path:')[-1])

    def test_pr_smoke_includes_synthetic_supervisor_without_natural_dispatch(self):
        text = (WORK.parent / '.github/workflows/oracle-smoke.yml').read_text()
        self.assertIn('oracle_pilot.py smoke', text)
        self.assertIn('test_oracle_pilot', text)
        self.assertNotIn('oracle_pilot.py run', text)


if __name__ == '__main__':
    unittest.main()
