"""DELSK-003A C1-B: activation tooling of delsk.oracle-contract.v2 (contract 16, items 6-11). Activates nothing.

    oracle_activation_v2.py check-workflows                 static witness of contract 4.1 / 12.2 on the reviewed files
    oracle_activation_v2.py write-surface OUT.json          activation item 10, inside oracle-registry-write-surface.yml
    oracle_activation_v2.py verify-rulesets RULESETS.json   activation item 7 over admin-collected API responses
    oracle_activation_v2.py verify-smoke SMOKE.json SCENARIOS.json   activation items 8-9
    oracle_activation_v2.py verify-record ACTIVATION.json   the whole activation record against the working tree

The activation record (`delsk.oracle.v2-activation.v1`, ACTIVATION_FILE) fixes the bind/boundary/KAT step names and
binds the evidence of items 6-10 by SHA-256. It takes effect only when a reviewed PR also sets
oracle_g1_v2.ACTIVATION_RECORD to the SHA-256 of its exact bytes; production re-verifies it in the pinned main tree on
every evaluation (activation_in_tree). Before that, production G1 is NOT_PASSED V2_NOT_ACTIVE without reads and the
production `register` refuses. Nothing here creates the registry branch, configures rulesets or dispatches a workflow.
"""
import os
from pathlib import Path
import re
import sys
import tempfile

import oracle_attempts as oa
import oracle_eval as ev
import oracle_registry_git as rg
import oracle_registry_v2 as reg

ACTIVATION_FILE = '.work/oracle/activation-v2.json'
EVIDENCE_DIR = '.work/oracle/activation/'
SCHEMA = 'delsk.oracle.v2-activation.v1'
RULESETS_SCHEMA = 'delsk.oracle.rulesets-evidence.v1'
SMOKE_EVALUATION_SCHEMA = 'delsk.oracle.registry-smoke-evaluation.v1'
SCENARIOS_SCHEMA = 'delsk.oracle.registry-smoke-scenarios.v1'
WRITE_SURFACE_SCHEMA = 'delsk.oracle.write-surface.v1'

PILOT_WORKFLOW = reg.WORKFLOW_PATH
SMOKE_WORKFLOW = reg.SMOKE_WORKFLOW_PATH
WRITE_SURFACE_WORKFLOW = '.github/workflows/oracle-registry-write-surface.yml'
KAT_WORKFLOW = oa.SMOKE_WORKFLOW

# Step names proposed for the activation record (contract 4.1, 9.1 item 10). Reviewed code constants.
REGISTER_STEP = 'Register attempt in the append-only registry (contract v2 register)'
BIND_STEP = 'Bind registry entry before the measurement boundary (contract v2 bind)'
BOUNDARY_STEP = 'Measurement boundary (contract v2 boundary)'
KAT_STEP = oa.KAT_STEP
ROLES = {BIND_STEP: 'bind', BOUNDARY_STEP: 'boundary'}
KAT_MODULES = ('test_oracle_contract', 'test_oracle_eval', 'test_oracle_v2_frozen', 'test_oracle_registry_v2',
               'test_oracle_g1_v2', 'test_oracle_v2_mutants')

# Deterministic registry root commits (oracle_registry_git.genesis_commit; reproduced by the tests).
GENESIS_SHA256 = {p.name: ev.hc(reg.make_genesis(p.g1_freeze_sha256, p)) for p in reg.PROFILES}
ROOT_COMMIT = {'production': '6cf2c6a7c35cee005f894366c97fca00230a5670',
               'smoke': 'a429d34d67959e49af8f79da024ce6eed34cbc13'}

GITHUB_ACTIONS_APP_ID = 15368   # the GitHub Actions integration: the workflow token's ruleset actor
REQUIRED_RULES = {'refs/heads/main': {'deletion', 'non_fast_forward', 'pull_request'},
                  reg.REGISTRY_REF: {'deletion', 'non_fast_forward'},
                  reg.SMOKE_REGISTRY_REF: {'deletion', 'non_fast_forward'}}

