"""DELSK-003A C1-B: Git and provider transport of delsk.oracle-contract.v3 (registry runner and production reads).

    oracle_registry_git.py genesis {production|smoke} OUT_GIT_DIR   deterministic registry root commit, local only
    oracle_registry_git.py register                                 contract 5.7, job `register` of oracle-pilot.yml
    oracle_registry_git.py bind OUT_BINDING.json                    contract 5.8, step `bind` of job `measure`
    oracle_registry_git.py smoke-register                           the same code on the SMOKE registry profile
    oracle_registry_git.py smoke-bind OUT_BINDING.json
    oracle_registry_git.py smoke-evaluate SCENARIOS.json OUT.json   smoke registry + provider facts of every scenario
    oracle_registry_git.py g1 IDENTITY OUT_RECORD.json              production G1 record (none before activation)

Authority is never a parameter: production commands are bound to reg.PRODUCTION (contract 5.1) and the constant provider
API, smoke commands to reg.SMOKE. The registry is read from its full branch history (contract 5.2) into a private bare
repository; appends are one commit with one new line, pushed only by the explicit refspec HEAD:<registry ref>, never
forced. Before activation (g1.ACTIVATION_RECORD is None) the production `register` refuses with DISPATCH_REJECTED before
any read or write, so the production registry stays untouched; the smoke profile exercises the same code paths.

No command reads a natural byte, builds or runs a codec, or measures anything. `genesis` never pushes: creating the
remote registry branch, configuring rulesets and dispatching workflows are maintainer activation steps (slice-c1c.md).
"""
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

import budget
import oracle_attempts as oa
import oracle_eval as ev
import oracle_g1_v2 as g1
import oracle_registry_v2 as reg

MAIN_REF = reg.SOURCE_REF
PIN = 'refs/delsk-pin/'            # private local namespace for remote refs pinned by this tool
PUSH_ROUNDS = 3                    # contract 5.7 item 5
MAX_RUN_ATTEMPTS = 256             # provider claims beyond this are treated as unobtainable data
GENESIS_DATE = '2026-10-05T00:00:00+00:00'
COMMITTER = {'GIT_AUTHOR_NAME': 'delsk-registry', 'GIT_AUTHOR_EMAIL': 'delsk-registry@users.noreply.github.com',
             'GIT_COMMITTER_NAME': 'delsk-registry', 'GIT_COMMITTER_EMAIL': 'delsk-registry@users.noreply.github.com'}
V2_ROOT = reg.RESULTS_ROOT
V1_ROOT = ev.RESULTS.relative_to(ev.ROOT).as_posix() + '/'
FREEZE_V3 = '.work/oracle/freeze-v3.json'
EVALUATOR_FILES = ('oracle_g1_v2.py', 'oracle_registry_v2.py', 'oracle_registry_git.py', 'oracle_activation_v2.py',
                   'oracle_eval.py', 'oracle_attempts.py', 'budget.py')


class TransportError(ev.EvalError):
    """Data could not be obtained or written (network, Git, API). Infrastructure failure, never a verdict."""


