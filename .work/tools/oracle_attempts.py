"""Independent Slice C0 all-dispatch inventory and reviewed retention (stdlib only).

No measurements, workflow dispatches, artifact downloads or Git writes. API history is
read from workflow inception, twice, without date/event filters. Source identities must
come from immutable commit manifests, never uploaded run.json. Every rerun attempt is
queried separately. Deleted/gapped/changing/unresolved history fails closed.

    oracle_attempts.py inventory REPOSITORY OUT.json
    oracle_attempts.py reconcile SNAPSHOT.json RESULTS [BASE_RESULTS]
    oracle_attempts.py retain ENVELOPE RESULTS
    oracle_attempts.py audit RESULTS BASE_RESULTS
    oracle_attempts.py audit-base BASE_SHA [RESULTS]
    oracle_attempts.py g1 IDENTITY [RESULTS]

Snapshots and sidecars are outside the evaluator's closed normative bundle. The
append-only ledger records dispatches; sidecars cannot turn an absent bundle into a
verified attempt. A production G1 reads the independent live API before evaluation.
"""
import datetime as dt
import gzip
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile

import budget
import oracle_eval as ev

WORKFLOW = '.github/workflows/oracle-pilot.yml'
LEDGER_SCHEMA = 'delsk.oracle.attempts.v1'
SNAPSHOT_SCHEMA = 'delsk.oracle.inventory.v1'
SIDECAR_SCHEMA = 'delsk.oracle.attempt.v1'
LEDGER_KEYS = frozenset(('measurement_identity_sha256', 'run_id', 'run_attempt', 'repository',
                         'run_number', 'measured_source_sha', 'workflow_sha', 'workflow_ref',
                         'workflow_id', 'created_at', 'status'))
OBSERVATION_KEYS = LEDGER_KEYS | {'github_status', 'conclusion', 'updated_at', 'run_started_at'}
RUN_KEYS = frozenset(('run_id', 'run_number', 'run_attempt', 'event', 'head_sha', 'head_branch',
                      'path', 'workflow_id', 'created_at', 'updated_at', 'run_started_at',
                      'github_status', 'conclusion'))
SNAPSHOT_KEYS = frozenset(('schema', 'repository', 'workflow', 'workflow_id', 'workflow_created_at',
                           'collected_at', 'runs', 'attempts', 'snapshot_sha256'))
SIDECAR_KEYS = frozenset(('schema', 'repository', 'run_id', 'run_attempt', 'measured_source_sha',
                          'workflow_sha', 'workflow_ref', 'measurement_identity_sha256',
                          'status', 'phase', 'failure_class', 'admission', 'created_at', 'updated_at'))
STATUSES = frozenset(('REGISTERED', 'FAILED', 'NOT_ADMITTED', 'READY', 'ORACLE_FINISHED', 'COMPLETE',
                      'INCOMPLETE', 'INVALID', 'BUILD_FAILED', 'CONFORMANCE_FAILED',
                      'MATERIALIZATION_FAILED', 'ARTIFACT_UPLOAD_FAILED', 'DISPATCH_REJECTED',
                      'TIMEOUT', 'CANCELLED', 'INFRASTRUCTURE_FAILED'))
PHASES = frozenset(('bootstrap', 'setup', 'build', 'conformance', 'materialize', 'verify',
                    'admission', 'register', 'oracle', 'finalize', 'export', 'upload', 'finished',
                    'dispatch', 'frozen_bindings', 'codec_build', 'materialization', 'premeasurement',
                    'oracle_finished', 'recovery', 'infrastructure', 'artifact_upload',
                    'synthetic_premeasurement'))
FAILURES = frozenset(('SOURCE_MISMATCH', 'WORKFLOW_MISMATCH', 'DISPATCH_REJECTED', 'SETUP_FAILED',
                      'BUILD_FAILED', 'CONFORMANCE_FAILED', 'MATERIALIZATION_FAILED', 'VERIFY_FAILED',
                      'BUDGET_REFUSED', 'ARTIFACT_CAP', 'ADMISSION_FAILED', 'ORACLE_FAILED',
                      'FINALIZE_FAILED', 'EXPORT_FAILED', 'ARTIFACT_UPLOAD_FAILED', 'TIMEOUT',
                      'CANCELLED', 'INFRASTRUCTURE_FAILED', 'RESOURCE_LIMIT', 'INPUT_INTEGRITY',
                      'ATTEMPT_NOT_RETAINED', 'DISK_ADMISSION_REFUSED', 'STALE_WORKDIR', 'PROCESS_WALL_TIMEOUT',
                      'RUNNER_KILLED', 'WORKLOAD_FAILED', 'EXPORT_UNSAFE', 'ARTIFACT_SIZE_CAP',
                      'BUNDLE_VERIFICATION_FAILED', 'PILOT_GATE_MISSING', 'PILOT_GATE_MISMATCH',
                      'CODEC_BUILD_FAILED', 'FROZEN_BINDING', 'SYNTHETIC_INCOMPLETE', 'SOURCE_FETCH_FAILED',
                      'SOURCE_IDENTITY_MISMATCH', 'ARCHIVE_UNSAFE', 'EXPANSION_CAP', 'OBJECT_INTEGRITY',
                      'OBJECT_SET_MISMATCH', 'DISPATCH_HISTORY_UNVERIFIED'))
FAILURE_CLASSES = FAILURES  # supervisor's public machine vocabulary
API_STATUSES = frozenset(('queued', 'in_progress', 'completed', 'waiting', 'pending', 'requested'))
API_CONCLUSIONS = frozenset(('success', 'failure', 'neutral', 'cancelled', 'skipped', 'timed_out',
                             'action_required', 'stale', 'startup_failure'))
