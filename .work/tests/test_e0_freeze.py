"""Offline integrity of the adopted E0 construction freeze (no downloads, no candidate construction)."""
import datetime as dt
import gzip
import hashlib
import itertools
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / '.work'
E0 = WORK / 'corpus' / 'e0'
sys.path.insert(0, str(WORK / 'tools'))
import manifests as m
import origin_leads


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return m.loads_strict(path.read_bytes())


class E0FreezeTests(unittest.TestCase):
    def setUp(self):
        self.freeze = load(E0 / 'freeze.json')
        self.plan = load(WORK / 'corpus' / 'source-plan.json')
        self.policy = load(WORK / 'corpus' / 'selection-policy.json')
        self.source_lock = load(WORK / 'corpus' / 'pilot-v1' / 'source-lock.json')

    def test_status_and_rulings(self):
        self.assertEqual(self.freeze['schema'], 'delsk.e0.construction-freeze.v1')
        self.assertEqual(self.freeze['status'], 'FROZEN_DESIGN')
        self.assertEqual(sorted(self.freeze['rulings']), ['A%02d' % i for i in range(1, 11)])

    def test_pinned_files_and_unchanged_inputs(self):
        for name, digest in {**self.freeze['inputs'], **self.freeze['files']}.items():
            self.assertEqual(sha(ROOT / name), digest, name)
        raw = gzip.decompress((WORK / 'corpus' / 'pilot-v1' / 'corpus-lock.json.gz').read_bytes())
        self.assertEqual(hashlib.sha256(raw).hexdigest(), self.freeze['corpus_lock_canonical_sha256'])

    def test_candidate_lock_bindings(self):
        b, inputs, files = self.freeze['candidate_lock_bindings'], self.freeze['inputs'], self.freeze['files']
        self.assertEqual(b, {
            'corpus_lock_sha256': self.freeze['corpus_lock_canonical_sha256'],
            'selection_policy_sha256': inputs['.work/corpus/selection-policy.json'],
            'protocol_sha256': inputs['.work/protocol.md'],
            'construction_spec_sha256': files['.work/corpus/e0/construction-spec.md'],
            'ancestry_audit_sha256': files['.work/corpus/e0/ancestry-audit.json'],
            'acquisition_freeze_sha256': inputs['.work/corpus/pilot-v1/freeze.json'],
            'historical_bytes_sha256': files['.work/corpus/e0/historical-bytes.json']})
        self.assertEqual(self.source_lock['source_plan_sha256'], inputs['.work/corpus/source-plan.json'])
        self.assertEqual(self.source_lock['selection_policy_sha256'], inputs['.work/corpus/selection-policy.json'])

    def test_audit_runs_reacquired_exact_d_archives(self):
        expected = {s['source_id']: s['archive_sha256'] for s in self.source_lock['sources']}
        sha1 = set()
        for name in self.freeze['runs']:
            run = load(E0 / 'runs' / name)
            self.assertEqual(run['status'], 'ok')
            self.assertEqual(run['candidates'], 'NOT_CONSTRUCTED')
            self.assertEqual({d['source_id']: d['sha256'] for d in run['downloads']}, expected)
            sha1.add(tuple(d['sha1_base32'] for d in run['downloads']))
        self.assertEqual(len(sha1), 1)

    def test_ancestry_audit_closes_all_pairs(self):
        audit = load(E0 / 'ancestry-audit.json')
        raw = gzip.decompress((E0 / 'origin-evidence.json.gz').read_bytes())
        evidence = m.loads_strict(raw)
        run = load(E0 / audit['bindings']['run'])
        self.assertEqual(hashlib.sha256(raw).hexdigest(), run['evidence_sha256'])
        self.assertEqual(audit['bindings']['origin_evidence_sha256'], run['evidence_sha256'])
        for key in ('source_plan_sha256', 'selection_policy_sha256', 'source_lock_sha256'):
            self.assertEqual(audit['bindings'][key], evidence[key])
        self.assertEqual(audit['bindings']['source_lock_sha256'], self.freeze['inputs']['.work/corpus/pilot-v1/source-lock.json'])
        families = sorted(f['family_id'] for f in self.plan['families'])
        self.assertEqual([(p['a'], p['b']) for p in audit['pairs']], list(itertools.combinations(families, 2)))
        observed = {(p['a'], p['b']): p for p in evidence['pairs']}
        allowed = {'no_shared_origin_established', 'no_shared_payload', 'path_excluded'}
        for row in audit['pairs']:
            self.assertIn(row['resolution'], allowed)
            e = observed[row['a'], row['b']]
            self.assertEqual((row['shared_window_hashes'], row['identical_member_objects']),
                             (e['shared_window_hashes'], e['identical_member_objects']))
        self.assertTrue(all(evidence['within_family_cross_release_window_hashes'][f] > 0 for f in families))
        self.assert_leads_closed(audit, evidence)
        self.assertEqual(audit['result']['merges'], [])
        components, assigned = m._family_splits(self.plan, self.policy)
        self.assertEqual([list(c) for c in components], audit['result']['components'])
        counts = {}
        for split in assigned.values():
            counts[split] = counts.get(split, 0) + 1
        self.assertEqual(counts, audit['result']['split_component_counts'])
        self.assertEqual(counts, dict(self.policy['splits']['counts']))

    def assert_leads_closed(self, audit, evidence):
        """Every generated lead has exactly one reviewed disposition; unresolved is derived, not declared."""
        generated = origin_leads.generate(evidence)
        reviewed = [{k: v for k, v in lead.items() if k not in ('disposition', 'reference')}
                    for lead in audit['leads']]
        self.assertEqual(reviewed, generated)
        dispositions = {'algorithm_or_standard_reference', 'api_dependency', 'contributor_credit',
                        'descriptive_text', 'external_origin', 'generated_first_party', 'intra_family',
                        'public_domain_notice', 'roster_api_reference', 'standard_vocabulary', 'unresolved'}
        origins = {o['origin']: o for o in audit['external_origins']}
        pairs = {p['a'] + '-' + p['b']: p for p in audit['pairs']}
        for lead in audit['leads']:
            self.assertIn(lead['disposition'], dispositions)
            if lead['disposition'] == 'external_origin':
                self.assertEqual(origins[lead['reference']]['families'], [lead['family_id']])
            if lead['disposition'] == 'roster_api_reference':
                self.assertIn(lead['family_id'], lead['reference'].split('-'))
                self.assertNotEqual(pairs[lead['reference']]['relation'], 'none_found')
        self.assertTrue(all(len(o['families']) == 1 for o in origins.values()))
        self.assertEqual(audit['result']['unresolved'],
                         [lead['id'] for lead in audit['leads'] if lead['disposition'] == 'unresolved'])
        self.assertEqual(audit['result']['unresolved'], [])

    def test_historical_bytes_match_acquired_archives(self):
        history = load(E0 / 'historical-bytes.json')
        run = load(E0 / history['run'])
        downloads = {d['source_id']: d for d in run['downloads']}
        sha256 = {s['source_id']: s['archive_sha256'] for s in self.source_lock['sources']}
        self.assertEqual(history['source_lock_sha256'], self.freeze['inputs']['.work/corpus/pilot-v1/source-lock.json'])
        self.assertEqual({r['source_id'] for r in history['sources']}, set(sha256))
        attested = {}
        for row in history['sources']:
            d = downloads[row['source_id']]
            self.assertEqual(row['archive_sha256'], sha256[row['source_id']])
            self.assertEqual((row['archive_sha1_base32'], row['archive_md5']), (d['sha1_base32'], d['md5']))
            self.assertEqual(row['contrary_archive_captures'], [])
            self.assertTrue(row['evidence'])
            self.assertEqual(row['earliest_attested_utc'], min(e['attested_utc'] for e in row['evidence']))
            attested[row['source_id']] = row['earliest_attested_utc']
        # Usable source pairs, derived here from plan and policy, not copied from the record.
        _, split = m._family_splits(self.plan, self.policy)
        releases = [(f['family_id'], r) for f in self.plan['families'] for r in f['releases']]
        expected = {}
        for fb, b in releases:
            for ft, t in releases:
                lo_t = m.availability(t['time'])[0]
                if split[fb] == split[ft] and t['ordinal'] in (2, 3) and m.availability(b['time'])[1] < lo_t:
                    when = dt.datetime.strptime(attested[b['release_id']], '%Y-%m-%dT%H:%M:%SZ')
                    expected[b['release_id'], t['release_id']] =                         int(when.replace(tzinfo=dt.timezone.utc).timestamp()) < lo_t
        pairs = history['source_pairs']
        self.assertEqual({(p['base_source'], p['target_source']): p['base_bytes_attested_before_target_release']
                          for p in pairs['pairs']}, expected)
        self.assertEqual(pairs['total'], len(expected))
        self.assertEqual(pairs['base_bytes_attested_before_target_release'], sum(expected.values()))
        self.assertTrue(all(expected.values()))

if __name__ == '__main__':
    unittest.main()