class Refusal(Exception):
    """Runner-level refusal with a closed contract code (contract 9.2)."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


# --- Git -------------------------------------------------------------------------------------------------------------

def auth_env(token):
    """Credential for github.com through the environment only (never argv, never persisted in a config file)."""
    if not token:
        return {}
    basic = base64.b64encode(f'x-access-token:{token}'.encode()).decode()
    return {'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'http.https://github.com/.extraheader',
            'GIT_CONFIG_VALUE_0': f'AUTHORIZATION: basic {basic}'}


def git(repo, *args, data=None, env=None, check=True):
    repo = Path(repo).resolve()
    full = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    full.update({'GIT_TERMINAL_PROMPT': '0', 'LC_ALL': 'C', 'GIT_CONFIG_NOSYSTEM': '1'}, **(env or {}))
    out = subprocess.run(['git', '-C', str(repo), '-c', f'safe.directory={repo.as_posix()}', '-c', 'credential.helper=',
                          '-c', 'commit.gpgsign=false', *args],
                         input=data, capture_output=True, env=full, check=False)
    if check and out.returncode != 0:
        raise TransportError(f'git {args[0]} failed')
    return out if not check else out.stdout


def init_bare(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=False)
    git(path, 'init', '--quiet', '--bare')
    return path


def ls_remote(repo, remote, ref, token=None):
    """Current value of exactly `ref` on the remote, or None when it does not exist."""
    lines = [line.split('\t') for line in git(repo, 'ls-remote', '--', remote, ref, env=auth_env(token)).decode()
             .splitlines() if line]
    found = [sha for sha, name in lines if name == ref]
    if len(found) > 1 or not all(ev.HEX40.match(sha) for sha in found):
        raise TransportError('ambiguous remote ref')
    return found[0] if found else None


def fetch(repo, remote, ref, token=None):
    """Fetch exactly `ref` (full history) into the private namespace; commit SHA, or None if the remote lacks it."""
    local = PIN + ref.removeprefix('refs/')
    out = git(repo, 'fetch', '--no-tags', '--no-recurse-submodules', '--quiet', remote, f'+{ref}:{local}',
              env=auth_env(token), check=False)
    if out.returncode != 0:
        if b"couldn't find remote ref" in out.stderr:
            return None
        raise TransportError('fetch failed')
    if git(repo, 'rev-parse', '--is-shallow-repository').strip() != b'false':
        raise TransportError('shallow repository: ancestry is not decidable')
    return git(repo, 'rev-parse', '--verify', f'{local}^{{commit}}').decode().strip()


def show(repo, commit, path):
    """Bytes of `path` in `commit`, or None when absent."""
    out = git(repo, 'show', f'{commit}:{path}', check=False)
    return out.stdout if out.returncode == 0 else None


def registry_history(gitdir, head):
    """Registry branch history root first, as validate_physical expects: [(parent_count, {path: bytes})]. Any tree
    entry that is not a regular 100644 blob is kept under a marker name, so the exact-tree rule (5.2) rejects it."""
    commits, blobs = [], {}
    for line in git(gitdir, 'rev-list', '--topo-order', '--reverse', '--parents', head).decode().splitlines():
        sha, *parents = line.split()
        files = {}
        for item in git(gitdir, 'ls-tree', '-z', sha).split(b'\0'):
            if not item:
                continue
            meta, name = item.split(b'\t', 1)
            mode, kind, blob = meta.decode().split()
            name = name.decode('utf-8', 'replace')
            if mode == '100644' and kind == 'blob':
                if blob not in blobs:
                    blobs[blob] = git(gitdir, 'cat-file', 'blob', blob)
                files[name] = blobs[blob]
            else:
                files[f'{name}\0{mode}'] = b''
        commits.append((len(parents), files))
    return commits


def lenient(commits):
    """(genesis, entries) of the head tree for gathering inputs only; authority is decided by reg.authoritative_registry.
    Unparseable bytes give ({}, []): the authoritative check then fails closed."""
    try:
        files = commits[-1][1]
        genesis, entries = reg.parse_registry(files[reg.GENESIS_FILE], files[reg.ENTRIES_FILE])
        if type(genesis) is dict and type(entries) is list and all(type(e) is dict for e in entries):
            return genesis, entries
    except (IndexError, KeyError, reg.RegistryInvalid):
        pass
    return {}, []


def _field(e, *path):
    for k in path:
        e = e.get(k) if type(e) is dict else None
    return e


def referenced_commits(entries):
    """Measured sources and transition merge commits named by entries (well-formed SHAs only)."""
    found = {_field(e, 'measured_source_sha') for e in entries}
    found |= {_field(e, 'transition', 'change_review', 'merge_commit_sha') for e in entries}
    return {c for c in found if type(c) is str and ev.HEX40.match(c)}


def transition_numbers(entries, transition=None):
    found = {_field(e, 'transition', 'change_review', 'pull_request') for e in entries}
    found.add(_field(transition, 'change_review', 'pull_request'))
    return sorted(n for n in found if oa.positive(n))


def snapshot(root, main_head, commits):
    """reg.GitSnapshot pinned at main_head over commit-addressed objects of `root` (contract 9.0). Only commits on the
    pinned main get ancestry and git_source identities; anything else is unresolvable, never assumed."""
    ancestors, identities = {}, {}
    for c in sorted({main_head, *commits}):
        if not (type(c) is str and ev.HEX40.match(c)):
            continue
        if git(root, 'cat-file', '-e', f'{c}^{{commit}}', check=False).returncode != 0:
            continue
        if git(root, 'merge-base', '--is-ancestor', c, main_head, check=False).returncode != 0:
            continue
        ancestors[c] = set(git(root, 'rev-list', c).decode().split()) - {c}
        try:
            identities[c] = oa.git_identity(c, root)
        except Exception:  # unresolvable identity: absent, so validation fails closed
            pass
    return reg.GitSnapshot.build(main_head, ancestors, identities)


def make_commit(gitdir, files, parent, message, date=None):
    lines = []
    for name in sorted(files):
        blob = git(gitdir, 'hash-object', '-w', '--stdin', data=files[name]).decode().strip()
        lines.append(f'100644 blob {blob}\t{name}')
    tree = git(gitdir, 'mktree', data=('\n'.join(lines) + '\n').encode()).decode().strip()
    env = dict(COMMITTER)
    if date is not None:
        env.update(GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
    return git(gitdir, 'commit-tree', '--no-gpg-sign', tree, *(['-p', parent] if parent else []), '-m', message,
               env=env).decode().strip()


def genesis_bytes(profile):
    return ev.canonical(reg.make_genesis(profile.g1_freeze_sha256, profile))


def genesis_commit(gitdir, profile):
    """Deterministic root commit of contract 5.2: exactly {genesis.json, empty entries.jsonl}. Local only."""
    return make_commit(gitdir, {reg.GENESIS_FILE: genesis_bytes(profile), reg.ENTRIES_FILE: b''}, None,
                       f'delsk registry genesis ({profile.name})', GENESIS_DATE)


def push(gitdir, remote, commit, ref, token=None):
    """Fast-forward push of `commit` through the explicit refspec HEAD:<ref> (contract 5.7 item 5); never forced."""
    git(gitdir, 'update-ref', '--no-deref', 'HEAD', commit)
    out = git(gitdir, 'push', '--porcelain', '--no-verify', remote, f'HEAD:{ref}', env=auth_env(token), check=False)
    return out.returncode == 0


# --- provider --------------------------------------------------------------------------------------------------------

def api_get(path):
    """GET from the constant provider API (contract 5.1). None for 404; TransportError for anything else unusable.
    GITHUB_TOKEN only raises rate limits; it never changes the authority (contract 11)."""
    headers = {'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28',
               'User-Agent': 'delsk-oracle-registry'}
    if os.environ.get('GITHUB_TOKEN'):
        headers['Authorization'] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    request = urllib.request.Request(reg.PROVIDER_API + path, headers=headers)
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            if error.code < 500:
                raise TransportError(f'provider HTTP {error.code}') from None
        except (urllib.error.URLError, TimeoutError, ValueError):
            pass
        time.sleep(2 ** attempt)
    raise TransportError('provider unavailable')


def paged(get, path, key):
    """Complete paginated list (budget.paged) or TransportError; a 404 page is never an empty list."""
    def page(p):
        doc = get(p)
        if type(doc) is not dict:
            raise TransportError('provider list unavailable')
        return doc
    try:
        return budget.paged(page, path, key)
    except (budget.Incomplete, KeyError, TypeError):
        raise TransportError('provider list incomplete') from None


def provider_observations(get, entries, roles):
    """Live provider observations (contract 8.3) of every attempt 1..max(latest_run_attempt, registered attempts) of
    every registered run ID; a deleted run or attempt yields run = null. Only registered run IDs are read (10.1)."""
    out = []
    for run_id in sorted({e['run_id'] for e in entries}):
        run = get(f'/repos/{reg.REPOSITORY}/actions/runs/{run_id}')
        latest = run.get('run_attempt') if type(run) is dict else None
        latest = latest if oa.positive(latest) else 0
        numbers = set(range(1, latest + 1)) | {e['run_attempt'] for e in entries if e['run_id'] == run_id}
        if max(numbers) > MAX_RUN_ATTEMPTS:
            raise TransportError('implausible run attempt count')
        for n in sorted(numbers):
            attempt = get(f'/repos/{reg.REPOSITORY}/actions/runs/{run_id}/attempts/{n}') if run is not None else None
            jobs = paged(get, f'/repos/{reg.REPOSITORY}/actions/runs/{run_id}/attempts/{n}/jobs',
                         'jobs') if attempt is not None else []
            out.append(g1.provider_observation(run_id, n, run, attempt, jobs, roles))
    return out


def pull_request(get, number):
    """Normalized pull request of this repository (schema pull_request) or None."""
    doc = get(f'/repos/{reg.REPOSITORY}/pulls/{number}')
    try:
        if doc['number'] != number or doc['base']['repo']['full_name'] != reg.REPOSITORY:
            return None
        return {'number': number, 'merged': doc['merged'] is True, 'merge_commit_sha': doc['merge_commit_sha'],
                'base_ref': f"refs/heads/{doc['base']['ref']}"}
    except (KeyError, TypeError):
        return None


def pull_requests(get, numbers):
    return [p for p in (pull_request(get, n) for n in numbers) if p is not None and reg.valid(p, 'pull_request')]


# --- runner (contract 5.7, 5.8) --------------------------------------------------------------------------------------

def _int(value):
    return int(value) if type(value) is str and re.fullmatch('[1-9][0-9]{0,17}', value) else None


def execution(env, profile):
    """The executing attempt from the Actions environment. The dispatch input source_sha, the branch ref and the
    workflow ref of this profile must agree (C0 validate_dispatch); the rest is decided by register_check."""
    x = {'event': env.get('GITHUB_EVENT_NAME'), 'repository': env.get('GITHUB_REPOSITORY'),
         'sha': env.get('GITHUB_SHA'), 'workflow_sha': env.get('GITHUB_WORKFLOW_SHA'),
         'workflow_ref': env.get('GITHUB_WORKFLOW_REF'), 'run_id': _int(env.get('GITHUB_RUN_ID')),
         'run_attempt': _int(env.get('GITHUB_RUN_ATTEMPT'))}
    ref = env.get('GITHUB_REF', '')
    if not (env.get('SOURCE_SHA') == x['sha'] and ref.startswith('refs/heads/')
            and x['workflow_ref'] == f'{reg.REPOSITORY}/{profile.workflow_path}@{ref}'):
        raise Refusal('DISPATCH_REJECTED')
    return x


def _transition_bytes(root, sha):
    return show(root, sha, reg.TRANSITION_FILE) if ev.HEX40.match(sha or '') else None


def _parsed(data):
    try:
        return ev.parse_doc(data) if data is not None else None
    except (ev.EvalError, ValueError, UnicodeDecodeError):
        return None


def _inputs(root, gitdir, profile, main, get, extra_commits=(), transition=None, token=None):
    """(registry commits, entries, git snapshot, pull requests) of the registry as it is now on the remote."""
    head = fetch(gitdir, profile.registry_remote, profile.registry_ref, token)
    if head is None:
        raise Refusal('REGISTRY_INVALID')  # no genesis: nothing can be registered or bound
    commits = registry_history(gitdir, head)
    _, entries = lenient(commits)
    merge = _field(transition, 'change_review', 'merge_commit_sha')
    wanted = referenced_commits(entries) | set(extra_commits) | ({merge} if type(merge) is str else set())
    return head, commits, entries, snapshot(root, main, wanted), pull_requests(get, transition_numbers(entries,
                                                                                                       transition))


def register(profile, env, root=ev.ROOT, get=api_get, token=None):
    """Contract 5.7 for the executing attempt: validate everything, append exactly one entry, read it back. Returns
    the entry. Refusal(code) means nothing was written; TransportError means the write could not be completed (the
    job fails, `measure` never starts, and a retry of this attempt is idempotent)."""
    if profile is reg.PRODUCTION and g1.ACTIVATION_RECORD is None:
        raise Refusal('DISPATCH_REJECTED')  # V3_NOT_ACTIVE: production registry stays untouched before activation
    x = execution(env, profile)
    transition_data = _transition_bytes(root, x['sha'])
    transition = _parsed(transition_data)
    with tempfile.TemporaryDirectory() as tmp:
        gitdir = init_bare(Path(tmp) / 'registry.git')
        for _ in range(PUSH_ROUNDS):
            main = fetch(root, profile.registry_remote, MAIN_REF, token)
            if main is None:
                raise TransportError('main not found')
            head, commits, entries, snap, prs = _inputs(root, gitdir, profile, main, get, {x['sha']}, transition,
                                                        token)
            code, entry = g1.register_check(commits, x, snap, prs, transition_data, profile)
            if code != 'APPENDED':
                raise Refusal(code)
            if any(e.get('entry_sha256') == entry['entry_sha256'] for e in entries):
                break  # idempotent: this attempt's entry is already durable (lost push response)
            files = dict(commits[-1][1])
            files[reg.ENTRIES_FILE] += ev.compact(entry).encode() + b'\n'
            commit = make_commit(gitdir, files, head,
                                 f"registry: entry {entry['sequence']} run {x['run_id']}-{x['run_attempt']}")
            if push(gitdir, profile.registry_remote, commit, profile.registry_ref, token):
                break
        else:
            raise TransportError('registry append not accepted')
        return readback(root, gitdir, profile, main, get, x, entry, token)


def readback(root, gitdir, profile, main, get, x, entry, token=None):
    """Contract 5.7 item 6: a fresh fetch holds this attempt's entry exactly once, in an authoritative registry."""
    _, commits, entries, snap, _ = _inputs(root, gitdir, profile, main, get, {x['sha']}, None, token)
    try:
        genesis, entries = reg.physical_objects(reg.authoritative_registry(commits, snap, profile))
    except reg.RegistryInvalid:
        raise Refusal('REGISTRY_INVALID') from None
    if reg.duplicate_keys(entries):
        raise Refusal('REGISTRY_DUPLICATE')
    mine = [e for e in entries if reg.run_key(e) == (x['run_id'], x['run_attempt'])]
    chain = ('sequence', 'previous_entry_sha256', 'entry_sha256')
    if len(mine) != 1 or any(mine[0][k] != entry[k] for k in entry if k not in chain):
        raise TransportError('readback does not hold this attempt exactly once')
    return mine[0]


