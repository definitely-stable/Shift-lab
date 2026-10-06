"""Slice C0: exact-commit pilot gates, quiet bounded supervision and sealed export.

initialize OUT; run OUT WORK ADMISSION; worker OUT WORK ADMISSION;
smoke TOOLS CONFORMANCE OUT WORK; finish OUT STATUS.
Only the manual pilot workflow may run the natural worker. Smoke uses synthetic locks only.
"""
import contextlib
import datetime as dt
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time

TOOLS = Path(__file__).resolve().parent
WORK = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import manifests as m
import oracle_build as build
import oracle_eval as ev
import oracle_run as runner

REPOSITORY = 'definitely-stable/Shift-lab'
WORKFLOW = '.github/workflows/oracle-pilot.yml'
WALL_SECONDS = 22 * 60
WORK_CAP = 1280 << 20
ADDRESS_CAP = 8 << 30
ARTIFACT_CAP = (16 << 20) - (16 << 10)  # reserve room for the three small dispatch/status artifacts
SAFE_ENV = ('GITHUB_ACTIONS', 'GITHUB_EVENT_NAME', 'GITHUB_REPOSITORY', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT',
            'GITHUB_SHA', 'GITHUB_WORKFLOW_SHA', 'GITHUB_WORKFLOW_REF', 'GITHUB_REF', 'RUNNER_OS', 'RUNNER_ARCH',
            'SOURCE_SHA', 'ATTEMPT_ARTIFACT_ID', 'ImageOS', 'ImageVersion')


class PilotError(Exception):
    def __init__(self, failure_class):
        self.failure_class = failure_class
        super().__init__(failure_class)


def require(ok, failure_class):
    if not ok:
        raise PilotError(failure_class)


def validate_dispatch(env):
    sha, ref = env.get('SOURCE_SHA', ''), env.get('GITHUB_REF', '')
    require(env.get('GITHUB_EVENT_NAME') == 'workflow_dispatch' and env.get('GITHUB_REPOSITORY') == REPOSITORY,
            'DISPATCH_REJECTED')
    require(re.fullmatch('[0-9a-f]{40}', sha) is not None and sha == env.get('GITHUB_SHA') ==
            env.get('GITHUB_WORKFLOW_SHA'), 'DISPATCH_REJECTED')
    require(ref.startswith('refs/heads/') and env.get('GITHUB_WORKFLOW_REF') ==
            f'{REPOSITORY}/{WORKFLOW}@{ref}', 'DISPATCH_REJECTED')
    require(env.get('RUNNER_ARCH') == 'X64' and env.get('RUNNER_OS') == 'Linux', 'DISPATCH_REJECTED')
    require(all(re.fullmatch('[1-9][0-9]*', env.get(k, '')) for k in ('GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT')),
            'DISPATCH_REJECTED')


def validate_receipt(env):
    require(re.fullmatch('[1-9][0-9]*', env.get('ATTEMPT_ARTIFACT_ID', '')) is not None,
            'ATTEMPT_NOT_RETAINED')


# Contract-v3 5 (contract-v4 2) replaces the C0 refusal DISPATCH_HISTORY_UNVERIFIED (GitHub list-runs cannot prove the
# absence of a deleted dispatch) by the registered-attempt model: a natural run is admitted only while
# delsk.oracle-contract.v4 is active, for an execution of exactly the activated oracle-pilot.yml. The v1 G1 path stays
# NOT_PASSED DISPATCH_HISTORY_UNVERIFIED for ever (oracle_attempts); this gate never makes it pass.
ADMISSION_SCHEMA = 'delsk.oracle.v4-pilot-admission.v1'
ADMISSION_FILE = 'v4-activation.json'   # beside the evidence directory: not part of the exported envelope


def v4_admission_file(out):
    return Path(out).resolve().parent / ADMISSION_FILE


def _workflow_sha256(sha):
    """SHA-256 of oracle-pilot.yml in the Git tree of the executed commit (contract-v3 1.5), or None."""
    out = subprocess.run(['git', '-C', str(WORK.parent), 'show', f'{sha}:{WORKFLOW}'], capture_output=True,
                         check=False)
    return runner.sha256(out.stdout) if out.returncode == 0 and re.fullmatch('[0-9a-f]{40}', sha) else None


