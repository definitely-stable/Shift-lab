"""DELSK-003A C1-B: activation tooling of contract-v3 section 5 (oracle_activation_v2.py), offline.

1. static witness of contract 4.1 / 12.2 on the reviewed workflows, and the mutations it must reject;
2. ruleset evidence (item 7), smoke scenarios (items 8-9) and write-surface evidence (item 10) verifiers;
3. the write-surface probe against a local remote that emulates server-side rule rejection, and its preflight;
4. a complete synthetic activation record verified end to end in a temporary tree (never committed), and the facts
   that the repository itself carries no activation record, no genesis and no activation evidence.
"""
import copy
import datetime
from pathlib import Path
import sys
import tempfile
import unittest
import unittest.mock
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import oracle_activation_v2 as act
import oracle_eval as ev
import oracle_g1_v2 as g1
import oracle_registry_v2 as reg
import oracle_registry_git as rg
from test_oracle_registry_git import Provider, World, smoke_documents

ROOT = ev.ROOT
REPO = reg.REPOSITORY


def text(path):
    return (ROOT / path).read_text(encoding='utf-8')


PILOT, SMOKE, WRITE, KAT = (text(p) for p in (act.PILOT_WORKFLOW, act.SMOKE_WORKFLOW, act.WRITE_SURFACE_WORKFLOW,
                                              act.KAT_WORKFLOW))


SOURCE_BLOCK = PILOT[PILOT.index(f'      - name: {act.SOURCE_STEP}'):PILOT.index(f'      - name: {act.REGISTER_STEP}')]
CHECKOUT = ('      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1\n        with:\n'
            '          persist-credentials: false\n          fetch-depth: 0\n')


def swap(source, old, new):
    assert source.count(old) == 1, old
    return source.replace(old, new)


