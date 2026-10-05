"""DELSK-003A C1-A: G1 v2 of the frozen provenance/G1 contract delsk.oracle-contract.v2 (synthetic conformance only).

Implements contract-v2 sections 7-11 (.work/oracle/contract-v2.md) on top of oracle_registry_v2.py:

    registry validation (5.6) -> evidence root (8.1) -> PRE / BUNDLE / MISSING + violations (8.3-8.4)
    -> unbound attempts of registered runs (8.5) -> series state machine (7.3) -> v1 G1 core (oracle_eval.g1)
    -> v2 codes and gates (7.4, 9.1) -> verdict (9.3) -> G1 record (9.6)

The population is always every entry of the registry: no caller selects entries, bundles or a subset. The core
(_g1_core) is a pure function of an immutable Evaluation and only ever returns SCIENTIFIC_PASS / NOT_PASSED / INVALID /
NOT_RUN / NO_VERDICT. g1_test maps SCIENTIFIC_PASS to TEST_ONLY_PASS with authority = evaluator = null.
g1_production takes only the identity; before activation (contract 16) it is NOT_PASSED V2_NOT_ACTIVE and performs
no read at all. Never imports test modules; not in the v1 code manifest.
"""
import collections
from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess

import oracle_attempts as oa
import oracle_eval as ev
import oracle_registry_v2 as reg

NO_VERDICT_CODES = ('REGISTRY_INVALID', 'REGISTRY_DUPLICATE', 'REGISTRY_STALE', 'MAIN_STALE', 'REGISTRY_ROLLBACK',
                    'EVIDENCE_ROOT_INVALID')
INVALID_V2 = frozenset(('BINDING_MISMATCH', 'UNBOUND_MEASUREMENT', 'DUPLICATE_EXECUTION', 'SERIES_INVALID',
                        'SERIES_REPEAT_MISMATCH', 'SERIES_TRANSITION_MISMATCH', 'SERIES_FORK', 'SERIES_REENTRY'))
NOT_PASSED_V2 = frozenset(('RESULT_MISSING', 'SERIES_FAILURE', 'SERIES_TRANSITION_MISSING', 'SERIES_SUPERSEDED',
                           'KAT_NOT_VERIFIED', 'V2_NOT_ACTIVE'))
CORE_VERDICTS = ('SCIENTIFIC_PASS', 'NOT_PASSED', 'INVALID', 'NOT_RUN', 'NO_VERDICT')
TEST_VERDICT = {'SCIENTIFIC_PASS': 'TEST_ONLY_PASS'}
BINDING_FIELDS = ('run_id', 'run_attempt', 'repository', 'measured_source_sha', 'measurement_identity_sha256',
                  'entry_sha256')
RUN_KEY = re.compile(r'[1-9][0-9]*-[1-9][0-9]*\Z')
V1_RESULTS = Path(ev.RESULTS)
# Activation record (contract 16): bind/boundary step names, KAT step name, evidence of items 6-10. C1-B sets it in a
# reviewed PR; until then production can never return PASS.
ACTIVATION_RECORD = None


# --- inputs -----------------------------------------------------------------------------------------------------------

def _copy(value):
    return json.loads(ev.compact(value))  # deep copy restricted to canonical JSON values


@dataclass(frozen=True)
class Evidence:
    """Retained v2 results root (contract 8.1) as read from the pinned main tree."""
    bundles: tuple          # bundle_projection documents, one per bundles/<run_id>-<run_attempt>/
    bindings: tuple         # attempt_binding documents, one per bindings/<run_id>-<run_attempt>.json
    foreign_paths: tuple    # any other path, symlink, bad name or unreadable sidecar
    v1_root_keys: tuple     # run keys present in the v1 root (bundles, sidecars, ledger)

    @classmethod
    def build(cls, bundles=(), bindings=(), foreign_paths=(), v1_root_keys=()):
        return cls(tuple(map(_copy, bundles)), tuple(map(_copy, bindings)), tuple(foreign_paths),
                   tuple((int(a), int(b)) for a, b in v1_root_keys))


@dataclass(frozen=True)
class Evaluation:
    """Everything one evaluation reads, pinned once (contract 9.0). Production fills it only from the authority
    constants; tests build it from synthetic data. registry_reread / main_reread are the values read again after the
    evaluation (stale checks); kat_green holds the commits with green exact-commit KAT evidence (kat_verified_v2)."""
    genesis: dict
    entries: tuple
    registry_reread: dict
    git: reg.GitSnapshot
    main_reread: str
    provider: tuple         # provider_observation documents obtained live in this evaluation
    pull_requests: tuple
    evidence: Evidence
    evaluator_source_sha: str
    kat_green: frozenset
    g1_freeze_sha256: str = None   # production: SHA-256 of freeze-v2.json in the pinned tree; test core: None

    @classmethod
    def build(cls, *, genesis, entries, registry_reread, git, main_reread, provider, pull_requests, evidence,
              evaluator_source_sha, kat_green, g1_freeze_sha256=None):
        return cls(_copy(genesis), tuple(map(_copy, entries)), _copy(registry_reread), git, main_reread,
                   tuple(map(_copy, provider)), tuple(map(_copy, pull_requests)), evidence, evaluator_source_sha,
                   frozenset(kat_green), g1_freeze_sha256)


# --- provider facts (contract 8.3) ------------------------------------------------------------------------------------

