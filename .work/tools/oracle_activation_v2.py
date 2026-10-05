"""DELSK-003A C1-B: activation tooling of delsk.oracle-contract.v3 (contract-v3 5, items 6-11). Activates nothing.

    oracle_activation_v2.py check-workflows                 static witness of contract 4.1 / 12.2 on the reviewed files
    oracle_activation_v2.py write-surface OUT.json          activation item 10, inside oracle-registry-write-surface.yml
    oracle_activation_v2.py verify-rulesets RULESETS.json   activation item 7 over admin-collected API responses
    oracle_activation_v2.py verify-smoke SMOKE.json SCENARIOS.json   activation items 8-9
    oracle_activation_v2.py verify-infra INFRA.json         infra record (items 6-10) against the working tree
    oracle_activation_v2.py verify-record ACTIVATION.json   enable record: infra record + items 6, 11, 12 live

Activation takes two records (see "activation records" below): the infra record fixes the bind/boundary/KAT step
names and the closed provider-step set (contract-v3 1.1) and binds the evidence of items 6-10; the enable record
(ACTIVATION_FILE) binds the infra record, the merged infra PR and the maintainer decision. It takes effect only
when the enable PR also sets oracle_g1_v2.ACTIVATION_RECORD to the SHA-256 of its exact bytes; production re-verifies both in the pinned main tree,
and items 6, 11 and 12 live, on every evaluation (activation_in_tree). Before that, production G1 is NOT_PASSED
V3_NOT_ACTIVE without reads and the production `register` refuses. Nothing here creates the registry branch,
configures rulesets or dispatches a workflow.
"""
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Callable

import oracle_attempts as oa
import oracle_eval as ev
import oracle_registry_git as rg
import oracle_registry_v2 as reg

ACTIVATION_FILE = '.work/oracle/activation-v3.json'
EVIDENCE_DIR = '.work/oracle/activation/'
SCHEMA = 'delsk.oracle.v3-activation.v2'
RULESETS_SCHEMA = 'delsk.oracle.rulesets-evidence.v1'
SMOKE_EVALUATION_SCHEMA = 'delsk.oracle.registry-smoke-evaluation.v1'
SCENARIOS_SCHEMA = 'delsk.oracle.registry-smoke-scenarios.v1'
WRITE_SURFACE_SCHEMA = 'delsk.oracle.write-surface.v1'

PILOT_WORKFLOW = reg.WORKFLOW_PATH
SMOKE_WORKFLOW = reg.SMOKE_WORKFLOW_PATH
WRITE_SURFACE_WORKFLOW = '.github/workflows/oracle-registry-write-surface.yml'
KAT_WORKFLOW = oa.SMOKE_WORKFLOW

# Step names proposed for the activation record (contract 4.1, 9.1 item 10). Reviewed code constants.
REGISTER_STEP = 'Register attempt in the append-only registry (contract v3 register)'
BIND_STEP = 'Bind registry entry before the measurement boundary (contract v3 bind)'
BOUNDARY_STEP = 'Measurement boundary (contract v3 boundary)'
CHECKOUT_STEP = 'Read-only source checkout'
KAT_STEP = oa.KAT_STEP
# The only actions allowed before the boundary (contract-v3 2 item 2), with the reviewed post-hook map of contract-v3
# 1.1: whether action.yml at exactly this SHA declares `runs.post` (checkout: `post: dist/index.js`; upload-artifact:
# `main` only). A new action or SHA needs a review of its metadata and of this map.
CHECKOUT_ACTION = 'actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1'
UPLOAD_ACTION = 'actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a'
POST_HOOK = {CHECKOUT_ACTION: True, UPLOAD_ACTION: False}
# Provider steps (contract-v3 1.1): steps GitHub Actions adds to a started job itself. Exactly `Complete job` and
# `Post <name>` of every step of job measure before the boundary whose pinned action has a post hook; check_*_workflow
# derives the set from the reviewed workflow and requires equality, and forbids these names (and `Set up job`,
# `Post ...`) as workflow steps.
PROVIDER_COMPLETE = 'Complete job'
PILOT_PROVIDER_STEPS = (PROVIDER_COMPLETE, f'Post {CHECKOUT_STEP}')
SMOKE_PROVIDER_STEPS = (PROVIDER_COMPLETE, f'Post {CHECKOUT_STEP}')
RESERVED_STEP_NAMES = ('Set up job', PROVIDER_COMPLETE)
ROLES = {BIND_STEP: 'bind', BOUNDARY_STEP: 'boundary', **{n: 'provider' for n in PILOT_PROVIDER_STEPS}}
SMOKE_ROLES = {BIND_STEP: 'bind', BOUNDARY_STEP: 'boundary', **{n: 'provider' for n in SMOKE_PROVIDER_STEPS}}
KAT_MODULES = ('test_oracle_contract', 'test_oracle_eval', 'test_oracle_v2_frozen', 'test_oracle_contract_v3',
               'test_oracle_registry_v2', 'test_oracle_g1_v2', 'test_oracle_v2_mutants')

