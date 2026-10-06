# S4 implementation runner

Status: **IMPLEMENTED / NOT_RUN**.  
Protocol authority: `ea35f16a0f52cd7c41df2763f0bd2794fbbdb476` (merge of PR #52).  
ChunkShift consumer: `74bb301b6d8ecc52cf0bc0e00d86fa174093d91b`.

This slice implements the measurement transport for the already-frozen [S4 development screen](s4.md). It does not change the plan, lanes, thresholds or evaluator.

## Boundary

The workflow refuses to run anywhere except the current `refs/heads/main`. Therefore this implementation cannot produce an authorized S4 result while it is still only a PR branch.

At runtime it uses three independent trees:

1. current reviewed Shift-lab main — implementation runner and budget/admission;
2. separate checkout of the exact S4 protocol-authority merge — plan builder, retained inputs, natural materializers and final evaluator;
3. separate checkout of the exact ChunkShift consumer pin — public CLI only.

The implementation tree never supplies the S4 plan or decision function.

## One-job execution

The first implementation deliberately uses one standard `ubuntu-24.04` job with `timeout-minutes: 30`.

Reasons:

- it preserves the existing one-job `RUN_RESERVATION_MINUTES=30` admission semantics;
- the frozen workload is small objects even though it contains 3,815 creates;
- no matrix race or multi-job budget accounting is introduced before evidence says sharding is necessary.

If the job cannot finish inside the cap, the outcome is infrastructure failure / no S4 verdict. A later implementation-only change may deterministically shard the exact frozen pair set, as allowed by S4 §8, without changing §§1–6.

## Data path

After admission:

1. the authority checkout builds `plan.json`;
2. pilot development/calibration objects are re-materialized by the already-reviewed natural materializer;
3. X0 objects are re-materialized by the already-reviewed X0 acquisition path;
4. the runner requires freshly generated X0 `corpus.json.gz` and `candidates.json` to be byte-identical to the retained X0 run metadata;
5. every object required by the plan is re-hashed against its SHA-256 object id before ChunkShift sees it;
6. the pinned ChunkShift CLI is built in Release/net10.0;
7. manifests are created once per unique object with `--blake3`, no BIDX;
8. exactly 3,815 self-contained/base-dependent CSP create+apply measurements are executed;
9. every row is flushed and fsynced as it is produced;
10. only after measurement completes does the authority checkout execute the frozen evaluator.

Payload files, manifests, CSP files and reconstructed outputs remain under `RUNNER_TEMP` and are not uploaded.

## Fail-closed behavior

A result cannot silently improve when evidence is missing.

- wrong protocol/consumer git head -> runner fails;
- tracked modification of either external tree -> runner fails;
- fresh X0 metadata drift -> runner fails;
- absent/tampered object -> runner fails;
- manifest creation failure -> runner fails before a decision result exists;
- pair create/apply/verification failure -> retained failed row;
- missing/extra pair row -> frozen evaluator rejects;
- reconstruction SHA mismatch -> frozen evaluator returns `INVALID`;
- timeout before complete evidence -> workflow failure, no S4 verdict;
- artifact cap failure -> workflow failure even if measurement succeeded.

## Evidence

The compact artifact contains:

- `admission.json`;
- frozen `plan.json`;
- `pilot-materialization.json`;
- `x0-materialization.log`;
- `run.json`;
- `measurements.jsonl`;
- `result.json` only when frozen evaluation completed.

`run.json` binds protocol authority, implementation SHA, workflow SHA/ref/run/attempt, consumer commit, runner image/arch/kernel, .NET version, CLI assembly digest, fresh X0 metadata digests, object/descriptor accounting and manifest construction cost.

The development screen remains in-sample and cannot produce G5.