def run_binding(run, e):
    return (run['head_sha'] == e['measured_source_sha'] and run['workflow_path'] == e['workflow_path']
            and run['event'] == 'workflow_dispatch'
            and e['workflow_ref'] == f"{e['repository']}/{run['workflow_path']}@refs/heads/{run['head_branch']}")


def _measure_jobs(run):
    return [j for j in run['jobs'] if j['name'] == 'measure']


def _steps(job, role):
    return [s for s in job['steps'] if s['role'] == role]


def pre_proven(observation, e):
    """PRE conditions 2-4 for one live observation against entry e. Absent, deleted, pending or ambiguous data,
    unknown jobs, a started boundary or a started measure job without a boundary step are never PRE."""
    run = observation['run'] if observation else None
    if run is None or not run_binding(run, e) or run['status'] != 'completed':
        return False
    names = [j['name'] for j in run['jobs']]
    if not set(names) <= set(reg.JOBS) or names.count('measure') > 1:
        return False
    measure = _measure_jobs(run)
    if not measure or not measure[0]['started']:
        return True
    boundary = _steps(measure[0], 'boundary')
    return len(boundary) == 1 and not any(s['started'] for s in measure[0]['steps']
                                          if s['number'] >= boundary[0]['number'])


def boundary_started(run):
    return any(s['started'] for j in _measure_jobs(run) for s in _steps(j, 'boundary'))


def bound_before_boundary(run):
    """Step bind started, succeeded and precedes the single boundary step of the single measure job."""
    measure = _measure_jobs(run)
    if len(measure) != 1:
        return False
    bind, boundary = _steps(measure[0], 'bind'), _steps(measure[0], 'boundary')
    return (len(bind) == len(boundary) == 1 and bind[0]['started'] and bind[0]['conclusion'] == 'success'
            and bind[0]['number'] < boundary[0]['number'])


def provider_observation(run_id, run_attempt, run, attempt, jobs, roles):
    """Normalize GitHub API documents (contract 8.3) fail-closed.

    Raw documents must prove that they belong to the requested (run_id, run_attempt). Cache, pagination or adapter
    mix-ups are treated as missing provider evidence; data is never relabelled under another scientific key.
    """
    doc = {'schema': 'delsk.oracle.provider-observation.v1', 'run_id': run_id, 'run_attempt': run_attempt,
           'run': None}
    if run is None or attempt is None:
        return doc
    if not (type(run) is dict and type(attempt) is dict and run.get('id') == run_id
            and attempt.get('id') == run_id and attempt.get('run_attempt') == run_attempt
            and oa.positive(run.get('run_attempt')) and run['run_attempt'] >= run_attempt):
        return doc
    head = attempt.get('head_sha')
    if not oa.digest(head, 40):
        return doc
    for job in jobs:
        if not (type(job) is dict and job.get('run_id') == run_id and job.get('run_attempt') == run_attempt
                and job.get('head_sha') == head):
            return doc

    def started(x):
        return x['status'] in ('in_progress', 'completed') and x['conclusion'] != 'skipped'

    try:
        doc['run'] = {'head_sha': head, 'head_branch': attempt['head_branch'],
                      'workflow_path': attempt['path'], 'event': attempt['event'], 'status': attempt['status'],
                      'latest_run_attempt': run['run_attempt'],
                      'jobs': [{'name': j['name'], 'started': started(j), 'conclusion': j['conclusion'],
                                'steps': [{'number': s['number'], 'role': roles.get(s['name'], 'other'),
                                           'started': started(s), 'conclusion': s['conclusion']} for s in j['steps']]}
                               for j in jobs]}
    except (KeyError, TypeError):
        doc['run'] = None
    return doc


# --- registry-wide analysis -------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Analysis:
    """Registry-wide part of contract 9.1 shared by every identity of one evaluation."""
    main_head_sha: str
    blocker: str            # NO_VERDICT code, or None
    registry_head: dict
    genesis_sha256: str
    entries: tuple
    classes: dict           # run key -> {class, outcome, conformance, violations, bundle}
    unbound: tuple          # {measurement_identity_sha256, science_identity_sha256, run_id, run_attempt}
    series: dict            # science -> {phase, first_sequence, state, codes}
    transitions: tuple
    kat_green: frozenset    # commits whose KAT gate holds: on the pinned main and green
    evaluator_source_sha: str


def _unique(docs, key):
    """{key: doc} of the valid documents; a key reported more than once is ambiguous and dropped (never chosen)."""
    count = collections.Counter(key(d) for d in docs)
    return {key(d): d for d in docs if count[key(d)] == 1}


def _no_verdict(git, code, registry_head=None, genesis_sha256=None):
    return Analysis(git.main_head_sha, code, registry_head, genesis_sha256, (), {}, (), {}, (), frozenset(), None)


_RUN_TYPES = {'repository': str, 'run_id': int, 'run_attempt': int, 'sha': str, 'workflow_ref': str,
              'workflow_sha': str}
_PILOT_RUN = {'repository': reg.REPOSITORY, 'run_id': 1, 'run_attempt': 1, 'sha': '0' * 40, 'workflow_sha': '0' * 40,
              'workflow_ref': f'{reg.REPOSITORY}/{reg.WORKFLOW_PATH}@refs/heads/main'}