# Deterministic registry root commits (oracle_registry_git.genesis_commit; reproduced by the tests).
GENESIS_SHA256 = {p.name: ev.hc(reg.make_genesis(p.g1_freeze_sha256, p)) for p in reg.PROFILES}
ROOT_COMMIT = {'production': '1a93f4ce71d9e4fbf5f21eaa9e66c660672ee258',
               'smoke': '62f79c1ceeb4f61615039104532e8dee251efaa3'}

GITHUB_ACTIONS_APP_ID = 15368   # the GitHub Actions integration: the workflow token's ruleset actor
# Retired v2 registry refs (contract-v3 3): never evaluated, but they disclose the v2 activation attempt and stay
# protected against deletion and rewrite.
RETIRED_REGISTRY_REFS = ('refs/heads/delsk/registry', 'refs/heads/delsk/registry-smoke')
REQUIRED_RULES = {'refs/heads/main': {'deletion', 'non_fast_forward', 'pull_request'},
                  reg.REGISTRY_REF: {'deletion', 'non_fast_forward'},
                  reg.SMOKE_REGISTRY_REF: {'deletion', 'non_fast_forward'},
                  **{ref: {'deletion', 'non_fast_forward'} for ref in RETIRED_REGISTRY_REFS}}

# Anything that may read natural bytes or run the measurement apparatus (contract 4.1 B) must not appear before the
# boundary step. Syntactic witness only: the exact step list and bodies are reviewed, this keeps them honest.
FORBIDDEN_BEFORE_BOUNDARY = ('oracle_build', 'oracle_run', 'oracle_materialize', 'materialize.py', 'oracle_pilot.py run',
                             'oracle_pilot.py smoke', 'download-artifact', 'actions/cache', 'curl', 'wget', 'corpus',
                             'codec', 'xdelta', 'zstd', 'gzip')

# A step after the boundary may start only if the boundary step itself started. Positive list: a step that was never
# evaluated has an empty outcome, which a `!= 'skipped'` test would wrongly accept.
BOUNDARY_STARTED = """contains(fromJSON('["success","failure","cancelled"]'), steps.workload.outcome)"""
# Write-capable jobs never run actions/checkout: its `token` input defaults to the job's GITHUB_TOKEN, which there has
# contents: write, so `persist-credentials: false` alone would still hand the write token to a third-party step
# (contract 12.2: the token is available to the registry update step only). The source comes from an anonymous fetch of
# the public repository instead, by exactly this reviewed step.
SOURCE_STEP = 'Anonymous source checkout without the write token'
SOURCE_TEXT = '\n'.join((
    f'name: {SOURCE_STEP}', 'env:', "  GIT_TERMINAL_PROMPT: '0'", 'run: |', '  git init -q .',
    f'  git -c credential.helper= fetch -q --no-tags {reg.REGISTRY_REMOTE} \\',
    "    '+refs/heads/main:refs/remotes/source/main' \"$GITHUB_SHA\"",
    '  git -c advice.detachedHead=false checkout -q --detach "$GITHUB_SHA"'))
PILOT_REGISTER_STEPS = (SOURCE_STEP, REGISTER_STEP)
PILOT_PRE_BOUNDARY = ('Bootstrap dispatch proof before checkout', 'Retain immutable dispatch proof', CHECKOUT_STEP,
                      'Validate dispatch, frozen chain and register scientific identity', BIND_STEP,
                      'Retain binding sidecar before the boundary', 'Retain attempt before codec setup',
                      'Budget and artifact admission', 'Hard capped transient work filesystem')
