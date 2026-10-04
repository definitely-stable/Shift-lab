"""Offline durable-registration foundation; no live CLI or provider adapter.

Broker(base_bytes, publish, readback, submit) injects three callbacks:
  publish(expected_base_bytes, new_bytes): atomic remote compare-and-append;
  readback() -> bytes: independent exact durable readback (including genesis);
  submit(request) -> closed binding or None: one provider submission, no retries.
The caller/backend must serialize writers. These fakeable interfaces do not prove
independent capture of UI/API bypass; history_blockers ALWAYS keeps that gate shut.

register(intent_id64, request) publishes REGISTERED. submit(intent_id64) publishes
SUBMITTING and reads it back BEFORE the sole submit callback. Lost responses or
unbound replies append UNRESOLVED with a machine class. A crash leaves SUBMITTING,
which blocks registration and cannot be retried. No local authoritative-resolution
API is supplied; a future verified capture backend must implement reconciliation.

Requests carry exact source/ref/repository/identity and the expected next attempt.
Reruns require an earlier acknowledged same-source run at previous_attempt; job_id
is required only for rerun_job. A return HTTP status alone is not a binding.
"""
import copy
import re

import oracle_eval as ev

SCHEMA = 'delsk.oracle.dispatch-journal.v1'
WORKFLOW = '.github/workflows/oracle-pilot.yml'
SOURCE = frozenset(('repository', 'workflow_ref', 'workflow_sha', 'measured_source_sha',
                    'measurement_identity_sha256'))
REQUEST = SOURCE | {'operation', 'run_id', 'previous_attempt', 'expected_attempt', 'job_id'}
BINDING = SOURCE | {'operation', 'run_id', 'run_attempt', 'job_id'}
EVENT = frozenset(('sequence', 'previous_sha256', 'intent_id', 'action', 'data', 'event_sha256'))
OPERATIONS = ('dispatch', 'rerun_all', 'rerun_failed', 'rerun_job')
FAILURES = ('SUBMISSION_UNCERTAIN', 'BINDING_MISSING', 'BINDING_MISMATCH')


class JournalError(Exception):
    """Closed machine-only errors; callback exception text is never retained."""


def check(condition, reason):
    if not condition:
        raise JournalError(reason)


def _hex(value, length=64):
    return type(value) is str and re.fullmatch('[0-9a-f]{' + str(length) + '}', value) is not None


def _positive(value):
    return type(value) is int and 0 < value < ev.INT_LIMIT


def _dump(value):
    try:
        return ev.canonical(value)
    except (ev.EvalError, TypeError, ValueError, UnicodeError):
        raise JournalError('CANONICAL_JSON_REQUIRED') from None


def genesis():
    """Canonical empty journal; backend must independently retain it before use."""
    return _dump(dict(schema=SCHEMA, events=[]))


def _source(data):
    repo, ref = data['repository'], data['workflow_ref']
    check(type(repo) is str and re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo), 'REPOSITORY_MISMATCH')
    prefix = f'{repo}/{WORKFLOW}@refs/heads/'
    check(type(ref) is str and ref.startswith(prefix), 'WORKFLOW_REF_MISMATCH')
    name = ref[len(prefix):]
    check(name and not any(ord(c) <= 32 or ord(c) == 127 or c in '~^:?*[\\' for c in name) and
          not any(t in name for t in ('..', '//', '@{')) and not name.endswith('.') and
          all(p and not p.startswith('.') and not p.endswith('.lock') for p in name.split('/')),
          'WORKFLOW_REF_MISMATCH')
    check(_hex(data['measured_source_sha'], 40) and data['workflow_sha'] == data['measured_source_sha'] and
          _hex(data['measurement_identity_sha256']), 'SOURCE_IDENTITY_MISMATCH')


def _request(data, states):
    check(type(data) is dict and set(data) == REQUEST, 'REQUEST_CLOSED_SCHEMA')
    _source(data)
    check(type(data['operation']) is str and data['operation'] in OPERATIONS, 'OPERATION_INVALID')
    previous, expected = data['previous_attempt'], data['expected_attempt']
    check(type(previous) is int and previous >= 0 and _positive(expected) and expected == previous + 1,
          'NEXT_ATTEMPT_MISMATCH')
    if data['operation'] == 'dispatch':
        check(data['run_id'] is None and previous == 0 and data['job_id'] is None, 'DISPATCH_BINDING_INVALID')
    else:
        check(_positive(data['run_id']) and previous > 0, 'RERUN_BINDING_INVALID')
        check(_positive(data['job_id']) if data['operation'] == 'rerun_job' else data['job_id'] is None,
              'RERUN_JOB_MISMATCH')
        known = [s['binding'] for s in states.values() if s['state'] == 'ACKNOWLEDGED' and
                 s['binding']['run_id'] == data['run_id']]
        check(known and max(b['run_attempt'] for b in known) == previous, 'RERUN_PRIOR_BINDING_MISSING')
        check(all(b[k] == data[k] for b in known for k in SOURCE), 'RERUN_SOURCE_MISMATCH')
        check(not any(s['request']['run_id'] == data['run_id'] and
                      s['request']['expected_attempt'] == expected for s in states.values()), 'RESERVATION_REUSED')


def _binding(data, request, states):
    check(type(data) is dict and set(data) == BINDING, 'BINDING_MISSING')
    _source(data)
    check(_positive(data['job_id']) if request['operation'] == 'rerun_job' else data['job_id'] is None,
          'BINDING_MISMATCH')
    check(_positive(data['run_id']) and _positive(data['run_attempt']) and
          all(data[k] == request[k] for k in SOURCE | {'operation', 'job_id'}) and
          data['run_attempt'] == request['expected_attempt'] and
          (request['run_id'] is None or data['run_id'] == request['run_id']), 'BINDING_MISMATCH')
    check(not any(s['state'] == 'ACKNOWLEDGED' and
                  (s['binding']['run_id'], s['binding']['run_attempt']) == (data['run_id'], data['run_attempt'])
                  for s in states.values()), 'BINDING_MISMATCH')