MAX_AGE_SECONDS = 3600
SMOKE_WORKFLOW = '.github/workflows/oracle-smoke.yml'
KAT_JOB = 'smoke'
KAT_STEP = 'Oracle tests (contract, production KAT/G1, mutants, metamorphic, faults, pinned codecs)'
KAT_EVENTS = frozenset(('push', 'workflow_dispatch'))


class AttemptError(ev.EvalError):
    """Infrastructure evidence incomplete or inconsistent. No sealed data in errors."""


def check(ok, reason):
    if not ok:
        raise AttemptError(reason)


def timestamp(value):
    check(type(value) is str, 'timestamp type')
    try:
        parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
        check(parsed.utcoffset() == dt.timedelta(0), 'timestamp must be UTC')
        return parsed
    except (ValueError, TypeError) as error:
        raise AttemptError('invalid timestamp') from error


def utc(now=None):
    value = now or dt.datetime.now(dt.timezone.utc)
    check(value.tzinfo is not None, 'clock must be timezone-aware')
    return value.astimezone(dt.timezone.utc).replace(microsecond=0)


def positive(value):
    return type(value) is int and 0 < value < ev.INT_LIMIT


def digest(value, size=64):
    return type(value) is str and re.fullmatch('[0-9a-f]{' + str(size) + '}', value) is not None


def repository(value):
    return type(value) is str and re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', value) is not None


def key(entry):
    return entry['run_id'], entry['run_attempt']


def workflow_ref(repo, branch):
    check(type(branch) is str and branch and not any(c in branch for c in '\n\r\x00'), 'workflow branch')
    return f'{repo}/{WORKFLOW}@refs/heads/{branch}'


def _run(doc, repo, workflow_id):
    check(type(doc) is dict, 'run metadata missing')
    check(all(positive(doc.get(k)) for k in ('id', 'run_number', 'run_attempt', 'workflow_id')),
          'run metadata integers')
    check(doc['workflow_id'] == workflow_id, 'workflow ID mismatch')
    check(doc.get('repository', {}).get('full_name') == repo and
          doc.get('head_repository', {}).get('full_name') == repo, 'foreign repository')
    check(digest(doc.get('head_sha'), 40), 'run source SHA')
    ref = workflow_ref(repo, doc.get('head_branch'))
    check(doc.get('path') in (WORKFLOW, ref.split('/', 2)[2]), 'workflow path/ref mismatch')
    check(type(doc.get('event')) is str and doc['event'], 'run event missing')
    check(doc.get('status') in API_STATUSES and doc.get('conclusion') in API_CONCLUSIONS | {None},
          'run API status')
    check((doc['status'] == 'completed') == (doc['conclusion'] is not None), 'partial run completion')
    for name in ('created_at', 'updated_at'):
        timestamp(doc.get(name))
    if doc.get('run_started_at') is not None:
        timestamp(doc['run_started_at'])
    return dict(run_id=doc['id'], run_number=doc['run_number'], run_attempt=doc['run_attempt'],
                event=doc['event'], head_sha=doc['head_sha'], head_branch=doc['head_branch'],
                path=doc['path'], workflow_id=doc['workflow_id'], created_at=doc['created_at'],
                updated_at=doc['updated_at'], run_started_at=doc.get('run_started_at'),
                github_status=doc['status'], conclusion=doc['conclusion'])


def _history(get, repo, workflow_id):
    rows = budget.paged(get, f'/repos/{repo}/actions/workflows/oracle-pilot.yml/runs', 'workflow_runs')
    runs = sorted((_run(r, repo, workflow_id) for r in rows), key=lambda r: r['run_number'])
    check([r['run_number'] for r in runs] == list(range(1, len(runs) + 1)), 'run_number gap/deleted history')
    check(len({r['run_id'] for r in runs}) == len(runs), 'duplicate workflow run')
    return runs


def inventory(get, repo, resolve_source, now=None):
    """get(path)->API dict; resolve_source(head_sha, exact_workflow_ref)->four-key source binding.

    No artifacts are needed for discovering a destroyed/cancelled runner. Any inability
    to derive a dispatch identity or read any attempt prevents a complete snapshot.
    """
    check(repository(repo), 'repository syntax')
    check(callable(resolve_source), 'immutable source resolver required')
    try:
        workflow_path = f'/repos/{repo}/actions/workflows/oracle-pilot.yml'
        workflow = get(workflow_path)
        check(workflow['path'] == WORKFLOW and positive(workflow['id']), 'workflow identity')
        timestamp(workflow['created_at'])
        runs = _history(get, repo, workflow['id'])
        attempts = []
        for run in runs:
            if run['event'] != 'workflow_dispatch':
                continue
            ref = workflow_ref(repo, run['head_branch'])
            binding = resolve_source(run['head_sha'], ref)
            check(type(binding) is dict and set(binding) == {'measurement_identity_sha256',
                  'measured_source_sha', 'workflow_sha', 'workflow_ref'}, 'unresolved source identity')
            check(digest(binding['measurement_identity_sha256']) and
                  binding['measured_source_sha'] == binding['workflow_sha'] == run['head_sha'] and
                  binding['workflow_ref'] == ref, 'source/workflow identity mismatch')
            for number in range(1, run['run_attempt'] + 1):
                path = f"/repos/{repo}/actions/runs/{run['run_id']}/attempts/{number}"
                attempt = _run(get(path), repo, workflow['id'])
                check(attempt['run_attempt'] == number and all(attempt[k] == run[k] for k in
                      ('run_id', 'run_number', 'event', 'head_sha', 'head_branch', 'path', 'workflow_id',
                       'created_at')), 'attempt metadata mismatch')
                check(_run(get(path), repo, workflow['id']) == attempt, 'attempt changed during inventory')
                attempts.append(dict(binding, repository=repo, run_id=run['run_id'], run_attempt=number,
                                     run_number=run['run_number'], workflow_id=workflow['id'],
                                     created_at=run['created_at'], status='DISPATCHED',
                                     **{k: attempt[k] for k in ('github_status', 'conclusion', 'updated_at',
                                                              'run_started_at')}))
        check(_history(get, repo, workflow['id']) == runs and get(workflow_path) == workflow,
              'workflow history changed during inventory')
        out = dict(schema=SNAPSHOT_SCHEMA, repository=repo, workflow=WORKFLOW, workflow_id=workflow['id'],
                   workflow_created_at=workflow['created_at'], collected_at=utc(now).isoformat(),
                   runs=runs, attempts=attempts)
        out['snapshot_sha256'] = ev.hc(out)
        validate_snapshot(out)
        return out
    except AttemptError:
        raise
    except Exception as error:
        raise AttemptError('incomplete independent API inventory') from error


