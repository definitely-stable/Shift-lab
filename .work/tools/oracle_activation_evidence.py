"""DELSK-003A: read-only collectors and live re-check of the contract-v4 activation evidence (contract-v4 2). Activates
nothing.

    oracle_activation_evidence.py rulesets OUT.json    item 3: rulesets + effective rules, two equal reads
    oracle_activation_evidence.py genesis OUT.json     item 4: remote readback of the v4 production registry root
    oracle_activation_evidence.py refs OUT.json        registry refs: v4 append-only from its root, retired unchanged
    oracle_activation_evidence.py activity OUT.json    GitHub's server-side history of every registry ref
    oracle_activation_evidence.py recheck              live re-check of the committed evidence (CI)

Every collector reads only GitHub (constant API and remote of oracle_registry_v2) and writes canonical JSON. Nothing
here writes to GitHub, reads a natural byte, or sets ACTIVATION_RECORD. The enable record (.work/oracle/
activation-v4.json) binds the rulesets evidence that oracle_activation_v2.validate_record verifies; the other files are
supplementary proofs that a reviewer can regenerate. The v3 activation evidence (.work/oracle/activation/) is history:
v4 binds it by the hash of the v3 infra record and does not re-verify it with v4 constants (contract-v4 2).
"""
import datetime
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

import oracle_activation_v2 as act
import oracle_eval as ev
import oracle_g1_v2 as g1
import oracle_registry_git as rg
import oracle_registry_v2 as reg

API = f'{reg.PROVIDER_API}/repos/{reg.REPOSITORY}'
EVIDENCE = ev.ROOT / act.EVIDENCE_DIR
RULESET_REFS = ('refs/heads/main', reg.REGISTRY_REF, reg.SMOKE_REGISTRY_REF, *act.RETIRED_REGISTRY_REFS)
# Retired registry heads and roots, disclosed by activation-c1b-log.md (v2) and activation-v3-log.md (v3, with its one
# natural attempt as entry 1 of the production registry): v4 never writes them; they must never move.
RETIRED_HEADS = {'refs/heads/delsk/registry': '6cf2c6a7c35cee005f894366c97fca00230a5670',
                 'refs/heads/delsk/registry-smoke': 'd3ec84c7fd17ad613dc1e51463532b139e0ae864',
                 'refs/heads/delsk/registry-v3': '8343a55522c10e5c520ffa0806e50b90df712758',
                 'refs/heads/delsk/registry-v3-smoke': '479cc9d90ba88329cd5cc2bf2e7786b05a86ffc6'}
RETIRED_ROOTS = {'refs/heads/delsk/registry': '6cf2c6a7c35cee005f894366c97fca00230a5670',
                 'refs/heads/delsk/registry-smoke': 'a429d34d67959e49af8f79da024ce6eed34cbc13',
                 'refs/heads/delsk/registry-v3': '1a93f4ce71d9e4fbf5f21eaa9e66c660672ee258',
                 'refs/heads/delsk/registry-v3-smoke': '62f79c1ceeb4f61615039104532e8dee251efaa3'}
ZERO = '0' * 40


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


def _when(value):
    parsed = datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
    act.check(parsed.utcoffset() is not None, 'timestamp without offset')
    return parsed


# --- genesis review, live -------------------------------------------------------------------------------------------

def pinned_view(root, main):
    """TreeView pinned at `main`, built exactly as production builds it (oracle_registry_git.active_activation)."""
    def first_parent(commit):
        out = rg.git(root, 'rev-parse', '--verify', f'{commit}^1', check=False)
        return out.stdout.decode().strip() if out.returncode == 0 else None

    def on_main(commit):
        return type(commit) is str and ev.HEX40.match(commit) is not None and rg.git(
            root, 'merge-base', '--is-ancestor', commit, main, check=False).returncode == 0
    return act.TreeView(lambda path: rg.show(root, main, path), lambda commit, path: rg.show(root, commit, path),
                        on_main, first_parent)


