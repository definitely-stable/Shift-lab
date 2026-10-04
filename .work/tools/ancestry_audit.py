"""E0 provenance evidence on exact Slice D archives; no candidate/scorer/encoder.

Only the CLI acquires data, and only in the bounded Actions foundation job.
Payload stays in memory. Outputs are identities, provenance quotations, token
locations and exact normalized-text overlap hashes, not natural corpus files.
This audit supplies leads for review; it never decides lineage independence.
"""
import base64
import collections
import hashlib
import itertools
import json
import os
from pathlib import Path
import re
import sys

import manifests as m
import materialize as mz

WINDOW_LINES = 12
WINDOW_MIN_BYTES = 240
REPORT_CAP = 12 << 20
ORIGIN_MARKER = re.compile(
    r'copyright|based (?:on|upon)|derived from|adapted from|borrowed from|'
    r'copied from|taken from|originally (?:written|from|by)|'
    r'automatically generated|generated (?:by|from)|public domain', re.I)
TOKENS = {
    'bzip2': r'\bbzip2\b|\bbzlib\b', 'curl': r'\bcurl\b',
    'libpng': r'\blibpng\b', 'sqlite': r'\bsqlite\b',
    'zlib': r'\bzlib\b', 'zstd': r'\bzstd\b|\bzstandard\b',
    'libtomcrypt': r'\blibtomcrypt\b|Tom St Denis',
    'libmicrohttpd': r'\blibmicrohttpd\b',
    'xxhash': r'\bxxhash\b|\bXXH(?:32|64|128)',
    'finite_state_entropy': r'FiniteStateEntropy|Finite State Entropy',
    'unicode': r'\bUnicode\b|CaseFolding\.txt',
    'keccak': r'\bKeccak\b', 'lz4': r'\bLZ4\b',
    'openssl': r'\bOpenSSL\b', 'sha1': r'\bSHA-?1\b',
}


def analyze_members(members, families):
    """Deterministic evidence over every retained (source,path), with no verdict."""
    families = sorted(set(families))
    members = sorted(members, key=lambda v: (v['source_id'], v['path']))
    refs, windows, objects, seen = [], collections.defaultdict(list), collections.defaultdict(set), set()
    token_patterns = {key: re.compile(pattern, re.I) for key, pattern in TOKENS.items()}
    for index, member in enumerate(members):
        key = member['source_id'], member['path']
        data = member['data']
        if key in seen or member['family_id'] not in families:
            raise ValueError('duplicate source/path or unknown family')
        seen.add(key)
        if len(data) != member['bytes'] or hashlib.sha256(data).hexdigest() != member['object_id']:
            raise ValueError('retained member content identity mismatch')
        objects[member['object_id']].add(member['family_id'])
        lines = data.decode('utf-8', 'backslashreplace').splitlines()
        markers, tokens, significant = [], collections.defaultdict(list), []
        for number, line in enumerate(lines, 1):
            if ORIGIN_MARKER.search(line):
                markers.append({'line': number, 'text': line.strip()[:500],
                                'text_truncated': len(line.strip()) > 500})
            for name, pattern in token_patterns.items():
                if pattern.search(line):
                    tokens[name].append(number)
            normalized = re.sub(r'\s+', '', line)
            if len(normalized) >= 12:
                significant.append((number, normalized))
        for start in range(len(significant) - WINDOW_LINES + 1):
            block = significant[start:start + WINDOW_LINES]
            raw = '\n'.join(v for _, v in block).encode('utf-8')
            if len(raw) >= WINDOW_MIN_BYTES:
                windows[hashlib.sha256(raw).hexdigest()].append(
                    [index, block[0][0], block[-1][0]])
        refs.append({key: member[key] for key in ('family_id', 'source_id', 'path', 'object_id', 'bytes')})
        refs[-1].update(origin_markers=markers, origin_tokens={
            name: {'matching_lines': len(numbers), 'first_lines': numbers[:12],
                   'locations_truncated': len(numbers) > 12}
            for name, numbers in sorted(tokens.items())})
    pair_counts = collections.Counter()
    overlaps = []
    for digest, locations in sorted(windows.items()):
        matched_families = sorted({refs[index]['family_id'] for index, _, _ in locations})
        if len(matched_families) < 2:
            continue
        for pair in itertools.combinations(matched_families, 2):
            pair_counts[pair] += 1
        overlaps.append({'sha256': digest, 'families': matched_families,
                         'locations': locations})
    return {'schema': 'delsk.e0.acquired-origin-evidence.v1',
            'scope': 'Provenance leads only; no independence, absence-of-copying, or candidate verdict.',
            'method': {'window_lines': WINDOW_LINES, 'minimum_window_bytes': WINDOW_MIN_BYTES,
                       'normalization': 'remove whitespace per line; omit lines shorter than 12 characters; '
                                        '12 consecutive remaining lines; comments and strings retained',
                       'limits': 'Exact text only: modified/renamed/nonconsecutive copies can be missed. '
                                 'Shared license/algorithm constants can produce false ancestry leads.',
                       'origin_marker_regex': ORIGIN_MARKER.pattern, 'origin_token_regexes': TOKENS},
            'retained_member_records': len(refs), 'members': refs,
            'pairs': [{'a': a, 'b': b, 'shared_window_hashes': pair_counts[a, b],
                       'identical_member_objects': sum(a in group and b in group for group in objects.values())}
                      for a, b in itertools.combinations(families, 2)],
            'shared_windows': overlaps}