def validate_entry(entry):
    check(type(entry) is dict and set(entry) == LEDGER_KEYS, 'attempt ledger closed fields')
    check(all(positive(entry[k]) for k in ('run_id', 'run_attempt', 'run_number', 'workflow_id')),
          'attempt ledger integer')
    check(digest(entry['measurement_identity_sha256']) and digest(entry['measured_source_sha'], 40) and
          entry['measured_source_sha'] == entry['workflow_sha'], 'attempt source identity')
    check(repository(entry['repository']) and type(entry['workflow_ref']) is str and
          entry['workflow_ref'].startswith(f"{entry['repository']}/{WORKFLOW}@refs/heads/") and
          entry['workflow_ref'] != f"{entry['repository']}/{WORKFLOW}@refs/heads/", 'attempt workflow ref')
    check(entry['status'] == 'DISPATCHED', 'attempt dispatch status')
    timestamp(entry['created_at'])


def validate_snapshot(doc, now=None, max_age_seconds=None):
    check(type(doc) is dict and set(doc) == SNAPSHOT_KEYS and doc['schema'] == SNAPSHOT_SCHEMA,
          'inventory closed schema')
    check(digest(doc['snapshot_sha256']) and ev.hc({k: v for k, v in doc.items() if k != 'snapshot_sha256'}) ==
          doc['snapshot_sha256'], 'inventory hash mismatch')
    check(repository(doc['repository']) and doc['workflow'] == WORKFLOW and positive(doc['workflow_id']),
          'inventory workflow identity')
    timestamp(doc['workflow_created_at'])
    collected = timestamp(doc['collected_at'])
    if max_age_seconds is not None:
        check(0 <= (utc(now) - collected).total_seconds() <= max_age_seconds, 'stale/future inventory')
    check(type(doc['runs']) is list and type(doc['attempts']) is list, 'inventory list type')
    check(all(type(r) is dict and set(r) == RUN_KEYS for r in doc['runs']), 'inventory run closed fields')
    check([r['run_number'] for r in doc['runs']] == list(range(1, len(doc['runs']) + 1)),
          'inventory run gap/deleted history')
    runs = {r['run_id']: r for r in doc['runs']}
    check(len(runs) == len(doc['runs']), 'inventory repeated run')
    expected = [(r['run_id'], a) for r in doc['runs'] if r['event'] == 'workflow_dispatch'
                for a in range(1, r['run_attempt'] + 1)]
    check([key(a) for a in doc['attempts']] == expected, 'inventory incomplete attempt set')
    for r in doc['runs']:
        raw = {**r, 'id': r['run_id'], 'status': r['github_status'],
               'repository': {'full_name': doc['repository']}, 'head_repository': {'full_name': doc['repository']}}
        check(_run(raw, doc['repository'], doc['workflow_id']) == r, 'inventory run metadata')
    for a in doc['attempts']:
        check(type(a) is dict and set(a) == OBSERVATION_KEYS, 'inventory attempt closed fields')
        validate_entry({k: a[k] for k in LEDGER_KEYS})
        r = runs[a['run_id']]
        check(a['repository'] == doc['repository'] and a['workflow_id'] == doc['workflow_id'] and
              a['run_number'] == r['run_number'] and a['created_at'] == r['created_at'] and
              a['measured_source_sha'] == r['head_sha'] and a['workflow_ref'] ==
              workflow_ref(doc['repository'], r['head_branch']), 'inventory binding mismatch')
        check(a['github_status'] in API_STATUSES and a['conclusion'] in API_CONCLUSIONS | {None} and
              ((a['github_status'] == 'completed') == (a['conclusion'] is not None)), 'inventory API status')
        timestamp(a['updated_at'])
        if a['run_started_at'] is not None:
            timestamp(a['run_started_at'])
    return doc


def audit_ledger(doc, base=None):
    check(type(doc) is dict and set(doc) == {'schema', 'attempts'} and doc['schema'] == LEDGER_SCHEMA and
          type(doc['attempts']) is list, 'attempt ledger closed schema')
    for a in doc['attempts']:
        validate_entry(a)
    entries = {key(a): a for a in doc['attempts']}
    check(len(entries) == len(doc['attempts']), 'attempt ledger duplicate')
    if base is not None:
        audit_ledger(base)
        check(doc['attempts'][:len(base['attempts'])] == base['attempts'], 'attempt ledger deletion/rebinding/edit')
    return entries