def genesis_review(record, get=rg.api_get, root=ev.ROOT, main=None):
    """Genesis review live, as the enable path verifies it (verify_genesis_review): the recorded PR is merged into main
    by the recorded commit and itself introduced the reviewed production-root binding. Unavailable data is a problem."""
    try:
        main = main or rg.fetch(root, reg.REGISTRY_REMOTE, reg.SOURCE_REF)
        act.check(main is not None, 'main not found')
        return act.verify_genesis_review(record, get, pinned_view(root, main))
    except (TypeError, KeyError, AttributeError, ev.EvalError):
        return ['genesis review: provider or Git evidence unavailable']


# --- server-side ref history ---------------------------------------------------------------------------------------

def activity(refs=None):
    """GitHub's own record of every update of every registry ref (repository activity API, server timestamps)."""
    out = {'schema': 'delsk.oracle.registry-activity.v1', 'repository': reg.REPOSITORY, 'refs': {}}
    for ref in refs or (reg.REGISTRY_REF, *act.RETIRED_REGISTRY_REFS):
        items = get(f'/activity?per_page=100&direction=asc&ref={ref}')
        act.check(type(items) is list and len(items) < 100, 'activity listing pagination')
        out['refs'][ref] = [{'id': a['id'], 'ref': a['ref'], 'activity_type': a['activity_type'],
                             'before': a['before'], 'after': a['after'], 'timestamp': a['timestamp'],
                             'actor': {k: (a.get('actor') or {}).get(k) for k in ('login', 'type')}} for a in items]
    out['collected_at'] = now()
    return out


def activity_problems(doc, last_ruleset_change, heads):
    """Every registry ref was created once (from nothing to its root) and afterwards only fast-forwarded to its current
    head: no force push, no deletion, no gap in the before/after chain. The v4 registry was created after the last
    ruleset change by GitHub's clock, so it was protected from its first byte; the retired refs end at their disclosed
    heads."""
    problems = []
    roots = {reg.REGISTRY_REF: act.ROOT_COMMIT['production'], **RETIRED_ROOTS}
    for ref in (reg.REGISTRY_REF, *RETIRED_ROOTS):
        items = doc['refs'].get(ref) or []
        if not items:
            problems.append(f'{ref}: no server-side history')
            continue
        first = items[0]
        if not (first['activity_type'] == 'branch_creation' and first['before'] == ZERO
                and first['after'] == roots.get(ref) and first['ref'] == ref):
            problems.append(f'{ref}: not created from nothing at its reviewed root')
        for previous, item in zip(items, items[1:]):
            if not (item['activity_type'] == 'push' and item['before'] == previous['after'] and item['ref'] == ref
                    and _when(item['timestamp']) >= _when(previous['timestamp'])):
                problems.append(f"{ref}: update {item['id']} is not a fast-forward of the previous head")
        if items[-1]['after'] != heads.get(ref):
            problems.append(f'{ref}: server-side history does not end at the current head')
        if ref == reg.REGISTRY_REF and last_ruleset_change is not None and _when(first['timestamp']) <= \
                last_ruleset_change:
            problems.append(f'{ref}: created before the last ruleset change')
    for ref, head in RETIRED_HEADS.items():
        if heads.get(ref) != head:
            problems.append(f'{ref}: retired registry moved')
    return problems


# --- rulesets --------------------------------------------------------------------------------------------------------

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


def last_change(rulesets_doc):
    return max(_when(r['updated_at']) for r in rulesets_doc['rulesets'])


def rulesets_drift(committed, live):
    """Live rulesets against the committed evidence. Rules, targets and effective rules are visible to any reader;
    bypass_actors only to repository admins. Without them the live read cannot re-prove an empty bypass list: that
    stays proven by the admin-collected evidence, and a live read that shows bypass_actors must match it exactly."""
    problems = []
    visible = ('id', 'name', 'target', 'source_type', 'source', 'enforcement', 'conditions', 'rules', 'updated_at')

    # updated_at is rendered in the reader's profile time zone: compare the instant, not the string.
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
    return problems


# --- genesis and refs ------------------------------------------------------------------------------------------------

