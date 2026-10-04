"""DELSK-002/005 Slice F: R0 foundation handoff, payload-free recomputation and readiness gate.

    python3 recompute_foundation.py handoff OUT_DIR      Actions workload `foundation-handoff`
    python3 recompute_foundation.py bundle ARTIFACT_DIR  retain a downloaded run as .work/results/R0-FOUNDATION/<run>-<attempt>
    python3 recompute_foundation.py verify BUNDLE_DIR... recompute and check retained bundles
    python3 recompute_foundation.py readiness            R0 gate; exit 0 only when READY

Metadata only: reads the committed locks, never corpus payloads, scorer, encoder or oracle.
Contract prose: .work/ci-plan.md (Evidence bundle), .work/research/R0-readiness.md.
"""

import collections
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time

TOOLS = Path(__file__).resolve().parent
WORK = TOOLS.parent
ROOT = WORK.parent
sys.path.insert(0, str(TOOLS))
import manifests as m  # noqa: E402

RESULTS = WORK / "results" / "R0-FOUNDATION"
PILOT, E1 = WORK / "corpus" / "pilot-v1", WORK / "corpus" / "e1"
# Code that computes the handoff. Runner and workflow identity is the run's source SHA (run.json), not pinned here:
# the runner and workflow gain workloads in later slices, which must not invalidate retained R0 bundles.
CODE = ("recompute_foundation.py", "manifests.py")
E0 = WORK / "corpus" / "e0"
# candidate-lock binding -> the repository file it must hash.
BINDING_FILES = {"acquisition_freeze_sha256": PILOT / "freeze.json", "ancestry_audit_sha256": E0 / "ancestry-audit.json",
                 "construction_spec_sha256": E0 / "construction-spec.md", "historical_bytes_sha256": E0 / "historical-bytes.json",
                 "protocol_sha256": WORK / "protocol.md", "selection_policy_sha256": WORK / "corpus" / "selection-policy.json"}
SCHEMA = "delsk.r0.foundation-handoff.v1"
WORKLOAD = "foundation-handoff"
FILES = {"run.json", "workload/handoff.json", "workload/timings.jsonl", "checksums.sha256"}
WARMUPS, BLOCKS, ARMS = 2, 5, ("A1", "A2")
TIMED_BYTES = 8 << 20
HEX40 = re.compile(r"[0-9a-f]{40}\Z")


class FoundationError(Exception):
    pass


def sha(data):
    return hashlib.sha256(data).hexdigest()


def rel(path):
    return path.relative_to(ROOT).as_posix()


def check(condition, message):
    if not condition:
        raise FoundationError(message)


# --- accounting -----------------------------------------------------------

def freeze_graph():
    """SHA-256 of every file in the D -> E0 -> E1 freeze chain: the three root records and everything they pin.
    Any difference between roots, between a root and the file it pins, or in a pinned file is an error."""
    roots = {"pilot": PILOT / "freeze.json", "e0": E0 / "freeze.json", "seal": E1 / "seal.json"}
    docs = {name: m.loads_strict(path.read_bytes()) for name, path in roots.items()}
    check(docs["pilot"]["status"] == "FROZEN_ACQUISITION" and docs["e0"]["status"] == "FROZEN_DESIGN"
          and docs["seal"]["status"] == "SEALED", "freeze chain is not FROZEN_ACQUISITION -> FROZEN_DESIGN -> SEALED")
    pins = {rel(path): sha(path.read_bytes()) for path in roots.values()}
    for base, files in ((PILOT, docs["pilot"]["files"]), (ROOT, docs["e0"]["files"]), (ROOT, docs["e0"]["inputs"]),
                        (ROOT, docs["seal"]["files"])):
        for name, digest in files.items():
            path = rel(base / name)
            check(pins.setdefault(path, digest) == digest, f"{path}: two records pin different SHA-256 values")
    for path, digest in sorted(pins.items()):
        check(sha((ROOT / path).read_bytes()) == digest, f"{path}: differs from its pinned SHA-256")
    bindings = docs["seal"]["bindings"]
    check(bindings == docs["e0"]["candidate_lock_bindings"], "seal bindings differ from the E0 freeze bindings")
    for key, path in BINDING_FILES.items():
        check(pins.get(rel(path)) == bindings[key], f"binding {key} does not hash {rel(path)}")
    return dict(sorted(pins.items())), docs["pilot"], docs["seal"]


