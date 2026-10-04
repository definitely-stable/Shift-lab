"""DELSK-002 E1 workload `candidate-seal`: build, independently verify, then write the lock.

    python3 e1_seal.py OUT_DIR

I/O adapter only: reads the closed frozen inputs from the repository, feeds the
builder a world whose occurrence and source order is permuted by ORDER_KEY (the
GitHub run ID and attempt, recorded in the evidence) and runs the independent
verifier. candidate-lock.json is written only after the verifier reports ok;
selection, coverage and verification evidence are written in every case.
Contract: .work/corpus/e0/construction-spec.md §7.
"""

import hashlib
import json
import os
from pathlib import Path
import sys
import time

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parents[1]
sys.path.insert(0, str(TOOLS))
import candidate_verify  # noqa: E402
import candidates  # noqa: E402
import manifests as m  # noqa: E402

CODE = ("candidates.py", "candidate_verify.py", "manifests.py", "e1_seal.py")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def permuted(items, key, order_key):
    return sorted(items, key=lambda item: sha(f"{order_key}:{item[key]}".encode()))


def main(argv, env):
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    out = Path(argv[0])
    out.mkdir(parents=True, exist_ok=True)
    order_key = f"{env.get('GITHUB_RUN_ID', 'local')}-{env.get('GITHUB_RUN_ATTEMPT', '0')}"
    run = {"schema": "delsk.e1.seal-run.v1", "status": "failed", "order_key": order_key,
           "code_sha256": {name: sha((TOOLS / name).read_bytes()) for name in CODE},
           "scorer": "NOT_RUN", "encoder": "NOT_RUN", "oracle": "NOT_RUN"}
    try:
        inputs = {name: (ROOT / path).read_bytes() for name, (path, _) in candidates.INPUTS.items()}
        started = time.monotonic()
        world, params, bindings, layout = candidates.admit(inputs)
        world = {**world, "occurrences": permuted(world["occurrences"], "occurrence_id", order_key),
                 "sources": permuted(world["sources"], "source_id", order_key)}
        run["builder_iteration_order_sha256"] = m.digest([o["occurrence_id"] for o in world["occurrences"]])
        result = candidates.construct(world, params)
        lock = candidates.make_lock(bindings, result, params)
        selection = m.canonical_bytes(result["selection"])
        cover = m.canonical_bytes(candidates.coverage(world, params, result, layout))
        run["builder_ms"] = int((time.monotonic() - started) * 1000)
        (out / "selection.json").write_bytes(selection)
        (out / "coverage.json").write_bytes(cover)
        started = time.monotonic()
        report = candidate_verify.verify(inputs, (ROOT / candidate_verify.E0_FREEZE[0]).read_bytes(),
                                         lock, result["selection"])
        run["verifier_ms"] = int((time.monotonic() - started) * 1000)
        (out / "verification.json").write_bytes(m.canonical_bytes(report))
        run.update(bindings=bindings, verification=report["status"], selection_sha256=sha(selection),
                   coverage_sha256=sha(cover), candidate_lock_sha256=sha(lock),
                   planned_pairs_per_codec=result["planned_pairs_per_codec"],
                   queries=len(result["queries"]),
                   near_queries=sum(q["status"] == "near_duplicate" for q in result["queries"]))
        if report["status"] == "ok":
            (out / "candidate-lock.json").write_bytes(lock)
            run["status"] = "ok"
        else:
            run["status"] = "verification_failed"
    except (candidates.CandidateError, ValueError, KeyError, TypeError, OSError) as error:
        run.update(status="failed", error=f"{type(error).__name__}: {error}")
    (out / "seal-run.json").write_bytes(m.canonical_bytes(run))
    print(json.dumps({k: run.get(k) for k in ("status", "candidate_lock_sha256", "verification", "error")}))
    return 0 if run["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:], os.environ))