# Anything that may read natural bytes or run the measurement apparatus (contract 4.1 B) must not appear before the
# boundary step. Syntactic witness only: the exact step list and bodies are reviewed, this keeps them honest.
FORBIDDEN_BEFORE_BOUNDARY = ('oracle_build', 'oracle_run', 'oracle_materialize', 'materialize.py', 'oracle_pilot.py run',
                             'oracle_pilot.py smoke', 'download-artifact', 'actions/cache', 'curl', 'wget', 'corpus',
                             'codec', 'xdelta', 'zstd', 'gzip')

# A step after the boundary may start only if the boundary step itself started. Positive list: a step that was never
# evaluated has an empty outcome, which a `!= 'skipped'` test would wrongly accept.
BOUNDARY_STARTED = """contains(fromJSON('["success","failure","cancelled"]'), steps.workload.outcome)"""
PILOT_REGISTER_STEPS = (None, REGISTER_STEP)
PILOT_PRE_BOUNDARY = ('Bootstrap dispatch proof before checkout', 'Retain immutable dispatch proof', None,
                      'Validate dispatch, frozen chain and register scientific identity', BIND_STEP,
                      'Retain binding sidecar before the boundary', 'Retain attempt before codec setup',
                      'Budget and artifact admission', 'Hard capped transient work filesystem')
SMOKE_REGISTER_STEPS = (None, 'Synthetic hold before register', REGISTER_STEP)
SMOKE_MEASURE_STEPS = (None, 'Synthetic hold before the boundary', BIND_STEP,
                       'Retain binding sidecar before the boundary', 'Synthetic stop before the boundary',
                       BOUNDARY_STEP)
REGISTER_RUN = {'production': '/usr/bin/python3 .work/tools/oracle_registry_git.py register',
                'smoke': '/usr/bin/python3 .work/tools/oracle_registry_git.py smoke-register'}
BIND_RUN = {'production': '/usr/bin/python3 .work/tools/oracle_registry_git.py bind "$RUNNER_TEMP/binding/binding.json"',
            'smoke': '/usr/bin/python3 .work/tools/oracle_registry_git.py smoke-bind "$RUNNER_TEMP/binding/binding.json"'}

SCENARIOS = {  # activation items 8-9: scenario -> (registry entry expected, class, provider run present)
    'stop-before-boundary': (True, 'PRE', True),
    'cross-boundary': (True, 'MISSING', True),
    'rerun-all': (True, 'PRE', True),
    'rerun-failed': (False, None, True),
    'cancel-before-register': (False, None, True),
    'cancel-after-register': (True, 'PRE', True),
    'deleted-run': (True, 'MISSING', False),
}


class ActivationError(ev.EvalError):
    pass


def check(ok, reason):
    if not ok:
        raise ActivationError(reason)


# --- static workflow witness (contract 4.1, 12.2) ---------------------------------------------------------------------

def workflow_jobs(text):
    """Strict reader for the reviewed workflow layout: two-space indentation, jobs at indent 2, job keys at indent 4,
    steps at indent 6 ('- '). Returns {job: {'header': str, 'steps': [{'name', 'id', 'text'}]}}. Anything outside this
    layout raises, so an unreadable workflow is never assumed safe."""
    lines = text.splitlines()
    check(lines.count('jobs:') == 1, 'workflow must have one top-level jobs key')
    jobs, job, in_steps = {}, None, False
    for line in lines[lines.index('jobs:') + 1:]:
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        indent = len(line) - len(line.lstrip(' '))
        check('\t' not in line[:indent + 1], 'tab indentation')
        if indent == 0:
            break
        if indent == 2:
            m = re.fullmatch(r'  ([A-Za-z_][A-Za-z0-9_-]*):', line)
            check(m is not None and m[1] not in jobs, 'job header')
            job, in_steps = jobs.setdefault(m[1], {'header': [], 'steps': []}), False
        elif indent == 4:
            check(job is not None, 'job key outside a job')
            in_steps = line == '    steps:'
            if not in_steps:
                job['header'].append(line[4:])
        elif in_steps and indent == 6:
            check(line.startswith('      - '), 'step item')
            job['steps'].append([line[8:]])
        elif in_steps and indent >= 8:
            check(bool(job['steps']), 'step body before the first step')
            job['steps'][-1].append(line[8:])
        else:
            check(job is not None and not in_steps, 'unexpected indentation')
            job['header'].append(line[4:])
    out = {}
    for name, j in jobs.items():
        steps = []
        for body in j['steps']:
            keys = {m[1]: m[2] for m in (re.fullmatch(r'([a-z-]+):\s*(.*)', b) for b in body) if m}
            steps.append({'name': keys.get('name'), 'id': keys.get('id'), 'if': keys.get('if'),
                          'uses': keys.get('uses'), 'continue-on-error': keys.get('continue-on-error'),
                          'text': '\n'.join(body)})
        out[name] = {'header': '\n'.join(j['header']), 'steps': steps}
    return out


