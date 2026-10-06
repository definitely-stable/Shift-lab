"""DELSK-003A C1-A: executable mutation obligations PM01-PM20 (contract-v2 section 15, contract-v3 section 4.4).

Each mutant is one exact single-occurrence source change of oracle_g1_v2.py or oracle_registry_v2.py that breaks one
semantic rule. The mutated modules are loaded from source and run on the frozen vector *inputs*; a mutant is killed
when at least one vector named in its frozen `killed_by` list stops reproducing (core verdict, full record and
record_sha256, the R17 API expectation or the R12/R21 runner expectation). A surviving mutant fails this test.
"""
import inspect
import sys
import types
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import oracle_v2_vectors as V
from oracle_v2_vectors import BY_ID, VECTORS
import oracle_g1_v2 as g1
import oracle_registry_v2 as reg

G1, REG = Path(g1.__file__), Path(reg.__file__)

# contract-v3 1.3 item 4: cancelled measure job without steps and without a runner never started
RULE = ("or (measure[0]['conclusion'] == 'cancelled'\n"
        "                                                     and not measure[0]['steps']\n"
        "                                                     and measure[0]['runner_assigned'] is False):\n")
WITNESS = "    if violations or e['measured_source_sha'] not in witnessed:\n"

MUTANTS = {
    'PM01': [(G1, "    if v1_verdict != 'INVALID' and missing:\n", "    if False and missing:\n")],
    'PM02': [(G1, "    mine = [e for e in a.entries if e['measurement_identity_sha256'] == identity]\n",
              "    mine = [e for e in a.entries if e['measurement_identity_sha256'] == identity\n"
              "            and a.classes[reg.run_key(e)]['class'] == 'BUNDLE']\n")],
    'PM03': [(G1, "        if len(set(found)) != len(found) or not set(found) <= keys:\n",
              "        if len(set(found)) != len(found):\n")],
    'PM04': [(G1, "    if run is None or not run_binding(run, e) or run['status'] != 'completed':\n",
              "    if run is None or not run_binding(run, e):\n"),                                    # pending run
             (G1, "    if bundle is None and pre_proven(observation, e):\n",
              "    if bundle is None and (binding is not None or pre_proven(observation, e)):\n"),   # sidecar
             (G1, "    if not set(names) <= set(reg.JOBS) or names.count('measure') > 1:\n",
              "    if names.count('measure') > 1:\n")],                                            # unknown job
    'PM05': [(G1, "    return {'github_run_id': e['run_id'], 'run_status': bundle['run_status'],\n",
              "    return {'github_run_id': (e['run_id'], e['run_attempt']), 'run_status': bundle['run_status'],\n")],
    'PM06': [(REG, "        require(e['previous_entry_sha256'] == previous, f'{where}: previous_entry_sha256 breaks the chain')\n",
              ""),
             (REG, "        require(self_digest_ok(e, 'entry_sha256'), f'{where}: entry_sha256 != Hc(entry)')\n", ""),
             (REG, "        require(e['sequence'] == number, f'{where}: sequence gap or repeat')\n", "")],
    'PM07': [(G1, "TEST_VERDICT = {'SCIENTIFIC_PASS': 'TEST_ONLY_PASS'}\n",
              "TEST_VERDICT = {'SCIENTIFIC_PASS': 'PASS'}\n"),                                      # test core says PASS
             (G1, "    if ACTIVATION_RECORD is None and verdict in ('SCIENTIFIC_PASS', 'NOT_PASSED'):\n",
              "    if False:\n"),                                                                   # gate dropped
             (G1, "def g1_production(measurement_identity_sha256):\n",
              "def g1_production(measurement_identity_sha256, provider=None):\n"),                  # injectable
             (G1, "    return 'NOT_PASSED', ['V4_NOT_ACTIVE']\n",
              "    return 'PASS', []\n")],                                                          # production PASS
    'PM08': [(G1, "        if e['measurement_identity_sha256'] == identity or c['class'] == 'PRE':\n",
              "        if True:\n"),                                                                  # no sibling codes
             (G1, "        elif c['class'] == 'MISSING' or c['outcome'] in ('INCOMPLETE', 'COMPLETE_WITH_FAILURES') or \\\n",
              "        elif c['outcome'] in ('INCOMPLETE', 'COMPLETE_WITH_FAILURES') or \\\n"),          # proposal defect
             (G1, "    if len(repeats) > 1:\n", "    if False:\n")],                                # no series repeat
    'PM09': [(G1, "    if binding is not None and binding['observed_head']['sequence'] < e['sequence']:\n",
              "    if False:\n"),
             (G1, "    if bundle is not None and binding is None:\n", "    if False:\n"),
             (G1, "    if bundle is not None and run is not None and not bound_before_boundary(run):\n",
              "    if False:\n"),
             (G1, "            if n in keys or all(e['measured_source_sha'] in witnessed"
                  " and pre_proven(provider.get((run_id, n)), e)\n                                for e in es):\n",
              "            if True:\n")],
    'PM10': [(G1, "            elif s != p['current'] and s not in p['orphans']:\n"
                  "                p['orphans'].add(s)\n"
                  "                taint[s].add('SERIES_TRANSITION_MISSING')\n",
              "            elif s != p['current'] and s not in p['orphans']:\n"
                  "                p['retired'].add(p['current'])\n"
                  "                p['current'] = s\n"),                                          # silent reset
             (G1, "        if transition_bytes is None:\n            return 'TRANSITION_REQUIRED', None\n",
              "        if False:\n            return 'TRANSITION_REQUIRED', None\n")],              # register lets it in
    'PM11': [(G1, "    if not {mine[0]['measured_source_sha'], a.evaluator_source_sha} <= a.kat_green:\n",
              "    if not {mine[0]['measured_source_sha']} <= a.kat_green:\n"),
             (G1, "    if not {mine[0]['measured_source_sha'], a.evaluator_source_sha} <= a.kat_green:\n",
              "    if not {a.evaluator_source_sha} <= a.kat_green:\n"),
             (G1, "    green = frozenset(c for c in x.kat_green if git.on_main(c))\n",
              "    green = frozenset(x.kat_green)\n")],
    'PM12': [(G1, "                         ('MAIN_STALE', lambda: reg.stale(git.main_head_sha, x.main_reread)),\n",
              "                         ('MAIN_STALE', lambda: False),\n"),                            # not re-read
             (G1, "            'science_identity_sha256': None, 'main_head_sha': a.main_head_sha,",
              "            'science_identity_sha256': None, 'main_head_sha': evaluation.main_reread,")],  # floating
    # contract-v3 section 1.3 item 4 (provider steps, cancelled measure job without steps)
    'PM13': [(G1, "and s['role'] != 'provider')\n", "and False)\n")],                         # every step exempt
    'PM14': [(G1, "and s['role'] != 'provider')\n", ")\n")],                                  # v2 rule
    'PM15': [(G1, RULE, "or False:\n")],
    'PM16': [(G1, RULE, "or measure[0]['conclusion'] == 'cancelled':\n")],
    'PM17': [(G1, RULE, "or not measure[0]['steps']:\n")],
    'PM18': [(G1, RULE, "or (measure[0]['conclusion'] == 'cancelled' and not measure[0]['steps']):\n")],
    # contract-v3 1.5: the executed workflow must be the activated one for PRE and for BUNDLE
    'PM19': [(G1, WITNESS, "    if violations or (e['measured_source_sha'] not in witnessed\n"
                           "                      and bundle is not None):\n")],
    'PM20': [(G1, WITNESS, "    if violations or (e['measured_source_sha'] not in witnessed\n"
                           "                      and bundle is None):\n")],
}