SMOKE_REGISTER_STEPS = (SOURCE_STEP, 'Synthetic hold before register', REGISTER_STEP)
SMOKE_MEASURE_STEPS = (CHECKOUT_STEP, 'Synthetic hold before the boundary', BIND_STEP,
                       'Retain binding sidecar before the boundary', 'Synthetic stop before the boundary',
                       BOUNDARY_STEP)
REGISTER_RUN = {'production': '/usr/bin/python3 .work/tools/oracle_registry_git.py register',
                'smoke': '/usr/bin/python3 .work/tools/oracle_registry_git.py smoke-register'}
BIND_RUN = {'production': '/usr/bin/python3 .work/tools/oracle_registry_git.py bind "$RUNNER_TEMP/binding/binding.json"',
            'smoke': '/usr/bin/python3 .work/tools/oracle_registry_git.py smoke-bind "$RUNNER_TEMP/binding/binding.json"'}

# Activation items 8-9. Each scenario is a distinct real-GitHub action; verify_smoke checks it against the live provider
# observation of its run key (never against the manifest label): run topology, job/step facts and registry class.
SCENARIOS = ('stop-before-boundary', 'cross-boundary', 'rerun-all', 'rerun-failed', 'cancel-before-register',
             'cancel-after-register', 'deleted-run')
DISPATCHED = ('stop-before-boundary', 'cross-boundary', 'cancel-before-register', 'cancel-after-register',
              'deleted-run')   # each a separate workflow_dispatch: own run ID, attempt 1


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
    source, step = job['steps'][0], job['steps'][-1]
    if source['text'] != SOURCE_TEXT:
        problems.append('register: source must come from the reviewed anonymous fetch')
    if any(s['uses'] for s in job['steps']):
        problems.append('register: no action may run in the write-capable job (actions/checkout defaults to its token)')
    if step['id'] != 'register' or _run_line(step) != REGISTER_RUN[kind] or step['if'] or step['continue-on-error']:
        problems.append('register: register step')
    _token_only_in(job, REGISTER_STEP, 'register', problems)


def _token_only_in(job, name, label, problems):
    """The write token is referenced by exactly one step, and nowhere else in the job (header, env, other steps)."""
    tokens = [s['name'] for s in job['steps'] if re.search(r'github\.token|GITHUB_TOKEN|secrets\.', s['text'])]
    if tokens != [name] or re.search(r'github\.token|GITHUB_TOKEN|secrets\.', job['header']):
        problems.append(f'{label}: write token must be visible to the {name!r} step only')


def _action(step):
    return step['uses'].split(' ')[0] if step['uses'] else None


def provider_steps(steps, boundary):
    """Contract-v3 1.1 from the reviewed measure steps before the boundary: Complete job and Post <name> of each step
    whose pinned action has a post hook by the reviewed map (a nameless one yields None, which matches nothing)."""
    return {PROVIDER_COMPLETE} | {f"Post {s['name']}" if s['name'] else None for s in steps[:boundary]
                                  if POST_HOOK.get(_action(s)) is True}


def _reserved_names(jobs, problems):
    """Contract-v3 2 item 2: no workflow step may carry a provider step name, so none can be exempt from PRE."""
    for job, j in jobs.items():
        for step in j['steps']:
            name = step['name'] or ''
            if name in RESERVED_STEP_NAMES or name.startswith('Post '):
                problems.append(f'{job}: step name {name!r} is reserved for provider steps')


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
    if None in names or len(set(names)) != len(names):
        problems.append('measure: every step needs an explicit unique name (provider steps are matched by name)')
    for step in steps[:x]:
        if step['uses'] and (not step['name'] or _action(step) not in POST_HOOK):
            problems.append(f"measure: {step['name'] or step['uses']} before the boundary must be a named pinned "
                            'checkout or upload-artifact (its post hook is part of the witness)')
    expected_provider = PILOT_PROVIDER_STEPS if kind == 'production' else SMOKE_PROVIDER_STEPS
    if provider_steps(steps, x) != set(expected_provider):
        problems.append(f'measure: provider steps {sorted(map(str, provider_steps(steps, x)))} differ from the '
                        'reviewed closed set')
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
    _reserved_names(jobs, problems)
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
    _reserved_names(jobs, problems)
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
    if not job['steps'] or job['steps'][0]['text'] != SOURCE_TEXT:
        problems.append('write-surface: source must come from the reviewed anonymous fetch')
    if any(s['uses'] and not s['uses'].startswith(UPLOAD_ACTION) for s in job['steps']):
        problems.append('write-surface: no action except the pinned artifact upload in the write-capable job')
    _token_only_in(job, 'Negative write-surface tests (contract v3 section 12.1)', 'write-surface', problems)
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

