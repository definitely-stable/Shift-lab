"""Committed mutation check of E1: the candidate builder and its independent verifier.

Each mutant is an exact one-substring change of tools/candidates.py or tools/candidate_verify.py that breaks a rule of
the frozen contract (corpus/e0/construction-spec.md sections 3-4). The mutated source is loaded under the real module
name, swapped into tests/test_e1_candidates.py, and a fast oracle subset of that suite must fail. The snippet count is
asserted to be exactly one so a mutant can never silently become a no-op. EQUIVALENT lists mutants proven to keep
behaviour; they must survive, which documents the known gap honestly.
"""
import copy
import sys
import types
import unittest
import unittest.mock
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent / 'tools'
sys.path[:0] = [str(TOOLS), str(HERE)]
import test_e1_candidates as t

MODULES = {'c': 'candidates', 'cv': 'candidate_verify'}
# Oracle subset: every class except Properties (slow, randomized) plus these fast sharp properties.
FAST_PROPERTIES = {'test_world_generator_is_not_vacuous', 'test_order_direction', 'test_two_independent_derivations',
                   'test_corruption_fails_closed', 'test_time_zones'}


class Gaps(t.Base):
    """Oracle checks the mutants showed missing from test_e1_candidates.py; they also run on the real modules."""

    def identity_world(self):
        fx = t.Fx().std('a')
        fx.add('a1', 'p0.c', 'X')
        target = fx.add('a2', 'p0.c', 'X')
        world = fx.world()
        return world, target, t.c.construct(world, t.P())

    def test_other_options_same_track_is_not_a_base(self):  # construction-spec section 3 options comparison
        fx = t.Fx().std('a')
        old, target = fx.add('a1', 'p0.c', 'X'), fx.add('a2', 'p0.c', 'X')
        old['provenance']['options'] = {'unit_bytes': 4096, 'other': 1}
        old['occurrence_id'] = t.m.occurrence_id('a1', old['provenance'])
        res = self.both(fx.world())
        self.assertEqual([(q['status'], q['bases']) for q in res['queries']], [('near_duplicate', [])])

    def test_compare_checks_duplicate_of(self):
        world, target, res = self.identity_world()
        ref = t.cv.derive(world, t.P())
        lock = {'planned_pairs_per_codec': 0, 'queries': copy.deepcopy(res['queries'])}
        self.assertEqual(t.cv.compare(ref, lock, res['selection']), [])
        lock['queries'][0]['duplicate_of'] = target['occurrence_id']
        self.has(t.cv.compare(ref, lock, res['selection']), 'field duplicate_of differs')

    def test_compare_checks_schedule_evidence(self):
        world, _, res = self.identity_world()
        sel = copy.deepcopy(res['selection'])
        sel['schedule']['rounds'] += 1
        self.has(t.cv.compare(t.cv.derive(world, t.P()), {'planned_pairs_per_codec': 0, 'queries': res['queries']}, sel),
                 'selection evidence schedule differs')

    def test_source_closure_checks_byte_sum(self):
        plan, policy, sl, lock = t.closed()
        lock['materialized_bytes'] += 1
        self.has(t.l1(plan, policy, sl, lock)[0], 'materialized_bytes differs')

    def test_zz_verify_compares_canonical_lock_bytes(self):  # a binding change leaves every query equal
        world, _, res = self.identity_world()
        ref, freeze_bytes = t.cv.derive(world, t.P()), (t.ROOT.parent / t.cv.E0_FREEZE[0]).read_bytes()
        bindings = t.m.loads_strict(freeze_bytes)['candidate_lock_bindings']
        lock = {'planned_pairs_per_codec': 0, 'queries': ref['queries'], 'schema': t.c.SCHEMA, **bindings,
                'protocol_sha256': '0' * 64}
        with unittest.mock.patch.object(t.cv, 'check_source_closure', lambda *a: ([], {})),                 unittest.mock.patch.object(t.cv, 'derive', lambda *a: ref):  # real inputs, stubbed heavy layers
            report = t.cv.verify(t.real_inputs(), freeze_bytes, t.m.canonical_bytes(lock), res['selection'])
        self.assertEqual(report['status'], 'mismatch')
        self.has(report['errors'], 'candidate lock bytes differ')


CLASSES = (t.IdentityAndAliases, t.PlanAncestryTime, t.Categories, t.Refusals, t.OrderingAndSchedule, t.Coverage,
           t.Properties, Gaps)

