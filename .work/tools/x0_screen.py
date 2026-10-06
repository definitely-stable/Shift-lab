"""DELSK-002 X0 screening: exhaustive oracle on the screening C_t, baselines and the preregistered decision.

Exploratory only (.work/corpus/x0/README.md sections 5-6): no registry, no G1, numbers are labelled SCREENING.
`oracle_run.py`, `oracle_build.py`, `oracle_eval.py` and `baselines.py` are imported and never changed.

    x0_screen.py measure <tools-dir> <store> <out-dir>   oracle rows for every measured query (Actions only)
    x0_screen.py rank <store> <out-dir>                   baseline rankings of the measured near queries
    x0_screen.py evaluate <out-dir>                       rows, summary and decision from retained files
"""

import gzip
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import baselines as bl  # noqa: E402
import manifests as m  # noqa: E402
import oracle_eval as oe  # noqa: E402
import oracle_run as orun  # noqa: E402
import x0_corpus as xc  # noqa: E402

PARAMS = xc.PARAMS
PAIR_SCHEMA, TARGET_SCHEMA = 'delsk.x0.pair.v1', 'delsk.x0.target.v1'
SUMMARY_SCHEMA, DECISION_SCHEMA = 'delsk.x0.summary.v1', 'delsk.x0.decision.v1'
FILE_CAP = 64 << 20
LABEL = 'SCREENING'


def load(out):
    out = Path(out)
    corpus = m.loads_strict(gzip.decompress((out / 'corpus.json.gz').read_bytes()))
    candidates = m.loads_strict((out / 'candidates.json').read_bytes())
    xc.check(candidates['corpus_sha256'] == m.digest(corpus), 'candidates bind another corpus')
    return corpus, candidates


def measured_queries(candidates):
    qs = [q for q in candidates['queries'] if q['status'] == 'near_duplicate' and q['measured']]
    return sorted(qs, key=lambda q: q['measure_rank'])


# --- oracle ---------------------------------------------------------------------------------------------------------

def target_row(q, t, solo, costs):
    """Target row in the shape baselines.target_rows reads (oracle_eval.derive_target semantics)."""
    raw = oe.raw_total(t['bytes'])
    comp = solo['compressed_total_bytes'] if solo['status'] == 'ok' else None
    s = comp if comp is not None and comp < raw else raw
    finite = {b: c for b, c in costs.items() if c is not None}
    best = min(finite.values()) if finite else None
    useful = best is not None and best < s
    return {'schema': TARGET_SCHEMA, 'label': LABEL, 'target_occurrence_id': q['target'], 'cell': q['cell'],
            'target_object_id': t['object_id'], 'family_id': t['family_id'], 'split': t['split'],
            'track': t['track'], 'query_status': q['status'], 'target_bytes': t['bytes'],
            'candidate_count': len(costs), 'pairs_ok': len(finite), 'raw_total_bytes': raw,
            'standalone_status': solo['status'], 'standalone_compressed_total_bytes': comp,
            'standalone_total_bytes': s, 'oracle_delta_total_bytes': best,
            'oracle_tie_bases': sorted(b for b, c in finite.items() if c == best),
            'oracle_total_bytes': best if useful else s, 'useful_delta': useful}


def measure(tools_dir, store, out, env=os.environ):
    """Every pair of every measured query under the pinned codec lock; decode mismatch makes the run INVALID."""
    corpus, candidates = load(out)
    out, started = Path(out), time.monotonic()
    tools_path = Path(tools_dir) / 'tools.json'
    _, codecs = orun.load_tools(tools_path, orun.CODEC_LOCK.read_bytes())
    conformance, _ = orun.conformance_record(tools_path, env=env)
    (out / 'conformance.json').write_bytes(m.canonical_bytes(conformance))
    xc.check(conformance['verdict'] == 'PASS', 'codec conformance C01-C14 did not pass')
    occ = {o['occurrence_id']: o for o in corpus['occurrences']}
    work = Path(tempfile.mkdtemp(prefix='x0-'))
    pairs, targets, invalid = [], [], []
    try:
        for q in measured_queries(candidates):
            t = occ[q['target']]
            tdata = bl.read_object(store, t['object_id'], t['bytes'])
            xc.check(time.monotonic() - started < PARAMS['workload_wall_seconds'], 'workload wall cap reached')
            status, phase, error, fields, _ = orun.measure_standalone(codecs['standalone'], tdata, work, FILE_CAP)
            solo = {'status': status, 'compressed_total_bytes': fields['compressed_total_bytes']}
            if status == 'decode_mismatch':
                invalid.append(['standalone', q['target']])
            costs = {}
            for b in q['bases']:
                bdata = bl.read_object(store, b['object_id'], occ[b['representative']]['bytes'])
                status, phase, error, fields, _ = orun.measure_delta(codecs['delta'], bdata, tdata, work, FILE_CAP)
                if status == 'decode_mismatch':
                    invalid.append([b['object_id'], q['target']])
                costs[b['object_id']] = fields['delta_total_bytes'] if status == 'ok' else None
                pairs.append({'schema': PAIR_SCHEMA, 'label': LABEL, 'target_occurrence_id': q['target'],
                              'base_object_id': b['object_id'], 'category': b['category'], 'status': status,
                              'phase': phase, 'error_class': error,
                              'delta_total_bytes': fields['delta_total_bytes'],
                              'encode_wall_ns': fields['encode_wall_ns'], 'decode_wall_ns': fields['decode_wall_ns']})
            targets.append(target_row(q, t, solo, costs))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    bl.write_jsonl(out / 'pairs.jsonl', pairs)
    bl.write_jsonl(out / 'targets.jsonl', targets)
    xc.check(not invalid, f'INVALID: decode mismatch on {invalid[:3]}')
    return {'pairs': len(pairs), 'targets': len(targets), 'wall_seconds': round(time.monotonic() - started)}