def _job(run, name):
    jobs = [j for j in run['jobs'] if j['name'] == name] if run else []
    return jobs[0] if len(jobs) == 1 else None


def _step(job, role):
    steps = [x for x in job['steps'] if x['role'] == role] if job else []
    return steps[0] if len(steps) == 1 else None


def _started(job, role=None):
    target = job if role is None else _step(job, role)
    return target is not None and target['started']


def _never_ran(job):
    """No step of the job ran: absent, not started, or cancelled before it got a runner (GitHub then reports the job
    completed/cancelled without a single step and with runner_id = runner_name = null; contract-v3 1.3 item 4)."""
    return job is None or not job['started'] or (job['conclusion'] == 'cancelled' and not job['steps']
                                                 and job['runner_assigned'] is False)


def _scenario_facts(name, run, entry):
    """Problems of one scenario from the provider facts of its own run key and its registry class (topology is checked
    by the caller). run is the normalized live observation (None = deleted / not found)."""
    out = []
    if name == 'deleted-run':
        if run is not None:
            out.append('provider still has the run')
    elif run is None:
        return ['no provider observation of this run key']
    elif (run['workflow_path'], run['event'], run['status']) != (SMOKE_WORKFLOW, 'workflow_dispatch', 'completed'):
        out.append('not a completed dispatch of the smoke workflow')
    register, measure = _job(run, 'register'), _job(run, 'measure')
    cls = entry['class'] if entry else None
    if entry and entry['violations']:
        out.append(f"violations {entry['violations']}")
    if name == 'stop-before-boundary':
        if not (cls == 'PRE' and measure and measure['conclusion'] == 'failure' and _started(measure, 'bind')
                and _step(measure, 'bind')['conclusion'] == 'success' and not _started(measure, 'boundary')):
            out.append('must be PRE: bind succeeded, the job failed before the boundary started')
    elif name == 'cross-boundary':
        if not (cls == 'MISSING' and _started(measure, 'boundary')):
            out.append('must be MISSING with the boundary started')
    elif name == 'rerun-all':
        if not (cls == 'PRE' and register and register['started'] and register['conclusion'] == 'success'):
            out.append('must be a new registered attempt (register job re-executed) classified PRE')
    elif name == 'rerun-failed':
        if not (cls is None and measure and _started(measure, 'bind')
                and _step(measure, 'bind')['conclusion'] == 'failure' and not _started(measure, 'boundary')):
            out.append('must have no entry, a refused bind and no boundary start')
    elif name == 'cancel-before-register':
        if not (cls is None and register and register['conclusion'] == 'cancelled' and _never_ran(measure)):
            out.append('must have no entry, a cancelled register job and no measure start')
    elif name == 'cancel-after-register':
        if not (cls == 'PRE' and register and register['conclusion'] == 'success' and measure
                and measure['conclusion'] == 'cancelled' and not _started(measure, 'boundary')):
            out.append('must be PRE with the measure job cancelled before the boundary')
    elif name == 'deleted-run':
        if cls != 'MISSING':
            out.append('a deleted registered run must be MISSING')
    return out