def verify_v4_activation(env):
    """Live admission in step initialize, before bind and the boundary: v4 is active on the live main exactly as
    production G1 verifies it (oracle_registry_git.active_activation: the enable record named by ACTIVATION_RECORD,
    its genesis review live, the reviewed registry root); the executed oracle-pilot.yml is the activated one (its
    bytes have the enable record's workflow_sha256); the measured source lies on that main. A refusal here stops the
    job before the boundary, so it never leaves a measurement. Any unobtainable fact refuses."""
    import oracle_g1_v2 as g1
    import oracle_registry_git as transport
    sha = env.get('GITHUB_SHA', '')
    require(g1.ACTIVATION_RECORD is not None, 'V4_NOT_ACTIVE')
    try:
        active = transport.active_activation(g1.ACTIVATION_RECORD)
    except Exception:  # transport, provider or Git failure: activation not proven
        active = None
    require(active is not None, 'V4_NOT_ACTIVE')
    main, enable = active
    require(_workflow_sha256(sha) == enable['workflow_sha256'], 'V4_NOT_ACTIVE')
    on_main = subprocess.run(['git', '-C', str(WORK.parent), 'merge-base', '--is-ancestor', sha, main],
                             capture_output=True, check=False)
    require(on_main.returncode == 0, 'V4_NOT_ACTIVE')
    return {'schema': ADMISSION_SCHEMA, 'repository': REPOSITORY, 'run_id': int(env['GITHUB_RUN_ID']),
            'run_attempt': int(env['GITHUB_RUN_ATTEMPT']), 'measured_source_sha': sha, 'main_head_sha': main,
            'activation_record': g1.ACTIVATION_RECORD, 'workflow_sha256': enable['workflow_sha256']}


def require_v4_active(env, path):
    """Offline admission of the worker and the runner gate, after the boundary: the admission that step initialize
    wrote for exactly this execution, for the activation record of this code and the executed workflow bytes. No
    network: a provider outage after the boundary cannot turn a verified admission into a refusal."""
    import oracle_g1_v2 as g1
    require(g1.ACTIVATION_RECORD is not None, 'V4_NOT_ACTIVE')
    path = Path(path)
    try:
        require(path.is_file() and not path.is_symlink(), 'V4_NOT_ACTIVE')
        doc = m.loads_strict(path.read_bytes())
        sha = env.get('GITHUB_SHA', '')
        ok = (type(doc) is dict and set(doc) == {'schema', 'repository', 'run_id', 'run_attempt',
                                                 'measured_source_sha', 'main_head_sha', 'activation_record',
                                                 'workflow_sha256'}
              and doc['schema'] == ADMISSION_SCHEMA and doc['repository'] == REPOSITORY
              and (doc['run_id'], doc['run_attempt']) == (int(env['GITHUB_RUN_ID']), int(env['GITHUB_RUN_ATTEMPT']))
              and doc['measured_source_sha'] == sha and doc['activation_record'] == g1.ACTIVATION_RECORD
              and doc['workflow_sha256'] == _workflow_sha256(sha))
    except (PilotError, ValueError, KeyError, TypeError, OSError):
        ok = False
    require(ok, 'V4_NOT_ACTIVE')


def measurement_identity(env, phase='pilot', candidate_data=None, corpus_data=None):
    freeze_data = (WORK / 'oracle/freeze.json').read_bytes()
    lock_data = (WORK / 'oracle/codec-lock.json').read_bytes()
    freeze, lock = m.loads_strict(freeze_data), m.loads_strict(lock_data)
    return {'contract_id': freeze['contract_id'], 'contract_freeze_sha256': runner.sha256(freeze_data),
            'codec_lock_sha256': runner.sha256(lock_data),
            **{role: {k: lock['codecs'][role][k] for k in ('codec_id', 'options_sha256')}
               for role in ('delta', 'standalone')},
            'corpus_lock_sha256': runner.sha256(corpus_data) if corpus_data is not None else
                freeze['bindings']['corpus_lock_sha256'],
            'candidate_lock_sha256': runner.sha256(candidate_data) if candidate_data is not None else
                freeze['bindings']['candidate_lock_sha256'],
            'measured_source_sha': env.get('GITHUB_SHA', ''), 'oracle_code_sha256': m.digest(build.code_manifest()),
            'phase': phase, 'sealed_splits': ['evaluation']}


def atomic_json(path, doc):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'wb') as file:
        file.write(m.canonical_bytes(doc))
        file.flush()
        os.fsync(file.fileno())
    os.replace(tmp, path)


