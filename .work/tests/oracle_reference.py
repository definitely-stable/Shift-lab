"""Test-only reference of delsk.oracle-contract.v1 (DELSK-003 Slice A): accounting, oracle and evaluator rules.

Slow and literal on purpose. It exists only to prove that the known-answer vectors in .work/oracle/known-answer.json
are consistent with the frozen contract and that they kill the mutants of its section 11. It is NOT the production
evaluator: the Slice B evaluator must be written independently, must not import this module, and must reproduce the
same vector outcomes. No codec is invoked here; rows are synthetic. Contract prose: .work/oracle/contract.md.
"""
from fractions import Fraction
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import manifests as m

BASE_REFERENCE_BYTES = 32  # raw SHA-256 object ID of the base (contract section 3)
CODEC_METADATA_BYTES = 0
TOLERANCE_FLOOR = 64
EPSILON_PERCENT = (1, 2, 5)
PAIR_STATUSES = ('ok', 'timeout', 'codec_error', 'resource_limit', 'decode_mismatch', 'input_integrity', 'not_run')
BOUNDED = {'timeout', 'codec_error', 'resource_limit'}
FATAL = {'decode_mismatch': 'DECODE_MISMATCH', 'input_integrity': 'INPUT_INTEGRITY'}
SEALED = {'delsk.oracle.pair-sealed.v1', 'delsk.oracle.standalone-sealed.v1'}
TIMING_FIELDS = ('encode_wall_ns', 'decode_wall_ns', 'encode_peak_rss_bytes', 'decode_peak_rss_bytes',
                 'compress_wall_ns', 'decompress_wall_ns')
# Fields a reveal run cannot reproduce: run timings and the measurement identity of the publishing run.
RUN_SPECIFIC = (*TIMING_FIELDS, 'measurement_identity_sha256', 'measured_source_sha')
COST_FIELDS = ('patch_payload_bytes', 'patch_sha256', 'wrapper_bytes', 'base_reference_bytes', 'codec_metadata_bytes',
               'delta_total_bytes', 'decoded_bytes', 'decoded_sha256')
IDENTITY_FIELDS = ('measurement_identity_sha256', 'measured_source_sha', 'corpus_lock_sha256', 'candidate_lock_sha256')


# --- frame v1 accounting (contract section 3) -----------------------------------------------------------------------

def uleb128_len(n):
    k = 1
    while n >= 128:
        n >>= 7
        k += 1
    return k


def wrapper_bytes(payload):
    return 1 + uleb128_len(payload)


def raw_total(n):
    return n + wrapper_bytes(n)


def standalone_total(payload):
    return payload + wrapper_bytes(payload) + CODEC_METADATA_BYTES


def delta_total(payload):
    return payload + wrapper_bytes(payload) + BASE_REFERENCE_BYTES + CODEC_METADATA_BYTES


def pair_id(codec_id, target, base):
    return m.digest(['delsk.oracle.pair.v1', codec_id, target, base])


def commitment(row):
    """row_sha256 of a sealed row: Hc of the full row without run-specific fields (contract section 9.1)."""
    return m.digest({k: v for k, v in row.items() if k not in RUN_SPECIFIC})