class Workflows(unittest.TestCase):
    def test_reviewed_workflows_pass(self):
        self.assertEqual(act.check_pilot_workflow(PILOT), [])
        self.assertEqual(act.check_smoke_workflow(SMOKE), [])
        self.assertEqual(act.check_write_surface_workflow(WRITE), [])
        self.assertEqual(act.check_kat_workflow(KAT), [])
        self.assertEqual(act.main(['check-workflows']), 0)

    def test_pilot_layout(self):
        jobs = act.workflow_jobs(PILOT)
        names = [s['name'] for s in jobs['measure']['steps']]
        self.assertLess(names.index(act.BIND_STEP), names.index(act.BOUNDARY_STEP))
        self.assertEqual(tuple(names[:names.index(act.BOUNDARY_STEP)]), act.PILOT_PRE_BOUNDARY)
        self.assertEqual([s['name'] for s in jobs['register']['steps']], list(act.PILOT_REGISTER_STEPS))

    def test_pilot_mutations_are_rejected(self):
        bind = act.BIND_RUN['production']
        boundary_if = ("if: steps.bind.outcome == 'success' && steps.binding_record.outcome == 'success' "
                       "&& steps.admission.outcome == 'success'")
        tmpfs = '      - name: Hard capped transient work filesystem'
        mutants = {
            'boundary without bind': swap(PILOT, boundary_if, "if: steps.admission.outcome == 'success'"),
            'boundary under always()': swap(PILOT, boundary_if, 'if: always()'),
            'bind may fail open': swap(PILOT, f'        run: {bind}',
                                       f'        continue-on-error: true\n        run: {bind}'),
            'codec before boundary': swap(PILOT, tmpfs, '      - name: Early build\n'
                                                        '        run: python3 .work/tools/oracle_build.py x\n' + tmpfs),
            'natural fetch before boundary': swap(PILOT, tmpfs, '      - name: Fetch\n'
                                                                '        run: curl -sO https://example.invalid\n' + tmpfs),
            'post-boundary step without guard': swap(
                PILOT, f"if: always() && {act.BOUNDARY_STARTED} && steps.initialize.outcome == 'success' "
                       "&& steps.evidence_upload.outcome != 'success'",
                "if: always() && steps.initialize.outcome == 'success' && steps.evidence_upload.outcome != 'success'"),
            'negative guard accepts a never-evaluated boundary': PILOT.replace(
                act.BOUNDARY_STARTED, "steps.workload.outcome != 'skipped'"),
            'write token in measure': swap(PILOT, '    permissions:\n      contents: read\n      actions: read\n    env:',
                                           '    permissions:\n      contents: write\n    env:'),
            # review of PR 31: actions/checkout defaults `token` to the job's write-capable GITHUB_TOKEN
            'checkout in the write job': swap(PILOT, SOURCE_BLOCK, CHECKOUT),
            'checkout next to the anonymous fetch': swap(PILOT, f'{SOURCE_BLOCK}      - name: Register',
                                                         f'{SOURCE_BLOCK}{CHECKOUT}      - name: Register'),
            'token handed to the source step': swap(PILOT, "          GIT_TERMINAL_PROMPT: '0'\n        run: |\n"
                                                           "          git init -q .\n",
                                                    "          GIT_TERMINAL_PROMPT: '0'\n"
                                                    "          GITHUB_TOKEN: ${{ github.token }}\n        run: |\n"
                                                    "          git init -q .\n"),
            'source from another remote': PILOT.replace('https://github.com/definitely-stable/Shift-lab.git',
                                                        'https://example.invalid/fork.git', 1),
            'register depends on measure': swap(PILOT, '  register:\n    runs-on',
                                                '  register:\n    needs: measure\n    runs-on'),
            'push trigger': swap(PILOT, 'on:\n  workflow_dispatch:', 'on:\n  push:\n  workflow_dispatch:'),
            'unpinned action': PILOT.replace('actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1',
                                             'actions/checkout@v4', 1),
            'renamed boundary': PILOT.replace(act.BOUNDARY_STEP, 'Bounded pilot'),
            'bind after boundary': swap(swap(PILOT, act.BIND_STEP, 'TMP'), act.BOUNDARY_STEP, act.BIND_STEP).replace(
                'TMP', act.BOUNDARY_STEP),
            'shallow source fetch': swap(PILOT, 'fetch -q --no-tags', 'fetch -q --depth 1 --no-tags'),
        }
        for name, source in mutants.items():
            with self.subTest(name):
                self.assertTrue(act.check_pilot_workflow(source), name)

    def test_provider_steps_are_derived_from_the_reviewed_workflows(self):
        """Contract-v3 1.1 / 2 item 3: the closed sets equal what the reviewed measure jobs imply."""
        for source, expected in ((PILOT, act.PILOT_PROVIDER_STEPS), (SMOKE, act.SMOKE_PROVIDER_STEPS)):
            steps = act.workflow_jobs(source)['measure']['steps']
            x = [s['name'] for s in steps].index(act.BOUNDARY_STEP)
            self.assertEqual(act.provider_steps(steps, x), set(expected))
        self.assertLessEqual(set(act.SMOKE_PROVIDER_STEPS), set(act.PILOT_PROVIDER_STEPS))
        self.assertEqual({n for n, r in act.ROLES.items() if r == 'provider'}, set(act.PILOT_PROVIDER_STEPS))
        self.assertEqual({n for n, r in act.SMOKE_ROLES.items() if r == 'provider'}, set(act.SMOKE_PROVIDER_STEPS))
        # review of PR 32: only actions whose pinned action.yml declares runs.post get a Post <name> provider step
        self.assertEqual(act.POST_HOOK, {act.CHECKOUT_ACTION: True, act.UPLOAD_ACTION: False})
        for name in ('Post Retain immutable dispatch proof', 'Post Retain binding sidecar before the boundary',
                     'Post Retain attempt before codec setup'):
            self.assertNotIn(name, act.ROLES)
            self.assertNotIn(name, act.SMOKE_ROLES)

    def test_provider_step_mutations_are_rejected(self):
        """Contract-v3 2: no workflow step can hide behind a provider step name or add an unreviewed post hook."""
        last = '      - name: Require workload and export success'
        export = '      - name: Record export failure without debug data'
        checkout = f'      - name: {act.CHECKOUT_STEP}\n        uses: actions/checkout@'
        tmpfs = '      - name: Hard capped transient work filesystem'
        cache = ('      - name: Warm cache\n        uses: actions/cache@0057852bfaa89a56745cba8c7296529d2fc39830\n'
                 '        with:\n          path: x\n          key: x\n')
        second_checkout = ('      - name: Second checkout\n        uses: ' + act.CHECKOUT_ACTION + '\n'
                           '        with:\n          persist-credentials: false\n')
        upload = ('      - name: Extra upload\n'
                  '        uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a\n'
                  '        with:\n          name: x\n          path: x\n')
        mutants = {
            'workflow step named Complete job after the boundary': (
                swap(PILOT, last, '      - name: Complete job'), 'reserved for provider steps'),
            'workflow step named Post <checkout> after the boundary': (
                swap(PILOT, last, f'      - name: Post {act.CHECKOUT_STEP}'), 'reserved for provider steps'),
            'workflow step named Set up job': (swap(PILOT, export, '      - name: Set up job'),
                                               'reserved for provider steps'),
            'unnamed checkout before the boundary': (
                swap(PILOT, checkout, '      - uses: actions/checkout@'), 'named pinned checkout or upload-artifact'),
            'other action before the boundary': (swap(PILOT, tmpfs, cache + tmpfs),
                                                 'named pinned checkout or upload-artifact'),
            'extra upload adds no provider step but breaks the reviewed step list': (
                swap(PILOT, tmpfs, upload + tmpfs), 'steps before the boundary'),
            'unreviewed post hook before the boundary': (swap(PILOT, tmpfs, second_checkout + tmpfs),
                                                         'differ from the reviewed closed set'),
            'post-boundary action named like a pre-boundary step': (
                swap(PILOT, '      - name: Immutable sealed pilot envelope',
                     '      - name: Retain binding sidecar before the boundary'), 'explicit unique name'),
            'unnamed step in measure': (swap(PILOT, last + '\n        if: ', '      - if: '), 'explicit unique name'),
            'smoke: workflow step named Complete job': (
                swap(SMOKE, '      - name: Synthetic stop before the boundary', '      - name: Complete job'),
                'reserved for provider steps'),
        }
        for name, (source, reason) in mutants.items():
            with self.subTest(name):
                checker = act.check_smoke_workflow if name.startswith('smoke') else act.check_pilot_workflow
                problems = checker(source)
                self.assertTrue(any(reason in p for p in problems), problems)

    def test_smoke_and_write_surface_mutations_are_rejected(self):
        self.assertTrue(act.check_smoke_workflow(SMOKE.replace("echo 'synthetic boundary marker'",
                                                               'python3 .work/tools/oracle_run.py synthetic x')))
        self.assertTrue(act.check_smoke_workflow(SMOKE.replace('smoke-register', 'register')))
        self.assertTrue(act.check_smoke_workflow(SMOKE + '# reads the corpus\n'))
        self.assertTrue(act.check_write_surface_workflow(WRITE.replace('write-surface "$RUNNER_TEMP', 'x "$RUNNER_TEMP')))
        self.assertTrue(act.check_smoke_workflow(swap(SMOKE, SOURCE_BLOCK, CHECKOUT)))
        self.assertTrue(act.check_write_surface_workflow(swap(WRITE, SOURCE_BLOCK, CHECKOUT)))
        self.assertTrue(act.check_write_surface_workflow(WRITE.replace(
            '      - name: Retain write-surface evidence', '      - name: Leak\n        run: echo ${{ github.token }}\n'
            '      - name: Retain write-surface evidence')))
        self.assertTrue(act.check_kat_workflow(KAT.replace(' test_oracle_v2_mutants', '')))
        self.assertTrue(act.check_kat_workflow(KAT, 'Some other step'))

    def test_unreadable_layout_fails_closed(self):
        for bad in ('jobs:\n\tx:\n', 'name: x\n', 'jobs:\n  a:\n     odd: 1\n    steps:\n     - x\n'):
            with self.subTest(bad):
                self.assertTrue(act.check_pilot_workflow(bad))


