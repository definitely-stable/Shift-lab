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


@contextlib.contextmanager
def admitted(directory):
    """initialize with the live v3 admission stubbed (no network) and its file kept inside the test directory."""
    doc = {'schema': pilot.ADMISSION_SCHEMA, 'stub': True}
    with patch.object(pilot, 'verify_v3_activation', return_value=doc), \
            patch.object(pilot, 'v3_admission_file', lambda out: Path(directory) / pilot.ADMISSION_FILE):
        yield


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
            with admitted(t):
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
            with admitted(t):
                pilot.initialize(out, ENV)
            admission = Path(t) / 'admission'
            admission.write_text(json.dumps({'admitted': True, 'within_budget': True, 'accounting_complete': True}))
            with patch.object(pilot, 'require_v3_active'), patch.object(pilot, 'resource_precheck'), \
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
            with admitted(t):
                pilot.initialize(out, ENV)
            admission = Path(t) / 'admission'
            admission.write_text(json.dumps({'admitted': True, 'within_budget': True, 'accounting_complete': True}))
            with patch.object(pilot, 'require_v3_active'), patch.object(pilot, 'resource_precheck'), \
                    patch.object(pilot.build, 'main', return_value=0), \
                    patch.object(pilot.runner, 'conformance_record', return_value=({'verdict': 'FAIL'}, {})), \
                    patch.object(materializer, 'materialize_store', side_effect=AssertionError('natural fetch')):
                self.assertEqual(pilot.worker(out, work, admission,
                                            {**ENV, 'ATTEMPT_ARTIFACT_ID': '123'}), 1)
            self.assertEqual(json.loads((out / 'attempt.json').read_bytes())['failure_class'], 'CONFORMANCE_FAILED')

    def test_direct_runner_gate_refuses_without_v3_activation(self):
        import oracle_g1_v2 as g1
        with patch.object(g1, 'ACTIVATION_RECORD', None), \
                patch.object(pilot, 'measurement_identity', side_effect=AssertionError('gate reached')):
            with self.assertRaises(pilot.PilotError) as blocked:
                pilot.validate_gate({**ENV, 'ATTEMPT_ARTIFACT_ID': '123'}, 'unused', 'unused')
        self.assertEqual(blocked.exception.failure_class, 'V3_NOT_ACTIVE')

    def test_worker_without_v3_admission_never_builds_or_fetches(self):
        import oracle_materialize as materializer
        with tempfile.TemporaryDirectory() as t:
            out, work = Path(t) / 'out', Path(t) / 'work'
            out.mkdir(); work.mkdir()
            admission = Path(t) / 'admission'
            admission.write_text(json.dumps({'admitted': True, 'within_budget': True, 'accounting_complete': True}))
            with patch.object(pilot, 'v3_admission_file', lambda out: Path(t) / pilot.ADMISSION_FILE), \
                    patch.object(pilot.build, 'main', side_effect=AssertionError('codec build')), \
                    patch.object(materializer, 'load_natural', side_effect=AssertionError('natural fetch')):
                self.assertEqual(pilot.main(['worker', str(out), str(work), str(admission)],
                                            {**ENV, 'ATTEMPT_ARTIFACT_ID': '123'}), 1)
            self.assertEqual(json.loads((out / 'attempt.json').read_bytes())['failure_class'], 'V3_NOT_ACTIVE')