def reconcile(snapshot, ledger, base_ledger=None):
    """Return a new ledger only after all checks. Existing entry bytes/ordering are immutable."""
    validate_snapshot(snapshot)
    entries = audit_ledger(ledger, base_ledger)
    observed = {key(a): {k: a[k] for k in LEDGER_KEYS} for a in snapshot['attempts']}
    check(set(entries) <= set(observed), 'previous dispatch disappeared from API history')
    check(all(a == observed[k] for k, a in entries.items()), 'dispatch identity rebound')
    return dict(schema=LEDGER_SCHEMA, attempts=[*ledger['attempts'],
                *(observed[key(a)] for a in snapshot['attempts'] if key(a) not in entries)])


def _read(path):
    return ev.parse_doc(Path(path).read_bytes())


def _write_atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f'.{path.name}.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def import_snapshot(snapshot, results, base_results=None):
    """Stage snapshot+ledger as a single evidence root replacement; fail before any publication.

    Snapshot files never change. Files already present are copied unchanged. This is an
    offline reviewed-PR operation and must not race another evidence writer.
    """
    results = Path(results)
    old = _read(results / 'attempts.json') if (results / 'attempts.json').exists() else dict(
        schema=LEDGER_SCHEMA, attempts=[])
    base = _read(Path(base_results) / 'attempts.json') if base_results is not None else None
    new = reconcile(snapshot, old, base)
    if base_results is not None:
        audit_root(results, base_results)
    relative = Path('.inventory') / f"{snapshot['snapshot_sha256']}.json"
    data = ev.canonical(snapshot)
    if (results / relative).exists():
        check((results / relative).read_bytes() == data, 'immutable inventory was altered')
    results.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f'.{results.name}.inventory.', dir=results.parent))
    backup = results.with_name(f'.{results.name}.previous')
    check(not backup.exists(), 'unfinished evidence transaction')
    try:
        if results.exists():
            _no_links(results)
            shutil.copytree(results, stage, dirs_exist_ok=True)
        (stage / relative).parent.mkdir(parents=True, exist_ok=True)
        (stage / relative).write_bytes(data)
        (stage / 'inventory.json').write_bytes(data)
        (stage / 'attempts.json').write_bytes(ev.canonical(new))
        if results.exists():
            results.rename(backup)
        try:
            stage.rename(results)
        except BaseException:
            if backup.exists():
                backup.rename(results)
            raise
        shutil.rmtree(backup, ignore_errors=True)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    return new


def _no_links(root):
    root = Path(root)
    for p in [root, *root.rglob('*')]:
        mode = p.lstat()
        check(not stat.S_ISLNK(mode.st_mode) and not getattr(mode, 'st_file_attributes', 0) & 0x400 and
              (stat.S_ISREG(mode.st_mode) or stat.S_ISDIR(mode.st_mode)), 'evidence contains unsafe entry')


def audit_root(results, base_results=None):
    """CI compares committed PR root against the authoritative base checkout; no deleting failures."""
    results = Path(results)
    if not results.exists():
        check(base_results is None or not Path(base_results).exists(), 'retained evidence root deleted')
        return True  # the initial NOT_RUN state has no evidence directory
    _no_links(results)
    if base_results is not None:
        base_results = Path(base_results)
        _no_links(base_results)
        audit_ledger(_read(results / 'attempts.json'), _read(base_results / 'attempts.json'))
        for prior in base_results.rglob('*'):
            if not prior.is_file() or prior.relative_to(base_results).as_posix() in ('attempts.json', 'inventory.json'):
                continue
            target = results / prior.relative_to(base_results)
            check(target.is_file() and target.read_bytes() == prior.read_bytes(), 'retained evidence deletion/edit')
    else:
        audit_ledger(_read(results / 'attempts.json'))
    snap = _read(results / 'inventory.json') if (results / 'inventory.json').exists() else None
    if snap is not None:
        validate_snapshot(snap)
        check((results / '.inventory' / f"{snap['snapshot_sha256']}.json").read_bytes() == ev.canonical(snap),
              'inventory pointer lacks immutable snapshot')
        check(reconcile(snap, _read(results / 'attempts.json')) == _read(results / 'attempts.json'),
              'ledger misses dispatched attempts')
    else:
        check(not _read(results / 'attempts.json')['attempts'], 'nonempty ledger lacks inventory')
    return True


def audit_git(base_commit, results=ev.RESULTS):
    """Read the authoritative PR base Git tree; never run a shell, fetch, or write Git."""
    check(digest(base_commit, 40), 'audit base must be immutable lowercase SHA')
    results = Path(results)
    prefix = '.work/results/DELSK-003-ORACLE/'
    git = ['git', '-c', f'safe.directory={ev.ROOT.as_posix()}']
    def read(*args):
        proc = subprocess.run([*git, *args], cwd=ev.ROOT, capture_output=True, check=False)
        check(proc.returncode == 0, 'base evidence unavailable')
        return proc.stdout
    names = read('ls-tree', '-rz', '--name-only', base_commit, '--', prefix).split(b'\x00')
    base = None
    for raw in names:
        if not raw:
            continue
        name = raw.decode('utf-8')
        check(name.startswith(prefix), 'base evidence path outside root')
        rel = name[len(prefix):]
        check(rel and not any(p in ('..', '.') for p in Path(rel).parts), 'base evidence unsafe path')
        data = read('show', f'{base_commit}:{name}')
        if rel == 'attempts.json':
            base = ev.parse_doc(data)
        elif rel != 'inventory.json':
            current = results / rel
            check(current.is_file() and current.read_bytes() == data, 'retained base evidence deletion/edit')
    if not results.exists():
        check(base is None and not any(names), 'retained base evidence root deleted')
        return True
    current = _read(results / 'attempts.json')
    audit_ledger(current, base or dict(schema=LEDGER_SCHEMA, attempts=[]))
    return audit_root(results)


