"""DELSK-003A C1-B: activation tooling of contract v2 section 16 (oracle_activation_v2.py), offline.

1. static witness of contract 4.1 / 12.2 on the reviewed workflows, and the mutations it must reject;
2. ruleset evidence (item 7), smoke scenarios (items 8-9) and write-surface evidence (item 10) verifiers;
3. the write-surface probe against a local remote that emulates server-side rule rejection, and its preflight;
4. a complete synthetic activation record verified end to end in a temporary tree (never committed), and the facts
   that the repository itself carries no activation record, no genesis and no activation evidence.
"""
import copy
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
                         ruleset(2, [reg.REGISTRY_REF, reg.SMOKE_REGISTRY_REF], ['deletion', 'non_fast_forward'])],
            'effective': {'refs/heads/main': [{'type': t} for t in ('deletion', 'non_fast_forward', 'pull_request')],
                          reg.REGISTRY_REF: [{'type': 'deletion'}, {'type': 'non_fast_forward'}],
                          reg.SMOKE_REGISTRY_REF: [{'type': 'deletion'}, {'type': 'non_fast_forward'}]}}


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


AUTHOR, REVIEWER = 'author-login', 'reviewer-login'
GENESIS_PR, INFRA_PR = 31, 40
GENESIS_MERGE, INFRA_MERGE, INFRA_HEAD = 'a' * 40, 'b' * 40, 'c' * 40
GENESIS_PARENT, INFRA_PARENT = '1' * 40, '2' * 40