def _run_line(step):
    """The single-line `run:` command of a step, or None."""
    m = re.search(r'^run: (.+)$', step['text'], re.M)
    return m[1] if m and not m[1].startswith(('|', '>')) else None


def _permissions(header):
    m = re.search(r'^permissions:\n((?:  .+\n?)+)', header + '\n', re.M)
    return None if m is None else sorted(l.strip() for l in m[1].splitlines())


def _common(text, problems):
    if re.search(r'^  (push|pull_request|pull_request_target|schedule|workflow_run|repository_dispatch):', text, re.M):
        problems.append('workflow must be workflow_dispatch only')
    if 'secrets.' in text or 'github.event.inputs' in text:
        problems.append('workflow must not read secrets or untyped event inputs')
    for action in re.findall(r'uses: ([^\s]+)', text):
        if not re.search(r'@[0-9a-f]{40}$', action):
            problems.append(f'unpinned action {action}')
    if not re.search(r'^permissions:\n  contents: read\n', text, re.M):
        problems.append('workflow default permissions must be read-only')


def _register_job(job, kind, expected_names, problems):
    if _permissions(job['header']) != ['contents: write']:
        problems.append('register: permissions must be exactly contents: write')
    if 'needs:' in job['header']:
        problems.append('register must not depend on another job')
    if 'entry_sha256: ${{ steps.register.outputs.entry_sha256 }}' not in job['header']:
        problems.append('register: output entry_sha256')
    names = tuple(s['name'] for s in job['steps'])
    if names != expected_names:
        problems.append(f'register: steps {names}')
        return
    checkout, step = job['steps'][0], job['steps'][-1]
    if not (checkout['uses'] or '').startswith('actions/checkout@') or 'persist-credentials: false' not in \
            checkout['text'] or 'fetch-depth: 0' not in checkout['text']:
        problems.append('register: checkout without credentials and with full history')
    if step['id'] != 'register' or _run_line(step) != REGISTER_RUN[kind] or step['if'] or step['continue-on-error']:
        problems.append('register: register step')
    tokens = [s['name'] for s in job['steps'] if 'github.token' in s['text']]
    if tokens != [REGISTER_STEP] or 'github.token' in job['header']:
        problems.append('register: write token must be visible to the register step only')


