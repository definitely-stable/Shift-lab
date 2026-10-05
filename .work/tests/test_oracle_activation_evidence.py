"""DELSK-003A activation evidence checks (oracle_activation_evidence.py), offline.

Item 6 provenance as `recheck` runs it (verify_genesis_review over a TreeView pinned like production) against the
real Git history of the repository with a fake provider, and the server-side registry history rules over the
committed evidence and its mutations. No network.
"""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import oracle_activation_evidence as x
import oracle_activation_v2 as act
import oracle_eval as ev
import oracle_registry_git as rg
import oracle_registry_v2 as reg

ROOT = ev.ROOT
REPO = reg.REPOSITORY
GENESIS_PR, GENESIS_MERGE = 32, '13c7d74ede7e2fd41bade001ec0e88926882459c'
GENESIS_PARENT = 'ba68ec73e1e2943005d372459742f063ea768e94'   # merge of PR #31: v2 root, not the v3 binding


def have(*commits):
    return all(rg.git(ROOT, 'cat-file', '-e', f'{c}^{{commit}}', check=False).returncode == 0 for c in commits)


class Provider:
    def __init__(self, docs):
        self.docs = docs

    def __call__(self, path):
        return copy.deepcopy(self.docs.get(path))


@unittest.skipUnless(have(GENESIS_MERGE, GENESIS_PARENT), 'needs the full history of main (fetch-depth: 0)')
class GenesisReviewLive(unittest.TestCase):
    def setUp(self):
        blob = rg.git(ROOT, 'rev-parse', f'{GENESIS_MERGE}:{act.TOOL_FILE}').decode().strip()
        api = f'/repos/{REPO}/pulls'
        self.docs = {
            f'{api}/{GENESIS_PR}': {'number': GENESIS_PR, 'merged': True, 'merge_commit_sha': GENESIS_MERGE,
                                    'merged_at': '2026-10-05T15:25:07Z',
                                    'base': {'ref': 'main', 'repo': {'full_name': REPO}}},
            f'{api}/{GENESIS_PR}/files?per_page=100&page=1': [
                {'filename': act.TOOL_FILE, 'status': 'modified', 'sha': blob}],
            f'{api}/31': {'number': 31, 'merged': True, 'merge_commit_sha': GENESIS_PARENT,
                          'merged_at': '2026-10-05T10:48:00Z', 'base': {'ref': 'main', 'repo': {'full_name': REPO}}},
            f'{api}/31/files?per_page=100&page=1': [
                {'filename': act.TOOL_FILE, 'status': 'modified',
                 'sha': rg.git(ROOT, 'rev-parse', f'{GENESIS_PARENT}:{act.TOOL_FILE}').decode().strip()}]}

    def check(self, record, docs=None):
        infra = {'genesis_review': record}
        return x.genesis_review(infra, Provider(self.docs if docs is None else docs), ROOT, GENESIS_MERGE)

    def test_recorded_pr_introduced_the_production_root(self):
        self.assertEqual(self.check({'pull_request': GENESIS_PR, 'merge_commit_sha': GENESIS_MERGE}), [])

    def test_wrong_pr(self):
        # PR #31 is merged into main too, but it introduced the v2 root, not the v3 production binding
        self.assertTrue(self.check({'pull_request': 31, 'merge_commit_sha': GENESIS_PARENT}))

    def test_wrong_merge_commit(self):
        self.assertTrue(self.check({'pull_request': GENESIS_PR, 'merge_commit_sha': GENESIS_PARENT}))

    def test_pr_that_did_not_introduce_the_root_marker(self):
        docs = copy.deepcopy(self.docs)
        docs[f'/repos/{REPO}/pulls/{GENESIS_PR}/files?per_page=100&page=1'] = [
            {'filename': 'README.md', 'status': 'modified', 'sha': '9' * 40}]
        self.assertTrue(self.check({'pull_request': GENESIS_PR, 'merge_commit_sha': GENESIS_MERGE}, docs))

    def test_unmerged_or_unavailable(self):
        docs = copy.deepcopy(self.docs)
        docs[f'/repos/{REPO}/pulls/{GENESIS_PR}']['merged'] = False
        self.assertTrue(self.check({'pull_request': GENESIS_PR, 'merge_commit_sha': GENESIS_MERGE}, docs))
        self.assertTrue(self.check({'pull_request': GENESIS_PR, 'merge_commit_sha': GENESIS_MERGE}, {}))


class RegistryActivity(unittest.TestCase):
    def setUp(self):
        evidence = ROOT / act.EVIDENCE_DIR
        if not (evidence / 'registry-activity.json').exists():
            self.skipTest('no activation evidence in this tree')
        self.doc = ev.parse_doc((evidence / 'registry-activity.json').read_bytes())
        self.last = x.last_change(ev.parse_doc((evidence / 'rulesets.json').read_bytes()))
        refs = ev.parse_doc((evidence / 'registry-refs.json').read_bytes())['refs']
        self.heads = {ref: value['head'] for ref, value in refs.items()}

    def problems(self, edit=None):
        doc = copy.deepcopy(self.doc)
        if edit:
            edit(doc['refs'])
        return x.activity_problems(doc, self.last, self.heads)

    def test_committed_history(self):
        self.assertEqual(self.problems(), [])
        self.assertEqual(self.doc['problems'], [])
        for ref in (reg.REGISTRY_REF, reg.SMOKE_REGISTRY_REF):
            self.assertGreater(x._when(self.doc['refs'][ref][0]['timestamp']), self.last)

    def test_violations(self):
        smoke, prod = reg.SMOKE_REGISTRY_REF, reg.REGISTRY_REF
        cases = {
            'force push': lambda r: r[smoke][2].update(activity_type='force_push'),
            'deletion': lambda r: r[smoke].append({**r[smoke][-1], 'activity_type': 'branch_deletion',
                                                   'before': r[smoke][-1]['after'], 'after': x.ZERO}),
            'gap in the chain': lambda r: r[smoke][3].update(before='f' * 40),
            'created before the last ruleset change': lambda r: r[prod][0].update(timestamp='2026-10-05T15:00:00Z'),
            'created at another root': lambda r: r[prod][0].update(after='e' * 40),
            'production updated after genesis': lambda r: r[prod].append({**r[prod][0], 'activity_type': 'push',
                                                                          'before': r[prod][0]['after']}),
            'no server history': lambda r: r.pop(smoke),
            'v2 ref pushed after disclosure': lambda r: r['refs/heads/delsk/registry'].append(
                {**r['refs/heads/delsk/registry'][0], 'activity_type': 'push', 'before': x.V2_HEADS[
                    'refs/heads/delsk/registry'], 'after': 'a' * 40}),
        }
        for name, edit in cases.items():
            with self.subTest(name):
                self.assertTrue(self.problems(edit))


if __name__ == '__main__':
    unittest.main()