def ruleset(id_, include, rules, bypass=()):
    return {'id': id_, 'target': 'branch', 'enforcement': 'active', 'source_type': 'Repository', 'source': REPO,
            'conditions': {'ref_name': {'include': list(include), 'exclude': []}},
            'rules': [{'type': r} for r in rules], 'bypass_actors': list(bypass)}


def rulesets_doc():
    admin = {'actor_id': 5, 'actor_type': 'RepositoryRole', 'bypass_mode': 'always'}
    return {'schema': act.RULESETS_SCHEMA, 'repository': REPO, 'collected_at': '2026-10-05T12:00:00Z',
            'rulesets': [ruleset(1, ['~DEFAULT_BRANCH'], ['deletion', 'non_fast_forward', 'pull_request'], [admin]),
                         ruleset(2, [reg.REGISTRY_REF, reg.SMOKE_REGISTRY_REF, *act.RETIRED_REGISTRY_REFS],
                                 ['deletion', 'non_fast_forward'])],
            'effective': {'refs/heads/main': [{'type': t} for t in ('deletion', 'non_fast_forward', 'pull_request')],
                          **{ref: [{'type': 'deletion'}, {'type': 'non_fast_forward'}]
                             for ref in (reg.REGISTRY_REF, reg.SMOKE_REGISTRY_REF, *act.RETIRED_REGISTRY_REFS)}}}


