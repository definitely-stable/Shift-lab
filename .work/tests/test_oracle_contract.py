"""DELSK-003 Slice A: integrity of the frozen oracle sub-contract delsk.oracle-contract.v1.

Offline and payload-free: no codec runs, no corpus bytes, no patch costs. Checks that the freeze record pins the
contract files, that the codec lock and pair universe are bound to the sealed E1 candidate lock, that the schemas are
closed, that every known-answer vector agrees with the test-only reference of the contract (oracle_reference.py),
that the metamorphic properties hold and that every mutant of contract section 11 is killed by the vectors.
"""
import copy
import hashlib
import random
import sys
import types
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = HERE.parent
ROOT = WORK.parent
ORACLE = WORK / 'oracle'
sys.path[:0] = [str(WORK / 'tools'), str(HERE)]
import manifests as m
import oracle_reference as ref


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return m.loads_strict(path.read_bytes())


FREEZE = load(ORACLE / 'freeze.json')
LOCK = load(ORACLE / 'codec-lock.json')
SCHEMAS = load(ORACLE / 'schemas.json')
KAT = load(ORACLE / 'known-answer.json')
CASES = {c['id']: c for c in KAT['cases']}


def outcome(case, module=ref):
    out = ref.run_case(case, LOCK, module)
    return out, ref.render(out, case)


def kat_failures(module=ref):
    """IDs of vectors whose outcome differs from the frozen expectation."""
    failed = []
    for case in KAT['cases']:
        try:
            out, got = outcome(case, module)
            want = case['expect']
            if 'same_as' in want:
                ok = out == ref.run_case(CASES[want['same_as']], LOCK, module)
            else:
                ok = got == want
        except Exception:  # a crashing mutant is killed too
            ok = False
        if not ok:
            failed.append(case['id'])
    for case in KAT['g1_cases']:
        if list(module.g1(case['runs'])) != case['expect']:
            failed.append(case['id'])
    return failed


class Freeze(unittest.TestCase):
    def test_record_pins_contract_files(self):
        self.assertEqual(FREEZE['schema'], 'delsk.oracle-contract.freeze.v1')
        self.assertEqual(FREEZE['contract_id'], 'delsk.oracle-contract.v1')
        self.assertEqual(FREEZE['natural_measurements'], 'NOT_RUN')
        for name, digest in FREEZE['files'].items():
            with self.subTest(name):
                self.assertEqual(sha(ROOT / name), digest)
        for required in ('contract.md', 'codec-lock.json', 'schemas.json', 'known-answer.json'):
            self.assertIn(f'.work/oracle/{required}', FREEZE['files'])
        self.assertIn('.work/tests/oracle_reference.py', FREEZE['files'])
        self.assertIn('.work/tests/test_oracle_contract.py', FREEZE['files'])

    def test_bindings_are_the_sealed_e1_universe(self):
        seal = load(WORK / 'corpus' / 'e1' / 'seal.json')
        clock = load(WORK / 'corpus' / 'e1' / 'candidate-lock.json')
        b = FREEZE['bindings']
        self.assertEqual(b['candidate_lock_sha256'], seal['candidate_lock_sha256'])
        self.assertEqual(b['candidate_lock_sha256'], sha(WORK / 'corpus' / 'e1' / 'candidate-lock.json'))
        self.assertEqual(b['corpus_lock_sha256'], clock['corpus_lock_sha256'])
        self.assertEqual(b['protocol_sha256'], clock['protocol_sha256'])
        self.assertEqual(b['protocol_sha256'], sha(WORK / 'protocol.md'))
        self.assertEqual(b['seal_sha256'], sha(WORK / 'corpus' / 'e1' / 'seal.json'))
        self.assertEqual(b['codec_lock_sha256'], sha(ORACLE / 'codec-lock.json'))

    def test_no_natural_oracle_evidence_exists(self):
        results = WORK / 'results'
        self.assertEqual([p.name for p in results.iterdir() if p.name.startswith('DELSK-003')], [])

    def test_contract_states_scope_and_verdict(self):
        text = (ORACLE / 'contract.md').read_text(encoding='utf-8')
        self.assertIn('delsk.oracle-contract.v1', text)
        self.assertIn('**Slice A verdict: ORACLE CONTRACT FREEZE-READY**', text)
        self.assertIn('DELSK-P1', text)