def write_attempt(out, env, status, phase, failure_class=None, admission=None, identity=None):
    import oracle_attempts as attempts
    path = Path(out) / 'attempt.json'
    previous = m.loads_strict(path.read_bytes()) if path.exists() else None
    identity = identity or (previous or {}).get('measurement_identity_sha256')
    if failure_class is not None and failure_class not in attempts.FAILURE_CLASSES:
        failure_class = 'INFRASTRUCTURE_FAILED'
    doc = attempts.create_attempt(env, identity, status=status, phase=phase, failure_class=failure_class)
    if previous:
        doc['created_at'] = previous['created_at']
        doc['admission'] = previous['admission']
    if admission:
        doc['admission'] = admission
    atomic_json(path, doc)
    return doc


def initialize(out, env):
    # A bounded status is written even if checkout/manifest validation cannot proceed.
    Path(out).mkdir(parents=True, exist_ok=True)
    write_attempt(out, env, 'REGISTERED', 'dispatch')
    validate_dispatch(env)
    import oracle_materialize as materializer
    materializer.validate_frozen()
    write_attempt(out, env, 'REGISTERED', 'frozen_bindings', identity=m.digest(measurement_identity(env)))
    atomic_json(v4_admission_file(out), verify_v4_activation(env))  # contract-v4 2, before bind and the boundary


def resource_precheck(work, require_tmpfs=True):
    work = Path(work).resolve()
    require(shutil.disk_usage(work).free >= 2 * WORK_CAP if not require_tmpfs else
            shutil.disk_usage(work.parent).free >= 2 * WORK_CAP, 'DISK_ADMISSION_REFUSED')
    if require_tmpfs:
        require(sys.platform.startswith('linux'), 'DISK_ADMISSION_REFUSED')
        mounted = False
        for line in Path('/proc/self/mountinfo').read_text().splitlines():
            left, right = line.split(' - ', 1)
            point = left.split()[4].replace('\\040', ' ').replace('\\134', '\\')
            if point == str(work) and right.split()[0] == 'tmpfs':
                mounted = True
        fs = os.statvfs(work)
        require(mounted and fs.f_blocks * fs.f_frsize <= WORK_CAP, 'DISK_ADMISSION_REFUSED')
    require(not any(work.iterdir()), 'STALE_WORKDIR')


def _descendants(parent):
    """Observe descendants independently of session/process groups (codec calls create new sessions)."""
    facts = {}
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():
            continue
        try:
            fields = (path / 'stat').read_text().rsplit(')', 1)[1].split()
            facts[int(path.name)] = (int(fields[1]), fields[19])  # ppid, starttime (PID reuse guard)
        except (OSError, ValueError, IndexError):
            pass
    found, frontier = {}, {parent}
    while frontier:
        new = {pid for pid, (ppid, _) in facts.items() if ppid in frontier and pid not in found}
        found.update({pid: facts[pid][1] for pid in new})
        frontier = new
    return found


def _kill_descendants(known):
    for pid, born in known.items():
        try:
            current = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19]
            if current == born:
                os.kill(pid, signal.SIGKILL)
        except (OSError, ValueError, IndexError):
            pass


def run_bounded(argv, work, seconds, env):
    """Discard stdout/stderr, hard wall/AS/file caps; kill codec descendants across their fresh sessions."""
    import resource

    def limits():
        resource.setrlimit(resource.RLIMIT_AS, (ADDRESS_CAP, ADDRESS_CAP))
        resource.setrlimit(resource.RLIMIT_FSIZE, (WORK_CAP, WORK_CAP))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    clean = {k: env[k] for k in SAFE_ENV if k in env}
    clean.update(LC_ALL='C', PATH='/usr/bin:/bin', TMPDIR=str(Path(work).resolve()))
    child = subprocess.Popen(argv, cwd=work, env=clean, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True, preexec_fn=limits)
    deadline, known, status = time.monotonic() + seconds, {}, None
    previous = signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(InterruptedError()))
    try:
        while True:
            known.update(_descendants(child.pid))
            if child.poll() is not None:
                break
            if time.monotonic() >= deadline:
                status = 'PROCESS_WALL_TIMEOUT'
                break
            time.sleep(min(0.1, max(0, deadline - time.monotonic())))
    except (InterruptedError, KeyboardInterrupt):
        status = 'CANCELLED'
    finally:
        signal.signal(signal.SIGTERM, previous)
        known.update(_descendants(child.pid))
        _kill_descendants(known)
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        child.wait()
        _kill_descendants(known)
    return status or ('OK' if child.returncode == 0 else 'RUNNER_KILLED' if child.returncode < 0 else
                      'WORKLOAD_FAILED')


