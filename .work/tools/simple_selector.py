"""Delsk simple selector `delsk.simple-selector.v1` (.work/selector/README.md): reference and offline evaluation.

The selector interleaves two cheap orders: metadata (same logical path and release line, nearest offset, latest
earlier version) and a 64-byte bottom-k MinHash of 8-byte shingles. It proposes K bases; the caller encodes each,
verifies the decode and keeps the cheapest of them and the standalone representation.

    simple_selector.py evaluate <out.json>   in-sample evaluation on retained development data (pilot-v1 dev/cal, X0)
    simple_selector.py vectors <out.txt>     parity vectors for other implementations (.work/selector/rust)
    simple_selector.py features <pilot-store> <x0-store> <out.jsonl>   S3 descriptor resemblance per pair (Actions)
    simple_selector.py abstention <features.jsonl> <out.json>          S3 abstention analysis and decision (offline)
"""

import json
import sys
from fractions import Fraction
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


# --- parity vectors ------------------------------------------------------------------------------------------

def xorshift_bytes(seed, n):
    """Deterministic test bytes shared with the Rust tests: xorshift64 state, low byte of each step."""
    x, out = seed or 1, bytearray()
    for _ in range(n):
        x ^= (x << 13) & bl.M64
        x ^= x >> 7
        x ^= (x << 17) & bl.M64
        out.append(x & 0xff)
    return bytes(out)


def mutate(data, seed, edits):
    """Deterministic edits for related objects: each edit replaces 16 bytes at a position from xorshift."""
    data, noise = bytearray(data), xorshift_bytes(seed, 18 * edits)
    for i in range(edits):
        chunk = noise[18 * i:18 * i + 18]
        at = int.from_bytes(chunk[:2], 'big') % max(1, len(data) - 16)
        data[at:at + 16] = chunk[2:]
    return bytes(data)


def vector_lines():
    """D: descriptor of xorshift bytes (seed, length); R: resemblance as shared/union; C: select cases."""
    lines = []
    for seed, n in [(1, 0), (2, 1), (3, 7), (4, 8), (5, 9), (6, 64), (7, 4096), (8, 65537), (9, 300000)]:
        d = descriptor(xorshift_bytes(seed, n))
        lines.append(f"D {seed} {n} {','.join(f'{h:016x}' for h in d) or '-'}")
    base = xorshift_bytes(11, 20000)
    family = {f'o{i:02d}': mutate(base, 100 + i, 60 * i)[:20000 - 97 * i] for i in range(12)}
    family['far'] = xorshift_bytes(12, 20000)
    family['tiny'] = xorshift_bytes(13, 5)
    desc = {k: descriptor(v) for k, v in family.items()}
    for a, b in [('o00', 'o01'), ('o00', 'o11'), ('o00', 'far'), ('tiny', 'tiny'), ('o03', 'tiny')]:
        da, db = set(desc[a][:SKETCH_HASHES]), set(desc[b][:SKETCH_HASHES])
        union = sorted(da | db)[:SKETCH_HASHES]
        lines.append(f"R {a} {b} {sum(1 for x in union if x in da and x in db)} {len(union)}")
    meta = {}
    for i, k in enumerate(sorted(family)):
        meta[k] = {'object_id': k, 'bytes': len(family[k]), 'path': ['src/a.c', 'src/a.c', 'src/b.c', None][i % 4],
                   'line': ['1', '2', '1', None][i % 4], 'version_rank': i, 'offset': [None, 0, 4096, 8192][i % 3]}
    for k_name, t_name, ks in [('c1', 'o11', 1), ('c2', 'o11', 3), ('c3', 'far', 2), ('c4', 'o06', 14), ('c5', 'tiny', 4)]:
        t = meta[t_name]
        bases = [meta[k] for k in sorted(meta) if k != t_name]
        order = select(t, bases, desc, ks)
        lines.append(f"C {k_name} {t_name} {ks} {','.join(order)}")
    for k in sorted(meta):
        m = meta[k]
        lines.append(f"O {k} {m['bytes']} {m['path'] or '-'} {m['line'] or '-'} {m['version_rank']} "
                     f"{'-' if m['offset'] is None else m['offset']} {','.join(f'{h:016x}' for h in desc[k]) or '-'}")
    return lines


