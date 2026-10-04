"""DELSK-003 Slice B: the production evaluator (.work/tools/oracle_eval.py) against the frozen contract.

Known answers K01-K42 and G01-G09, mutants M01-M30 (plus production-only mutants) on the production source, the
metamorphic properties, canonical/closed-schema parsing, sealing and leakage, finalize/verify/bundle. Payload-free and
codec-free; runs on any OS. The compact vectors are expanded here independently (contract section 10) and the
expansion is cross-checked row by row against the test-only reference, which the evaluator itself never imports.
"""
import copy
import hashlib
import io
import json
import random
import shutil
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = HERE.parent
ROOT = WORK.parent
sys.path[:0] = [str(WORK / 'tools'), str(HERE)]
import oracle_eval as ev  # noqa: E402

LOCK = ev.parse_doc((WORK / 'oracle' / 'codec-lock.json').read_bytes())
KAT = ev.parse_doc((WORK / 'oracle' / 'known-answer.json').read_bytes())
CASES = {c['id']: c for c in KAT['cases']}
DELTA = {k: LOCK['codecs']['delta'][k] for k in ('codec_id', 'options_sha256')}
ZSTD = {k: LOCK['codecs']['standalone'][k] for k in ('codec_id', 'options_sha256')}
DEFAULT_ERROR = {'timeout': 'wall_timeout', 'codec_error': 'nonzero_exit', 'resource_limit': 'address_space',
                 'decode_mismatch': 'bytes_mismatch', 'input_integrity': 'base_integrity', 'not_run': 'runner_abort'}


# --- independent expansion of compact vectors (contract section 10) ---------------------------------------------------

def occ(label):
    return ev.hc(['delsk.oracle.kat.v1', 'occurrence', label])


def obj(label):
    return ev.hc(['delsk.oracle.kat.v1', 'object', label])


def kat_identity():
    ident = {'measured_source_sha': 'a' * 40, 'corpus_lock_sha256': ev.hc(['delsk.oracle.kat.v1', 'corpus']),
             'candidate_lock_sha256': ev.hc(['delsk.oracle.kat.v1', 'candidate'])}
    return {**ident, 'measurement_identity_sha256': ev.hc(['delsk.oracle.kat.v1', 'identity', ident])}


