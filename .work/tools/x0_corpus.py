"""DELSK-002 X0 screening corpus: acquisition, representations and C_t (.work/corpus/x0/README.md).

Exploratory screening only: not a corpus lock of pilot-v1, not oracle evidence of contract v4. The frozen modules
`manifests.py` and `materialize.py` are imported and never changed (their bytes are part of the v4 science identity).

    x0_corpus.py build <store-dir> <out-dir>   download, materialize, build C_t (GitHub Actions only)
    x0_corpus.py check                          validate the committed source plan and params
"""

import gzip
import hashlib
import json
import sys
from fractions import Fraction
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import manifests as m  # noqa: E402
import materialize as mat  # noqa: E402

WORK = TOOLS.parent
X0 = WORK / 'corpus' / 'x0'
PARAMS_PATH, PLAN_PATH = X0 / 'params.json', X0 / 'source-plan.json'
PARAMS = json.loads(PARAMS_PATH.read_bytes())
CORPUS_SCHEMA = 'delsk.x0.corpus.v1'
CANDIDATES_SCHEMA = 'delsk.x0.candidates.v1'
PLAN_SCHEMA = 'delsk.x0.source-plan.v1'
CLASSES = tuple(sorted(PARAMS['classes']))
ARCHIVE_FORMATS = ('tar.gz', 'tar.xz', 'tar.bz2')
EXPANDED_MAX = 512 << 20
M64 = (1 << 64) - 1
SPLIT = 'development'  # X0 families are development-only forever (burn rule, README section 3)


class X0Error(Exception):
    pass


def check(ok, reason):
    if not ok:
        raise X0Error(reason)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def file_sha256(path):
    return sha256(Path(path).read_bytes())


# --- source plan ------------------------------------------------------------------------------------------------

def validate_plan(plan):
    """Errors of the X0 source plan (empty list when valid)."""
    errors = []

    def need(ok, reason):
        if not ok:
            errors.append(reason)
    need(plan.get('schema') == PLAN_SCHEMA, 'plan schema')
    families = plan.get('families', [])
    need(sorted(f['family_id'] for f in families) == [f['family_id'] for f in families], 'families not sorted')
    need(len({f['family_id'] for f in families}) == len(families), 'duplicate family')
    releases = set()
    for f in families:
        fid = f['family_id']
        need(bool(m.IDENT.match(fid)), f'{fid}: family id')
        need(f.get('class') in CLASSES, f'{fid}: class')
        need(m._https(f.get('license', {}).get('evidence_url')) and f['license'].get('spdx'), f'{fid}: license')
        for rule in f.get('exclude_globs', []):
            need(bool(rule.get('glob')) and bool(rule.get('reason')), f'{fid}: exclusion needs glob and reason')
        if f.get('class') == 'H4':
            need(m.valid_member_path(f.get('install_path') or '') and '/' not in f['install_path'],
                 f'{fid}: install_path')
            need(not f.get('exclude_globs'), f'{fid}: binaries have no path exclusions')
        rs = f.get('releases', [])
        need(len(rs) == 4 and [r['ordinal'] for r in rs] == [1, 2, 3, 4], f'{fid}: four releases, ordinals 1-4')
        spans = []
        for r in rs:
            rid = r['release_id']
            need(rid not in releases and bool(m.IDENT.match(rid)), f'{rid}: release id')
            releases.add(rid)
            need(m._https(r.get('url')), f'{rid}: https url')
            need(r.get('format') in (*ARCHIVE_FORMATS, *(('binary',) if f.get('class') == 'H4' else ())),
                 f'{rid}: format')
            need(m._https(r.get('time', {}).get('evidence_url')), f'{rid}: time evidence')
            need(bool(r.get('branch')) and bool(r.get('version')), f'{rid}: branch and version')
            if f.get('class') == 'H4':
                need((r['format'] == 'binary') == (r.get('member') is None), f'{rid}: member iff archive')
            else:
                need(r.get('member') is None, f'{rid}: source releases have no member')
            try:
                spans.append(m.availability(r['time']))
            except (ValueError, KeyError):
                errors.append(f'{rid}: time')
        if len(spans) == len(rs) and None not in spans:
            need(all(spans[i][1] < spans[i + 1][0] for i in range(len(spans) - 1)),
                 f'{fid}: releases must be strictly chronological by availability interval')
        if f.get('class') == 'H1' and len(rs) == 4:
            b = [r['branch'] for r in rs]
            need(b[0] == b[2] and b[1] == b[3] and b[0] != b[1], f'{fid}: H1 order must be A1 < B1 < A2 < B2')
    return errors


