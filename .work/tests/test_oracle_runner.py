"""DELSK-003 Slice B: production runner (.work/tools/oracle_run.py) with fault-injection codec shims, the evidence
chain runner -> finalize -> verify -> bundle on its output, sealed-cost leakage, and, when ORACLE_TOOLS names a real
oracle_build.py record, the pinned codecs on synthetic inputs. Synthetic data only; Linux only (process groups,
pidfd, setrlimit), so these tests are skipped elsewhere.
"""
import io
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = HERE.parent
sys.path[:0] = [str(WORK / 'tools'), str(HERE)]
import manifests as m  # noqa: E402
import oracle_eval as ev  # noqa: E402
import oracle_run as orun  # noqa: E402

LINUX = sys.platform.startswith('linux')
LOCK_DATA = (WORK / 'oracle' / 'codec-lock.json').read_bytes()
LOCK = m.loads_strict(LOCK_DATA)
ENV = {'GITHUB_REPOSITORY': 'definitely-stable/Shift-lab', 'GITHUB_RUN_ID': '7', 'GITHUB_RUN_ATTEMPT': '1',
       'GITHUB_SHA': 'f' * 40, 'GITHUB_WORKFLOW_SHA': 'f' * 40,
       'GITHUB_WORKFLOW_REF': 'definitely-stable/Shift-lab/.github/workflows/oracle-smoke.yml@refs/pull/1/merge'}

# A shim speaks the argv shape of the locked codec it replaces. Every call first checks the invocation contract
# (only LC_ALL in the environment, stdin is /dev/null, the call directory holds only its inputs) and exits 4 if not.
SHIM = r'''#!{python}
import os, signal, sys, time
MODE, ROLE, PIDS = {mode!r}, {role!r}, {pids!r}
args = sys.argv[1:]
null = os.stat('/dev/null')
if set(os.environ) - {{'LC_ALL'}} or os.environ.get('LC_ALL') != 'C' or os.fstat(0).st_rdev != null.st_rdev:
    sys.exit(4)
decode = '-d' in args
if ROLE == 'delta':
    inputs = [args[args.index('-s') + 1], args[-2]]
    src, out = args[-2], args[-1]
else:
    src, out = args[args.index('-o') - 1], args[args.index('-o') + 1]
    inputs = [src]
if sorted(os.listdir('.')) != sorted(inputs):
    sys.exit(4)
if MODE == ('hang-decode' if decode else 'hang-encode'):
    if os.fork() == 0:
        open(PIDS, 'a').write(f'{{os.getpid()}}\n')
        time.sleep(600)
        os._exit(0)
    time.sleep(600)
if MODE == 'slow':
    time.sleep(0.25)
data = open(src, 'rb').read()
if not decode:
    if MODE == 'encode-exit':
        sys.exit(1)
    if MODE == 'enomem':
        sys.stderr.write('shim: Cannot allocate memory\n')
        sys.exit(1)
    if MODE == 'bigfile':
        open(out, 'wb').write(b'\0' * (4 << 20))
    open(out, 'wb').write(b'JUNK' if MODE == 'garbage' else b'SHIM' + data)
    sys.exit(0)
if MODE == 'decode-exit' or not data.startswith(b'SHIM'):
    sys.exit(1)
body = data[4:]
if MODE == 'corrupt':
    body = bytes([body[0] ^ 1]) + body[1:] if body else b'\0'
open(out, 'wb').write(body)
'''