def create_attempt(env, identity_sha256=None, status='REGISTERED', phase='bootstrap', failure_class=None,
                   admission='UNKNOWN', now=None):
    """Closed infrastructure sidecar; no arbitrary exception string, payload cost or command output."""
    value = utc(now).isoformat()
    try:
        doc = dict(schema=SIDECAR_SCHEMA, repository=env['GITHUB_REPOSITORY'],
                   run_id=int(env['GITHUB_RUN_ID']), run_attempt=int(env['GITHUB_RUN_ATTEMPT']),
                   measured_source_sha=env['GITHUB_SHA'], workflow_sha=env['GITHUB_WORKFLOW_SHA'],
                   workflow_ref=env['GITHUB_WORKFLOW_REF'], measurement_identity_sha256=identity_sha256,
                   status=status, phase=phase, failure_class=failure_class, admission=admission,
                   created_at=value, updated_at=value)
    except (KeyError, TypeError, ValueError) as error:
        raise AttemptError('dispatch environment incomplete') from error
    validate_sidecar(doc)
    return doc


def validate_sidecar(doc):
    check(type(doc) is dict and set(doc) == SIDECAR_KEYS and doc['schema'] == SIDECAR_SCHEMA,
          'attempt sidecar closed schema')
    check(repository(doc['repository']) and positive(doc['run_id']) and positive(doc['run_attempt']),
          'attempt sidecar dispatch identity')
    check(digest(doc['measured_source_sha'], 40) and digest(doc['workflow_sha'], 40) and
          _sidecar_workflow_ref(doc['repository'], doc['workflow_ref']), 'attempt sidecar source/ref')
    check(doc['measurement_identity_sha256'] is None or digest(doc['measurement_identity_sha256']),
          'attempt sidecar measurement identity')
    check(doc['status'] in STATUSES and doc['phase'] in PHASES and doc['failure_class'] in FAILURES | {None} and
          doc['admission'] in ('UNKNOWN', 'ADMITTED', 'REFUSED'), 'attempt sidecar machine status')
    check(timestamp(doc['updated_at']) >= timestamp(doc['created_at']), 'attempt sidecar timestamps')
    return doc


def _sidecar_workflow_ref(repo, ref):
    """Smoke sidecars describe the synthetic PR/push/dispatch lane only.

    Production inventory and _bind_sidecar still require the independently resolved
    exact pilot workflow ref; accepting smoke metadata here never admits it to G1.
    """
    if type(ref) is not str:
        return False
    if ref.startswith(f'{repo}/{WORKFLOW}@refs/'):
        return True
    prefix = f'{repo}/.github/workflows/oracle-smoke.yml@'
    if not ref.startswith(prefix):
        return False
    suffix = ref[len(prefix):]
    if re.fullmatch(r'refs/pull/[1-9][0-9]*/merge', suffix):
        return True
    named = re.fullmatch(r'refs/(?:heads|tags)/(.+)', suffix)
    if named is None:
        return False
    name = named[1]
    return (not any(ord(c) <= 32 or ord(c) == 127 or c in '~^:?*[\\' for c in name) and
            not any(token in name for token in ('..', '//', '@{')) and not name.endswith('.') and
            all(part and not part.startswith('.') and not part.endswith('.lock') for part in name.split('/')))


def update_attempt(path, status, phase, failure_class=None, admission=None, now=None):
    doc = validate_sidecar(_read(path))
    doc.update(status=status, phase=phase, failure_class=failure_class, updated_at=utc(now).isoformat())
    if admission is not None:
        doc['admission'] = admission
    validate_sidecar(doc)
    _write_atomic(path, ev.canonical(doc))
    return doc


def _bind_sidecar(doc, entry):
    validate_sidecar(doc)
    for name in ('repository', 'run_id', 'run_attempt', 'measured_source_sha', 'workflow_sha', 'workflow_ref'):
        check(doc[name] == entry[name], 'attempt sidecar dispatch binding mismatch')
    check(doc['measurement_identity_sha256'] in (None, entry['measurement_identity_sha256']),
          'attempt sidecar measurement binding mismatch')


def check_bundle_binding(directory, entry):
    run = _read(Path(directory) / 'run.json')
    gh = run['github']
    check(run['measurement_identity_sha256'] == entry['measurement_identity_sha256'] and
          run['measurement_identity']['phase'] == 'pilot' and
          run['measurement_identity']['measured_source_sha'] == entry['measured_source_sha'],
          'bundle measurement identity mismatch')
    check(all(gh[k] == entry[k] for k in ('repository', 'run_id', 'run_attempt', 'workflow_sha', 'workflow_ref')) and
          gh['sha'] == entry['measured_source_sha'], 'bundle dispatch binding mismatch')


