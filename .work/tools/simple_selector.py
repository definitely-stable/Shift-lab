"""Delsk simple selector `delsk.simple-selector.v1` (.work/selector/README.md): reference and offline evaluation.

The selector interleaves two cheap orders: metadata (same logical path and release line, nearest offset, latest
earlier version) and a 64-byte bottom-k MinHash of 8-byte shingles. It proposes K bases; the caller encodes each,
verifies the decode and keeps the cheapest of them and the standalone representation.

    simple_selector.py evaluate <out.json>   in-sample evaluation on retained development data (pilot-v1 dev/cal, X0)
"""

import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import baselines as bl  # noqa: E402

WORK = TOOLS.parent
SPEC = 'delsk.simple-selector.v1'
SKETCH_HASHES = 8          # 8 hashes x 8 bytes = 64-byte descriptor
SHINGLE_BYTES = 8
SEED = 20261006            # Slice A sketch seed: the retained minhash@64 rankings are exactly this order
K_GRID = (1, 2, 4, 8)
PILOT_ORACLE = WORK / 'results' / 'ORACLE-G1-V4' / 'bundles' / '37434946174-1'
PILOT_RANKINGS = WORK / 'results' / 'DELSK-004-BASELINES-A' / '37443926816-1' / 'rankings.jsonl'
X0_RUN = WORK / 'results' / 'DELSK-002-X0' / '37449333091-1'


# --- descriptor and orders ------------------------------------------------------------------------------------

def descriptor(data):
    """64-byte descriptor: the 8 smallest distinct splitmix64-mixed 8-byte shingles, ascending."""
    return bl.sketch(data, k=SKETCH_HASHES, n=SHINGLE_BYTES, seed=SEED)


def resemblance(a, b):
    return bl.resemblance(a, b, SKETCH_HASHES)


def _gap(t, b):
    return abs(b['bytes'] - t['bytes'])


def metadata_order(t, bases):
    """Bases with the target's logical path and release line, nearest offset first, then the latest earlier
    version. Bases without that path or with an unknown path are not in this order."""
    if t.get('path') is None:
        return []
    same = [b for b in bases if b.get('path') == t['path'] and b.get('line') == t.get('line')]
    return [b['object_id'] for b in sorted(same, key=lambda b: (abs((b.get('offset') or 0) - (t.get('offset') or 0)),
                                                                 -b['version_rank'], _gap(t, b), b['object_id']))]


def content_order(t, bases, descriptors):
    d = descriptors[t['object_id']]
    return [b['object_id'] for b in sorted(bases, key=lambda b: (-resemblance(d, descriptors[b['object_id']]),
                                                                 _gap(t, b), b['object_id']))]


def interleave(meta, content):
    """meta[0], content[0], meta[1], content[1], ... without repeats; the rest of content after meta runs out."""
    out, seen = [], set()
    for i in range(max(len(meta), len(content))):
        for order in (meta, content):
            if i < len(order) and order[i] not in seen:
                seen.add(order[i])
                out.append(order[i])
    return out


def select(t, bases, descriptors, k):
    """The K bases to encode. Every base of C_t appears in the full order, so K = |C_t| is exhaustive."""
    return interleave(metadata_order(t, bases), content_order(t, bases, descriptors))[:k]


# --- offline evaluation on retained development data ----------------------------------------------------------

def rows_for(target_id, order, target, pairs):
    """Protocol section 2-3 quantities of one ranking for every K of K_GRID."""
    d = {b: c for (q, b), c in pairs.items() if q == target_id}
    bl.check(sorted(order) == sorted(d) and len(set(order)) == len(order), f'ranking is not C_t: {target_id}')
    s, o, od = target['standalone_total_bytes'], target['oracle_total_bytes'], target['oracle_delta_total_bytes']
    ties = set(target['oracle_tie_bases'])
    out = []
    for k in K_GRID:
        chosen = order[:k]
        values = [d[b] for b in chosen if d[b] is not None]
        a = min([s, *values])
        out.append({'target_occurrence_id': target_id, 'family_id': target['family_id'], 'k': k,
                    'candidates': len(order), 'encodes': len(chosen), 'standalone_bytes': s, 'oracle_bytes': o,
                    'selected_bytes': a, 'finite_delta': od is not None, 'useful_delta': od is not None and od < s,
                    'strict_hit': od is not None and bool(set(chosen) & ties),
                    'epsilon_hits': {str(e): od is not None and any(v <= od + max(64, e * od) for v in values)
                                     for e in bl.PARAMS['epsilons']},
                    'regret_bytes': a - o, 'normalized_regret': (a - o) / max(o, 64)})
    return out