def account():
    """Content, lineage and candidate accounting recomputed from committed locks; cross-checked
    against the independently derived E1 seal summary and coverage. Returns (locks, accounting, limitations)."""
    locks, freeze, seal = freeze_graph()
    raw = gzip.decompress((PILOT / "corpus-lock.json.gz").read_bytes())
    check(sha(raw) == freeze["corpus_lock_canonical_sha256"], "corpus lock: canonical SHA-256 differs")
    corpus = m.loads_strict(raw)
    lock = m.loads_strict((E1 / "candidate-lock.json").read_bytes())
    check(lock["corpus_lock_sha256"] == sha(raw), "candidate lock is bound to another corpus lock")
    check({k: lock[k] for k in seal["bindings"]} == seal["bindings"], "candidate lock bindings differ from the seal")
    check(lock["planned_pairs_per_codec"] == seal["summary"]["planned_pairs_per_codec"], "seal pair count differs")
    cover = m.loads_strict((E1 / "coverage.json").read_bytes())

    family_split = {f: c["split"] for c in corpus["components"] for f in c["families"]}
    check(len(family_split) == sum(len(c["families"]) for c in corpus["components"]), "family in two components")
    occurrences = {o["occurrence_id"]: o for o in corpus["occurrences"]}
    check(len(occurrences) == len(corpus["occurrences"]), "duplicate occurrence id")
    splits_of = collections.defaultdict(set)
    for o in occurrences.values():
        check(family_split.get(o["family_id"]) == o["split"], f"occurrence {o['occurrence_id']}: split differs from its lineage component")
        splits_of[o["object_id"]].add(o["split"])
    by_split = {s: {"content_classes": 0, "occurrences": 0} for s in m.SPLITS}
    for o in occurrences.values():
        by_split[o["split"]]["occurrences"] += 1
    for splits in splits_of.values():
        for s in splits:
            by_split[s]["content_classes"] += 1
    content = {"by_split": by_split, "content_classes": len(splits_of),
               "cross_split_classes": sum(len(s) > 1 for s in splits_of.values()),
               "materialized_bytes": corpus["materialized_bytes"], "occurrences": len(occurrences)}
    check(content["cross_split_classes"] == cover["universe"]["cross_split_classes"] == 0, "cross-split content classes")
    check((content["content_classes"], content["occurrences"]) ==
          (cover["universe"]["content_classes"], cover["universe"]["occurrences"]), "universe differs from E1 coverage")
    per_occ = collections.Counter(o["family_id"] for o in occurrences.values())
    lineage = {"components": sorted(({"families": c["families"], "occurrences": sum(per_occ[f] for f in c["families"]),
                                      "split": c["split"]} for c in corpus["components"]), key=lambda c: c["families"])}

    pairs, kinds, per_family = 0, collections.Counter(), collections.Counter()
    for q in lock["queries"]:
        target = occurrences.get(q["target"])
        check(target is not None, f"query target {q['target']} is not a corpus occurrence")
        check(q["candidate_count"] == len(q["bases"]), f"{q['target']}: candidate_count differs from bases")
        for base in q["bases"]:
            check(splits_of.get(base["object_id"]) == {target["split"]}, f"{q['target']}: base outside the target split")
            check(base["object_id"] != target["object_id"], f"{q['target']}: target class is its own base")
        pairs += q["candidate_count"]
        per_family[target["family_id"]] += q["candidate_count"]
        kinds[q["status"]] += 1
    summary = seal["summary"]
    check(pairs == lock["planned_pairs_per_codec"] == cover["pair_plan"]["total"] <= m.P1_CAPS["planned_pairs_per_codec_max"],
          "planned pairs differ or exceed the P1 cap")
    check(dict(per_family) == cover["pair_plan"]["by_component"], "pairs per component differ from E1 coverage")
    check((len(lock["queries"]), kinds["near_duplicate"], kinds["identity_only"]) ==
          (summary["queries"], summary["near_queries"], summary["identity_queries"]), "query counts differ from the seal")
    candidates = {"identity_queries": kinds["identity_only"], "near_queries": kinds["near_duplicate"],
                  "pairs_by_family": dict(sorted(per_family.items())), "planned_pairs_per_codec": pairs,
                  "queries": len(lock["queries"])}
    return locks, {"candidates": candidates, "content": content, "lineage": lineage}, seal["limitations"]