def verify_smoke(evaluation, scenarios):
    """smoke-evaluate output against the maintainer's scenario manifest. [] when every required scenario was executed
    on real GitHub and the live provider observation of its own run key proves it (contract 8.3-8.5, 10.2): labels in
    the manifest only say which key to look at, never what happened."""
    if not (type(evaluation) is dict and evaluation.get('schema') == SMOKE_EVALUATION_SCHEMA):
        return ['smoke evaluation: schema']
    if not (type(scenarios) is dict and scenarios.get('schema') == SCENARIOS_SCHEMA
            and set(scenarios) == {'schema', 'workflow', 'registry_ref', 'runs'}
            and scenarios['workflow'] == SMOKE_WORKFLOW and scenarios['registry_ref'] == reg.SMOKE_REGISTRY_REF
            and type(scenarios['runs']) is list):
        return ['smoke scenarios: closed document']
    problems = []
    if evaluation.get('blocker') is not None:
        problems.append(f"smoke registry: {evaluation['blocker']}")
    attempts = {(a['run_id'], a['run_attempt']): a for a in evaluation.get('attempts', [])}
    observed = {(o['run_id'], o['run_attempt']): o['run'] for o in evaluation.get('provider', [])}
    if evaluation.get('unbound_attempts'):
        problems.append(f"smoke: unbound attempts {evaluation['unbound_attempts']}")
    runs = {}
    for run in scenarios['runs']:
        if not (type(run) is dict and set(run) == {'scenario', 'run_id', 'run_attempt', 'html_url'}
                and run['scenario'] in SCENARIOS and oa.positive(run['run_id']) and oa.positive(run['run_attempt'])
                and run['html_url'] == f"https://github.com/{reg.REPOSITORY}/actions/runs/{run['run_id']}"
                and run['scenario'] not in runs):
            return problems + ['smoke scenarios: malformed or repeated scenario']
        runs[run['scenario']] = (run['run_id'], run['run_attempt'])
    missing = [name for name in SCENARIOS if name not in runs]
    if missing:
        return problems + [f'smoke: scenarios not executed {missing}']
    # topology: distinct keys; separate dispatches have distinct run IDs at attempt 1; reruns are later attempts of
    # the base dispatch, rerun-failed after rerun-all
    if len(set(runs.values())) != len(runs):
        problems.append('smoke: one run key cannot prove two scenarios')
    if len({runs[n][0] for n in DISPATCHED}) != len(DISPATCHED) or any(runs[n][1] != 1 for n in DISPATCHED):
        problems.append('smoke: each dispatched scenario needs its own run ID at attempt 1')
    base, rerun_all, rerun_failed = runs['stop-before-boundary'], runs['rerun-all'], runs['rerun-failed']
    if not (rerun_all[0] == rerun_failed[0] == base[0] and base[1] < rerun_all[1] < rerun_failed[1]):
        problems.append('smoke: rerun-all and rerun-failed must be later attempts of the stop-before-boundary run')
    for name, key in runs.items():
        problems += [f'{name} {key}: {p}' for p in _scenario_facts(name, observed.get(key), attempts.get(key))]
        if key not in observed:
            problems.append(f'{name} {key}: provider observation was not collected')
    extra = sorted(set(attempts) - set(runs.values()))
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


# --- activation records (contract 16 items 6-12) ---------------------------------------------------------------------
#
# Two records, in this order, so that every item is evidence that exists before the step that relies on it:
#   1. infra record (INFRA_FILE, items 6-10): step names, registry genesis, the reviewed genesis PR and the retained
#      evidence of items 7-10, merged into main by an "infra PR";
#   2. after that infra PR is merged (item 11) and a maintainer decision comment on issue DELSK-003A names the infra
#      record digest (item 12), an "enable PR" adds ACTIVATION_FILE, which binds the infra record, the merged infra PR
#      and the decision comment, and sets oracle_g1_v2.ACTIVATION_RECORD to its SHA-256.
# Item 11, maintainer decision of 2026-10-05: the project has one developer, so no approving GitHub review by another
# person is required (record schema v2 drops review_id). The provenance of the infra PR stays mandatory: it is merged
# into main by exactly the recorded commit and itself introduced exactly these infra bytes.
# Items 6, 11 and 12 are verified live against the constant provider API on every production evaluation; anything that
# cannot be confirmed (edited comment, unmerged PR, other merge commit, other infra bytes) keeps v3 not active.

