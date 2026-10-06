"""DELSK-002 X0 screening (tools/x0_corpus.py, tools/x0_screen.py) on synthetic data only."""
import gzip
import hashlib
import io
import json
from pathlib import Path
import random
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import manifests as m
import x0_corpus as xc
import x0_screen as xs

PLAN = xc.PLAN_PATH


def tar_gz(top, files):
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode='w') as t:
        for name, data in files.items():
            info = tarfile.TarInfo(f'{top}/{name}')
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
    return gzip.compress(raw.getvalue(), mtime=0)


def release(fid, i, branch, day, fmt='tar.gz', member=None):
    return {'release_id': f'{fid}-{i}', 'version': f'{branch}.{i}', 'branch': branch, 'ordinal': i,
            'url': f'https://example.org/{fid}-{i}', 'format': fmt, 'member': member,
            'time': {'value': f'2024-0{i}-{day:02d}', 'evidence_url': 'https://example.org/news'}}


def mutate(data, rng, edits=3):
    data = bytearray(data)
    for _ in range(edits):
        at = rng.randrange(len(data))
        data[at:at] = bytes(rng.randrange(256) for _ in range(rng.randrange(1, 40)))
    return bytes(data)


def synthetic_plan_and_bodies():
    rng = random.Random(7)
    plan = {'schema': xc.PLAN_SCHEMA, 'families': []}
    bodies = {}
    for fid in ('alpha', 'beta', 'gamma'):
        branches = ['1', '2', '1', '2']
        rels = [release(fid, i + 1, branches[i], 10) for i in range(4)]
        plan['families'].append({'family_id': fid, 'class': 'H1', 'name': fid,
                                 'license': {'spdx': 'MIT', 'evidence_url': 'https://example.org/l'},
                                 'exclude_globs': [{'glob': 'deps/*', 'reason': 'vendored'}], 'releases': rels})
        big = bytes(rng.randrange(256) for _ in range(40000))
        other = bytes(rng.randrange(256) for _ in range(70000))
        line = {'1': big, '2': mutate(big, rng, 30)}
        for r in rels:
            line[r['branch']] = mutate(line[r['branch']], rng)
            bodies[r['url']] = tar_gz(f"{fid}-{r['ordinal']}", {
                'src/main.c': line[r['branch']], 'src/util.h': other, 'README': b'x', 'deps/lua.c': big})
    for fid in ('delta', 'eps', 'zeta'):
        rels = [release(fid, i + 1, 'main', 12, fmt='binary') for i in range(4)]
        plan['families'].append({'family_id': fid, 'class': 'H4', 'name': fid, 'install_path': fid,
                                 'license': {'spdx': 'MIT', 'evidence_url': 'https://example.org/l'},
                                 'releases': rels})
        exe = bytes(rng.randrange(256) for _ in range(70000))
        for r in rels:
            exe = mutate(exe, rng, 8)
            bodies[r['url']] = exe
    plan['families'].sort(key=lambda f: f['family_id'])
    return plan, bodies


class Plan(unittest.TestCase):
    def test_committed_plan_is_valid(self):
        if PLAN.exists():
            self.assertEqual(xc.validate_plan(json.loads(PLAN.read_bytes())), [])

    def test_synthetic_plan_is_valid(self):
        plan, _ = synthetic_plan_and_bodies()
        self.assertEqual(xc.validate_plan(plan), [])

    def test_h1_order_and_chronology_are_enforced(self):
        plan, _ = synthetic_plan_and_bodies()
        alpha = plan['families'][0]
        alpha['releases'][2]['branch'] = '2'
        self.assertTrue(any('A1 < B1 < A2 < B2' in e for e in xc.validate_plan(plan)))
        plan, _ = synthetic_plan_and_bodies()
        plan['families'][0]['releases'][1]['time']['value'] = '2024-01-10'
        self.assertTrue(any('chronological' in e for e in xc.validate_plan(plan)))

    def test_http_and_unknown_class_are_rejected(self):
        plan, _ = synthetic_plan_and_bodies()
        plan['families'][0]['releases'][0]['url'] = 'http://example.org/x'
        plan['families'][1]['class'] = 'H9'
        errors = xc.validate_plan(plan)
        self.assertTrue(any('https url' in e for e in errors) and any(': class' in e for e in errors))