def _measure_job(job, kind, problems):
    perms = _permissions(job['header'])
    if perms not in (['actions: read', 'contents: read'], ['contents: read']):
        problems.append('measure: permissions must be read-only')
    if not re.search(r'^needs: register$', job['header'], re.M):
        problems.append('measure: needs register')
    if 'REGISTER_ENTRY_SHA256: ${{ needs.register.outputs.entry_sha256 }}' not in job['header']:
        problems.append('measure: register output')
    steps = job['steps']
    names = [s['name'] for s in steps]
    if names.count(BIND_STEP) != 1 or names.count(BOUNDARY_STEP) != 1:
        problems.append('measure: exactly one bind and one boundary step')
        return
    b, x = names.index(BIND_STEP), names.index(BOUNDARY_STEP)
    expected = PILOT_PRE_BOUNDARY if kind == 'production' else SMOKE_MEASURE_STEPS[:-1]
    if tuple(names[:x]) != expected or b >= x:
        problems.append(f'measure: steps before the boundary {tuple(names[:x])}')
    bind, boundary = steps[b], steps[x]
    if bind['id'] != 'bind' or _run_line(bind) != BIND_RUN[kind] or bind['if'] or bind['continue-on-error']:
        problems.append('measure: bind step must run unconditionally and stop the job on failure')
    cond = boundary['if'] or ''
    if "steps.bind.outcome == 'success'" not in cond or re.search(r'always\(\)|failure\(\)|cancelled\(\)', cond):
        problems.append('measure: boundary must require a successful bind')
    if boundary['id'] != 'workload':
        problems.append('measure: boundary step id workload')
    for step in steps[:x]:
        body = '\n'.join(l for l in step['text'].splitlines() if not l.startswith('name:')).lower()
        hits = [t for t in FORBIDDEN_BEFORE_BOUNDARY if t in body]
        if hits:
            problems.append(f"measure: {step['name'] or step['uses']} before the boundary uses {hits}")
    for step in steps[x + 1:]:
        if BOUNDARY_STARTED not in (step['if'] or ''):
            problems.append(f"measure: {step['name'] or step['uses']} after the boundary may start without it")


def check_pilot_workflow(text):
    """Contract 4.1 witness and 12.2 minimum for oracle-pilot.yml. [] when every rule holds."""
    problems = []
    _common(text, problems)
    if 'group: delsk-experimental' not in text or 'cancel-in-progress: false' not in text:
        problems.append('pilot concurrency')
    try:
        jobs = workflow_jobs(text)
    except ActivationError as error:
        return problems + [str(error)]
    if list(jobs) != ['register', 'measure']:
        return problems + [f'pilot jobs {list(jobs)}']
    _register_job(jobs['register'], 'production', PILOT_REGISTER_STEPS, problems)
    _measure_job(jobs['measure'], 'production', problems)
    if text.count('contents: write') != 1:
        problems.append('contents: write outside the register job')
    return problems


def check_smoke_workflow(text):
    """Synthetic smoke (items 8-9): same register/bind code on the SMOKE profile, nothing natural anywhere."""
    problems = []
    _common(text, problems)
    hits = [t for t in FORBIDDEN_BEFORE_BOUNDARY if t in text.lower()]
    if hits:
        problems.append(f'smoke workflow mentions {hits}')
    try:
        jobs = workflow_jobs(text)
    except ActivationError as error:
        return problems + [str(error)]
    if list(jobs) != ['register', 'measure']:
        return problems + [f'smoke jobs {list(jobs)}']
    _register_job(jobs['register'], 'smoke', SMOKE_REGISTER_STEPS, problems)
    _measure_job(jobs['measure'], 'smoke', problems)
    names = tuple(s['name'] for s in jobs['measure']['steps'])
    if names != SMOKE_MEASURE_STEPS:
        problems.append(f'smoke measure steps {names}')
    elif _run_line(jobs['measure']['steps'][-1]) != "echo 'synthetic boundary marker'":
        problems.append('smoke boundary must be a synthetic marker')
    if text.count('contents: write') != 1:
        problems.append('contents: write outside the register job')
    return problems


def check_write_surface_workflow(text):
    problems = []
    _common(text, problems)
    try:
        jobs = workflow_jobs(text)
    except ActivationError as error:
        return problems + [str(error)]
    job = jobs.get('write_surface')
    if list(jobs) != ['write_surface'] or _permissions(job['header']) != ['contents: write']:
        return problems + ['write-surface: one job with exactly contents: write']
    run = [_run_line(s) for s in job['steps']]
    if '/usr/bin/python3 .work/tools/oracle_activation_v2.py write-surface "$RUNNER_TEMP/write-surface.json"' \
            not in run:
        problems.append('write-surface: tool step')
    hits = [t for t in FORBIDDEN_BEFORE_BOUNDARY if t in text.lower()]
    if hits:
        problems.append(f'write-surface workflow mentions {hits}')
    return problems