class CodecLock(unittest.TestCase):
    def test_schema_and_options_hashes(self):
        self.assertEqual(ref.schema_errors(LOCK, SCHEMAS['$defs']['codec_lock'], SCHEMAS), [])
        for role, codec in LOCK['codecs'].items():
            with self.subTest(role):
                self.assertEqual(codec['role'], role)
                self.assertEqual(codec['options_sha256'],
                                 m.digest({k: v for k, v in codec.items() if k != 'options_sha256'}))

    def test_delta_framing_switches(self):
        xd = LOCK['codecs']['delta']
        enc, dec, build = xd['encode_argv'], xd['decode_argv'], xd['build']['argv']
        self.assertEqual(enc[enc.index('-S') + 1], 'none')  # explicit: LZMA would be the default when compiled in
        for flag in ('-e', '-9', '-A=', '-n', '-a', '-D', '-R', '-f', '-q'):
            self.assertIn(flag, enc)
        for flag in ('-d', '-n', '-a', '-D', '-R', '-f', '-q'):
            self.assertIn(flag, dec)
        self.assertNotIn('-c', enc + dec)
        self.assertEqual(enc[enc.index('-B') + 1], dec[dec.index('-B') + 1])
        for define in ('-DEXTERNAL_COMPRESSION=0', '-DXD3_ARMOR=0', '-DSECONDARY_LZMA=0', '-DXD3_DEBUG=0'):
            self.assertIn(define, build)
        self.assertEqual(enc[-4:], ['-s', '{base}', '{target}', '{patch}'])
        self.assertEqual(dec[-4:], ['-s', '{base}', '{patch}', '{decoded}'])

    def test_standalone_framing_switches(self):
        zs = LOCK['codecs']['standalone']
        enc = zs['encode_argv']
        for flag in ('-19', '--single-thread', '--no-check', '--content-size'):
            self.assertIn(flag, enc)
        for forbidden in ('-D', '--patch-from', '--long', '-T0', '--ultra'):
            self.assertNotIn(forbidden, enc)
        self.assertIn('HAVE_THREAD=0', zs['build']['argv'])

    def test_frame_and_invocation_policy(self):
        self.assertEqual(LOCK['frame']['base_reference_bytes'], ref.BASE_REFERENCE_BYTES)
        self.assertEqual(LOCK['frame']['codec_metadata_bytes'], ref.CODEC_METADATA_BYTES)
        self.assertFalse(LOCK['invocation']['env_inherited'])
        self.assertTrue({'XDELTA', 'ZSTD_CLEVEL', 'ZSTD_NBTHREADS'} <= set(LOCK['invocation']['forbidden_env']))
        self.assertEqual(LOCK['second_codec'], 'NOT_ADMITTED')

    def test_frame_accounting(self):
        self.assertEqual([ref.uleb128_len(n) for n in (0, 127, 128, 16383, 16384, 2 ** 21 - 1, 2 ** 21)],
                         [1, 1, 2, 2, 3, 3, 4])
        self.assertEqual(ref.raw_total(0), 2)
        self.assertEqual(ref.delta_total(100), 134)
        self.assertEqual(ref.standalone_total(400), 403)