def _by_target(rankings, method, budget):
    return {r['target_occurrence_id']: r['ranking'] for r in rankings
            if r['method'] == method and r['budget_bytes'] == budget}


def pilot_population():
    """pilot-v1 development and calibration: single release line per family, so line = family."""
    targets, pairs = bl.load_oracle(PILOT_ORACLE)
    rankings = bl.jsonl(PILOT_RANKINGS)
    content = _by_target(rankings, 'minhash_resemblance', 64)
    out = []
    for q in bl.natural_universe():
        meta = lambda m: {**m, 'line': q['family_id'], 'version_rank': m['ordinal']}
        t, bases = meta(q['target']), [meta(b) for b in q['bases']]
        order = interleave(metadata_order(t, bases), content[q['target_occurrence_id']])
        out.append({'population': f"pilot-{q['split']}", 'target_occurrence_id': q['target_occurrence_id'],
                    'order': order, 'target': targets[q['target_occurrence_id']]})
    return out, pairs


def x0_population():
    import x0_screen as xs
    corpus, candidates = xs.load(X0_RUN)
    targets = {r['target_occurrence_id']: r for r in bl.jsonl(X0_RUN / 'targets.jsonl')}
    pairs = {(r['target_occurrence_id'], r['base_object_id']): r['delta_total_bytes'] if r['status'] == 'ok'
             else None for r in bl.jsonl(X0_RUN / 'pairs.jsonl')}
    content = _by_target(bl.jsonl(X0_RUN / 'rankings.jsonl'), 'minhash_resemblance', 64)
    out = []
    for q in xs.queries_for_ranking(corpus, candidates):
        meta = lambda m: {**m, 'line': m['branch'], 'version_rank': m['ordinal']}
        t, bases = meta(q['target']), [meta(b) for b in q['bases']]
        order = interleave(metadata_order(t, bases), content[q['target_occurrence_id']])
        out.append({'population': f"x0-{q['cell']}", 'target_occurrence_id': q['target_occurrence_id'],
                    'order': order, 'target': targets[q['target_occurrence_id']]})
    return out, pairs


def evaluate():
    summary = []
    for population, pairs in (pilot_population(), x0_population()):
        groups = {}
        for item in population:
            for row in rows_for(item['target_occurrence_id'], item['order'], item['target'], pairs):
                groups.setdefault((item['population'], row['k']), []).append(row)
        for (name, k), rows in sorted(groups.items()):
            agg = bl.aggregate(rows)
            summary.append({'population': name, 'k': k, 'targets': agg['targets'],
                            'useful_delta_targets': agg['useful_delta_targets'],
                            'savings_capture': agg['savings_capture'], 'useful_recall': agg['useful_recall'],
                            'strict_recall': agg['strict_recall'],
                            'normalized_regret_p50': agg['normalized_regret_p50'],
                            'normalized_regret_p95': agg['normalized_regret_p95'],
                            'encoder_call_reduction': agg['encoder_call_reduction']})
    return {'schema': 'delsk.simple-selector.dev-eval.v1', 'spec': SPEC, 'in_sample': True,
            'inputs': {'pilot_oracle': str(PILOT_ORACLE.relative_to(WORK)),
                       'pilot_rankings': str(PILOT_RANKINGS.relative_to(WORK)), 'x0_run': str(X0_RUN.relative_to(WORK))},
            'summary': summary}


def main(argv):
    if argv[:1] == ['evaluate'] and len(argv) == 2:
        result = evaluate()
        Path(argv[1]).write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
        for s in result['summary']:
            print(f"{s['population']:18} K={s['k']:<2} SC={s['savings_capture']:.4f} UR={s['useful_recall']:.3f} "
                  f"nrp95={s['normalized_regret_p95']:.3f} calls÷{s['encoder_call_reduction']:.1f}")
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