def bundle_admissible(doc):
    """bundle_projection by schema. v1 verify accepts any run.json repository/workflow_ref, which the v2 bundle_run
    schema cannot express; such a verified bundle keeps its true run block (well-typed, checked against a
    schema-valid stand-in only for the other fields) so that classify reports it as BINDING_MISMATCH (8.4) instead of
    treating the root as malformed. The stand-in is never compared with an entry."""
    if reg.valid(doc, 'bundle_projection'):
        return True
    run = doc.get('run') if type(doc) is dict else None
    return (type(run) is dict and doc.get('bundle_verified') is True and set(run) == set(_RUN_TYPES)
            and all(type(run[k]) is t for k, t in _RUN_TYPES.items()) and reg.canonical_value(run)
            and reg.valid({**doc, 'run': _PILOT_RUN}, 'bundle_projection'))


def evidence_root_valid(evidence, keys):
    """Contract 8.1 (Model 1, no v1/v2 mixing) over the read root."""
    if evidence.foreign_paths or set(evidence.v1_root_keys) & keys:
        return False
    for docs, admissible in ((evidence.bundles, bundle_admissible),
                             (evidence.bindings, lambda d: reg.valid(d, 'attempt_binding'))):
        if not all(admissible(d) for d in docs):
            return False
        found = [reg.run_key(d) for d in docs]
        if len(set(found)) != len(found) or not set(found) <= keys:
            return False
    return all(reg.self_digest_ok(b, 'binding_sha256') for b in evidence.bindings)


def classify(e, observation, bundle, binding, duplicate):
    """Contract 8.4 for one entry: (class, violations). observation None = not obtained (never better than deleted)."""
    run = observation['run'] if observation else None
    violations = set()
    if duplicate:
        violations.add('DUPLICATE_EXECUTION')
    if run is not None and not run_binding(run, e):
        violations.add('BINDING_MISMATCH')
    if binding is not None and (any(binding[f] != e[f] for f in BINDING_FIELDS)
                                or binding['entry_sequence'] != e['sequence']):
        violations.add('BINDING_MISMATCH')
    verified = bundle is not None and bundle['bundle_verified']
    expected_run = {'repository': e['repository'], 'run_id': e['run_id'], 'run_attempt': e['run_attempt'],
                    'sha': e['measured_source_sha'], 'workflow_sha': e['workflow_sha'],
                    'workflow_ref': e['workflow_ref']}
    if verified and (bundle['run'] != expected_run or
                     bundle['measurement_identity_sha256'] != e['measurement_identity_sha256']):
        violations.add('BINDING_MISMATCH')
    if bundle is not None and run is not None and not boundary_started(run):
        violations.add('BINDING_MISMATCH')
    if bundle is not None and binding is None:
        violations.add('UNBOUND_MEASUREMENT')
    if binding is not None and binding['observed_head']['sequence'] < e['sequence']:
        violations.add('UNBOUND_MEASUREMENT')
    if bundle is not None and run is not None and not bound_before_boundary(run):
        violations.add('UNBOUND_MEASUREMENT')
    if violations:
        return 'MISSING', violations
    if verified and run is not None:
        return 'BUNDLE', violations
    if bundle is None and pre_proven(observation, e):
        return 'PRE', violations
    return 'MISSING', violations


def unbound_attempts(entries, provider):
    """Contract 8.5: attempts 1..latest_run_attempt of every registered run ID without an entry and without PRE proof
    (run binding against every entry of that run). Only registered run IDs are inspected (Model 1)."""
    by_run = collections.defaultdict(list)
    for e in entries:
        by_run[e['run_id']].append(e)
    latest = collections.defaultdict(int)
    for (run_id, _), o in provider.items():
        if o['run'] is not None:
            latest[run_id] = max(latest[run_id], o['run']['latest_run_attempt'])
    out = []
    for run_id, es in by_run.items():
        keys = {e['run_attempt'] for e in es}
        # ponytail: one pass per attempt number; a provider claiming an absurd latest_run_attempt only lengthens the
        # (already INVALID) unbound list.
        for n in range(1, latest[run_id] + 1):
            if n in keys or all(pre_proven(provider.get((run_id, n)), e) for e in es):
                continue
            for mi, si in sorted({(e['measurement_identity_sha256'], e['science_identity_sha256']) for e in es}):
                out.append({'measurement_identity_sha256': mi, 'science_identity_sha256': si, 'run_id': run_id,
                            'run_attempt': n})
    return tuple(sorted(out, key=lambda u: (u['run_id'], u['run_attempt'], u['measurement_identity_sha256'])))


def transition_valid(e, current, git, pull_requests, sciences):
    """V1-V5 of contract 7.3 for transition T of entry e opening new series S while `current` is C (V6 holds by the
    caller: S has no entries)."""
    t, s = e['transition'], e['science_identity_sha256']
    merge = t['change_review']['merge_commit_sha']
    pr = pull_requests.get(t['change_review']['pull_request'])
    merged = git.identity(merge)
    return (t['phase'] == e['phase'] and t['new_science_identity_sha256'] == s                           # V1
            and t['previous_science_identity_sha256'] == current
            and pr is not None and pr['merged'] is True and pr['merge_commit_sha'] == merge             # V2
            and pr['base_ref'] == reg.SOURCE_REF
            and git.ancestor_or_equal(merge, e['measured_source_sha']) and git.on_main(merge)           # V3
            and merged is not None and ev.hc(reg.science_identity(merged)) == s                        # V4
            and (t['reason'] == 'SEMANTIC_CHANGE') ==                                                  # V5
            (sciences[current]['contract_freeze_sha256'] != sciences[s]['contract_freeze_sha256']))