def bind(profile, env, register_entry_sha256, root=ev.ROOT, get=api_get, token=None):
    """Contract 5.8 for the executing attempt: the binding sidecar, or Refusal('REGISTRY_UNBOUND') before B."""
    try:
        x = execution(env, profile)
        if not (type(register_entry_sha256) is str and ev.HEX64.match(register_entry_sha256)):
            raise Refusal('REGISTRY_UNBOUND')
        with tempfile.TemporaryDirectory() as tmp:
            gitdir = init_bare(Path(tmp) / 'registry.git')
            main = fetch(root, profile.registry_remote, MAIN_REF, token)
            if main is None:
                raise Refusal('REGISTRY_UNBOUND')
            _, commits, _, snap, _ = _inputs(root, gitdir, profile, main, get, {x['sha']}, None, token)
            code, binding = g1.bind_check(commits, x, snap, register_entry_sha256, profile)
    except (Refusal, TransportError):
        raise Refusal('REGISTRY_UNBOUND') from None
    if code != 'BOUND':
        raise Refusal('REGISTRY_UNBOUND')
    return binding


def write_new(path, data):
    """Create `path` exclusively (no overwrite, no symlink follow) and fsync it."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o644)
    with os.fdopen(fd, 'wb') as file:
        file.write(data)
        file.flush()
        os.fsync(file.fileno())


# --- evaluation inputs (contract 9.0, 9.1) ---------------------------------------------------------------------------

def evidence_from_tree(root, commit):
    """Retained v3 and v1 results roots exactly as in the pinned main tree (contract 8.1), not the working tree."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp, foreign = Path(tmp), []
        for prefix in (V2_ROOT, V1_ROOT):
            for item in git(root, 'ls-tree', '-r', '-z', '--full-tree', commit, '--', prefix).split(b'\0'):
                if not item:
                    continue
                meta, name = item.split(b'\t', 1)
                mode, kind, blob = meta.decode().split()
                name = name.decode('utf-8', 'replace')
                dest = tmp / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                if kind == 'blob' and mode in ('100644', '100755'):
                    dest.write_bytes(git(root, 'cat-file', 'blob', blob))
                elif kind == 'blob' and mode == '120000':
                    os.symlink(git(root, 'cat-file', 'blob', blob).decode('utf-8', 'replace'), dest)
                else:
                    foreign.append(name)
        evidence = g1.read_evidence_root(tmp / V2_ROOT, tmp / V1_ROOT)
    if foreign:
        evidence = g1.Evidence(evidence.bundles, evidence.bindings, evidence.foreign_paths + tuple(foreign),
                               evidence.v1_root_keys)
    return evidence