INFRA_FILE = EVIDENCE_DIR + 'infra.json'
INFRA_SCHEMA = 'delsk.oracle.v3-activation-infra.v1'
DECISION_ISSUE = 27  # DELSK-003A
DECISION_PHRASE = 'DELSK-003A NATURAL MEASUREMENT AUTHORIZED infra_sha256={}'
MAINTAINER_ASSOCIATIONS = ('OWNER', 'MEMBER')
TOOL_FILE = '.work/tools/oracle_activation_v2.py'


@dataclass(frozen=True)
class TreeView:
    """Pinned main tree plus commit ancestry used by activation provenance checks."""
    read: Callable
    read_at: Callable
    on_main: Callable
    first_parent: Callable


def _evidence(entry, read):
    check(type(entry) is dict and set(entry) == {'path', 'sha256'} and type(entry['path']) is str
          and entry['path'].startswith(EVIDENCE_DIR) and '..' not in entry['path'].split('/'), 'evidence reference')
    data = read(entry['path'])
    check(data is not None and ev.sha256(data) == entry['sha256'], f"evidence bytes {entry['path']}")
    return ev.parse_doc(data)


def _pull(entry):
    return type(entry) is dict and set(entry) == {'pull_request', 'merge_commit_sha'} and \
        oa.positive(entry['pull_request']) and type(entry['merge_commit_sha']) is str and \
        ev.HEX40.match(entry['merge_commit_sha']) is not None


def validate_infra(doc, view):
    """Problems of the infra record (items 6-10) that need no provider: closed document, constants, evidence bytes and
    their verifiers, and the workflow witnesses of the pinned tree."""
    keys = {'schema', 'g1_contract', 'g1_freeze_sha256', 'steps', 'workflow_sha256', 'registry', 'genesis_review',
            'evidence'}
    if not (type(doc) is dict and set(doc) == keys and doc['schema'] == INFRA_SCHEMA
            and doc['g1_contract'] == reg.G1_CONTRACT and doc['g1_freeze_sha256'] == reg.G1_FREEZE_SHA256):
        return ['infra record: closed document of this contract']
    problems = []
    if doc['steps'] != {'register': REGISTER_STEP, 'bind': BIND_STEP, 'boundary': BOUNDARY_STEP, 'kat': KAT_STEP,
                        'provider': list(PILOT_PROVIDER_STEPS)}:
        problems.append('infra record: step names')
    pilot = view.read(PILOT_WORKFLOW)
    if pilot is None or doc['workflow_sha256'] != ev.sha256(pilot):  # contract-v3 1.5: the witnessed bytes
        problems.append('infra record: workflow_sha256 is not the reviewed oracle-pilot.yml')
    if doc['registry'] != {'ref': reg.REGISTRY_REF, 'genesis_sha256': GENESIS_SHA256['production'],
                           'root_commit': ROOT_COMMIT['production']}:
        problems.append('infra record: registry genesis')
    if not _pull(doc['genesis_review']):
        problems.append('infra record: genesis review (item 6)')
    ev_doc = doc['evidence']
    if not (type(ev_doc) is dict and set(ev_doc) == {'rulesets', 'smoke', 'scenarios', 'write_surface'}):
        return problems + ['infra record: evidence']
    try:
        problems += verify_rulesets(_evidence(ev_doc['rulesets'], view.read))
        problems += verify_smoke(_evidence(ev_doc['smoke'], view.read), _evidence(ev_doc['scenarios'], view.read))
        problems += verify_write_surface(_evidence(ev_doc['write_surface'], view.read))
    except (ev.EvalError, ValueError, UnicodeDecodeError) as error:
        problems.append(f'infra record: {error}')
    for path, checker in ((PILOT_WORKFLOW, check_pilot_workflow), (SMOKE_WORKFLOW, check_smoke_workflow),
                          (WRITE_SURFACE_WORKFLOW, check_write_surface_workflow), (KAT_WORKFLOW, check_kat_workflow)):
        data = view.read(path)
        problems += [f'{path}: missing'] if data is None else [f'{path}: {p}' for p in checker(data.decode())]
    return problems


