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
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import oracle_activation_v2 as act
import oracle_eval as ev
import oracle_g1_v2 as g1
import oracle_registry_v2 as reg
from test_oracle_registry_git import World

ROOT = ev.ROOT
REPO = reg.REPOSITORY


def text(path):
    return (ROOT / path).read_text(encoding='utf-8')


PILOT, SMOKE, WRITE, KAT = (text(p) for p in (act.PILOT_WORKFLOW, act.SMOKE_WORKFLOW, act.WRITE_SURFACE_WORKFLOW,
                                              act.KAT_WORKFLOW))


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
            'token leaks to checkout': swap(PILOT, '          fetch-depth: 0\n      - name: Register',
                                            '          fetch-depth: 0\n          token: ${{ github.token }}\n'
                                            '      - name: Register'),
            'register depends on measure': swap(PILOT, '  register:\n    runs-on',
                                                '  register:\n    needs: measure\n    runs-on'),
            'push trigger': swap(PILOT, 'on:\n  workflow_dispatch:', 'on:\n  push:\n  workflow_dispatch:'),
            'unpinned action': PILOT.replace('actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1',
                                             'actions/checkout@v4', 1),
            'renamed boundary': PILOT.replace(act.BOUNDARY_STEP, 'Bounded pilot'),
            'bind after boundary': swap(swap(PILOT, act.BIND_STEP, 'TMP'), act.BOUNDARY_STEP, act.BIND_STEP).replace(
                'TMP', act.BOUNDARY_STEP),
            'shallow register checkout': swap(PILOT, '          fetch-depth: 0\n      - name: Register',
                                              '      - name: Register'),
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
    """A smoke evaluation and its scenario manifest as the real-GitHub runs would produce them (synthetic)."""
    runs = [('stop-before-boundary', 31, 1, 'PRE', True), ('cross-boundary', 32, 1, 'MISSING', True),
            ('rerun-all', 31, 2, 'PRE', True), ('rerun-failed', 31, 3, None, True),
            ('cancel-after-register', 33, 1, 'PRE', True), ('deleted-run', 34, 1, 'MISSING', False),
            ('cancel-before-register', 35, 1, None, True)]
    attempts = [{'run_id': r, 'run_attempt': a, 'class': c, 'violations': []} for _, r, a, c, _ in runs if c]
    provider = [{'run_id': r, 'run_attempt': a, 'run': {} if present else None} for _, r, a, c, present in runs if c]
    evaluation = {'schema': act.SMOKE_EVALUATION_SCHEMA, 'blocker': None, 'attempts': attempts,
                  'unbound_attempts': [], 'provider': provider, 'records': []}
    scenarios = {'schema': act.SCENARIOS_SCHEMA, 'workflow': reg.SMOKE_WORKFLOW_PATH,
                 'registry_ref': reg.SMOKE_REGISTRY_REF,
                 'runs': [{'scenario': s, 'run_id': r, 'run_attempt': a,
                           'html_url': f'https://github.com/{REPO}/actions/runs/{r}'} for s, r, a, _, _ in runs]}
    return evaluation, scenarios


class Smoke(unittest.TestCase):
    def test_required_scenarios(self):
        self.assertEqual(act.verify_smoke(*smoke_docs()), [])

    def test_incomplete_or_misclassified_smoke_is_rejected(self):
        cases = {
            'scenario not executed': lambda e, s: s['runs'].pop(),
            'pre misclassified': lambda e, s: e['attempts'][0].update({'class': 'MISSING'}),
            'unexplained entry': lambda e, s: e['attempts'].append({'run_id': 99, 'run_attempt': 1, 'class': 'PRE',
                                                                    'violations': []}),
            'unbound attempt': lambda e, s: e['unbound_attempts'].append({'run_id': 31, 'run_attempt': 3}),
            'rerun-failed registered': lambda e, s: e['attempts'].append({'run_id': 31, 'run_attempt': 3,
                                                                          'class': 'PRE', 'violations': []}),
            'deleted run still present': lambda e, s: e['provider'][-1].update({'run': {}}),
            'registry blocker': lambda e, s: e.update(blocker='REGISTRY_INVALID'),
            'violations': lambda e, s: e['attempts'][1].update(violations=['BINDING_MISMATCH']),
            'foreign workflow': lambda e, s: s.update(workflow=reg.WORKFLOW_PATH),
        }
        for name, fn in cases.items():
            with self.subTest(name):
                e, s = smoke_docs()
                fn(e, s)
                self.assertTrue(act.verify_smoke(e, s), name)