def check_export(out):
    """A closed envelope: no debug/private/build/source data, unknown paths or link aliases."""
    out = Path(out)
    allowed = {'attempt.json', 'materialization.json', 'checksums.sha256'}
    if (out / 'bundle').exists():
        allowed |= {f'bundle/{n}' for n in ev.BUNDLE_FILES}
        run = ev.parse_doc((out / 'bundle/run.json').read_bytes())
        if run['measurement_identity']['phase'] == 'smoke':
            allowed |= {f'bundle/{n}' for n in ev.SMOKE_LOCKS}
    entries = list(out.rglob('*'))
    require(not out.is_symlink() and not any(p.is_symlink() for p in entries), 'EXPORT_UNSAFE')
    present = {p.relative_to(out).as_posix() for p in entries if p.is_file()}
    require(present <= allowed and 'attempt.json' in present, 'EXPORT_UNSAFE')
    require(sum(p.stat().st_size for p in entries if p.is_file()) <= ARTIFACT_CAP, 'ARTIFACT_SIZE_CAP')
    if (out / 'bundle').exists():
        require(not ev.verify(out / 'bundle'), 'BUNDLE_VERIFICATION_FAILED')
    return present


def export_checksums(out):
    check_export(out)
    (Path(out) / 'checksums.sha256').write_text(ev.checksums(out), encoding='utf-8')
    check_export(out)


def validate_gate(env, tools_path, conformance_path, store=None):
    """Infrastructure entry gate used by the existing runner; scientific identity/status rules are unchanged."""
    validate_dispatch(env)
    validate_receipt(env)
    import oracle_g1_v2 as g1
    require(g1.ACTIVATION_RECORD is not None, 'V4_NOT_ACTIVE')  # before any gate read
    path = Path(env.get('ORACLE_PILOT_GATE', ''))
    require(path.is_absolute() and path.is_file() and not path.is_symlink(), 'PILOT_GATE_MISSING')
    doc = m.loads_strict(path.read_bytes())
    require(set(doc) == {'schema', 'measurement_identity_sha256', 'artifact_id', 'tools_sha256',
                        'conformance_sha256', 'store', 'objects_sha256', 'attempt', 'materialization_sha256'} and
            doc['schema'] == 'delsk.oracle.pilot-gate.v1', 'PILOT_GATE_MISSING')
    require(doc['measurement_identity_sha256'] == m.digest(measurement_identity(env)) and
            doc['artifact_id'] == int(env['ATTEMPT_ARTIFACT_ID']) and
            doc['tools_sha256'] == runner.sha256(Path(tools_path).read_bytes()) and
            doc['conformance_sha256'] == runner.sha256(Path(conformance_path).read_bytes()), 'PILOT_GATE_MISMATCH')
    attempt_path = Path(doc['attempt'])
    require(attempt_path.is_absolute() and attempt_path.is_file() and not attempt_path.is_symlink(),
            'PILOT_GATE_MISMATCH')
    require_v4_active(env, v4_admission_file(attempt_path.parent))
    attempt = m.loads_strict(attempt_path.read_bytes())
    require(attempt['status'] == 'READY' and attempt['admission'] == 'ADMITTED' and
            attempt['measurement_identity_sha256'] == doc['measurement_identity_sha256'] and
            (attempt['run_id'], attempt['run_attempt']) == (int(env['GITHUB_RUN_ID']), int(env['GITHUB_RUN_ATTEMPT'])) ,
            'PILOT_GATE_MISMATCH')
    materialized = attempt_path.parent / 'materialization.json'
    require(runner.sha256(materialized.read_bytes()) == doc['materialization_sha256'], 'PILOT_GATE_MISMATCH')
    if store is not None:
        import oracle_materialize as materializer
        candidate, corpus, _, _ = materializer.load_natural()
        expected = materializer.expected_objects(candidate, corpus)
        require(str(Path(store).resolve()) == doc['store'] and m.digest(expected) == doc['objects_sha256'],
                'PILOT_GATE_MISMATCH')
        materializer.verify_store(store, expected)


def _finalize(out, work, env):
    evidence, private = Path(out) / 'bundle', Path(work) / 'private'
    if not (evidence / 'run.json').exists():
        return False
    result = ev.finalize(evidence, private)
    require(not ev.verify(evidence), 'BUNDLE_VERIFICATION_FAILED')
    write_attempt(out, env, result['run_status'], 'oracle_finished')
    return result['run_status'] == 'COMPLETE'


