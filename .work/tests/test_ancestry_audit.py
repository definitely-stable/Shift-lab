"""Synthetic provenance-audit checks; correctness execution belongs in Actions."""
import hashlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
try:
    import ancestry_audit as audit
except ModuleNotFoundError:
    audit = None


def member(family, path, data, source=None):
    return {'family_id': family, 'source_id': source or family + '-1', 'path': path,
            'object_id': hashlib.sha256(data).hexdigest(), 'bytes': len(data), 'data': data}


class AncestryAuditTests(unittest.TestCase):
    def test_audit_is_available(self):
        self.assertIsNotNone(audit, 'A08 needs a bounded acquired-snapshot evidence audit')

    @unittest.skipIf(audit is None, 'audit implementation pending')
    def test_scan_covers_full_file_and_keeps_source_identity(self):
        data = b'\n' * 200 + b'/* derived from external upstream */\nint value;\n'
        report = audit.analyze_members([member('a', 'x.c', data)], ['a'])
        row = report['members'][0]
        self.assertEqual(row['source_id'], 'a-1')
        self.assertEqual(row['origin_markers'][0]['line'], 201)
        self.assertEqual(report['retained_member_records'], 1)

    @unittest.skipIf(audit is None, 'audit implementation pending')
    def test_shared_windows_detect_shifted_partial_copy(self):
        shared = b''.join(('int shared_function_%02d(int x) { return x + %d; }\n' % (i, i)).encode()
                          for i in range(15))
        members = [member('a', 'a.c', b'/* header a */\n' + shared),
                   member('b', 'b.c', b'/* header b */\n\n' + shared + b'int b;\n')]
        report = audit.analyze_members(members, ['a', 'b'])
        pair = report['pairs'][0]
        self.assertEqual(pair['identical_member_objects'], 0)
        self.assertGreater(pair['shared_window_hashes'], 0)
        self.assertTrue(report['shared_windows'])

    @unittest.skipIf(audit is None, 'audit implementation pending')
    def test_permutation_is_identical_and_absent_pairs_remain(self):
        members = [member('a', 'x.c', b'int unique_a;\n'),
                   member('b', 'x.c', b'int unique_b;\n')]
        first = audit.analyze_members(members, ['a', 'b', 'c'])
        second = audit.analyze_members(list(reversed(members)), ['c', 'b', 'a'])
        self.assertEqual(first, second)
        self.assertEqual(len(first['pairs']), 3)
        self.assertTrue(all(p['shared_window_hashes'] == 0 for p in first['pairs']))

    @unittest.skipIf(audit is None, 'audit implementation pending')
    def test_corrupt_member_identity_is_rejected(self):
        row = member('a', 'x.c', b'x')
        row['object_id'] = '0' * 64
        with self.assertRaises(ValueError):
            audit.analyze_members([row], ['a'])

    @unittest.skipIf(audit is None, 'audit implementation pending')
    def test_duplicate_source_path_is_rejected(self):
        row = member('a', 'x.c', b'x')
        with self.assertRaises(ValueError):
            audit.analyze_members([row, row], ['a'])


if __name__ == '__main__':
    unittest.main()
