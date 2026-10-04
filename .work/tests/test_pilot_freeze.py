"""Offline integrity of the retained Slice D acquisition evidence (no downloads)."""
import gzip
import hashlib
import json
from pathlib import Path
import sys
import unittest

WORK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORK / 'tools'))
import manifests as m


class PilotFreezeTests(unittest.TestCase):
    def test_durable_full_lock(self):
        pilot = WORK / 'corpus' / 'pilot-v1'
        raw = gzip.decompress((pilot / 'corpus-lock.json.gz').read_bytes())
        summary = json.loads((pilot / 'materialization.json').read_bytes())
        self.assertEqual(hashlib.sha256(raw).hexdigest(), summary['corpus_lock_sha256'])
        lock = m.loads_strict(raw)
        plan = m.loads_strict((pilot.parent / 'source-plan.json').read_bytes())
        policy = m.loads_strict((pilot.parent / 'selection-policy.json').read_bytes())
        self.assertEqual(m.validate_corpus_lock(lock, plan, policy), [])
        self.assertEqual(len(lock['occurrences']), summary['occurrences'])
        self.assertEqual(len({row['object_id'] for row in lock['occurrences']}), summary['objects'])
        self.assertEqual(sum(row['bytes'] for row in lock['occurrences']), summary['materialized_bytes'])

    def test_review_and_independent_runs_pin_frozen_files(self):
        pilot = WORK / 'corpus' / 'pilot-v1'
        review = json.loads((pilot / 'freeze.json').read_bytes())
        self.assertEqual(review['status'], 'FROZEN_ACQUISITION')
        for name, digest in review['files'].items():
            self.assertEqual(hashlib.sha256((pilot / name).read_bytes()).hexdigest(), digest)
        licenses = json.loads((pilot / 'licenses.json').read_bytes())
        expected_sources = {s['source_id'] for s in json.loads((pilot / 'source-lock.json').read_bytes())['sources']}
        seen = set()
        for family in review['license_review']:
            self.assertEqual(family['status'], 'REVIEWED_FOR_PILOT')
            observed = next(f for f in licenses['families'] if f['family_id'] == family['family_id'])
            self.assertFalse(observed['notices_truncated'])
            for source in family['sources']:
                seen.add(source['source_id'])
                if family['family_id'] != 'sqlite':
                    match = next(f for f in observed['license_files'] if f['source_id'] == source['source_id'] and f['path'] == source['path'])
                    self.assertEqual(match['sha256'], source['sha256'])
                    self.assertTrue(source['matches_acquired_snapshot'])
        self.assertEqual(seen, expected_sources)
        identities = set()
        modes = set()
        for name in review['runs']:
            run = json.loads((pilot / 'runs' / name).read_bytes())
            identities.add(run['run']['GITHUB_RUN_ID'])
            modes.add(run['mode'])
            self.assertEqual(run['status'], 'ok')
            for filename in ('source-lock.json', 'licenses.json', 'materialization.json'):
                self.assertEqual(run['outputs'][filename]['sha256'], review['files'][filename])
            if run['mode'] == 'verify':
                self.assertTrue(all(run['matches'].values()))
        self.assertGreaterEqual(len(identities), 2)
        self.assertEqual(modes, {'discover', 'verify'})


if __name__ == '__main__':
    unittest.main()