def worker(out, work, admission_path, env):
    """Every premeasurement phase finishes before the sole natural runner entry point."""
    import oracle_materialize as materializer
    out, work = Path(out).resolve(), Path(work).resolve()
    validate_dispatch(env)
    validate_receipt(env)
    require_v4_active(env, v4_admission_file(out))
    admission = json.loads(Path(admission_path).read_bytes())
    require(all(admission.get(k) is True for k in ('admitted', 'within_budget', 'accounting_complete')),
            'BUDGET_REFUSED')
    resource_precheck(work)
    materializer.validate_frozen()
    try:
        write_attempt(out, env, 'REGISTERED', 'codec_build', admission='ADMITTED')
        require(build.main([str(work / 'build')], env) == 0, 'CODEC_BUILD_FAILED')
        tools_path = work / 'build/tools.json'
        write_attempt(out, env, 'REGISTERED', 'conformance')
        conformance, _ = runner.conformance_record(tools_path, env=env)
        require(conformance['verdict'] == 'PASS', 'CONFORMANCE_FAILED')
        conformance_path = work / 'conformance.json'
        atomic_json(conformance_path, conformance)
        write_attempt(out, env, 'REGISTERED', 'materialization')
        candidate, corpus, sources, policy = materializer.load_natural()
        provenance = materializer.materialize_store(work / 'store', candidate, corpus, sources, policy)
        expected = materializer.expected_objects(candidate, corpus)
        verification = materializer.verify_store(work / 'store', expected)
        require((len(candidate['queries']), sum(q['status'] == 'near_duplicate' for q in candidate['queries']),
                 sum(q['status'] == 'identity_only' for q in candidate['queries']),
                 candidate['planned_pairs_per_codec']) == (79, 64, 15, 1961), 'FROZEN_BINDING')
        atomic_json(out / 'materialization.json', {
            'schema': 'delsk.oracle.materialization-evidence.v1',
            'measurement_identity_sha256': m.digest(measurement_identity(env)),
            'measured_source_sha': env['GITHUB_SHA'], 'workflow_sha': env['GITHUB_WORKFLOW_SHA'],
            'run_id': int(env['GITHUB_RUN_ID']), 'run_attempt': int(env['GITHUB_RUN_ATTEMPT']),
            'provenance': provenance, 'verification': verification})
        require(json.loads(Path(admission_path).read_bytes()).get('admitted') is True, 'BUDGET_REFUSED')
        write_attempt(out, env, 'READY', 'premeasurement', admission='ADMITTED')
        gate = {'schema': 'delsk.oracle.pilot-gate.v1', 'measurement_identity_sha256': m.digest(measurement_identity(env)),
                'artifact_id': int(env['ATTEMPT_ARTIFACT_ID']),
                'tools_sha256': runner.sha256(tools_path.read_bytes()),
                'conformance_sha256': runner.sha256(conformance_path.read_bytes()),
                'store': str(work / 'store'), 'objects_sha256': m.digest(expected),
                'attempt': str(out / 'attempt.json'),
                'materialization_sha256': runner.sha256((out / 'materialization.json').read_bytes())}
        atomic_json(work / 'gate.json', gate)
        run_env = {**env, 'ORACLE_PILOT_GATE': str(work / 'gate.json')}
        # prepare repeats C01-C14 byte for byte, after materialization and before the first natural encode.
        ctx = runner.prepare('pilot', tools_path, conformance_path, env=run_env)
        require(ctx['identity_sha256'] == gate['measurement_identity_sha256'], 'PILOT_GATE_MISMATCH')
        validate_gate(run_env, tools_path, conformance_path, work / 'store')
        runner.execute(ctx, work / 'store', out / 'bundle', work / 'private', run_env)
        return 0 if _finalize(out, work, env) else 1
    except BaseException as error:
        failure = getattr(error, 'failure_class', 'INFRASTRUCTURE_FAILED')
        write_attempt(out, env, 'FAILED', 'premeasurement' if not (out / 'bundle/run.json').exists() else 'oracle',
                      failure_class=failure)
        return 1