def series_machine(entries, git, pull_requests):
    """Contract 7.3, deterministic by sequence, per phase. Returns (series, transitions, current per phase)."""
    phases = collections.defaultdict(lambda: {'current': None, 'retired': set(), 'orphans': set()})
    sciences = {e['science_identity_sha256']: reg.science_identity(git.identity(e['measured_source_sha']))
                for e in entries}
    series, taint, transitions = {}, collections.defaultdict(set), []
    for e in entries:
        p, s, t = phases[e['phase']], e['science_identity_sha256'], e['transition']
        series.setdefault(s, {'phase': e['phase'], 'first_sequence': e['sequence']})
        if t is None:
            if p['current'] is None:
                p['current'] = s
            elif s in p['retired']:
                taint[s].add('SERIES_REENTRY')
            elif s != p['current'] and s not in p['orphans']:
                p['orphans'].add(s)
                taint[s].add('SERIES_TRANSITION_MISSING')
            continue
        if p['current'] is None:
            p['current'] = s
            status = 'MISMATCH'
        elif s == p['current'] or s in p['orphans']:
            status = 'MISMATCH'
        elif s in p['retired']:
            status = 'REENTRY'
        elif t['previous_science_identity_sha256'] in p['retired']:
            p['orphans'].add(s)
            status = 'FORK'
        elif not transition_valid(e, p['current'], git, pull_requests, sciences):
            p['orphans'].add(s)
            status = 'MISMATCH'
        else:
            p['retired'].add(p['current'])
            p['current'] = s
            status = 'VALID'
        if status != 'VALID':
            taint[s].add({'MISMATCH': 'SERIES_TRANSITION_MISMATCH', 'REENTRY': 'SERIES_REENTRY',
                          'FORK': 'SERIES_FORK'}[status])
        transitions.append({'sequence': e['sequence'], 'status': status, 'transition': t})
    for s, info in series.items():
        p = phases[info['phase']]
        info['state'] = 'CURRENT' if s == p['current'] else 'RETIRED' if s in p['retired'] else 'ORPHAN'
        info['codes'] = sorted(taint[s])
    return series, tuple(transitions), {phase: p['current'] for phase, p in phases.items()}


def analyze(evaluation):
    """Validation 5.6 items 1-6 in their fixed order (first failure is the single blocker), then classification of
    every entry of every identity and phase, unbound attempts and the series machine."""
    x, git = evaluation, evaluation.git
    entries = list(x.entries)
    try:
        registry_head = reg.validate(x.genesis, entries, git, x.g1_freeze_sha256)
    except reg.RegistryInvalid:
        return _no_verdict(git, 'REGISTRY_INVALID')
    genesis_sha256 = ev.hc(x.genesis)
    chain = reg.history(x.genesis, entries)
    for code, failed in (('REGISTRY_DUPLICATE', lambda: reg.duplicate_keys(entries)),
                         ('REGISTRY_STALE', lambda: reg.stale(registry_head, x.registry_reread)),
                         ('MAIN_STALE', lambda: reg.stale(git.main_head_sha, x.main_reread)),
                         ('REGISTRY_ROLLBACK', lambda: any(
                             not reg.on_history(b['observed_head'], chain) for b in x.evidence.bindings
                             if type(b) is dict and reg.valid(b.get('observed_head'), 'registry_head'))),
                         ('EVIDENCE_ROOT_INVALID', lambda: not evidence_root_valid(
                             x.evidence, {reg.run_key(e) for e in entries}))):
        if failed():
            return _no_verdict(git, code, registry_head, genesis_sha256)
    provider = _unique([o for o in x.provider if reg.valid(o, 'provider_observation')], reg.run_key)
    bundles = {reg.run_key(b): b for b in x.evidence.bundles}
    bindings = {reg.run_key(b): b for b in x.evidence.bindings}
    claimed = collections.defaultdict(list)
    for key, b in bindings.items():
        claimed[b['entry_sha256']].append(key)
    by_sha = {e['entry_sha256']: reg.run_key(e) for e in entries}
    duplicate = set()
    for sha, keys in claimed.items():
        if len(keys) > 1:
            duplicate.update(keys)
            duplicate.update([by_sha[sha]] if sha in by_sha else [])
    classes = {}
    for e in entries:
        key = reg.run_key(e)
        cls, violations = classify(e, provider.get(key), bundles.get(key), bindings.get(key), key in duplicate)
        bundle = bundles.get(key) if cls == 'BUNDLE' else None
        classes[key] = {'class': cls, 'violations': sorted(violations), 'bundle': bundle,
                        'outcome': bundle['run_status'] if bundle else None,
                        'conformance': bundle['conformance'] if bundle else None}
    pull_requests = _unique([p for p in x.pull_requests if reg.valid(p, 'pull_request')], lambda p: p['number'])
    series, transitions, _ = series_machine(entries, git, pull_requests)
    green = frozenset(c for c in x.kat_green if git.on_main(c))
    return Analysis(git.main_head_sha, None, registry_head, genesis_sha256, tuple(entries), classes,
                    unbound_attempts(entries, provider), series, transitions, green, x.evaluator_source_sha)


def analyze_authoritative(evaluation, registry_commits):
    """Production composition boundary: validate raw physical history and exact v2 freeze before analysis."""
    try:
        snapshot = reg.authoritative_registry(registry_commits, evaluation.git)
        genesis, entries = reg.physical_objects(snapshot)
    except (reg.RegistryInvalid, TypeError):
        return _no_verdict(evaluation.git, 'REGISTRY_INVALID')
    if (ev.compact(genesis) != ev.compact(evaluation.genesis)
            or ev.compact(list(entries)) != ev.compact(list(evaluation.entries))
            or evaluation.g1_freeze_sha256 != reg.G1_FREEZE_SHA256):
        return _no_verdict(evaluation.git, 'REGISTRY_INVALID')
    return analyze(evaluation)