def expand(case, ident=None, full=False):
    """Compact vector -> (world, standalone rows, pair rows, retrieval rows, target rows) of the production evaluator.
    full=True returns every pair/standalone row unsealed (what the runner keeps privately)."""
    ident = ident or kat_identity()
    sealed_splits = case.get('sealed_splits', [])
    raw = {s['t']: s['raw'] for s in case['standalone']}
    split = {q['t']: q.get('split', 'development') for q in case['queries']}
    labels = {q['t'] for q in case['queries']} | set(raw) | {p['t'] for p in case['pairs']}
    facts = {occ(t): {'object_id': obj(t), 'bytes': raw.get(t, 4096), 'split': split.get(t, 'development'),
                      'family_id': 'kat', 'track': 'kat'} for t in labels}
    queries = {occ(q['t']): {'status': q['status'], 'bases': [(obj(b), occ(b)) for b in sorted(q['bases'])]}
               for q in case['queries']}
    world = {'identity': ident, 'delta': DELTA, 'standalone': ZSTD, 'sealed_splits': sealed_splits,
             'queries': dict(sorted(queries.items())), 'facts': facts,
             'base_bytes': {obj(b): 4096 for b in {b for q in case['queries'] for b in q['bases']}
                            | {p['b'] for p in case['pairs']}}}
    hidden = set() if case.get('leak') or full else set(sealed_splits)
    pairs, full_pairs, solo_rows, full_solo = [], {}, [], {}
    for p in case['pairs']:
        t, b = occ(p['t']), obj(p['b'])
        fact, ok, n = facts[t], p['status'] == 'ok', p.get('payload')
        row = {'schema': ev.PAIR, **ident, **DELTA, 'pair_id': ev.pair_id(DELTA['codec_id'], t, b),
               'target_occurrence_id': t, 'target_object_id': fact['object_id'], 'target_bytes': fact['bytes'],
               'base_object_id': b, 'base_representative': occ(p['b']), 'base_bytes': 4096, 'split': fact['split'],
               'status': p['status'], 'failure_phase': None, 'error_class': None, 'encode_exit': None,
               'encode_signal': None, 'decode_exit': None, 'decode_signal': None, 'patch_payload_bytes': None,
               'patch_sha256': None, 'wrapper_bytes': None, 'base_reference_bytes': None,
               'codec_metadata_bytes': None, 'delta_total_bytes': None, 'decoded_bytes': None,
               'decoded_sha256': None, 'encode_wall_ns': None, 'decode_wall_ns': None,
               'encode_peak_rss_bytes': None, 'decode_peak_rss_bytes': None}
        if ok:
            row.update(encode_exit=0, decode_exit=0, patch_payload_bytes=n,
                       patch_sha256=ev.hc(['delsk.oracle.kat.v1', 'patch', p['t'], p['b'], n]),
                       wrapper_bytes=ev.wrapper_bytes(n), base_reference_bytes=32, codec_metadata_bytes=0,
                       delta_total_bytes=ev.delta_total(n), decoded_bytes=fact['bytes'],
                       decoded_sha256=fact['object_id'], encode_wall_ns=1000, decode_wall_ns=1000,
                       encode_peak_rss_bytes=1 << 20, decode_peak_rss_bytes=1 << 20)
        else:
            row.update(failure_phase={'decode_mismatch': 'decode', 'input_integrity': 'materialize'}
                       .get(p['status'], 'encode'), error_class=DEFAULT_ERROR[p['status']])
            if p['status'] == 'timeout':
                row['encode_signal'] = 9
            elif p['status'] == 'codec_error':
                row['encode_exit'] = 1
            elif p['status'] == 'decode_mismatch':
                row.update(encode_exit=0, decode_exit=0)
        row.update(p.get('set', {}))
        full_pairs.setdefault(t, {})[b] = row
        pairs.append(ev.seal_pair(row) if fact['split'] in hidden else row)
    for s in case['standalone']:
        t, st = occ(s['t']), s.get('status', 'ok')
        fact, ok, c = facts[t], st == 'ok', s.get('compressed')
        row = {'schema': ev.SOLO, **ident, **ZSTD, 'target_occurrence_id': t, 'target_object_id': fact['object_id'],
               'target_bytes': fact['bytes'], 'split': fact['split'],
               'query_status': next((q['status'] for q in case['queries'] if q['t'] == s['t']), 'near_duplicate'),
               'raw_total_bytes': ev.raw_total(fact['bytes']), 'status': st,
               'failure_phase': None if ok else 'encode', 'error_class': None if ok else DEFAULT_ERROR[st],
               'compress_exit': 0 if ok else None, 'compress_signal': 9 if st == 'timeout' else None,
               'decompress_exit': 0 if ok else None, 'decompress_signal': None,
               'compressed_payload_bytes': c if ok else None,
               'compressed_sha256': ev.hc(['delsk.oracle.kat.v1', 'zstd', s['t'], c]) if ok else None,
               'compressed_wrapper_bytes': ev.wrapper_bytes(c) if ok else None,
               'compressed_total_bytes': ev.compressed_total(c) if ok else None,
               'decoded_sha256': fact['object_id'] if ok else None,
               'compress_wall_ns': 1000 if ok else None, 'decompress_wall_ns': 1000 if ok else None}
        row.update(s.get('set', {}))
        full_solo[t] = row
        solo_rows.append(ev.seal_standalone(row) if fact['split'] in hidden else row)
    label = {occ(q['t']): q['t'] for q in case['queries']}
    targets = []
    for t, q in world['queries'].items():
        rows, srow = full_pairs.get(t, {}), full_solo.get(t)
        if label[t] in case.get('drop_targets', ()) or srow is None or srow['status'] == 'not_run' or any(
                b not in rows or rows[b]['status'] == 'not_run' for b, _ in q['bases']):
            continue
        row = ev.derive_target(world, t, rows, srow)
        if facts[t]['split'] in sealed_splits and not case.get('leak_target') and not full:
            row = ev.seal_target(row)
        row.update(case.get('target_set', {}).get(label[t], {}))
        targets.append(row)
    retrieval = None
    if case.get('retrieval') is not None:
        r = case['retrieval']
        retrieval = [{'schema': 'delsk.oracle.retrieval.v1', 'method_id': 'kat', 'K': r['K'],
                      'target_occurrence_id': occ(x['t']), 'bases': [obj(b) for b in x['bases']],
                      'encode_calls': x['encode_calls']} for x in r['rows']]
    return world, solo_rows, pairs, retrieval, targets


def run_case(case, module=ev):
    world, solo, pairs, retrieval, targets = expand(case)
    return module.evaluate(world, pairs, solo, targets, retrieval)


def text(x):
    return 'N/A' if x is None else str(Fraction(x))


