"""DELSK-003A C1-B: registry Git transport, register/bind runner and evaluation inputs (oracle_registry_git.py).

Everything runs against local bare repositories: a test-only global Git config (temporary HOME) rewrites the constant
registry remote https://github.com/definitely-stable/Shift-lab.git to a local bare repository, so the code under test
keeps its authority constants and no network, GitHub write, natural byte or codec is involved. The source repository
holds only the committed metadata that git_source reads (workflow, frozen v1 files, locks, code manifest).
"""
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import oracle_attempts as oa
import oracle_activation_v2 as act
import oracle_eval as ev
import oracle_g1_v2 as g1
import oracle_registry_git as rg
import oracle_registry_v2 as reg

REPO = reg.REPOSITORY
IDENTITY_FILES = (reg.WORKFLOW_PATH, '.work/oracle/freeze.json', '.work/oracle/codec-lock.json',
                  '.work/corpus/e1/candidate-lock.json', '.work/corpus/pilot-v1/corpus-lock.json.gz',
                  *(f'.work/tools/{n}' for n in ev.CODE_FILES))


def sh(cwd, *args, env=None):
    return subprocess.run(['git', '-C', str(cwd), *args], check=True, capture_output=True,
                          env={**os.environ, **COMMIT_ENV, **(env or {})}).stdout.decode().strip()


COMMIT_ENV = {**rg.COMMITTER, 'GIT_CONFIG_NOSYSTEM': '1'}


class World:
    """Temporary source checkout + bare remote reachable under the constant GitHub URL."""

    def __init__(self, tmp):
        self.tmp = Path(tmp)
        self.home = self.tmp / 'home'
        self.home.mkdir()
        self.remote = self.tmp / 'remote.git'
        self.root = self.tmp / 'checkout'
        (self.home / '.gitconfig').write_text(
            f'[url "{self.remote.as_posix()}"]\n\tinsteadOf = {reg.REGISTRY_REMOTE}\n'
            f'[init]\n\tdefaultBranch = main\n[user]\n\tname = t\n\temail = t@example.invalid\n'
            f'[commit]\n\tgpgsign = false\n')
        self.env = patch.dict(os.environ, {'HOME': str(self.home)})
        self.env.start()
        subprocess.run(['git', 'init', '--quiet', '-b', 'main', str(self.root)], check=True)
        for name in IDENTITY_FILES:
            dest = self.root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes((ev.ROOT / name).read_bytes())
        self.base = self.commit('base: committed metadata only')
        self.docs = self.commit('docs: same science identity', {'README.md': b'docs\n'})
        subprocess.run(['git', 'clone', '--quiet', '--bare', str(self.root), str(self.remote)], check=True,
                       capture_output=True)
        self.main = self.docs

    def close(self):
        self.env.stop()

    def commit(self, message, files=None, branch='main'):
        for name, data in (files or {}).items():
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
            (self.root / name).write_bytes(data)
        sh(self.root, 'add', '-A')
        sh(self.root, 'commit', '--quiet', '--allow-empty', '-m', message)
        return sh(self.root, 'rev-parse', 'HEAD')

    def publish_main(self, sha):
        sh(self.root, 'push', '--quiet', '--force', str(self.remote), f'{sha}:refs/heads/main')
        self.main = sha

    def genesis(self, profile=reg.SMOKE):
        with tempfile.TemporaryDirectory() as t:
            gitdir = rg.init_bare(Path(t) / 'g.git')
            root = rg.genesis_commit(gitdir, profile)
            sh(gitdir, 'push', '--quiet', str(self.remote), f'{root}:{profile.registry_ref}')
        return root

    def remote_ref(self, ref):
        out = subprocess.run(['git', '-C', str(self.remote), 'rev-parse', '--verify', '--quiet', ref],
                             capture_output=True)
        return out.stdout.decode().strip() or None

    def env_of(self, run_id, attempt=1, sha=None, profile=reg.SMOKE, **over):
        sha = sha or self.main
        e = {'GITHUB_EVENT_NAME': 'workflow_dispatch', 'GITHUB_REPOSITORY': REPO, 'GITHUB_SHA': sha,
             'GITHUB_WORKFLOW_SHA': sha, 'GITHUB_REF': 'refs/heads/main', 'SOURCE_SHA': sha,
             'GITHUB_WORKFLOW_REF': f'{REPO}/{profile.workflow_path}@refs/heads/main',
             'GITHUB_RUN_ID': str(run_id), 'GITHUB_RUN_ATTEMPT': str(attempt)}
        e.update(over)
        return e

    def registry(self, profile=reg.SMOKE):
        """(commits, genesis, entries) of the remote registry, through the reader under test."""
        with tempfile.TemporaryDirectory() as t:
            gitdir = rg.init_bare(Path(t) / 'r.git')
            head = rg.fetch(gitdir, reg.REGISTRY_REMOTE, profile.registry_ref)
            commits = rg.registry_history(gitdir, head)
        return (commits, *rg.lenient(commits))

    def snap(self, extra=()):
        rg.fetch(self.root, reg.REGISTRY_REMOTE, rg.MAIN_REF)
        _, _, entries = self.registry()
        return rg.snapshot(self.root, self.main, rg.referenced_commits(entries) | set(extra))