# --- G1 for one identity ----------------------------------------------------------------------------------------------

def series_codes(a, science, identity):
    """Contract 7.4 for identity `identity` of series `science`: taint, supersession and carry-over."""
    info = a.series[science]
    codes = set(info['codes'])
    if info['state'] == 'RETIRED':
        codes.add('SERIES_SUPERSEDED')
    members = [(e, a.classes[reg.run_key(e)]) for e in a.entries if e['science_identity_sha256'] == science]
    for e, c in members:
        if e['measurement_identity_sha256'] == identity or c['class'] == 'PRE':
            continue
        if c['violations'] or c['outcome'] == 'INVALID':
            codes.add('SERIES_INVALID')
        elif c['class'] == 'MISSING' or c['outcome'] in ('INCOMPLETE', 'COMPLETE_WITH_FAILURES') or \
                (c['outcome'] == 'COMPLETE' and c['conformance'] is not True):
            codes.add('SERIES_FAILURE')
    if any(u['science_identity_sha256'] == science and u['measurement_identity_sha256'] != identity
           for u in a.unbound):
        codes.add('SERIES_INVALID')
    repeats = {(c['bundle']['series_projection_sha256'], c['bundle']['sealed_commitments_sha256'])
               for _, c in members if c['class'] == 'BUNDLE' and c['outcome'] == 'COMPLETE'}
    if len(repeats) > 1:
        codes.add('SERIES_REPEAT_MISMATCH')
    return codes


def _v1_record(e, bundle):
    if bundle is None:  # an attempt with violations, or an unbound attempt: INVALID for the v1 table
        return {'github_run_id': e['run_id'], 'run_status': 'INVALID', 'cost_projection_sha256': None,
                'targets_sha256': None, 'sealed_commitments_sha256': None, 'conformance': None,
                'bundle_verified': None}
    return {'github_run_id': e['run_id'], 'run_status': bundle['run_status'],
            'cost_projection_sha256': bundle['cost_projection_sha256'], 'targets_sha256': bundle['targets_sha256'],
            'sealed_commitments_sha256': bundle['sealed_commitments_sha256'], 'conformance': bundle['conformance'],
            'bundle_verified': bundle['bundle_verified']}


def combine(v1_verdict, v1_blockers, codes):
    """Contract 9.3."""
    x, y = codes & INVALID_V2, codes & NOT_PASSED_V2
    if v1_verdict == 'INVALID' or x:
        return 'INVALID', sorted(set(v1_blockers if v1_verdict == 'INVALID' else ()) | x)
    if v1_verdict == 'NOT_PASSED' or y:
        return 'NOT_PASSED', sorted(set(v1_blockers) | y)
    return 'SCIENTIFIC_PASS', []


def _disclosure(a):
    attempts = [{'sequence': e['sequence'], 'entry_sha256': e['entry_sha256'], 'run_id': e['run_id'],
                 'run_attempt': e['run_attempt'], 'phase': e['phase'],
                 'measurement_identity_sha256': e['measurement_identity_sha256'],
                 'science_identity_sha256': e['science_identity_sha256'],
                 **{k: a.classes[reg.run_key(e)][k] for k in ('class', 'outcome', 'conformance', 'violations')}}
                for e in a.entries]
    series = sorted(({'phase': i['phase'], 'science_identity_sha256': s, 'first_sequence': i['first_sequence'],
                      'state': i['state'], 'codes': i['codes']} for s, i in a.series.items()),
                    key=lambda i: (i['phase'], i['first_sequence']))
    unbound = [{k: u[k] for k in ('measurement_identity_sha256', 'run_id', 'run_attempt')} for u in a.unbound]
    return {'attempts': attempts, 'unbound_attempts': unbound, 'series': series,
            'transitions': [dict(t) for t in a.transitions]}


def _g1_core(identity, evaluation, analysis=None):
    """Contract 9.1 steps 0-10 (without the production activation gate) for measurement identity `identity`.
    Returns (core verdict, record body without verdict/authority/evaluator/record_sha256)."""
    a = analysis or analyze(evaluation)
    body = {'schema': 'delsk.oracle.g1-record.v1', 'g1_contract': reg.G1_CONTRACT,
            'measurement_contract': reg.MEASUREMENT_CONTRACT, 'measurement_identity_sha256': identity,
            'science_identity_sha256': None, 'main_head_sha': a.main_head_sha, 'registry_head': a.registry_head,
            'genesis_sha256': a.genesis_sha256, 'external_checkpoint': None}
    if a.blocker is not None:
        return 'NO_VERDICT', {**body, 'blockers': [a.blocker], 'attempts': [], 'unbound_attempts': [], 'series': [],
                              'transitions': []}
    body.update(_disclosure(a))
    mine = [e for e in a.entries if e['measurement_identity_sha256'] == identity]
    unbound = [u for u in a.unbound if u['measurement_identity_sha256'] == identity]
    if not mine and not unbound:
        return 'NOT_RUN', {**body, 'blockers': []}
    science = mine[0]['science_identity_sha256']
    records, missing, codes = [], [], set()
    for e in mine:
        c = a.classes[reg.run_key(e)]
        codes.update(c['violations'])
        if c['violations'] or c['class'] == 'BUNDLE':
            records.append(_v1_record(e, c['bundle']))
        elif c['class'] == 'MISSING':
            missing.append(reg.run_key(e))
    records += [_v1_record(u, None) for u in unbound]
    v1_verdict, v1_blockers = ev.g1(records)
    if v1_verdict != 'INVALID' and missing:
        v1_verdict, v1_blockers = 'NOT_PASSED', sorted({*v1_blockers, 'RESULT_MISSING'})
    if unbound:
        codes.add('UNBOUND_MEASUREMENT')
    codes |= series_codes(a, science, identity)
    if not {mine[0]['measured_source_sha'], a.evaluator_source_sha} <= a.kat_green:
        codes.add('KAT_NOT_VERIFIED')
    verdict, blockers = combine(v1_verdict, v1_blockers, codes)
    return verdict, {**body, 'science_identity_sha256': science, 'blockers': blockers}