def load(path=None, old=None, new=None):
    """oracle_g1_v2 (over oracle_registry_v2) compiled from source, with at most one substring replaced."""
    sources = {p: p.read_text(encoding='utf-8') for p in (REG, G1)}
    if path is not None:
        sources[path] = sources[path].replace(old, new)
    modules = {}
    saved = sys.modules.get('oracle_registry_v2')
    try:
        for p, name in ((REG, 'oracle_registry_v2'), (G1, 'oracle_g1_v2')):
            module = types.ModuleType(name)
            module.__file__ = str(p)
            sys.modules['oracle_registry_v2'] = modules.get('oracle_registry_v2', saved)
            exec(compile(sources[p], str(p), 'exec'), module.__dict__)
            if name == 'oracle_g1_v2':
                # R17 api and PM07 are judged in the pre-activation state (contract-v4 2), whatever main carries
                module.ACTIVATION_RECORD = None
            modules[name] = module
    finally:
        sys.modules['oracle_registry_v2'] = saved
    return modules['oracle_g1_v2']


def api_failures(module):
    """R17 api expectation: production takes only the identity and is never PASS; test record never PASS."""
    case = BY_ID['R17']
    identity = case['expect'][0]['measurement_identity_sha256']
    out = []
    if list(inspect.signature(module.g1_production).parameters) != case['api']['production_parameters']:
        out.append('signature')
    try:
        if module.g1_production(identity) != ('NOT_PASSED', ['V4_NOT_ACTIVE']):
            out.append('production verdict')
        x = V.evaluation(case, module)
        verdict, body = module._g1_core(identity, x)
        if verdict == 'PASS' or module._production_record(verdict, body, '0' * 40)['verdict'] == 'PASS':
            out.append('production PASS')
        if module.g1_test(identity, x)[1]['verdict'] != case['api']['test_pass_vocabulary']:
            out.append('test vocabulary')
    except Exception as error:  # a crashing mutant is killed
        out.append(type(error).__name__)
    return out


