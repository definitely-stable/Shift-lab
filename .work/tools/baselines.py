"""DELSK-004 Slice A: cheap baselines on the common oracle (contract: .work/baselines/contract.md).

    baselines.py materialize STORE                     fetch and verify the pinned natural store (Actions only)
    baselines.py rank STORE OUT_DIR                    rankings of every method on development/calibration targets
    baselines.py evaluate RANKINGS ORACLE_BUNDLE OUT_DIR    metrics against a retained oracle bundle

Stdlib only. Every method sees exactly the frozen candidate universe C_t of the candidate lock and the metadata a
deployment has (size, release order, member path and offset). It never sees the candidate category of the lock, the
split label beyond selecting the population, or any oracle value. Evaluation-split targets are never read, ranked or
evaluated: their oracle rows are sealed and the evaluation split opens once, for a finalist (protocol 4).

Quality is computed from the exhaustive oracle rows (D_E(b, t) of every pair), so no candidate is re-encoded:
A_K(t) = min(S(t), min D_E(b, t) over the first K bases of the ranking) (protocol 2-3).
"""
import hashlib
import heapq
import json
import math
from pathlib import Path
import random
import sys
import time

TOOLS = Path(__file__).resolve().parent
WORK = TOOLS.parent
sys.path.insert(0, str(TOOLS))

PARAMS_PATH = WORK / 'baselines' / 'params.json'
PARAMS = json.loads(PARAMS_PATH.read_bytes())
SPLITS = tuple(PARAMS['evaluated_splits'])
K_GRID = tuple(PARAMS['k_grid'])
M64 = (1 << 64) - 1
CONTENT_METHODS = ('minhash_resemblance', 'containment')
RANKINGS_SCHEMA = 'delsk.baselines.ranking.v1'
ROW_SCHEMA = 'delsk.baselines.row.v1'
SUMMARY_SCHEMA = 'delsk.baselines.summary.v1'


class BaselineError(Exception):
    """Inconsistent input: the run fails, nothing is repaired."""


def check(ok, reason):
    if not ok:
        raise BaselineError(reason)


def params_sha256():
    return hashlib.sha256(PARAMS_PATH.read_bytes()).hexdigest()


def jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line]


def write_jsonl(path, rows):
    Path(path).write_text(''.join(json.dumps(r, sort_keys=True, separators=(',', ':')) + '\n' for r in rows),
                          encoding='utf-8')


# --- universe (C_t and deployment metadata) ----------------------------------------------------------------------

def universe(candidate, corpus, plan):
    """Near-duplicate queries of the evaluated splits with the metadata every method may use. Identity-only targets
    are the dedup branch and evaluation-split targets stay sealed; neither is returned."""
    occurrences = {o['occurrence_id']: o for o in corpus['occurrences']}
    ordinal = {r['release_id']: r['ordinal'] for f in plan['families'] for r in f['releases']}

    def meta(occ):
        prov = occ['provenance']
        return {'object_id': occ['object_id'], 'bytes': occ['bytes'], 'path': prov.get('member_path'),
                'offset': prov.get('offset'), 'ordinal': ordinal[occ['source_id']]}
    out = []
    for q in candidate['queries']:
        target = occurrences[q['target']]
        if q['status'] != 'near_duplicate' or target['split'] not in SPLITS:
            continue
        bases = [meta(occurrences[b['representative']]) for b in q['bases']]
        check([b['object_id'] for b in bases] == [b['object_id'] for b in q['bases']], 'representative mismatch')
        out.append({'target_occurrence_id': q['target'], 'family_id': target['family_id'], 'track': target['track'],
                    'split': target['split'], 'target': meta(target), 'bases': bases})
    return sorted(out, key=lambda q: q['target_occurrence_id'])


def natural_universe():
    import oracle_materialize as om
    candidate, corpus, _, _ = om.load_natural()
    plan = json.loads((WORK / 'corpus' / 'source-plan.json').read_bytes())
    return universe(candidate, corpus, plan)


# --- metadata methods -------------------------------------------------------------------------------------------

def _gap(q, b):
    return abs(b['bytes'] - q['target']['bytes'])


def rank_random(q, seed=None):
    seed = PARAMS['random_seed'] if seed is None else seed
    tid = q['target']['object_id']
    return [b['object_id'] for b in sorted(
        q['bases'], key=lambda b: (hashlib.sha256(f"{seed}:{tid}:{b['object_id']}".encode()).hexdigest(),
                                   b['object_id']))]