def check_kat_workflow(text, kat_step=KAT_STEP):
    """KAT step of contract 9.1 item 10: exists once by this exact name and runs the v1 suite and v2 R/XC/PM tests."""
    try:
        steps = [s for s in workflow_jobs(text).get(oa.KAT_JOB, {'steps': []})['steps'] if s['name'] == kat_step]
    except ActivationError as error:
        return [str(error)]
    if len(steps) != 1:
        return ['KAT step must exist exactly once in the smoke job']
    return [f'KAT step does not run {m}' for m in KAT_MODULES if not re.search(rf'\b{m}\b', steps[0]['text'])]


# --- activation item 7: rulesets --------------------------------------------------------------------------------------

def _includes(ruleset, ref):
    include = ((ruleset.get('conditions') or {}).get('ref_name') or {}).get('include') or []
    exclude = ((ruleset.get('conditions') or {}).get('ref_name') or {}).get('exclude') or []
    hit = ref in include or (ref == 'refs/heads/main' and '~DEFAULT_BRANCH' in include)
    return hit and not exclude


def verify_rulesets(doc):
    """Admin-collected ruleset API responses (GET /repos/{repo}/rulesets/{id} for every ruleset, and
    GET /repos/{repo}/rules/branches/{branch} for main and both registries). [] when contract 12.1 holds."""
    problems = []
    if not (type(doc) is dict and doc.get('schema') == RULESETS_SCHEMA and doc.get('repository') == reg.REPOSITORY
            and set(doc) == {'schema', 'repository', 'collected_at', 'rulesets', 'effective'}):
        return ['rulesets evidence: closed document']
    try:
        oa.timestamp(doc['collected_at'])
    except ev.EvalError:
        problems.append('rulesets evidence: collected_at')
    rulesets = [r for r in doc['rulesets'] if type(r) is dict and r.get('target') == 'branch'
                and r.get('enforcement') == 'active' and r.get('source_type') == 'Repository'
                and r.get('source') == reg.REPOSITORY]
    for ref, required in REQUIRED_RULES.items():
        covering = [r for r in rulesets if _includes(r, ref)
                    and required <= {rule.get('type') for rule in r.get('rules') or [] if type(rule) is dict}]
        if not covering:
            problems.append(f'{ref}: no active ruleset with {sorted(required)}')
        registry = ref != 'refs/heads/main'
        for r in rulesets:
            if not _includes(r, ref):
                continue
            actors = r.get('bypass_actors')
            if registry and actors != []:
                problems.append(f'{ref}: ruleset {r.get("id")} bypass list must be empty')
            if not registry and (type(actors) is not list or any(
                    a.get('actor_type') == 'Integration' and a.get('actor_id') == GITHUB_ACTIONS_APP_ID
                    for a in actors if type(a) is dict)):
                problems.append(f'{ref}: workflow token (GitHub Actions) in bypass')
        effective = {rule.get('type') for rule in (doc['effective'].get(ref) or []) if type(rule) is dict}
        if not required <= effective:
            problems.append(f'{ref}: effective rules {sorted(effective)} lack {sorted(required - effective)}')
    return problems


# --- activation items 8-9: smoke scenarios ----------------------------------------------------------------------------