def jsonl_sha256(rows, drop=()):
    rows = sorted(({k: v for k, v in r.items() if k not in drop} for r in rows),
                  key=lambda r: (r['target_occurrence_id'], r.get('base_object_id', '')))
    text = ''.join(json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n' for r in rows)
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def quantile7(values, p):
    """Hyndman-Fan type 7 on exact rationals; p is a Fraction."""
    xs = sorted(values)
    h = (len(xs) - 1) * p
    lo = h.numerator // h.denominator
    if lo + 1 >= len(xs):
        return xs[lo]
    return xs[lo] + (h - lo) * (xs[lo + 1] - xs[lo])


def ratio(num, den):
    return None if den == 0 else Fraction(num, den)


# --- oracle run validation and derivation (contract sections 4-7) ---------------------------------------------------

def evaluate(world, standalone_rows, pair_rows, retrieval=None):
    """world: identity, codec, standalone_codec, facts{target: object_id, bytes, split}, base_bytes{base: n},
    queries[{target, status, bases[{object_id, representative}]}], sealed_splits. Returns a plain dict."""
    ident, queries = world['identity'], {q['target']: q for q in world['queries']}
    sealed_splits, reasons = set(world['sealed_splits']), set()
    near = sorted(t for t, q in queries.items() if q['status'] == 'near_duplicate')
    expected = {(t, b['object_id']): b for t in near for b in queries[t]['bases']}

    def common(row, codec, fact):
        if any(row[f] != ident[f] for f in IDENTITY_FIELDS) or row['codec_id'] != codec['codec_id']:
            reasons.add('IDENTITY_MISMATCH')
        elif row['options_sha256'] != codec['options_sha256']:
            reasons.add('OPTIONS_MISMATCH')
        if row['split'] != fact['split']:
            reasons.add('LOCK_FIELD_MISMATCH')
        if (row['schema'] in SEALED) != (fact['split'] in sealed_splits):
            reasons.add('SEALING_VIOLATION')
        if row['status'] in FATAL:
            reasons.add(FATAL[row['status']])

    seen = {}
    for row in pair_rows:
        key = (row['target_occurrence_id'], row['base_object_id'])
        if key not in expected:
            reasons.add('FOREIGN_PAIR')
            continue
        if key in seen:
            reasons.add('DUPLICATE_PAIR')
            continue
        seen[key] = row
        fact = world['facts'][key[0]]
        if row['pair_id'] != pair_id(world['codec']['codec_id'], *key):
            reasons.add('PAIR_ID_MISMATCH')
        common(row, world['codec'], fact)
        if row['schema'] in SEALED:
            if row['status'] == 'ok' and row['decoded_sha256'] != fact['object_id']:
                reasons.add('DECODE_MISMATCH')
            continue
        if (row['target_object_id'], row['target_bytes'], row['base_representative'], row['base_bytes']) != \
                (fact['object_id'], fact['bytes'], expected[key]['representative'], world['base_bytes'][key[1]]):
            reasons.add('LOCK_FIELD_MISMATCH')
        if row['status'] != 'ok':
            if any(row[f] is not None for f in COST_FIELDS):
                reasons.add('INCONSISTENT_ROW')
            continue
        if any(row[f] is None for f in COST_FIELDS):
            reasons.add('INCONSISTENT_ROW')
            continue
        p = row['patch_payload_bytes']
        if (row['wrapper_bytes'], row['base_reference_bytes'], row['codec_metadata_bytes'], row['delta_total_bytes']) \
                != (wrapper_bytes(p), BASE_REFERENCE_BYTES, CODEC_METADATA_BYTES, delta_total(p)):
            reasons.add('ACCOUNTING_MISMATCH')
        if row['decoded_bytes'] != fact['bytes'] or row['decoded_sha256'] != fact['object_id']:
            reasons.add('DECODE_MISMATCH')

    standalone = {}
    for row in standalone_rows:
        t = row['target_occurrence_id']
        if t not in queries:
            reasons.add('FOREIGN_STANDALONE')
            continue
        if t in standalone:
            reasons.add('DUPLICATE_STANDALONE')
            continue
        standalone[t] = row
        fact = world['facts'][t]
        common(row, world['standalone_codec'], fact)
        if row['schema'] in SEALED:
            continue
        if (row['target_object_id'], row['target_bytes']) != (fact['object_id'], fact['bytes']):
            reasons.add('LOCK_FIELD_MISMATCH')
        if row['raw_total_bytes'] != raw_total(row['target_bytes']):
            reasons.add('ACCOUNTING_MISMATCH')
        if row['status'] != 'ok':
            if row['compressed_payload_bytes'] is not None:
                reasons.add('INCONSISTENT_ROW')
            continue
        c = row['compressed_payload_bytes']
        if c is None:
            reasons.add('INCONSISTENT_ROW')
        elif row['decoded_sha256'] != fact['object_id']:
            reasons.add('DECODE_MISMATCH')
        elif row['compressed_total_bytes'] != standalone_total(c):
            reasons.add('ACCOUNTING_MISMATCH')

    out = {'invalid_reasons': sorted(reasons), 'coverage': None, 'targets': None, 'metrics': None,
           'retrieval_status': 'NOT_EVALUATED', 'retrieval_reasons': []}
    if reasons:
        out['run_status'] = 'INVALID'
        return out

    counts = {s: 0 for s in PAIR_STATUSES}
    for row in seen.values():
        counts[row['status']] += 1
    sealed_t = sorted(t for t in queries if world['facts'][t]['split'] in sealed_splits)
    coverage = {'expected_pairs': len(expected), 'ok': counts['ok'], 'timeout': counts['timeout'],
                'codec_error': counts['codec_error'], 'resource_limit': counts['resource_limit'],
                'missing': len(expected) - len(seen) + counts['not_run'],
                'sealed_pairs': sum(r['schema'] in SEALED for r in seen.values()),
                'near_targets': len(near), 'identity_targets': len(queries) - len(near),
                'sealed_targets': len(sealed_t),
                'standalone_missing': sum(t not in standalone or standalone[t]['status'] == 'not_run' for t in queries),
                'standalone_failed': sum(r['status'] in BOUNDED for r in standalone.values())}
    out['coverage'] = coverage
    if coverage['missing'] or coverage['standalone_missing']:
        out['run_status'] = 'INCOMPLETE'
        return out
    failed = counts['timeout'] + counts['codec_error'] + counts['resource_limit'] + coverage['standalone_failed']
    out['run_status'] = 'COMPLETE_WITH_FAILURES' if failed else 'COMPLETE'
    out['oracle_kind'] = 'exhaustive' if not failed else 'bounded'

    targets, cost = {}, {}
    for t, q in queries.items():
        if t in sealed_t:
            targets[t] = {'sealed': True}
            continue
        row = standalone[t]
        raw = row['raw_total_bytes']
        comp = row['compressed_total_bytes'] if row['status'] == 'ok' else None
        s = raw if comp is None or raw <= comp else comp
        finite = {b['object_id']: seen[(t, b['object_id'])]['delta_total_bytes'] for b in q['bases']
                  if seen[(t, b['object_id'])]['status'] == 'ok'}
        cost[t] = finite
        od = min(finite.values()) if finite else None
        status = ('identity_only' if q['status'] == 'identity_only' else 'finite' if finite
                  else 'empty_candidate_set' if not q['bases'] else 'all_pairs_failed')
        useful = od is not None and od < s
        targets[t] = {'S': s, 'S_choice': 'raw' if s == raw else 'compressed', 'O_delta': od, 'delta_status': status,
                      'ties': sorted(b for b, c in finite.items() if c == od), 'O': od if useful else s,
                      'useful': useful}
    out['targets'] = targets
    for key, test in (('near_empty', lambda v: v.get('delta_status') == 'empty_candidate_set'),
                      ('near_all_failed', lambda v: v.get('delta_status') == 'all_pairs_failed'),
                      ('near_finite', lambda v: v.get('delta_status') == 'finite'),
                      ('near_useful', lambda v: v.get('useful') is True)):
        coverage[key] = sum(test(targets[t]) for t in near)
    unsealed = [r for r in pair_rows if r['schema'] not in SEALED]
    out['pairs_canonical_sha256'] = jsonl_sha256(unsealed)
    out['cost_projection_sha256'] = jsonl_sha256(unsealed, TIMING_FIELDS)
    if retrieval is not None:
        evaluate_retrieval(out, queries, [t for t in near if t not in sealed_t], cost, retrieval)
    return out


# --- metric evaluator (contract section 8) --------------------------------------------------------------------------

def evaluate_retrieval(out, queries, scored, cost, retrieval):
    targets, rows, k, reasons = out['targets'], retrieval['rows'], retrieval['K'], set()
    by_target = {}
    for row in rows:
        if row['target_occurrence_id'] in by_target:
            reasons.add('RETRIEVAL_COVERAGE')
        by_target[row['target_occurrence_id']] = row
    if set(by_target) != set(scored):
        reasons.add('RETRIEVAL_COVERAGE')
    for t, row in by_target.items():
        allowed = {b['object_id'] for b in queries[t]['bases']} if t in queries else set()
        bases = row['bases']
        if len(set(bases)) != len(bases):
            reasons.add('RETRIEVAL_DUPLICATE_BASE')
        if not set(bases) <= allowed:
            reasons.add('RETRIEVAL_FOREIGN_BASE')
        if len(bases) > k:
            reasons.add('RETRIEVAL_OVER_K')
        if row['encode_calls'] < len(bases):
            reasons.add('RETRIEVAL_CALLS')
    out['retrieval_reasons'] = sorted(reasons)
    if reasons:
        out['retrieval_status'] = 'INVALID'
        return
    out['retrieval_status'] = 'OK'
    finite = [t for t in scored if targets[t]['delta_status'] == 'finite']
    useful = [t for t in finite if targets[t]['useful']]
    hit, eps, achieved = {}, {e: 0 for e in EPSILON_PERCENT}, {}
    for t in scored:
        tr = targets[t]
        costs = [cost[t][b] for b in by_target[t]['bases'] if b in cost[t]]
        achieved[t] = min([tr['S'], *costs])
        if t in finite:
            hit[t] = bool(set(by_target[t]['bases']) & set(tr['ties']))
            od = tr['O_delta']
            for e in EPSILON_PERCENT:
                eps[e] += any(100 * c <= 100 * od + max(100 * TOLERANCE_FLOOR, e * od) for c in costs)
    regret = {t: achieved[t] - targets[t]['O'] for t in scored}
    nregret = {t: Fraction(regret[t], max(targets[t]['O'], TOLERANCE_FLOOR)) for t in scored}

    def dist(pop, values):
        xs = [values[t] for t in pop]
        if not xs:
            return {'sum': None, 'p50': None, 'p95': None, 'max': None}
        return {'sum': sum(xs), 'p50': quantile7(xs, Fraction(1, 2)), 'p95': quantile7(xs, Fraction(19, 20)),
                'max': max(xs)}

    calls = sum(by_target[t]['encode_calls'] for t in scored)
    out['metrics'] = {
        'strict': ratio(sum(hit[t] for t in finite), len(finite)),
        'useful': ratio(sum(hit[t] for t in useful), len(useful)),
        **{f'eps{e}': ratio(eps[e], len(finite)) for e in EPSILON_PERCENT},
        'savings_capture': ratio(sum(targets[t]['S'] - achieved[t] for t in scored),
                                 sum(targets[t]['S'] - targets[t]['O'] for t in scored)),
        'call_reduction': ratio(sum(len(queries[t]['bases']) for t in scored), calls),
        'regret_near': dist(scored, regret), 'nregret_near': dist(scored, nregret),
        'regret_useful': dist(useful, regret), 'nregret_useful': dist(useful, nregret),
    }


def g1(runs):
    """G1 over all attempts of one measurement identity (contract section 7)."""
    if any(r['run_status'] == 'INVALID' for r in runs):
        return 'INVALID', ['RUN_INVALID']
    complete = [r for r in runs if r['run_status'] == 'COMPLETE']
    if len({(r['cost_projection_sha256'], r['targets_sha256']) for r in complete}) > 1:
        return 'INVALID', ['REPEAT_MISMATCH']
    blockers = sorted({f'RUN_{r["run_status"]}' for r in runs if r['run_status'] != 'COMPLETE'})
    good = [r for r in complete if r['conformance'] and r['bundle_verified']]
    if len(good) < len(complete):
        blockers.append('CONFORMANCE_OR_BUNDLE')
    if len({r['github_run_id'] for r in good}) < 2:
        blockers.append('REPEAT_MISSING')
    return ('PASS', []) if not blockers else ('NOT_PASSED', blockers)


# --- known-answer expansion (contract section 10) -------------------------------------------------------------------

def occ(label):
    return m.digest(['delsk.oracle.kat.v1', 'occurrence', label])


def obj(label):
    return m.digest(['delsk.oracle.kat.v1', 'object', label])


DEFAULT_ERROR = {'timeout': 'wall_timeout', 'codec_error': 'nonzero_exit', 'resource_limit': 'address_space',
                 'decode_mismatch': 'bytes_mismatch', 'input_integrity': 'base_integrity', 'not_run': 'runner_abort'}


def expand(case, codec_lock):
    """Compact vector -> (world, standalone rows, pair rows, retrieval) in full durable row form."""
    ident = {'measured_source_sha': 'a' * 40, 'corpus_lock_sha256': m.digest(['delsk.oracle.kat.v1', 'corpus']),
             'candidate_lock_sha256': m.digest(['delsk.oracle.kat.v1', 'candidate'])}
    ident['measurement_identity_sha256'] = m.digest(['delsk.oracle.kat.v1', 'identity', ident])
    codec, zstd = ({'codec_id': c['codec_id'], 'options_sha256': c['options_sha256']}
                   for c in (codec_lock['codecs']['delta'], codec_lock['codecs']['standalone']))
    sizes = {s['t']: s['raw'] for s in case['standalone']}
    split = {q['t']: q.get('split', 'development') for q in case['queries']}
    status = {q['t']: q['status'] for q in case['queries']}
    labels = {q['t'] for q in case['queries']} | set(sizes) | {p['t'] for p in case['pairs']}
    facts = {occ(t): {'object_id': obj(t), 'bytes': sizes.get(t, 4096), 'split': split.get(t, 'development')}
             for t in labels}
    sealed_splits = case.get('sealed_splits', [])
    world = {'identity': ident, 'codec': codec, 'standalone_codec': zstd, 'facts': facts,
             'sealed_splits': sealed_splits,
             'base_bytes': {obj(b): 4096 for b in {b for q in case['queries'] for b in q['bases']}
                            | {p['b'] for p in case['pairs']}},
             'queries': [{'target': occ(q['t']), 'status': q['status'],
                          'bases': [{'object_id': obj(b), 'representative': occ(b)} for b in sorted(q['bases'])]}
                         for q in case['queries']]}

    def seal(row, keys):
        return {'schema': row['schema'].replace('.v1', '-sealed.v1'), **{k: row[k] for k in keys},
                **({'decoded_sha256': row['decoded_sha256']} if 'base_object_id' in keys else {}),
                'row_sha256': commitment(row)}

    hide = set() if case.get('leak') else set(sealed_splits)  # 'leak': rows of a sealed split stay unsealed
    common = (*IDENTITY_FIELDS, 'codec_id', 'options_sha256', 'target_occurrence_id', 'split', 'status',
              'failure_phase', 'error_class')
    pairs = []
    for p in case['pairs']:
        t, b, fact = occ(p['t']), obj(p['b']), facts[occ(p['t'])]
        ok, n = p['status'] == 'ok', p.get('payload')
        row = {'schema': 'delsk.oracle.pair.v1', **ident, **codec, 'pair_id': pair_id(codec['codec_id'], t, b),
               'target_occurrence_id': t, 'target_object_id': fact['object_id'], 'target_bytes': fact['bytes'],
               'base_object_id': b, 'base_representative': occ(p['b']), 'base_bytes': 4096, 'split': fact['split'],
               'status': p['status'], 'failure_phase': None if ok else 'encode',
               'error_class': None if ok else DEFAULT_ERROR[p['status']],
               'encode_exit': 0 if ok else None, 'encode_signal': None, 'decode_exit': 0 if ok else None,
               'decode_signal': None, 'patch_payload_bytes': n if ok else None,
               'patch_sha256': m.digest(['delsk.oracle.kat.v1', 'patch', p['t'], p['b'], n]) if ok else None,
               'wrapper_bytes': wrapper_bytes(n) if ok else None,
               'base_reference_bytes': BASE_REFERENCE_BYTES if ok else None,
               'codec_metadata_bytes': CODEC_METADATA_BYTES if ok else None,
               'delta_total_bytes': delta_total(n) if ok else None,
               'decoded_bytes': fact['bytes'] if ok else None, 'decoded_sha256': fact['object_id'] if ok else None,
               'encode_wall_ns': 1000 if ok else None, 'decode_wall_ns': 1000 if ok else None,
               'encode_peak_rss_bytes': 1 << 20 if ok else None, 'decode_peak_rss_bytes': 1 << 20 if ok else None}
        if p['status'] == 'timeout':
            row['encode_signal'] = 9
        elif p['status'] == 'codec_error':
            row['encode_exit'] = 1
        elif p['status'] == 'decode_mismatch':
            row.update(failure_phase='decode', encode_exit=0, decode_exit=0)
        elif p['status'] == 'input_integrity':
            row['failure_phase'] = 'materialize'
        row.update(p.get('set', {}))
        pairs.append(seal(row, (*common, 'pair_id', 'base_object_id')) if fact['split'] in hide else row)
    standalone_rows = []
    for s in case['standalone']:
        t, fact = occ(s['t']), facts[occ(s['t'])]
        st = s.get('status', 'ok')
        ok, c = st == 'ok', s.get('compressed')
        row = {'schema': 'delsk.oracle.standalone.v1', **ident, **zstd, 'target_occurrence_id': t,
               'target_object_id': fact['object_id'], 'target_bytes': fact['bytes'], 'split': fact['split'],
               'query_status': status.get(s['t'], 'near_duplicate'),
               'raw_total_bytes': raw_total(fact['bytes']), 'status': st,
               'failure_phase': None if ok else 'encode', 'error_class': None if ok else DEFAULT_ERROR[st],
               'compress_exit': 0 if ok else None, 'compress_signal': 9 if st == 'timeout' else None,
               'decompress_exit': 0 if ok else None, 'decompress_signal': None,
               'compressed_payload_bytes': c if ok else None,
               'compressed_sha256': m.digest(['delsk.oracle.kat.v1', 'zstd', s['t'], c]) if ok else None,
               'compressed_wrapper_bytes': wrapper_bytes(c) if ok else None,
               'compressed_total_bytes': standalone_total(c) if ok else None,
               'decoded_sha256': fact['object_id'] if ok else None,
               'compress_wall_ns': 1000 if ok else None, 'decompress_wall_ns': 1000 if ok else None}
        row.update(s.get('set', {}))
        standalone_rows.append(seal(row, (*common, 'query_status')) if fact['split'] in hide else row)
    retrieval = None
    if case.get('retrieval') is not None:
        r = case['retrieval']
        retrieval = {'method_id': 'kat', 'K': r['K'],
                     'rows': [{'target_occurrence_id': occ(x['t']), 'bases': [obj(b) for b in x['bases']],
                               'encode_calls': x['encode_calls']} for x in r['rows']]}
    return world, standalone_rows, pairs, retrieval


def run_case(case, codec_lock, module=None):
    module = module or sys.modules[__name__]
    world, standalone_rows, pairs, retrieval = module.expand(case, codec_lock)
    return module.evaluate(world, standalone_rows, pairs, retrieval)


def render(out, case):
    """Map an evaluation back to the compact labels of a vector, in the shape of its 'expect' block."""
    tnames = {occ(t): t for t in {q['t'] for q in case['queries']}}
    bnames = {obj(b): b for q in case['queries'] for b in q['bases']}

    def text(x):
        return 'N/A' if x is None else str(x)

    res = {k: out[k] for k in ('run_status', 'invalid_reasons', 'coverage', 'retrieval_status', 'retrieval_reasons')}
    res['targets'] = None if out['targets'] is None else {
        tnames[t]: v if v.get('sealed') else {**v, 'ties': [bnames[b] for b in v['ties']]}
        for t, v in out['targets'].items()}
    res['metrics'] = None if out['metrics'] is None else {
        k: {kk: text(vv) for kk, vv in v.items()} if isinstance(v, dict) else text(v) for k, v in out['metrics'].items()}
    return res


# --- minimal closed-schema checker (test-only) ----------------------------------------------------------------------

KINDS = {'object': dict, 'array': list, 'string': str, 'integer': int, 'null': type(None), 'boolean': bool}


def schema_errors(value, schema, root, where='$'):
    """Keywords used by .work/oracle/schemas.json: $ref type const enum pattern minimum required properties
    additionalProperties items minItems uniqueItems oneOf allOf if/then/else."""
    if '$ref' in schema:
        target = root
        for part in schema['$ref'].lstrip('#/').split('/'):
            target = target[part]
        return schema_errors(value, target, root, where)
    if 'type' in schema:
        kinds = schema['type'] if isinstance(schema['type'], list) else [schema['type']]
        if not any(type(value) is KINDS[k] for k in kinds):
            return [f'{where}: not {schema["type"]}']
    errors = []
    if 'const' in schema and (type(value), value) != (type(schema['const']), schema['const']):
        errors.append(f'{where}: not const')
    if 'enum' in schema and not any((type(value), value) == (type(e), e) for e in schema['enum']):
        errors.append(f'{where}: not in enum')
    if type(value) is str and 'pattern' in schema and not re.search(schema['pattern'], value):
        errors.append(f'{where}: pattern')
    if type(value) is int and value < schema.get('minimum', value):
        errors.append(f'{where}: below minimum')
    if type(value) is dict:
        props = schema.get('properties', {})
        errors += [f'{where}: missing {k}' for k in schema.get('required', []) if k not in value]
        if schema.get('additionalProperties') is False:
            errors += [f'{where}: extra {k}' for k in value if k not in props]
        for k, sub in props.items():
            if k in value:
                errors += schema_errors(value[k], sub, root, f'{where}.{k}')
    if type(value) is list:
        if len(value) < schema.get('minItems', 0):
            errors.append(f'{where}: too few items')
        if schema.get('uniqueItems') and len({m.digest(v) for v in value}) != len(value):
            errors.append(f'{where}: items not unique')
        if 'items' in schema:
            for i, item in enumerate(value):
                errors += schema_errors(item, schema['items'], root, f'{where}[{i}]')
    for sub in schema.get('allOf', []):
        errors += schema_errors(value, sub, root, where)
    if 'oneOf' in schema and sum(not schema_errors(value, sub, root) for sub in schema['oneOf']) != 1:
        errors.append(f'{where}: not exactly one of oneOf')
    if 'if' in schema:
        branch = 'then' if not schema_errors(value, schema['if'], root) else 'else'
        if branch in schema:
            errors += schema_errors(value, schema[branch], root, where)
    return errors