def rank_size_closest(q):
    return [b['object_id'] for b in sorted(q['bases'], key=lambda b: (_gap(q, b), b['object_id']))]


def rank_previous_version(q):
    """Same member path first (nearest offset, then the latest earlier release), then size-closest. Uses only what a
    deployment that knows file paths and release order has; for whole-archive tracks there is no path."""
    t = q['target']

    def key(b):
        same = t['path'] is not None and b['path'] == t['path']
        if same:
            return (0, abs((b['offset'] or 0) - (t['offset'] or 0)), -b['ordinal'], _gap(q, b), b['object_id'])
        return (1, 0, 0, _gap(q, b), b['object_id'])
    return [b['object_id'] for b in sorted(q['bases'], key=key)]


def git_name_hash(path):
    """git pack_name_hash (name-hash version 1): later characters weigh most, whitespace skipped."""
    h = 0
    for c in path.encode('utf-8'):
        if c in b' \t\n\r\x0b\x0c':
            continue
        h = ((h >> 2) + (c << 24)) & 0xffffffff
    return h


def rank_git_like(q):
    """PROXY of git's delta-base heuristic: candidates with the target's name hash first, then size-closest. Not
    `git pack-objects`; window and type ordering of git are not reproduced."""
    t = q['target']
    th = git_name_hash(t['path']) if t['path'] is not None else None

    def key(b):
        same = th is not None and b['path'] is not None and git_name_hash(b['path']) == th
        return (0 if same else 1, _gap(q, b), b['object_id'])
    return [b['object_id'] for b in sorted(q['bases'], key=key)]


METADATA_METHODS = {'random': rank_random, 'size_closest': rank_size_closest,
                    'previous_version': rank_previous_version, 'git_like': rank_git_like}


# --- content methods: bottom-k MinHash over byte shingles -----------------------------------------------------

def sketch(data, k=None, n=None, seed=None):
    """Bottom-k (k smallest distinct) splitmix64-mixed hashes of all n-byte shingles, ascending. Bottom-k sketches
    are nested: the first k' values are the bottom-k' sketch, so one pass serves every budget."""
    k = PARAMS['budgets_bytes'][-1] // PARAMS['hash_bytes'] if k is None else k
    n = PARAMS['shingle_bytes'] if n is None else n
    seed = PARAMS['sketch_seed'] if seed is None else seed
    check(n == 8, 'shingle mixer is defined for 8-byte shingles')
    if len(data) < n:
        windows = [int.from_bytes(data, 'big')] if data else []
    else:
        windows = None
    heap, members, threshold = [], set(), M64 + 1

    def offer(w):
        nonlocal threshold
        z = (w ^ seed) & M64
        z = ((z ^ (z >> 30)) * 0xbf58476d1ce4e5b9) & M64
        z = ((z ^ (z >> 27)) * 0x94d049bb133111eb) & M64
        z ^= z >> 31
        if z < threshold and z not in members:
            if len(heap) < k:
                heapq.heappush(heap, -z)
            else:
                members.discard(-heapq.heappushpop(heap, -z))
            members.add(z)
            if len(heap) == k:
                threshold = -heap[0]
    if windows is not None:
        for w in windows:
            offer(w)
        return sorted(members)
    w = int.from_bytes(data[:n - 1], 'big')
    s, c1, c2 = seed, 0xbf58476d1ce4e5b9, 0x94d049bb133111eb
    for byte in data[n - 1:]:
        w = ((w << 8) | byte) & M64
        z = w ^ s
        z = ((z ^ (z >> 30)) * c1) & M64
        z = ((z ^ (z >> 27)) * c2) & M64
        z ^= z >> 31
        if z < threshold and z not in members:
            if len(heap) < k:
                heapq.heappush(heap, -z)
            else:
                members.discard(-heapq.heappushpop(heap, -z))
            members.add(z)
            if len(heap) == k:
                threshold = -heap[0]
    return sorted(members)


def distinct_estimate(hashes, k):
    """KMV estimate of the number of distinct shingles from a bottom-k prefix; exact when fewer than k exist."""
    if len(hashes) < k:
        return float(len(hashes))
    return (k - 1) * float(1 << 64) / (hashes[k - 1] + 1)