def load_plan(path=PLAN_PATH):
    plan = json.loads(Path(path).read_bytes())
    errors = validate_plan(plan)
    check(not errors, 'source plan: ' + '; '.join(errors))
    return plan


# --- representations --------------------------------------------------------------------------------------------

def strata():
    return [{'id': f'{lo}-{hi}', 'min_bytes': lo, 'max_bytes': hi} for lo, hi in PARAMS['file_strata']]


def member_policy():
    return {'member_rules': {'include_suffixes': PARAMS['source_suffixes'], 'global_exclude_globs': []},
            'file_strata': strata(), 'seed': PARAMS['seed']}


def _gear(seed):
    out = []
    for i in range(256):
        z = (seed + (i + 1) * 0x9e3779b97f4a7c15) & M64
        z = ((z ^ (z >> 30)) * 0xbf58476d1ce4e5b9) & M64
        z = ((z ^ (z >> 27)) * 0x94d049bb133111eb) & M64
        out.append(z ^ (z >> 31))
    return out


GEAR = _gear(PARAMS['cdc']['seed'])


def cdc_spans(data, bits=None, lo=None, hi=None, gear=GEAR):
    """Gear content-defined chunking (README section 4.1): [(offset, length)] covering data exactly."""
    c = PARAMS['cdc']
    bits = c['bits'] if bits is None else bits
    lo = c['min_bytes'] if lo is None else lo
    hi = c['max_bytes'] if hi is None else hi
    shift = 64 - bits
    spans, start, n = [], 0, len(data)
    while start < n:
        end = min(n, start + hi)
        cut, h, i = end, 0, start
        # bytes before the minimum length cannot cut, but they still feed the rolling hash
        while i < end:
            h = ((h << 1) + gear[data[i]]) & M64
            i += 1
            if i - start >= lo and h >> shift == 0:
                cut = i
                break
        spans.append((start, cut - start))
        start = cut
    return spans


def _occurrence(family, release, track, path, data, offset, stratum, parent=None, options=None):
    provenance = {'member_path': path, 'transform': track, 'options': options, 'offset': offset,
                  'length': len(data)}
    span = m.availability(release['time'])
    return {'occurrence_id': m.occurrence_id(release['release_id'], provenance), 'object_id': sha256(data),
            'bytes': len(data), 'source_id': release['release_id'], 'family_id': family['family_id'],
            'class': family['class'], 'split': SPLIT, 'track': track, 'stratum': stratum,
            'provenance': provenance, 'parent_object_id': parent['object_id'] if parent else None,
            'parent_bytes': parent['bytes'] if parent else None, 'ordinal': release['ordinal'],
            'branch': release['branch'], 'version': release['version'], 'available': list(span)}


def file_members(family, release, body):
    """[(member_path, stratum, data)] of the file track and the exclusions of one release."""
    if family['class'] == 'H4':
        if release['format'] == 'binary':
            data = body
        else:
            entries, _ = mat.expand(body, release['format'], EXPANDED_MAX)
            hits = [e for e in entries if e[0].lstrip('./') == release['member'].lstrip('./')]
            check(len(hits) == 1 and hits[0][1] == 'file', f"{release['release_id']}: member {release['member']!r} "
                                                           'must be exactly one regular file')
            data = hits[0][2]
        stratum = m.stratum_of(len(data), strata())
        if stratum is None:
            return [], [{'source_id': release['release_id'], 'path': family['install_path'], 'reason': 'oversize'
                         if len(data) >= PARAMS['file_strata'][-1][1] else 'undersize', 'detail': str(len(data))}]
        return [(family['install_path'], stratum, data)], []
    entries, _ = mat.expand(body, release['format'], EXPANDED_MAX)
    _, members = mat.normalize(entries)
    rows = [{'source_id': release['release_id'], 'family_id': family['family_id'], 'path': x['path'],
             'size': x['size'], 'type': x['type']} for x in members]
    globs = {family['family_id']: [g['glob'] for g in family.get('exclude_globs', [])]}
    picked = m.select_members(rows, member_policy(), globs)
    for e in picked['exclusions']:
        check(e['reason'] != 'non_regular_member' or m.path_exclusion(e['path'], family['family_id'],
                                                                       member_policy(), globs) is not None,
              f"{release['release_id']}: non-regular member on a retained path {e['path']!r}")
    data = {x['path']: x['data'] for x in members}
    oversize = [{'source_id': release['release_id'], 'path': x['path'], 'reason': 'oversize', 'detail': str(x['size'])}
                for x in picked['retained'] if x['size'] >= PARAMS['file_strata'][-1][1]]
    return [(x['path'], x['stratum'], data[x['path']]) for x in picked['selected']], oversize


