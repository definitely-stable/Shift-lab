#!/usr/bin/env python3
"""Append-only preservation of ORIGINAL first-attempt S4-C GitHub evidence.

No new S4-C measurement, rerun, change to S4-C v3 thresholds, or consumer build.
Read existing GitHub-hosted provider artifacts, authenticate identities and ZIP
digests, replay the original v3 evaluator, and archive original binary bytes.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

REPO = "definitely-stable/Shift-lab"
SOURCE_SHA = "e002276e6820f2b2f2544a894d3de5c59da0d073"
PROTOCOL_SHA = "9ec28a0022651bb7416871089b0bcc4edd3454b8"
CONSUMER_SHA = "74bb301b6d8ecc52cf0bc0e00d86fa174093d91b"
ROOT = Path(".work/results/SELECTOR-S4C")
RUNS = {
    "A": (37804898028, 11562547245, "9b289cc785d2cbb14d0db9ec593aca431f743dd54db83c32455cb978ead24167"),
    "B": (37805606542, 11562722944, "a5937bc8b488392c62a1f031ed3fcf6c8a94581572407a5a04259b817d5996b3"),
    "evaluation": (37806374272, 11563067146, "30677da6695d84cb889fc4440885420c4452e414b3c3860d554fa72326c332b2"),
}
REPEAT_FILES = {"admission.json", "manifests.jsonl", "measurements.jsonl", "run.json", "rust-cost.json", "selection.json", "timing.json"}
EVAL_FILES = {"evaluation-run.json", "plan.json", "provider-index.jsonl", "result.json"}


def require(condition, message):
    if not condition:
        raise SystemExit("S4-C ARCHIVE FAIL CLOSED: " + message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def gh(endpoint):
    return json.loads(subprocess.check_output(["gh", "api", f"/repos/{REPO}/{endpoint}"], text=True))


def get_original(role, temp):
    run_id, artifact_id, zip_sha256 = RUNS[role]
    workflow = "selector-s4-confirm-evaluate.yml" if role == "evaluation" else "selector-s4-confirm-repeat.yml"
    provider = gh(f"actions/runs/{run_id}")
    for field, expected in {
        "id": run_id, "head_sha": SOURCE_SHA, "head_branch": "main",
        "run_attempt": 1, "event": "workflow_dispatch",
        "status": "completed", "conclusion": "success",
        "path": f".github/workflows/{workflow}",
    }.items():
        require(provider.get(field) == expected, f"{role}: provider mismatch {field}")
    artifacts = gh(f"actions/runs/{run_id}/artifacts?per_page=100")["artifacts"]
    require(len(artifacts) == 1, f"{role}: artifact count not exactly one")
    metadata = artifacts[0]
    name = f"delsk-s4c-evaluation-{run_id}-1" if role == "evaluation" else f"delsk-s4c-repeat-{role}-{run_id}-1"
    require(
        metadata.get("id") == artifact_id and metadata.get("name") == name
        and metadata.get("digest") == "sha256:" + zip_sha256
        and metadata.get("expired") is False,
        f"{role}: artifact id/digest/expiry drift",
    )
    archive = temp / f"{role}.zip"
    with archive.open("wb") as fd:
        subprocess.run(["gh", "api", f"/repos/{REPO}/actions/artifacts/{artifact_id}/zip"], check=True, stdout=fd)
    require(digest(archive.read_bytes()) == zip_sha256, f"{role}: ZIP SHA-256 mismatch")
    extracted = temp / role
    extracted.mkdir()
    with zipfile.ZipFile(archive) as z:
        entries = z.infolist()
        valid = EVAL_FILES if role == "evaluation" else REPEAT_FILES
        require(len(entries) == len(valid) and {e.filename for e in entries} == valid, f"{role}: unexpected ZIP members")
        for e in entries:
            require(
                not e.is_dir() and "/" not in e.filename and "\\" not in e.filename
                and ((e.external_attr >> 16) & 0o170000) != 0o120000,
                f"{role}: unsafe ZIP entry",
            )
            (extracted / e.filename).write_bytes(z.read(e))
    return {
        "provider_run_id": run_id, "run_attempt": 1, "artifact_id": artifact_id,
        "original_zip_sha256": zip_sha256,
        "original_zip_size": archive.stat().st_size,
        "extracted_sha256": {p.name: digest(p.read_bytes()) for p in sorted(extracted.iterdir())},
    }


def quality(root):
    records = [json.loads(line) for line in (root / "measurements.jsonl").read_text().splitlines() if line]
    require(len(records) == 115, "quality row count not 115")
    require(all(row.get("status") == "ok" for row in records), "failed quality row")
    sig = [
        (r["target_occurrence_id"], r.get("base_object_id") or "", r["patch_bytes"], r["applied_sha256"])
        for r in records
    ]
    require(len({(r[0], r[1]) for r in sig}) == 115, "duplicate quality row")
    return sorted(sig)


def main():
    require(os.environ.get("GITHUB_EVENT_NAME") == "push", "not GitHub push")
    require(os.environ.get("GITHUB_REF") == "refs/heads/research/delsk-s4c-evidence-lock", "unexpected branch")
    require(bool(os.environ.get("GH_TOKEN")), "missing GitHub token")
    require(not ROOT.exists(), "refuse to overwrite existing retained evidence")
    with tempfile.TemporaryDirectory(prefix="delsk-s4c-archive-") as wd:
        tmp = Path(wd)
        records = {name: get_original(name, tmp) for name in RUNS}
        a, b = tmp / "A", tmp / "B"
        require(quality(a) == quality(b), "A/B semantic quality drift")
        require((a / "selection.json").read_bytes() == (b / "selection.json").read_bytes(), "A/B selection mismatch")
        raw_equal = (a / "measurements.jsonl").read_bytes() == (b / "measurements.jsonl").read_bytes()
        for role, folder in (("A", a), ("B", b)):
            run = json.loads((folder / "run.json").read_text())
            for k, v in {
                "repeat": role, "run_id": RUNS[role][0], "run_attempt": 1,
                "protocol_authority": PROTOCOL_SHA, "implementation_sha": SOURCE_SHA,
                "chunkshift_commit": CONSUMER_SHA, "science_state": "COMPLETE",
            }.items():
                require(run.get(k) == v, f"{role}: original internal run provenance drift {k}")
        evaluation_run = json.loads((tmp / "evaluation" / "evaluation-run.json").read_text())
        for k, v in {
            "github_run_id": RUNS["evaluation"][0], "github_run_attempt": 1,
            "protocol_authority": PROTOCOL_SHA, "implementation_sha": SOURCE_SHA,
            "repeat_a_run_id": RUNS["A"][0], "repeat_b_run_id": RUNS["B"][0],
        }.items():
            require(evaluation_run.get(k) == v, f"evaluator run provenance drift {k}")
        result = json.loads((tmp / "evaluation" / "result.json").read_text())
        require(result.get("verdict") == "G5_SCOPED_PASS_K2", "unexpected original verdict")
        independent = tmp / "independent-evaluation.json"
        subprocess.run([
            sys.executable, ".work/tools/selector_s4_confirmation_v3.py",
            "evaluate", str(tmp / "evaluation" / "plan.json"),
            str(a), str(b), str(independent),
        ], check=True)
        require(json.loads(independent.read_text()) == result, "frozen independent evaluator replay differs")

        (ROOT / "source").mkdir(parents=True)
        for role in RUNS:
            shutil.copy2(tmp / f"{role}.zip", ROOT / "source" / f"{role}.zip")
            shutil.copytree(tmp / role, ROOT / role)
        shutil.copy2(independent, ROOT / "independent-evaluation.json")
        manifest = {
            "schema": "delsk.s4c.retained.v1",
            "protocol_sha": PROTOCOL_SHA,
            "source_sha": SOURCE_SHA,
            "consumer_sha": CONSUMER_SHA,
            "verdict": "G5_SCOPED_PASS_K2",
            "raw_measurements_identical": raw_equal,
            "semantic_quality_identical": True,
            "independent_frozen_v3_replay_identical": True,
            "artifacts": records,
        }
        (ROOT / "retained-manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
        print(json.dumps({"verdict": result["verdict"], "all_original_archives": True, "retained_files": 24}, sort_keys=True))


if __name__ == "__main__":
    main()