def shim_tools(root, delta='ok', standalone='ok'):
    """A tools.json in the builder's format whose executables are shims, plus a bound non-PASS conformance record."""
    root = Path(root)
    (root / 'bin').mkdir(parents=True)
    codecs = {}
    for role, mode, name in (('delta', delta, 'xdelta3'), ('standalone', standalone, 'zstd')):
        exe = root / 'bin' / name
        exe.write_text(SHIM.format(python=sys.executable, mode=mode, role=role, pids=str(root / 'pids')))
        exe.chmod(0o755)
        src = LOCK['codecs'][role]['source']
        codecs[role] = {'codec_id': LOCK['codecs'][role]['codec_id'], 'archive_url': src['archive_url'],
                        'archive_bytes': src['archive_bytes'], 'archive_sha256': src['archive_sha256'],
                        'archive_root': src['archive_root'], 'archive_path': f'archives/{name}.tar.gz',
                        'extracted_files': 1, 'extracted_tree_sha256': '0' * 64, 'skipped_members': [],
                        'build_argv': LOCK['codecs'][role]['build']['argv'], 'build_cwd': src['archive_root'],
                        'build_env': LOCK['codecs'][role]['build']['env'], 'executable': f'bin/{name}',
                        'executable_bytes': exe.stat().st_size, 'executable_sha256': orun.sha256(exe.read_bytes()),
                        'self_report': f'{name} shim\n'}
    tools = {'schema': 'delsk.oracle.tools.v1', 'codec_lock_sha256': orun.sha256(LOCK_DATA),
             'compiler': {'path': '/usr/bin/cc', 'realpath': '/usr/bin/cc', 'sha256': '0' * 64, 'version': 'shim'},
             'make': {'path': '/usr/bin/make', 'realpath': '/usr/bin/make', 'sha256': '0' * 64, 'version': 'shim'},
             'codecs': codecs, 'source': {'sha': None, 'workflow_sha': None, 'run_id': None, 'run_attempt': None}}
    (root / 'tools.json').write_bytes(m.canonical_bytes(tools))
    conformance = {'schema': 'delsk.oracle.conformance.v1', 'codec_lock_sha256': orun.sha256(LOCK_DATA),
                   'executables': {r: c['executable_sha256'] for r, c in codecs.items()}, 'inputs_sha256': {},
                   'golden': {}, 'verdict': 'FAIL',
                   'checks': {f'C{i:02d}': {'status': 'FAIL', 'detail': 'shim codecs'} for i in range(1, 15)}}
    (root / 'conformance.json').write_bytes(m.canonical_bytes(conformance))
    return root / 'tools.json', root / 'conformance.json'


def read_rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