def supervise(out, work, admission_path, env):
    out, work = Path(out).resolve(), Path(work).resolve()
    admission = json.loads(Path(admission_path).read_bytes())
    if admission.get('admitted') is not True or admission.get('within_budget') is not True or \
            admission.get('accounting_complete') is not True:
        write_attempt(out, env, 'NOT_ADMITTED', 'admission', failure_class='BUDGET_REFUSED', admission='REFUSED')
        export_checksums(out)
        return 1
    validate_dispatch(env)
    validate_receipt(env)
    resource_precheck(work)
    require(not any(out.glob('bundle*')) and not (out / 'materialization.json').exists(), 'STALE_WORKDIR')
    write_attempt(out, env, 'REGISTERED', 'admission', admission='ADMITTED')
    status = run_bounded([sys.executable, str(Path(__file__).resolve()), 'worker', str(out), str(work),
                          str(Path(admission_path).resolve())], work, WALL_SECONDS, env)
    if status != 'OK':
        attempt = m.loads_strict((out / 'attempt.json').read_bytes())
        if attempt['status'] in ('READY', 'REGISTERED'):
            write_attempt(out, env, 'FAILED', attempt['phase'], failure_class=status)
        # Recover partial rows only through the same independent sealing/evaluator; raw private data is never exported.
        if (out / 'bundle/run.json').exists():
            recovery = run_bounded([sys.executable, str(Path(__file__).resolve()), 'recover', str(out), str(work)],
                                   work, 60, env)
            if recovery != 'OK':
                shutil.rmtree(out / 'bundle')
                write_attempt(out, env, 'FAILED', 'recovery', failure_class='BUNDLE_VERIFICATION_FAILED')
    export_checksums(out)
    return 0 if status == 'OK' else 1


def smoke(tools_path, conformance_path, out, work, env):
    """The full codec/runner/finalize/export path on synthetic inputs; never calls natural materialization."""
    import oracle_materialize as materializer
    out, work = Path(out).resolve(), Path(work).resolve()
    require(not out.exists() and not work.exists(), 'STALE_WORKDIR')
    work.mkdir(parents=True)
    out.mkdir(parents=True)
    runner.synthetic(work / 'synthetic')
    candidate_data = (work / 'synthetic/candidate-lock.json').read_bytes()
    corpus_data = (work / 'synthetic/corpus-lock.json').read_bytes()
    expected = materializer.expected_objects(m.loads_strict(candidate_data), m.loads_strict(corpus_data))
    verification = materializer.verify_store(work / 'synthetic/store', expected)
    ctx = runner.prepare('smoke', tools_path, conformance_path, work / 'synthetic', env)
    write_attempt(out, env, 'READY', 'synthetic_premeasurement', admission='ADMITTED', identity=ctx['identity_sha256'])
    atomic_json(out / 'materialization.json', {
        'schema': 'delsk.oracle.materialization-evidence.v1',
        'measurement_identity_sha256': ctx['identity_sha256'],
        'measured_source_sha': env['GITHUB_SHA'], 'workflow_sha': env['GITHUB_WORKFLOW_SHA'],
        'run_id': int(env['GITHUB_RUN_ID']), 'run_attempt': int(env['GITHUB_RUN_ATTEMPT']),
        'provenance': {'schema': 'delsk.oracle.synthetic-materialization.v1'}, 'verification': verification})
    runner.execute(ctx, work / 'synthetic/store', out / 'bundle', work / 'private', env)
    require(_finalize(out, work, env), 'SYNTHETIC_INCOMPLETE')
    export_checksums(out)
    return 0


def main(argv, env=os.environ):
    out = Path(argv[1]) if len(argv) > 1 and argv[0] in ('initialize', 'run', 'worker', 'recover', 'finish') else None
    try:
        if argv[:1] == ['initialize'] and len(argv) == 2:
            initialize(out, env)
        elif argv[:1] == ['run'] and len(argv) == 4:
            return supervise(out, argv[2], argv[3], env)
        elif argv[:1] == ['worker'] and len(argv) == 4:
            return worker(out, argv[2], argv[3], env)
        elif argv[:1] == ['recover'] and len(argv) == 3:
            _finalize(out, argv[2], env)
        elif argv[:1] == ['smoke'] and len(argv) == 5:
            return smoke(*argv[1:], env)
        elif argv[:1] == ['finish'] and len(argv) == 3:
            if argv[2] != 'success':
                write_attempt(out, env, 'FAILED', 'artifact_upload', failure_class='ARTIFACT_UPLOAD_FAILED')
            export_checksums(out)
        else:
            return 2
    except BaseException as error:
        # No exception text or captured codec/build output crosses the evidence boundary.
        failure = getattr(error, 'failure_class', 'INFRASTRUCTURE_FAILED')
        if out is not None:
            write_attempt(out, env, 'FAILED', 'infrastructure', failure_class=failure)
        print('PILOT REFUSED', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