def evaluator_source_sha(root=ev.ROOT):
    """Commit whose G1 code executes this evaluation: HEAD of the checkout, only if every evaluator file in the working
    tree is byte-identical to that commit (otherwise None, which can never satisfy the KAT gate)."""
    head = git(root, 'rev-parse', '--verify', 'HEAD^{commit}', check=False)
    if head.returncode != 0:
        return None
    head = head.stdout.decode().strip()
    tools = Path(__file__).resolve().parent
    same = all(show(root, head, f'.work/tools/{name}') == (tools / name).read_bytes() for name in EVALUATOR_FILES)
    return head if same else None


def registry_reread(gitdir, profile, head_commit, evaluated_head, token=None):
    """Registry head re-read from the remote after the evaluation (contract 5.6 item 3)."""
    again = fetch(gitdir, profile.registry_remote, profile.registry_ref, token)
    if again == head_commit:
        return evaluated_head
    if again is None:
        return None
    genesis, entries = lenient(registry_history(gitdir, again))
    return reg.head(genesis, entries) if genesis else None


def collect(profile, root, get, roles, evidence, kat_step, evaluator):
    """Every input of one evaluation, read once from the profile's constant remote and the provider (contract 9.0):
    main pin, registry history, live provider observations, pull requests, evidence, KAT, then the re-reads.
    Returns (Evaluation, registry commits)."""
    remote = profile.registry_remote
    main = fetch(root, remote, MAIN_REF)
    if main is None:
        raise TransportError('main not found')
    with tempfile.TemporaryDirectory() as tmp:
        gitdir = init_bare(Path(tmp) / 'registry.git')
        head = fetch(gitdir, remote, profile.registry_ref)
        commits = registry_history(gitdir, head) if head is not None else []
        genesis, entries = lenient(commits)
        sources = {e['measured_source_sha'] for e in entries if type(e.get('measured_source_sha')) is str}
        snap = snapshot(root, main, referenced_commits(entries) | ({evaluator} if evaluator else set()))
        ok_entries = [e for e in entries if oa.positive(e.get('run_id')) and oa.positive(e.get('run_attempt'))]
        provider = provider_observations(get, ok_entries, roles)
        prs = pull_requests(get, transition_numbers(entries))
        evidence = evidence(main) if callable(evidence) else evidence
        kat = {c for c in sources | ({evaluator} if evaluator else set())
               if kat_step is not None and g1.kat_verified_v2(get, c, main, kat_step, root)}
        freeze = show(root, main, FREEZE_V3)
        evaluated_head = reg.head(genesis, entries) if genesis else None
        reread = registry_reread(gitdir, profile, head, evaluated_head)
    main_again = ls_remote(root, remote, MAIN_REF)
    evaluation = g1.Evaluation.build(
        genesis=genesis, entries=entries, registry_reread=reread, git=snap, main_reread=main_again,
        provider=provider, pull_requests=prs, evidence=evidence, evaluator_source_sha=evaluator, kat_green=kat,
        g1_freeze_sha256=(profile.g1_freeze_sha256 if profile is reg.SMOKE else
                          ev.sha256(freeze) if freeze is not None else None),
        profile=None if profile is reg.PRODUCTION else profile)
    return evaluation, commits