def runner_failures(module, case):
    r = case['runner']
    genesis, entries = case['registry']['genesis'], case['registry']['entries']
    git = V.git_snapshot(V.environment(case), module)
    mine = [e for e in entries if (e['run_id'], e['run_attempt']) == (r['run_id'], r['run_attempt'])]
    ex = {'event': 'workflow_dispatch', 'repository': reg.REPOSITORY, 'run_id': r['run_id'],
          'run_attempt': r['run_attempt'], 'workflow_ref': entries[0]['workflow_ref']}
    try:
        if r['register'] != 'NOT_RUN':
            sha = mine[0]['measured_source_sha']
            got = module.register_check_test(genesis, entries[:mine[0]['sequence'] - 1], {**ex, 'sha': sha,
                                        'workflow_sha': sha}, git, VECTORS['environment']['pull_requests'])[0]
            return got != r['register']
        sha = entries[0]['measured_source_sha']
        return module.bind_check_test(genesis, entries, {**ex, 'sha': sha, 'workflow_sha': sha}, git, '0' * 64)[0] != r['bind']
    except Exception:
        return True


def killers(module, ids):
    bad = set(V.mismatches(module, ids))
    if 'R17' in ids and api_failures(module):
        bad.add('R17')
    bad |= {i for i in ids if BY_ID[i]['runner'] and runner_failures(module, BY_ID[i])}
    return bad


class Mutants(unittest.TestCase):
    def test_harness_reproduces_everything_unmutated(self):
        module = load()
        self.assertEqual(V.mismatches(module), [])
        self.assertEqual(api_failures(module), [])
        self.assertFalse([c['id'] for c in V.CASES if c['runner'] and runner_failures(module, c)])

    def test_every_frozen_mutant_is_killed(self):
        frozen = {m['id']: m['killed_by'] for m in VECTORS['mutants']}
        self.assertEqual(sorted(MUTANTS), sorted(frozen))
        for pm, variants in MUTANTS.items():
            for n, (path, old, new) in enumerate(variants, 1):
                with self.subTest(f'{pm}.{n}'):
                    self.assertEqual(path.read_text(encoding='utf-8').count(old), 1, 'patch must match exactly once')
                    killed = killers(load(path, old, new), frozen[pm])
                    self.assertTrue(killed, f'{pm}.{n} survived {frozen[pm]}')


if __name__ == '__main__':
    unittest.main()
