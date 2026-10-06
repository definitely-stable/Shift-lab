import hashlib
import json
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

import selector_s4_run as run  # noqa: E402


class Helpers(unittest.TestCase):
    def test_parse_field_is_exactly_one(self):
        self.assertEqual(run.parse_field("x=1\nmanifest-id=abc\n", "manifest-id"), "abc")
        with self.assertRaises(run.RunnerError):
            run.parse_field("manifest-id=a\nmanifest-id=b\n", "manifest-id")

    def test_locate_object_rehashes_every_store_hit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a, b = root / "a", root / "b"
            a.mkdir()
            b.mkdir()
            payload = b"hello"
            oid = hashlib.sha256(payload).hexdigest()
            (a / oid).write_bytes(payload)
            (b / oid).write_bytes(payload)
            self.assertEqual(run.locate_object(oid, (a, b)), a / oid)
            (b / oid).write_bytes(b"tampered")
            with self.assertRaises(run.RunnerError):
                run.locate_object(oid, (a, b))

    def test_verify_x0_requires_byte_identical_retained_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            protocol = root / "protocol"
            retained = protocol / run.X0_RETAINED
            fresh = root / "fresh"
            retained.mkdir(parents=True)
            fresh.mkdir()
            for name, data in (("corpus.json.gz", b"corpus"), ("candidates.json", b"candidates")):
                (retained / name).write_bytes(data)
                (fresh / name).write_bytes(data)
            got = run.verify_x0(protocol, fresh)
            self.assertEqual(set(got), {"corpus.json.gz", "candidates.json"})
            (fresh / "candidates.json").write_bytes(b"drift")
            with self.assertRaises(run.RunnerError):
                run.verify_x0(protocol, fresh)


class Cli(unittest.TestCase):
    def fake_cli(self, root):
        script = Path(root) / "fake_chunkshift.py"
        script.write_text(textwrap.dedent(
            """
            import hashlib
            from pathlib import Path
            import shutil
            import sys

            args = sys.argv[1:]
            if args[0] == "create":
                content, manifest = Path(args[1]), Path(args[2])
                assert args[3:] == ["--blake3"]
                manifest.write_bytes(b"manifest:" + content.read_bytes())
                print("manifest-id=m-" + hashlib.sha256(content.read_bytes()).hexdigest())
                raise SystemExit(0)

            if args[:2] == ["patch", "create"]:
                def value(name):
                    return args[args.index(name) + 1]
                target = Path(value("--target"))
                patch = Path(value("-o"))
                patch.write_bytes(target.read_bytes())
                print("target-manifest-id=x")
                raise SystemExit(0)

            if args[:2] == ["patch", "apply"]:
                patch = Path(args[2])
                output = Path(args[args.index("-o") + 1])
                shutil.copyfile(patch, output)
                print("applied=true")
                raise SystemExit(0)

            raise SystemExit(2)
            """
        ).strip() + "\n", encoding="utf-8")
        return script

    def test_pair_is_measured_and_manifests_are_cached(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "target"
            base = root / "base"
            target.write_bytes(b"target payload")
            base.write_bytes(b"base payload")
            target_oid = hashlib.sha256(target.read_bytes()).hexdigest()
            base_oid = hashlib.sha256(base.read_bytes()).hexdigest()
            cli = run.ChunkShiftCli(
                [sys.executable, str(self.fake_cli(root))],
                root / "manifests",
                root / "work",
            )
            row = cli.measure_pair(target_oid, target, base_oid, base)
            self.assertEqual(row["status"], "ok")
            self.assertEqual(row["applied_sha256"], target_oid)
            self.assertEqual(row["patch_file_digest"], target_oid)
            self.assertEqual(row["target_object_id"], target_oid)
            self.assertEqual(row["base_object_id"], base_oid)
            self.assertEqual(row["create_exit_code"], 0)
            self.assertEqual(row["apply_exit_code"], 0)
            self.assertEqual(len(cli.manifests), 2)

            again = cli.measure_pair(target_oid, target, base_oid, base)
            self.assertEqual(again["status"], "ok")
            self.assertEqual(len(cli.manifests), 2)


if __name__ == "__main__":
    unittest.main()
