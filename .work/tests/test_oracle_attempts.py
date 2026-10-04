"""Slice C0 dispatch inventory/retention: synthetic API only, no pilot execution."""
import copy
import datetime as dt
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import oracle_eval as ev
import oracle_attempts as oa

REPO = 'test/repo'
SHA, ID = 'a' * 40, 'b' * 64
NOW = dt.datetime(2026, 10, 5, 12, tzinfo=dt.timezone.utc)
DATE = '2026-10-05T11:00:00Z'
REF = f'{REPO}/.github/workflows/oracle-pilot.yml@refs/heads/main'


def source(sha, ref):
    return dict(measurement_identity_sha256=ID, measured_source_sha=sha, workflow_sha=sha, workflow_ref=ref)


def run(n, attempts=1, **changes):
    doc = dict(id=n * 10, run_number=n, run_attempt=attempts, event='workflow_dispatch', head_sha=SHA,
               head_branch='main', path='.github/workflows/oracle-pilot.yml', workflow_id=7,
               repository={'full_name': REPO}, head_repository={'full_name': REPO}, created_at=DATE,
               updated_at=DATE, run_started_at=DATE, status='completed', conclusion='success')
    doc.update(changes)
    return doc


class API:
    def __init__(self, runs=(), page_size=100):
        self.runs, self.page_size, self.calls = list(runs), page_size, []
        self.attempts = {(r['id'], a): dict(r, run_attempt=a) for r in self.runs
                         for a in range(1, r['run_attempt'] + 1)}

    def __call__(self, path):
        self.calls.append(path)
        if path.endswith('/actions/workflows/oracle-pilot.yml'):
            return {'id': 7, 'path': '.github/workflows/oracle-pilot.yml', 'created_at': DATE}
        if '/attempts/' in path:
            tail = path.split('/actions/runs/')[1].split('/')
            return copy.deepcopy(self.attempts[int(tail[0]), int(tail[2])])
        page = int(path.rsplit('page=', 1)[1])
        return {'total_count': len(self.runs), 'workflow_runs': copy.deepcopy(
            self.runs[(page - 1) * self.page_size:page * self.page_size])}


def snapshot(runs=()):
    return oa.inventory(API(runs), REPO, source, now=NOW)


def ledger(snap):
    return oa.reconcile(snap, {'schema': 'delsk.oracle.attempts.v1', 'attempts': []})


def record(r, status='COMPLETE', **changes):
    out = dict(identity=ID, phase='pilot', github_run_id=r['id'], run_attempt=1, run_status=status,
               cost_projection_sha256='c' * 64, targets_sha256='d' * 64,
               sealed_commitments_sha256='e' * 64, conformance=True, bundle_verified=True)
    out.update(changes)
    return out


class Inventory(unittest.TestCase):
    def test_all_pages_runs_and_reruns_from_inception(self):
        api = API([run(1, 3), run(2), run(3, event='push')], page_size=1)
        snap = oa.inventory(api, REPO, source, now=NOW)
        self.assertEqual([(a['run_id'], a['run_attempt']) for a in snap['attempts']],
                         [(10, 1), (10, 2), (10, 3), (20, 1)])
        self.assertEqual(len(snap['runs']), 3)
        self.assertTrue(any('page=3' in p for p in api.calls))
        self.assertFalse(any('created=' in p or 'event=' in p for p in api.calls))

    def test_gap_including_deleted_first_run_fails_closed(self):
        for runs in ([run(2)], [run(1), run(3)]):
            with self.subTest(runs=runs), self.assertRaises(oa.AttemptError):
                snapshot(runs)

    def test_attempts_must_exist_and_match_source_workflow(self):
        for field, value in [('head_sha', 'f' * 40), ('workflow_id', 8), ('path', 'other.yml'),
                             ('run_attempt', 2), ('id', 11), ('event', 'push'),
                             ('head_repository', {'full_name': 'attacker/repo'})]:
            api = API([run(1)])
            api.attempts[10, 1][field] = value
            with self.subTest(field=field), self.assertRaises(oa.AttemptError):
                oa.inventory(api, REPO, source, now=NOW)
        api = API([run(1, 2)])
        del api.attempts[10, 1]
        with self.assertRaises(oa.AttemptError):
            oa.inventory(api, REPO, source, now=NOW)

    def test_unknown_or_rebound_source_identity_is_not_omitted(self):
        for resolve in (lambda *_: None, lambda sha, ref: dict(source(sha, ref), workflow_sha='f' * 40),
                        lambda sha, ref: dict(source(sha, ref), workflow_ref=ref + 'x')):
            with self.assertRaises(oa.AttemptError):
                oa.inventory(API([run(1)]), REPO, resolve, now=NOW)

    def test_changed_total_duplicate_and_incomplete_pages(self):
        for mode in ('total', 'duplicate', 'incomplete', 'second_read'):
            api, count = API([run(1), run(2)], page_size=1), [0]
            def get(path):
                doc = api(path)
                if 'workflow_runs' in doc:
                    count[0] += 1
                    if mode == 'total' and count[0] == 2:
                        doc['total_count'] = 3
                    elif mode == 'duplicate' and count[0] == 2:
                        doc['workflow_runs'] = [run(1)]
                    elif mode == 'incomplete' and count[0] == 2:
                        doc['workflow_runs'] = []
                    elif mode == 'second_read' and count[0] >= 3:
                        doc['workflow_runs'][0]['head_sha'] = 'f' * 40
                return doc
            with self.subTest(mode=mode), self.assertRaises(oa.AttemptError):
                oa.inventory(get, REPO, source, now=NOW)

    def test_snapshot_hash_covers_every_observation(self):
        snap = snapshot([run(1)])
        snap['attempts'][0]['conclusion'] = 'failure'
        with self.assertRaises(oa.AttemptError):
            oa.reconcile(snap, {'schema': 'delsk.oracle.attempts.v1', 'attempts': []})