def render(out, case):
    """Production result in the compact label shape of a vector's 'expect' block."""
    tname = {occ(q['t']): q['t'] for q in case['queries']}
    bname = {obj(b): b for q in case['queries'] for b in q['bases']}
    sealed = {occ(q['t']) for q in case['queries'] if q.get('split', 'development') in case.get('sealed_splits', [])}
    res = {k: out[k] for k in ('run_status', 'invalid_reasons', 'coverage', 'retrieval_status', 'retrieval_reasons')}
    res['targets'] = None if out['targets'] is None else {
        tname[t]: {'sealed': True} if t in sealed else {
            'S': r['standalone_total_bytes'], 'S_choice': r['standalone_choice'], 'O_delta': r['oracle_delta_total_bytes'],
            'delta_status': r['oracle_delta_status'], 'ties': [bname[b] for b in r['oracle_tie_bases']],
            'O': r['oracle_total_bytes'], 'useful': r['useful_delta']}
        for t, r in [*out['targets'].items(), *((t, None) for t in sealed)]}
    res['metrics'] = None if out['metrics'] is None else {
        k: {kk: text(vv) for kk, vv in v.items()} if isinstance(v, dict) else text(v) for k, v in out['metrics'].items()}
    return res


def kat_failures(module=ev):
    failed = []
    for case in KAT['cases']:
        try:
            out = run_case(case, module)
            want = case['expect']
            ok = out == run_case(CASES[want['same_as']], module) if 'same_as' in want else render(out, case) == want
        except Exception:  # a crashing mutant is killed too
            ok = False
        if not ok:
            failed.append(case['id'])
    for case in KAT['g1_cases']:
        try:
            ok = list(module.g1(case['runs'])) == case['expect']
        except Exception:
            ok = False
        if not ok:
            failed.append(case['id'])
    return failed


class Expansion(unittest.TestCase):
    def test_expansion_equals_the_reference_rows(self):
        """Fixture equivalence: the evaluator sees exactly the rows the frozen reference expands."""
        import oracle_reference as ref
        for case in KAT['cases']:
            with self.subTest(case['id']):
                _, rsolo, rpairs, rretrieval, rtargets = ref.expand(case, LOCK)
                world, solo, pairs, retrieval, targets = expand(case)
                for r in targets:  # the reference KAT world names family and track 'kat' too
                    self.assertTrue(r['schema'] != ev.TARGET or (r['family_id'], r['track']) == ('kat', 'kat'))
                self.assertEqual((solo, pairs, targets), (rsolo, rpairs, rtargets))
                if rretrieval is not None:
                    self.assertEqual([{k: r[k] for k in ('target_occurrence_id', 'bases', 'encode_calls')}
                                      for r in retrieval], rretrieval['rows'])

    def test_production_derivation_equals_reference_target_rows(self):
        import oracle_reference as ref
        for case in KAT['cases']:
            world, *_ = expand(case)
            rworld, rsolo, _, _, _ = ref.expand({**case, 'leak': True}, LOCK)
            _, solo, pairs, _, _ = expand(case, full=True)
            for t, q in world['queries'].items():
                rows = {r['base_object_id']: r for r in pairs if r['target_occurrence_id'] == t}
                srow = next((r for r in solo if r['target_occurrence_id'] == t), None)
                if srow is None or len(rows) != len(q['bases']):
                    continue
                rq = next(x for x in rworld['queries'] if x['target'] == t)
                with self.subTest(case['id']):
                    want = ref.target_row(rworld, rq, srow, rows, ref.derive_target(rq, srow, rows)[0])
                    self.assertEqual(ev.derive_target(world, t, rows, srow), want)