class PairUniverse(unittest.TestCase):
    """Contract section 4 on the committed sealed lock: counts, canonical order and pair IDs."""

    def test_expected_pairs_per_codec(self):
        clock = load(WORK / 'corpus' / 'e1' / 'candidate-lock.json')
        queries = clock['queries']
        near = [q for q in queries if q['status'] == 'near_duplicate']
        pairs = [(q['target'], b['object_id']) for q in near for b in q['bases']]
        self.assertEqual((len(queries), len(near), len(queries) - len(near)), (79, 64, 15))
        self.assertEqual(len(pairs), 1961)
        self.assertEqual(len(pairs), clock['planned_pairs_per_codec'])
        self.assertEqual(pairs, sorted(pairs))  # lock storage order is the canonical pair order
        self.assertEqual(len(set(pairs)), len(pairs))
        self.assertTrue(all(not q['bases'] for q in queries if q['status'] == 'identity_only'))
        ids = {ref.pair_id(LOCK['codecs']['delta']['codec_id'], *p) for p in pairs}
        self.assertEqual(len(ids), len(pairs))
        self.assertLessEqual(len(pairs), 4096)


class Schemas(unittest.TestCase):
    def test_every_object_schema_is_closed(self):
        open_ = []

        def walk(node, where):
            if isinstance(node, dict):
                if 'properties' in node and node.get('type') == 'object' and node.get('additionalProperties') is not False:
                    open_.append(where)
                for k, v in node.items():
                    walk(v, f'{where}/{k}')
            elif isinstance(node, list):
                for i, v in enumerate(node):
                    walk(v, f'{where}[{i}]')

        walk(SCHEMAS['$defs'], '#')
        self.assertEqual(open_, [])
        for artifact in ('codec_lock', 'run', 'pair', 'pair_sealed', 'standalone', 'standalone_sealed', 'target',
                         'target_sealed', 'coverage', 'summary', 'retrieval', 'evaluation'):
            self.assertIn(artifact, SCHEMAS['$defs'])

    def test_expanded_vector_rows_satisfy_schemas(self):
        d = SCHEMAS['$defs']
        for case in KAT['cases']:
            _, standalone_rows, pairs, _ = ref.expand(case, LOCK)
            for row in pairs + standalone_rows:
                kind = row['schema'][len('delsk.oracle.'):-len('.v1')].replace('-', '_')
                with self.subTest(case['id'], kind=kind):
                    self.assertEqual(ref.schema_errors(row, d[kind], SCHEMAS), [])

    def test_schemas_fail_closed(self):
        _, _, pairs, _ = ref.expand(CASES['K01'], LOCK)
        for name, mutate in (('extra key', lambda r: r.update(score=1)),
                             ('ok without payload', lambda r: r.update(patch_payload_bytes=None)),
                             ('failure with cost', lambda r: r.update(status='timeout', error_class='wall_timeout',
                                                                      failure_phase='encode')),
                             ('bool as integer', lambda r: r.update(target_bytes=True)),
                             ('missing field', lambda r: r.pop('split')),
                             ('base reference other than 32', lambda r: r.update(base_reference_bytes=64))):
            row = copy.deepcopy(pairs[0])
            mutate(row)
            with self.subTest(name):
                self.assertTrue(ref.schema_errors(row, SCHEMAS['$defs']['pair'], SCHEMAS))