def materialize(plan, store, fetcher=mat.fetch, log=print, plan_sha256=None):
    """Download every release, write file-track and CDC objects into `store`; corpus metadata (no payload)."""
    store = Path(store)
    store.mkdir(parents=True, exist_ok=True)
    acquired = materialized = 0
    sources, occurrences, exclusions, spans_of = [], [], [], {}
    c = PARAMS['cdc']
    cdc_options = {'bits': c['bits'], 'max_bytes': c['max_bytes'], 'min_bytes': c['min_bytes'], 'seed': c['seed']}

    def put(data):
        path = store / sha256(data)
        if not path.exists():
            path.write_bytes(data)
    for family in plan['families']:
        for release in family['releases']:
            body, final, attempts = fetcher(release['url'], PARAMS['acquired_bytes_max'] - acquired)
            acquired += len(body)
            sources.append({'source_id': release['release_id'], 'family_id': family['family_id'],
                            'url': release['url'], 'final_url': final, 'attempts': attempts,
                            'archive_bytes': len(body), 'archive_sha256': sha256(body)})
            members, excluded = file_members(family, release, body)
            exclusions += excluded
            for path, stratum, data in members:
                parent = _occurrence(family, release, 'file', path, data, 0, stratum)
                occurrences.append(parent)
                put(data)
                materialized += len(data)
                key = sha256(data)
                if key not in spans_of:
                    spans_of[key] = cdc_spans(data)
                for offset, length in spans_of[key]:
                    chunk = data[offset:offset + length]
                    occurrences.append(_occurrence(family, release, c['track'], path, chunk, offset, stratum,
                                                   parent, cdc_options))
                    put(chunk)
                    materialized += length
                check(materialized <= PARAMS['materialized_bytes_max'], 'materialized bytes exceed the cap')
            log(f"{release['release_id']}: {len(body)} B, {len(members)} file objects")
    occurrences.sort(key=lambda o: o['occurrence_id'])
    check(len({o['occurrence_id'] for o in occurrences}) == len(occurrences), 'duplicate occurrence position')
    return {'schema': CORPUS_SCHEMA, 'params_sha256': file_sha256(PARAMS_PATH), 'plan_sha256': plan_sha256 or file_sha256(PLAN_PATH),
            'acquired_bytes': acquired, 'materialized_bytes': materialized, 'toolchain': mat.toolchain(),
            'x0_corpus_sha256': file_sha256(__file__), 'sources': sources,
            'exclusions': sorted(exclusions, key=lambda e: (e['source_id'], e['path'])), 'occurrences': occurrences}


# --- C_t ----------------------------------------------------------------------------------------------------------

def cell_of(o):
    return f"{o['class']}-{'file' if o['track'] == 'file' else 'cdc'}"


def _rel(o):
    return Fraction(o['provenance']['offset'], o['parent_bytes'] or o['bytes'])


def query(t, by_track):
    """Status, duplicate and categorized C_t of one target occurrence (README section 4, items 4 and 6)."""
    seed, caps = PARAMS['seed'], PARAMS['candidate_caps']
    eligible = [b for b in by_track[t['track']] if m.time_eligible(b['available'], t['available'])]
    same = [b for b in eligible if b['object_id'] == t['object_id']]
    if same:
        return {'status': 'identity_only', 'duplicate_of': min(b['occurrence_id'] for b in same), 'bases': []}
    classes = {}
    for b in eligible:
        classes.setdefault(b['object_id'], []).append(b)
    pools = {k: [] for k in m.CANDIDATE_CATEGORIES}
    path = t['provenance']['member_path']
    for oid, aliases in classes.items():
        same_path = [a for a in aliases if a['family_id'] == t['family_id'] and a['provenance']['member_path'] == path]
        if same_path:
            category = 'same_path_historical'
        elif any(a['family_id'] == t['family_id'] for a in aliases):
            category = 'same_family_decoy'
        else:
            category = 'foreign_family_decoy'
        rank = m.rank('candidate', seed, t['occurrence_id'], oid)
        if category == 'same_path_historical' and t['track'] != 'file':
            key = (min(abs(_rel(a) - _rel(t)) for a in same_path), rank, oid)
        else:
            key = (rank, oid)
        pools[category].append((key, oid, min(a['occurrence_id'] for a in aliases)))
    bases, pool_sizes = [], {}
    for category in m.CANDIDATE_CATEGORIES:
        pool = sorted(pools[category])
        pool_sizes[category] = len(pool)
        bases += [{'object_id': oid, 'representative': rep, 'category': category}
                  for _, oid, rep in pool[:caps[category]]]
    return {'status': 'near_duplicate', 'duplicate_of': None, 'pool_sizes': pool_sizes,
            'bases': sorted(bases, key=lambda b: b['object_id'])}