# (name, module, old snippet, new snippet)
MUTANTS = [
    ('duplicate_of max', 'c', 'duplicate_of[t["occurrence_id"]] = min(dups)', 'duplicate_of[t["occurrence_id"]] = max(dups)'),
    ('representative max (bases)', 'c', 'bases += [{"category": k, "object_id": x,\n                   "representative": min(',
     'bases += [{"category": k, "object_id": x,\n                   "representative": max('),
    ('representative max (witness row)', 'c', '"eligible_aliases": len(pool[x]), "object_id": x,\n                       "representative": min(',
     '"eligible_aliases": len(pool[x]), "object_id": x,\n                       "representative": max('),
    ('category witness max', 'c', 'min(b["occurrence_id"] for b in pool[x] if witness[k](b))',
     'max(b["occurrence_id"] for b in pool[x] if witness[k](b))'),
    ('time rule non-strict (builder)', 'c', 'and ib is not None and it is not None and ib[1] < it[0])',
     'and ib is not None and it is not None and ib[1] <= it[0])'),
    ('options comparison dropped', 'c', '\n                and b["provenance"]["options"] == t["provenance"]["options"]', ''),
    ('track comparison dropped', 'c', 'and b["track"] == t["track"]\n', '\n'),
    ('identity consumes near quota (builder)', 'c', 'queries.append(_query(tid, "identity_only", duplicate_of[tid], []))',
     'queries.append(_query(tid, "identity_only", duplicate_of[tid], []))\n                near += 1'),
    ('same-family precedence removed', 'c', 'elif any(b["family_id"] == t["family_id"] for b in aliases):', 'elif False:'),
    ('category precedence swapped', 'c',
     '        if any((b["family_id"], b["provenance"]["member_path"], b["provenance"]["offset"]) == position\n'
     '               for b in aliases):\n            by_category["same_path_historical"].append(x)\n'
     '        elif any(b["family_id"] == t["family_id"] for b in aliases):\n            by_category["same_family_decoy"].append(x)\n',
     '        if any(b["family_id"] == t["family_id"] for b in aliases):\n            by_category["same_family_decoy"].append(x)\n'
     '        elif any((b["family_id"], b["provenance"]["member_path"], b["provenance"]["offset"]) == position\n'
     '                 for b in aliases):\n            by_category["same_path_historical"].append(x)\n'),
    ('cap off by one (builder)', 'c', 'chosen = keyed[:caps[k]]', 'chosen = keyed[:caps[k] + 1]'),
    ('candidate rank secondary key dropped', 'c',
     'keyed = sorted((m.rank("candidate", seed, t["occurrence_id"], x), x) for x in by_category[k])',
     'keyed = sorted(((m.rank("candidate", seed, t["occurrence_id"], x), x) for x in by_category[k]), key=lambda p: p[0])'),
    ('group order reversed', 'c', 'order = sorted(groups, key=lambda g: (m.rank("target-group", seed, *g), g))',
     'order = sorted(groups, key=lambda g: (m.rank("target-group", seed, *g), g), reverse=True)'),
    ('target queue order by ID', 'c', 'key=lambda tid: (m.rank("target", seed, tid), tid)', 'key=lambda tid: tid'),
    ('X_U computed over time-known occurrences only (builder)', 'c', 'splits[o["object_id"]].add(o["split"])',
     'splits[o["object_id"]].add(o["split"]) if sources[o["source_id"]]["availability_interval_utc_seconds"] is not None else None'),
    ('stop condition over quota (builder)', 'c', 'if near >= params["max_targets"]:\n                break',
     'if near > params["max_targets"]:\n                break'),
    ('stop reason strict', 'c', '"near_quota" if near >= params["max_targets"] else "exhausted"',
     '"near_quota" if near > params["max_targets"] else "exhausted"'),
    ('list hash over reversed IDs', 'c', '"candidate_list_sha256": m.digest(ids),\n            "duplicate_of": duplicate',
     '"candidate_list_sha256": m.digest(sorted(ids, reverse=True)),\n            "duplicate_of": duplicate'),
    ('pool hash over unsorted IDs', 'c', '"pool_object_ids_sha256": m.digest(sorted(by_category[k]))',
     '"pool_object_ids_sha256": m.digest(by_category[k])'),
    ('lock accepts pairs above cap', 'c', 'or pairs > params["pairs_max"] or', 'or'),
    ('lock accepts no near query', 'c', 'if not near:\n        raise CandidateError("no near_duplicate', 'if False:\n        raise CandidateError("no near_duplicate'),
    # verifier
    ('verifier time rule non-strict', 'cv', 'and iv(b) is not None and iv(b)[1] < iv(t)[0])',
     'and iv(b) is not None and iv(b)[1] <= iv(t)[0])'),
    ('verifier duplicate_of max', 'cv', 'dup[t["occurrence_id"]] = ids[0]', 'dup[t["occurrence_id"]] = ids[-1]'),
    ('verifier representative max', 'cv', 'bases.append({"category": k, "object_id": x, "representative": ids[0]})',
     'bases.append({"category": k, "object_id": x, "representative": ids[-1]})'),
    ('verifier witness max', 'cv', '"category_witness": sorted(proof)[0]', '"category_witness": sorted(proof)[-1]'),
    ('verifier cap off by one', 'cv', 'keep = ranked[:cap]', 'keep = ranked[:cap + 1]'),
    ('verifier identity consumes near quota', 'cv', '"status": "identity_only", "target": tid}\n        else:',
     '"status": "identity_only", "target": tid}\n            near += 1\n        else:'),
    ('verifier category precedence swapped', 'cv',
     'pools[CATS[0] if here in positions else CATS[1] if t["family_id"] in families else CATS[2]].append(x)',
     'pools[CATS[1] if t["family_id"] in families else CATS[0] if here in positions else CATS[2]].append(x)'),
    ('verifier group order reversed', 'cv', 'params["seed"], g[0], g[1], g[2]]), g))', 'params["seed"], g[0], g[1], g[2]]), g), reverse=True)'),
    ('verifier compare ignores duplicate_of', 'cv', 'for field in sorted(set(want[tid]) | set(got[tid])):',
     'for field in sorted((set(want[tid]) | set(got[tid])) - {"duplicate_of"}):'),
    ('verifier compare ignores bases', 'cv', 'for field in sorted(set(want[tid]) | set(got[tid])):',
     'for field in sorted((set(want[tid]) | set(got[tid])) - {"bases"}):'),
    ('verifier compare ignores schedule evidence', 'cv', 'for part in ("targets", "schedule"):', 'for part in ("targets",):'),
    ('verifier source closure ignores missing positions', 'cv', 'for k in sorted(missing, key=repr)[:20]]', 'for k in []]'),
    ('verifier source closure ignores extra positions', 'cv', 'for k in sorted(extra, key=repr)[:20]]', 'for k in []]'),
    ('verifier source closure ignores byte sum', 'cv', 'if total != lock["materialized_bytes"]:', 'if False:'),
    ('verifier accounting temporal non-strict', 'cv', 'lambda b: iv(b)[1] >= iv(t)[0])', 'lambda b: iv(b)[1] > iv(t)[0])'),
    ('verifier stop condition over quota', 'cv', 'if near == params["max_targets"]:', 'if near > params["max_targets"]:'),
    ('verifier skips canonical byte comparison', 'cv', 'if canonical_bytes(expected_lock) != lock_bytes:', 'if False:'),
    ('verifier date interval lower bound', 'cv', 'return [day - 50400, day + 129600]', 'return [day - 46800, day + 129600]'),
]
EQUIVALENT = [
    # buckets by (split, track) in _select and X_U on raw U in identity already force equal splits
    ('split comparison dropped from builder eligible', 'c', 'and b["split"] == t["split"] and b["track"] == t["track"]',
     'and b["track"] == t["track"]'),
    # bases are re-sorted by object_id, so the order categories are visited in is unobservable
    ('category visit order reversed', 'c', '    for k in CATEGORIES:\n        keyed', '    for k in reversed(CATEGORIES):\n        keyed'),
]