# --- baselines ------------------------------------------------------------------------------------------------------

def rank_version_previous(q):
    """Knows versions: same member path and same release branch first (nearest offset, latest earlier release),
    then the previous_version order."""
    t, pv = q['target'], {oid: i for i, oid in enumerate(bl.rank_previous_version(q))}

    def key(b):
        same = t['path'] is not None and b['path'] == t['path'] and b['branch'] == t['branch']
        if same:
            return (0, abs((b['offset'] or 0) - (t['offset'] or 0)), -b['ordinal'], pv[b['object_id']])
        return (1, 0, 0, pv[b['object_id']])
    return [b['object_id'] for b in sorted(q['bases'], key=key)]


METADATA = {**bl.METADATA_METHODS, 'version_previous': rank_version_previous}


def queries_for_ranking(corpus, candidates):
    occ = {o['occurrence_id']: o for o in corpus['occurrences']}

    def meta(o):
        return {'object_id': o['object_id'], 'bytes': o['bytes'], 'path': o['provenance']['member_path'],
                'offset': o['provenance']['offset'], 'ordinal': o['ordinal'], 'branch': o['branch']}
    out = []
    for q in measured_queries(candidates):
        t = occ[q['target']]
        out.append({'target_occurrence_id': q['target'], 'family_id': t['family_id'], 'track': t['track'],
                    'split': t['split'], 'cell': q['cell'], 'target': meta(t),
                    'bases': [meta(occ[b['representative']]) for b in q['bases']]})
    return out


def rank(store, out):
    corpus, candidates = load(out)
    queries = queries_for_ranking(corpus, candidates)
    objects = {}
    for q in queries:
        for meta in (q['target'], *q['bases']):
            objects[meta['object_id']] = meta['bytes']
    started, sketches = time.process_time(), {}
    for oid, size in sorted(objects.items()):
        sketches[oid] = bl.sketch(bl.read_object(store, oid, size))
    sketch_seconds = time.process_time() - started
    rows = []
    for q in queries:
        base = {'schema': bl.RANKINGS_SCHEMA, 'target_occurrence_id': q['target_occurrence_id'],
                'family_id': q['family_id'], 'track': q['track'], 'split': q['split'], 'cell': q['cell']}
        for method, fn in METADATA.items():
            rows.append({**base, 'method': method, 'budget_bytes': None, 'ranking': fn(q)})
        for method in bl.CONTENT_METHODS:
            for budget in PARAMS['decision']['budgets_bytes']:
                rows.append({**base, 'method': method, 'budget_bytes': budget,
                             'ranking': bl.rank_content(q, sketches, method, budget // bl.PARAMS['hash_bytes'])})
    bl.write_jsonl(Path(out) / 'rankings.jsonl', rows)
    costs = {'objects': len(objects), 'object_bytes': sum(objects.values()),
             'sketch_cpu_seconds': round(sketch_seconds, 3)}
    (Path(out) / 'costs.json').write_text(json.dumps(costs, indent=2, sort_keys=True) + '\n')
    return costs


# --- evaluation and decision ----------------------------------------------------------------------------------------

def evaluate(out):
    out = Path(out)
    _, candidates = load(out)
    targets = {r['target_occurrence_id']: r for r in bl.jsonl(out / 'targets.jsonl')}
    pairs = {}
    for r in bl.jsonl(out / 'pairs.jsonl'):
        key = (r['target_occurrence_id'], r['base_object_id'])
        xc.check(key not in pairs, 'duplicate pair row')
        pairs[key] = r['delta_total_bytes'] if r['status'] == 'ok' else None
    expected = {q['target']: q for q in measured_queries(candidates)}
    xc.check(set(targets) == set(expected), 'target rows differ from the measured queries')
    for tid, q in expected.items():
        xc.check({b for (t, b) in pairs if t == tid} == {b['object_id'] for b in q['bases']},
                 f'pair rows differ from C_t: {tid}')
    rankings = bl.jsonl(out / 'rankings.jsonl')
    rows = []
    for r in rankings:
        for row in bl.target_rows(r, targets, pairs):
            rows.append({**row, 'cell': targets[r['target_occurrence_id']]['cell'], 'label': LABEL})
    groups = {}
    for r in rows:
        groups.setdefault((r['cell'], r['method'], r['budget_bytes'], r['k']), []).append(r)
    summary = []
    for (cell, method, budget, k), group in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1],
                                                                                   kv[0][2] or 0, kv[0][3])):
        population = {t for t in expected if expected[t]['cell'] == cell}
        xc.check({r['target_occurrence_id'] for r in group} == population and len(group) == len(population),
                 f'population incomplete: {cell} {method} {budget} K={k}')
        summary.append({'schema': SUMMARY_SCHEMA, 'label': LABEL, 'cell': cell, 'method': method,
                        'budget_bytes': budget, 'k': k, **bl.aggregate(group), 'bootstrap': bl.bootstrap(group)})
    bl.write_jsonl(out / 'rows.jsonl', rows)
    bl.write_jsonl(out / 'summary.jsonl', summary)
    decision = decide(summary, rows)
    (out / 'decision.json').write_text(json.dumps(decision, indent=2, sort_keys=True) + '\n')
    return decision