class KnownAnswers(unittest.TestCase):
    def test_vectors(self):
        for case in KAT['cases']:
            with self.subTest(case['id']):
                out, want = run_case(case), case['expect']
                if 'same_as' in want:
                    self.assertEqual(out, run_case(CASES[want['same_as']]))
                else:
                    self.assertEqual(render(out, case), want)

    def test_g1_vectors(self):
        for case in KAT['g1_cases']:
            with self.subTest(case['id']):
                self.assertEqual(list(ev.g1(case['runs'])), case['expect'])

    def test_evaluator_identity_is_a_new_record_with_the_same_measurement(self):  # K20
        world, *_ = expand(CASES['K20'])
        out = run_case(CASES['K20'])
        docs = [ev.documents(out, world, {'evaluator_sha256': e * 64, 'evaluator_source_sha': 'b' * 40})
                for e in '12']
        self.assertEqual(docs[0]['coverage.json'], docs[1]['coverage.json'])
        for name in ('summary.json', 'evaluation.json'):
            a, b = docs[0][name], docs[1][name]
            self.assertNotEqual(ev.hc(a), ev.hc(b))
            self.assertEqual({k: v for k, v in a.items() if k != 'evaluator_sha256'},
                             {k: v for k, v in b.items() if k != 'evaluator_sha256'})

    def test_every_vector_document_satisfies_the_closed_schemas(self):
        for case in KAT['cases']:
            world, *_ = expand(case)
            with self.subTest(case['id']):
                docs = ev.documents(run_case(case), world, {'evaluator_sha256': '1' * 64,
                                                            'evaluator_source_sha': 'b' * 40})
                for name, doc in docs.items():
                    self.assertEqual(ev.schema_errors(doc, ev.schemas()['$defs'][name[:-5]]), [])

    def test_sealed_rows_never_carry_costs(self):  # contract section 9.1
        world, solo, pairs, _, targets = expand(CASES['K30'])
        published = {k for r in pairs + solo + targets if r['schema'].endswith('-sealed.v1') for k in r}
        self.assertFalse(published & {'patch_payload_bytes', 'delta_total_bytes', 'patch_sha256', 'wrapper_bytes',
                                      'compressed_payload_bytes', 'compressed_total_bytes', 'compressed_sha256',
                                      'target_bytes', 'raw_total_bytes', 'decoded_bytes', 'standalone_total_bytes',
                                      'oracle_total_bytes', 'oracle_delta_total_bytes', 'oracle_tie_bases',
                                      'useful_delta', 'oracle_choice', 'candidate_list_sha256',
                                      'standalone_compressed_total_bytes'})
        out = run_case(CASES['K30'])
        docs = ev.documents(out, world, {'evaluator_sha256': '1' * 64, 'evaluator_source_sha': 'b' * 40})
        sealed_t = occ('t2')
        self.assertNotIn(sealed_t, json.dumps(docs['evaluation.json']))
        split = {s['split']: s for s in docs['summary.json']['per_split']}['evaluation']
        self.assertEqual((split['near_useful'], split['oracle_total_bytes_sum'], split['standalone_total_bytes_sum']),
                         (None, None, None))

    def test_reveal_commitments_and_hidden_repeat_changes(self):
        _, solo, pairs, _, targets = expand(CASES['K30'])
        _, fsolo, fpairs, _, ftargets = expand(CASES['K30'], full=True)
        def key(r):
            return (*ev.row_key(r)[:2], r['schema'].replace('-sealed', ''))

        sealed = {key(r): r['row_sha256'] for r in pairs + solo + targets if 'row_sha256' in r}
        self.assertEqual(len(sealed), 4)  # two pairs, one standalone and one target row of t2
        revealed = [r for r in fpairs + fsolo + ftargets if key(r) in sealed]
        self.assertEqual(len(revealed), 4)
        for r in revealed:  # a reveal run with other run-specific fields reproduces every commitment
            moved = {**r, 'measurement_identity_sha256': 'e' * 64}
            moved.update({k: 7 for k in ev.RUN_SPECIFIC - {'measurement_identity_sha256', 'measured_source_sha'}
                          if k in r})
            if 'measured_source_sha' in r:
                moved['measured_source_sha'] = 'c' * 40
            self.assertEqual(ev.commitment(moved), sealed[key(r)])
            forged = {**moved, 'standalone_status' if r['schema'] == ev.TARGET else 'status': 'timeout'}
            self.assertNotEqual(ev.commitment(forged), sealed[key(r)])
        drift = copy.deepcopy(CASES['K30'])
        next(p for p in drift['pairs'] if p['b'] == 'b4')['payload'] = 130  # non-winner in the sealed split
        a, b = run_case(CASES['K30']), run_case(drift)
        for key in ('cost_projection_sha256', 'targets_canonical_sha256'):
            self.assertEqual(a['digests'][key], b['digests'][key])
        self.assertNotEqual(a['digests']['sealed_commitments_sha256'], b['digests']['sealed_commitments_sha256'])


# --- production-specific adversarial vectors (row semantics beyond the frozen KAT) ------------------------------------

