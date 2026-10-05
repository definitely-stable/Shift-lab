"""DELSK-003A C1-A: registry mechanics of delsk.oracle-contract.v3 (oracle_registry_v2.py), synthetic only.

Canonical parsing, closed schemas, hash chain, sequence, duplicates, head, level-1 witness (rollback), stale primitive,
physical branch form, science identity (SI01-SI05), transition records and external checkpoints (XC01-XC05).
Every registry here is built by the implementation's own append path or taken from frozen vector inputs.
"""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from oracle_v2_vectors import VECTORS, BY_ID, environment, git_snapshot
import oracle_eval as ev
import oracle_registry_v2 as reg

ENV = VECTORS['environment']
GIT = git_snapshot(ENV)
SOURCES = {s['sha']: s['measurement_identity'] for s in ENV['sources']}
A, C, NEW = 'a77f420c89c111651682e0b015fde143d5119b1f', '085bbd6c728fa0e1ce82af37eb73027436bc34c4', \
    '921f3b8c44251a24c9bd63cae943b444c0856cf2'
REF = 'definitely-stable/Shift-lab/.github/workflows/oracle-pilot.yml@refs/heads/main'
GENESIS = BY_ID['R01']['registry']['genesis']


def registry(*runs):
    """Entries appended by the implementation: runs = [(run_id, run_attempt, source[, transition])]."""
    entries = []
    for run in runs:
        run_id, attempt, source, *t = run
        entries.append(reg.make_entry(GENESIS, entries, run_id=run_id, run_attempt=attempt,
                                      measured_source_sha=source, workflow_ref=REF,
                                      measurement_identity=SOURCES[source], transition=t[0] if t else None))
    return entries


def redigest(entries, start=0):
    """Recompute entry digests and chain links from `start` on, as an adversary rehashing a rewritten history."""
    previous = entries[start - 1]['entry_sha256'] if start else ev.hc(GENESIS)
    for e in entries[start:]:
        e['previous_entry_sha256'] = previous
        e['entry_sha256'] = ev.hc(reg.without(e, 'entry_sha256'))
        previous = e['entry_sha256']
    return entries


def files(genesis, entries):
    return ev.canonical(genesis), b''.join(ev.compact(e).encode() + b'\n' for e in entries)


class Canonical(unittest.TestCase):
    def test_round_trip_of_frozen_registry_bytes(self):
        case = BY_ID['R01']['registry']
        genesis, entries = reg.parse_registry(*files(case['genesis'], case['entries']))
        self.assertEqual((genesis, entries), (case['genesis'], case['entries']))
        self.assertEqual(reg.validate(genesis, entries, GIT),
                         {'sequence': 2, 'entry_sha256': case['entries'][-1]['entry_sha256']})
        self.assertEqual(reg.parse_registry(ev.canonical(GENESIS), b''), (GENESIS, []))

    def test_malformed_bytes_fail_closed(self):
        g, e = files(GENESIS, registry((1, 1, A)))
        for label, gb, eb in (('BOM', b'\xef\xbb\xbf' + g, e), ('genesis compact', ev.compact(GENESIS).encode(), e),
                              ('genesis no LF', g[:-1], e), ('entries no LF', g, e[:-1]),
                              ('entries pretty', g, ev.canonical(registry((1, 1, A))[0])),
                              ('float', g, e.replace(b'"run_attempt":1', b'"run_attempt":1.0')),
                              ('exponent', g, e.replace(b'"run_attempt":1', b'"run_attempt":1e0')),
                              ('NaN', g, e.replace(b'"run_attempt":1', b'"run_attempt":NaN')),
                              ('duplicate key', g, e.replace(b'{"entry_sha256"', b'{"run_id":1,"entry_sha256"')),
                              ('blank line', g, e + b'\n'), ('not utf-8', g, e.replace(b'pilot', b'pil\xffot')),
                              ('array line', g, b'[1]\n')):
            with self.subTest(label), self.assertRaises(reg.RegistryInvalid):
                reg.validate(*reg.parse_registry(gb, eb), GIT)