class Record(unittest.TestCase):
    """Complete synthetic activation in a temporary tree: proves the record is checkable end to end, not that any
    item holds on GitHub. Nothing of this is committed."""

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
        self.record = {'schema': act.SCHEMA, 'g1_contract': reg.G1_CONTRACT, 'g1_freeze_sha256': reg.G1_FREEZE_SHA256,
                       'steps': {'register': act.REGISTER_STEP, 'bind': act.BIND_STEP, 'boundary': act.BOUNDARY_STEP,
                                 'kat': act.KAT_STEP},
                       'registry': {'ref': reg.REGISTRY_REF, 'genesis_sha256': act.GENESIS_SHA256['production'],
                                    'root_commit': act.ROOT_COMMIT['production']},
                       'evidence': {'genesis_pull_request': 40, **evidence}, 'review': {'pull_request': 41},
                       'natural_measurement': {'decision_url': f'https://github.com/{REPO}/issues/27#issuecomment-1'}}

    def read(self, path):
        return self.files.get(path)

    def test_complete_record_verifies_and_binds_by_digest(self):
        self.assertEqual(act.validate_activation(self.record, self.read), [])
        self.files[act.ACTIVATION_FILE] = ev.canonical(self.record)
        digest = ev.sha256(self.files[act.ACTIVATION_FILE])
        self.assertEqual(act.activation_in_tree(self.read, digest), self.record)
        self.assertIsNone(act.activation_in_tree(self.read, '0' * 64))
        self.assertIsNone(act.activation_in_tree(self.read, None))

    def test_any_gap_keeps_v2_inactive(self):
        def edit(fn):
            r, files = copy.deepcopy(self.record), dict(self.files)
            fn(r, files)
            return r, files
        cases = {
            'step names': lambda r, f: r['steps'].update(boundary='Bounded pilot'),
            'genesis': lambda r, f: r['registry'].update(root_commit='0' * 40),
            'evidence bytes': lambda r, f: f.update({r['evidence']['rulesets']['path']: b'{}'}),
            'evidence outside the evidence directory': lambda r, f: r['evidence']['smoke'].update(path='README.md'),
            'no review': lambda r, f: r.update(review={}),
            'no natural decision': lambda r, f: r.update(natural_measurement={'decision_url': 'https://x.invalid'}),
            'pilot workflow regressed': lambda r, f: f.update({act.PILOT_WORKFLOW: PILOT.replace(
                act.BIND_STEP, 'bind').encode()}),
            'kat workflow missing': lambda r, f: f.pop(act.KAT_WORKFLOW),
            'other contract': lambda r, f: r.update(g1_freeze_sha256='0' * 64),
        }
        for name, fn in cases.items():
            with self.subTest(name):
                r, files = edit(fn)
                self.assertTrue(act.validate_activation(r, files.get), name)


class NotActivatedHere(unittest.TestCase):
    def test_repository_carries_no_activation(self):
        self.assertIsNone(g1.ACTIVATION_RECORD)
        self.assertFalse((ROOT / act.ACTIVATION_FILE).exists())
        self.assertFalse((ROOT / act.EVIDENCE_DIR).exists())
        self.assertFalse(list((ROOT / '.work').rglob('genesis.json')))
        self.assertFalse(list((ROOT / '.work').rglob('entries.jsonl')))


if __name__ == '__main__':
    unittest.main()