def verify_smoke(evaluation, scenarios):
    """smoke-evaluate output against the maintainer's scenario manifest. [] when every required scenario was executed
    on real GitHub and classified as contract 8.3-8.5 and 10.2 require."""
    problems = []
    if not (type(evaluation) is dict and evaluation.get('schema') == SMOKE_EVALUATION_SCHEMA):
        return ['smoke evaluation: schema']
    if not (type(scenarios) is dict and scenarios.get('schema') == SCENARIOS_SCHEMA
            and set(scenarios) == {'schema', 'workflow', 'registry_ref', 'runs'}
            and scenarios['workflow'] == SMOKE_WORKFLOW and scenarios['registry_ref'] == reg.SMOKE_REGISTRY_REF):
        return ['smoke scenarios: closed document']
    if evaluation.get('blocker') is not None:
        problems.append(f"smoke registry: {evaluation['blocker']}")
    attempts = {(a['run_id'], a['run_attempt']): a for a in evaluation.get('attempts', [])}
    unbound = {(u['run_id'], u['run_attempt']) for u in evaluation.get('unbound_attempts', [])}
    provider = {(o['run_id'], o['run_attempt']): o for o in evaluation.get('provider', [])}
    if unbound:
        problems.append(f'smoke: unbound attempts {sorted(unbound)}')
    seen, listed = set(), set()
    for run in scenarios['runs']:
        if not (type(run) is dict and set(run) == {'scenario', 'run_id', 'run_attempt', 'html_url'}
                and run['scenario'] in SCENARIOS and oa.positive(run['run_id']) and oa.positive(run['run_attempt'])
                and run['html_url'] == f"https://github.com/{reg.REPOSITORY}/actions/runs/{run['run_id']}"):
            problems.append('smoke scenarios: malformed run')
            continue
        key = (run['run_id'], run['run_attempt'])
        entry, cls, present = SCENARIOS[run['scenario']]
        seen.add(run['scenario'])
        listed.add(key)
        got = attempts.get(key)
        if entry != (got is not None) or (got is not None and (got['class'] != cls or got['violations'])):
            problems.append(f"{run['scenario']} {key}: registry class {got and got['class']} != {cls}")
        if entry and (provider.get(key, {}).get('run') is not None) != present:
            problems.append(f"{run['scenario']} {key}: provider run presence != {present}")
    missing = sorted(set(SCENARIOS) - seen)
    if missing:
        problems.append(f'smoke: scenarios not executed {missing}')
    extra = sorted(set(attempts) - listed)
    if extra:
        problems.append(f'smoke: registry entries without a scenario {extra}')
    return problems


# --- activation item 10: write-surface negative tests ------------------------------------------------------------------

OPERATIONS = ('push-main', 'non-fast-forward-registry', 'delete-registry')


def _effective(get, branch):
    rules = get(f'/repos/{reg.REPOSITORY}/rules/branches/{branch}')
    return {r.get('type') for r in rules if type(r) is dict} if type(rules) is list else set()


def _attempt(gitdir, remote, token, operation, ref, refspec):
    before = rg.ls_remote(gitdir, remote, ref, token)
    out = rg.git(gitdir, 'push', '--porcelain', '--no-verify', remote, refspec, env=rg.auth_env(token), check=False)
    after = rg.ls_remote(gitdir, remote, ref, token)
    return {'operation': operation, 'ref': ref, 'exit_code': out.returncode,
            'server_rejected': out.returncode != 0 and b'[remote rejected]' in out.stdout,
            'ref_before': before, 'ref_after': after}