# --- S3: abstention (.work/selector/s3.md) ------------------------------------------------------------------

S3_LEVELS = (0, 1, 2, 3, 4)       # abstain if no metadata candidate and best shared hashes < level; 0 = never
S3_K = 2
S3_LOST_MAX = 0.005               # pooled lost oracle savings / total oracle savings
S3_FN_MAX = 0.01                  # abstained useful-delta targets / useful-delta targets


def _feature_row(population, target_id, t, bases, desc, oracle):
    has_meta = bool(metadata_order(t, bases))
    per_base = {b['object_id']: list(_shared_union(desc[t['object_id']], desc[b['object_id']])) for b in bases}
    best = max(per_base.values(), key=lambda su: (Fraction(su[0], max(su[1], 1)), su[0]), default=[0, 0])
    return {'population': population, 'target_occurrence_id': target_id, 'candidates': len(bases),
            'has_meta': has_meta, 'best_shared': max((su[0] for su in per_base.values()), default=0),
            'best_pair': best, 'useful_delta': oracle['useful_delta'] if oracle else None,
            'standalone_bytes': oracle['standalone_total_bytes'] if oracle else None,
            'oracle_bytes': oracle['oracle_total_bytes'] if oracle else None, 'per_base': per_base}


def _shared_union(a, b):
    da, db = set(a[:SKETCH_HASHES]), set(b[:SKETCH_HASHES])
    union = sorted(da | db)[:SKETCH_HASHES]
    return sum(1 for x in union if x in da and x in db), len(union)


def features(pilot_store, x0_store):
    """Descriptor resemblance of every (target, base) of the evaluated populations, from natural bytes."""
    import x0_screen as xs
    rows, cache = [], {}

    def desc_of(store, m):
        key = (str(store), m['object_id'])
        if key not in cache:
            cache[key] = descriptor(bl.read_object(store, m['object_id'], m['bytes']))
        return cache[key]
    targets, _ = bl.load_oracle(PILOT_ORACLE)
    for q in bl.natural_universe():
        meta = lambda m: {**m, 'line': q['family_id'], 'version_rank': m['ordinal']}
        t, bases = meta(q['target']), [meta(b) for b in q['bases']]
        desc = {m['object_id']: desc_of(pilot_store, m) for m in (t, *bases)}
        rows.append(_feature_row(f"pilot-{q['split']}", q['target_occurrence_id'], t, bases, desc,
                                 targets[q['target_occurrence_id']]))
    corpus, candidates = xs.load(X0_RUN)
    x0_targets = {r['target_occurrence_id']: r for r in bl.jsonl(X0_RUN / 'targets.jsonl')}
    for q in xs.queries_for_ranking(corpus, candidates):
        meta = lambda m: {**m, 'line': m['branch'], 'version_rank': m['ordinal']}
        t, bases = meta(q['target']), [meta(b) for b in q['bases']]
        desc = {m['object_id']: desc_of(x0_store, m) for m in (t, *bases)}
        rows.append(_feature_row(f"x0-{q['cell']}", q['target_occurrence_id'], t, bases, desc,
                                 x0_targets[q['target_occurrence_id']]))
    # Adversarial negatives without metadata: random bytes and zlib streams of real targets against the pilot
    # development bases of the file track. Delta from real bases cannot help them; only the signal is recorded.
    import zlib
    pool = {}
    for q in bl.natural_universe():
        if q['split'] == 'development' and q['track'] == 'file':
            for b in q['bases']:
                pool[b['object_id']] = b
    pool_bases = [{**b, 'path': None, 'line': None, 'version_rank': 0} for _, b in sorted(pool.items())]
    for i in range(8):
        data = xorshift_bytes(500 + i, 65536)
        t = {'object_id': f'random-{i}', 'bytes': len(data), 'path': None, 'line': None, 'version_rank': 0,
             'offset': None}
        desc = {t['object_id']: descriptor(data), **{b['object_id']: desc_of(pilot_store, b) for b in pool_bases}}
        rows.append(_feature_row('adversarial-random', t['object_id'], t, pool_bases, desc, None))
    for i, (oid, b) in enumerate(sorted(pool.items())[:8]):
        data = zlib.compress(bl.read_object(pilot_store, oid, b['bytes']), 9)
        t = {'object_id': f'zlib-{i}', 'bytes': len(data), 'path': None, 'line': None, 'version_rank': 0,
             'offset': None}
        others = [x for x in pool_bases if x['object_id'] != oid]
        desc = {t['object_id']: descriptor(data), **{x['object_id']: desc_of(pilot_store, x) for x in others}}
        rows.append(_feature_row('adversarial-zlib', t['object_id'], t, others, desc, None))
    return rows