def genesis():
    """Remote readback of the v4 production registry root: fresh bare fetch, Git Data API, effective rules."""
    p = reg.PRODUCTION
    with tempfile.TemporaryDirectory() as tmp:
        gitdir = rg.init_bare(Path(tmp) / 'r.git')
        head = rg.fetch(gitdir, reg.REGISTRY_REMOTE, p.registry_ref)
        act.check(head is not None, f'{p.registry_ref} absent')
        root = rg.git(gitdir, 'rev-list', '--max-parents=0', head).decode().split()
        gen = rg.show(gitdir, root[0], reg.GENESIS_FILE) if len(root) == 1 else None
        entries = rg.show(gitdir, root[0], reg.ENTRIES_FILE) if len(root) == 1 else None
    doc = ev.parse_doc(gen) if gen is not None else None
    api_commit = get(f"/git/commits/{act.ROOT_COMMIT['production']}")
    api_tree = get(f"/git/trees/{api_commit['tree']['sha']}")
    rules = get(f'/rules/branches/{short(p.registry_ref)}?per_page=100')
    out = {'schema': 'delsk.oracle.registry-genesis-readback.v1', 'repository': reg.REPOSITORY,
           'ref': p.registry_ref, 'head': head, 'roots': root, 'expected_root': act.ROOT_COMMIT['production'],
           'genesis_json': doc, 'genesis_sha256': ev.hc(doc) if doc is not None else None,
           'expected_genesis_sha256': act.GENESIS_SHA256['production'],
           'api_root_tree': [{k: t[k] for k in ('path', 'mode', 'type', 'sha', 'size')} for t in api_tree['tree']],
           'effective_rules': sorted(x['type'] for x in rules)}
    checks = {
        'single root commit equal to the reviewed root': root == [act.ROOT_COMMIT['production']],
        'root has no parent': api_commit['parents'] == [],
        'root tree is exactly genesis.json and entries.jsonl (100644 blobs)':
            sorted(t['path'] for t in out['api_root_tree']) == [reg.ENTRIES_FILE, reg.GENESIS_FILE]
            and all(t['mode'] == '100644' and t['type'] == 'blob' for t in out['api_root_tree'])
            and not api_tree['truncated'],
        'root entries.jsonl is empty': entries == b'',
        'genesis.json is canonical and equals make_genesis': gen == rg.genesis_bytes(p),
        'g1_freeze_sha256 is freeze-v4': doc is not None and doc['g1_freeze_sha256'] == reg.G1_FREEZE_SHA256
            == ev.sha256((ev.ROOT / rg.FREEZE_V4).read_bytes()),
        'protected by deletion and non_fast_forward': {'deletion', 'non_fast_forward'} <= set(out['effective_rules'])}
    out['checks'] = checks
    out['problems'] = [k for k, v in checks.items() if not v]
    out['collected_at'] = now()
    return out


def refs():
    """Heads of main and every registry ref; retired refs at their disclosed heads with their disclosed roots; the v4
    registry linear from its reviewed root, every commit adding one entry line (append-only)."""
    out = {'schema': 'delsk.oracle.registry-refs.v1', 'repository': reg.REPOSITORY, 'refs': {}}
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        gitdir = rg.init_bare(Path(tmp) / 'r.git')
        out['main'] = rg.fetch(gitdir, reg.REGISTRY_REMOTE, reg.SOURCE_REF)
        for ref in (reg.REGISTRY_REF, *act.RETIRED_REGISTRY_REFS):
            head = rg.fetch(gitdir, reg.REGISTRY_REMOTE, ref)
            chain = rg.git(gitdir, 'rev-list', '--reverse', '--parents', head).decode().splitlines() if head else []
            lines = []
            for row in chain:
                sha, *parents = row.split()
                data = rg.show(gitdir, sha, reg.ENTRIES_FILE)
                lines.append({'commit': sha, 'parents': parents,
                              'entry_lines': None if data is None else data.count(b'\n')})
            linear = all(len(c['parents']) == (0 if i == 0 else 1)
                         and (i == 0 or c['parents'][0] == lines[i - 1]['commit']) for i, c in enumerate(lines))
            append_only = all(c['entry_lines'] == i for i, c in enumerate(lines))
            out['refs'][ref] = {'head': head, 'commits': len(lines), 'linear': linear,
                                'one_entry_per_commit': append_only}
            if ref in RETIRED_HEADS:
                if not (head == RETIRED_HEADS[ref] and lines and lines[0]['commit'] == RETIRED_ROOTS[ref] and linear):
                    problems.append(f'{ref}: retired registry moved or lost its disclosed history')
            elif head is not None and not (lines and lines[0]['commit'] == act.ROOT_COMMIT['production']
                                           and linear and append_only):
                problems.append(f'{ref}: not a linear append-only history from the reviewed root')
    out['problems'] = problems
    out['collected_at'] = now()
    return out