def _materialization(doc, entry):
    """Default envelope provenance binding. A caller may supply a stricter adapter validator."""
    wanted = {'schema', 'measurement_identity_sha256', 'measured_source_sha', 'workflow_sha',
              'run_id', 'run_attempt', 'provenance', 'verification'}
    check(type(doc) is dict and set(doc) == wanted and doc['schema'] == 'delsk.oracle.materialization-evidence.v1',
          'materialization provenance schema')
    check(all(doc.get(k) == entry[k] for k in ('measurement_identity_sha256', 'measured_source_sha', 'workflow_sha',
                                             'run_id', 'run_attempt')), 'materialization provenance binding')
    check(type(doc['provenance']) is dict and type(doc['verification']) is dict,
          'materialization provenance/verification missing')
    # Metadata only: no fetching or construction. The verifier's exact expected
    # object universe includes the identity-only witnesses as well as candidates.
    import oracle_materialize as materializer
    candidate, corpus, sources, policy = materializer.load_natural()
    expected = materializer.expected_objects(candidate, corpus)
    occurrences = {o['occurrence_id']: o for o in corpus['occurrences']}
    required = set()
    for q in candidate['queries']:
        required.add(q['target'])
        if q['status'] == 'identity_only':
            required.add(q['duplicate_of'])
        required.update(b['representative'] for b in q['bases'])
    verification = dict(schema='delsk.oracle.store-verification.v1', verified=True, objects=len(expected),
                        object_set_sha256=ev.hc(sorted(expected)), expected_manifest_sha256=ev.hc(expected))
    provenance = dict(schema='delsk.oracle.materialization-provenance.v1', verification=verification,
                      required_occurrences=len(required), required_sources=len({occurrences[i]['source_id']
                      for i in required}), candidate_lock_sha256=ev.sha256(ev.canonical(candidate)),
                      corpus_lock_sha256=ev.sha256(ev.canonical(corpus)),
                      source_lock_sha256=ev.sha256(ev.canonical(sources)),
                      selection_policy_sha256=ev.sha256(ev.canonical(policy)))
    check(ev.canonical(doc['verification']) == ev.canonical(verification) and
          ev.canonical(doc['provenance']) == ev.canonical(provenance), 'materialization frozen provenance mismatch')


def _envelope_receipt(sidecar, bundle=None):
    """The original envelope checksum is retained unchanged alongside the sidecars."""
    sidecar = Path(sidecar)
    receipt = sidecar / 'checksums.sha256'
    if bundle is not None:
        check(receipt.is_file(), 'bundle lacks envelope checksum receipt')
    if not receipt.exists():
        return  # early status-only upload precedes the final envelope checksum
    files = {p.name: p for p in sidecar.iterdir() if p.is_file() and p.name != 'checksums.sha256'}
    if bundle is not None:
        files.update({f'bundle/{p.relative_to(bundle).as_posix()}': p for p in Path(bundle).rglob('*')
                      if p.is_file() and p.name != 'checksums.sha256'})
    expected = ''.join(f'{ev.sha256(p.read_bytes())}  {n}\n' for n, p in sorted(files.items()))
    check(receipt.read_bytes() == expected.encode('utf-8'), 'envelope checksum receipt mismatch')


def retain(envelope, results=ev.RESULTS, snapshot=None, validate_materialization=None):
    """Import one envelope only if independently inventoried; never accepts a cherry-picked bundle list.

    ev.bundle verifies the normative bundle in staging; sidecars are published to
    .attempts/run-attempt separately. Failure envelopes publish sidecars only. An import
    cannot alter an existing retained bundle or sidecar, including INVALID evidence.
    """
    envelope, results = Path(envelope), Path(results)
    _no_links(envelope)
    check(envelope.is_dir(), 'envelope missing')
    check(sum(p.stat().st_size for p in envelope.rglob('*') if p.is_file()) <= budget.RUN_ARTIFACT_CAP,
          'envelope artifact size cap')
    names = {p.name for p in envelope.iterdir()}
    check('attempt.json' in names and names <= {'attempt.json', 'materialization.json', 'bundle', 'checksums.sha256'},
          'envelope contains unexpected files')
    if 'checksums.sha256' in names:
        check((envelope / 'checksums.sha256').read_bytes() == ev.checksums(envelope).encode('utf-8'),
              'envelope checksums mismatch')
    snap = validate_snapshot(snapshot or _read(results / 'inventory.json'))
    doc = validate_sidecar(_read(envelope / 'attempt.json'))
    entries = audit_ledger(_read(results / 'attempts.json'))
    check(reconcile(snap, _read(results / 'attempts.json')) == _read(results / 'attempts.json'),
          'ledger incomplete relative to inventory')
    check(key(doc) in entries, 'unlisted dispatch envelope')
    entry = entries[key(doc)]
    _bind_sidecar(doc, entry)
    has_bundle = 'bundle' in names
    if has_bundle:
        check('checksums.sha256' in names, 'bundle envelope checksum missing')
        check(doc['measurement_identity_sha256'] == entry['measurement_identity_sha256'],
              'bundle sidecar lacks derived measurement identity')
        check_bundle_binding(envelope / 'bundle', entry)
        check({p.relative_to(envelope / 'bundle').as_posix() for p in (envelope / 'bundle').rglob('*')
               if p.is_file()} == set(ev.BUNDLE_FILES), 'normative bundle closed files')
        check('materialization.json' in names, 'bundle lacks materialization provenance')
    if 'materialization.json' in names:
        (validate_materialization or _materialization)(_read(envelope / 'materialization.json'), entry)
    name = f"{entry['run_id']}-{entry['run_attempt']}"
    sidecar = results / '.attempts' / name
    target = results / name
    check(not sidecar.exists() and not target.exists(), 'attempt evidence already retained')
    stage = Path(tempfile.mkdtemp(prefix=f'.{name}.import.', dir=results))
    published_bundle = False
    try:
        staged_sidecar = stage / 'sidecar'
        staged_sidecar.mkdir()
        for n in sorted(names - {'bundle'}):
            check((envelope / n).is_file(), 'envelope sidecar must be regular file')
            shutil.copyfile(envelope / n, staged_sidecar / n)
        staged_bundle = ev.bundle(envelope / 'bundle', stage / 'normative') if has_bundle else None
        sidecar.parent.mkdir(exist_ok=True)
        if staged_bundle is not None:
            staged_bundle.rename(target)
            published_bundle = True
        try:
            staged_sidecar.rename(sidecar)
        except BaseException:
            if published_bundle:
                target.rename(stage / 'rolled-back-bundle')
            raise
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    return target if has_bundle else sidecar