class Ledger(unittest.TestCase):
    def test_append_only_no_delete_rebinding_or_metadata_edit(self):
        snap, base = snapshot([run(1)]), ledger(snapshot([run(1)]))
        newer = oa.reconcile(snapshot([run(1), run(2)]), base, base)
        self.assertEqual(newer['attempts'][:1], base['attempts'])
        for field, value in [('measurement_identity_sha256', 'f' * 64), ('run_id', 11),
                             ('created_at', '2020-01-01T00:00:00Z'), ('workflow_sha', 'f' * 40)]:
            changed = copy.deepcopy(base)
            changed['attempts'][0][field] = value
            with self.subTest(field=field), self.assertRaises(oa.AttemptError):
                oa.audit_ledger(changed, base)
        with self.assertRaises(oa.AttemptError):
            oa.audit_ledger({'schema': 'delsk.oracle.attempts.v1', 'attempts': []}, base)
        with self.assertRaises(oa.AttemptError):
            oa.reconcile(snapshot(), base)
        with self.assertRaises(oa.AttemptError):
            oa.reconcile(snap, dict(base, attempts=base['attempts'] * 2))

    def test_closed_schema_and_no_unknown_identities(self):
        doc = ledger(snapshot([run(1)]))
        for edit in (lambda d: d['attempts'][0].update(extra=True),
                     lambda d: d['attempts'][0].update(run_attempt=True),
                     lambda d: d['attempts'][0].update(measurement_identity_sha256=None)):
            changed = copy.deepcopy(doc)
            edit(changed)
            with self.assertRaises(oa.AttemptError):
                oa.audit_ledger(changed)

    def test_import_snapshot_is_hashed_immutable_and_transactional(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, snap = Path(tmp), snapshot([run(1)])
            oa.import_snapshot(snap, root)
            before = {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            oa.import_snapshot(snap, root)
            self.assertEqual(before, {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()})
            stale = snapshot()
            with self.assertRaises(oa.AttemptError):
                oa.import_snapshot(stale, root)
            self.assertEqual(before, {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()})

    def test_git_base_audit_no_deletion_rebinding_or_snapshot_edits(self):
        snap = snapshot([run(1)])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            oa.import_snapshot(snap, root)
            relative = '.work/results/DELSK-003-ORACLE/'
            base_files = {relative + p.relative_to(root).as_posix(): p.read_bytes()
                          for p in root.rglob('*') if p.is_file()}
            class Result:
                returncode = 0
                def __init__(self, data):
                    self.stdout = data
            def git(argv, **kwargs):
                self.assertNotIn('shell', kwargs)
                if 'ls-tree' in argv:
                    return Result(b'\x00'.join(p.encode() for p in base_files) + b'\x00')
                if 'show' in argv:
                    return Result(base_files[argv[-1].split(':', 1)[1]])
                raise AssertionError(argv)
            with patch.object(oa.subprocess, 'run', side_effect=git):
                oa.audit_git(SHA, root)
                old_snapshot = next((root / '.inventory').glob('*.json'))
                old_snapshot.unlink()
                with self.assertRaises(oa.AttemptError):
                    oa.audit_git(SHA, root)

    def test_absent_initial_results_is_valid_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'not-yet-run'
            class Result:
                returncode, stdout = 0, b''
            with patch.object(oa.subprocess, 'run', return_value=Result()):
                self.assertTrue(oa.audit_git(SHA, root))
            self.assertFalse(root.exists())

    def test_root_audit_failed_sidecars_are_immutable(self):
        snap = snapshot([run(1)])
        with tempfile.TemporaryDirectory() as tmp:
            base, new = Path(tmp) / 'base', Path(tmp) / 'new'
            oa.import_snapshot(snap, base)
            failed = base / '.attempts' / '10-1' / 'attempt.json'
            failed.parent.mkdir(parents=True)
            failed.write_bytes(b'failure witness\n')
            import shutil
            shutil.copytree(base, new)
            (new / '.attempts' / '10-1' / 'attempt.json').unlink()
            with self.assertRaises(oa.AttemptError):
                oa.audit_root(new, base)


class G1(unittest.TestCase):
    def evaluate(self, runs, records, live=False, **kw):
        snap = snapshot(runs)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'attempts.json').write_bytes(ev.canonical(ledger(snap)))
            for rec in records:
                (root / f"{rec['github_run_id']}-{rec['run_attempt']}").mkdir()
                env = dict(GITHUB_REPOSITORY=REPO, GITHUB_RUN_ID=str(rec['github_run_id']),
                           GITHUB_RUN_ATTEMPT=str(rec['run_attempt']), GITHUB_SHA=SHA,
                           GITHUB_WORKFLOW_SHA=SHA, GITHUB_WORKFLOW_REF=REF)
                sidecar = root / '.attempts' / f"{rec['github_run_id']}-{rec['run_attempt']}"
                sidecar.mkdir(parents=True)
                (sidecar / 'attempt.json').write_bytes(ev.canonical(oa.create_attempt(env, ID, now=NOW)))
                (sidecar / 'materialization.json').write_bytes(ev.canonical({'synthetic': True}))
            by_name = {f"{r['github_run_id']}-{r['run_attempt']}": r for r in records}
            with patch.object(ev, 'attempt_record', side_effect=lambda d: by_name[d.name]), \
                    patch.object(oa, 'check_bundle_binding'), patch.object(oa, '_materialization'), \
                    patch.object(oa, '_envelope_receipt'), patch.dict(os.environ, {'GITHUB_REPOSITORY': REPO}):
                return oa.g1_root(ID, root, snapshot=None if live else snap, now=NOW,
                                  get=API(runs), resolve_source=source, **kw)

    def test_A_no_dispatch_is_not_run(self):
        self.assertEqual(self.evaluate([], []), ('NOT_RUN', []))

    def test_B_one_complete_requires_independent_repeat(self):
        self.assertEqual(self.evaluate([run(1)], [record(run(1))]), ('NOT_PASSED', ['REPEAT_MISSING']))

    def test_C_two_identical_independent_runs_pass(self):
        self.assertEqual(self.evaluate([run(1), run(2)], [record(run(1)), record(run(2))]), ('PASS', []))

    def test_D_same_run_rerun_does_not_count(self):
        self.assertEqual(self.evaluate([run(1, 2)], [record(run(1)), record(run(1), run_attempt=2)]),
                         ('NOT_PASSED', ['REPEAT_MISSING']))

    def test_E_invalid_cannot_be_outvoted(self):
        runs = [run(1), run(2), run(3)]
        self.assertEqual(self.evaluate(runs, [record(runs[0], 'INVALID'), *[record(r) for r in runs[1:]]]),
                         ('INVALID', ['RUN_INVALID']))

    def test_F_incomplete_and_bounded_block(self):
        for status in ('INCOMPLETE', 'COMPLETE_WITH_FAILURES'):
            result = self.evaluate([run(1), run(2), run(3)],
                                   [record(run(1), status), record(run(2)), record(run(3))])
            self.assertEqual(result, ('NOT_PASSED', ['RUN_' + status]))

    def test_G_repeat_mismatch_including_sealed_is_invalid(self):
        for field in ('cost_projection_sha256', 'targets_sha256', 'sealed_commitments_sha256'):
            result = self.evaluate([run(1), run(2)], [record(run(1)), record(run(2), **{field: 'f' * 64})])
            self.assertEqual(result, ('INVALID', ['REPEAT_MISMATCH']))

    def test_H_missing_cancelled_timeout_refused_artifacts_block(self):
        for conclusion in ('cancelled', 'timed_out', 'failure', 'success'):
            result = self.evaluate([run(1, conclusion=conclusion), run(2), run(3)],
                                   [record(run(2)), record(run(3))])
            self.assertEqual(result, ('NOT_PASSED', ['ATTEMPT_NOT_RETAINED']))

    def test_I_nonconformance_or_unverified_bundle_blocks(self):
        for change in ({'conformance': False}, {'bundle_verified': False}):
            result = self.evaluate([run(1), run(2)], [record(run(1)), record(run(2), **change)])
            self.assertEqual(result, ('NOT_PASSED', ['CONFORMANCE_OR_BUNDLE', 'REPEAT_MISSING']))

    def test_J_stale_pending_partial_and_unlisted_block(self):
        with self.assertRaises(oa.AttemptError):
            self.evaluate([run(1), run(2)], [record(run(1)), record(run(2))], max_age_seconds=-1)
        self.assertIn('INVENTORY_PENDING', self.evaluate([run(1, status='in_progress', conclusion=None)], [])[1])
        with self.assertRaises(oa.AttemptError):
            self.evaluate([run(1)], [record(run(1)), record(run(2))])

    def test_live_api_cannot_prove_a_never_observed_deleted_tail(self):
        # API history with 1/2 can look exactly like 1/2/3 after 3 was deleted
        # before this inventory's first observation. Re-reading cannot prove it.
        self.assertEqual(self.evaluate([run(1), run(2)], [record(run(1)), record(run(2))], live=True),
                         ('NOT_PASSED', ['DISPATCH_HISTORY_UNVERIFIED']))

    def test_custom_results_root_cannot_bypass_production_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'attempts.json').write_bytes(ev.canonical({'schema': oa.LEDGER_SCHEMA, 'attempts': []}))
            with patch.object(oa, 'g1_root', return_value=('NOT_PASSED', ['DISPATCH_HISTORY_UNVERIFIED'])) as call:
                self.assertEqual(ev.g1_root(ID, root), ('NOT_PASSED', ['DISPATCH_HISTORY_UNVERIFIED']))
                call.assert_called_once_with(ID, root)