def abstention(rows):
    """README s3.md section 3: per level, saved encoder calls and lost savings; the preregistered choice."""
    levels = []
    natural = [r for r in rows if r['useful_delta'] is not None]
    total_savings = sum(r['standalone_bytes'] - r['oracle_bytes'] for r in natural)
    useful = [r for r in natural if r['useful_delta']]
    calls = sum(min(S3_K, r['candidates']) for r in natural)
    for level in S3_LEVELS:
        skip = lambda r: level > 0 and not r['has_meta'] and r['best_shared'] < level
        lost = sum(r['standalone_bytes'] - r['oracle_bytes'] for r in useful if skip(r))
        fn = sum(1 for r in useful if skip(r))
        by_pop = {}
        for r in rows:
            p = by_pop.setdefault(r['population'], {'targets': 0, 'abstained': 0, 'useful': 0, 'useful_abstained': 0})
            p['targets'] += 1
            p['abstained'] += skip(r)
            p['useful'] += bool(r['useful_delta'])
            p['useful_abstained'] += bool(r['useful_delta']) and skip(r)
        levels.append({'level': level,
                       'saved_calls': sum(min(S3_K, r['candidates']) for r in natural if skip(r)),
                       'saved_call_share': sum(min(S3_K, r['candidates']) for r in natural if skip(r)) / calls,
                       'useful_abstained': fn, 'useful_abstained_share': fn / len(useful),
                       'lost_savings_bytes': lost, 'lost_savings_share': lost / total_savings,
                       'populations': by_pop})
    ok = [l for l in levels if l['lost_savings_share'] <= S3_LOST_MAX and l['useful_abstained_share'] <= S3_FN_MAX]
    chosen = max(ok, key=lambda l: (l['saved_calls'], -l['level']))['level'] if ok else 0
    return {'schema': 'delsk.simple-selector.s3-abstention.v1', 'in_sample': True, 'k': S3_K,
            'lost_max': S3_LOST_MAX, 'fn_max': S3_FN_MAX, 'natural_targets': len(natural),
            'useful_targets': len(useful), 'encoder_calls_k2': calls, 'levels': levels, 'chosen_level': chosen}


def main(argv):
    if argv[:1] == ['evaluate'] and len(argv) == 2:
        result = evaluate()
        Path(argv[1]).write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
        for s in result['summary']:
            print(f"{s['population']:18} K={s['k']:<2} SC={s['savings_capture']:.4f} UR={s['useful_recall']:.3f} "
                  f"nrp95={s['normalized_regret_p95']:.3f} calls÷{s['encoder_call_reduction']:.1f}")
        return 0
    if argv[:1] == ['features'] and len(argv) == 4:
        rows = features(argv[1], argv[2])
        bl.write_jsonl(argv[3], rows)
        print(f'{len(rows)} feature rows')
        return 0
    if argv[:1] == ['abstention'] and len(argv) == 3:
        result = abstention(bl.jsonl(argv[1]))
        Path(argv[2]).write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
        for l in result['levels']:
            print(f"level {l['level']}: calls saved {l['saved_call_share']:.3f}, useful abstained "
                  f"{l['useful_abstained']} ({l['useful_abstained_share']:.3f}), lost {l['lost_savings_share']:.4f}")
        print('chosen level', result['chosen_level'])
        return 0
    if argv[:1] == ['vectors'] and len(argv) == 2:
        Path(argv[1]).write_text('\n'.join(vector_lines()) + '\n')
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