def adversarial():
    """(name, case, expected run_status, expected reasons) the production evaluator must reject or accept."""
    k01 = CASES['K01']

    def with_pair(index, **fields):
        case = copy.deepcopy(k01)
        case['pairs'][index].setdefault('set', {}).update(fields)
        return case

    laundered = copy.deepcopy(k01)
    laundered['pairs'][2] = {'t': 't1', 'b': 'b3', 'status': 'codec_error',
                             'set': {'failure_phase': 'decode', 'error_class': 'nonzero_exit'}}
    solo_tamper = copy.deepcopy(k01)
    solo_tamper['standalone'][0]['set'] = {'compressed_wrapper_bytes': 2}
    query_tamper = copy.deepcopy(k01)
    query_tamper['standalone'][0]['set'] = {'query_status': 'identity_only'}
    ok_exit = with_pair(0, decode_exit=1)
    decoded_len = with_pair(0, decoded_bytes=4095)
    pair_id_bad = with_pair(1, pair_id='0' * 64)
    base_bytes = with_pair(1, base_bytes=4097)
    representative = with_pair(1, base_representative=occ('b3'))
    bool_int = with_pair(0, encode_exit=True)
    negative = with_pair(0, target_bytes=-1)
    extra = with_pair(0, score=1)
    swapped = copy.deepcopy(k01)
    swapped['pairs'][0]['set'] = {'target_occurrence_id': occ('b1'), 'base_object_id': obj('t1')}
    return [('decode-phase codec_error is laundering', laundered, 'INVALID', ['INCONSISTENT_ROW']),
            ('standalone wrapper tamper', solo_tamper, 'INVALID', ['ACCOUNTING_MISMATCH']),
            ('standalone query status != lock', query_tamper, 'INVALID', ['LOCK_FIELD_MISMATCH']),
            ('ok row with decoder exit 1', ok_exit, 'INVALID', ['INCONSISTENT_ROW']),
            ('ok row with short decode', decoded_len, 'INVALID', ['DECODE_MISMATCH']),
            ('pair id', pair_id_bad, 'INVALID', ['PAIR_ID_MISMATCH']),
            ('base bytes != lock', base_bytes, 'INVALID', ['LOCK_FIELD_MISMATCH']),
            ('base representative != lock', representative, 'INVALID', ['LOCK_FIELD_MISMATCH']),
            ('bool accepted as int', bool_int, 'INVALID', ['SCHEMA']),
            ('negative size', negative, 'INVALID', ['SCHEMA']),
            ('extra field', extra, 'INVALID', ['SCHEMA']),
            ('base and target swapped', swapped, 'INVALID', ['FOREIGN_PAIR'])]


def adversarial_failures(module=ev):
    failed = []
    for name, case, status, reasons in adversarial():
        try:
            out = run_case(case, module)
            ok = (out['run_status'], out['invalid_reasons']) == (status, reasons)
        except Exception:
            ok = False
        if not ok:
            failed.append(name)
    return failed


class Adversarial(unittest.TestCase):
    def test_rows_beyond_the_frozen_vectors(self):
        self.assertEqual(adversarial_failures(), [])

    def test_identity_query_rows_do_not_enter_near_population(self):
        out = run_case(CASES['K25'])
        self.assertEqual(out['populations'], {'near': 1, 'finite': 1, 'useful': 1, 'sealed_excluded': 0})


# --- canonical and closed parsing -------------------------------------------------------------------------------------