def _merged(get, view, entry, label):
    """Live: the pull request is merged into main of this repository by exactly the recorded merge commit, which lies
    on the pinned main. Returns (pull request document or None, problems)."""
    pr = get(f"/repos/{reg.REPOSITORY}/pulls/{entry['pull_request']}")
    try:
        ok = (pr['number'] == entry['pull_request'] and pr['merged'] is True
              and pr['merge_commit_sha'] == entry['merge_commit_sha'] and pr['base']['ref'] == 'main'
              and pr['base']['repo']['full_name'] == reg.REPOSITORY and view.on_main(entry['merge_commit_sha']))
        oa.timestamp(pr['merged_at'])
    except (KeyError, TypeError, ev.EvalError):
        ok = False
    return (pr, []) if ok else (None, [f'{label}: pull request not merged into main by the recorded commit'])


def _pr_files(get, number):
    """Complete GitHub PR-files inventory, fail-closed at the provider's 3000-file ceiling."""
    out = []
    for page in range(1, 31):
        batch = get(f"/repos/{reg.REPOSITORY}/pulls/{number}/files?per_page=100&page={page}")
        if type(batch) is not list or any(type(item) is not dict for item in batch):
            raise rg.TransportError('pull request files unavailable')
        out.extend(batch)
        if len(batch) < 100:
            return out
    raise rg.TransportError('pull request files exceed verifiable provider limit')


def _git_blob_sha(data):
    return hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest()


def _introduced(get, view, pr, path, *, expected_sha256=None, marker=None):
    """Bind a reviewed PR to the exact artifact bytes it introduced.

    Presence in a later merge tree is insufficient: the merge's first parent must not already carry these bytes (or,
    for a marker, the marker itself), and GitHub's PR-files blob SHA must equal the blob actually present after merge.
    """
    merge = pr.get('merge_commit_sha')
    parent = view.first_parent(merge)
    if not (type(parent) is str and ev.HEX40.match(parent) and view.on_main(parent)):
        return False
    merged = view.read_at(merge, path)
    before = view.read_at(parent, path)
    if merged is None or before == merged:
        return False
    if expected_sha256 is not None and ev.sha256(merged) != expected_sha256:
        return False
    if marker is not None and (marker not in merged or (before is not None and marker in before)):
        return False
    hits = [item for item in _pr_files(get, pr['number'])
            if item.get('filename') == path and item.get('status') in ('added', 'modified')]
    return len(hits) == 1 and hits[0].get('sha') == _git_blob_sha(merged)


def verify_genesis_review(doc, get, view):
    """Item 6: the recorded PR itself introduced the deterministic production-root binding."""
    pr, problems = _merged(get, view, doc['genesis_review'], 'genesis review (item 6)')
    if pr is None:
        return problems
    marker = f"'production': '{ROOT_COMMIT['production']}'".encode()
    if not _introduced(get, view, pr, TOOL_FILE, marker=marker):
        problems.append('genesis review (item 6): recorded PR did not introduce the reviewed genesis binding')
    return problems


def validate_activation(doc, view, get):
    """All problems of the enable record (ACTIVATION_FILE): the infra record it binds, then items 6, 11 and 12 live."""
    keys = {'schema', 'g1_contract', 'g1_freeze_sha256', 'infra', 'infra_pr', 'decision'}
    if not (type(doc) is dict and set(doc) == keys and doc['schema'] == SCHEMA
            and doc['g1_contract'] == reg.G1_CONTRACT and doc['g1_freeze_sha256'] == reg.G1_FREEZE_SHA256
            and type(doc['infra']) is dict and doc['infra'].get('path') == INFRA_FILE):
        return ['activation record: closed document of this contract']
    try:
        infra = _evidence(doc['infra'], view.read)
    except (ev.EvalError, ValueError, UnicodeDecodeError):
        return ['activation record: infra record bytes']
    problems = validate_infra(infra, view)
    if problems:
        return problems
    try:
        problems += verify_genesis_review(infra, get, view)
        problems += _verify_review(doc, get, view)
        problems += _verify_decision(doc, get, view)
    except (TypeError, KeyError, AttributeError, ev.EvalError, rg.TransportError):
        problems.append('activation record: provider evidence unavailable')
    return problems