def load(key, old, new):
    """Module from the mutated source of one tool, under its real name; not registered in sys.modules."""
    path = TOOLS / (MODULES[key] + '.py')
    source = path.read_text(encoding='utf-8')
    assert source.count(old) == 1, f'snippet occurs {source.count(old)} times: {old!r}'
    mutated = source.replace(old, new)
    assert mutated != source
    module = types.ModuleType(MODULES[key])
    module.__file__ = str(path)
    exec(compile(mutated, str(path), 'exec'), module.__dict__)
    return module


def oracle():
    """Cheap tests first (a killed mutant stops at its first failure), then fast properties, then the real-input check."""
    loader = unittest.TestLoader()
    tests = [cls(n) for cls in CLASSES for n in loader.getTestCaseNames(cls)
             if cls is not t.Properties or n in FAST_PROPERTIES]
    return unittest.TestSuite(sorted(tests, key=lambda x: 2 if 'test_zz' in x.id() else isinstance(x, t.Properties)))


class FirstFailure(unittest.TestResult):
    """Stops the run at the first failure or error: one is enough to kill a mutant."""

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.stop()

    addError = addFailure


def run(key=None, old=None, new=None):
    """TestResult of the oracle subset against the real modules, or with one of them mutated."""
    swap = {} if key is None else {key: load(key, old, new)}
    result = FirstFailure()
    with unittest.mock.patch.object(t, 'c', swap.get('c', t.c)), unittest.mock.patch.object(t, 'cv', swap.get('cv', t.cv)):
        oracle().run(result)
    return result


class MutantTests(unittest.TestCase):
    def test_unmutated_modules_pass_oracle(self):
        result = run()
        self.assertGreater(result.testsRun, 50)
        self.assertEqual(result.errors + result.failures, [])

    def test_every_mutant_is_killed(self):
        self.assertEqual(len({n for n, *_ in MUTANTS}), len(MUTANTS))
        for name, key, old, new in MUTANTS:
            with self.subTest(mutant=name):
                result = run(key, old, new)
                self.assertTrue(result.errors or result.failures, name + ' survived the oracle subset')

    def test_equivalent_mutants_survive(self):
        for name, key, old, new in EQUIVALENT:
            with self.subTest(mutant=name):
                result = run(key, old, new)
                self.assertEqual(result.errors + result.failures, [], name + ' is not equivalent after all')

    def test_both_modules_are_mutated(self):
        self.assertGreaterEqual(sum(k == 'cv' for _, k, *_ in MUTANTS), 5)


if __name__ == '__main__':
    unittest.main()