class Validate(unittest.TestCase):
    def assertInvalid(self, entries, genesis=GENESIS, git=GIT, **kw):
        with self.assertRaises(reg.RegistryInvalid):
            reg.validate(genesis, entries, git, **kw)

    def test_appended_registry_is_valid(self):
        entries = registry((24000000001, 1, A), (24000000002, 1, A), (24000000003, 1, A))
        self.assertEqual(reg.validate(GENESIS, entries, GIT)['sequence'], 3)
        self.assertEqual(entries, BY_ID['R05']['registry']['entries'])  # byte-identical to the frozen R05 registry
        self.assertEqual(reg.head(GENESIS, []), {'sequence': 0, 'entry_sha256': ev.hc(GENESIS)})

    def test_frozen_r02_faults(self):
        for cid in ('R02.a', 'R02.b', 'R02.c', 'R02.d'):
            with self.subTest(cid):
                self.assertInvalid(BY_ID[cid]['registry']['entries'], BY_ID[cid]['registry']['genesis'])

    def test_genesis_fail_closed(self):
        for label, change in (('unknown field', {'note': 'x'}), ('other contract', {'g1_contract': 'x'}),
                              ('v1 freeze', {'measurement_freeze_sha256': '0' * 64}),
                              ('uppercase', {'g1_freeze_sha256': GENESIS['g1_freeze_sha256'].upper()}),
                              ('other ref', {'registry_ref': 'refs/heads/main'})):
            with self.subTest(label):
                self.assertInvalid([], {**GENESIS, **change})
        self.assertInvalid([], {k: v for k, v in GENESIS.items() if k != 'repository'})
        self.assertInvalid([], [GENESIS])
        self.assertInvalid([], GENESIS, g1_freeze_sha256='f' * 64)  # production binds genesis to freeze-v3
        reg.validate(GENESIS, [], GIT, g1_freeze_sha256=GENESIS['g1_freeze_sha256'])

    def test_entry_fail_closed(self):
        t = reg.make_transition('pilot', BY_ID['R01']['registry']['entries'][0]['science_identity_sha256'],
                                registry((9, 1, NEW))[0]['science_identity_sha256'], 'BUG_FIX', 101,
                                'c64080c36580d5b937d3f86f4e3b5f53000368a1')
        cases = {
            'unknown field': lambda e: e.update(note='x'),
            'missing field': lambda e: e.pop('transition'),
            'bool as int': lambda e: e.update(run_attempt=True),
            'zero run id': lambda e: e.update(run_id=0),
            'int64 overflow': lambda e: e.update(run_id=1 << 63),
            'uppercase hash': lambda e: e.update(measurement_identity_sha256=e['measurement_identity_sha256'].upper()),
            'hash + LF': lambda e: e.update(science_identity_sha256=e['science_identity_sha256'] + '\n'),
            'short SHA': lambda e: e.update(measured_source_sha=A[:39], workflow_sha=A[:39]),
            'other workflow path': lambda e: e.update(workflow_path='.github/workflows/foundation.yml'),
            'workflow ref of tag': lambda e: e.update(workflow_ref=REF.replace('heads', 'tags')),
            'workflow_sha != source': lambda e: e.update(workflow_sha=C),
            'source not on main': lambda e: e.update(measured_source_sha='ed787d5c809f13f6d8f0a348fa4dec56472500a1',
                                                     workflow_sha='ed787d5c809f13f6d8f0a348fa4dec56472500a1'),
            'source moved, identity kept': lambda e: e.update(measured_source_sha=C, workflow_sha=C),
            'measurement identity': lambda e: e.update(measurement_identity_sha256='0' * 64),
            'science identity': lambda e: e.update(science_identity_sha256='0' * 64),
            'phase reveal': lambda e: e.update(phase='reveal'),
            'other repository': lambda e: e.update(repository='fork/Shift-lab'),
            'non-NFC string': lambda e: e.update(workflow_ref=REF.replace('main', 'maín')),
            'bad transition digest': lambda e: e.update(transition={**t, 'reason': 'IMPLEMENTATION_CHANGE'}),
            'transition to itself': lambda e: e.update(transition=reg.make_transition(
                'pilot', e['science_identity_sha256'], e['science_identity_sha256'], 'BUG_FIX', 101, A)),
            'transition unknown field': lambda e: e.update(transition={**t, 'note': 'x'}),
        }
        reasons = {'workflow_sha != source': 'workflow_sha != measured_source_sha',
                   'source not on main': 'not on the pinned main', 'source moved, identity kept': 'git_source',
                   'measurement identity': 'git_source', 'science identity': 'contract 6', 'phase reveal': 'phase',
                   'bad transition digest': 'transition_sha256', 'transition to itself': 'must differ'}
        for label, change in cases.items():
            with self.subTest(label):
                entries = registry((1, 1, A), (2, 1, A))
                change(entries[1])
                try:  # re-digested like an adversary would, so only the targeted rule can fire
                    redigest(entries, 1)
                except ev.EvalError:
                    pass  # not representable in canonical JSON at all
                with self.assertRaises(reg.RegistryInvalid) as fault:
                    reg.validate(GENESIS, entries, GIT)
                self.assertIn(reasons.get(label, 'not canonical or not by schema'), str(fault.exception))

    def test_chain_sequence_and_digest(self):
        entries = registry((1, 1, A), (2, 1, A), (3, 1, A))
        broken = copy.deepcopy(entries)
        broken[1]['previous_entry_sha256'] = '0' * 64
        redigest(broken, 2)
        self.assertInvalid(broken)                                       # previous hash wrong
        digest = copy.deepcopy(entries)
        digest[1]['run_id'] = 7
        self.assertInvalid(digest)                                       # entry digest wrong
        for seq in (0, 2, 4):
            gap = copy.deepcopy(entries)
            gap[2]['sequence'] = seq
            self.assertInvalid(redigest(gap, 2))                         # gap / repeat / zero, rehashed
        self.assertInvalid(redigest(entries[1:]))                        # chain must start at 1
        self.assertInvalid(list(reversed(entries)))
        self.assertInvalid(redigest(registry((1, 1, A), (2, 1, A))[:1] + [registry((1, 1, A))[0]], 1))

    def test_duplicates_and_head(self):
        entries = registry((1, 1, A), (1, 2, A), (1, 1, A))
        self.assertEqual(reg.duplicate_keys(entries), {(1, 1)})
        self.assertEqual(reg.duplicate_keys(entries[:2]), set())
        self.assertEqual(reg.validate(GENESIS, entries, GIT)['sequence'], 3)  # chain valid; duplicate is item 2
        self.assertEqual(reg.duplicate_keys(BY_ID['R04']['registry']['entries']), {(24000000001, 1)})