# --- recheck ---------------------------------------------------------------------------------------------------------

def enable_record_problems(get=rg.api_get, view=None):
    """Enable record, when the tree carries one: ACTIVATION_RECORD names its exact bytes, and the record verifies with
    the genesis review live (validate_activation), exactly as production checks it (activation_in_tree)."""
    path = ev.ROOT / act.ACTIVATION_FILE
    if g1.ACTIVATION_RECORD is None:
        return ['enable record present but ACTIVATION_RECORD is None'] if path.exists() else []
    if not path.is_file() or ev.sha256(path.read_bytes()) != g1.ACTIVATION_RECORD:
        return ['ACTIVATION_RECORD does not name the bytes of the enable record']
    view = view or act.local_view()
    problems = [f'enable record live: {p}' for p in act.validate_activation(ev.parse_doc(path.read_bytes()), view, get)]
    if not problems and act.activation_in_tree(view, get, g1.ACTIVATION_RECORD) is None:
        problems.append('activation_in_tree rejects the enable record')
    return problems


def recheck():
    """Live re-check of the committed evidence against GitHub now. Any drift, missing file or failed check: problems.
    Before the v4 rulesets evidence exists (adoption PR) only the retired refs and the absent enable record are
    checked."""
    problems = []
    live_refs = refs()
    problems += [f'refs live: {p}' for p in live_refs['problems']]
    heads = {ref: value['head'] for ref, value in live_refs['refs'].items()}
    path = EVIDENCE / 'rulesets.json'
    committed = ev.parse_doc(path.read_bytes()) if path.exists() else None
    if committed is not None:
        problems += [f'rulesets evidence: {p}' for p in act.verify_rulesets(committed)]
        problems += rulesets_drift(committed, rulesets())
    if heads.get(reg.REGISTRY_REF) is not None:
        problems += [f'genesis live: {p}' for p in genesis()['problems']]
    history = activity()
    created = heads.get(reg.REGISTRY_REF) is not None   # before genesis the v4 ref has no history to check
    last = last_change(committed) if committed is not None else None
    problems += [f'activity live: {p}' for p in activity_problems(history, last, heads)
                 if created or not p.startswith(reg.REGISTRY_REF)]
    record = ev.ROOT / act.ACTIVATION_FILE
    if record.exists():
        problems += [f'live: {p}' for p in genesis_review(ev.parse_doc(record.read_bytes()))]
    problems += enable_record_problems()
    return problems


def live_heads():
    return {ref: rg.ls_remote(ev.ROOT, reg.REGISTRY_REMOTE, ref)
            for ref in (reg.REGISTRY_REF, *act.RETIRED_REGISTRY_REFS)}


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
        committed = EVIDENCE / 'rulesets.json'
        doc['problems'] = activity_problems(doc, last_change(ev.parse_doc(committed.read_bytes()))
                                            if committed.exists() else None, live_heads())
    else:
        print(__doc__, file=sys.stderr)
        return 2
    rg.write_new(args[-1], ev.canonical(doc))
    failed = act.verify_rulesets(doc) if command == 'rulesets' else doc.get('problems') or []
    for p in failed:
        print(p)
    print('PASS' if not failed else f'FAIL: {len(failed)} problem(s)')
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