class CDC(unittest.TestCase):
    def test_spans_cover_input_and_respect_bounds(self):
        data = random.Random(1).randbytes(300000)
        spans = xc.cdc_spans(data)
        self.assertEqual([o for o, _ in spans], [sum(l for _, l in spans[:i]) for i in range(len(spans))])
        self.assertEqual(sum(l for _, l in spans), len(data))
        self.assertTrue(all(4096 <= l <= 65536 for _, l in spans[:-1]))

    def test_boundaries_resynchronize_after_an_insertion(self):
        data = random.Random(2).randbytes(200000)
        edited = data[:1000] + b'inserted' + data[1000:]
        cuts = {o + l for o, l in xc.cdc_spans(data)}
        shifted = {o + l - 8 for o, l in xc.cdc_spans(edited)}
        self.assertGreater(len(cuts & shifted), len(cuts) // 2)

    def test_golden_lengths(self):
        data = bytes((i * 131 + (i >> 7)) & 0xff for i in range(150000))
        digest = hashlib.sha256(json.dumps(xc.cdc_spans(data)).encode()).hexdigest()[:16]
        self.assertEqual(digest, GOLDEN_CDC)
        self.assertEqual(digest, hashlib.sha256(json.dumps(_reference_spans(data)).encode()).hexdigest()[:16])

    def test_max_cut_on_constant_input(self):
        spans = xc.cdc_spans(bytes(140000))
        self.assertTrue(all(l <= 65536 for _, l in spans))
        self.assertEqual(sum(l for _, l in spans), 140000)


GOLDEN_CDC = '268949d6f35bcc94'  # params cdc seed 20261007, bits 14, min 4096, max 65536


def _reference_spans(data):
    """Slow restatement of README 4.1 for the golden vector."""
    c = xc.PARAMS['cdc']
    gear = []
    for i in range(256):
        z = (c['seed'] + (i + 1) * 0x9e3779b97f4a7c15) % 2 ** 64
        z = ((z ^ (z >> 30)) * 0xbf58476d1ce4e5b9) % 2 ** 64
        z = ((z ^ (z >> 27)) * 0x94d049bb133111eb) % 2 ** 64
        gear.append(z ^ (z >> 31))
    spans, start = [], 0
    while start < len(data):
        h, length = 0, 0
        while start + length < len(data):
            h = (h * 2 + gear[data[start + length]]) % 2 ** 64
            length += 1
            if (length >= c['min_bytes'] and h >> (64 - c['bits']) == 0) or length == c['max_bytes']:
                break
        spans.append((start, length))
        start += length
    return spans




class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan, bodies = synthetic_plan_and_bodies()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.store = Path(cls.tmp.name) / 'store'
        fetch = lambda url, cap: (bodies[url], url, 1)
        cls.corpus = xc.materialize(cls.plan, cls.store, fetch, log=lambda *_: None, plan_sha256='0' * 64)
        cls.candidates = xc.build_candidates(cls.corpus)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_corpus_is_canonical_and_store_matches(self):
        m.loads_strict(m.canonical_bytes(self.corpus))
        for o in self.corpus['occurrences']:
            data = (self.store / o['object_id']).read_bytes()
            self.assertEqual((len(data), hashlib.sha256(data).hexdigest()), (o['bytes'], o['object_id']))

    def test_members_and_exclusions(self):
        paths = {o['provenance']['member_path'] for o in self.corpus['occurrences'] if o['class'] == 'H1'}
        self.assertEqual(paths, {'src/main.c', 'src/util.h'})  # README not .c/.h, deps/* vendored
        bins = {o['provenance']['member_path'] for o in self.corpus['occurrences'] if o['class'] == 'H4'}
        self.assertEqual(bins, {'delta', 'eps', 'zeta'})

    def test_cdc_chunks_tile_their_parent(self):
        parents = {o['object_id']: o for o in self.corpus['occurrences'] if o['track'] == 'file'}
        chunks = {}
        for o in self.corpus['occurrences']:
            if o['track'] == 'cdc-16k':
                chunks.setdefault((o['source_id'], o['parent_object_id']), []).append(o)
        for (_, pid), cs in chunks.items():
            self.assertEqual(sum(c['bytes'] for c in cs), parents[pid]['bytes'])

    def test_queries_follow_the_rules(self):
        occ = {o['occurrence_id']: o for o in self.corpus['occurrences']}
        caps = xc.PARAMS['candidate_caps']
        near = [q for q in self.candidates['queries'] if q['status'] == 'near_duplicate']
        self.assertTrue(near)
        for q in near:
            t = occ[q['target']]
            self.assertIn(t['ordinal'], (2, 3, 4))
            self.assertEqual(q['cell'], xc.cell_of(t))
            for cat, cap in caps.items():
                self.assertLessEqual(sum(b['category'] == cat for b in q['bases']), cap)
            for b in q['bases']:
                r = occ[b['representative']]
                self.assertEqual((r['object_id'], r['track']), (b['object_id'], t['track']))
                self.assertLess(r['available'][1], t['available'][0])
                self.assertNotEqual(b['object_id'], t['object_id'])
        for cell in xc.PARAMS['cells']:
            self.assertLessEqual(sum(q['cell'] == cell for q in near), xc.PARAMS['cell_quota'])

    def test_h1_same_path_includes_the_other_branch(self):
        occ = {o['occurrence_id']: o for o in self.corpus['occurrences']}
        q = next(q for q in self.candidates['queries'] if q['status'] == 'near_duplicate' and q['cell'] == 'H1-file'
                 and occ[q['target']]['ordinal'] == 4)
        branches = {occ[b['representative']]['branch'] for b in q['bases'] if b['category'] == 'same_path_historical'}
        self.assertEqual(branches, {'1', '2'})

    def test_deterministic_and_order_independent(self):
        shuffled = dict(self.corpus, occurrences=list(reversed(self.corpus['occurrences'])))
        again = xc.build_candidates(shuffled)
        self.assertEqual(again['queries'], self.candidates['queries'])

    def test_compute_cap_truncates_a_suffix(self):
        saved = xc.PARAMS['encode_bytes_max']
        try:
            xc.PARAMS['encode_bytes_max'] = 2_000_000
            small = xc.build_candidates(self.corpus)
        finally:
            xc.PARAMS['encode_bytes_max'] = saved
        ranks = sorted(q['measure_rank'] for q in small['queries'] if q['measured'])
        self.assertTrue(small['compute_cap_truncated'])
        self.assertEqual(ranks, list(range(len(ranks))))

    def test_rankings_and_version_previous(self):
        queries = xs.queries_for_ranking(self.corpus, self.candidates)
        q = next(q for q in queries if q['cell'] == 'H1-file' and q['target']['ordinal'] == 3)
        first = next(b for b in q['bases'] if b['object_id'] == xs.rank_version_previous(q)[0])
        self.assertEqual((first['branch'], first['path']), (q['target']['branch'], q['target']['path']))


class Decision(unittest.TestCase):
    def _rows(self, cell, fams, useful=True):
        return [{'cell': cell, 'k': 1, 'useful_delta': useful, 'target_occurrence_id': f'{cell}{i}',
                 'family_id': fams[i % len(fams)]} for i in range(10)]

    def _summary(self, cell, method, budget, sc, k=1):
        return {'cell': cell, 'method': method, 'budget_bytes': budget, 'k': k, 'savings_capture': sc,
                'useful_recall': sc, 'bootstrap': {'savings_capture': {'ci95': [sc, sc]}}}

    def test_hard_needs_headroom_targets_and_families(self):
        summary, rows = [], []
        for cell in xc.PARAMS['cells']:
            rows += self._rows(cell, ['a', 'b', 'c'] if cell != 'H4-cdc' else ['a'])
            for k in (1, 4):
                summary += [self._summary(cell, 'previous_version', None, 0.99 if cell == 'H1-file' else 0.9, k),
                            self._summary(cell, 'minhash_resemblance', 64, 0.95, k),
                            self._summary(cell, 'minhash_resemblance', 1024, 0.97, k)]
        d = xs.decide(summary, rows)
        by = {(c['cell'], c['lane'], c['budget_bytes']): c for c in d['cells']}
        self.assertFalse(by[('H1-file', 'L-meta', 64)]['hard'])  # previous_version 0.99: headroom 0.01
        self.assertTrue(by[('H1-file', 'L-blind', 64)]['hard'])  # minhash 64 B 0.95
        self.assertTrue(by[('H1-file', 'L-blind', 1024)]['hard'])  # 0.97 → 0.03
        self.assertEqual(by[('H1-cdc', 'L-meta', 64)]['best_method'], 'minhash_resemblance')
        self.assertFalse(by[('H4-cdc', 'L-blind', 64)]['hard'])  # one family only
        self.assertEqual(d['verdict'], 'HEADROOM_FOUND')


if __name__ == '__main__':
    unittest.main()