def no_api(path):
    raise AssertionError(f'unexpected provider read {path}')


class Provider:
    """Fake constant provider API: GitHub-shaped run, attempt and jobs documents (only what contract 8.3 reads)."""

    def __init__(self, world, profile=reg.SMOKE):
        self.world, self.profile, self.runs = world, profile, {}

    def add(self, run_id, attempt, scenario, sha=None):
        """Jobs and steps as GitHub reports them for each smoke scenario (status, conclusion per job and step)."""
        sha = sha or self.world.main
        ok, skip, fail, cancel = (('completed', c) for c in ('success', 'skipped', 'failure', 'cancelled'))
        register = [(act.SOURCE_STEP, ok), ('Synthetic hold before register', skip), (act.REGISTER_STEP, ok)]
        measure = {  # checkout, hold, bind, retain binding, synthetic stop, boundary
            'stop-before-boundary': ('failure', (ok, skip, ok, ok, fail, skip)),
            'cross-boundary': ('success', (ok, skip, ok, ok, skip, ok)),
            'rerun-failed': ('failure', (ok, skip, fail, skip, skip, skip)),
            'cancel-after-register': ('cancelled', (ok, cancel, skip, skip, skip, skip)),
        }
        names = ('Checkout', 'Synthetic hold before the boundary', act.BIND_STEP,
                 'Retain binding sidecar before the boundary', 'Synthetic stop before the boundary', act.BOUNDARY_STEP)
        if scenario == 'cancel-before-register':
            jobs = [('register', 'cancelled', [(act.SOURCE_STEP, ok), ('Synthetic hold before register', cancel),
                                               (act.REGISTER_STEP, skip)]),
                    ('measure', 'skipped', [])]
        else:
            conclusion, steps = measure[scenario]
            jobs = [('measure', conclusion, list(zip(names, steps)))]
            if scenario != 'rerun-failed':  # a failed-job rerun does not execute register again
                jobs.insert(0, ('register', 'success', register))
        run = self.runs.setdefault(run_id, {'attempts': {}})
        run['attempts'][attempt] = {'sha': sha, 'jobs': jobs}

    def delete(self, run_id):
        self.runs.pop(run_id)

    def __call__(self, path):
        base = f'/repos/{REPO}/actions/runs/'
        m = re.fullmatch(re.escape(base) + r'(\d+)(?:/attempts/(\d+)(/jobs\?per_page=100&page=1)?)?', path)
        if m is None:
            if path.startswith(f'/repos/{REPO}/pulls/'):
                return None
            raise AssertionError(path)
        run = self.runs.get(int(m[1]))
        if run is None:
            return None
        latest = max(run['attempts'])
        if m[2] is None:
            return {'id': int(m[1]), 'run_attempt': latest}
        a = run['attempts'].get(int(m[2]))
        if a is None:
            return None
        if m[3] is None:
            return {'id': int(m[1]), 'run_attempt': int(m[2]), 'head_sha': a['sha'], 'head_branch': 'main',
                    'path': self.profile.workflow_path, 'event': 'workflow_dispatch', 'status': 'completed'}
        jobs = [{'id': int(m[1]) * 100 + int(m[2]) * 10 + n, 'name': name, 'run_id': int(m[1]),
                 'run_attempt': int(m[2]), 'head_sha': a['sha'], 'status': 'completed', 'conclusion': conclusion,
                 'steps': [{'name': s, 'number': i, 'status': st, 'conclusion': c}
                           for i, (s, (st, c)) in enumerate(steps, 1)]}
                for n, (name, conclusion, steps) in enumerate(a['jobs'])]
        return {'total_count': len(jobs), 'jobs': jobs}