def write_surface(env, get=rg.api_get, remote=reg.REGISTRY_REMOTE, token=None):
    """Contract 12.1 negative test with the workflow token of a contents: write job. A read-only preflight first
    requires the effective rules on main and the registry; without them no write is attempted. Each write must be
    rejected by the server; a ref that changed anyway stops the test at once and is reported."""
    doc = {'schema': WRITE_SURFACE_SCHEMA, 'repository': reg.REPOSITORY,
           'workflow_ref': env.get('GITHUB_WORKFLOW_REF'), 'run_id': rg._int(env.get('GITHUB_RUN_ID')),
           'run_attempt': rg._int(env.get('GITHUB_RUN_ATTEMPT')), 'credential': 'GITHUB_TOKEN contents: write',
           'collected_at': oa.utc().isoformat().replace('+00:00', 'Z'), 'preflight': 'FAILED', 'attempts': []}
    if not (REQUIRED_RULES['refs/heads/main'] <= _effective(get, 'main')
            and REQUIRED_RULES[reg.REGISTRY_REF] <= _effective(get, reg.REGISTRY_REF.removeprefix('refs/heads/'))):
        return doc
    with tempfile.TemporaryDirectory() as tmp:
        gitdir = rg.init_bare(Path(tmp) / 'probe.git')
        main = rg.fetch(gitdir, remote, 'refs/heads/main', token)
        registry = rg.fetch(gitdir, remote, reg.REGISTRY_REF, token)
        if main is None or registry is None:
            return doc
        doc['preflight'] = 'PASSED'
        tree = rg.git(gitdir, 'rev-parse', f'{main}^{{tree}}').decode().strip()
        probe = rg.git(gitdir, 'commit-tree', '--no-gpg-sign', tree, '-p', main, '-m',
                       'DELSK write-surface negative test: must be rejected', env=rg.COMMITTER).decode().strip()
        orphan = rg.make_commit(gitdir, {reg.GENESIS_FILE: rg.genesis_bytes(reg.PRODUCTION), reg.ENTRIES_FILE: b''},
                                None, 'DELSK write-surface negative test: non-fast-forward must be rejected')
        for operation, ref, refspec in (('push-main', 'refs/heads/main', f'{probe}:refs/heads/main'),
                                        ('non-fast-forward-registry', reg.REGISTRY_REF, f'+{orphan}:{reg.REGISTRY_REF}'),
                                        ('delete-registry', reg.REGISTRY_REF, f':{reg.REGISTRY_REF}')):
            result = _attempt(gitdir, remote, token, operation, ref, refspec)
            doc['attempts'].append(result)
            if result['ref_after'] != result['ref_before']:
                break  # never continue after a write got through
    return doc


def verify_write_surface(doc):
    if not (type(doc) is dict and doc.get('schema') == WRITE_SURFACE_SCHEMA and doc.get('repository') ==
            reg.REPOSITORY and doc.get('workflow_ref', '').startswith(f'{reg.REPOSITORY}/{WRITE_SURFACE_WORKFLOW}@')
            and oa.positive(doc.get('run_id')) and oa.positive(doc.get('run_attempt'))):
        return ['write-surface: closed document from the reviewed workflow']
    if doc.get('preflight') != 'PASSED':
        return ['write-surface: preflight did not find the rulesets; no write was attempted']
    problems = []
    if [a.get('operation') for a in doc.get('attempts', [])] != list(OPERATIONS):
        problems.append('write-surface: all three operations, in order')
    for a in doc.get('attempts', []):
        if not (a.get('server_rejected') is True and a.get('ref_before') == a.get('ref_after') is not None):
            problems.append(f"write-surface: {a.get('operation')} was not rejected by the server")
    return problems


# --- activation record ------------------------------------------------------------------------------------------------

def _evidence(entry, read):
    check(type(entry) is dict and set(entry) == {'path', 'sha256'} and type(entry['path']) is str
          and entry['path'].startswith(EVIDENCE_DIR) and '..' not in entry['path'].split('/'), 'evidence reference')
    data = read(entry['path'])
    check(data is not None and ev.sha256(data) == entry['sha256'], f"evidence bytes {entry['path']}")
    return ev.parse_doc(data)