def decide(summary, rows):
    """README section 6, unchanged after any result is seen."""
    d = PARAMS['decision']
    cells = []
    for cell in PARAMS['cells']:
        cell_rows = [r for r in rows if r['cell'] == cell and r['k'] == d['k']]
        useful = {r['target_occurrence_id']: r['family_id'] for r in cell_rows if r['useful_delta']}
        enough = len(useful) >= d['min_useful_targets'] and len(set(useful.values())) >= d['min_families']
        for lane, methods in sorted(PARAMS['lanes'].items()):
            for budget in d['budgets_bytes']:
                pool = [s for s in summary if s['cell'] == cell and s['k'] == d['k'] and s['method'] in methods
                        and (s['budget_bytes'] or 0) <= budget and s['savings_capture'] is not None]
                best = sorted(pool, key=lambda s: (-s['savings_capture'], -(s['useful_recall'] or 0),
                                                   s['budget_bytes'] or 0, s['method']))[0] if pool else None
                second = None
                if best is not None:
                    second = next(s for s in summary if s['cell'] == cell and s['method'] == best['method']
                                  and s['budget_bytes'] == best['budget_bytes'] and s['k'] == d['secondary_k'])
                headroom = None if best is None else 1 - best['savings_capture']
                cells.append({'cell': cell, 'lane': lane, 'budget_bytes': budget,
                              'useful_targets': len(useful), 'families_with_useful': len(set(useful.values())),
                              'best_method': best and best['method'], 'best_budget_bytes': best and best['budget_bytes'],
                              'best_savings_capture': best and best['savings_capture'],
                              'best_useful_recall': best and best['useful_recall'],
                              'best_savings_capture_ci95': best and best['bootstrap']['savings_capture']['ci95'],
                              'headroom': headroom,
                              'headroom_secondary_k': None if second is None or second['savings_capture'] is None
                              else 1 - second['savings_capture'],
                              'hard': bool(enough and headroom is not None and headroom >= d['headroom_min'])})
    hard_256 = [c for c in cells if c['hard'] and c['budget_bytes'] == 256]
    return {'schema': DECISION_SCHEMA, 'label': LABEL, 'params_sha256': xc.file_sha256(xc.PARAMS_PATH),
            'cells': cells, 'hard_at_1024': sorted({(c['cell'], c['lane']) for c in cells
                                                    if c['hard'] and c['budget_bytes'] == 1024}),
            'hard_at_256': sorted({(c['cell'], c['lane']) for c in hard_256}),
            'verdict': 'HEADROOM_FOUND' if hard_256 else 'NO_HEADROOM_AT_256'}


def main(argv):
    if argv[:1] == ['measure'] and len(argv) == 4:
        print(json.dumps(measure(*argv[1:])))
        return 0
    if argv[:1] == ['rank'] and len(argv) == 3:
        print(json.dumps(rank(*argv[1:])))
        return 0
    if argv[:1] == ['evaluate'] and len(argv) == 2:
        decision = evaluate(argv[1])
        print(decision['verdict'], decision['hard_at_256'])
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