@unittest.skipUnless(pilot is not None, 'production pilot gate is missing')
class V3Admission(unittest.TestCase):
    """Contract-v3 5 replaces the C0 refusal: live admission before the boundary (initialize), offline re-check of
    that admission after it (worker, runner gate). Exercised on the real Git history of this checkout with the live
    activation stubbed; every unprovable fact refuses with V3_NOT_ACTIVE."""

    def setUp(self):
        import oracle_g1_v2 as g1
        self.g1 = g1
        git = lambda *a: subprocess.run(['git', '-C', str(WORK.parent), *a], capture_output=True, text=True)
        self.head = git('rev-parse', 'HEAD').stdout.strip()
        self.parent = git('rev-parse', '--verify', '--quiet', 'HEAD^1').stdout.strip() or None
        self.workflow = pilot._workflow_sha256(self.head)
        self.assertRegex(self.workflow or '', '^[0-9a-f]{64}$')
        self.env = {**ENV, 'GITHUB_SHA': self.head, 'SOURCE_SHA': self.head, 'GITHUB_WORKFLOW_SHA': self.head}
        self.record = 'd' * 64

    def active(self, main=None, workflow=None):
        return (main or self.head, ({'infra': {'path': 'x', 'sha256': 'e' * 64}},
                                    {'workflow_sha256': workflow or self.workflow}))

    def verify(self, active=None, raises=None, record='default'):
        import oracle_registry_git as transport
        side = {'side_effect': raises} if raises else {'return_value': active}
        with patch.object(self.g1, 'ACTIVATION_RECORD', self.record if record == 'default' else record), \
                patch.object(transport, 'active_activation', **side) as call:
            return pilot.verify_v3_activation(self.env), call

    def refused(self, fn):
        with self.assertRaises(pilot.PilotError) as blocked:
            fn()
        self.assertEqual(blocked.exception.failure_class, 'V3_NOT_ACTIVE')

    def test_live_admission_of_an_active_v3(self):
        doc, call = self.verify(self.active())
        call.assert_called_once_with(self.record)
        self.assertEqual(doc, {'schema': pilot.ADMISSION_SCHEMA, 'repository': pilot.REPOSITORY, 'run_id': 71,
                               'run_attempt': 1, 'measured_source_sha': self.head, 'main_head_sha': self.head,
                               'activation_record': self.record, 'infra_sha256': 'e' * 64,
                               'workflow_sha256': self.workflow})

    def test_live_admission_refusals(self):
        self.refused(lambda: self.verify(None))                                      # activation does not verify
        self.refused(lambda: self.verify(raises=RuntimeError('provider down')))      # unobtainable facts
        self.refused(lambda: self.verify(self.active(workflow='0' * 64)))            # other oracle-pilot.yml bytes
        if self.parent:
            self.refused(lambda: self.verify(self.active(main=self.parent)))         # source not on the main
        import oracle_registry_git as transport
        with patch.object(transport, 'active_activation', side_effect=AssertionError('read without a record')):
            self.refused(lambda: self.verify(record=None))                           # no activation record

    def test_initialize_refuses_before_bind_without_activation(self):
        import oracle_registry_git as transport
        with tempfile.TemporaryDirectory() as t:
            out = Path(t) / 'out'
            with patch.object(self.g1, 'ACTIVATION_RECORD', self.record), \
                    patch.object(transport, 'active_activation', return_value=None), \
                    patch.object(pilot, 'v3_admission_file', lambda out: Path(t) / pilot.ADMISSION_FILE):
                self.assertEqual(pilot.main(['initialize', str(out)], self.env), 1)
            self.assertEqual(json.loads((out / 'attempt.json').read_bytes())['failure_class'], 'V3_NOT_ACTIVE')
            self.assertFalse((Path(t) / pilot.ADMISSION_FILE).exists())

    def test_offline_admission_after_the_boundary(self):
        with tempfile.TemporaryDirectory() as t:
            path = Path(t) / pilot.ADMISSION_FILE
            doc, _ = self.verify(self.active())
            pilot.atomic_json(path, doc)
            with patch.object(self.g1, 'ACTIVATION_RECORD', self.record), \
                    patch('urllib.request.urlopen', side_effect=AssertionError('network after the boundary')):
                pilot.require_v3_active(self.env, path)
                for env in ({**self.env, 'GITHUB_RUN_ATTEMPT': '2'}, {**self.env, 'GITHUB_RUN_ID': '72'},
                            {**self.env, 'GITHUB_SHA': self.parent or '0' * 40}):
                    with self.subTest(env=env):
                        self.refused(lambda: pilot.require_v3_active(env, path))
                with patch.object(pilot, '_workflow_sha256', return_value='0' * 64):
                    self.refused(lambda: pilot.require_v3_active(self.env, path))   # executed workflow changed
                self.refused(lambda: pilot.require_v3_active(self.env, Path(t) / 'absent.json'))
                link = Path(t) / 'link.json'
                link.symlink_to(path)
                self.refused(lambda: pilot.require_v3_active(self.env, link))
                pilot.atomic_json(path, {**doc, 'extra': 1})
                self.refused(lambda: pilot.require_v3_active(self.env, path))
                path.write_bytes(path.read_bytes() + b' ')
                self.refused(lambda: pilot.require_v3_active(self.env, path))          # non-canonical bytes
            pilot.atomic_json(path, doc)
            with patch.object(self.g1, 'ACTIVATION_RECORD', 'f' * 64):
                self.refused(lambda: pilot.require_v3_active(self.env, path))       # another activation record
            with patch.object(self.g1, 'ACTIVATION_RECORD', None):
                self.refused(lambda: pilot.require_v3_active(self.env, path))


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
            out = Path(t) / 'out'
            with admitted(t):
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
        self.assertLess(text.index('id: attempt_record'), text.index('name: Measurement boundary (contract v3 boundary)'))
        self.assertIn('steps.attempt_record.outputs.artifact-id', text)
        self.assertNotIn('private', text.split('path:')[-1])

    def test_pr_smoke_includes_synthetic_supervisor_without_natural_dispatch(self):
        text = (WORK.parent / '.github/workflows/oracle-smoke.yml').read_text()
        self.assertIn('oracle_pilot.py smoke', text)
        self.assertIn('test_oracle_pilot', text)
        self.assertNotIn('oracle_pilot.py run', text)


if __name__ == '__main__':
    unittest.main()
