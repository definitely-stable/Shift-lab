"""Test-only adapter: frozen registry-vectors-v3.json cases -> immutable inputs of the v3 G1 core.

Feeds the vector *inputs* (registry, provider observations, evidence, environment) to the implementation; expected
records are only ever compared against, never returned. The vectors' generator was never committed and is not used.
"""
import copy
import sys
from pathlib import Path

WORK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORK / 'tools'))
import oracle_eval as ev
import oracle_g1_v2 as g1

VECTORS = ev.parse_doc((WORK / 'oracle' / 'registry-vectors-v3.json').read_bytes())
CASES = [c for v in VECTORS['vectors'] for c in v['cases']]
BY_ID = {c['id']: c for c in CASES}


def environment(case):
    env = dict(VECTORS['environment'])
    env.update(case['environment_override'] or {})
    return env


def git_snapshot(env, module=g1, main_head=None):
    return module.reg.GitSnapshot.build(main_head or env['main_head'],
                                        {c['sha']: c['ancestors'] for c in env['commits']},
                                        {s['sha']: s['measurement_identity'] for s in env['sources']})


def evaluation(case, module=g1):
    env, x = environment(case), case['evidence']
    return module.Evaluation.build(
        genesis=case['registry']['genesis'], entries=case['registry']['entries'],
        registry_reread=case['registry_remote_head'], git=git_snapshot(env, module),
        main_reread=case['main_remote_head'], provider=case['provider'], pull_requests=env['pull_requests'],
        evidence=module.Evidence.build(x['bundles'], x['bindings'], x['foreign_paths'],
                                       [(k['run_id'], k['run_attempt']) for k in x['v1_root_keys']]),
        evaluator_source_sha=env['evaluator_source_sha'], kat_green=env['kat_green'])


def results(case, module=g1):
    """[(expectation, core verdict, test record)] computed by `module` for every expected identity of the case."""
    x = evaluation(case, module)
    analysis = module.analyze(x)
    return [(e, *module.g1_test(e['measurement_identity_sha256'], x, analysis)) for e in case['expect']]


def mismatches(module=g1, ids=None):
    """Case ids whose computed core verdict or full record (hence record_sha256) differs from the frozen expectation.
    An exception inside the implementation also counts as a mismatch."""
    bad = []
    for case in CASES if ids is None else [BY_ID[i] for i in ids]:
        try:
            if any(v != e['core_verdict'] or r != e['record'] for e, v, r in results(case, module)):
                bad.append(case['id'])
        except Exception:  # a crashing mutant is killed
            bad.append(case['id'])
    return bad


def variant(case_id, **changes):
    """Deep copy of a frozen case with top-level fields replaced (adversarial tests build on frozen inputs)."""
    case = copy.deepcopy(BY_ID[case_id])
    case.update(copy.deepcopy(changes))
    return case


def redigest(case, sidecars=True):
    """Re-chain a case after its entries were edited, deleted or appended: sequences, chain links, entry digests and
    the re-read remote head. sidecars=True also rewrites every retained sidecar to the new chain (an adversary that
    controls the registry and the reviewed results root); sidecars=False leaves retained evidence as it was."""
    reg = g1.reg
    genesis, entries = case['registry']['genesis'], case['registry']['entries']
    moved = {reg.run_key(e): e['sequence'] for e in entries}
    previous = ev.hc(genesis)
    for number, e in enumerate(entries, 1):
        e.update(sequence=number, previous_entry_sha256=previous)
        e['entry_sha256'] = ev.hc(reg.without(e, 'entry_sha256'))
        previous = e['entry_sha256']
    chain = reg.history(genesis, entries)
    by_key = {reg.run_key(e): e for e in entries}
    for b in case['evidence']['bindings'] if sidecars else ():
        e = by_key.get(reg.run_key(b))
        if e is not None:
            lag = b['observed_head']['sequence'] - moved[reg.run_key(e)]
            seen = min(len(chain) - 1, max(0, e['sequence'] + lag))
            b.update(entry_sequence=e['sequence'], entry_sha256=e['entry_sha256'],
                     observed_head={'sequence': seen, 'entry_sha256': chain[seen]})
            b['binding_sha256'] = ev.hc(reg.without(b, 'binding_sha256'))
    case['registry_remote_head'] = reg.head(genesis, entries)
    return case