def seal(record):
    return {**record, 'record_sha256': ev.hc(record)}


def g1_test(identity, evaluation, analysis=None):
    """Test wrapper (contract 11): never PASS; authority = evaluator = null. Returns (core verdict, record)."""
    verdict, body = _g1_core(identity, evaluation, analysis)
    return verdict, seal({**body, 'verdict': TEST_VERDICT.get(verdict, verdict), 'authority': None,
                          'evaluator': None})


# --- production -------------------------------------------------------------------------------------------------------

def g1_code_sha256():
    return ev.hc({p.name: ev.sha256(p.read_bytes()) for p in
                  (Path(__file__), Path(reg.__file__), Path(ev.__file__))})


def _production_record(verdict, body, evaluator_source_sha):
    """Production record from a core result over inputs production itself obtained from the authority constants.
    Before activation V2_NOT_ACTIVE joins NOT_PASSED-class codes (contract 9.1 item 10, 9.3); PASS needs the
    activation record."""
    blockers = list(body['blockers'])
    if ACTIVATION_RECORD is None and verdict in ('SCIENTIFIC_PASS', 'NOT_PASSED'):
        verdict, blockers = 'NOT_PASSED', sorted({*blockers, 'V2_NOT_ACTIVE'})
    if verdict == 'SCIENTIFIC_PASS':
        verdict = 'PASS'
    return seal({**body, 'verdict': verdict, 'blockers': blockers, 'authority': dict(reg.AUTHORITY),
                 'evaluator': {'g1_code_sha256': g1_code_sha256(), 'evaluator_source_sha': evaluator_source_sha}})


def g1_production(measurement_identity_sha256):
    """Contract 11 production entry point: exactly one parameter. Authority is hard-bound to the constants of
    contract 5.1; nothing (registry, remote, repository, results root, provider, snapshot, subset, records) can be
    injected. Not active (contract 16): no registry, provider, Git or evidence read is made and the result is
    NOT_PASSED V2_NOT_ACTIVE. C1-B wires the authority reads behind the activation record."""
    ev.check(type(measurement_identity_sha256) is str and ev.HEX64.match(measurement_identity_sha256) is not None,
             'G1 identity syntax')
    return 'NOT_PASSED', ['V2_NOT_ACTIVE']


# --- evidence root and bundle projection (contract 8.1, 8.4) ----------------------------------------------------------

def series_projection_sha256(directory):
    """SHA-256 of the canonical JSONL of every unsealed pair/standalone/target row without RUN_SPECIFIC keys."""
    rows = [r for name in ev.ROW_FILES for r in ev.parse_jsonl((Path(directory) / name).read_bytes())
            if r['schema'] in (ev.PAIR, ev.SOLO, ev.TARGET)]
    return ev.sha256(ev.jsonl(rows, ev.RUN_SPECIFIC))


def bundle_projection(directory):
    """bundle_projection of one retained bundle: v1 attempt_record (v1 verify inside) plus series projection.
    Unverifiable bundles project to bundle_verified = false; nothing is repaired."""
    directory = Path(directory)
    run_id, run_attempt = map(int, directory.name.split('-'))
    doc = {'run_id': run_id, 'run_attempt': run_attempt, 'bundle_verified': False, 'run': None, 'run_status': None,
           'measurement_identity_sha256': None, 'conformance': None, 'cost_projection_sha256': None,
           'targets_sha256': None, 'sealed_commitments_sha256': None, 'series_projection_sha256': None}
    try:
        record = ev.attempt_record(directory)  # checks the directory name against run.json
        if not record['bundle_verified']:
            return doc
        github = ev.parse_doc((directory / 'run.json').read_bytes())['github']
        complete = record['run_status'] == 'COMPLETE'
        return {**doc, 'bundle_verified': True, 'run_status': record['run_status'],
                'run': {k: github[k] for k in ('repository', 'run_id', 'run_attempt', 'sha', 'workflow_sha',
                                               'workflow_ref')},
                'measurement_identity_sha256': record['identity'], 'conformance': record['conformance'],
                'cost_projection_sha256': record['cost_projection_sha256'], 'targets_sha256': record['targets_sha256'],
                'sealed_commitments_sha256': record['sealed_commitments_sha256'],
                'series_projection_sha256': series_projection_sha256(directory) if complete else None}
    except (ev.EvalError, OSError, KeyError, TypeError, ValueError):
        return doc