class KnownAnswers(unittest.TestCase):
    def test_user_required_vectors_present(self):
        self.assertEqual(set(KAT['user_required'].values()), {f'K{i:02d}' for i in range(1, 21)})
        self.assertTrue(set(KAT['user_required'].values()) <= set(CASES))

    def test_vectors(self):
        for case in KAT['cases']:
            with self.subTest(case['id']):
                out, got = outcome(case)
                want = case['expect']
                if 'same_as' in want:
                    self.assertEqual(out, ref.run_case(CASES[want['same_as']], LOCK))
                else:
                    self.assertEqual(got, want)

    def test_g1_vectors(self):
        for case in KAT['g1_cases']:
            with self.subTest(case['id']):
                self.assertEqual(list(ref.g1(case['runs'])), case['expect'])

    def test_sealed_commitment_survives_a_reveal_run(self):  # contract section 9.1
        _, standalone_rows, pairs, _ = ref.expand(CASES['K30'], LOCK)
        _, _, full, _ = ref.expand({**CASES['K30'], 'leak': True}, LOCK)
        sealed = {r['pair_id']: r for r in pairs if r['schema'] == 'delsk.oracle.pair-sealed.v1'}
        self.assertEqual(len(sealed), 2)
        for row in full:
            if row['pair_id'] in sealed:
                reveal = {**row, 'encode_wall_ns': 7, 'decode_peak_rss_bytes': 9,
                          'measurement_identity_sha256': 'e' * 64, 'measured_source_sha': 'b' * 40}
                self.assertEqual(ref.commitment(reveal), sealed[row['pair_id']]['row_sha256'])
                forged = {**reveal, 'patch_payload_bytes': row['patch_payload_bytes'] + 1}
                self.assertNotEqual(ref.commitment(forged), sealed[row['pair_id']]['row_sha256'])
        published = [k for r in pairs + standalone_rows if r['schema'].endswith('-sealed.v1') for k in r]
        self.assertFalse({'patch_payload_bytes', 'delta_total_bytes', 'patch_sha256', 'compressed_payload_bytes',
                          'compressed_total_bytes', 'target_bytes', 'raw_total_bytes'} & set(published))

    def test_evaluator_identity_is_separate_from_measurement(self):  # K20
        out = ref.run_case(CASES['K20'], LOCK)
        records = [{'evaluator_sha256': e, 'measurement': out['cost_projection_sha256'],
                    'metrics': m.digest(ref.render(out, CASES['K20'])['metrics'])} for e in ('1' * 64, '2' * 64)]
        self.assertEqual(records[0]['measurement'], records[1]['measurement'])
        self.assertEqual(records[0]['metrics'], records[1]['metrics'])
        self.assertNotEqual(m.digest(records[0]), m.digest(records[1]))


def random_case(rng):
    queries, standalone, pairs, rows = [], [], [], []
    for i in range(rng.randint(1, 4)):
        t = f't{i}'
        bases = [f'{t}b{j}' for j in range(rng.randint(0, 5))]
        queries.append({'t': t, 'status': 'near_duplicate', 'bases': bases})
        raw = rng.randint(0, 5000)
        standalone.append({'t': t, 'raw': raw, 'compressed': rng.randint(9, raw + 20)})
        for b in bases:
            pairs.append({'t': t, 'b': b, 'status': 'ok', 'payload': rng.randint(0, 6000)} if rng.random() < .85
                         else {'t': t, 'b': b, 'status': rng.choice(['timeout', 'codec_error', 'resource_limit'])})
        pick = rng.sample(bases, min(len(bases), rng.randint(0, 2)))
        rows.append({'t': t, 'bases': pick, 'encode_calls': len(pick)})
    return {'queries': queries, 'standalone': standalone, 'pairs': pairs,
            'retrieval': {'K': 2, 'rows': rows}}