SMOKE_RUNS = (('stop-before-boundary', 31, 1), ('cross-boundary', 32, 1), ('rerun-all', 31, 2),
              ('rerun-failed', 31, 3), ('cancel-after-register', 33, 1), ('deleted-run', 34, 1),
              ('cancel-before-register', 35, 1))


def smoke_documents(world, provider):
    """Every activation item 8-9 scenario against a local smoke registry (real register code) and the fake provider;
    returns (smoke-evaluate output, scenario manifest)."""
    if world.remote_ref(reg.SMOKE_REGISTRY_REF) is None:
        world.genesis()
    for name, run_id, attempt in SMOKE_RUNS:
        if name not in ('rerun-failed', 'cancel-before-register'):  # those never register
            rg.register(reg.SMOKE, world.env_of(run_id, attempt), world.root, no_api)
        provider.add(run_id, attempt, {'rerun-all': 'stop-before-boundary',
                                       'deleted-run': 'stop-before-boundary'}.get(name, name))
    provider.delete(34)
    scenarios = {'schema': act.SCENARIOS_SCHEMA, 'workflow': reg.SMOKE_WORKFLOW_PATH,
                 'registry_ref': reg.SMOKE_REGISTRY_REF,
                 'runs': [{'scenario': s, 'run_id': r, 'run_attempt': a,
                           'html_url': f'https://github.com/{REPO}/actions/runs/{r}'} for s, r, a in SMOKE_RUNS]}
    return rg.smoke_evaluation(world.root, provider, scenarios), scenarios


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.w = World(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(self.w.close)

    def register(self, run_id, attempt=1, profile=reg.SMOKE, **over):
        return rg.register(profile, self.w.env_of(run_id, attempt, profile=profile, **over), self.w.root, no_api)

    def refused(self, code, fn, *args, **kwargs):
        with self.assertRaises(rg.Refusal) as caught:
            fn(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)


class Genesis(Base):
    def test_root_commits_are_deterministic_and_pinned(self):
        for profile in reg.PROFILES:
            with self.subTest(profile.name), tempfile.TemporaryDirectory() as t:
                gitdir = rg.init_bare(Path(t) / 'g.git')
                root = rg.genesis_commit(gitdir, profile)
                self.assertEqual(root, act.ROOT_COMMIT[profile.name])
                commits = rg.registry_history(gitdir, root)
                self.assertEqual(commits, [(0, {'genesis.json': rg.genesis_bytes(profile), 'entries.jsonl': b''})])
                self.assertEqual(ev.hc(ev.parse_doc(rg.genesis_bytes(profile))), act.GENESIS_SHA256[profile.name])
        self.assertEqual(ev.parse_doc(rg.genesis_bytes(reg.PRODUCTION))['g1_freeze_sha256'], reg.G1_FREEZE_SHA256)

    def test_profiles_never_validate_each_other(self):
        snap = rg.snapshot(self.w.root, self.w.main, ())
        for profile in reg.PROFILES:
            commits = [(0, {'genesis.json': rg.genesis_bytes(profile), 'entries.jsonl': b''})]
            self.assertIsInstance(reg.authoritative_registry(commits, snap, profile), reg.PhysicalRegistry)
            other = reg.SMOKE if profile is reg.PRODUCTION else reg.PRODUCTION
            with self.assertRaises(reg.RegistryInvalid):
                reg.authoritative_registry(commits, snap, other)
        with self.assertRaises(reg.RegistryInvalid):  # a look-alike profile is not an authority
            import dataclasses
            reg.authoritative_registry(commits, snap, dataclasses.replace(reg.SMOKE, name='x'))

    def test_profile_schema_derivation_touches_three_values_only(self):
        self.assertEqual(ev.compact(reg._profile_schemas(reg.REGISTRY_REF, reg.WORKFLOW_PATH)), ev.compact(reg._SCHEMAS))
        diff = [k for k in reg._SCHEMAS['$defs'] if reg._SCHEMAS['$defs'][k] != reg.SMOKE.schemas['$defs'][k]]
        self.assertEqual(diff, ['registry_entry', 'registry_genesis'])

    def test_live_registry_root_must_be_the_reviewed_genesis(self):
        self.assertIsNone(rg.registry_root(self.w.root))
        self.w.genesis(reg.PRODUCTION)
        self.assertEqual(rg.registry_root(self.w.root), act.ROOT_COMMIT['production'])
        with tempfile.TemporaryDirectory() as t:  # same genesis bytes, another root commit (other date/author)
            gitdir = rg.init_bare(Path(t) / 'g.git')
            forged = rg.make_commit(gitdir, {'genesis.json': rg.genesis_bytes(reg.PRODUCTION), 'entries.jsonl': b''},
                                    None, 'look-alike genesis')
            sh(gitdir, 'push', '--quiet', '--force', str(self.w.remote), f'{forged}:{reg.REGISTRY_REF}')
        self.assertNotEqual(rg.registry_root(self.w.root), act.ROOT_COMMIT['production'])

    def test_genesis_cli_is_local_only(self):
        out = self.w.tmp / 'cli.git'
        self.assertEqual(rg.main(['genesis', 'production', str(out)]), 0)
        self.assertEqual(sh(out, 'rev-parse', reg.REGISTRY_REF), act.ROOT_COMMIT['production'])
        self.assertIsNone(self.w.remote_ref(reg.REGISTRY_REF))  # nothing was pushed anywhere


class Register(Base):
    def setUp(self):
        super().setUp()
        self.w.genesis()

    def test_append_readback_and_physical_form(self):
        first = self.register(11)
        second = self.register(12)
        commits, genesis, entries = self.w.registry()
        self.assertEqual(entries, [first, second])
        self.assertEqual([c[0] for c in commits], [0, 1, 1])
        self.assertEqual(reg.validate_physical(commits)[1], commits[-1][1]['entries.jsonl'])
        snap = self.w.snap()
        reg.authoritative_registry(commits, snap, reg.SMOKE)
        self.assertEqual((first['sequence'], first['workflow_path'], first['measured_source_sha']),
                         (1, reg.SMOKE_WORKFLOW_PATH, self.w.main))
        self.assertEqual(first['measurement_identity_sha256'], ev.hc(oa.git_identity(self.w.main, self.w.root)))
        self.assertIsNone(first['transition'])

    def test_retry_of_the_same_attempt_is_idempotent(self):
        entry = self.register(11)
        head = self.w.remote_ref(reg.SMOKE_REGISTRY_REF)
        self.assertEqual(self.register(11), entry)
        self.assertEqual(self.w.remote_ref(reg.SMOKE_REGISTRY_REF), head)

    def test_concurrent_writer_forces_refetch_and_retry(self):
        real = rg.push
        raced = []

        def racing(gitdir, remote, commit, ref, token=None):
            if not raced:
                raced.append(True)
                self.register(99)  # another attempt lands between fetch and push
            return real(gitdir, remote, commit, ref, token)

        with patch.object(rg, 'push', racing):
            mine = self.register(11)
        _, _, entries = self.w.registry()
        self.assertEqual([(e['run_id'], e['sequence']) for e in entries], [(99, 1), (11, 2)])
        self.assertEqual(entries[-1], mine)

    def test_rejected_push_is_bounded_and_writes_nothing(self):
        hook = self.w.remote / 'hooks' / 'pre-receive'
        hook.write_text('#!/bin/sh\necho "GH013: Repository rule violations found" >&2\nexit 1\n')
        hook.chmod(0o755)
        head = self.w.remote_ref(reg.SMOKE_REGISTRY_REF)
        calls = []
        real = rg.push
        with patch.object(rg, 'push', lambda *a, **k: calls.append(1) or real(*a, **k)), \
                self.assertRaises(rg.TransportError):
            self.register(11)
        self.assertEqual(len(calls), rg.PUSH_ROUNDS)
        self.assertEqual(self.w.remote_ref(reg.SMOKE_REGISTRY_REF), head)

    def test_refusals_write_nothing(self):
        head = self.w.remote_ref(reg.SMOKE_REGISTRY_REF)
        off_main = self.w.commit('off main', {'x': b'1'})
        sh(self.w.remote, 'fetch', '--quiet', str(self.w.root), f'{off_main}:refs/heads/side')
        cases = [('SOURCE_NOT_ON_MAIN', dict(sha=off_main)),
                 ('DISPATCH_REJECTED', dict(SOURCE_SHA='0' * 40)),
                 ('DISPATCH_REJECTED', dict(GITHUB_REF='refs/tags/v1')),
                 ('DISPATCH_REJECTED', dict(GITHUB_EVENT_NAME='push')),
                 ('DISPATCH_REJECTED', dict(GITHUB_WORKFLOW_REF=f'{REPO}/{reg.WORKFLOW_PATH}@refs/heads/main')),
                 ('DISPATCH_REJECTED', dict(GITHUB_RUN_ATTEMPT='0'))]
        for code, over in cases:
            with self.subTest(code, **{k: str(v)[:12] for k, v in over.items()}):
                self.refused(code, self.register, 11, **over)
        self.assertEqual(self.w.remote_ref(reg.SMOKE_REGISTRY_REF), head)

    def test_missing_or_corrupt_registry_is_never_written(self):
        sh(self.w.remote, 'update-ref', '-d', reg.SMOKE_REGISTRY_REF)
        self.refused('REGISTRY_INVALID', self.register, 11)
        self.assertIsNone(self.w.remote_ref(reg.SMOKE_REGISTRY_REF))
        # a commit that adds a third file makes the whole registry permanently invalid (5.2, 5.6)
        root = self.w.genesis()
        with tempfile.TemporaryDirectory() as t:
            gitdir = rg.init_bare(Path(t) / 'x.git')
            sh(gitdir, 'fetch', '--quiet', str(self.w.remote), f'{reg.SMOKE_REGISTRY_REF}:refs/x')
            bad = rg.make_commit(gitdir, {'genesis.json': rg.genesis_bytes(reg.SMOKE), 'entries.jsonl': b'',
                                          'extra': b'1'}, root, 'tamper')
            sh(gitdir, 'push', '--quiet', str(self.w.remote), f'{bad}:{reg.SMOKE_REGISTRY_REF}')
        self.refused('REGISTRY_INVALID', self.register, 11)
        self.assertEqual(self.w.remote_ref(reg.SMOKE_REGISTRY_REF), bad)

    def test_new_science_identity_needs_a_transition(self):
        self.register(11)
        code = self.w.commit('apparatus change', {'.work/tools/oracle_run.py':
                                                  (ev.ROOT / '.work/tools/oracle_run.py').read_bytes() + b'# x\n'})
        self.w.publish_main(code)
        self.refused('TRANSITION_REQUIRED', self.register, 12, sha=code)
        docs = self.w.commit('docs only', {'README.md': b'more docs\n'})
        self.w.publish_main(docs)
        self.refused('TRANSITION_REQUIRED', self.register, 12, sha=docs)  # still the new apparatus series

    def test_production_register_refuses_before_activation_without_any_read(self):
        self.w.genesis(reg.PRODUCTION)
        head = self.w.remote_ref(reg.REGISTRY_REF)
        with patch.object(rg, 'fetch', side_effect=AssertionError('read before activation')):
            self.refused('DISPATCH_REJECTED', self.register, 11, profile=reg.PRODUCTION)
        self.assertEqual(self.w.remote_ref(reg.REGISTRY_REF), head)
        self.assertEqual(rg.main(['register'], self.w.env_of(11, profile=reg.PRODUCTION)), 3)

    def test_production_profile_path_with_a_stand_in_activation(self):
        """The production code path itself (frozen schemas, real freeze-v2 digest) on a local remote."""
        self.w.genesis(reg.PRODUCTION)
        with patch.object(g1, 'ACTIVATION_RECORD', '1' * 64):
            entry = self.register(11, profile=reg.PRODUCTION)
        commits, genesis, entries = self.w.registry(reg.PRODUCTION)
        self.assertEqual(entries, [entry])
        reg.authoritative_registry(commits, rg.snapshot(self.w.root, self.w.main, {self.w.main}), reg.PRODUCTION)
        self.assertEqual(entry['workflow_path'], reg.WORKFLOW_PATH)
        self.assertEqual(rg.main(['register'], {**self.w.env_of(12, profile=reg.PRODUCTION)}), 3)


class Bind(Base):
    def setUp(self):
        super().setUp()
        self.w.genesis()
        self.entry = rg.register(reg.SMOKE, self.w.env_of(21), self.w.root, no_api)

    def bind(self, run_id=21, attempt=1, entry_sha256=None, **over):
        return rg.bind(reg.SMOKE, self.w.env_of(run_id, attempt, **over),
                       self.entry['entry_sha256'] if entry_sha256 is None else entry_sha256, self.w.root, no_api)

    def test_bound_sidecar_witnesses_the_head(self):
        rg.register(reg.SMOKE, self.w.env_of(22), self.w.root, no_api)
        binding = self.bind()
        self.assertTrue(reg.valid(binding, 'attempt_binding'))
        self.assertEqual((binding['entry_sequence'], binding['entry_sha256'], binding['observed_head']['sequence']),
                         (1, self.entry['entry_sha256'], 2))
        out = self.w.tmp / 'b' / 'binding.json'
        env = {**self.w.env_of(21), 'REGISTER_ENTRY_SHA256': self.entry['entry_sha256']}
        with patch.object(ev, 'ROOT', self.w.root):  # the CLI reads the checkout at call time, never a default
            self.assertEqual(rg.main(['smoke-bind', str(out)], env), 0)
            self.assertEqual(ev.parse_doc(out.read_bytes())['entry_sha256'], self.entry['entry_sha256'])
            self.assertEqual(rg.main(['smoke-bind', str(out)], env), 1)  # never overwritten

    def test_unbound_executions_stop_before_the_boundary(self):
        cases = {'rerun failed jobs: attempt without entry': dict(attempt=2),
                 'wrong register output': dict(entry_sha256='0' * 64),
                 'no register output': dict(entry_sha256=''),
                 'other source': dict(sha=self.w.base),
                 'unregistered run': dict(run_id=23)}
        for name, kw in cases.items():
            with self.subTest(name):
                self.refused('REGISTRY_UNBOUND', self.bind, **kw)
        env = {**self.w.env_of(21, 2), 'REGISTER_ENTRY_SHA256': self.entry['entry_sha256']}
        with patch.object(ev, 'ROOT', self.w.root):
            self.assertEqual(rg.main(['smoke-bind', str(self.w.tmp / 'x.json')], env), 3)
        self.assertFalse((self.w.tmp / 'x.json').exists())

    def test_production_bind_cannot_use_the_smoke_registry(self):
        self.refused('REGISTRY_UNBOUND', rg.bind, reg.PRODUCTION, self.w.env_of(21, profile=reg.PRODUCTION),
                     self.entry['entry_sha256'], self.w.root, no_api)


class History(Base):
    def test_non_linear_or_non_regular_history_is_invalid(self):
        with tempfile.TemporaryDirectory() as t:
            gitdir = rg.init_bare(Path(t) / 'h.git')
            root = rg.genesis_commit(gitdir, reg.SMOKE)
            other = rg.make_commit(gitdir, {'genesis.json': rg.genesis_bytes(reg.SMOKE), 'entries.jsonl': b''}, None,
                                   'second root')
            tree = sh(gitdir, 'rev-parse', f'{root}^{{tree}}')
            merge = sh(gitdir, 'commit-tree', tree, '-p', root, '-p', other, '-m', 'merge')
            with self.assertRaises(reg.RegistryInvalid):
                reg.validate_physical(rg.registry_history(gitdir, merge))
            g = subprocess.run(['git', '-C', str(gitdir), 'hash-object', '-w', '--stdin'],
                               input=rg.genesis_bytes(reg.SMOKE), capture_output=True, check=True).stdout.decode().strip()
            e = subprocess.run(['git', '-C', str(gitdir), 'hash-object', '-w', '--stdin'], input=b'',
                               capture_output=True, check=True).stdout.decode().strip()
            for mode in ('100755', '120000'):
                t2 = subprocess.run(['git', '-C', str(gitdir), 'mktree'], capture_output=True, check=True,
                                    input=f'{mode} blob {g}\tgenesis.json\n100644 blob {e}\tentries.jsonl\n'.encode()
                                    ).stdout.decode().strip()
                c = sh(gitdir, 'commit-tree', t2, '-m', mode)
                with self.subTest(mode), self.assertRaises(reg.RegistryInvalid):
                    reg.validate_physical(rg.registry_history(gitdir, c))


class Evaluation(Base):
    """Inputs of an evaluation (contract 9.0) and the production classifier over real Git + fake provider."""

    def setUp(self):
        super().setUp()
        self.w.genesis()
        self.provider = Provider(self.w)

    def run_scenario(self, run_id, attempt, scenario, register=True):
        if register:
            rg.register(reg.SMOKE, self.w.env_of(run_id, attempt), self.w.root, no_api)
        self.provider.add(run_id, attempt, scenario)

    def test_smoke_scenarios_classify_as_contract_8_and_10(self):
        doc, scenarios = smoke_documents(self.w, self.provider)
        classes = {(a['run_id'], a['run_attempt']): a['class'] for a in doc['attempts']}
        self.assertIsNone(doc['blocker'])
        self.assertEqual(classes, {(31, 1): 'PRE', (32, 1): 'MISSING', (31, 2): 'PRE', (33, 1): 'PRE',
                                   (34, 1): 'MISSING'})
        self.assertEqual(doc['unbound_attempts'], [])
        self.assertTrue(all(r['verdict'] != 'PASS' and r['authority'] is None for r in doc['records']))
        self.assertIn((35, 1), {(o['run_id'], o['run_attempt']) for o in doc['provider']})  # unregistered, observed
        self.assertEqual(act.verify_smoke(doc, scenarios), [])

    def test_failed_job_rerun_that_crosses_the_boundary_is_unbound(self):
        self.run_scenario(41, 1, 'stop-before-boundary')
        self.provider.add(41, 2, 'cross-boundary')  # attempt 2 without entry, boundary started
        doc = rg.smoke_evaluation(self.w.root, self.provider)
        self.assertEqual([(u['run_id'], u['run_attempt']) for u in doc['unbound_attempts']], [(41, 2)])
        self.assertTrue(all(r['verdict'] == 'INVALID' for r in doc['records']))

    def test_collect_pins_main_and_rereads(self):
        self.run_scenario(51, 1, 'stop-before-boundary')
        x, commits = rg.collect(reg.SMOKE, self.w.root, self.provider, act.ROLES, g1.Evidence.build(), None, None)
        self.assertEqual((x.git.main_head_sha, x.main_reread), (self.w.main, self.w.main))
        self.assertEqual(x.registry_reread, reg.head(x.genesis, list(x.entries)))
        self.assertEqual(len(commits), 2)
        real = rg.registry_history
        moved = []

        def moving(gitdir, head):  # registry and main move while the evaluation reads
            if not moved:
                moved.append(1)
                rg.register(reg.SMOKE, self.w.env_of(52), self.w.root, no_api)
                self.w.publish_main(self.w.commit('concurrent merge', {'y': b'1'}))
            return real(gitdir, head)

        with patch.object(rg, 'registry_history', moving):
            x, _ = rg.collect(reg.SMOKE, self.w.root, self.provider, act.ROLES, g1.Evidence.build(), None, None)
        a = g1.analyze(x)
        self.assertEqual(a.blocker, 'REGISTRY_STALE')
        self.assertNotEqual(x.main_reread, x.git.main_head_sha)

    def test_evidence_root_is_read_from_the_pinned_tree(self):
        key = '7-1'
        binding = {'schema': 'delsk.oracle.attempt-binding.v1'}
        pinned = self.w.commit('evidence', {f'{rg.V2_ROOT}bindings/{key}.json': ev.canonical(binding),
                                            f'{rg.V2_ROOT}stray.txt': b'x'})
        os.symlink('bindings', self.w.root / rg.V2_ROOT / 'link')
        later = self.w.commit('symlink')
        evidence = rg.evidence_from_tree(self.w.root, pinned)
        self.assertEqual(sorted(evidence.foreign_paths), [f'bindings/{key}.json', 'stray.txt'])
        self.assertIn('link', rg.evidence_from_tree(self.w.root, later).foreign_paths)
        (self.w.root / rg.V2_ROOT / 'stray.txt').unlink()  # the working tree is never read
        self.assertIn('stray.txt', rg.evidence_from_tree(self.w.root, pinned).foreign_paths)


class Production(Base):
    def test_no_read_before_activation(self):
        identity = '0' * 64
        with patch.object(rg, 'fetch', side_effect=AssertionError('read')), \
                patch.object(rg, 'api_get', side_effect=AssertionError('read')):
            self.assertEqual(g1.g1_production(identity), ('NOT_PASSED', ['V2_NOT_ACTIVE']))
            self.assertIsNone(g1._production_evaluate(identity))
            self.assertEqual(rg.main(['g1', identity, str(self.w.tmp / 'r.json')]), 1)
        self.assertFalse((self.w.tmp / 'r.json').exists())

    def test_unverified_activation_record_keeps_v2_inactive(self):
        self.w.genesis(reg.PRODUCTION)
        with patch.object(ev, 'ROOT', self.w.root), patch.object(g1, 'ACTIVATION_RECORD', '2' * 64), \
                patch.object(rg, 'api_get', side_effect=AssertionError('provider read without activation')):
            self.assertIsNone(rg.production_inputs('2' * 64))
            self.assertEqual(g1.g1_production('3' * 64), ('NOT_PASSED', ['V2_NOT_ACTIVE']))
            self.w.publish_main(self.w.commit('record', {act.ACTIVATION_FILE: b'{}\n'}))
            self.assertIsNone(rg.production_inputs(ev.sha256(b'{}\n')))  # bytes match, record invalid


if __name__ == '__main__':
    unittest.main()