def v1_root_keys(v1_root):
    """Run keys of the v1 root: bundle directories, .attempts sidecars and ledger entries. Raises when unreadable."""
    root, keys = Path(v1_root), set()
    if not root.exists():
        return keys
    for d in (root, root / '.attempts'):
        if d.is_dir():
            keys |= {tuple(map(int, p.name.split('-'))) for p in d.iterdir() if RUN_KEY.match(p.name)}
    if (root / ev.ATTEMPTS).exists():
        for a in ev.parse_doc((root / ev.ATTEMPTS).read_bytes())['attempts']:
            keys.add((a['run_id'], a['run_attempt']))
    return keys


def read_evidence_root(root, v1_root=V1_RESULTS):
    """Evidence of the v2 results root checked out from the pinned main tree. Every path outside
    bundles/<run_id>-<run_attempt>/ and bindings/<run_id>-<run_attempt>.json, every symlink and every unreadable,
    non-canonical or misnamed sidecar becomes a foreign path (EVIDENCE_ROOT_INVALID)."""
    root = Path(root)
    foreign, bundles, bindings = [], [], []
    for p in sorted(root.rglob('*')) if root.exists() else ():
        rel = p.relative_to(root).as_posix()
        parts = rel.split('/')
        if p.is_symlink():
            foreign.append(rel)
        elif len(parts) == 1:
            if parts[0] not in ('bundles', 'bindings') or not p.is_dir():
                foreign.append(rel)
        elif parts[0] == 'bundles' and len(parts) == 2:
            if p.is_dir() and RUN_KEY.match(parts[1]):
                bundles.append(bundle_projection(p))
            else:
                foreign.append(rel)
        elif parts[0] == 'bindings':
            name = parts[1][:-len('.json')] if parts[1].endswith('.json') else ''
            try:
                doc = ev.parse_doc(p.read_bytes()) if len(parts) == 2 and RUN_KEY.match(name) else None
            except (ev.EvalError, OSError, ValueError, UnicodeDecodeError):
                doc = None
            if type(doc) is dict and reg.valid(doc, 'attempt_binding') and \
                    f"{doc['run_id']}-{doc['run_attempt']}" == name:
                bindings.append(doc)
            else:
                foreign.append(rel)
    try:
        v1_keys = v1_root_keys(v1_root)
    except (ev.EvalError, OSError, KeyError, TypeError, ValueError, UnicodeDecodeError):
        foreign.append(Path(v1_root).as_posix())
        v1_keys = set()
    return Evidence.build(bundles, bindings, foreign, sorted(v1_keys))


# --- KAT gate (contract 9.1 item 10) ----------------------------------------------------------------------------------

def _git(root, *args):
    return subprocess.run(['git', '-c', f'safe.directory={Path(root).as_posix()}', *args], cwd=root,
                          capture_output=True, check=False)


def kat_verified_v2(get, sha, main_head_sha, kat_step, root=ev.ROOT):
    """Green exact-commit KAT evidence for commit `sha` evaluated at the pinned main_head_sha: sha is ancestor-or-equal
    main_head_sha; at sha the reviewed oracle-smoke.yml (as in main_head_sha), v1 freeze.json with every v1 frozen
    file and freeze-v2.json with every provenance_layer file are byte-identical; and the Actions API shows a green KAT
    step (named by the activation record) for sha with no red or pending attempt. Called for both the evaluator and the
    measured commit; anything unverifiable is not green. get must be bound to the constant provider API."""
    try:
        oa.check(kat_step is not None and oa.digest(sha, 40) and oa.digest(main_head_sha, 40), 'KAT inputs')
        oa.check(_git(root, 'merge-base', '--is-ancestor', sha, main_head_sha).returncode == 0, 'off pinned main')

        def same(path):
            return oa._git_show(root, sha, path) == oa._git_show(root, main_head_sha, path)

        oa.check(same(oa.SMOKE_WORKFLOW), 'smoke workflow differs from the pinned main')
        for freeze_path, layer in (('.work/oracle/freeze.json', None), ('.work/oracle/freeze-v2.json',
                                                                         'provenance_layer')):
            oa.check(same(freeze_path), f'{freeze_path} differs from the pinned main')
            freeze = ev.parse_doc(oa._git_show(root, main_head_sha, freeze_path))
            files = freeze[layer]['files'] if layer else freeze['files']
            oa.check(all(ev.sha256(oa._git_show(root, sha, p)) == d for p, d in files.items()), 'frozen file differs')
        oa.check(ev.sha256(oa._git_show(root, main_head_sha, '.work/oracle/freeze.json')) ==
                 reg.MEASUREMENT_FREEZE_SHA256, 'v1 freeze differs from contract-v2 section 1')
        return oa.kat_actions_green(get, reg.REPOSITORY, sha, kat_step)
    except Exception:  # unverifiable evidence is never green
        return False


# --- runner-level decisions (contract 5.7, 5.8): pure, no Git write ---------------------------------------------------

