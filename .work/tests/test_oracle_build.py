"""DELSK-003 Slice B: codec builder (.work/tools/oracle_build.py) without network: source identity, hostile archives,
stale outputs and the exact build environment. The real pinned builds run in the PR smoke workflow."""
import hashlib
import io
import os
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = HERE.parent
sys.path.insert(0, str(WORK / 'tools'))
import manifests as m  # noqa: E402
import materialize  # noqa: E402
import oracle_build as ob  # noqa: E402

LOCK = m.loads_strict((WORK / 'oracle' / 'codec-lock.json').read_bytes())


def targz(members):
    """members: (name, kind, data_or_linkname)."""
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode='w:gz') as tar:
        for name, kind, payload in members:
            info = tarfile.TarInfo(name)
            if kind == 'file':
                info.size = len(payload)
                tar.addfile(info, io.BytesIO(payload))
                continue
            info.type = {'dir': tarfile.DIRTYPE, 'sym': tarfile.SYMTYPE, 'lnk': tarfile.LNKTYPE,
                         'fifo': tarfile.FIFOTYPE, 'chr': tarfile.CHRTYPE}[kind]
            info.linkname = payload or ''
            tar.addfile(info)
    return raw.getvalue()


def source_for(data, **change):
    src = dict(LOCK['codecs']['delta']['source'], archive_bytes=len(data),
               archive_sha256=hashlib.sha256(data).hexdigest())
    src.update(change)
    return src


class Source(unittest.TestCase):
    def test_locked_archive_identity(self):
        data = b'archive'
        ob.check_source(source_for(data), data)
        for name, src, blob in (
                ('size', source_for(data, archive_bytes=8), data),
                ('sha', source_for(data), b'archivf'),
                ('other tag', source_for(data, archive_url='https://github.com/jmacd/xdelta/releases/download/v3.2.0/x.tgz'),
                 data),
                ('plain http', source_for(data, archive_url='http://github.com/jmacd/xdelta/releases/download/v3.2.1/x'),
                 data),
                ('other repository', source_for(data, archive_url='https://github.com/evil/xdelta/releases/download/'
                                                                  'v3.2.1/xdelta3-3.2.1.tar.gz'), data)):
            with self.subTest(name):
                with self.assertRaises(ob.BuildError):
                    ob.check_source(src, blob)

    def test_both_lock_urls_are_release_assets_of_their_repository(self):
        for codec in LOCK['codecs'].values():
            src = codec['source']
            self.assertTrue(src['archive_url'].startswith(f"{src['repository']}/releases/download/{src['tag']}/"))


class Extraction(unittest.TestCase):
    def setUp(self):
        self.dest = Path(tempfile.mkdtemp(prefix='oracle-build-test-'))
        self.addCleanup(__import__('shutil').rmtree, self.dest, True)

    def test_regular_files_only(self):
        data = targz([('r', 'dir', None), ('r/a.c', 'file', b'int x;\n'), ('r/sub/b.h', 'file', b'#define B\n'),
                      ('r/link', 'sym', '../../etc/passwd'), ('r/hard', 'lnk', 'r/a.c'), ('r/fifo', 'fifo', None)])
        count, tree, skipped = ob.extract(data, 'r', self.dest)
        self.assertEqual(count, 2)
        self.assertEqual((self.dest / 'r' / 'sub' / 'b.h').read_bytes(), b'#define B\n')
        self.assertEqual(sorted(s['path'] for s in skipped), ['fifo', 'hard', 'link'])
        self.assertFalse(os.path.lexists(self.dest / 'r' / 'link'))
        self.assertFalse(os.path.lexists(self.dest / 'r' / 'hard'))
        self.assertEqual(tree, m.digest([['a.c', hashlib.sha256(b'int x;\n').hexdigest()],
                                         ['sub/b.h', hashlib.sha256(b'#define B\n').hexdigest()]]))

    def test_hostile_archives_are_refused(self):
        for name, members in (('traversal', [('r/../evil', 'file', b'x')]),
                              ('absolute', [('/etc/evil', 'file', b'x')]),
                              ('two roots', [('r/a', 'file', b'x'), ('s/b', 'file', b'y')]),
                              ('top-level file', [('evil', 'file', b'x')]),
                              ('duplicate', [('r/a', 'file', b'x'), ('r/a', 'file', b'y')]),
                              ('backslash', [('r/a\\..\\b', 'file', b'x')])):
            with self.subTest(name):
                with self.assertRaises((ob.BuildError, materialize.MaterializeError)):
                    ob.extract(targz(members), 'r', self.dest / name)

    def test_wrong_root_and_expansion_cap(self):
        with self.assertRaises(ob.BuildError):
            ob.extract(targz([('other/a', 'file', b'x')]), 'r', self.dest)
        cap, ob.EXPANDED_CAP = ob.EXPANDED_CAP, 1024
        try:
            with self.assertRaises(materialize.MaterializeError):
                ob.extract(targz([('r/big', 'file', b'\0' * 4096)]), 'r', self.dest / 'cap')
        finally:
            ob.EXPANDED_CAP = cap

    def test_stale_output_directory_is_refused(self):
        (self.dest / 'old').write_text('x')
        self.assertEqual(ob.main([str(self.dest)]), 1)


@unittest.skipUnless(sys.platform.startswith('linux'), 'build commands run on Linux')
class BuildRecipe(unittest.TestCase):
    def test_exact_argv_and_environment(self):
        script = "env > env.txt; printf '#!/bin/sh\\necho report \"$@\"\\n' > tool; chmod 755 tool"
        data = targz([('r/readme', 'file', b'x')])
        codec = {'codec_id': 'test-codec', 'source': source_for(data, archive_root='r'),
                 'build': {'argv': ['sh', '-c', script], 'cwd': 'r', 'env': {'LC_ALL': 'C', 'PATH': '/usr/bin:/bin'},
                           'executable': 'tool'}}
        out = Path(tempfile.mkdtemp(prefix='oracle-build-recipe-'))
        self.addCleanup(__import__('shutil').rmtree, out, True)
        os.environ['DELSK_INHERITED_PROBE'] = '1'
        self.addCleanup(os.environ.pop, 'DELSK_INHERITED_PROBE')
        record = ob.build_codec('delta', codec, out, fetcher=lambda url, cap: (data, url, 1))
        env = dict(line.split('=', 1) for line in (out / 'src' / 'r' / 'env.txt').read_text().splitlines())
        self.assertNotIn('DELSK_INHERITED_PROBE', env)
        self.assertEqual((env['LC_ALL'], env['PATH']), ('C', '/usr/bin:/bin'))
        self.assertTrue(set(env) <= {'LC_ALL', 'PATH', 'PWD', 'SHLVL', '_', 'OLDPWD'}, sorted(env))
        self.assertEqual(record['self_report'], 'report config\n')
        self.assertEqual(record['executable'], 'src/r/tool')
        self.assertEqual(record['executable_sha256'], hashlib.sha256((out / 'src' / 'r' / 'tool').read_bytes()).hexdigest())
        self.assertEqual((out / record['archive_path']).read_bytes(), data)


if __name__ == '__main__':
    unittest.main()