def resemblance(a, b, k):
    """Bottom-k Jaccard estimate: share of the k smallest union hashes present in both sketches."""
    sa, sb = set(a[:k]), set(b[:k])
    union = sorted(sa | sb)[:k]
    return sum(1 for x in union if x in sa and x in sb) / len(union) if union else 0.0


def containment(target, base, k):
    """Target-normalized containment |S_t ∩ S_b| / |S_t| from the Jaccard estimate and KMV set sizes, in [0, 1]."""
    j = resemblance(target, base, k)
    nt, nb = distinct_estimate(target, k), distinct_estimate(base, k)
    if nt == 0:
        return 0.0
    return min(1.0, j * (nt + nb) / ((1 + j) * nt))


def rank_content(q, sketches, method, k):
    t = sketches[q['target']['object_id']]
    score = resemblance if method == 'minhash_resemblance' else containment
    return [b['object_id'] for b in sorted(
        q['bases'], key=lambda b: (-score(t, sketches[b['object_id']], k), _gap(q, b), b['object_id']))]


# --- ranking stage (natural bytes, Actions) ------------------------------------------------------------------

def read_object(store, object_id, size):
    path = Path(store) / object_id
    check(path.is_file() and not path.is_symlink(), f'object missing: {object_id}')
    data = path.read_bytes()
    check(len(data) == size and hashlib.sha256(data).hexdigest() == object_id, f'object integrity: {object_id}')
    return data


def rank_all(queries, store):
    """Rankings of every (method, budget) for every query, plus construction costs of the content descriptors."""
    objects = {}
    for q in queries:
        for meta in (q['target'], *q['bases']):
            objects[meta['object_id']] = meta['bytes']
    started, sketches = time.process_time(), {}
    for oid, size in sorted(objects.items()):
        sketches[oid] = sketch(read_object(store, oid, size))
    sketch_seconds = time.process_time() - started
    rows = []
    for q in queries:
        base = {'schema': RANKINGS_SCHEMA, 'target_occurrence_id': q['target_occurrence_id'],
                'family_id': q['family_id'], 'track': q['track'], 'split': q['split']}
        for method, fn in METADATA_METHODS.items():
            rows.append({**base, 'method': method, 'budget_bytes': None, 'ranking': fn(q)})
        for method in CONTENT_METHODS:
            for budget in PARAMS['budgets_bytes']:
                k = budget // PARAMS['hash_bytes']
                rows.append({**base, 'method': method, 'budget_bytes': budget,
                             'ranking': rank_content(q, sketches, method, k)})
    costs = {'objects': len(objects), 'object_bytes': sum(objects.values()),
             'sketch_cpu_seconds': round(sketch_seconds, 3),
             'max_descriptor_bytes_per_object': PARAMS['budgets_bytes'][-1]}
    return rows, costs


# --- evaluation against the oracle ------------------------------------------------------------------------------

def load_oracle(bundle):
    """Unsealed target rows and D_E of every unsealed pair; sealed (evaluation) rows are skipped, never opened."""
    bundle = Path(bundle)
    targets = {r['target_occurrence_id']: r for r in jsonl(bundle / 'targets.jsonl')
               if r['schema'] == 'delsk.oracle.target.v1'}
    pairs = {}
    for r in jsonl(bundle / 'pairs.jsonl'):
        if r['schema'] != 'delsk.oracle.pair.v1':
            continue
        key = (r['target_occurrence_id'], r['base_object_id'])
        check(key not in pairs, 'duplicate oracle pair')
        pairs[key] = r['delta_total_bytes'] if r['status'] == 'ok' else None
    return targets, pairs


def quantile(values, p):
    """Hyndman-Fan type 7 (linear) quantile; None for an empty population."""
    xs = sorted(values)
    if not xs:
        return None
    h = (len(xs) - 1) * p
    lo = math.floor(h)
    return xs[lo] + (h - lo) * (xs[min(lo + 1, len(xs) - 1)] - xs[lo])


