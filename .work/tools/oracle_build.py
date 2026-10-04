"""DELSK-003 Slice B: build the two pinned codecs of delsk.oracle-contract.v1 from their exact source archives.

    python3 oracle_build.py OUT_DIR

For each codec of .work/oracle/codec-lock.json: download the release archive (https only, byte cap = locked size),
check size, SHA-256 and that the URL is the locked repository's release asset for the locked tag, expand it in memory
(materialize.expand/normalize: no traversal, absolute paths, duplicates or second top directory), write regular files
only (links and special members are skipped and recorded, never created), run the exact locked build argv with
exactly the locked environment (nothing inherited) and record durable provenance in OUT_DIR/tools.json: archive and
executable SHA-256, compiler and make identity, argv, environment, self report and source/workflow SHA.

Never uses a system codec or a package manager: the runner invokes only the executables recorded here, after
re-hashing them. Linux only (GitHub-hosted ubuntu-24.04 x64).
"""

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys

TOOLS = Path(__file__).resolve().parent
WORK = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import manifests as m  # noqa: E402
import materialize  # noqa: E402

CODEC_LOCK = WORK / "oracle" / "codec-lock.json"
EXPANDED_CAP = 64 << 20  # both sources expand to < 9 MiB
BUILD_SECONDS = 300
SELF_REPORT = {"delta": ["config"], "standalone": ["-vV"]}
# Oracle code of the measurement: Hc of this manifest is the run's oracle_code_sha256, and it binds the in-job
# evaluator identity (oracle_eval.py) that bundle verification checks.
CODE_FILES = ("oracle_build.py", "oracle_run.py", "oracle_eval.py", "manifests.py", "materialize.py")
INVOKE_ENV = {"LC_ALL": "C"}


class BuildError(Exception):
    pass


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def code_manifest():
    return {name: sha256((TOOLS / name).read_bytes()) for name in CODE_FILES}


def check_source(source, data):
    """Archive identity: https release asset of the locked repository and tag, exact size and SHA-256."""
    url, repo, tag = source["archive_url"], source["repository"], source["tag"]
    if not url.startswith(f"{repo}/releases/download/{tag}/") or not url.startswith("https://github.com/"):
        raise BuildError(f"archive URL is not a release asset of {repo} {tag}")
    if (len(data), sha256(data)) != (source["archive_bytes"], source["archive_sha256"]):
        raise BuildError(f"{url}: size or SHA-256 differs from the codec lock")


def extract(data, root, dest):
    """Write the regular files of a verified tar.gz under dest/root; returns (files, tree digest, skipped members).
    Links, devices and other special members are never created."""
    entries, _ = materialize.expand(data, "tar.gz", EXPANDED_CAP)
    top, members = materialize.normalize(entries)
    if top != root:
        raise BuildError(f"archive top directory {top!r} is not the locked root {root!r}")
    base = Path(dest) / root
    base.mkdir(parents=True)
    files, skipped = [], []
    for member in members:
        if member["type"] != "file":
            skipped.append({"path": member["path"], "type": member["type"]})
            continue
        path = base / member["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o644)
        with os.fdopen(fd, "wb") as out:
            out.write(member["data"])
        files.append([member["path"], member["sha256"]])
    return len(files), m.digest(files), skipped


def tool_identity(name, path="/usr/bin:/bin"):
    """Resolved path, SHA-256 and first version line of a build tool found on the locked build PATH."""
    found = shutil.which(name, path=path)
    if found is None:
        raise BuildError(f"{name} is not on {path}")
    real = os.path.realpath(found)
    out = subprocess.run([found, "--version"], env={"LC_ALL": "C", "PATH": path}, stdin=subprocess.DEVNULL,
                         capture_output=True, timeout=30, check=True)
    return {"path": found, "realpath": real, "sha256": sha256(Path(real).read_bytes()),
            "version": out.stdout.decode("utf-8", "replace").splitlines()[0]}


def self_report(exe, role, cwd):
    out = subprocess.run([str(exe), *SELF_REPORT[role]], cwd=cwd, env=dict(INVOKE_ENV), stdin=subprocess.DEVNULL,
                         capture_output=True, timeout=30)
    if out.returncode != 0:
        raise BuildError(f"{role}: self report exited {out.returncode}")
    return (out.stdout + out.stderr).decode("utf-8", "replace")


def build_codec(role, codec, out, fetcher=materialize.fetch):
    source, build = codec["source"], codec["build"]
    data, _, _ = fetcher(source["archive_url"], source["archive_bytes"])
    check_source(source, data)
    archive = out / "archives" / f"{source['archive_root']}.tar.gz"
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_bytes(data)
    count, tree, skipped = extract(data, source["archive_root"], out / "src")
    cwd = out / "src" / build["cwd"]
    log = out / f"build-{role}.log"
    with open(log, "wb") as sink:
        done = subprocess.run(build["argv"], cwd=cwd, env=dict(build["env"]), stdin=subprocess.DEVNULL,
                              stdout=sink, stderr=subprocess.STDOUT, timeout=BUILD_SECONDS)
    if done.returncode != 0:
        raise BuildError(f"{role}: build exited {done.returncode}; see {log.name}")
    exe = cwd / build["executable"]
    if exe.is_symlink() or not exe.is_file():
        raise BuildError(f"{role}: build did not produce a regular executable")
    scratch = out / f"report-{role}"
    scratch.mkdir()
    report = self_report(exe.resolve(), role, scratch)
    shutil.rmtree(scratch)
    blob = exe.read_bytes()
    return {"codec_id": codec["codec_id"], "archive_url": source["archive_url"], "archive_bytes": len(data),
            "archive_sha256": sha256(data), "archive_root": source["archive_root"],
            "archive_path": archive.relative_to(out).as_posix(), "extracted_files": count,
            "extracted_tree_sha256": tree, "skipped_members": skipped, "build_argv": build["argv"],
            "build_cwd": build["cwd"], "build_env": build["env"], "executable": exe.relative_to(out).as_posix(),
            "executable_bytes": len(blob), "executable_sha256": sha256(blob), "self_report": report}


def main(argv, env=os.environ):
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    out = Path(argv[0]).resolve()
    if out.exists() and any(out.iterdir()):
        print(f"{out} is not empty: stale build outputs are never reused", file=sys.stderr)
        return 1
    out.mkdir(parents=True, exist_ok=True)
    try:
        data = CODEC_LOCK.read_bytes()
        lock = m.loads_strict(data)
        tools = {"schema": "delsk.oracle.tools.v1", "codec_lock_sha256": sha256(data),
                 "compiler": tool_identity("cc"), "make": tool_identity("make"),
                 "codecs": {role: build_codec(role, lock["codecs"][role], out) for role in ("delta", "standalone")},
                 "code": code_manifest(),
                 "source": {k.lower(): env.get(f"GITHUB_{k}") for k in ("SHA", "WORKFLOW_SHA", "RUN_ID",
                                                                         "RUN_ATTEMPT")}}
        (out / "tools.json").write_bytes(m.canonical_bytes(tools))
    except (BuildError, materialize.MaterializeError, subprocess.SubprocessError, OSError, ValueError) as error:
        print(f"BUILD FAILED: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    for role, c in tools["codecs"].items():
        print(f"{role}: {c['codec_id']} archive {c['archive_sha256']} executable {c['executable_sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