@unittest.skipUnless(LINUX, 'runner needs Linux process groups, pidfd and setrlimit')
class Runner(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='oracle-runner-test-'))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        orun.synthetic(self.tmp / 'syn')

    def run_shims(self, delta='ok', standalone='ok', codec_limits=None, file_cap=None, name='run'):
        tools, conformance = shim_tools(self.tmp / f'{name}-tools', delta, standalone)
        ctx = orun.prepare('smoke', tools, conformance, self.tmp / 'syn', ENV)
        evidence, private = self.tmp / f'{name}-evidence', self.tmp / f'{name}-private'
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            status = orun.execute(ctx, self.tmp / 'syn' / 'store', evidence, private, ENV, codec_limits, file_cap)
            result = ev.finalize(evidence, private)
        self.logs = out.getvalue() + err.getvalue()
        return status, result, evidence, private

    def statuses(self, private):
        return {(r['status'], r['failure_phase'], r['error_class']) for r in read_rows(private / 'pairs.full.jsonl')}

    def test_clean_run_is_complete_and_verifies(self):
        status, result, evidence, private = self.run_shims()
        self.assertEqual((status, result['run_status'], result['invalid_reasons']), ('ok', 'COMPLETE', []))
        self.assertEqual(ev.verify(evidence), [])
        pairs = read_rows(private / 'pairs.full.jsonl')
        self.assertEqual(len(pairs), 14)
        self.assertEqual([(r['target_occurrence_id'], r['base_object_id']) for r in pairs],
                         sorted((r['target_occurrence_id'], r['base_object_id']) for r in pairs))
        coverage = ev.parse_doc((evidence / 'coverage.json').read_bytes())['counts']
        self.assertEqual((coverage['sealed_pairs'], coverage['sealed_targets'], coverage['near_empty']), (3, 2, 1))
        evaluation = ev.parse_doc((evidence / 'evaluation.json').read_bytes())
        self.assertEqual((evaluation['metrics_status'], evaluation['metrics']['strict']),
                         ('COMPUTED', {'num': 1, 'den': 1}))  # oracle self-retrieval sanity

    def test_bundle_is_transactional(self):
        _, _, evidence, _ = self.run_shims()
        results = self.tmp / 'results'
        dest = ev.bundle(evidence, results)
        self.assertEqual(dest.name, '7-1')
        self.assertEqual(ev.verify(dest), [])
        with self.assertRaises(ev.EvalError):
            ev.bundle(evidence, results)  # already retained
        with self.assertRaises(ev.EvalError):  # smoke bundles never enter the repository results
            ev.bundle(evidence)
        bad = self.tmp / 'tampered'
        shutil.copytree(evidence, bad)
        rows = (bad / 'pairs.jsonl').read_bytes().replace(b'"status":"ok"', b'"status":"timeout"', 1)
        (bad / 'pairs.jsonl').write_bytes(rows)
        shutil.rmtree(dest)
        with self.assertRaises(ev.EvalError):
            ev.bundle(bad, results)
        self.assertEqual(list(results.iterdir()), [])  # nothing partial left behind
        self.assertTrue(ev.verify(bad))
        (bad / 'checksums.sha256').write_text(ev.checksums(bad))
        self.assertTrue(ev.verify(bad))  # consistent checksums do not hide a recomputation mismatch

    def test_decode_corruption_is_invalid_not_bounded(self):
        _, result, _, private = self.run_shims(delta='corrupt')
        self.assertEqual((result['run_status'], result['invalid_reasons']), ('INVALID', ['DECODE_MISMATCH']))
        self.assertTrue({s[0] for s in self.statuses(private)} == {'decode_mismatch'})

    def test_decoder_exit_is_invalid_not_codec_error(self):
        _, result, _, private = self.run_shims(delta='decode-exit')
        self.assertEqual(result['invalid_reasons'], ['DECODE_MISMATCH'])
        self.assertEqual(self.statuses(private), {('decode_mismatch', 'decode', 'nonzero_exit')})

    def test_malformed_patch_is_invalid(self):
        _, result, _, private = self.run_shims(delta='garbage')
        self.assertEqual(result['invalid_reasons'], ['DECODE_MISMATCH'])

    def test_standalone_decode_corruption_is_invalid(self):
        _, result, _, private = self.run_shims(standalone='corrupt')
        self.assertEqual(result['invalid_reasons'], ['DECODE_MISMATCH'])

    def test_encoder_exit_is_bounded_codec_error(self):
        _, result, _, private = self.run_shims(delta='encode-exit')
        self.assertEqual(result['run_status'], 'COMPLETE_WITH_FAILURES')
        self.assertEqual(self.statuses(private), {('codec_error', 'encode', 'nonzero_exit')})

    def test_encode_timeout_kills_the_process_tree(self):
        _, result, _, private = self.run_shims(delta='hang-encode', codec_limits={'encode_wall_seconds': 1})
        self.assertEqual(result['run_status'], 'COMPLETE_WITH_FAILURES')
        self.assertEqual(self.statuses(private), {('timeout', 'encode', 'wall_timeout')})
        self.assert_no_survivors()

    def test_decode_timeout_is_bounded(self):
        _, result, _, private = self.run_shims(delta='hang-decode', codec_limits={'decode_wall_seconds': 1})
        self.assertEqual(result['run_status'], 'COMPLETE_WITH_FAILURES')
        self.assertEqual(self.statuses(private), {('timeout', 'decode', 'wall_timeout')})
        self.assert_no_survivors()

    def assert_no_survivors(self):
        pids = [int(p) for p in (self.tmp / 'run-tools' / 'pids').read_text().split()]
        self.assertEqual(len(pids), 14)
        deadline = time.monotonic() + 5
        alive = pids
        while alive and time.monotonic() < deadline:
            alive = [p for p in alive if Path(f'/proc/{p}').exists() and
                     Path(f'/proc/{p}/stat').read_text().split(') ')[-1][0] != 'Z']
            time.sleep(0.05)
        self.assertEqual(alive, [], 'a codec descendant outlived its call')

    def test_allocation_failure_is_resource_limit(self):
        _, result, _, private = self.run_shims(delta='enomem')
        self.assertEqual(self.statuses(private), {('resource_limit', 'encode', 'address_space')})
        self.assertEqual(result['run_status'], 'COMPLETE_WITH_FAILURES')

    def test_work_dir_cap_is_resource_limit(self):
        _, result, _, private = self.run_shims(delta='bigfile', file_cap=1 << 20)
        self.assertEqual(self.statuses(private), {('resource_limit', 'encode', 'work_dir')})

    def test_wrong_input_sha_is_input_integrity(self):
        store = self.tmp / 'syn' / 'store'
        victim = sorted(store.iterdir())[3]
        victim.write_bytes(victim.read_bytes() + b'x')
        _, result, _, _ = self.run_shims()
        self.assertEqual((result['run_status'], result['invalid_reasons']), ('INVALID', ['INPUT_INTEGRITY']))

    def test_store_symlink_is_not_followed(self):
        store = self.tmp / 'syn' / 'store'
        victim = sorted(store.iterdir())[3]
        real = self.tmp / 'elsewhere'
        victim.rename(real)
        victim.symlink_to(real)
        _, result, _, _ = self.run_shims()
        self.assertEqual(result['invalid_reasons'], ['INPUT_INTEGRITY'])

    def test_foreign_and_missing_pairs(self):
        _, _, evidence, private = self.run_shims()
        rows = read_rows(private / 'pairs.full.jsonl')
        for name, change, want in (
                ('foreign', lambda rs: rs + [{**rs[0], 'base_object_id': 'f' * 64,
                                               'pair_id': ev.pair_id(rs[0]['codec_id'], rs[0]['target_occurrence_id'],
                                                                     'f' * 64)}], ('INVALID', ['FOREIGN_PAIR'])),
                ('missing', lambda rs: rs[1:], ('INCOMPLETE', [])),
                ('duplicate', lambda rs: rs + rs[:1], ('INVALID', ['DUPLICATE_PAIR']))):
            with self.subTest(name):
                ev2, pr2 = self.tmp / f'{name}-ev', self.tmp / f'{name}-pr'
                shutil.copytree(private, pr2)
                (pr2 / 'pairs.full.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in change(rows)))
                ev2.mkdir()
                for f in ('run.json', 'codec-lock.json', 'tools.json', 'conformance.json', 'candidate-lock.json',
                          'corpus-lock.json'):
                    shutil.copy(evidence / f, ev2 / f)
                with redirect_stdout(io.StringIO()):
                    result = ev.finalize(ev2, pr2)
                self.assertEqual((result['run_status'], result['invalid_reasons']), want)
                self.assertEqual(ev.verify(ev2), [])  # an INVALID/INCOMPLETE run is still a faithful bundle

    def test_runner_abort_halfway_leaves_not_run_rows(self):
        tools, conformance = shim_tools(self.tmp / 'abort-tools', delta='slow')
        evidence, private = self.tmp / 'abort-ev', self.tmp / 'abort-pr'
        proc = subprocess.Popen([sys.executable, str(WORK / 'tools' / 'oracle_run.py'), 'run', 'smoke', str(tools),
                                 str(conformance), str(self.tmp / 'syn' / 'store'), str(evidence), str(private),
                                 str(self.tmp / 'syn')], env={**os.environ, **ENV}, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        while not (private / 'pairs.full.jsonl').exists() or \
                len((private / 'pairs.full.jsonl').read_text().splitlines()) < 3:
            time.sleep(0.05)
        proc.send_signal(signal.SIGTERM)
        out, err = proc.communicate(timeout=30)
        self.assertEqual(proc.returncode, 1)
        run = m.loads_strict((evidence / 'run.json').read_bytes())
        self.assertEqual(run['workload_status'], 'failed')
        pairs = read_rows(private / 'pairs.full.jsonl')
        self.assertEqual(len(pairs), 14)
        self.assertIn('not_run', {r['status'] for r in pairs})
        self.assertTrue(all(r['error_class'] == 'runner_abort' for r in pairs if r['status'] == 'not_run'))
        with redirect_stdout(io.StringIO()):
            result = ev.finalize(evidence, private)
        self.assertEqual(result['run_status'], 'INCOMPLETE')
        self.assertGreater(result['coverage']['missing'], 0)
        self.assertNotIn(b'"', out + err)  # progress only, never row content

    def test_sigkill_leaves_pessimistic_evidence(self):
        tools, conformance = shim_tools(self.tmp / 'kill-tools', delta='slow')
        evidence, private = self.tmp / 'kill-ev', self.tmp / 'kill-pr'
        proc = subprocess.Popen([sys.executable, str(WORK / 'tools' / 'oracle_run.py'), 'run', 'smoke', str(tools),
                                 str(conformance), str(self.tmp / 'syn' / 'store'), str(evidence), str(private),
                                 str(self.tmp / 'syn')], env={**os.environ, **ENV}, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        while not (private / 'pairs.full.jsonl').exists() or \
                len((private / 'pairs.full.jsonl').read_text().splitlines()) < 2:
            time.sleep(0.05)
        proc.kill()
        proc.wait()
        with open(private / 'pairs.full.jsonl', 'a') as torn:
            torn.write('{"schema":"delsk.oracle.pair.v1","stat')  # a write cut by the kill
        self.assertEqual(m.loads_strict((evidence / 'run.json').read_bytes())['workload_status'], 'failed')
        with redirect_stdout(io.StringIO()):
            result = ev.finalize(evidence, private)
        self.assertEqual(result['run_status'], 'INCOMPLETE')
        self.assertEqual(ev.verify(evidence), [])

    def test_sealed_costs_never_leak(self):
        summary = self.tmp / 'step-summary'
        os.environ['GITHUB_STEP_SUMMARY'] = str(summary)
        self.addCleanup(os.environ.pop, 'GITHUB_STEP_SUMMARY')
        _, result, evidence, private = self.run_shims()
        occurrences = ev.parse_doc((evidence / 'corpus-lock.json').read_bytes())['occurrences']
        sealed = {o['occurrence_id'] for o in occurrences if o['split'] == 'evaluation'}
        secrets = set()
        for row in read_rows(private / 'pairs.full.jsonl') + read_rows(private / 'standalone.full.jsonl'):
            if row['target_occurrence_id'] in sealed:
                for key in ('patch_sha256', 'compressed_sha256'):
                    if row.get(key):
                        secrets.add(row[key])
                for key in ('patch_payload_bytes', 'delta_total_bytes', 'compressed_payload_bytes',
                            'compressed_total_bytes', 'raw_total_bytes', 'target_bytes', 'decoded_bytes'):
                    if row.get(key) is not None:
                        secrets.add(f'"{key}":{row[key]}')
                        secrets.add(f'"{key}": {row[key]}')
        self.assertGreater(len(secrets), 10)
        published = b''.join(p.read_bytes() for p in evidence.iterdir() if p.is_file()).decode('utf-8')
        for secret in secrets:
            self.assertNotIn(secret, published)
            self.assertNotIn(secret, self.logs)
        self.assertFalse(summary.exists() and summary.read_text())
        sealed_rows = [r for name in ('pairs.jsonl', 'standalone.jsonl', 'targets.jsonl')
                       for r in ev.parse_jsonl((evidence / name).read_bytes()) if r['target_occurrence_id'] in sealed]
        self.assertTrue(sealed_rows and all(r['schema'].endswith('-sealed.v1') for r in sealed_rows))
        evaluation = (evidence / 'evaluation.json').read_text()
        self.assertFalse(any(t in evaluation for t in sealed))  # no per-target metric row of the sealed split

    def test_refusals(self):
        tools, conformance = shim_tools(self.tmp / 'ref-tools')
        natural = self.tmp / 'natural'
        natural.mkdir()
        shutil.copy(WORK / 'corpus' / 'e1' / 'candidate-lock.json', natural / 'candidate-lock.json')
        shutil.copy(self.tmp / 'syn' / 'corpus-lock.json', natural / 'corpus-lock.json')
        with self.assertRaises(orun.RunError):  # smoke on the natural C_t
            orun.prepare('smoke', tools, conformance, natural, ENV)
        with self.assertRaises(orun.RunError):  # pilot without conformance PASS / workflow_dispatch
            orun.prepare('pilot', tools, conformance, None, {**ENV, 'GITHUB_EVENT_NAME': 'pull_request'})
        with self.assertRaises(orun.RunError):
            orun.prepare('smoke', tools, conformance, self.tmp / 'syn', {**ENV, 'GITHUB_WORKFLOW_SHA': 'e' * 40})
        exe = self.tmp / 'ref-tools' / 'bin' / 'xdelta3'
        exe.write_text(exe.read_text() + '\n# substituted\n')
        with self.assertRaises(orun.RunError):  # PATH or binary substitution
            orun.prepare('smoke', tools, conformance, self.tmp / 'syn', ENV)
        exe.unlink()
        exe.symlink_to('/bin/true')
        with self.assertRaises(orun.RunError):
            orun.prepare('smoke', tools, conformance, self.tmp / 'syn', ENV)

    def test_stale_output_is_refused(self):
        tools, conformance = shim_tools(self.tmp / 'stale-tools')
        ctx = orun.prepare('smoke', tools, conformance, self.tmp / 'syn', ENV)
        (self.tmp / 'stale-ev').mkdir()
        (self.tmp / 'stale-ev' / 'pairs.jsonl').write_text('')
        with self.assertRaises(orun.RunError):
            orun.execute(ctx, self.tmp / 'syn' / 'store', self.tmp / 'stale-ev', self.tmp / 'stale-pr', ENV)

    def test_placeholders_are_whole_tokens(self):
        self.assertEqual(orun.argv_for(['{exe}', '-s', '{base}', 'x{base}'], '/e'),
                         ['/e', '-s', 'base.bin', 'x{base}'])
        with self.assertRaises(KeyError):
            orun.argv_for(['{unknown}'], '/e')


class SyntheticInputs(unittest.TestCase):
    def test_inputs_are_deterministic_and_well_formed(self):
        import gzip
        a, b = orun.conformance_inputs(), orun.conformance_inputs()
        self.assertEqual(a, b)
        base, target = a['C02']
        changed = sum(x != y for x, y in zip(base, target))
        self.assertTrue(500 <= changed <= 656)  # about 1% of 64 KiB
        self.assertEqual(a['C09'][1][:2], b'\x1f\x8b')
        self.assertEqual(len(gzip.decompress(a['C09'][1])), 48 << 10)
        self.assertEqual([len(a[c][1]) for c in ('C04', 'C06', 'C07')], [0, 0, 1])
        self.assertEqual(a['C08'][0], a['C08'][1])

    def test_frame_parsers(self):
        self.assertEqual(orun.vcdiff_windows(b'\xd6\xc3\xc4\x00\x00' + b'\x01\x05\x00\x02ab'), [1])
        with self.assertRaises(ValueError):
            orun.vcdiff_windows(b'\xd6\xc3\xc4\x00\x00' + b'\x01\x05\x00\x09ab')
        frame = b'\x28\xb5\x2f\xfd' + bytes([0x20]) + b'\x03' + (3 << 3 | 1 | 0).to_bytes(3, 'little') + b'abc'
        self.assertIsNone(orun.zstd_frame_error(frame, 3))
        self.assertEqual(orun.zstd_frame_error(frame, 4), 'content size differs')
        self.assertEqual(orun.zstd_frame_error(frame[:4] + bytes([0x24]) + frame[5:], 3), 'checksum flag set')
        self.assertEqual(orun.zstd_frame_error(frame + b'x', 3), 'bytes after the frame')


@unittest.skipUnless(LINUX and os.environ.get('ORACLE_TOOLS'), 'needs the pinned codecs built by oracle_build.py')
class PinnedCodecs(unittest.TestCase):
    """Real xdelta3 3.2.1 / zstd 1.5.7 from the build record named by ORACLE_TOOLS; synthetic inputs only."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='oracle-pinned-test-'))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        _, self.codecs = orun.load_tools(os.environ['ORACLE_TOOLS'], LOCK_DATA)

    def test_malformed_patch_and_frame_are_decode_mismatch(self):
        base, target = orun.conformance_inputs()['C02']
        _, _, _, _, patch = orun.measure_delta(self.codecs['delta'], base, target, self.tmp, 1 << 26)
        for name, codec, inputs, template in (
                ('patch', self.codecs['delta'], {'base.bin': base, 'patch.bin': patch[:len(patch) // 2]}, 'patch'),
                ('frame', self.codecs['standalone'], {'payload.bin': b'\x28\xb5\x2f\xfd' + b'\0' * 9}, 'payload')):
            with self.subTest(name):
                d = orun.call_dir(self.tmp, inputs)
                lim = codec['limits']
                call = orun.invoke(orun.argv_for(codec['entry']['decode_argv'], codec['exe']), d,
                                   lim['decode_wall_seconds'], lim['address_space_bytes'], 1 << 26)
                failure = orun.decode_failure(call, orun.read_regular(d / 'decoded.bin', len(target)), target)
                self.assertEqual(failure[0], 'decode_mismatch')

    def test_conformance_passes_against_the_committed_golden(self):
        if not orun.GOLDEN.exists():
            self.skipTest('golden record not committed yet (first smoke writes the candidate)')
        doc, candidate = orun.conformance(os.environ['ORACLE_TOOLS'])
        self.assertEqual({c: v['status'] for c, v in doc['checks'].items()},
                         {f'C{i:02d}': 'PASS' for i in range(1, 15)})
        golden = m.loads_strict(orun.GOLDEN.read_bytes())
        self.assertEqual((candidate['golden'], candidate['inputs_sha256']), (golden['golden'], golden['inputs_sha256']))


if __name__ == '__main__':
    unittest.main()