def registry_root(root=ev.ROOT, profile=reg.PRODUCTION):
    """The single root commit of the live registry branch, or None."""
    with tempfile.TemporaryDirectory() as tmp:
        gitdir = init_bare(Path(tmp) / 'root.git')
        head = fetch(gitdir, profile.registry_remote, profile.registry_ref)
        roots = git(gitdir, 'rev-list', '--max-parents=0', head).decode().split() if head else []
    return roots[0] if len(roots) == 1 else None


def production_inputs(activation_sha256):
    """Inputs of g1._production_evaluate, all from the authority constants. None when the activation record named by
    the code constant is absent or does not verify in the pinned main tree (then v3 is not active)."""
    import oracle_activation_v2 as act
    root = ev.ROOT
    main = fetch(root, reg.REGISTRY_REMOTE, MAIN_REF)
    if main is None:
        raise TransportError('main not found')
    def first_parent(commit):
        out = git(root, 'rev-parse', '--verify', f'{commit}^1', check=False)
        return out.stdout.decode().strip() if out.returncode == 0 else None
    view = act.TreeView(lambda path: show(root, main, path), lambda commit, path: show(root, commit, path),
                        lambda commit: type(commit) is str and ev.HEX40.match(commit) is not None and git(
                            root, 'merge-base', '--is-ancestor', commit, main, check=False).returncode == 0,
                        first_parent)
    activation = act.activation_in_tree(view, api_get, activation_sha256)
    if activation is None or registry_root(root) != act.ROOT_COMMIT['production']:
        return None  # item 6: the live registry must start at the reviewed genesis root commit
    steps = activation[1]['steps']
    roles = {steps['bind']: 'bind', steps['boundary']: 'boundary', **{n: 'provider' for n in steps['provider']}}
    return collect(reg.PRODUCTION, root, api_get, roles, lambda pinned: evidence_from_tree(root, pinned),
                   steps['kat'], evaluator_source_sha(root))


