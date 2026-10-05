"""DELSK-003A: read-only collectors and live re-check of the contract-v3 activation evidence (items 6-10). Activates nothing.

    oracle_activation_evidence.py rulesets OUT.json                    item 7: rulesets + effective rules, two equal reads
    oracle_activation_evidence.py genesis OUT.json                     item 6: remote readback of both v3 registry roots
    oracle_activation_evidence.py refs OUT.json                        registry refs: v2 preserved, v3 histories
    oracle_activation_evidence.py activity OUT.json                    GitHub's server-side history of every registry ref
    oracle_activation_evidence.py provider-raw OUT.json RUN_ID...       raw provider responses (disclosure only)
    oracle_activation_evidence.py semantics EVAL.json RAW.json OUT.json contract-v3 1.1-1.5 on the real smoke data
    oracle_activation_evidence.py recheck                              live re-check of the committed evidence (CI)

Every collector reads only GitHub (constant API and remote of oracle_registry_v2) and writes canonical JSON. Nothing
here writes to GitHub, reads a natural byte, or sets ACTIVATION_RECORD. The infra record (.work/oracle/activation/
infra.json) binds the evidence that oracle_activation_v2.validate_infra verifies; the other files are supplementary
proofs that a reviewer can regenerate. `semantics` runs the unmodified production classifier (oracle_g1_v2) on the
real observations; its counterfactuals only remove or weaken inputs or apply the frozen mutant rules PM14 and PM18, so
they can show fail-closed behaviour but never change a frozen rule.
"""
import copy
import datetime
import hashlib
import io
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import oracle_activation_v2 as act
import oracle_eval as ev
import oracle_g1_v2 as g1
import oracle_registry_git as rg
import oracle_registry_v2 as reg

API = f'{reg.PROVIDER_API}/repos/{reg.REPOSITORY}'
EVIDENCE = ev.ROOT / act.EVIDENCE_DIR
RULESET_REFS = ('refs/heads/main', reg.REGISTRY_REF, reg.SMOKE_REGISTRY_REF, *act.RETIRED_REGISTRY_REFS)
# Retired v2 registry heads disclosed by activation-c1b-log.md: v3 never writes them; they must never move.
V2_HEADS = {'refs/heads/delsk/registry': '6cf2c6a7c35cee005f894366c97fca00230a5670',
            'refs/heads/delsk/registry-smoke': 'd3ec84c7fd17ad613dc1e51463532b139e0ae864'}
V2_ROOTS = {'refs/heads/delsk/registry': '6cf2c6a7c35cee005f894366c97fca00230a5670',
            'refs/heads/delsk/registry-smoke': 'a429d34d67959e49af8f79da024ce6eed34cbc13'}