class Canonical(unittest.TestCase):
    def test_parse_rejects_noncanonical_input(self):
        good = ev.canonical({'a': 1, 'b': [True, None]})
        self.assertEqual(ev.parse_doc(good), {'a': 1, 'b': [True, None]})
        for bad in (b'{"a":1}\n', b'\xef\xbb\xbf' + good, good.replace(b'1', b'1.0'), b'{\n  "a": 1,\n  "a": 2\n}\n',
                    good.replace(b'1', b'NaN'), ev.canonical({'a': 1})[:-1], good.replace(b'1', b'99999999999999999999')):
            with self.subTest(bad):
                with self.assertRaises((ev.EvalError, ValueError)):
                    ev.parse_doc(bad)

    def test_jsonl_is_strict(self):
        rows = [{'schema': 's', 'target_occurrence_id': 'b'}, {'schema': 's', 'target_occurrence_id': 'a'}]
        data = ev.jsonl(rows)
        self.assertEqual(ev.parse_jsonl(data), sorted(rows, key=ev.row_key))
        for bad in (data[:-1], data + b'\n', data.replace(b'"s"', b'"s" '), b'[1]\n', data.replace(b'"b"', b'1.5')):
            with self.subTest(bad):
                with self.assertRaises((ev.EvalError, ValueError)):
                    ev.parse_jsonl(bad)

    def test_floats_and_wide_integers_cannot_be_written(self):
        for value in ({'x': 0.5}, {'x': 1 << 63}, {'x': 'é'}):
            with self.assertRaises(ev.EvalError):
                ev.canonical(value)

    def test_frame_accounting(self):
        self.assertEqual([ev.uleb128_len(n) for n in (0, 127, 128, 16383, 16384, 2 ** 21 - 1, 2 ** 21)],
                         [1, 1, 2, 2, 3, 3, 4])
        self.assertEqual((ev.raw_total(0), ev.delta_total(100), ev.compressed_total(400)), (2, 134, 403))

    def test_natural_lock_world_without_payloads(self):
        """The sealed E1 universe parses into 79 queries and 1 961 canonical pairs; nothing is measured."""
        import gzip
        freeze = ev.parse_doc((WORK / 'oracle' / 'freeze.json').read_bytes())
        candidate = ev.parse_doc((WORK / 'corpus' / 'e1' / 'candidate-lock.json').read_bytes())
        corpus = ev.parse_doc(gzip.decompress((WORK / 'corpus' / 'pilot-v1' / 'corpus-lock.json.gz').read_bytes()))
        ident = {'measurement_identity_sha256': '0' * 64, 'measured_source_sha': '0' * 40,
                 'corpus_lock_sha256': freeze['bindings']['corpus_lock_sha256'],
                 'candidate_lock_sha256': freeze['bindings']['candidate_lock_sha256'], 'sealed_splits': ['evaluation']}
        world = ev.world_from_locks(candidate, corpus, ident, LOCK)
        pairs = ev.expected_pairs(world)
        self.assertEqual((len(world['queries']), len(pairs), len(set(pairs))), (79, 1961, 1961))
        self.assertEqual(pairs, sorted(pairs))
        self.assertEqual(sum(world['facts'][t]['split'] == 'evaluation' for t in world['queries']), 10)


# --- metamorphic properties on the production evaluator (contract section 11) -----------------------------------------

class Metamorphic(unittest.TestCase):
    def setUp(self):
        from test_oracle_contract import random_case
        self.rng = random.Random(20261004)
        self.cases = [random_case(self.rng) for _ in range(60)]

    def targets(self, case):
        out = run_case(case)
        self.assertIn(out['run_status'], ('COMPLETE', 'COMPLETE_WITH_FAILURES'))
        return render(out, case)['targets']

    def test_generator_is_not_vacuous(self):
        kinds = {v['delta_status'] for c in self.cases for v in self.targets(c).values()}
        self.assertEqual(kinds, {'finite', 'empty_candidate_set', 'all_pairs_failed'})

    def test_row_permutation_invariance(self):
        for case in self.cases:
            world, solo, pairs, retrieval, targets = expand(case)
            for _ in range(3):
                shuffled = [copy.deepcopy(x) for x in (pairs, solo, targets, retrieval)]
                for rows in shuffled:
                    self.rng.shuffle(rows)
                self.assertEqual(ev.evaluate(world, shuffled[0], shuffled[1], shuffled[2], shuffled[3]),
                                 ev.evaluate(world, pairs, solo, targets, retrieval))

    def test_dominated_candidate_cannot_improve_oracle(self):
        for case in self.cases:
            before = self.targets(case)
            grown = copy.deepcopy(case)
            q = grown['queries'][0]
            old = before[q['t']]
            q['bases'].append('zz')
            grown['pairs'].append({'t': q['t'], 'b': 'zz', 'status': 'ok',
                                   'payload': max(old['O_delta'] or 0, old['S']) + self.rng.randint(0, 99)})
            grown['retrieval']['rows'][0].update(bases=[], encode_calls=0)
            after = self.targets(grown)[q['t']]
            self.assertEqual((after['O'], after['useful']), (old['O'], old['useful']))
            if old['O_delta'] is not None:
                self.assertEqual((after['O_delta'], after['ties']), (old['O_delta'], old['ties']))

    def test_raising_a_non_winner_changes_nothing(self):
        for case in self.cases:
            before = self.targets(case)
            for p in case['pairs']:
                if p['status'] == 'ok' and p['b'] not in before[p['t']]['ties']:
                    raised = copy.deepcopy(case)
                    next(x for x in raised['pairs'] if x['b'] == p['b'])['payload'] += self.rng.randint(1, 500)
                    self.assertEqual(self.targets(raised), before)
                    break

    def test_equal_cost_base_joins_the_tie_set(self):
        for case in self.cases:
            before = self.targets(case)
            for p in case['pairs']:
                if p['status'] == 'ok' and p['b'] in before[p['t']]['ties']:
                    twin = copy.deepcopy(case)
                    next(q for q in twin['queries'] if q['t'] == p['t'])['bases'].append('twin')
                    twin['pairs'].append({**p, 'b': 'twin'})
                    after = self.targets(twin)[p['t']]
                    self.assertEqual((after['O'], set(after['ties'])), (before[p['t']]['O'],
                                                                       {*before[p['t']]['ties'], 'twin'}))
                    break

    def test_cheaper_fallback_forces_standalone(self):
        for case in self.cases:
            cheap = copy.deepcopy(case)
            for s in cheap['standalone']:
                s['raw'] = 0
            for v in self.targets(cheap).values():
                self.assertEqual((v['O'], v['useful']), (2, False))

    def test_recomputation_is_deterministic(self):
        for case in self.cases[:10]:
            self.assertEqual(ev.hc(render(run_case(case), case)), ev.hc(render(run_case(copy.deepcopy(case)), case)))