def _register_check_core(genesis, entries, execution, git, pull_requests, transition_bytes=None,
                         g1_freeze_sha256=None):
    """Pure register decision. Synthetic callers may omit the freeze digest; authoritative callers never do."""
    x = execution
    if not (x['event'] == 'workflow_dispatch' and x['repository'] == reg.REPOSITORY and x['sha'] == x['workflow_sha']
            and oa.digest(x['sha'], 40) and oa.positive(x['run_id']) and oa.positive(x['run_attempt']) and re.search(
                reg._SCHEMAS['$defs']['registry_entry']['properties']['workflow_ref']['pattern'], x['workflow_ref'])):
        return 'DISPATCH_REJECTED', None
    if not git.on_main(x['sha']):
        return 'SOURCE_NOT_ON_MAIN', None
    mi = git.identity(x['sha'])
    if mi is None:
        return 'DISPATCH_REJECTED', None
    try:
        reg.validate(genesis, entries, git, g1_freeze_sha256)
    except reg.RegistryInvalid:
        return 'REGISTRY_INVALID', None
    if reg.duplicate_keys(entries):
        return 'REGISTRY_DUPLICATE', None
    key = (x['run_id'], x['run_attempt'])
    existing = [e for e in entries if reg.run_key(e) == key]
    if existing:  # idempotent retry after a lost push response
        code, mine = _register_check_core(genesis, entries[:existing[0]['sequence'] - 1], execution, git,
                                          pull_requests, transition_bytes, g1_freeze_sha256)
        same = code == 'APPENDED' and all(mine[k] == existing[0][k] for k in mine
                                          if k not in ('sequence', 'previous_entry_sha256', 'entry_sha256'))
        return ('APPENDED', existing[0]) if same else ('REGISTRY_DUPLICATE', None)
    science = ev.hc(reg.science_identity(mi))
    phase = [e for e in entries if e['phase'] == mi['phase']]
    transition = None
    if phase and all(e['science_identity_sha256'] != science for e in phase):
        if transition_bytes is None:
            return 'TRANSITION_REQUIRED', None
        _, _, current = series_machine(entries, git, _unique(pull_requests, lambda p: p['number']))
        try:
            transition = ev.parse_doc(transition_bytes)
        except (ev.EvalError, ValueError, UnicodeDecodeError):
            return 'TRANSITION_INVALID', None
        if not (reg.valid(transition, 'series_transition') and reg.self_digest_ok(transition, 'transition_sha256')
                and transition['phase'] == mi['phase'] and transition['new_science_identity_sha256'] == science
                and transition['previous_science_identity_sha256'] == current.get(mi['phase'])
                and git.ancestor_or_equal(transition['change_review']['merge_commit_sha'], x['sha'])):
            return 'TRANSITION_INVALID', None
    return 'APPENDED', reg.make_entry(genesis, entries, run_id=x['run_id'], run_attempt=x['run_attempt'],
                                      measured_source_sha=x['sha'], workflow_ref=x['workflow_ref'],
                                      measurement_identity=mi, transition=transition)


def register_check(registry_commits, execution, git, pull_requests, transition_bytes=None):
    """Authoritative register decision; raw registry history is physically and logically validated inside."""
    try:
        snapshot = reg.authoritative_registry(registry_commits, git)
        genesis, entries = reg.physical_objects(snapshot)
    except (reg.RegistryInvalid, TypeError):
        return 'REGISTRY_INVALID', None
    return _register_check_core(genesis, entries, execution, git, pull_requests, transition_bytes,
                                reg.G1_FREEZE_SHA256)


def register_check_test(genesis, entries, execution, git, pull_requests, transition_bytes=None):
    """Synthetic-only runner-vector decision; the frozen synthetic genesis intentionally has a non-production digest."""
    return _register_check_core(genesis, entries, execution, git, pull_requests, transition_bytes, None)


def _bind_check_core(genesis, entries, execution, git, register_entry_sha256, g1_freeze_sha256=None):
    """Pure bind decision used by the authoritative wrapper and frozen synthetic vectors."""
    x = execution
    try:
        registry_head = reg.validate(genesis, entries, git, g1_freeze_sha256)
    except reg.RegistryInvalid:
        return 'REGISTRY_UNBOUND', None
    mine = [e for e in entries if reg.run_key(e) == (x['run_id'], x['run_attempt'])]
    mi = git.identity(x['sha'])
    if reg.duplicate_keys(entries) or len(mine) != 1 or mi is None:
        return 'REGISTRY_UNBOUND', None
    e = mine[0]
    if (e['measured_source_sha'], e['workflow_sha'], e['workflow_ref'], e['measurement_identity_sha256'],
            e['science_identity_sha256'], e['phase'], e['entry_sha256']) != (
            x['sha'], x['workflow_sha'], x['workflow_ref'], ev.hc(mi), ev.hc(reg.science_identity(mi)), mi['phase'],
            register_entry_sha256):
        return 'REGISTRY_UNBOUND', None
    binding = {'schema': 'delsk.oracle.attempt-binding.v1', 'g1_contract': reg.G1_CONTRACT,
               'repository': reg.REPOSITORY, 'run_id': e['run_id'], 'run_attempt': e['run_attempt'],
               'measured_source_sha': e['measured_source_sha'],
               'measurement_identity_sha256': e['measurement_identity_sha256'], 'entry_sequence': e['sequence'],
               'entry_sha256': e['entry_sha256'], 'observed_head': registry_head}
    return 'BOUND', {**binding, 'binding_sha256': ev.hc(binding)}


def bind_check(registry_commits, execution, git, register_entry_sha256):
    """Authoritative bind decision; raw registry history is validated again before binding."""
    try:
        snapshot = reg.authoritative_registry(registry_commits, git)
        genesis, entries = reg.physical_objects(snapshot)
    except (reg.RegistryInvalid, TypeError):
        return 'REGISTRY_UNBOUND', None
    return _bind_check_core(genesis, entries, execution, git, register_entry_sha256, reg.G1_FREEZE_SHA256)


def bind_check_test(genesis, entries, execution, git, register_entry_sha256):
    """Synthetic-only bind decision for frozen runner vectors."""
    return _bind_check_core(genesis, entries, execution, git, register_entry_sha256, None)