class Witness(unittest.TestCase):
    def test_prefix_rollback_and_stale(self):
        entries = registry((1, 1, A), (2, 1, A), (3, 1, A))
        chain = reg.history(GENESIS, entries)
        for n in range(4):
            self.assertTrue(reg.on_history({'sequence': n, 'entry_sha256': chain[n]}, chain))
        self.assertFalse(reg.on_history({'sequence': 3, 'entry_sha256': chain[3]}, chain[:3]))     # truncated tail
        self.assertFalse(reg.on_history({'sequence': 2, 'entry_sha256': chain[3]}, chain))         # rewritten
        self.assertFalse(reg.on_history({'sequence': 4, 'entry_sha256': chain[3]}, chain))
        rehashed = redigest(copy.deepcopy(entries[:2]) + registry((1, 1, A), (2, 1, A), (9, 1, A))[2:], 2)
        self.assertFalse(reg.on_history({'sequence': 3, 'entry_sha256': chain[3]},
                                        reg.history(GENESIS, rehashed)))  # truncate + re-append + rehash
        head = reg.head(GENESIS, entries)
        self.assertFalse(reg.stale(head, dict(head)))
        self.assertTrue(reg.stale(head, reg.head(GENESIS, entries[:2])))
        self.assertTrue(reg.stale('a' * 40, 'b' * 40))


class Physical(unittest.TestCase):
    def commits(self, entries):
        g = ev.canonical(GENESIS)
        out, data = [(0, {reg.GENESIS_FILE: g, reg.ENTRIES_FILE: b''})], b''
        for e in entries:
            data += ev.compact(e).encode() + b'\n'
            out.append((1, {reg.GENESIS_FILE: g, reg.ENTRIES_FILE: data}))
        return out

    def test_branch_form(self):
        entries = registry((1, 1, A), (2, 1, A))
        good = self.commits(entries)
        self.assertEqual(reg.parse_registry(*reg.validate_physical(good)), (GENESIS, entries))
        bad = {
            'no root': [], 'root with parent': [(1, good[0][1])] + good[1:],
            'merge commit': good[:2] + [(2, good[2][1])],
            'extra file': good[:1] + [(1, {**good[1][1], 'README': b''})] + good[2:],
            'genesis edited': good[:2] + [(1, {**good[2][1], reg.GENESIS_FILE: ev.canonical({**GENESIS, 'x': 1})})],
            'two lines at once': [good[0], good[2]],
            'root not empty': [(0, good[1][1])] + good[2:],
            'history rewritten': good[:2] + [(1, {**good[2][1], reg.ENTRIES_FILE: good[2][1][reg.ENTRIES_FILE]
                                                  .replace(b'"run_id":1,', b'"run_id":5,', 1)})],
            'partial line': good[:2] + [(1, {**good[2][1], reg.ENTRIES_FILE: good[2][1][reg.ENTRIES_FILE][:-1]})],
        }
        for label, commits in bad.items():
            with self.subTest(label), self.assertRaises(reg.RegistryInvalid):
                reg.validate_physical(commits)