def build_candidates(corpus):
    """Targets per cell by round-robin, C_t, measurement order and the compute-cap prefix."""
    seed, quota = PARAMS['seed'], PARAMS['cell_quota']
    occ = corpus['occurrences']
    by_id = {o['occurrence_id']: o for o in occ}
    by_track = {}
    for o in occ:
        by_track.setdefault(o['track'], []).append(o)
    sizes = {o['object_id']: o['bytes'] for o in occ}
    visited, near = [], {cell: [] for cell in PARAMS['cells']}
    for cell in PARAMS['cells']:
        groups = {}
        for o in occ:
            if o['ordinal'] in PARAMS['target_ordinals'] and cell_of(o) == cell:
                groups.setdefault((o['family_id'], o['stratum']), []).append(o)
        order = sorted(groups, key=lambda g: (m.rank('target-group', seed, cell, *g), g))
        queues = {g: sorted(groups[g], key=lambda o: (m.rank('target', seed, o['occurrence_id']),
                                                       o['occurrence_id'])) for g in order}
        seen_objects = set()
        while len(near[cell]) < quota and any(queues.values()):
            for g in order:
                if len(near[cell]) >= quota or not queues[g]:
                    continue
                t = queues[g].pop(0)
                if t['object_id'] in seen_objects:
                    visited.append({'target': t['occurrence_id'], 'cell': cell, 'status': 'repeat_target',
                                    'duplicate_of': None, 'bases': []})
                    continue
                seen_objects.add(t['object_id'])
                q = {'target': t['occurrence_id'], 'cell': cell, **query(t, by_track)}
                visited.append(q)
                if q['status'] == 'near_duplicate':
                    near[cell].append(q)
    order, cost, budget = [], 0, PARAMS['encode_bytes_max']
    for i in range(quota):
        for cell in PARAMS['cells']:
            if i < len(near[cell]):
                order.append(near[cell][i])
    measured = set()
    truncated = False
    for q in order:
        tb = by_id[q['target']]['bytes']
        need = tb + sum(sizes[b['object_id']] + tb for b in q['bases'])
        if truncated or cost + need > budget:
            truncated = True
            continue
        cost += need
        measured.add(q['target'])
    queries = []
    for q in visited:
        out = dict(q)
        out['measure_rank'] = next((i for i, x in enumerate(order) if x['target'] == q['target']), None)
        out['measured'] = q['target'] in measured
        out['candidate_count'] = len(q['bases'])
        out['candidate_list_sha256'] = m.digest(sorted(b['object_id'] for b in q['bases']))
        queries.append(out)
    queries.sort(key=lambda q: q['target'])
    coverage = {cell: {'visited': sum(1 for q in queries if q['cell'] == cell),
                       'identity_only': sum(1 for q in queries if q['cell'] == cell and q['status'] == 'identity_only'),
                       'repeat_target': sum(1 for q in queries if q['cell'] == cell and q['status'] == 'repeat_target'),
                       'near': len(near[cell]),
                       'measured': sum(1 for q in near[cell] if q['target'] in measured)}
                for cell in PARAMS['cells']}
    return {'schema': CANDIDATES_SCHEMA, 'corpus_sha256': m.digest(corpus), 'params_sha256': corpus['params_sha256'],
            'encode_bytes_planned': cost, 'compute_cap_truncated': truncated,
            'planned_pairs': sum(len(q['bases']) for q in queries if q['measured']), 'coverage': coverage,
            'queries': queries}


def main(argv):
    if argv[:1] == ['check'] and len(argv) == 1:
        load_plan()
        print('source plan OK')
        return 0
    if argv[:1] == ['build'] and len(argv) == 3:
        plan = load_plan()
        corpus = materialize(plan, argv[1])
        candidates = build_candidates(corpus)
        out = Path(argv[2])
        out.mkdir(parents=True, exist_ok=True)
        (out / 'corpus.json.gz').write_bytes(gzip.compress(m.canonical_bytes(corpus), mtime=0))
        (out / 'candidates.json').write_bytes(m.canonical_bytes(candidates))
        print(json.dumps(candidates['coverage'], sort_keys=True))
        print(f"planned pairs {candidates['planned_pairs']}, encode bytes {candidates['encode_bytes_planned']}, "
              f"truncated {candidates['compute_cap_truncated']}")
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