def now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def get(path, missing_ok=False):
    """GET API path; None for 404 only when missing_ok. No cache reuse: evidence must be a fresh read."""
    headers = {'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28',
               'Cache-Control': 'no-cache', 'User-Agent': 'delsk-evidence'}
    if os.environ.get('GITHUB_TOKEN'):
        headers['Authorization'] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    req = urllib.request.Request(API + path, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404 and missing_ok:
            return None
        raise


def short(ref):
    return ref.removeprefix('refs/heads/')


REGISTRY_REFS = (reg.REGISTRY_REF, reg.SMOKE_REGISTRY_REF, *act.RETIRED_REGISTRY_REFS)
ZERO = '0' * 40


# --- item 6: provenance of the reviewed genesis binding, live -----------------------------------------------------------

def pinned_view(root, main):
    """TreeView pinned at `main`, built exactly as production builds it (oracle_registry_git.production_inputs)."""
    def first_parent(commit):
        out = rg.git(root, 'rev-parse', '--verify', f'{commit}^1', check=False)
        return out.stdout.decode().strip() if out.returncode == 0 else None

    def on_main(commit):
        return type(commit) is str and ev.HEX40.match(commit) is not None and rg.git(
            root, 'merge-base', '--is-ancestor', commit, main, check=False).returncode == 0
    return act.TreeView(lambda path: rg.show(root, main, path), lambda commit, path: rg.show(root, commit, path),
                        on_main, first_parent)


def genesis_review(infra, get=rg.api_get, root=ev.ROOT, main=None):
    """Item 6 live, as the enable path verifies it (verify_genesis_review): the recorded PR is merged into main by the
    recorded commit and itself introduced the reviewed production-root binding. Unavailable data is a problem."""
    try:
        main = main or rg.fetch(root, reg.REGISTRY_REMOTE, reg.SOURCE_REF)
        act.check(main is not None, 'main not found')
        return act.verify_genesis_review(infra, get, pinned_view(root, main))
    except (TypeError, KeyError, AttributeError, ev.EvalError):
        return ['genesis review (item 6): provider or Git evidence unavailable']


# --- server-side ref history ---------------------------------------------------------------------------------------

def activity():
    """GitHub's own record of every update of every registry ref (repository activity API, server timestamps): when
    each ref was created and each later push."""
    out = {'schema': 'delsk.oracle.registry-activity.v1', 'repository': reg.REPOSITORY, 'refs': {}}
    for ref in REGISTRY_REFS:
        items = get(f'/activity?per_page=100&direction=asc&ref={ref}')
        act.check(type(items) is list and len(items) < 100, 'activity listing pagination')
        out['refs'][ref] = [{'id': a['id'], 'ref': a['ref'], 'activity_type': a['activity_type'],
                             'before': a['before'], 'after': a['after'], 'timestamp': a['timestamp'],
                             'actor': {k: (a.get('actor') or {}).get(k) for k in ('login', 'type')}} for a in items]
    out['collected_at'] = now()
    return out


def activity_problems(doc, last_ruleset_change, heads):
    """Every registry ref was created once (from nothing to its root) and afterwards only fast-forwarded to its current
    head: no force push, no deletion, no gap in the before/after chain. Each v3 ref was created after the last ruleset
    change by GitHub's clock, so it was protected from its first byte; the v3 production registry holds only genesis;
    the retired v2 refs still end at their disclosed heads."""
    problems = []
    roots = {reg.REGISTRY_REF: act.ROOT_COMMIT['production'], reg.SMOKE_REGISTRY_REF: act.ROOT_COMMIT['smoke'],
             **V2_ROOTS}
    for ref in REGISTRY_REFS:
        items = doc['refs'].get(ref) or []
        if not items:
            problems.append(f'{ref}: no server-side history')
            continue
        first = items[0]
        if not (first['activity_type'] == 'branch_creation' and first['before'] == ZERO
                and first['after'] == roots[ref] and first['ref'] == ref):
            problems.append(f'{ref}: not created from nothing at its reviewed root')
        for previous, item in zip(items, items[1:]):
            if not (item['activity_type'] == 'push' and item['before'] == previous['after'] and item['ref'] == ref
                    and _when(item['timestamp']) >= _when(previous['timestamp'])):
                problems.append(f"{ref}: update {item['id']} is not a fast-forward of the previous head")
        if items[-1]['after'] != heads.get(ref):
            problems.append(f'{ref}: server-side history does not end at the current head')
        if ref in (reg.REGISTRY_REF, reg.SMOKE_REGISTRY_REF) and _when(first['timestamp']) <= last_ruleset_change:
            problems.append(f'{ref}: created before the last ruleset change')
    if len(doc['refs'].get(reg.REGISTRY_REF) or []) != 1:
        problems.append(f'{reg.REGISTRY_REF}: production registry updated after genesis')
    for ref, head in V2_HEADS.items():
        if heads.get(ref) != head:
            problems.append(f'{ref}: retired v2 registry moved')
    return problems


# --- item 7 ----------------------------------------------------------------------------------------------------------

def _rulesets_read():
    listing = get('/rulesets?includes_parents=true&per_page=100')
    act.check(type(listing) is list and len(listing) < 100, 'ruleset listing pagination')
    rulesets = [get(f"/rulesets/{r['id']}") for r in sorted(listing, key=lambda r: r['id'])]
    effective = {}
    for ref in RULESET_REFS:
        rules = get(f'/rules/branches/{short(ref)}?per_page=100')
        act.check(type(rules) is list and len(rules) < 100, 'effective rules pagination')
        effective[ref] = rules
    return rulesets, effective


def rulesets():
    """delsk.oracle.rulesets-evidence.v1 (verify_rulesets input). Two consecutive full reads must agree, otherwise the
    configuration is changing or a read is stale: fail closed."""
    first, second = _rulesets_read(), _rulesets_read()
    act.check(ev.compact(list(first)) == ev.compact(list(second)), 'rulesets changed between two reads')
    return {'schema': act.RULESETS_SCHEMA, 'repository': reg.REPOSITORY, 'collected_at': now(),
            'rulesets': second[0], 'effective': second[1]}


# --- item 6 ----------------------------------------------------------------------------------------------------------

def genesis():
    """Remote readback of both v3 registry roots: fresh bare fetch, Git Data API, branch protection, registry_root()."""
    out = {'schema': 'delsk.oracle.registry-genesis-readback.v1', 'repository': reg.REPOSITORY,
           'g1_freeze_sha256': reg.G1_FREEZE_SHA256,
           'freeze_v3_sha256_in_tree': ev.sha256((ev.ROOT / rg.FREEZE_V3).read_bytes()), 'registries': {}}
    problems = []
    for p in reg.PROFILES:
        with tempfile.TemporaryDirectory() as tmp:
            gitdir = rg.init_bare(Path(tmp) / 'r.git')
            head = rg.fetch(gitdir, reg.REGISTRY_REMOTE, p.registry_ref)
            act.check(head is not None, f'{p.registry_ref} absent')
            root = rg.git(gitdir, 'rev-list', '--max-parents=0', head).decode().split()
            gen = rg.show(gitdir, root[0], reg.GENESIS_FILE) if len(root) == 1 else None
            entries = rg.show(gitdir, root[0], reg.ENTRIES_FILE) if len(root) == 1 else None
            raw = rg.git(gitdir, 'cat-file', 'commit', root[0]).decode() if len(root) == 1 else ''
            tree = rg.git(gitdir, 'ls-tree', '-r', '--long', root[0]).decode().splitlines() if len(root) == 1 else []
        doc = ev.parse_doc(gen) if gen is not None else None
        api_commit = get(f'/git/commits/{act.ROOT_COMMIT[p.name]}')
        api_tree = get(f"/git/trees/{api_commit['tree']['sha']}")
        branch = get(f'/branches/{short(p.registry_ref)}')
        rules = get(f'/rules/branches/{short(p.registry_ref)}?per_page=100')
        r = {'ref': p.registry_ref, 'head': head, 'roots': root, 'expected_root': act.ROOT_COMMIT[p.name],
             'root_commit_object': raw, 'root_tree': tree, 'genesis_json': doc,
             'genesis_sha256': ev.hc(doc) if doc is not None else None,
             'expected_genesis_sha256': act.GENESIS_SHA256[p.name], 'root_entries_jsonl_bytes': None if entries is None else len(entries),
             'registry_root': rg.registry_root(profile=p), 'api_root_parents': api_commit['parents'],
             'api_root_tree': [{k: t[k] for k in ('path', 'mode', 'type', 'sha', 'size')} for t in api_tree['tree']],
             'api_root_tree_truncated': api_tree['truncated'], 'branch_protected': branch['protected'],
             'effective_rules': sorted(x['type'] for x in rules),
             'effective_ruleset_ids': sorted({x['ruleset_id'] for x in rules})}
        checks = {
            'single root commit equal to the reviewed root': root == [act.ROOT_COMMIT[p.name]],
            'root has no parent': api_commit['parents'] == [] and '\nparent ' not in raw,
            'root tree is exactly genesis.json and entries.jsonl (100644 blobs)':
                sorted(t['path'] for t in r['api_root_tree']) == [reg.ENTRIES_FILE, reg.GENESIS_FILE]
                and all(t['mode'] == '100644' and t['type'] == 'blob' for t in r['api_root_tree'])
                and not api_tree['truncated'],
            'root entries.jsonl is empty': entries == b'',
            'genesis.json is canonical and equals make_genesis': gen == rg.genesis_bytes(p),
            'genesis_sha256 equals the reviewed constant': r['genesis_sha256'] == act.GENESIS_SHA256[p.name],
            'g1_freeze_sha256 binding of this profile': doc is not None and doc['g1_freeze_sha256'] == p.g1_freeze_sha256,
            'registry_root() returns the reviewed root': r['registry_root'] == act.ROOT_COMMIT[p.name],
            'branch protected by deletion and non_fast_forward': branch['protected'] is True
                and {'deletion', 'non_fast_forward'} <= set(r['effective_rules'])}
        r['checks'] = checks
        problems += [f'{p.name}: {k}' for k, v in checks.items() if not v]
        out['registries'][p.name] = r
    pg, sg = (out['registries'][n]['genesis_json'] or {} for n in ('production', 'smoke'))
    out['production_g1_freeze_is_freeze_v3'] = out['freeze_v3_sha256_in_tree'] == reg.G1_FREEZE_SHA256 \
        == pg.get('g1_freeze_sha256')
    out['domain_separated'] = pg.get('g1_freeze_sha256') != sg.get('g1_freeze_sha256') \
        and pg.get('registry_ref') != sg.get('registry_ref') \
        and act.GENESIS_SHA256['production'] != act.GENESIS_SHA256['smoke']
    problems += [k for k in ('production_g1_freeze_is_freeze_v3', 'domain_separated') if not out[k]]
    out['problems'] = problems
    out['collected_at'] = now()
    return out


# --- registry refs ---------------------------------------------------------------------------------------------------

def refs():
    """Heads of main and every registry ref; v2 refs unchanged; v3 histories linear from their reviewed roots, every
    commit adding one entry line (append-only); smoke registry authoritative under the smoke profile."""
    out = {'schema': 'delsk.oracle.registry-refs.v1', 'repository': reg.REPOSITORY, 'refs': {}}
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        gitdir = rg.init_bare(Path(tmp) / 'r.git')
        main = rg.fetch(gitdir, reg.REGISTRY_REMOTE, reg.SOURCE_REF)
        out['main'] = main
        for ref in (reg.REGISTRY_REF, reg.SMOKE_REGISTRY_REF, *act.RETIRED_REGISTRY_REFS):
            head = rg.fetch(gitdir, reg.REGISTRY_REMOTE, ref)
            chain = rg.git(gitdir, 'rev-list', '--reverse', '--parents', head).decode().splitlines() if head else []
            lines = []
            for row in chain:
                sha, *parents = row.split()
                data = rg.show(gitdir, sha, reg.ENTRIES_FILE)
                lines.append({'commit': sha, 'parents': parents,
                              'entry_lines': None if data is None else data.count(b'\n'),
                              'subject': rg.git(gitdir, 'log', '-1', '--format=%s', sha).decode().strip()})
            linear = all(len(c['parents']) == (0 if i == 0 else 1) and (i == 0 or c['parents'][0] == lines[i - 1]['commit'])
                         for i, c in enumerate(lines))
            append_only = all(c['entry_lines'] == i for i, c in enumerate(lines))
            out['refs'][ref] = {'head': head, 'commits': lines, 'linear': linear, 'one_entry_per_commit': append_only}
            if ref in V2_HEADS:
                ok = head == V2_HEADS[ref] and lines and lines[0]['commit'] == V2_ROOTS[ref] and linear
                if not ok:
                    problems.append(f'{ref}: retired v2 registry moved or lost its disclosed history')
            else:
                profile = reg.PRODUCTION if ref == reg.REGISTRY_REF else reg.SMOKE
                if not (lines and lines[0]['commit'] == act.ROOT_COMMIT[profile.name] and linear and append_only):
                    problems.append(f'{ref}: not a linear append-only history from the reviewed root')
                if profile is reg.SMOKE:
                    snap = rg.snapshot(ev.ROOT, main, rg.referenced_commits(rg.lenient(rg.registry_history(gitdir, head))[1]))
                    try:
                        reg.authoritative_registry(rg.registry_history(gitdir, head), snap, reg.SMOKE)
                        out['refs'][ref]['authoritative'] = True
                    except (reg.RegistryInvalid, TypeError):
                        out['refs'][ref]['authoritative'] = False
                        problems.append(f'{ref}: REGISTRY_INVALID')
    out['production_registry_entries'] = len(out['refs'][reg.REGISTRY_REF]['commits']) - 1
    if out['production_registry_entries'] != 0:
        problems.append('production registry v3 is not genesis-only')
    out['problems'] = problems
    out['collected_at'] = now()
    return out


# --- smoke disclosure and semantics -----------------------------------------------------------------------------------

def provider_raw(run_ids):
    """Raw provider documents of every attempt and every jobs page of the given run IDs (404 recorded as null)."""
    out = {'schema': 'delsk.oracle.provider-raw.v1', 'repository': reg.REPOSITORY, 'responses': {}}
    for run_id in run_ids:
        path = f'/actions/runs/{run_id}'
        run = get(path, missing_ok=True)
        out['responses'][path] = run
        for n in range(1, (run or {}).get('run_attempt', 0) + 1):
            out['responses'][f'{path}/attempts/{n}'] = get(f'{path}/attempts/{n}', missing_ok=True)
            page = 1
            while True:
                query = f'{path}/attempts/{n}/jobs?per_page=100&page={page}'
                doc = get(query)
                out['responses'][query] = doc
                if len(doc['jobs']) < 100:
                    break
                page += 1
    out['collected_at'] = now()
    return out


def _key(e):
    return e['run_id'], e['run_attempt']


def semantics(evaluation, raw):
    """Contract-v3 1.1-1.5 (A-F of the activation review) checked on the real smoke observations."""
    with tempfile.TemporaryDirectory() as tmp:
        gitdir = rg.init_bare(Path(tmp) / 'r.git')
        head = rg.fetch(gitdir, reg.REGISTRY_REMOTE, reg.SMOKE_REGISTRY_REF)
        _, entries = rg.lenient(rg.registry_history(gitdir, head))
    main = evaluation['main_head_sha']
    reference = ev.sha256(rg.show(ev.ROOT, main, reg.SMOKE_WORKFLOW_PATH))
    sources = {e['measured_source_sha'] for e in entries}
    witnessed = {c for c in sources if (b := rg.show(ev.ROOT, c, reg.SMOKE_WORKFLOW_PATH)) is not None
                 and ev.sha256(b) == reference}
    provider = {(o['run_id'], o['run_attempt']): o for o in evaluation['provider']}
    scenario = {r['scenario']: (r['run_id'], r['run_attempt']) for r in evaluation_scenarios(evaluation)}

    def classes(prov, wit, pre=None):
        out = {}
        for e in entries:
            name = f"{e['run_id']}-{e['run_attempt']}"
            if pre is None:
                out[name] = g1.classify(e, prov.get(_key(e)), None, None, False, wit)[0]
            else:
                out[name] = 'PRE' if e['measured_source_sha'] in wit and pre(prov.get(_key(e)), e) else 'MISSING'
        return out

    def unbound(prov, wit):
        return [f"{u['run_id']}-{u['run_attempt']}" for u in g1.unbound_attempts(entries, prov, wit)]

    def pm14(observation, e):   # frozen mutant PM14 (v2 rule): provider steps are not exempt
        observation = copy.deepcopy(observation)
        for job in ((observation or {}).get('run') or {}).get('jobs', []):
            for step in job['steps']:
                if step['role'] == 'provider':
                    step['role'] = 'other'
        return g1.pre_proven(observation, e)

    def k(name):
        return '%d-%d' % scenario[name]

    base = classes(provider, witnessed)
    out = {'schema': 'delsk.oracle.v3-smoke-semantics.v1', 'smoke_registry_head': head, 'main_head_sha': main,
           'smoke_workflow_sha256': reference, 'witnessed_sources': sorted(witnessed), 'classes': base,
           'unbound': unbound(provider, witnessed)}
    checks = {}
    cbr = scenario['cancel-before-register']
    jobs = raw['responses'][f'/actions/runs/{cbr[0]}/attempts/{cbr[1]}/jobs?per_page=100&page=1']['jobs']
    measure = [j for j in jobs if j['name'] == 'measure'][0]
    checks['A raw measure: cancelled, steps=[], runner_id and runner_name reported and null'] = (
        measure['conclusion'] == 'cancelled' and measure['steps'] == [] and 'runner_id' in measure
        and 'runner_name' in measure and measure['runner_id'] is None and measure['runner_name'] is None)
    normalized = [j for j in provider[cbr]['run']['jobs'] if j['name'] == 'measure'][0]
    checks['A normalized measure: started, runner_assigned=false'] = (normalized['runner_assigned'] is False
                                                                       and normalized['started'] is True)
    checks['A never-ran rule accepts it'] = act._never_ran(normalized)
    assigned = {**normalized, 'runner_assigned': True}
    checks['A the same job with a runner is not never-ran (PM18 shape)'] = not act._never_ran(assigned)
    names = {s['name'] for path, doc in raw['responses'].items() if '/jobs' in path and doc
             for j in doc['jobs'] for s in j['steps']}
    out['provider_like_step_names_observed'] = sorted(n for n in names if n.startswith('Post ')
                                                      or n in ('Complete job', 'Set up job'))
    checks['B observed Post/Complete step names equal the closed provider set'] = {
        n for n in names if n.startswith('Post ') or n == 'Complete job'} == set(act.SMOKE_PROVIDER_STEPS)
    checks['B GitHub created no Post step for upload-artifact'] = \
        'Post Retain binding sidecar before the boundary' not in names
    checks['B smoke set == pilot set == {Complete job, Post Read-only source checkout}'] = \
        set(act.SMOKE_PROVIDER_STEPS) == set(act.PILOT_PROVIDER_STEPS) == {'Complete job',
                                                                            'Post Read-only source checkout'}
    checks['C every entry source carries the exact witnessed workflow bytes'] = witnessed == sources
    none = classes(provider, set())
    out['counterfactual_unwitnessed'] = {'classes': none, 'unbound': unbound(provider, set())}
    checks['C unwitnessed source: every entry MISSING'] = set(none.values()) == {'MISSING'}
    checks['C unwitnessed source: the rerun-failed attempt is no longer PRE-proven (unbound)'] = \
        k('rerun-failed') in out['counterfactual_unwitnessed']['unbound']
    checks['D rerun-all: new registered attempt classified PRE'] = base[k('rerun-all')] == 'PRE'
    checks['D rerun-failed: no entry and not unbound'] = k('rerun-failed') not in out['unbound'] \
        and scenario['rerun-failed'] not in map(_key, entries)
    checks['D rerun-failed attempt is PRE-proven against every entry of its run'] = all(
        g1.pre_proven(provider[scenario['rerun-failed']], e) for e in entries
        if e['run_id'] == scenario['rerun-failed'][0])
    v2_rule = classes(provider, witnessed, pm14)
    out['counterfactual_pm14_v2_rule'] = v2_rule
    checks['D/PM14 the v2 rule would make stop-before-boundary, rerun-all and cancel-after-register MISSING'] = all(
        v2_rule[k(n)] == 'MISSING' for n in ('stop-before-boundary', 'rerun-all', 'cancel-after-register'))
    cross = provider[scenario['cross-boundary']]
    checks['E cross-boundary: boundary started, MISSING'] = base[k('cross-boundary')] == 'MISSING' \
        and g1.boundary_started(cross['run'])
    widened = copy.deepcopy(cross)
    for job in widened['run']['jobs']:
        for step in job['steps']:
            if step['role'] == 'other':
                step['role'] = 'provider'
    checks['E cross-boundary is not PRE even if every other step were a provider step'] = not g1.pre_proven(
        widened, [e for e in entries if _key(e) == scenario['cross-boundary']][0])
    checks['F deleted run: run=null and MISSING'] = provider[scenario['deleted-run']]['run'] is None \
        and base[k('deleted-run')] == 'MISSING'
    empty = classes({}, witnessed)
    out['counterfactual_no_observations'] = empty
    checks['F no provider observations: every entry MISSING'] = set(empty.values()) == {'MISSING'}
    rank = {'MISSING': 0, 'PRE': 1}
    checks['F dropping any single observation never improves a class'] = all(
        rank[c] <= rank[base[x]] for drop in provider
        for x, c in classes({kk: v for kk, v in provider.items() if kk != drop}, witnessed).items())
    out['checks'] = checks
    out['collected_at'] = now()
    return out


def evaluation_scenarios(evaluation):
    return ev.parse_doc((EVIDENCE / 'smoke-scenarios.json').read_bytes())['runs']


# --- CI re-check -----------------------------------------------------------------------------------------------------

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def artifact_bytes(artifact_id):
    """Zip bytes of an Actions artifact: the API answers with a redirect to signed storage, which is fetched without
    the API credential."""
    headers = {'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28',
               'User-Agent': 'delsk-evidence'}
    if os.environ.get('GITHUB_TOKEN'):
        headers['Authorization'] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(urllib.request.Request(f'{API}/actions/artifacts/{artifact_id}/zip', headers=headers),
                         timeout=30) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        if error.code not in (301, 302, 303, 307, 308) or not error.headers.get('Location'):
            raise
        with urllib.request.urlopen(error.headers['Location'], timeout=60) as response:
            return response.read()


def _when(value):
    parsed = datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
    act.check(parsed.utcoffset() is not None, 'timestamp without offset')
    return parsed


def provenance(committed_rulesets, scenarios, write_surface_bytes):
    """The runs behind items 8-10 are what the evidence says: exact workflow, dispatch on main at the evidenced
    source, every attempt started after the last ruleset change, and the committed write-surface document is
    byte for byte the artifact GitHub holds for its run (zip digest as reported by GitHub)."""
    problems = []
    last_change = max(_when(r['updated_at']) for r in committed_rulesets['rulesets'])
    ws = ev.parse_doc(write_surface_bytes)
    runs = [(r['run_id'], r['run_attempt'], act.SMOKE_WORKFLOW) for r in scenarios['runs']
            if r['scenario'] != 'deleted-run']
    runs.append((ws['run_id'], ws['run_attempt'], act.WRITE_SURFACE_WORKFLOW))
    for run_id, attempt, workflow in runs:
        doc = get(f'/actions/runs/{run_id}/attempts/{attempt}', missing_ok=True)
        if not (type(doc) is dict and doc.get('id') == run_id and doc.get('run_attempt') == attempt
                and doc.get('path') == workflow and doc.get('event') == 'workflow_dispatch'
                and doc.get('head_branch') == 'main' and doc.get('status') == 'completed'):
            problems.append(f'run {run_id}/{attempt}: not a completed dispatch of {workflow} on main')
            continue
        if _when(doc['run_started_at']) <= last_change:
            problems.append(f'run {run_id}/{attempt}: started before the last ruleset change')
    listing = get(f"/actions/runs/{ws['run_id']}/artifacts?per_page=100")
    if listing.get('total_count') != len(listing.get('artifacts', [])):
        return problems + ['write-surface artifact listing incomplete']
    name = f"registry-write-surface-{ws['run_id']}-{ws['run_attempt']}"
    hits = [a for a in listing.get('artifacts', []) if a.get('name') == name]
    if len(hits) != 1 or hits[0].get('expired') or not str(hits[0].get('digest', '')).startswith('sha256:'):
        return problems + ['write-surface artifact unavailable (expired or ambiguous): cannot re-prove item 10']
    data = artifact_bytes(hits[0]['id'])
    if 'sha256:' + hashlib.sha256(data).hexdigest() != hits[0]['digest']:
        problems.append('write-surface artifact bytes differ from the digest GitHub reports')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if archive.namelist() != ['write-surface.json'] or archive.read('write-surface.json') != write_surface_bytes:
            problems.append('committed write-surface.json is not the artifact of its run')
    return problems


def _drop(doc, *keys):
    return {k: v for k, v in doc.items() if k not in keys}


def recheck():
    """Live re-check of the committed evidence against GitHub now. Any drift, missing file or failed check: problems."""
    problems = []
    infra = ev.parse_doc((ev.ROOT / act.INFRA_FILE).read_bytes())
    problems += [f'infra: {p}' for p in act.validate_infra(infra, act.local_view())]
    committed = ev.parse_doc((EVIDENCE / 'rulesets.json').read_bytes())
    problems += [f'rulesets evidence: {p}' for p in act.verify_rulesets(committed)]
    live = rulesets()
    # Rules, targets and effective rules are visible to any reader; bypass_actors only to repository admins. Without
    # them the live read cannot re-prove an empty bypass list: that stays proven by the admin-collected evidence only,
    # and a live read that does show bypass_actors must still match it exactly.
    visible = ('id', 'name', 'target', 'source_type', 'source', 'enforcement', 'conditions', 'rules', 'updated_at')
    # updated_at is rendered in the reader's profile time zone (admin read: +05:00, workflow token: UTC): compare
    # the instant, not the string.
    def shape(doc, admin):
        return [{k: _when(r[k]).astimezone(datetime.timezone.utc) if k == 'updated_at' else r.get(k)
                 for k in visible + (('bypass_actors',) if admin else ())} for r in doc['rulesets']]
    admin = all('bypass_actors' in r for r in live['rulesets'])
    seen, kept = shape(live, admin), shape(committed, admin)
    if [r['id'] for r in seen] != [r['id'] for r in kept]:
        problems.append('ruleset list changed since the evidence was collected')
    for a, b in zip(seen, kept):
        problems += [f"ruleset {b['id']} field {k} differs from the evidence" for k in a if a[k] != b[k]]
    for ref in RULESET_REFS:
        if live['effective'].get(ref) != committed['effective'].get(ref):
            problems.append(f'effective rules of {ref} differ from the evidence: {live["effective"].get(ref)}')
    if admin:
        problems += [f'rulesets live: {p}' for p in act.verify_rulesets(live)]
    else:
        print('note: bypass_actors not visible to this credential; empty bypass rests on the admin-collected evidence')
    scenarios = ev.parse_doc((EVIDENCE / 'smoke-scenarios.json').read_bytes())
    smoke = rg.smoke_evaluation(ev.ROOT, scenarios=scenarios)
    recorded = ev.parse_doc((EVIDENCE / 'smoke-evaluation.json').read_bytes())
    # main may move after this record merges; the smoke classification may not (witness: smoke workflow bytes)
    if _drop(smoke, 'main_head_sha') != _drop(recorded, 'main_head_sha'):
        problems.append('live smoke evaluation differs from the committed evidence')
    problems += provenance(committed, scenarios, (EVIDENCE / 'write-surface.json').read_bytes())
    problems += [f'smoke live: {p}' for p in act.verify_smoke(smoke, scenarios)]
    problems += [f'genesis live: {p}' for p in genesis()['problems']]
    live_refs = refs()
    problems += [f'refs live: {p}' for p in live_refs['problems']]
    committed_refs = ev.parse_doc((EVIDENCE / 'registry-refs.json').read_bytes())
    for ref, value in committed_refs['refs'].items():
        if live_refs['refs'].get(ref, {}).get('head') != value['head']:
            problems.append(f'{ref} moved since the evidence was collected')
    sem = semantics(ev.parse_doc((EVIDENCE / 'smoke-evaluation.json').read_bytes()),
                    ev.parse_doc((EVIDENCE / 'smoke-provider-raw.json').read_bytes()))
    problems += [f'semantics: {name}' for name, ok in sem['checks'].items() if not ok]
    problems += [f'live: {p}' for p in genesis_review(infra)]
    heads = {ref: value['head'] for ref, value in live_refs['refs'].items()}
    history = activity()
    problems += [f'activity live: {p}' for p in activity_problems(history, last_change(committed), heads)]
    if history['refs'] != ev.parse_doc((EVIDENCE / 'registry-activity.json').read_bytes())['refs']:
        problems.append('server-side registry history changed since the evidence was collected')
    return problems


def last_change(rulesets_doc):
    return max(_when(r['updated_at']) for r in rulesets_doc['rulesets'])


def live_heads():
    return {ref: rg.ls_remote(ev.ROOT, reg.REGISTRY_REMOTE, ref) for ref in REGISTRY_REFS}


def main(argv):
    command, args = (argv[0], argv[1:]) if argv else (None, [])
    if command == 'recheck' and not args:
        problems = recheck()
        for p in problems:
            print(p)
        print('PASS' if not problems else f'FAIL: {len(problems)} problem(s)')
        return 0 if not problems else 1
    if command in ('rulesets', 'genesis', 'refs') and len(args) == 1:
        doc = {'rulesets': rulesets, 'genesis': genesis, 'refs': refs}[command]()
    elif command == 'activity' and len(args) == 1:
        doc = activity()
        doc['problems'] = activity_problems(doc, last_change(ev.parse_doc((EVIDENCE / 'rulesets.json').read_bytes())),
                                            live_heads())
    elif command == 'provider-raw' and len(args) >= 2 and all(a.isdigit() for a in args[1:]):
        doc = provider_raw([int(a) for a in args[1:]])
    elif command == 'semantics' and len(args) == 3:
        doc = semantics(*(ev.parse_doc(Path(a).read_bytes()) for a in args[:2]))
    else:
        print(__doc__, file=sys.stderr)
        return 2
    rg.write_new(args[-1] if command != 'provider-raw' else args[0], ev.canonical(doc))
    failed = act.verify_rulesets(doc) if command == 'rulesets' else \
        doc.get('problems') or [k for k, v in doc.get('checks', {}).items() if not v]
    for p in failed:
        print(p)
    print('PASS' if not failed else f'FAIL: {len(failed)} problem(s)')
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