def handoff_doc():
    locks, accounting, limitations = account()
    return {"schema": SCHEMA, "evidence_scope": "foundation", "oracle": "NOT_RUN", "quality_verdict": "N/A",
            "scope": "R0 exploratory pilot: acquisition, lineage and sealed C_t accounting. No scorer, encoder, "
                     "oracle or quality result exists; this is not a G1-G5 verdict.",
            "locks": locks, "accounting": accounting, "limitations": limitations,
            "tools": {name: sha((TOOLS / name).read_bytes()) for name in CODE}}


def timing_plan():
    """Expected (block, arm, position, warmup) sequence: arm order alternates per block."""
    return [(block, arm, position, block < WARMUPS) for block in range(WARMUPS + BLOCKS)
            for position, arm in enumerate(ARMS if block % 2 == 0 else ARMS[::-1])]


def timing_rows():
    """A/A service timing of one SHA-256 over 8 MiB (2 warmups, 5 blocks, arm order alternates).
    Records the timing recorder only: it does not calibrate a future encoder or change the P1 noise gate."""
    data = bytes(range(256)) * (TIMED_BYTES // 256)
    rows = []
    for block, arm, position, warmup in timing_plan():
        start = time.perf_counter_ns()
        hashlib.sha256(data).digest()
        rows.append({"arm": arm, "block": block, "ns": time.perf_counter_ns() - start, "position": position, "warmup": warmup})
    return rows


def handoff(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "handoff.json").write_bytes(m.canonical_bytes(handoff_doc()))
    (out / "timings.jsonl").write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in timing_rows()))


# --- retained bundles -----------------------------------------------------

def checksums(directory):
    files = sorted(p for p in directory.rglob("*") if p.is_file() and p.name != "checksums.sha256")
    return "".join(f"{sha(p.read_bytes())}  {p.relative_to(directory).as_posix()}\n" for p in files)


def check_timings(text):
    rows = [json.loads(line) for line in text.splitlines()]
    check(all(type(r) is dict and set(r) == {"arm", "block", "ns", "position", "warmup"} and type(r["ns"]) is int and r["ns"] > 0
              for r in rows), "timings: malformed row")
    check([(r["block"], r["arm"], r["position"], r["warmup"]) for r in rows] == timing_plan(),
          "timings: rows differ from the expected block, arm order and warmup sequence")


