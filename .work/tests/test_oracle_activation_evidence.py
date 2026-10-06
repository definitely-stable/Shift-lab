"""DELSK-003A activation evidence checks (oracle_activation_evidence.py), offline.

The genesis-review provenance as `recheck` runs it (verify_genesis_review over a TreeView pinned like production)
against the real Git history of the repository with a fake provider, the server-side registry history rules on
synthetic activity documents, and the digest binding of the enable record. No network.
"""
import copy
from pathlib import Path
import sys
import unittest
import unittest.mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import oracle_activation_evidence as x
import oracle_activation_v2 as act
import oracle_eval as ev
import oracle_registry_git as rg
import oracle_registry_v2 as reg

ROOT = ev.ROOT
REPO = reg.REPOSITORY
# The v3 production-root binding was introduced by PR #32 (merge 13c7d74); the mechanism is checked on that real history
# with the v3 root as the reviewed root, since the v4 binding is introduced by the PR that carries this test.
GENESIS_PR, GENESIS_MERGE = 32, '13c7d74ede7e2fd41bade001ec0e88926882459c'
GENESIS_PARENT = 'ba68ec73e1e2943005d372459742f063ea768e94'   # merge of PR #31: v2 root, not the v3 binding
V3_ROOT = {'production': '1a93f4ce71d9e4fbf5f21eaa9e66c660672ee258',
           'smoke': '62f79c1ceeb4f61615039104532e8dee251efaa3'}


def have(*commits):
    return all(rg.git(ROOT, 'cat-file', '-e', f'{c}^{{commit}}', check=False).returncode == 0 for c in commits)


class Provider:
    def __init__(self, docs):
        self.docs = docs

    def __call__(self, path):
        return copy.deepcopy(self.docs.get(path))


@unittest.skipUnless(have(GENESIS_MERGE, GENESIS_PARENT), 'needs the full history of main (fetch-depth: 0)')
@unittest.mock.patch.object(act, 'ROOT_COMMIT', V3_ROOT)
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

    def check(self, review, docs=None):
        return x.genesis_review({'genesis_review': review}, Provider(self.docs if docs is None else docs), ROOT,
                                GENESIS_MERGE)

    def test_recorded_pr_introduced_the_production_root(self):
        self.assertEqual(self.check({'pull_request': GENESIS_PR, 'merge_commit_sha': GENESIS_MERGE}), [])

    def test_wrong_pr(self):
        # PR #31 is merged into main too, but it introduced the v2 root, not the reviewed production binding
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


def item(ref, n, kind, before, after, when):
    return {'id': n, 'ref': ref, 'activity_type': kind, 'before': before, 'after': after, 'timestamp': when,
            'actor': {'login': 'a', 'type': 'User'}}


class RegistryActivity(unittest.TestCase):
    """Server-side history rules on synthetic documents shaped like the repository activity API."""

    def setUp(self):
        prod, root = reg.REGISTRY_REF, act.ROOT_COMMIT['production']
        self.last = x._when('2026-10-06T08:00:00Z')
        self.doc = {'refs': {
            prod: [item(prod, 1, 'branch_creation', x.ZERO, root, '2026-10-06T09:00:00Z'),
                   item(prod, 2, 'push', root, 'b' * 40, '2026-10-06T10:00:00Z')],
            **{ref: [item(ref, 10 + n, 'branch_creation', x.ZERO, x.RETIRED_ROOTS[ref], '2026-10-05T09:00:00Z')]
               + ([] if x.RETIRED_ROOTS[ref] == head else
                  [item(ref, 20 + n, 'push', x.RETIRED_ROOTS[ref], head, '2026-10-05T10:00:00Z')])
               for n, (ref, head) in enumerate(x.RETIRED_HEADS.items())}}}
        self.heads = {prod: 'b' * 40, **x.RETIRED_HEADS}

    def problems(self, edit=None, heads=None):
        doc = copy.deepcopy(self.doc)
        if edit:
            edit(doc['refs'])
        return x.activity_problems(doc, self.last, heads or self.heads)

    def test_fast_forward_history(self):
        self.assertEqual(self.problems(), [])

    def test_violations(self):
        prod, v3 = reg.REGISTRY_REF, 'refs/heads/delsk/registry-v3'
        cases = {
            'force push': lambda r: r[prod][1].update(activity_type='force_push'),
            'deletion': lambda r: r[prod].append({**r[prod][-1], 'id': 3, 'activity_type': 'branch_deletion',
                                                  'before': r[prod][-1]['after'], 'after': x.ZERO}),
            'gap in the chain': lambda r: r[prod][1].update(before='f' * 40),
            'created before the last ruleset change': lambda r: r[prod][0].update(timestamp='2026-10-06T07:00:00Z'),
            'created at another root': lambda r: r[prod][0].update(after='e' * 40),
            'no server history': lambda r: r.pop(prod),
            'retired v3 registry pushed': lambda r: r[v3].append(
                {**r[v3][-1], 'id': 99, 'activity_type': 'push', 'before': x.RETIRED_HEADS[v3], 'after': 'a' * 40}),
        }
        for name, edit in cases.items():
            with self.subTest(name):
                self.assertTrue(self.problems(edit))

    def test_retired_head_moved(self):
        self.assertTrue(self.problems(heads={**self.heads, 'refs/heads/delsk/registry-v3': 'a' * 40}))


class EnableRecordBinding(unittest.TestCase):
    """The digest binding between ACTIVATION_RECORD and the enable record bytes is checked before any live read."""

    def offline(self, path):
        raise AssertionError(f'live read {path}')

    def test_constant_must_name_the_exact_bytes(self):
        with unittest.mock.patch.object(x.g1, 'ACTIVATION_RECORD', '0' * 64):
            self.assertEqual(x.enable_record_problems(get=self.offline),
                             ['ACTIVATION_RECORD does not name the bytes of the enable record'])

    def test_record_without_the_constant_is_reported(self):
        path = ROOT / act.ACTIVATION_FILE
        with unittest.mock.patch.object(x.g1, 'ACTIVATION_RECORD', None):
            self.assertEqual(x.enable_record_problems(get=self.offline),
                             ['enable record present but ACTIVATION_RECORD is None'] if path.exists() else [])


if __name__ == '__main__':
    unittest.main()