def _verify_review(doc, get, view):
    """Item 11 (one developer, see above): the infra PR is merged into main by the recorded commit and itself
    introduced exactly these infra bytes. No approving GitHub review by a second person is required."""
    merge = doc['infra_pr']
    if not _pull(merge):
        return ['infra PR (item 11): record']
    pr, problems = _merged(get, view, merge, 'infra PR (item 11)')
    if pr is None:
        return problems
    merged = view.read_at(merge['merge_commit_sha'], INFRA_FILE)
    if merged is None or ev.sha256(merged) != doc['infra']['sha256']:
        problems.append('infra PR (item 11): infra PR did not merge these infra bytes')
    if not _introduced(get, view, pr, INFRA_FILE, expected_sha256=doc['infra']['sha256']):
        problems.append('infra PR (item 11): merged PR did not introduce the exact infra artifact')
    return problems


def _verify_decision(doc, get, view):
    """Item 12: an unedited maintainer comment on issue DELSK-003A, made after the infra PR merged, that authorizes
    natural measurement for exactly this infra record."""
    decision = doc['decision']
    if not (type(decision) is dict and set(decision) == {'issue', 'comment_id', 'body_sha256'}
            and decision['issue'] == DECISION_ISSUE and oa.positive(decision['comment_id'])
            and type(decision['body_sha256']) is str and ev.HEX64.match(decision['body_sha256'])):
        return ['maintainer decision (item 12): record']
    comment = get(f"/repos/{reg.REPOSITORY}/issues/comments/{decision['comment_id']}")
    pr = get(f"/repos/{reg.REPOSITORY}/pulls/{doc['infra_pr']['pull_request']}")
    try:
        body = comment['body']
        ok = (comment['issue_url'] == f'{reg.PROVIDER_API}/repos/{reg.REPOSITORY}/issues/{DECISION_ISSUE}'
              and comment['author_association'] in MAINTAINER_ASSOCIATIONS and comment['user']['type'] == 'User'
              and ev.sha256(body.encode('utf-8')) == decision['body_sha256']
              and DECISION_PHRASE.format(doc['infra']['sha256']) in body
              and oa.timestamp(comment['created_at']) > oa.timestamp(pr['merged_at']))
    except (KeyError, TypeError, AttributeError, ev.EvalError):
        ok = False
    return [] if ok else ['maintainer decision (item 12): no unedited maintainer authorization for this infra record '
                          'after the infra PR merged']


def activation_in_tree(view, get, activation_sha256):
    """(enable record, infra record) named by the code constant and verified in the pinned tree and live, or None
    (v3 not active)."""
    if not (type(activation_sha256) is str and ev.HEX64.match(activation_sha256)):
        return None
    data = view.read(ACTIVATION_FILE)
    if data is None or ev.sha256(data) != activation_sha256:
        return None
    try:
        doc = ev.parse_doc(data)
        if validate_activation(doc, view, get):
            return None
        return doc, ev.parse_doc(view.read(INFRA_FILE))
    except (ev.EvalError, ValueError, UnicodeDecodeError, TypeError):
        return None


# --- CLI ---------------------------------------------------------------------------------------------------------------

def _read_tree(path):
    p = ev.ROOT / path
    return p.read_bytes() if p.is_file() and not p.is_symlink() else None


def local_view(root=None):
    """Working tree of the checkout, with HEAD as the pinned main (review tooling; production pins the remote)."""
    root = root or ev.ROOT
    def on_main(commit):
        return type(commit) is str and ev.HEX40.match(commit) is not None and rg.git(
            root, 'merge-base', '--is-ancestor', commit, 'HEAD', check=False).returncode == 0
    def first_parent(commit):
        out = rg.git(root, 'rev-parse', '--verify', f'{commit}^1', check=False)
        return out.stdout.decode().strip() if out.returncode == 0 else None
    return TreeView(_read_tree, lambda commit, path: rg.show(root, commit, path), on_main, first_parent)


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
        elif command == 'verify-infra' and len(args) == 1:
            problems = validate_infra(ev.parse_doc(Path(args[0]).read_bytes()), local_view())
        elif command == 'verify-record' and len(args) == 1:
            problems = validate_activation(ev.parse_doc(Path(args[0]).read_bytes()), local_view(), rg.api_get)
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