def validate_activation(doc, read):
    """All problems of an activation record; read(path) returns committed bytes (pinned tree) or None."""
    keys = {'schema', 'g1_contract', 'g1_freeze_sha256', 'steps', 'registry', 'evidence', 'review',
            'natural_measurement'}
    if not (type(doc) is dict and set(doc) == keys and doc['schema'] == SCHEMA
            and doc['g1_contract'] == reg.G1_CONTRACT and doc['g1_freeze_sha256'] == reg.G1_FREEZE_SHA256):
        return ['activation record: closed document of this contract']
    problems = []
    if doc['steps'] != {'register': REGISTER_STEP, 'bind': BIND_STEP, 'boundary': BOUNDARY_STEP, 'kat': KAT_STEP}:
        problems.append('activation record: step names')
    if doc['registry'] != {'ref': reg.REGISTRY_REF, 'genesis_sha256': GENESIS_SHA256['production'],
                           'root_commit': ROOT_COMMIT['production']}:
        problems.append('activation record: registry genesis')
    if not (type(doc['review']) is dict and set(doc['review']) == {'pull_request'}
            and oa.positive(doc['review']['pull_request'])):
        problems.append('activation record: independent review (item 11)')
    decision = doc['natural_measurement']
    if not (type(decision) is dict and set(decision) == {'decision_url'} and type(decision['decision_url']) is str
            and re.fullmatch(rf'https://github\.com/{reg.REPOSITORY}/(issues|pull)/[1-9][0-9]*(#issuecomment-[0-9]+)?',
                             decision['decision_url'])):
        problems.append('activation record: maintainer decision on natural measurement (item 12)')
    ev_doc = doc['evidence']
    if not (type(ev_doc) is dict and set(ev_doc) == {'genesis_pull_request', 'rulesets', 'smoke', 'scenarios',
                                                     'write_surface'} and oa.positive(ev_doc['genesis_pull_request'])):
        return problems + ['activation record: evidence']
    try:
        problems += verify_rulesets(_evidence(ev_doc['rulesets'], read))
        problems += verify_smoke(_evidence(ev_doc['smoke'], read), _evidence(ev_doc['scenarios'], read))
        problems += verify_write_surface(_evidence(ev_doc['write_surface'], read))
    except (ev.EvalError, ValueError, UnicodeDecodeError) as error:
        problems.append(f'activation record: {error}')
    for path, checker in ((PILOT_WORKFLOW, check_pilot_workflow), (SMOKE_WORKFLOW, check_smoke_workflow),
                          (WRITE_SURFACE_WORKFLOW, check_write_surface_workflow), (KAT_WORKFLOW, check_kat_workflow)):
        data = read(path)
        problems += [f'{path}: missing'] if data is None else [f'{path}: {p}' for p in checker(data.decode())]
    return problems


def activation_in_tree(read, activation_sha256):
    """The activation record named by the code constant, verified in a pinned tree, or None (v2 not active)."""
    if not (type(activation_sha256) is str and ev.HEX64.match(activation_sha256)):
        return None
    data = read(ACTIVATION_FILE)
    if data is None or ev.sha256(data) != activation_sha256:
        return None
    try:
        doc = ev.parse_doc(data)
    except (ev.EvalError, ValueError, UnicodeDecodeError):
        return None
    return doc if not validate_activation(doc, read) else None


# --- CLI ---------------------------------------------------------------------------------------------------------------

def _read_tree(path):
    p = ev.ROOT / path
    return p.read_bytes() if p.is_file() and not p.is_symlink() else None


def main(argv, env=os.environ):
    command, args = (argv[0], argv[1:]) if argv else (None, [])
    try:
        if command == 'check-workflows' and not args:
            problems = []
            for path, checker in ((PILOT_WORKFLOW, check_pilot_workflow), (SMOKE_WORKFLOW, check_smoke_workflow),
                                  (WRITE_SURFACE_WORKFLOW, check_write_surface_workflow),
                                  (KAT_WORKFLOW, check_kat_workflow)):
                problems += [f'{path}: {p}' for p in checker(_read_tree(path).decode())]
        elif command == 'write-surface' and len(args) == 1:
            doc = write_surface(env, token=env.get('GITHUB_TOKEN'))
            rg.write_new(args[0], ev.canonical(doc))
            problems = verify_write_surface(doc)
        elif command == 'verify-rulesets' and len(args) == 1:
            problems = verify_rulesets(ev.parse_doc(Path(args[0]).read_bytes()))
        elif command == 'verify-smoke' and len(args) == 2:
            problems = verify_smoke(*(ev.parse_doc(Path(a).read_bytes()) for a in args))
        elif command == 'verify-record' and len(args) == 1:
            problems = validate_activation(ev.parse_doc(Path(args[0]).read_bytes()), _read_tree)
        else:
            print(__doc__, file=sys.stderr)
            return 2
    except (ev.EvalError, OSError, KeyError, TypeError, ValueError, AttributeError) as error:
        print(f'activation tooling: {type(error).__name__}', file=sys.stderr)
        return 1
    for p in problems:
        print(p)
    print('PASS' if not problems else f'FAIL: {len(problems)} problem(s)')
    return 0 if not problems else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