def smoke_evaluation(root=ev.ROOT, get=api_get, scenarios=None):
    """Synthetic real-GitHub smoke (activation items 8-9): classification of every entry of the SMOKE registry with the
    production classifier, plus live provider observations of every run key the scenario manifest names (including
    runs that never registered), so that each scenario is proven by provider facts. No evidence root, no KAT: records
    are test records and never PASS."""
    import oracle_activation_v2 as act
    evaluation, commits = collect(reg.SMOKE, root, get, act.SMOKE_ROLES, g1.Evidence.build(), None, None)
    named = [{'run_id': r['run_id'], 'run_attempt': r['run_attempt']} for r in (scenarios or {}).get('runs', [])
             if type(r) is dict and oa.positive(r.get('run_id')) and oa.positive(r.get('run_attempt'))]
    seen = {reg.run_key(o) for o in evaluation.provider}
    provider = list(evaluation.provider) + [o for o in provider_observations(get, named, act.SMOKE_ROLES)
                                            if reg.run_key(o) not in seen]
    try:
        reg.authoritative_registry(commits, evaluation.git, reg.SMOKE)
    except (reg.RegistryInvalid, TypeError):
        return {'schema': act.SMOKE_EVALUATION_SCHEMA, 'main_head_sha': evaluation.git.main_head_sha,
                'blocker': 'REGISTRY_INVALID', 'registry_head': None, 'attempts': [], 'unbound_attempts': [],
                'provider': [], 'records': []}
    analysis = g1.analyze(evaluation)
    disclosure = g1._disclosure(analysis) if analysis.blocker is None else {'attempts': [], 'unbound_attempts': []}
    identities = sorted({e['measurement_identity_sha256'] for e in evaluation.entries})
    return {'schema': act.SMOKE_EVALUATION_SCHEMA, 'main_head_sha': analysis.main_head_sha,
            'blocker': analysis.blocker, 'registry_head': analysis.registry_head,
            'attempts': disclosure['attempts'], 'unbound_attempts': disclosure['unbound_attempts'],
            'provider': sorted(provider, key=reg.run_key),
            'records': [g1.g1_test(i, evaluation, analysis)[1] for i in identities]}