class ScienceIdentity(unittest.TestCase):
    def test_si_vectors(self):
        for v in VECTORS['science_identity_vectors']:
            with self.subTest(v['id']):
                si = reg.science_identity(v['measurement_identity'])
                self.assertEqual(si, v['science_identity'])
                self.assertEqual(ev.hc(si), v['science_identity_sha256'])
                self.assertEqual(ev.hc(v['measurement_identity']), v['measurement_identity_sha256'])
                self.assertTrue(reg.valid(si, 'science_identity'))

    def test_identity_hopping_keeps_series(self):
        a, c = registry((1, 1, A))[0], registry((3, 1, C))[0]
        self.assertNotEqual(a['measurement_identity_sha256'], c['measurement_identity_sha256'])
        self.assertEqual(a['science_identity_sha256'], c['science_identity_sha256'])
        self.assertNotEqual(a['science_identity_sha256'], registry((4, 1, NEW))[0]['science_identity_sha256'])


class ExternalCheckpoint(unittest.TestCase):
    def test_xc_vectors(self):
        for x in VECTORS['external_checkpoint_vectors']:
            with self.subTest(x['id']):
                ok = reg.checkpoint_admissible(x['record_head'], x['checkpoint'], x['checkpoint_history'],
                                               x['genesis_sha256'])
                self.assertEqual('ADMISSIBLE' if ok else 'INADMISSIBLE', x['expected'])

    def test_fake_checkpoints(self):
        x = VECTORS['external_checkpoint_vectors'][1]  # XC02: later checkpoint, admissible
        args = (x['record_head'], x['checkpoint'], x['checkpoint_history'], x['genesis_sha256'])
        self.assertTrue(reg.checkpoint_admissible(*args))
        cp = x['checkpoint']
        for label, changed in (
                ('head digest not the history end', (args[0], {**cp, 'head': {**cp['head'], 'entry_sha256': '0' * 64}},
                                                     *args[2:])),
                ('history longer than head', (args[0], cp, args[2] + ['0' * 64], args[3])),
                ('history shorter than head', (args[0], cp, args[2][:-1], args[3])),
                ('record digest wrong', ({**args[0], 'entry_sha256': '0' * 64}, *args[1:])),
                ('record beyond checkpoint', ({'sequence': 4, 'entry_sha256': '0' * 64}, *args[1:])),
                ('http locator', (args[0], {**cp, 'locator': 'http://checkpoint.invalid/x'}, *args[2:])),
                ('uppercase digest', (args[0], {**cp, 'checkpoint_sha256': cp['checkpoint_sha256'].upper()},
                                      *args[2:])),
                ('record without head', ({}, *args[1:]))):
            with self.subTest(label):
                self.assertFalse(reg.checkpoint_admissible(*changed))

    def test_genesis_record_head(self):
        x = VECTORS['external_checkpoint_vectors'][4]  # XC05: record head = genesis
        args = (x['record_head'], x['checkpoint'], x['checkpoint_history'], x['genesis_sha256'])
        self.assertTrue(reg.checkpoint_admissible(*args))
        self.assertFalse(reg.checkpoint_admissible(*args[:3], '0' * 64))
        self.assertFalse(reg.checkpoint_admissible({**args[0], 'entry_sha256': '0' * 64}, *args[1:]))

    def test_history_is_verified_from_full_entries(self):
        entries = registry((1, 1, A), (2, 1, A), (3, 1, A))
        reg.validate(GENESIS, entries, GIT)
        head = reg.head(GENESIS, entries)
        hist = reg.checkpoint_history(GENESIS, entries, head)
        self.assertTrue(reg.checkpoint_admissible({'sequence': 1, 'entry_sha256': entries[0]['entry_sha256']},
                                                  {'head': head, 'locator': 'https://x.invalid/c',
                                                   'checkpoint_sha256': '1' * 64}, hist, ev.hc(GENESIS)))
        with self.assertRaises(reg.RegistryInvalid):
            reg.checkpoint_history(GENESIS, entries[:2], head)


class Snapshot(unittest.TestCase):
    def test_git_snapshot_is_immutable_and_pinned(self):
        git = git_snapshot(environment(BY_ID['R01']))
        self.assertTrue(git.on_main(A) and git.ancestor_or_equal(C, A) and git.ancestor_or_equal(A, A))
        self.assertFalse(git.ancestor_or_equal(A, C) or git.on_main('ed787d5c809f13f6d8f0a348fa4dec56472500a1'))
        mi = git.identity(A)
        mi['phase'] = 'reveal'
        self.assertEqual(git.identity(A)['phase'], 'pilot')
        with self.assertRaises(Exception):
            git.main_head_sha = A
        with self.assertRaises(TypeError):
            git.ancestors[A] = frozenset()
        self.assertIsNone(git.identity('0' * 40))


if __name__ == '__main__':
    unittest.main()