class Envelopes(unittest.TestCase):
    def setUp(self):
        self.env = dict(GITHUB_REPOSITORY=REPO, GITHUB_RUN_ID='10', GITHUB_RUN_ATTEMPT='1',
                        GITHUB_SHA=SHA, GITHUB_WORKFLOW_SHA=SHA, GITHUB_WORKFLOW_REF=REF)

    def test_sidecar_closed_machine_failures_and_stable_identity(self):
        doc = oa.create_attempt(self.env, ID, now=NOW)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'attempt.json'
            path.write_bytes(ev.canonical(doc))
            updated = oa.update_attempt(path, 'NOT_ADMITTED', 'admission', 'BUDGET_REFUSED', 'REFUSED', now=NOW)
            self.assertEqual(updated['created_at'], doc['created_at'])
            self.assertEqual(updated['measurement_identity_sha256'], ID)
            with self.assertRaises(oa.AttemptError):
                oa.update_attempt(path, 'FAILED', 'build', 'arbitrary-secret-values', now=NOW)

    def test_dispatch_history_blocker_survives_sidecar_machine_vocabulary(self):
        doc = oa.create_attempt(self.env, ID, status='NOT_ADMITTED', phase='dispatch',
                                failure_class='DISPATCH_HISTORY_UNVERIFIED', admission='REFUSED', now=NOW)
        self.assertEqual(doc['failure_class'], 'DISPATCH_HISTORY_UNVERIFIED')
        self.assertIn(doc['failure_class'], oa.FAILURE_CLASSES)

    def test_synthetic_smoke_sidecar_accepts_only_the_allowlisted_workflow_refs(self):
        prefix = f'{REPO}/.github/workflows/oracle-smoke.yml@'
        for ref in ('refs/pull/26/merge', 'refs/heads/main', 'refs/tags/v1.0.0'):
            env = dict(self.env, GITHUB_WORKFLOW_REF=prefix + ref)
            doc = oa.create_attempt(env, ID, status='READY', phase='synthetic_premeasurement',
                                    admission='ADMITTED', now=NOW)
            self.assertEqual(doc['workflow_ref'], env['GITHUB_WORKFLOW_REF'])
        for ref in ('refs/pull/26/head', 'refs/pull/0/merge', 'refs/heads/', 'refs/heads/main\n',
                    'refs/heads/../main', 'refs/heads/main//other', 'refs/not-a-workflow/main'):
            with self.subTest(ref=ref), self.assertRaises(oa.AttemptError):
                oa.create_attempt(dict(self.env, GITHUB_WORKFLOW_REF=prefix + ref), ID, now=NOW)
        for ref in (f'{REPO}/.github/workflows/oracle-smoke.yml.evil@refs/pull/26/merge',
                    'other/repo/.github/workflows/oracle-smoke.yml@refs/pull/26/merge',
                    f'{REPO}/.github/workflows/other.yml@refs/pull/26/merge'):
            with self.subTest(ref=ref), self.assertRaises(oa.AttemptError):
                oa.create_attempt(dict(self.env, GITHUB_WORKFLOW_REF=ref), ID, now=NOW)

    def test_synthetic_smoke_sidecar_cannot_be_retained_against_a_pilot_dispatch(self):
        snap = snapshot([run(1)])
        ref = f'{REPO}/.github/workflows/oracle-smoke.yml@refs/pull/26/merge'
        doc = oa.create_attempt(dict(self.env, GITHUB_WORKFLOW_REF=ref), ID, status='READY',
                                phase='synthetic_premeasurement', admission='ADMITTED', now=NOW)
        with tempfile.TemporaryDirectory() as tmp:
            root, envelope = Path(tmp) / 'results', Path(tmp) / 'envelope'
            envelope.mkdir()
            (envelope / 'attempt.json').write_bytes(ev.canonical(doc))
            oa.import_snapshot(snap, root)
            with self.assertRaises(oa.AttemptError):
                oa.retain(envelope, root, snapshot=snap)
            self.assertFalse((root / '10-1').exists())
            self.assertFalse((root / '.attempts' / '10-1').exists())

    def test_original_envelope_receipt_checks_separate_normative_and_sidecar_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            sidecar, bundle = Path(tmp) / 'sidecar', Path(tmp) / 'bundle'
            sidecar.mkdir()
            bundle.mkdir()
            (sidecar / 'attempt.json').write_bytes(b'fixed synthetic status\n')
            (bundle / 'pairs.jsonl').write_bytes(b'fixed synthetic rows\n')
            (bundle / 'checksums.sha256').write_bytes(b'normative checksum independent\n')
            names = {'attempt.json': sidecar / 'attempt.json', 'bundle/pairs.jsonl': bundle / 'pairs.jsonl'}
            receipt = ''.join(f'{ev.sha256(p.read_bytes())}  {n}\n' for n, p in sorted(names.items()))
            (sidecar / 'checksums.sha256').write_bytes(receipt.encode())
            oa._envelope_receipt(sidecar, bundle)
            (bundle / 'pairs.jsonl').write_bytes(b'altered\n')
            with self.assertRaises(oa.AttemptError):
                oa._envelope_receipt(sidecar, bundle)

    def test_materialization_provenance_exact_frozen_universe_metadata_only(self):
        import oracle_materialize as materializer
        with patch.object(materializer.materialize, 'fetch', side_effect=AssertionError('natural fetch')):
            candidate, corpus, sources, policy = materializer.load_natural()
            expected = materializer.expected_objects(candidate, corpus)
            required = materializer._required(candidate, corpus)
            self.assertEqual(len(expected), 1549)
            verification = dict(schema='delsk.oracle.store-verification.v1', verified=True, objects=len(expected),
                                object_set_sha256=ev.hc(sorted(expected)), expected_manifest_sha256=ev.hc(expected))
            provenance = dict(schema='delsk.oracle.materialization-provenance.v1', verification=verification,
                              required_occurrences=len(required), required_sources=len({o['source_id']
                              for o in required.values()}), candidate_lock_sha256=ev.sha256(ev.canonical(candidate)),
                              corpus_lock_sha256=ev.sha256(ev.canonical(corpus)),
                              source_lock_sha256=ev.sha256(ev.canonical(sources)),
                              selection_policy_sha256=ev.sha256(ev.canonical(policy)))
            entry = ledger(snapshot([run(1)]))['attempts'][0]
            doc = {k: entry[k] for k in ('measurement_identity_sha256', 'measured_source_sha', 'workflow_sha',
                                        'run_id', 'run_attempt')}
            doc.update(schema='delsk.oracle.materialization-evidence.v1', provenance=provenance,
                       verification=verification)
            oa._materialization(doc, entry)
            for change in (lambda d: d['verification'].update(verified=False),
                           lambda d: d['provenance'].update(required_occurrences=0),
                           lambda d: d['provenance'].update(selection_policy_sha256='0' * 64),
                           lambda d: d['provenance'].update(untrusted_cost=123)):
                bad = copy.deepcopy(doc)
                change(bad)
                with self.assertRaises(oa.AttemptError):
                    oa._materialization(bad, entry)

    def test_sidecar_failure_retained_separately_without_bundle(self):
        snap = snapshot([run(1, conclusion='cancelled')])
        with tempfile.TemporaryDirectory() as tmp:
            root, envelope = Path(tmp) / 'results', Path(tmp) / 'envelope'
            envelope.mkdir()
            doc = oa.create_attempt(self.env, ID, status='CANCELLED', failure_class='CANCELLED', now=NOW)
            (envelope / 'attempt.json').write_bytes(ev.canonical(doc))
            oa.import_snapshot(snap, root)
            oa.retain(envelope, root, snapshot=snap)
            self.assertFalse((root / '10-1').exists())
            self.assertTrue((root / '.attempts' / '10-1' / 'attempt.json').is_file())
            self.assertIn('ATTEMPT_NOT_RETAINED', oa.g1_root(ID, root, snapshot=snap, now=NOW)[1])

    def test_unknown_envelope_and_source_mismatch_leave_no_retained_output(self):
        for mode in ('source', 'extra', 'unknown', 'materialization'):
            snap = snapshot([run(1)])
            with tempfile.TemporaryDirectory() as tmp:
                root, envelope = Path(tmp) / 'results', Path(tmp) / 'envelope'
                envelope.mkdir()
                doc = oa.create_attempt(self.env, ID, now=NOW)
                if mode == 'source':
                    doc['workflow_sha'] = 'f' * 40
                if mode == 'unknown':
                    doc['run_id'] = 11
                (envelope / 'attempt.json').write_bytes(ev.canonical(doc))
                if mode == 'extra':
                    (envelope / 'secret.log').write_text('secret')
                if mode == 'materialization':
                    (envelope / 'materialization.json').write_bytes(ev.canonical({'bad': 'provenance'}))
                oa.import_snapshot(snap, root)
                before = list(root.iterdir())
                with self.assertRaises(oa.AttemptError):
                    oa.retain(envelope, root, snapshot=snap)
                self.assertEqual(list(root.iterdir()), before)

    def test_bundle_identity_checked_before_transaction_and_failed_verify_rolls_back(self):
        snap = snapshot([run(1)])
        with tempfile.TemporaryDirectory() as tmp:
            root, envelope = Path(tmp) / 'results', Path(tmp) / 'envelope'
            (envelope / 'bundle').mkdir(parents=True)
            (envelope / 'attempt.json').write_bytes(ev.canonical(oa.create_attempt(self.env, ID, now=NOW)))
            run_doc = {'measurement_identity_sha256': ID, 'measurement_identity': {'phase': 'pilot',
                       'measured_source_sha': SHA}, 'github': {'repository': REPO, 'run_id': 10,
                       'run_attempt': 1, 'sha': SHA, 'workflow_sha': SHA, 'workflow_ref': REF}}
            (envelope / 'bundle' / 'run.json').write_bytes(ev.canonical(run_doc))
            oa.import_snapshot(snap, root)
            with self.assertRaises((oa.AttemptError, ev.EvalError)):
                oa.retain(envelope, root, snapshot=snap)
            self.assertFalse((root / '10-1').exists())
            self.assertFalse((root / '.attempts' / '10-1').exists())


if __name__ == '__main__':
    unittest.main()