def target_rows(ranking_row, targets, pairs):
    """Protocol 2-3 for one ranking: one row per K of the grid."""
    tid = ranking_row['target_occurrence_id']
    t = targets.get(tid)
    check(t is not None and t['split'] in SPLITS and t['query_status'] == 'near_duplicate', f'target not evaluable: {tid}')
    universe_ids = sorted(b for (q, b) in pairs if q == tid)
    ranking = ranking_row['ranking']
    check(sorted(ranking) == universe_ids and len(set(ranking)) == len(ranking), f'ranking is not C_t: {tid}')
    d = {b: pairs[(tid, b)] for b in ranking}
    finite = [v for v in d.values() if v is not None]
    s, o, od = t['standalone_total_bytes'], t['oracle_total_bytes'], t['oracle_delta_total_bytes']
    check((min(finite) if finite else None) == od, f'oracle delta minimum differs from pairs: {tid}')
    check(o == (min(s, od) if od is not None else s), f'oracle total inconsistent: {tid}')
    ties = set(t['oracle_tie_bases'])
    check(ties == {b for b, v in d.items() if v is not None and v == od}, f'oracle tie set differs: {tid}')
    rows = []
    for k in K_GRID:
        chosen = ranking[:k]
        values = [d[b] for b in chosen if d[b] is not None]
        a = min([s, *values])
        floor = PARAMS['epsilon_floor_bytes']
        rows.append({
            'schema': ROW_SCHEMA, 'target_occurrence_id': tid, 'family_id': t['family_id'], 'track': t['track'],
            'split': t['split'], 'method': ranking_row['method'], 'budget_bytes': ranking_row['budget_bytes'], 'k': k,
            'candidates': len(ranking), 'encodes': len(chosen), 'standalone_bytes': s, 'oracle_bytes': o,
            'oracle_delta_bytes': od, 'selected_bytes': a, 'finite_delta': od is not None,
            'useful_delta': od is not None and od < s,
            'strict_hit': od is not None and bool(set(chosen) & ties),
            'epsilon_hits': {str(e): od is not None and any(v <= od + max(floor, e * od) for v in values)
                             for e in PARAMS['epsilons']},
            'regret_bytes': a - o,
            'normalized_regret': (a - o) / max(o, PARAMS['normalized_regret_floor_bytes'])})
    return rows


def _ratio(num, den):
    return None if den == 0 else num / den


def aggregate(rows):
    """Protocol 3 metrics of one population of target rows (one method, budget, K and split)."""
    finite = [r for r in rows if r['finite_delta']]
    useful = [r for r in rows if r['useful_delta']]
    saved_oracle = sum(r['standalone_bytes'] - r['oracle_bytes'] for r in rows)
    out = {
        'targets': len(rows), 'finite_delta_targets': len(finite), 'useful_delta_targets': len(useful),
        'strict_recall': _ratio(sum(r['strict_hit'] for r in finite), len(finite)),
        'useful_recall': _ratio(sum(r['strict_hit'] for r in useful), len(useful)),
        'epsilon_recall': {e: _ratio(sum(r['epsilon_hits'][e] for r in finite), len(finite))
                           for e in (str(x) for x in PARAMS['epsilons'])},
        'regret_bytes_p50': quantile([r['regret_bytes'] for r in rows], 0.5),
        'regret_bytes_p95': quantile([r['regret_bytes'] for r in rows], 0.95),
        'normalized_regret_p50': quantile([r['normalized_regret'] for r in rows], 0.5),
        'normalized_regret_p95': quantile([r['normalized_regret'] for r in rows], 0.95),
        'savings_capture': _ratio(sum(r['standalone_bytes'] - r['selected_bytes'] for r in rows), saved_oracle),
        'encoder_call_reduction': _ratio(sum(r['candidates'] for r in rows), sum(r['encodes'] for r in rows)),
    }
    families = sorted({r['family_id'] for r in rows})
    per_family = {f: aggregate_flat([r for r in rows if r['family_id'] == f]) for f in families}
    out['macro_useful_recall'] = _mean([v['useful_recall'] for v in per_family.values()])
    out['macro_savings_capture'] = _mean([v['savings_capture'] for v in per_family.values()])
    return out


def aggregate_flat(rows):
    useful = [r for r in rows if r['useful_delta']]
    saved_oracle = sum(r['standalone_bytes'] - r['oracle_bytes'] for r in rows)
    return {'useful_recall': _ratio(sum(r['strict_hit'] for r in useful), len(useful)),
            'savings_capture': _ratio(sum(r['standalone_bytes'] - r['selected_bytes'] for r in rows), saved_oracle)}