def _states(doc):
    states, prior = {}, '0' * 64
    for number, event in enumerate(doc['events'], 1):
        check(type(event) is dict and set(event) == EVENT, 'EVENT_CLOSED_SCHEMA')
        check(type(event['sequence']) is int and event['sequence'] == number and
              event['previous_sha256'] == prior and _hex(event['intent_id']) and _hex(event['event_sha256']),
              'HASH_CHAIN_INVALID')
        check(ev.hc({k: v for k, v in event.items() if k != 'event_sha256'}) == event['event_sha256'],
              'HASH_CHAIN_INVALID')
        intent, action, data = event['intent_id'], event['action'], event['data']
        if action == 'REGISTERED':
            check(intent not in states and all(s['state'] == 'ACKNOWLEDGED' for s in states.values()),
                  'INTENT_REUSED_OR_PENDING')
            _request(data, states)
            states[intent] = dict(request=data, state=action)
        else:
            check(intent in states, 'TRANSITION_INVALID')
            current = states[intent]
            if action == 'SUBMITTING':
                check(current['state'] == 'REGISTERED' and type(data) is dict and not data, 'TRANSITION_INVALID')
            elif action == 'ACKNOWLEDGED':
                check(current['state'] == 'SUBMITTING', 'TRANSITION_INVALID')
                _binding(data, current['request'], states)
                current['binding'] = data
            elif action == 'UNRESOLVED':
                check(current['state'] == 'SUBMITTING' and type(data) is dict and
                      set(data) == {'failure_class'} and data['failure_class'] in FAILURES, 'TRANSITION_INVALID')
            else:
                raise JournalError('TRANSITION_INVALID')
            current['state'] = action
        prior = event['event_sha256']
    return states


def validate_journal(data, base=None):
    """Strict canonical closed journal and immutable independently retained prefix."""
    try:
        check(type(data) is bytes, 'CANONICAL_JSON_REQUIRED')
        doc = ev.parse_doc(data)
        check(type(doc) is dict and set(doc) == {'schema', 'events'} and doc['schema'] == SCHEMA and
              type(doc['events']) is list, 'JOURNAL_CLOSED_SCHEMA')
        _states(doc)
        if base is not None:
            prior = validate_journal(base)
            check(doc['events'][:len(prior['events'])] == prior['events'], 'RETAINED_BASE_REWRITTEN')
        return doc
    except JournalError:
        raise
    except (ev.EvalError, KeyError, TypeError, ValueError, UnicodeError):
        raise JournalError('JOURNAL_INVALID') from None


def history_blockers(data):
    states = _states(validate_journal(data))
    blockers = {'DISPATCH_HISTORY_UNVERIFIED'}
    if any(s['state'] == 'REGISTERED' for s in states.values()):
        blockers.add('REGISTRATION_PENDING')
    if any(s['state'] in ('SUBMITTING', 'UNRESOLVED') for s in states.values()):
        blockers.add('DISPATCH_BINDING_UNRESOLVED')
    return sorted(blockers)


class Broker:
    """Fakeable controller foundation. Durable store/capture provisioning is intentionally absent."""
    def __init__(self, base_bytes, publish, readback, submit):
        validate_journal(base_bytes)
        check(all(callable(f) for f in (publish, readback, submit)), 'ADAPTER_MISSING')
        self._bytes, self._publish, self._readback, self._submit = base_bytes, publish, readback, submit
        self._fresh()

    def _fresh(self):
        try:
            observed = self._readback()
            check(type(observed) is bytes and observed == self._bytes, 'STALE_OR_UNACKNOWLEDGED_JOURNAL')
        except Exception:
            raise JournalError('STALE_OR_UNACKNOWLEDGED_JOURNAL') from None

    def _append(self, intent, action, data):
        self._fresh()
        doc = validate_journal(self._bytes)
        event = dict(sequence=len(doc['events']) + 1,
                     previous_sha256=doc['events'][-1]['event_sha256'] if doc['events'] else '0' * 64,
                     intent_id=intent, action=action, data=copy.deepcopy(data))
        event['event_sha256'] = ev.hc(event)
        doc['events'].append(event)
        new = _dump(doc)
        validate_journal(new, self._bytes)
        try:
            self._publish(self._bytes, new)
            observed = self._readback()
            check(type(observed) is bytes and observed == new, 'DURABILITY_UNCERTAIN')
        except Exception:
            raise JournalError('DURABILITY_UNCERTAIN') from None
        self._bytes = new
        return new

    def register(self, intent_id, request):
        return self._append(intent_id, 'REGISTERED', request)

    def submit(self, intent_id):
        states = _states(validate_journal(self._bytes))
        check(intent_id in states and states[intent_id]['state'] == 'REGISTERED', 'SUBMISSION_RETRY_REFUSED')
        request = states[intent_id]['request']
        self._append(intent_id, 'SUBMITTING', {})
        try:
            binding = self._submit(copy.deepcopy(request))  # the only submission call site
        except Exception:
            return self._append(intent_id, 'UNRESOLVED', dict(failure_class='SUBMISSION_UNCERTAIN'))
        try:
            _binding(binding, request, states)
        except JournalError:
            failure = 'BINDING_MISSING' if type(binding) is not dict or set(binding) != BINDING else 'BINDING_MISMATCH'
            return self._append(intent_id, 'UNRESOLVED', dict(failure_class=failure))
        return self._append(intent_id, 'ACKNOWLEDGED', binding)
