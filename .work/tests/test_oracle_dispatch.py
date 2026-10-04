"""Durable-registration foundation: fake callbacks only, no provider writes."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import oracle_eval as ev
import oracle_dispatch as od

REPO, SHA, ID = 'test/repo', 'a' * 40, 'b' * 64
REF = f'{REPO}/.github/workflows/oracle-pilot.yml@refs/heads/main'


def request(operation='dispatch', run_id=None, previous_attempt=0, expected_attempt=1, job_id=None, **extra):
    return dict(repository=REPO, measured_source_sha=SHA, workflow_sha=SHA, workflow_ref=REF,
                measurement_identity_sha256=ID, operation=operation, run_id=run_id,
                previous_attempt=previous_attempt, expected_attempt=expected_attempt, job_id=job_id, **extra)


def binding(req, dispatch_run_id=10, **changes):
    out = {k: req[k] for k in ('repository', 'measured_source_sha', 'workflow_sha', 'workflow_ref',
                               'measurement_identity_sha256', 'operation', 'job_id')}
    out.update(run_id=req['run_id'] or dispatch_run_id, run_attempt=req['expected_attempt'])
    out.update(changes)
    return out


class Store:
    def __init__(self):
        self.data = od.genesis()
        self.trace, self.response, self.failure = [], None, None

    def publish(self, base, new):
        self.trace.append(('publish', ev.parse_doc(new)['events'][-1]['action']))
        if self.data != base:
            raise RuntimeError('stale PRIVATE_TOKEN')
        self.data = new

    def readback(self):
        action = ev.parse_doc(self.data)['events'][-1]['action'] if ev.parse_doc(self.data)['events'] else 'GENESIS'
        self.trace.append(('read', action))
        return self.data

    def submit(self, req):
        self.trace.append(('submit', req['operation']))
        if self.failure:
            raise self.failure
        return copy.deepcopy(self.response if self.response is not None else binding(req))

    def broker(self, base=None):
        return od.Broker(base or self.data, self.publish, self.readback, self.submit)


class Registration(unittest.TestCase):
    def test_exact_independent_readback_precedes_the_only_submit(self):
        store = Store()
        broker = store.broker()
        broker.register('1' * 64, request())
        self.assertFalse(any(t[0] == 'submit' for t in store.trace))
        broker.submit('1' * 64)
        actions = store.trace
        registered = actions.index(('publish', 'REGISTERED'))
        submitting = actions.index(('publish', 'SUBMITTING'))
        submitted = actions.index(('submit', 'dispatch'))
        self.assertLess(registered, actions.index(('read', 'REGISTERED')))
        self.assertLess(actions.index(('read', 'REGISTERED')), submitting)
        self.assertLess(submitting, actions.index(('read', 'SUBMITTING')))
        self.assertLess(actions.index(('read', 'SUBMITTING')), submitted)
        self.assertEqual(sum(t[0] == 'submit' for t in actions), 1)
        self.assertEqual([e['action'] for e in od.validate_journal(store.data)['events']],
                         ['REGISTERED', 'SUBMITTING', 'ACKNOWLEDGED'])

    def test_durability_failures_cannot_submit(self):
        for fail_action, mode in (('REGISTERED', 'publish'), ('REGISTERED', 'read'),
                                  ('SUBMITTING', 'publish'), ('SUBMITTING', 'read')):
            with self.subTest(action=fail_action, mode=mode):
                store = Store()
                def publish(base, new):
                    if mode == 'publish' and ev.parse_doc(new)['events'][-1]['action'] == fail_action:
                        raise RuntimeError('secret remote text')
                    store.publish(base, new)
                def read():
                    if mode == 'read' and ev.parse_doc(store.data)['events'] and \
                            ev.parse_doc(store.data)['events'][-1]['action'] == fail_action:
                        return od.genesis()
                    return store.readback()
                broker = od.Broker(store.data, publish, read, store.submit)
                with self.assertRaises(od.JournalError):
                    broker.register('1' * 64, request())
                    broker.submit('1' * 64)
                self.assertFalse(any(t[0] == 'submit' for t in store.trace))

    def test_crash_after_durable_submitting_never_blindly_retries(self):
        store = Store()
        def crash(req):
            raise KeyboardInterrupt()
        broker = od.Broker(store.data, store.publish, store.readback, crash)
        broker.register('1' * 64, request())
        with self.assertRaises(KeyboardInterrupt):
            broker.submit('1' * 64)
        restarted = store.broker()
        self.assertIn('DISPATCH_BINDING_UNRESOLVED', od.history_blockers(store.data))
        with self.assertRaises(od.JournalError):
            restarted.submit('1' * 64)
        with self.assertRaises(od.JournalError):
            restarted.register('2' * 64, request())

    def test_lost_or_unbound_submission_is_retained_without_exception_text(self):
        for failure, response in ((TimeoutError('SECRET_TOKEN'), None), (None, {}),
                                  (None, {'status': 204}), (None, binding(request(), run_attempt=2)),
                                  (None, binding(request(), workflow_sha='f' * 40))):
            with self.subTest(failure=failure, response=response):
                store = Store()
                store.failure, store.response = failure, response
                broker = store.broker()
                broker.register('1' * 64, request())
                broker.submit('1' * 64)
                doc = od.validate_journal(store.data)
                self.assertEqual(doc['events'][-1]['action'], 'UNRESOLVED')
                self.assertNotIn(b'SECRET_TOKEN', store.data)
                self.assertNotIn(b'exception', store.data)
                with self.assertRaises(od.JournalError):
                    broker.submit('1' * 64)
                with self.assertRaises(od.JournalError):
                    broker.register('2' * 64, request())

    def test_terminal_publication_failure_after_submit_never_permits_retry(self):
        for terminal in ('ACKNOWLEDGED', 'UNRESOLVED'):
            for mode in ('publish', 'read'):
                with self.subTest(terminal=terminal, mode=mode):
                    store = Store()
                    if terminal == 'UNRESOLVED':
                        store.response = {}
                    def publish(base, new):
                        if mode == 'publish' and ev.parse_doc(new)['events'][-1]['action'] == terminal:
                            raise TimeoutError('PRIVATE_REMOTE_RESPONSE')
                        store.publish(base, new)
                    def read():
                        if mode == 'read' and ev.parse_doc(store.data)['events'] and \
                                ev.parse_doc(store.data)['events'][-1]['action'] == terminal:
                            return od.genesis()
                        return store.readback()
                    broker = od.Broker(store.data, publish, read, store.submit)
                    broker.register('1' * 64, request())
                    with self.assertRaises(od.JournalError):
                        broker.submit('1' * 64)
                    self.assertEqual(sum(t[0] == 'submit' for t in store.trace), 1)
                    self.assertNotIn(b'PRIVATE_REMOTE_RESPONSE', store.data)
                    with self.assertRaises(od.JournalError):
                        broker.submit('1' * 64)
                    restarted = store.broker()
                    with self.assertRaises(od.JournalError):
                        restarted.submit('1' * 64)
                    self.assertEqual(sum(t[0] == 'submit' for t in store.trace), 1)

    def test_stale_or_concurrent_writers_cannot_replace_existing_registration(self):
        store = Store()
        first, second = store.broker(), store.broker()
        first.register('1' * 64, request())
        before = store.data
        with self.assertRaises(od.JournalError):
            second.register('2' * 64, request())
        self.assertEqual(store.data, before)
        self.assertFalse(any(t[0] == 'submit' for t in store.trace))

    def test_pending_registration_blocks_another_intent(self):
        store = Store()
        broker = store.broker()
        broker.register('1' * 64, request())
        with self.assertRaises(od.JournalError):
            broker.register('2' * 64, request())
        self.assertIn('REGISTRATION_PENDING', od.history_blockers(store.data))

    def test_retry_reused_intent_and_duplicate_ack_binding_are_refused(self):
        store = Store()
        broker = store.broker()
        broker.register('1' * 64, request())
        broker.submit('1' * 64)
        with self.assertRaises(od.JournalError):
            broker.submit('1' * 64)
        with self.assertRaises(od.JournalError):
            broker.register('1' * 64, request())
        broker.register('2' * 64, request())
        broker.submit('2' * 64)  # fake returns the already reserved run/attempt
        self.assertEqual(od.validate_journal(store.data)['events'][-1]['action'], 'UNRESOLVED')


class Reruns(unittest.TestCase):
    def initialized(self):
        store = Store()
        broker = store.broker()
        broker.register('1' * 64, request())
        broker.submit('1' * 64)
        return store, broker

    def test_every_rerun_route_reserves_exact_next_attempt_and_preserves_source(self):
        store, broker = self.initialized()
        for intent, op, previous, job in [('2', 'rerun_all', 1, None), ('3', 'rerun_failed', 2, None),
                                          ('4', 'rerun_job', 3, 99)]:
            req = request(op, 10, previous, previous + 1, job)
            broker.register(intent * 64, req)
            broker.submit(intent * 64)
            self.assertEqual(od.validate_journal(store.data)['events'][-1]['data'], binding(req))
        self.assertEqual([t[1] for t in store.trace if t[0] == 'submit'],
                         ['dispatch', 'rerun_all', 'rerun_failed', 'rerun_job'])

    def test_rerun_unknown_run_stale_attempt_wrong_source_and_bad_job_cannot_register(self):
        for req in (request('rerun_all', 11, 1, 2), request('rerun_all', 10, 2, 3),
                    request('rerun_all', 10, 1, 3), request('rerun_job', 10, 1, 2),
                    request('rerun_failed', 10, 1, 2, 99),
                    dict(request('rerun_all', 10, 1, 2), measured_source_sha='f' * 40, workflow_sha='f' * 40)):
            store, broker = self.initialized()
            before = store.data
            with self.subTest(req=req), self.assertRaises(od.JournalError):
                broker.register('2' * 64, req)
            self.assertEqual(store.data, before)

    def test_single_job_ack_requires_same_job_run_and_attempt(self):
        for changes in ({'job_id': 100}, {'job_id': True}, {'run_id': 11}, {'run_attempt': 3}):
            store, broker = self.initialized()
            req = request('rerun_job', 10, 1, 2, 99)
            store.response = binding(req, **changes)
            broker.register('2' * 64, req)
            broker.submit('2' * 64)
            self.assertEqual(od.validate_journal(store.data)['events'][-1]['action'], 'UNRESOLVED')

    def test_boolean_job_one_binding_cannot_impersonate_integer_job_one(self):
        store, broker = self.initialized()
        req = request('rerun_job', 10, 1, 2, 1)
        store.response = binding(req, job_id=True)
        broker.register('2' * 64, req)
        broker.submit('2' * 64)
        self.assertEqual(od.validate_journal(store.data)['events'][-1]['action'], 'UNRESOLVED')


class Journal(unittest.TestCase):
    def acknowledged(self):
        store = Store()
        broker = store.broker()
        broker.register('1' * 64, request())
        broker.submit('1' * 64)
        return store.data

    def test_closed_canonical_schema_and_exact_source_ref_repository_binding(self):
        for req in (dict(request(), token='secret'), dict(request(), workflow_sha='f' * 40),
                    dict(request(), workflow_ref=REF.replace(REPO, 'foreign/repo')),
                    dict(request(), workflow_ref=REF.replace('oracle-pilot.yml', 'oracle-smoke.yml')),
                    dict(request(), workflow_ref=REF.replace('refs/heads/', 'refs/tags/')),
                    dict(request(), operation='rerun_unknown'), dict(request(), expected_attempt=True),
                    dict(request(), measurement_identity_sha256=None)):
            store = Store()
            with self.subTest(req=req), self.assertRaises(od.JournalError):
                store.broker().register('1' * 64, req)
            self.assertEqual(store.data, od.genesis())
        with self.assertRaises(od.JournalError):
            od.validate_journal(b'{"schema": "delsk.oracle.dispatch-journal.v1", "events": []}')

    def test_chain_sequence_fields_and_state_tampering_fail_closed(self):
        good = self.acknowledged()
        for edit in (lambda d: d['events'][1].update(sequence=1),
                     lambda d: d['events'][1].update(previous_sha256='f' * 64),
                     lambda d: d['events'][1].update(action='ACKNOWLEDGED'),
                     lambda d: d['events'][0]['data'].update(measured_source_sha='f' * 40),
                     lambda d: d['events'][1].update(extra='unknown'),
                     lambda d: d.update(authority=True)):
            doc = ev.parse_doc(good)
            edit(doc)
            with self.assertRaises(od.JournalError):
                od.validate_journal(ev.canonical(doc))

    def test_independently_retained_base_prevents_valid_rehashed_rewrites_or_deletion(self):
        good = self.acknowledged()
        doc = ev.parse_doc(good)
        prefix = ev.canonical(dict(doc, events=doc['events'][:1]))
        od.validate_journal(good, prefix)
        with self.assertRaises(od.JournalError):
            od.validate_journal(prefix, good)
        changed = ev.parse_doc(good)
        changed['events'][0]['intent_id'] = '2' * 64
        for i, event in enumerate(changed['events']):
            event['intent_id'] = '2' * 64
            event['previous_sha256'] = changed['events'][i - 1]['event_sha256'] if i else '0' * 64
            event['event_sha256'] = ev.hc({k: v for k, v in event.items() if k != 'event_sha256'})
        changed = ev.canonical(changed)
        od.validate_journal(changed)
        with self.assertRaises(od.JournalError):
            od.validate_journal(changed, prefix)

    def test_local_or_acknowledged_history_always_unverified_no_waiver(self):
        self.assertEqual(od.history_blockers(od.genesis()), ['DISPATCH_HISTORY_UNVERIFIED'])
        self.assertEqual(od.history_blockers(self.acknowledged()), ['DISPATCH_HISTORY_UNVERIFIED'])
        with self.assertRaises(TypeError):
            od.history_blockers(self.acknowledged(), authority_verified=True)


if __name__ == '__main__':
    unittest.main()