def _mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def bootstrap(rows, draws=None, seed=None):
    """Cluster bootstrap over lineages (families): 95% intervals of SavingsCapture and Useful Recall."""
    draws = PARAMS['bootstrap']['draws'] if draws is None else draws
    seed = PARAMS['bootstrap']['seed'] if seed is None else seed
    by_family = {}
    for r in rows:
        by_family.setdefault(r['family_id'], []).append(r)
    families = sorted(by_family)
    rng = random.Random(seed)
    stats = {'savings_capture': [], 'useful_recall': []}
    for _ in range(draws):
        sample = [r for _ in families for r in by_family[rng.choice(families)]]
        flat = aggregate_flat(sample)
        for key in stats:
            if flat[key] is not None:
                stats[key].append(flat[key])
    return {key: {'ci95': [quantile(v, 0.025), quantile(v, 0.975)] if v else None, 'defined_draws': len(v)}
            for key, v in stats.items()} | {'lineages': len(families), 'exploratory': len(families) < 10}


def evaluate(rankings, bundle):
    targets, pairs = load_oracle(bundle)
    rows = [row for r in rankings for row in target_rows(r, targets, pairs)]
    expected = {tid for tid, t in targets.items() if t['split'] in SPLITS and t['query_status'] == 'near_duplicate'}
    groups = {}
    for r in rows:
        groups.setdefault((r['method'], r['budget_bytes'], r['k'], r['split']), []).append(r)
    summary = []
    for (method, budget, k, split), group in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1] or 0,
                                                                                   kv[0][2], kv[0][3])):
        check({r['target_occurrence_id'] for r in group} == {t for t in expected if targets[t]['split'] == split}
              and len(group) == len({r['target_occurrence_id'] for r in group}),
              f'population incomplete: {method} {budget} K={k} {split}')
        summary.append({'method': method, 'budget_bytes': budget, 'k': k, 'split': split, **aggregate(group),
                        'bootstrap': bootstrap(group)})
    return rows, summary, best_on_calibration(summary)


def best_on_calibration(summary, k=8):
    """Preregistered selection of the strongest baseline for the primary contrast: highest calibration
    SavingsCapture at K=8; ties by smaller descriptor budget, then method name."""
    cands = [s for s in summary if s['split'] == 'calibration' and s['k'] == k and s['savings_capture'] is not None]
    if not cands:
        return None
    best = sorted(cands, key=lambda s: (-s['savings_capture'], s['budget_bytes'] or 0, s['method']))[0]
    return {'method': best['method'], 'budget_bytes': best['budget_bytes'], 'k': k,
            'savings_capture': best['savings_capture']}


# --- CLI --------------------------------------------------------------------------------------------------------

def materialize(store):
    import oracle_materialize as om
    candidate, corpus, sources, policy = om.load_natural()
    provenance = om.materialize_store(store, candidate, corpus, sources, policy)
    verification = om.verify_store(store, om.expected_objects(candidate, corpus))
    return {'schema': 'delsk.baselines.materialization.v1', 'provenance': provenance, 'verification': verification}


def main(argv):
    command, args = (argv[0], argv[1:]) if argv else (None, [])
    if command == 'materialize' and len(args) == 1:
        doc = materialize(args[0])
        print(json.dumps(doc['verification'], sort_keys=True))
        return 0
    if command == 'rank' and len(args) == 2:
        out = Path(args[1])
        out.mkdir(parents=True, exist_ok=True)
        rows, costs = rank_all(natural_universe(), args[0])
        write_jsonl(out / 'rankings.jsonl', rows)
        (out / 'costs.json').write_text(json.dumps({**costs, 'params_sha256': params_sha256()}, sort_keys=True,
                                                   indent=2) + '\n')
        print(json.dumps(costs, sort_keys=True))
        return 0
    if command == 'evaluate' and len(args) == 3:
        out = Path(args[2])
        out.mkdir(parents=True, exist_ok=True)
        rows, summary, best = evaluate(jsonl(args[0]), args[1])
        write_jsonl(out / 'rows.jsonl', rows)
        doc = {'schema': SUMMARY_SCHEMA, 'contract': PARAMS['contract'], 'params_sha256': params_sha256(),
               'oracle_bundle': Path(args[1]).name, 'summary': summary, 'best_on_calibration': best}
        (out / 'summary.json').write_text(json.dumps(doc, sort_keys=True, indent=2) + '\n')
        print(json.dumps(best, sort_keys=True))
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