def acquire_locked(plan, policy, source_lock):
    """Acquire exact D inputs and check complete retained membership, in memory."""
    if source_lock['source_plan_sha256'] != m.file_sha256(plan) or \
            source_lock['selection_policy_sha256'] != m.file_sha256(policy):
        raise ValueError('source lock does not bind these plan/policy bytes')
    planned = {r['release_id']: (f['family_id'], r) for f in plan['families'] for r in f['releases']}
    if {s['source_id'] for s in source_lock['sources']} != set(planned):
        raise ValueError('source coverage mismatch')
    retained, downloads = [], []
    acquired = expanded = 0
    for source in source_lock['sources']:
        sid = source['source_id']
        fid, release = planned[sid]
        if (source['url'], source['format'], source['family_id']) != \
                (release['archive']['url'], release['archive']['format'], fid):
            raise ValueError('source identity mismatch')
        cap = min(source['archive_bytes'], policy['caps']['acquired_bytes_max'] - acquired)
        data, _, attempts = mz.fetch(source['url'], cap)
        if (len(data), mz.sha256(data)) != (source['archive_bytes'], source['archive_sha256']):
            raise ValueError('archive bytes differ from frozen source lock: ' + sid)
        acquired += len(data)
        entries, size = mz.expand(data, source['format'], policy['caps']['materialized_bytes_max'] - expanded)
        expanded += size
        top, members = mz.normalize(entries)
        inventory = m.digest([[v['path'], v['type'], v['size'], v['sha256']] for v in members])
        if (top, len(members), inventory) != (source['top_dir'], source['member_count'], source['inventory_sha256']):
            raise ValueError('archive inventory differs from D: ' + sid)
        selected = m.select_members([{'source_id': sid, 'family_id': fid, **v} for v in members],
                                    policy, m.family_globs(plan))
        actual = [{'bytes': v['size'], 'object_id': v['sha256'], 'path': v['path']} for v in selected['retained']]
        if actual != source['retained']:
            raise ValueError('retained member ledger differs from D: ' + sid)
        retained.extend({'family_id': fid, 'source_id': sid, 'path': v['path'], 'bytes': v['size'],
                         'object_id': v['sha256'], 'data': v['data']} for v in selected['retained'])
        # SHA-1 base32 is the Wayback CDX payload digest form, used for A07 historical-byte checks.
        downloads.append({'source_id': sid, 'sha256': source['archive_sha256'], 'archive_bytes': len(data),
                          'sha1_base32': base64.b32encode(hashlib.sha1(data).digest()).decode(),
                          'retained_members': len(actual), 'attempts': attempts})
    if acquired != source_lock['acquired_bytes'] or expanded != source_lock['expanded_bytes']:
        raise ValueError('acquisition accounting differs from D')
    return retained, downloads


def main(argv):
    if len(argv) != 1:
        return 2
    out = Path(argv[0])
    out.mkdir(parents=True, exist_ok=True)
    report = {'schema': 'delsk.e0.origin-audit-run.v1', 'status': 'error',
              'errors': [], 'run': {key: os.environ.get(key) for key in
                ('GITHUB_REPOSITORY', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT', 'GITHUB_SHA', 'SOURCE_SHA')},
              'oracle': 'NOT_RUN', 'candidates': 'NOT_CONSTRUCTED'}
    try:
        if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('GITHUB_REPOSITORY') != 'definitely-stable/Shift-lab':
            raise ValueError('natural acquisition permitted only in this repository Actions job')
        plan = m.loads_strict((mz.CORPUS / 'source-plan.json').read_bytes())
        policy = m.loads_strict((mz.CORPUS / 'selection-policy.json').read_bytes())
        source_raw = (mz.PILOT / 'source-lock.json').read_bytes()
        freeze = m.loads_strict((mz.PILOT / 'freeze.json').read_bytes())
        if mz.sha256(source_raw) != freeze['files']['source-lock.json'] or freeze['status'] != 'FROZEN_ACQUISITION':
            raise ValueError('acquisition freeze/source lock mismatch')
        errors = m.validate_source_plan(plan) + m.validate_selection_policy(policy)
        if errors:
            raise ValueError('; '.join(errors))
        members, downloads = acquire_locked(plan, policy, m.loads_strict(source_raw))
        report['downloads'] = downloads
        evidence = analyze_members(members, [f['family_id'] for f in plan['families']])
        evidence['source_lock_sha256'] = mz.sha256(source_raw)
        evidence['source_plan_sha256'] = m.file_sha256(plan)
        evidence['selection_policy_sha256'] = m.file_sha256(policy)
        raw = m.canonical_bytes(evidence)
        if len(raw) > REPORT_CAP:
            raise ValueError('origin evidence exceeds explicit 12 MiB cap; no truncation permitted')
        (out / 'origin-evidence.json').write_bytes(raw)
        report.update(status='ok', evidence_sha256=mz.sha256(raw), evidence_bytes=len(raw),
                      retained_member_records=len(members), family_pairs=len(evidence['pairs']))
    except Exception as error:
        report['errors'].append(type(error).__name__ + ': ' + str(error))
    (out / 'origin-run.json').write_bytes(m.canonical_bytes(report))
    print(json.dumps({key: report[key] for key in ('status', 'errors')}))
    return 0 if report['status'] == 'ok' else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