def _git_show(root, sha, path):
    out = subprocess.run(['git', '-c', f'safe.directory={Path(root).as_posix()}', 'show', f'{sha}:{path}'],
                         cwd=root, capture_output=True, check=False)
    check(out.returncode == 0, 'unavailable source commit manifest')
    return out.stdout


def git_source(head_sha, ref, root=ev.ROOT):
    """Pilot identity exactly as run.prepare, from Git object bytes; no build/fetch/measurement.

    Only the accepted frozen contract/codec is allowed. Missing commits, a changed
    freeze or unavailable manifests make history unresolved, never invisible.
    """
    check(digest(head_sha, 40), 'immutable source SHA required')
    def read(path):
        return _git_show(root, head_sha, path)
    read(WORKFLOW)
    freeze_data, codec_data = read('.work/oracle/freeze.json'), read('.work/oracle/codec-lock.json')
    check(freeze_data == (ev.ORACLE / 'freeze.json').read_bytes() and
          codec_data == (ev.ORACLE / 'codec-lock.json').read_bytes(), 'source frozen contract mismatch')
    freeze, codec = ev.parse_doc(freeze_data), ev.parse_doc(codec_data)
    candidate = read('.work/corpus/e1/candidate-lock.json')
    corpus = gzip.decompress(read('.work/corpus/pilot-v1/corpus-lock.json.gz'))
    check(ev.sha256(candidate) == freeze['bindings']['candidate_lock_sha256'] and
          ev.sha256(corpus) == freeze['bindings']['corpus_lock_sha256'], 'source lock binding mismatch')
    manifest = {n: ev.sha256(read(f'.work/tools/{n}')) for n in ev.CODE_FILES}
    identity = dict(contract_id=ev.CONTRACT_ID, contract_freeze_sha256=ev.sha256(freeze_data),
                    codec_lock_sha256=ev.sha256(codec_data), **{role: {k: codec['codecs'][role][k] for k in
                    ('codec_id', 'options_sha256')} for role in ('delta', 'standalone')},
                    corpus_lock_sha256=ev.sha256(corpus), candidate_lock_sha256=ev.sha256(candidate),
                    measured_source_sha=head_sha, oracle_code_sha256=ev.hc(manifest), phase='pilot',
                    sealed_splits=['evaluation'])
    return dict(measurement_identity_sha256=ev.hc(identity), measured_source_sha=head_sha,
                workflow_sha=head_sha, workflow_ref=ref)


def kat_verified(get, repo, sha, root=ev.ROOT):
    """Frozen contract section 7: KAT suite green on the exact evaluator commit.

    Evidence is the independent Actions API, never a field claimed by a bundle. Only the
    reviewed oracle-smoke.yml with the frozen KAT files counts, run for exactly `sha` in
    this repository by push or dispatch (pull_request tests a merge ref, not the commit).
    Every attempt counts: a red attempt is not outvoted by a green rerun; pending blocks.
    """
    try:
        check(repository(repo) and digest(sha, 40), 'KAT evidence identity')
        check(_git_show(root, sha, SMOKE_WORKFLOW) == (Path(root) / SMOKE_WORKFLOW).read_bytes(),
              'evaluator commit smoke workflow differs from reviewed KAT suite')
        freeze = ev.parse_doc((Path(root) / '.work' / 'oracle' / 'freeze.json').read_bytes())
        check(all(ev.sha256(_git_show(root, sha, path)) == value for path, value in freeze['files'].items()),
              'evaluator commit KAT files differ from freeze')
        workflow = get(f'/repos/{repo}/actions/workflows/oracle-smoke.yml')
        check(workflow['path'] == SMOKE_WORKFLOW and positive(workflow['id']), 'smoke workflow identity')
        green = False
        for run in budget.paged(get, f'/repos/{repo}/actions/workflows/oracle-smoke.yml/runs?head_sha={sha}',
                                'workflow_runs'):
            check(run['head_sha'] == sha and run['workflow_id'] == workflow['id'], 'smoke run identity')
            if run['event'] not in KAT_EVENTS or run['repository']['full_name'] != repo or \
                    run['head_repository']['full_name'] != repo:
                continue
            for number in range(1, run['run_attempt'] + 1):
                attempt = get(f"/repos/{repo}/actions/runs/{run['id']}/attempts/{number}")
                check(attempt['id'] == run['id'] and attempt['run_attempt'] == number and
                      attempt['head_sha'] == sha, 'smoke attempt identity')
                if attempt['conclusion'] in ('cancelled', 'skipped'):
                    continue
                if attempt['status'] != 'completed' or attempt['conclusion'] != 'success':
                    return False
                steps = [step for job in budget.paged(
                    get, f"/repos/{repo}/actions/runs/{run['id']}/attempts/{number}/jobs", 'jobs')
                    if job['name'] == KAT_JOB and job['run_attempt'] == number and job['head_sha'] == sha
                    for step in job['steps'] if step['name'] == KAT_STEP]
                if len(steps) != 1 or steps[0]['conclusion'] != 'success':
                    return False
                green = True
        return green
    except Exception:  # unverifiable evidence is never green
        return False