# --- mutants on the production source (contract section 11, applied to Slice B) ----------------------------------------
# Each entry injects one defect class as an exact single-occurrence substring change of oracle_eval.py.

MUTANTS = {
    'M01 drop worst pair': (
        "    for row in pairs:\n",
        "    for row in sorted(pairs, key=lambda r: -(r.get('delta_total_bytes') or 0))[1:]:\n"),
    'M02 drop best pair': (
        "    for row in pairs:\n",
        "    for row in sorted(pairs, key=lambda r: (r.get('delta_total_bytes') is None, "
        "r.get('delta_total_bytes') or 0))[1:]:\n"),
    'M03 arbitrary single tie': (
        '"oracle_tie_bases": sorted(b for b, c in finite.items() if c == best),',
        '"oracle_tie_bases": sorted(b for b, c in finite.items() if c == best)[:1],'),
    'M04 timeout counted as success': (
        'failures = coverage["timeout"] + coverage["codec_error"]', 'failures = coverage["codec_error"]'),
    'M05 decode mismatch ignored': ('FATAL = {"decode_mismatch": "DECODE_MISMATCH", ', 'FATAL = {'),
    'M06 payload instead of total': (
        'finite = {b: rows[b]["delta_total_bytes"] for b', 'finite = {b: rows[b]["patch_payload_bytes"] for b'),
    'M07 base reference omitted': (
        "return payload + wrapper_bytes(payload) + BASE_REFERENCE_BYTES + CODEC_METADATA_BYTES",
        "return payload + wrapper_bytes(payload) + CODEC_METADATA_BYTES"),
    'M08 N/A as 100%': ("return None if den == 0 else Fraction(num, den)",
                        "return Fraction(1) if den == 0 else Fraction(num, den)"),
    'M09 oracle best substituted into retrieval': (
        'for b in by_target[t]["bases"] if rows[t][b]["status"] == "ok"]\n',
        'for b in by_target[t]["bases"] if rows[t][b]["status"] == "ok"] or '
        '([tr["oracle_delta_total_bytes"]] if tr["oracle_delta_total_bytes"] is not None else [])\n'),
    'M10 denominator only successful targets': (
        'finite = [t for t in scored if targets[t]["oracle_delta_status"] == "finite"]',
        'finite = [t for t in scored if targets[t]["oracle_delta_status"] == "finite" '
        'and set(by_target[t]["bases"]) & set(targets[t]["oracle_tie_bases"])]'),
    'M11 row order changes result': (
        "rows = sorted(({k: v for k, v in r.items() if k not in drop} for r in rows), key=row_key)",
        "rows = [{k: v for k, v in r.items() if k not in drop} for r in rows]"),
    'M12 duplicate row silently collapsed': (
        '            reasons.add("DUPLICATE_PAIR")\n            continue\n', '            continue\n'),
    'M13 epsilon strict <': ("any(100 * c <= 100 * od", "any(100 * c < 100 * od"),
    'M14 64 B floor dropped': ("max(100 * TOLERANCE_FLOOR, e * od)", "e * od"),
    'M15 useful with <=': ("useful = best is not None and best < s", "useful = best is not None and best <= s"),
    'M16 normalized regret without floor': (
        'Fraction(regret[t], max(tr["oracle_total_bytes"], TOLERANCE_FLOOR))',
        'Fraction(regret[t], tr["oracle_total_bytes"] or 1)'),
    'M17 calls numerator from retrieval': (
        'ratio(sum(targets[t]["candidate_count"] for t in scored),',
        'ratio(sum(len(by_target[t]["bases"]) for t in scored),'),
    'M18 identity targets in near population': (
        'near = [t for t in sorted(queries) if queries[t]["status"] == "near_duplicate"]', 'near = sorted(queries)'),
    'M19 sealing not enforced': (
        'if row["schema"].endswith("-sealed.v1") != (facts[t]["split"] in sealed_splits):', 'if False:'),
    'M20 missing pairs not counted': (
        '"missing": len(expected) - len(seen) + status["not_run"],', '"missing": 0,'),
    'M21 accounting not checked': (
        'if (row["wrapper_bytes"], row["base_reference_bytes"], row["codec_metadata_bytes"],',
        'if False and (row["wrapper_bytes"], row["base_reference_bytes"], row["codec_metadata_bytes"],'),
    'M22 G1 from one run': ('if len({r["github_run_id"] for r in verified}) < 2:',
                            'if len({r["github_run_id"] for r in verified}) < 1:'),
    'M23 G1 repeat mismatch ignored': ("    if len(repeat) > 1:\n", "    if len(repeat) > 99:\n"),
    'M24 G1 invalid attempt outvoted': ('if any(r["run_status"] == "INVALID" for r in runs):', 'if False:'),
    'M25 sealed standalone decode unchecked': (
        'if status == "ok" and row["decoded_sha256"] != facts[t]["object_id"]:',
        'if status == "ok" and row["schema"] != SOLO_SEALED and row["decoded_sha256"] != facts[t]["object_id"]:'),
    'M26 G1 ignores sealed commitments': (
        'r["targets_sha256"], r["sealed_commitments_sha256"])', 'r["targets_sha256"])'),
    'M27 sealed target structure unchecked': ("            if any(row[k] != v for k, v in claim.items()):",
                                              "            if False:"),
    'M28 full target allowed on sealed split': (
        "        if is_sealed != (facts[t][\"split\"] in sealed_splits):\n            reasons.add(\"SEALING_VIOLATION\")\n",
        "        if False:\n            pass\n"),
    'M29 published target not recomputed': ("        if published[t] != derived[t]:", "        if False:"),
    'M30 missing target rows not counted': (
        '"targets_missing": sum(t not in published for t in queries)}', '"targets_missing": 0}'),
    # production-only defect classes, killed by the adversarial vectors above
    'P01 decode-phase laundering accepted': (
        'if status != "ok" and (row["failure_phase"], row["error_class"]) not in FAILURE_MODES[status]:',
        'if False:'),
    'P02 standalone accounting unchecked': (
        'if (row["compressed_wrapper_bytes"], row["compressed_total_bytes"]) != (wrapper_bytes(c), compressed_total(c)):',
        'if False:'),
    'P03 bool accepted as integer': (
        'if type(value) not in [kinds[k] for k in wanted]:',
        'if type(value) not in [kinds[k] for k in wanted] + ([bool] if "integer" in wanted else []):'),
    'P04 lock fields of pair rows unchecked': (
        '(fact["object_id"], fact["bytes"], expected[key], world["base_bytes"][b]):', '(row["target_object_id"], '
        'row["target_bytes"], row["base_representative"], row["base_bytes"]):'),
    'P05 closed schema opened': ('if node.get("additionalProperties") is False:', 'if False:'),
    'P06 ok exit codes unchecked': ('(row["encode_exit"], row["decode_exit"], row["encode_signal"], '
                                    'row["decode_signal"]) != (0, 0, None, None):', 'False:'),
    'P07 decoded length unchecked': ('if row["decoded_bytes"] != fact["bytes"]:', 'if False:'),
}


class Mutants(unittest.TestCase):
    def test_every_mutant_is_killed(self):
        self.assertEqual(kat_failures(), [])
        self.assertEqual(adversarial_failures(), [])
        source = (WORK / 'tools' / 'oracle_eval.py').read_text(encoding='utf-8')
        for name, (old, new) in MUTANTS.items():
            with self.subTest(name):
                self.assertEqual(source.count(old), 1, 'mutant patch must match exactly once')
                module = types.ModuleType('oracle_eval_mutant')
                module.__file__ = str(WORK / 'tools' / 'oracle_eval.py')
                exec(compile(source.replace(old, new), module.__file__, 'exec'), module.__dict__)
                killed = kat_failures(module) if name.startswith('M') else adversarial_failures(module)
                self.assertTrue(killed, 'mutant survived')


if __name__ == '__main__':
    unittest.main()