class Record(unittest.TestCase):
    """Complete synthetic activation (infra record, enable record, live items 6/11/12) in a temporary tree: proves the
    records are checkable end to end, not that any item holds on GitHub. Nothing of this is committed."""

    def setUp(self):
        self.files = {p: (ROOT / p).read_bytes() for p in (act.PILOT_WORKFLOW, act.SMOKE_WORKFLOW,
                                                            act.WRITE_SURFACE_WORKFLOW, act.KAT_WORKFLOW)}
        smoke, scenarios = smoke_docs()
        write = {'schema': act.WRITE_SURFACE_SCHEMA, 'repository': REPO,
                 'workflow_ref': f'{REPO}/{act.WRITE_SURFACE_WORKFLOW}@refs/heads/main', 'run_id': 7, 'run_attempt': 1,
                 'credential': 'GITHUB_TOKEN contents: write', 'collected_at': '2026-10-05T12:00:00Z',
                 'preflight': 'PASSED',
                 'attempts': [{'operation': o, 'ref': 'r', 'exit_code': 1, 'server_rejected': True,
                               'ref_before': 'a' * 40, 'ref_after': 'a' * 40} for o in act.OPERATIONS]}
        evidence = {}
        for name, doc in (('rulesets', rulesets_doc()), ('smoke', smoke), ('scenarios', scenarios),
                          ('write_surface', write)):
            path = f'{act.EVIDENCE_DIR}{name}.json'
            self.files[path] = ev.canonical(doc)
            evidence[name] = {'path': path, 'sha256': ev.sha256(self.files[path])}
        self.infra = {'schema': act.INFRA_SCHEMA, 'g1_contract': reg.G1_CONTRACT,
                      'g1_freeze_sha256': reg.G1_FREEZE_SHA256,
                      'steps': {'register': act.REGISTER_STEP, 'bind': act.BIND_STEP, 'boundary': act.BOUNDARY_STEP,
                                'kat': act.KAT_STEP},
                      'registry': {'ref': reg.REGISTRY_REF, 'genesis_sha256': act.GENESIS_SHA256['production'],
                                   'root_commit': act.ROOT_COMMIT['production']},
                      'genesis_review': {'pull_request': GENESIS_PR, 'merge_commit_sha': GENESIS_MERGE},
                      'evidence': evidence}
        self.files[act.INFRA_FILE] = ev.canonical(self.infra)
        infra_sha = ev.sha256(self.files[act.INFRA_FILE])
        body = f'Independent review done.\n{act.DECISION_PHRASE.format(infra_sha)}\n'
        self.record = {'schema': act.SCHEMA, 'g1_contract': reg.G1_CONTRACT, 'g1_freeze_sha256': reg.G1_FREEZE_SHA256,
                       'infra': {'path': act.INFRA_FILE, 'sha256': infra_sha},
                       'infra_review': {'pull_request': INFRA_PR, 'merge_commit_sha': INFRA_MERGE, 'review_id': 501},
                       'decision': {'issue': act.DECISION_ISSUE, 'comment_id': 9001,
                                    'body_sha256': ev.sha256(body.encode())}}
        tool_bytes = (ROOT / act.TOOL_FILE).read_bytes()
        self.at = {(GENESIS_MERGE, act.TOOL_FILE): tool_bytes,
                   (INFRA_MERGE, act.INFRA_FILE): self.files[act.INFRA_FILE]}
        self.parents = {GENESIS_MERGE: GENESIS_PARENT, INFRA_MERGE: INFRA_PARENT}
        self.main = {GENESIS_PARENT, GENESIS_MERGE, INFRA_PARENT, INFRA_MERGE}
        self.gh = FakeGitHub()
        api = f'/repos/{REPO}'
        for number, merge, head, merged_at in ((GENESIS_PR, GENESIS_MERGE, 'd' * 40, '2026-10-05T10:00:00Z'),
                                               (INFRA_PR, INFRA_MERGE, INFRA_HEAD, '2026-10-06T10:00:00Z')):
            self.gh.docs[f'{api}/pulls/{number}'] = {
                'number': number, 'merged': True, 'merge_commit_sha': merge, 'merged_at': merged_at,
                'base': {'ref': 'main', 'repo': {'full_name': REPO}}, 'head': {'sha': head},
                'user': {'login': AUTHOR, 'type': 'User'}}
        self.gh.docs[f'{api}/pulls/{GENESIS_PR}/files?per_page=100&page=1'] = [
            {'filename': act.TOOL_FILE, 'status': 'added', 'sha': act._git_blob_sha(tool_bytes),
             'patch': f"+reviewed genesis root {act.ROOT_COMMIT['production']}"}]
        self.gh.docs[f'{api}/pulls/{INFRA_PR}/files?per_page=100&page=1'] = [
            {'filename': act.INFRA_FILE, 'status': 'added', 'sha': act._git_blob_sha(self.files[act.INFRA_FILE]),
             'patch': '+infra record'}]
        self.gh.docs[f'{api}/pulls/{INFRA_PR}/reviews?per_page=100'] = [
            {'id': 500, 'state': 'COMMENTED', 'commit_id': INFRA_HEAD, 'user': {'login': AUTHOR, 'type': 'User'}},
            {'id': 501, 'state': 'APPROVED', 'commit_id': INFRA_HEAD, 'user': {'login': REVIEWER, 'type': 'User'}}]
        self.gh.docs[f'{api}/issues/comments/9001'] = {
            'id': 9001, 'issue_url': f'{reg.PROVIDER_API}{api}/issues/{act.DECISION_ISSUE}', 'body': body,
            'author_association': 'OWNER', 'user': {'login': AUTHOR, 'type': 'User'},
            'created_at': '2026-10-06T12:00:00Z'}

    def view(self, files=None, at=None, main=None, parents=None):
        files, at, main, parents = files or self.files, at or self.at, main or self.main, parents or self.parents
        return act.TreeView(files.get, lambda c, p: at.get((c, p)), lambda c: c in main, parents.get)

    def test_complete_records_verify_and_bind_by_digest(self):
        self.assertEqual(act.validate_infra(self.infra, self.view()), [])
        self.assertEqual(act.validate_activation(self.record, self.view(), self.gh), [])
        self.files[act.ACTIVATION_FILE] = ev.canonical(self.record)
        digest = ev.sha256(self.files[act.ACTIVATION_FILE])
        self.assertEqual(act.activation_in_tree(self.view(), self.gh, digest), (self.record, self.infra))
        self.assertIsNone(act.activation_in_tree(self.view(), self.gh, '0' * 64))
        self.assertIsNone(act.activation_in_tree(self.view(), self.gh, None))

    def test_any_gap_keeps_v2_inactive(self):
        api = f'/repos/{REPO}'
        comment, reviews = f'{api}/issues/comments/9001', f'{api}/pulls/{INFRA_PR}/reviews?per_page=100'
        def doc(path):
            return self.gh.docs[path]
        cases = {  # (record edit, tree edit, provider edit)
            'step names': lambda r, f, g: self.infra_edit(f, r, steps={**self.infra['steps'], 'boundary': 'x'}),
            'genesis root': lambda r, f, g: self.infra_edit(f, r, registry={**self.infra['registry'],
                                                                            'root_commit': '0' * 40}),
            'evidence bytes': lambda r, f, g: f.update({self.infra['evidence']['rulesets']['path']: b'{}'}),
            'pilot workflow regressed': lambda r, f, g: f.update({act.PILOT_WORKFLOW: PILOT.replace(
                act.BIND_STEP, 'bind').encode()}),
            'infra bytes swapped': lambda r, f, g: f.update({act.INFRA_FILE: f[act.INFRA_FILE] + b' '}),
            # item 6
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
            # item 11
            'self approval only': lambda r, f, g: doc(reviews)[1]['user'].update(login=AUTHOR),
            'dismissed approval': lambda r, f, g: doc(reviews)[1].update(state='DISMISSED'),
            'approval of an older head': lambda r, f, g: doc(reviews)[1].update(commit_id='f' * 40),
            'review id of the comment-only review': lambda r, f, g: r['infra_review'].update(review_id=500),
            'infra PR merged other bytes': lambda r, f, g: self.at.update({(INFRA_MERGE, act.INFRA_FILE): b'{}'}),
            'late unrelated approved PR cannot claim infra review': lambda r, f, g: (
                self.at.update({(INFRA_PARENT, act.INFRA_FILE): self.files[act.INFRA_FILE]}),
                g.docs.update({f'{api}/pulls/{INFRA_PR}/files?per_page=100&page=1':
                    [{'filename': 'README.md', 'status': 'modified', 'sha': '8' * 40, 'patch': '+unrelated'}]})),
            'infra PR file blob differs from merged bytes': lambda r, f, g: g.docs.update({
                f'{api}/pulls/{INFRA_PR}/files?per_page=100&page=1':
                    [{'filename': act.INFRA_FILE, 'status': 'modified', 'sha': '8' * 40, 'patch': '+wrong'}]}),
            'infra merge not on main': lambda r, f, g: self.main.discard(INFRA_MERGE),
            'bot approval': lambda r, f, g: doc(reviews)[1]['user'].update(type='Bot'),
            # item 12
            'decision edited': lambda r, f, g: doc(comment).update(body=doc(comment)['body'] + 'edit'),
            'decision for another infra record': lambda r, f, g: self.redecide(r, act.DECISION_PHRASE.format('0' * 64)),
            'decision by a non-maintainer': lambda r, f, g: doc(comment).update(author_association='CONTRIBUTOR'),
            'decision before the infra merge': lambda r, f, g: doc(comment).update(created_at='2026-10-06T09:00:00Z'),
            'decision on another issue': lambda r, f, g: doc(comment).update(
                issue_url=f'{reg.PROVIDER_API}{api}/issues/1'),
            'decision on the wrong issue in the record': lambda r, f, g: r['decision'].update(issue=1),
            'decision comment deleted': lambda r, f, g: g.docs.pop(comment),
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

    def infra_edit(self, files, record, **changes):
        infra = {**self.infra, **changes}
        files[act.INFRA_FILE] = ev.canonical(infra)
        record['infra']['sha256'] = ev.sha256(files[act.INFRA_FILE])

    def redecide(self, record, phrase):
        body = f'{phrase}\n'
        self.gh.docs[f'/repos/{REPO}/issues/comments/9001']['body'] = body
        record['decision']['body_sha256'] = ev.sha256(body.encode())


class NotActivatedHere(unittest.TestCase):
    def test_repository_carries_no_activation(self):
        self.assertIsNone(g1.ACTIVATION_RECORD)
        self.assertFalse((ROOT / act.ACTIVATION_FILE).exists())
        self.assertFalse((ROOT / act.EVIDENCE_DIR).exists())
        self.assertFalse(list((ROOT / '.work').rglob('genesis.json')))
        self.assertFalse(list((ROOT / '.work').rglob('entries.jsonl')))


if __name__ == '__main__':
    unittest.main()