# --- CLI -------------------------------------------------------------------------------------------------------------

def _output(name, value, env):
    path = env.get('GITHUB_OUTPUT')
    if path:
        with open(path, 'a', encoding='utf-8') as file:
            file.write(f'{name}={value}\n')


def main(argv, env=os.environ):
    command, args = (argv[0], argv[1:]) if argv else (None, [])
    profile = reg.SMOKE if command and command.startswith('smoke-') else reg.PRODUCTION
    try:
        if command == 'genesis' and len(args) == 2 and args[0] in ('production', 'smoke'):
            p = reg.PRODUCTION if args[0] == 'production' else reg.SMOKE
            gitdir = init_bare(args[1])
            commit = genesis_commit(gitdir, p)
            git(gitdir, 'update-ref', p.registry_ref, commit)
            print(f'genesis_sha256={ev.hc(reg.make_genesis(p.g1_freeze_sha256, p))}')
            print(f'root_commit={commit}')
            print(f'ref={p.registry_ref}')
        elif command in ('register', 'smoke-register') and not args:
            entry = register(profile, env, root=ev.ROOT, token=env.get('GITHUB_TOKEN'))
            _output('entry_sha256', entry['entry_sha256'], env)
            print(f"registered sequence={entry['sequence']} entry_sha256={entry['entry_sha256']}")
        elif command in ('bind', 'smoke-bind') and len(args) == 1:
            binding = bind(profile, env, env.get('REGISTER_ENTRY_SHA256'), root=ev.ROOT,
                           token=env.get('GITHUB_TOKEN'))
            write_new(args[0], ev.canonical(binding))
            print(f"bound sequence={binding['entry_sequence']} observed_head={binding['observed_head']['sequence']}")
        elif command == 'smoke-evaluate' and len(args) == 2:
            scenarios = ev.parse_doc(Path(args[0]).read_bytes())
            write_new(args[1], ev.canonical(smoke_evaluation(ev.ROOT, scenarios=scenarios)))
            print('smoke registry evaluated')
        elif command == 'g1' and len(args) == 2:
            record = g1._production_evaluate(args[0]) if ev.HEX64.match(args[0]) else None
            if record is None:
                print('G1: NOT_PASSED V3_NOT_ACTIVE')
                return 1
            write_new(args[1], ev.canonical(record))
            print(f"G1: {record['verdict']} {' '.join(record['blockers'])}".rstrip())
            return 0 if record['verdict'] == 'PASS' else 1
        else:
            print(__doc__, file=sys.stderr)
            return 2
    except Refusal as refusal:
        print(f'REFUSED {refusal.code}', file=sys.stderr)
        return 3
    except (TransportError, OSError, KeyError, TypeError, ValueError):
        print('registry transport: incomplete or inconsistent data', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