def verify(directory, name=None):
    """Errors for one retained bundle; [] means it recomputes. Checks identities, checksums and accounting."""
    directory = Path(directory)
    name = name or directory.name
    try:
        present = {p.relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file()}
        check(present == FILES, f"files: missing {sorted(FILES - present)}, unexpected {sorted(present - FILES)}")
        check((directory / "checksums.sha256").read_text() == checksums(directory), "checksums differ or bundle is truncated")
        run = json.loads((directory / "run.json").read_text())
        g = run["environment"]["github"]
        check(run["schema"] == "delsk.ci.foundation-run.v1" and run["workload"] == WORKLOAD, "run.json: not a foundation-handoff run")
        check((run["evidence_scope"], run["oracle"], run["quality_verdict"]) == ("foundation", "NOT_RUN", "N/A"), "run.json: scope fields")
        check(run["status"] == "ok" and run.get("exit_code") == 0, f"run.json: status {run['status']!r} (failed or cancelled attempt)")
        check(HEX40.match(run["source_sha"] or "") and g["GITHUB_SHA"] == g["GITHUB_WORKFLOW_SHA"] == run["source_sha"], "run.json: source/workflow SHA")
        check(g["RUNNER_ARCH"] == "X64" and run["admission"].get("admitted") is True, "run.json: runner arch or admission")
        check(name == f"{g['GITHUB_RUN_ID']}-{g['GITHUB_RUN_ATTEMPT']}", "directory name differs from run id and attempt")
        doc = m.loads_strict((directory / "workload" / "handoff.json").read_bytes())
        fresh = handoff_doc()
        check(set(doc) == set(fresh) and set(doc["tools"]) == set(CODE), "handoff.json: unexpected schema")
        for key in fresh:
            check(doc[key] == fresh[key], f"handoff.json: {key} differs from recomputation")
        check_timings((directory / "workload" / "timings.jsonl").read_text())
    except (FoundationError, KeyError, TypeError, ValueError, AttributeError, OSError) as error:
        return [f"{name}: {type(error).__name__}: {error}"]
    return []


def bundle(artifact):
    """Retain a downloaded foundation artifact. Copied and verified in a staging sibling, then renamed:
    a missing or bad artifact leaves nothing under RESULTS."""
    artifact = Path(artifact)
    g = json.loads((artifact / "run.json").read_text())["environment"]["github"]
    dest = RESULTS / f"{g['GITHUB_RUN_ID']}-{g['GITHUB_RUN_ATTEMPT']}"
    check(not dest.exists(), f"{dest.name} is already retained")
    RESULTS.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{dest.name}.", dir=RESULTS))
    try:
        for name in sorted(FILES - {"checksums.sha256"}):
            (stage / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(artifact / name, stage / name)
        (stage / "checksums.sha256").write_text(checksums(stage))
        errors = verify(stage, dest.name)
        check(not errors, "; ".join(errors))
        stage.rename(dest)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    return dest


def readiness(results=RESULTS):
    """R0 gate: READY needs a SEALED E1 and >=2 verified bundles from distinct run IDs whose handoff.json is byte-identical."""
    blockers = []
    try:
        handoff_doc()
    except (FoundationError, KeyError, ValueError, OSError) as error:
        blockers.append(f"locks do not recompute: {error}")
    good = {}
    for d in sorted(Path(results).glob("*")) if Path(results).is_dir() else []:
        errors = verify(d)
        blockers += errors
        if not errors:
            good[d.name] = (d / "workload" / "handoff.json").read_bytes()
    runs = {}
    for name, data in good.items():
        runs.setdefault(data, set()).add(name.rsplit("-", 1)[0])
    if not any(len(ids) >= 2 for ids in runs.values()):
        blockers.append(f"need 2 verified bundles from distinct run IDs with identical handoff.json, have {len(good)} bundle(s)")
    return {"ready": not blockers, "blockers": blockers, "bundles": sorted(good)}


def main(argv):
    command, args = (argv[0], argv[1:]) if argv else (None, [])
    try:
        if command == "handoff" and len(args) == 1:
            handoff(args[0])
        elif command == "bundle" and len(args) == 1:
            print(f"retained {rel(bundle(args[0]))}")
        elif command == "verify" and args:
            errors = [e for d in args for e in verify(d)]
            print("\n".join(errors) or "verified")
            return 1 if errors else 0
        elif command == "readiness" and not args:
            result = readiness()
            print(f"R0 foundation gate: {'READY' if result['ready'] else 'NOT READY'}")
            print("\n".join(f"- {b}" for b in result["blockers"]))
            return 0 if result["ready"] else 1
        else:
            print(__doc__, file=sys.stderr)
            return 2
    except (FoundationError, KeyError, ValueError, OSError) as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