def _g1(identity, results, snap):
    """Audit the whole evidence root against a validated snapshot and apply the frozen
    scientific G1. Returns (verdict, blockers, evaluator commit); never authority alone."""
    check(digest(identity), 'G1 identity syntax')
    results = Path(results)
    doc = _read(results / 'attempts.json') if results.exists() else dict(schema=LEDGER_SCHEMA, attempts=[])
    entries = audit_ledger(doc)
    check(reconcile(snap, doc) == doc, 'G1 ledger missing independently inventoried dispatch')
    if results.exists():
        _no_links(results)
    records = []
    for d in sorted(results.iterdir()) if results.exists() else []:
        if not d.is_dir() or d.name.startswith('.'):
            continue
        record = ev.attempt_record(d)
        k = record['github_run_id'], record['run_attempt']
        check(k in entries, 'retained bundle missing from ledger')
        check(record['identity'] == entries[k]['measurement_identity_sha256'], 'retained identity rebound')
        check_bundle_binding(d, entries[k])
        sidecar = results / '.attempts' / d.name / 'attempt.json'
        check(sidecar.is_file(), 'retained bundle missing dispatch sidecar')
        _bind_sidecar(_read(sidecar), entries[k])
        materialization = sidecar.parent / 'materialization.json'
        check(materialization.is_file(), 'retained bundle missing materialization provenance')
        _materialization(_read(materialization), entries[k])
        _envelope_receipt(sidecar.parent, d)
        records.append(record)
    # Status-only sidecars are audited too; never feed them to the scientific evaluator.
    sidecars = results / '.attempts'
    if sidecars.exists():
        for d in sidecars.iterdir():
            check(d.is_dir() and (d / 'attempt.json').is_file(), 'partial dispatch sidecar inventory')
            a = validate_sidecar(_read(d / 'attempt.json'))
            check(key(a) in entries and d.name == f"{a['run_id']}-{a['run_attempt']}", 'unlisted dispatch sidecar')
            _bind_sidecar(a, entries[key(a)])
            check({p.name for p in d.iterdir()} <= {'attempt.json', 'materialization.json', 'checksums.sha256'},
                  'dispatch sidecar contains unexpected files')
            if (d / 'materialization.json').exists():
                _materialization(_read(d / 'materialization.json'), entries[key(a)])
            if not (results / d.name).exists():
                _envelope_receipt(d)
    selected = [r for r in records if r['identity'] == identity]
    ledger = [k for k, a in entries.items() if a['measurement_identity_sha256'] == identity]
    if not ledger and not selected:
        return 'NOT_RUN', [], None
    verdict, blockers = ev.g1_inventory(selected, ledger)
    sources = {entries[k]['measured_source_sha'] for k in ledger}
    check(len(sources) == 1, 'G1 identity spans evaluator commits')
    if verdict != 'INVALID' and any(a['measurement_identity_sha256'] == identity and
                                    a['github_status'] != 'completed' for a in snap['attempts']):
        verdict, blockers = 'NOT_PASSED', sorted({*blockers, 'INVENTORY_PENDING'})
    return verdict, blockers, sources.pop()


def g1_offline(identity, results, snapshot, now=None, max_age_seconds=MAX_AGE_SECONDS):
    """Review/test projection over a supplied snapshot. A supplied snapshot is not
    independent history, so it never yields PASS: a passing root reports TEST_ONLY_PASS."""
    verdict, blockers, _ = _g1(identity, results, validate_snapshot(snapshot, now, max_age_seconds))
    return ('TEST_ONLY_PASS' if verdict == 'PASS' else verdict), blockers


def g1_root(identity, results=ev.RESULTS, now=None, max_age_seconds=MAX_AGE_SECONDS, get=None,
            resolve_source=None):
    """Production G1 over the full evidence root. Always refreshes the independent API
    inventory and checks KAT evidence for the evaluator commit; takes no snapshot."""
    check(digest(identity), 'G1 identity syntax')
    get = get or budget.github_get
    results = Path(results)
    prior = _read(results / 'inventory.json') if (results / 'inventory.json').exists() else None
    repo = prior['repository'] if prior else os.environ.get('GITHUB_REPOSITORY')
    if repo is None:
        rem = subprocess.run(['git', 'remote', 'get-url', 'origin'], cwd=ev.ROOT, capture_output=True,
                             text=True, check=False)
        match = re.search(r'github\.com[:/]([^/]+/[^/]+?)(?:\.git)?\s*$', rem.stdout)
        check(rem.returncode == 0 and match is not None, 'G1 needs repository for independent inventory')
        repo = match[1]
    snap = validate_snapshot(inventory(get, repo, resolve_source or git_source, now), now, max_age_seconds)
    verdict, blockers, source = _g1(identity, results, snap)
    if verdict in ('INVALID', 'NOT_RUN'):
        return verdict, blockers
    if not kat_verified(get, repo, source):
        blockers = [*blockers, 'KAT_NOT_VERIFIED']
    # The Actions API cannot reveal a trailing run deleted before anyone
    # inventoried it. A contiguous list and two reads do not prove inception
    # completeness. No independently durable dispatch capture exists in C0;
    # never manufacture a production PASS from this API-only projection.
    return 'NOT_PASSED', sorted({*blockers, 'DISPATCH_HISTORY_UNVERIFIED'})


def main(argv):
    try:
        command, args = (argv[0], argv[1:]) if argv else (None, [])
        if command == 'inventory' and len(args) == 2:
            _write_atomic(args[1], ev.canonical(inventory(budget.github_get, args[0], git_source)))
        elif command == 'reconcile' and len(args) in (2, 3):
            import_snapshot(_read(args[0]), *args[1:])
        elif command == 'retain' and len(args) == 2:
            retain(*args)
        elif command == 'audit' and len(args) == 2:
            audit_root(*args)
        elif command == 'audit-base' and len(args) in (1, 2):
            audit_git(*args)
        elif command == 'g1' and len(args) in (1, 2):
            verdict, blockers = g1_root(*args)
            print(f"G1: {verdict} {' '.join(blockers)}".rstrip())
            return 0 if verdict == 'PASS' else 1
        else:
            print(__doc__, file=sys.stderr)
            return 2
    except (ev.EvalError, KeyError, TypeError, ValueError, OSError):
        print('attempt infrastructure: incomplete or inconsistent evidence', file=sys.stderr)
        return 1
    print('attempt infrastructure verified')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