class Metamorphic(unittest.TestCase):
    """Contract section 11 properties on generated vectors (seed fixed)."""

    def setUp(self):
        self.rng = random.Random(20261004)
        self.cases = [random_case(self.rng) for _ in range(60)]

    def targets(self, case):
        out = ref.run_case(case, LOCK)
        self.assertIn(out['run_status'], ('COMPLETE', 'COMPLETE_WITH_FAILURES'))
        return ref.render(out, case)['targets']

    def test_generator_is_not_vacuous(self):
        kinds = {v['delta_status'] for c in self.cases for v in self.targets(c).values()}
        self.assertEqual(kinds, {'finite', 'empty_candidate_set', 'all_pairs_failed'})
        self.assertTrue(any(v['useful'] for c in self.cases for v in self.targets(c).values()))
        self.assertTrue(any(len(v['ties']) > 1 or not v['useful'] for c in self.cases for v in self.targets(c).values()))

    def test_row_permutation_invariance(self):
        for case in self.cases:
            shuffled = copy.deepcopy(case)
            self.rng.shuffle(shuffled['pairs'])
            self.rng.shuffle(shuffled['standalone'])
            self.assertEqual(ref.run_case(shuffled, LOCK), ref.run_case(case, LOCK))

    def test_dominated_candidate_cannot_improve_oracle(self):
        for case in self.cases:
            before = self.targets(case)
            grown = copy.deepcopy(case)
            q = grown['queries'][0]
            old = before[q['t']]
            floor = max(old['O_delta'] or 0, old['S'])
            q['bases'].append('zz')
            grown['pairs'].append({'t': q['t'], 'b': 'zz', 'status': 'ok', 'payload': floor + self.rng.randint(0, 99)})
            grown['retrieval']['rows'][0]['bases'] = []
            grown['retrieval']['rows'][0]['encode_calls'] = 0
            after = self.targets(grown)[q['t']]
            self.assertEqual((after['O'], after['useful']), (old['O'], old['useful']))
            if old['O_delta'] is not None:
                self.assertEqual((after['O_delta'], after['ties']), (old['O_delta'], old['ties']))

    def test_raising_a_non_winner_changes_nothing(self):
        for case in self.cases:
            before = self.targets(case)
            for p in case['pairs']:
                tie = before[p['t']]['ties']
                if p['status'] == 'ok' and p['b'] not in tie:
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
                    self.assertEqual(after['O'], before[p['t']]['O'])
                    self.assertEqual(set(after['ties']), {*before[p['t']]['ties'], 'twin'})
                    break

    def test_cheaper_fallback_forces_standalone(self):
        for case in self.cases:
            cheap = copy.deepcopy(case)
            for s in cheap['standalone']:
                s['raw'] = 0  # raw frame of 2 B beats every delta (>= 34 B)
            for t, v in self.targets(cheap).items():
                self.assertEqual((v['O'], v['useful']), (2, False))

    def test_recomputation_is_deterministic(self):
        for case in self.cases[:10]:
            self.assertEqual(m.digest(ref.render(ref.run_case(case, LOCK), case)),
                             m.digest(ref.render(ref.run_case(copy.deepcopy(case), LOCK), case)))