class Rulesets(unittest.TestCase):
    def test_contract_12_1(self):
        self.assertEqual(act.verify_rulesets(rulesets_doc()), [])

    def test_weakened_rulesets_are_rejected(self):
        def edit(fn):
            doc = rulesets_doc()
            fn(doc)
            return doc
        actions = {'actor_id': act.GITHUB_ACTIONS_APP_ID, 'actor_type': 'Integration', 'bypass_mode': 'always'}
        cases = {
            'registry deletion allowed': lambda d: d['rulesets'][1]['rules'].pop(0),
            'registry bypass': lambda d: d['rulesets'][1]['bypass_actors'].append(
                {'actor_id': 5, 'actor_type': 'RepositoryRole', 'bypass_mode': 'always'}),
            'workflow token bypasses main': lambda d: d['rulesets'][0]['bypass_actors'].append(actions),
            'main without pull_request': lambda d: d['rulesets'][0]['rules'].pop(),
            'evaluate mode': lambda d: d['rulesets'][1].update(enforcement='evaluate'),
            'exclusion': lambda d: d['rulesets'][1]['conditions']['ref_name'].update(exclude=[reg.REGISTRY_REF]),
            'effective rules absent': lambda d: d['effective'].update({reg.REGISTRY_REF: []}),
            'smoke registry unprotected': lambda d: d['rulesets'][1]['conditions']['ref_name'].update(
                include=[reg.REGISTRY_REF]),
            'org-level look-alike': lambda d: d['rulesets'][1].update(source_type='Organization'),
            'unknown field': lambda d: d.update(note='x'),
        }
        for name, fn in cases.items():
            with self.subTest(name):
                self.assertTrue(act.verify_rulesets(edit(fn)), name)


class WriteSurface(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.w = World(self._tmp.name)
        self.addCleanup(self.w.close)
        self.w.genesis(reg.PRODUCTION)
        self.env = {'GITHUB_WORKFLOW_REF': f'{REPO}/{act.WRITE_SURFACE_WORKFLOW}@refs/heads/main',
                    'GITHUB_RUN_ID': '7', 'GITHUB_RUN_ATTEMPT': '1'}
        self.rules = {'main': [{'type': t} for t in ('deletion', 'non_fast_forward', 'pull_request')],
                      reg.REGISTRY_REF.removeprefix('refs/heads/'): [{'type': 'deletion'}, {'type': 'non_fast_forward'}]}

    def get(self, path):
        prefix = f'/repos/{REPO}/rules/branches/'
        assert path.startswith(prefix), path
        return self.rules.get(path[len(prefix):], [])

    def refs(self):
        return self.w.remote_ref('refs/heads/main'), self.w.remote_ref(reg.REGISTRY_REF)

    def hook(self, script):
        hook = self.w.remote / 'hooks' / 'pre-receive'
        hook.write_text(script)
        hook.chmod(0o755)

    def test_server_rejection_of_all_three_writes(self):
        self.hook('#!/bin/sh\necho "GH013: Repository rule violations found" >&2\nexit 1\n')
        before = self.refs()
        doc = act.write_surface(self.env, self.get, str(self.w.remote))
        self.assertEqual(self.refs(), before)
        self.assertEqual(act.verify_write_surface(doc), [])
        self.assertEqual([a['operation'] for a in doc['attempts']], list(act.OPERATIONS))

    def test_missing_rulesets_mean_no_write_at_all(self):
        self.rules['main'] = self.rules['main'][:2]
        with patch.object(act, '_attempt', side_effect=AssertionError('write attempted')):
            doc = act.write_surface(self.env, self.get, str(self.w.remote))
        self.assertEqual((doc['preflight'], doc['attempts']), ('FAILED', []))
        self.assertTrue(act.verify_write_surface(doc))

    def test_an_accepted_write_stops_the_probe_and_fails(self):
        before = self.refs()
        doc = act.write_surface(self.env, self.get, str(self.w.remote))  # no server rule: the first push lands
        self.assertEqual(len(doc['attempts']), 1)
        self.assertNotEqual(self.refs()[0], before[0])
        self.assertEqual(self.refs()[1], before[1])  # the registry was never touched after that
        self.assertTrue(act.verify_write_surface(doc))

    def test_client_side_refusal_is_not_server_evidence(self):
        self.hook('#!/bin/sh\nexit 1\n')
        doc = act.write_surface(self.env, self.get, str(self.w.remote))
        doc['attempts'][1]['server_rejected'] = False
        self.assertTrue(act.verify_write_surface(doc))
        forged = copy.deepcopy(doc)
        forged['workflow_ref'] = f'{REPO}/.github/workflows/other.yml@refs/heads/main'
        self.assertTrue(act.verify_write_surface(forged))


def smoke_docs():
    """Realistic smoke documents: real register code on a local smoke registry and the fake GitHub provider."""
    if not hasattr(smoke_docs, 'cache'):
        with tempfile.TemporaryDirectory() as tmp:
            world = World(tmp)
            try:
                smoke_docs.cache = smoke_documents(world, Provider(world))
            finally:
                world.close()
    return copy.deepcopy(smoke_docs.cache)


class Smoke(unittest.TestCase):
    def test_required_scenarios(self):
        self.assertEqual(act.verify_smoke(*smoke_docs()), [])

    def test_labels_are_never_evidence(self):
        """Review of PR 31: a manifest label must not prove a scenario its own run key does not show."""
        def relabel(**moves):
            e, s = smoke_docs()
            for run in s['runs']:
                if run['scenario'] in moves:
                    run['run_id'], run['run_attempt'] = moves[run['scenario']]
                    run['html_url'] = f"https://github.com/{REPO}/actions/runs/{run['run_id']}"
            return e, s
        cases = {
            'one PRE run as three scenarios': relabel(**{'rerun-all': (31, 1), 'cancel-after-register': (31, 1)}),
            'absent key as cancel-before-register': relabel(**{'cancel-before-register': (999, 1)}),
            'absent key as rerun-failed': relabel(**{'rerun-failed': (31, 9)}),
            'rerun of another run': relabel(**{'rerun-all': (33, 1)}),
            'rerun-failed before rerun-all': relabel(**{'rerun-all': (31, 3), 'rerun-failed': (31, 2)}),
            'dispatch reusing a run ID': relabel(**{'cross-boundary': (31, 1)}),
            'PRE dispatch posing as cancelled': relabel(**{'cancel-after-register': (31, 2)}),
            'cancel-before-register that registered': relabel(**{'cancel-before-register': (33, 1)}),
        }
        for name, (e, s) in cases.items():
            with self.subTest(name):
                self.assertTrue(act.verify_smoke(e, s), name)

    def test_provider_facts_decide(self):
        def edit(fn):
            e, s = smoke_docs()
            fn(e, s, {(o['run_id'], o['run_attempt']): o for o in e['provider']})
            return e, s
        def job(o, name):
            return next(j for j in o['run']['jobs'] if j['name'] == name)
        cases = {
            'cancel run not cancelled': lambda e, s, o: job(o[33, 1], 'measure').update(conclusion='failure'),
            'cancel-before-register job succeeded': lambda e, s, o: job(o[35, 1], 'register').update(
                conclusion='success'),
            'cancel-before-register not observed': lambda e, s, o: e['provider'].remove(o[35, 1]),
            'rerun-failed bind succeeded': lambda e, s, o: next(
                x for x in job(o[31, 3], 'measure')['steps'] if x['role'] == 'bind').update(conclusion='success'),
            'deleted run still present': lambda e, s, o: o[34, 1].update(run=o[31, 1]['run']),
            'other workflow': lambda e, s, o: o[32, 1]['run'].update(workflow_path=reg.WORKFLOW_PATH),
            'pre misclassified': lambda e, s, o: e['attempts'][0].update({'class': 'MISSING'}),
            'unexplained entry': lambda e, s, o: e['attempts'].append({'run_id': 99, 'run_attempt': 1,
                                                                       'class': 'PRE', 'violations': []}),
            'unbound attempt': lambda e, s, o: e['unbound_attempts'].append({'run_id': 31, 'run_attempt': 3}),
            'registry blocker': lambda e, s, o: e.update(blocker='REGISTRY_INVALID'),
            'scenario missing': lambda e, s, o: s['runs'].pop(),
            'scenario repeated': lambda e, s, o: s['runs'].append(dict(s['runs'][0])),
            'foreign workflow manifest': lambda e, s, o: s.update(workflow=reg.WORKFLOW_PATH),
        }
        for name, fn in cases.items():
            with self.subTest(name):
                self.assertTrue(act.verify_smoke(*edit(fn)), name)


class FakeGitHub:
    """Pull requests, reviews and issue comments as the constant provider API returns them."""

    def __init__(self):
        self.docs = {}

    def __call__(self, path):
        return copy.deepcopy(self.docs.get(path))


AUTHOR = 'author-login'
GENESIS_PR = 38
GENESIS_MERGE, GENESIS_PARENT = 'a' * 40, '1' * 40


class Record(unittest.TestCase):
    """Complete synthetic v4 activation (enable record, genesis review live) in a temporary tree: proves the record is
    checkable end to end, not that any item holds on GitHub. Nothing of this is committed."""

    def setUp(self):
        self.files = {p: (ROOT / p).read_bytes() for p in (act.PILOT_WORKFLOW, act.SMOKE_WORKFLOW,
                                                            act.WRITE_SURFACE_WORKFLOW, act.KAT_WORKFLOW,
                                                            act.V3_INFRA['path'])}
        path = f'{act.EVIDENCE_DIR}rulesets.json'
        self.files[path] = ev.canonical(rulesets_doc())
        self.record = {'schema': act.SCHEMA, 'g1_contract': reg.G1_CONTRACT, 'g1_freeze_sha256': reg.G1_FREEZE_SHA256,
                       'steps': {'register': act.REGISTER_STEP, 'bind': act.BIND_STEP, 'boundary': act.BOUNDARY_STEP,
                                 'kat': act.KAT_STEP, 'provider': list(act.PILOT_PROVIDER_STEPS)},
                       'workflow_sha256': ev.sha256(PILOT.encode('utf-8')),
                       'registry': {'ref': reg.REGISTRY_REF, 'genesis_sha256': act.GENESIS_SHA256['production'],
                                    'root_commit': act.ROOT_COMMIT['production']},
                       'genesis_review': {'pull_request': GENESIS_PR, 'merge_commit_sha': GENESIS_MERGE},
                       'rulesets': {'path': path, 'sha256': ev.sha256(self.files[path])},
                       'v3_infra': dict(act.V3_INFRA)}
        tool_bytes = (ROOT / act.TOOL_FILE).read_bytes()
        self.at = {(GENESIS_MERGE, act.TOOL_FILE): tool_bytes}
        self.parents = {GENESIS_MERGE: GENESIS_PARENT}
        self.main = {GENESIS_PARENT, GENESIS_MERGE}
        self.gh = FakeGitHub()
        api = f'/repos/{REPO}'
        self.gh.docs[f'{api}/pulls/{GENESIS_PR}'] = {
            'number': GENESIS_PR, 'merged': True, 'merge_commit_sha': GENESIS_MERGE,
            'merged_at': '2026-10-06T10:00:00Z',
            'base': {'ref': 'main', 'repo': {'full_name': REPO}}, 'head': {'sha': 'd' * 40},
            'user': {'login': AUTHOR, 'type': 'User'}}
        self.gh.docs[f'{api}/pulls/{GENESIS_PR}/files?per_page=100&page=1'] = [
            {'filename': act.TOOL_FILE, 'status': 'modified', 'sha': act._git_blob_sha(tool_bytes),
             'patch': f"+reviewed genesis root {act.ROOT_COMMIT['production']}"}]

    def view(self, files=None):
        return act.TreeView((files or self.files).get, lambda c, p: self.at.get((c, p)), lambda c: c in self.main,
                            self.parents.get)

    def test_complete_record_verifies_and_binds_by_digest(self):
        self.assertEqual(act.validate_record(self.record, self.view()), [])
        self.assertEqual(act.validate_activation(self.record, self.view(), self.gh), [])
        self.files[act.ACTIVATION_FILE] = ev.canonical(self.record)
        digest = ev.sha256(self.files[act.ACTIVATION_FILE])
        self.assertEqual(act.activation_in_tree(self.view(), self.gh, digest), self.record)
        self.assertIsNone(act.activation_in_tree(self.view(), self.gh, '0' * 64))
        self.assertIsNone(act.activation_in_tree(self.view(), self.gh, None))

    def test_one_developer_merge_is_the_decision(self):
        # contract-v4 2 item 5: no review, no authorization comment is read; only the genesis PR and its files
        read = []
        self.assertEqual(act.validate_activation(self.record, self.view(), lambda path: read.append(path) or
                                                 self.gh(path)), [])
        self.assertTrue(read)
        self.assertFalse([path for path in read if '/issues/' in path or '/reviews' in path])

    def test_any_gap_keeps_v4_inactive(self):
        api = f'/repos/{REPO}'

        def doc(path):
            return self.gh.docs[path]
        cases = {  # (record edit, tree edit, provider edit)
            'step names': lambda r, f, g: r['steps'].update(boundary='x'),
            'provider steps widened': lambda r, f, g: r['steps'].update(
                provider=[*act.PILOT_PROVIDER_STEPS, 'Post Retain binding sidecar before the boundary']),
            'other workflow bytes': lambda r, f, g: r.update(workflow_sha256='0' * 64),
            'genesis root': lambda r, f, g: r['registry'].update(root_commit='0' * 40),
            'v3 registry ref': lambda r, f, g: r['registry'].update(ref='refs/heads/delsk/registry-v3'),
            'other contract': lambda r, f, g: r.update(g1_contract='delsk.oracle-contract.v3'),
            'extra field': lambda r, f, g: r.update(decision={}),
            'rulesets evidence bytes': lambda r, f, g: f.update({r['rulesets']['path']: b'{}'}),
            'rulesets evidence outside the v4 evidence directory': lambda r, f, g: r['rulesets'].update(
                path='.work/oracle/activation/rulesets.json'),
            'registry ruleset missing': lambda r, f, g: self.rulesets_edit(f, r, drop=reg.REGISTRY_REF),
            'retired v3 registry unprotected': lambda r, f, g: self.rulesets_edit(f, r,
                                                                                  drop='refs/heads/delsk/registry-v3'),
            'v3 infra digest': lambda r, f, g: r['v3_infra'].update(sha256='0' * 64),
            'v3 infra bytes': lambda r, f, g: f.update({act.V3_INFRA['path']: b'{}'}),
            'pilot workflow regressed': lambda r, f, g: f.update({act.PILOT_WORKFLOW: PILOT.replace(
                act.BIND_STEP, 'bind').encode()}),
            'genesis PR not merged': lambda r, f, g: doc(f'{api}/pulls/{GENESIS_PR}').update(merged=False),
            'genesis PR other merge commit': lambda r, f, g: doc(f'{api}/pulls/{GENESIS_PR}').update(
                merge_commit_sha='e' * 40),
            'genesis merge tree without the root': lambda r, f, g: self.at.update(
                {(GENESIS_MERGE, act.TOOL_FILE): b'nothing'}),
            'genesis PR into another base': lambda r, f, g: doc(f'{api}/pulls/{GENESIS_PR}')['base'].update(ref='x'),
            'late unrelated PR cannot claim genesis review': lambda r, f, g: (
                self.at.update({(GENESIS_PARENT, act.TOOL_FILE): self.at[(GENESIS_MERGE, act.TOOL_FILE)]}),
                g.docs.update({f'{api}/pulls/{GENESIS_PR}/files?per_page=100&page=1':
                    [{'filename': 'README.md', 'status': 'modified', 'sha': '9' * 40, 'patch': '+unrelated'}]})),
            'genesis PR file blob differs from merged binding': lambda r, f, g: g.docs.update({
                f'{api}/pulls/{GENESIS_PR}/files?per_page=100&page=1':
                    [{'filename': act.TOOL_FILE, 'status': 'modified', 'sha': '9' * 40,
                      'patch': f"+reviewed genesis root {act.ROOT_COMMIT['production']}"}]}),
            'genesis merge not on main': lambda r, f, g: self.main.discard(GENESIS_MERGE),
            'genesis merge without a parent': lambda r, f, g: self.parents.pop(GENESIS_MERGE),
            'files API unavailable': lambda r, f, g: g.docs.pop(f'{api}/pulls/{GENESIS_PR}/files?per_page=100&page=1'),
            'provider down': None,
        }
        for name, fn in cases.items():
            with self.subTest(name):
                self.setUp()
                record, files = copy.deepcopy(self.record), self.files
                if fn is None:  # provider down
                    gh = unittest.mock.Mock(side_effect=rg.TransportError('down'))
                else:
                    gh = self.gh
                    fn(record, files, gh)
                self.assertTrue(act.validate_activation(record, self.view(files), gh), name)

    def rulesets_edit(self, files, record, drop):
        doc = rulesets_doc()
        for r in doc['rulesets']:
            include = r['conditions']['ref_name']['include']
            if drop in include:
                include.remove(drop)
        doc['effective'].pop(drop, None)
        files[record['rulesets']['path']] = ev.canonical(doc)
        record['rulesets']['sha256'] = ev.sha256(files[record['rulesets']['path']])


class NotActivatedHere(unittest.TestCase):
    """Repository state: the enable record named by oracle_g1_v2.ACTIVATION_RECORD through the digest of its exact
    bytes, once enabled. The genesis review is a live provider fact; production re-verifies it on every evaluation
    (activation_in_tree), this offline test checks the bytes against the tree."""

    def test_activation_record_is_bound_by_digest(self):
        self.assertFalse(list((ROOT / '.work').rglob('genesis.json')))
        self.assertFalse(list((ROOT / '.work').rglob('entries.jsonl')))
        path = ROOT / act.ACTIVATION_FILE
        if g1.ACTIVATION_RECORD is None:
            self.assertFalse(path.exists())
            return
        data = path.read_bytes()
        self.assertEqual(ev.sha256(data), g1.ACTIVATION_RECORD)
        self.assertEqual(act.validate_record(ev.parse_doc(data), act.local_view()), [])

    def test_inherited_v3_infra_record_is_unchanged(self):
        # contract-v4 2: the v3 smoke and write-surface evidence is inherited by the exact bytes of the v3 infra record
        self.assertEqual(ev.sha256((ROOT / act.V3_INFRA['path']).read_bytes()), act.V3_INFRA['sha256'])


if __name__ == '__main__':
    unittest.main()