# Contract section 11: each mutant is an exact single-occurrence substring change of oracle_reference.py.
MUTANTS = {
    'M01 drop worst pair': ("    for row in pair_rows:\n",
                            "    for row in sorted(pair_rows, key=lambda r: -(r.get('delta_total_bytes') or 0))[1:]:\n"),
    'M02 drop best pair': ("    for row in pair_rows:\n",
                           "    for row in sorted(pair_rows, key=lambda r: (r.get('delta_total_bytes') is None, "
                           "r.get('delta_total_bytes') or 0))[1:]:\n"),
    'M03 one tie instead of all': ("'ties': sorted(b for b, c in finite.items() if c == od),",
                                   "'ties': sorted(b for b, c in finite.items() if c == od)[:1],"),
    'M04 timeout counted as success': ("failed = counts['timeout'] + counts['codec_error']", "failed = counts['codec_error']"),
    'M05 decode mismatch ignored': ("FATAL = {'decode_mismatch': 'DECODE_MISMATCH', ", "FATAL = {"),
    'M06 payload instead of total': ("seen[(t, b['object_id'])]['delta_total_bytes'] for b",
                                     "seen[(t, b['object_id'])]['patch_payload_bytes'] for b"),
    'M07 base reference omitted': ("return payload + wrapper_bytes(payload) + BASE_REFERENCE_BYTES + CODEC_METADATA_BYTES",
                                   "return payload + wrapper_bytes(payload) + CODEC_METADATA_BYTES"),
    'M08 N/A as 100%': ("return None if den == 0 else Fraction(num, den)", "return Fraction(1) if den == 0 else Fraction(num, den)"),
    'M09 oracle best substituted into retrieval': (
        "costs = [cost[t][b] for b in by_target[t]['bases'] if b in cost[t]]\n",
        "costs = [cost[t][b] for b in by_target[t]['bases'] if b in cost[t]] or "
        "([tr['O_delta']] if tr['O_delta'] is not None else [])\n"),
    'M10 denominator only successful targets': (
        "finite = [t for t in scored if targets[t]['delta_status'] == 'finite']",
        "finite = [t for t in scored if targets[t]['delta_status'] == 'finite' "
        "and set(by_target[t]['bases']) & set(targets[t]['ties'])]"),
    'M11 row order changes result': (
        "rows = sorted(({k: v for k, v in r.items() if k not in drop} for r in rows),\n"
        "                  key=lambda r: (r['target_occurrence_id'], r.get('base_object_id', '')))",
        "rows = [{k: v for k, v in r.items() if k not in drop} for r in rows]"),
    'M12 duplicate row silently collapsed': ("            reasons.add('DUPLICATE_PAIR')\n            continue\n",
                                             "            continue\n"),
    'M13 epsilon strict <': ("any(100 * c <= 100 * od", "any(100 * c < 100 * od"),
    'M14 64 B floor dropped': ("max(100 * TOLERANCE_FLOOR, e * od)", "e * od"),
    'M15 useful with <=': ("useful = od is not None and od < s", "useful = od is not None and od <= s"),
    'M16 normalized regret without floor': ("Fraction(regret[t], max(targets[t]['O'], TOLERANCE_FLOOR))",
                                            "Fraction(regret[t], targets[t]['O'] or 1)"),
    'M17 calls numerator from retrieval': ("ratio(sum(len(queries[t]['bases']) for t in scored), calls)",
                                           "ratio(sum(len(by_target[t]['bases']) for t in scored), calls)"),
    'M18 identity targets in near population': (
        "near = sorted(t for t, q in queries.items() if q['status'] == 'near_duplicate')", "near = sorted(queries)"),
    'M19 sealing not enforced': ("if (row['schema'] in SEALED) != (fact['split'] in sealed_splits):", "if False:"),
    'M20 missing pairs not counted': ("'missing': len(expected) - len(seen) + counts['not_run'],", "'missing': 0,"),
    'M21 accounting not checked': ("                != (wrapper_bytes(p), BASE_REFERENCE_BYTES, CODEC_METADATA_BYTES, delta_total(p)):",
                                   "                != (row['wrapper_bytes'], row['base_reference_bytes'], "
                                   "row['codec_metadata_bytes'], row['delta_total_bytes']):"),
    'M22 G1 from one run': ("if len({r['github_run_id'] for r in good}) < 2:", "if len({r['github_run_id'] for r in good}) < 1:"),
    'M23 G1 repeat mismatch ignored': ("if len({(r['cost_projection_sha256'], r['targets_sha256']) for r in complete}) > 1:",
                                       "if False:"),
    'M24 G1 invalid attempt outvoted': ("if any(r['run_status'] == 'INVALID' for r in runs):", "if False:"),
}


class Mutants(unittest.TestCase):
    def test_every_mutant_is_killed_by_the_vectors(self):
        self.assertEqual(kat_failures(), [])
        source = (HERE / 'oracle_reference.py').read_text(encoding='utf-8')
        for name, (old, new) in MUTANTS.items():
            with self.subTest(name):
                self.assertEqual(source.count(old), 1, 'mutant patch must match exactly once')
                module = types.ModuleType('oracle_reference_mutant')
                module.__file__ = str(HERE / 'oracle_reference.py')
                exec(compile(source.replace(old, new), module.__file__, 'exec'), module.__dict__)
                self.assertTrue(kat_failures(module), 'mutant survived every vector')


if __name__ == '__main__':
    unittest.main()
