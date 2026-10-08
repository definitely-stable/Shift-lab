# S4-C implementation: sealed holdout execution

Status: **IMPLEMENTED / NOT_RUN**.  
Frozen protocol authority: `abf6bd07540a132ddf2af4fa1001db103b27a9f8` (PR #55).  
Consumer: `definitely-stable/ChunkShift@74bb301b6d8ecc52cf0bc0e00d86fa174093d91b`.

This file describes execution only. It does not change [s4-confirmation.md](s4-confirmation.md), K=2, the sealed evaluation population or any G5 threshold.

## Execution graph

After this implementation PR is squash-merged directly on top of
`e1ee235fe08c7cc1f6e8ec8884b65439435adf92`:

`merge push → repeat A → repeat B → immutable evaluator`

The autostart is one-shot and checks the exact previous-main SHA. If main changes first, it does not open the holdout.

Each repeat is a separate first-attempt `workflow_dispatch` on standard `ubuntu-24.04`. There is no rerun/replacement path in the automation.

## Repeat execution

Each repeat independently:

1. checks out the implementation SHA and exact protocol authority;
2. rebuilds the 9-target / 106-base-pair plan from sealed metadata;
3. re-materializes the natural store in the GitHub-hosted runner;
4. builds pinned ChunkShift and the real Rust `delsk-confirm` driver;
5. computes Rust descriptors/Catalog/K2 selection;
6. independently computes Python K2 parity **before any CSP create**;
7. if parity is exact, creates/applies the complete 115-row quality table;
8. if all quality pairs are correct, executes seven frozen paired timing rounds;
9. uploads only compact evidence JSON/JSONL.

Natural objects, manifests, CSP files and reconstructed outputs remain in runner temp storage and are not uploaded.

Scientific pair/parity failures are retained and are not retried. Infrastructure/admission failure stops the one-shot chain.

## Rust path

`.work/selector/rust/src/bin/delsk-confirm.rs` uses the existing
`delsk-selector` library directly. It adds no dependency and does not alter selector semantics.

It records:

- unique objects and bytes scanned;
- real descriptor wall/process-CPU;
- real Catalog wall/process-CPU and `Catalog::index_bytes`;
- per-target K2 query time;
- seven query-only timing totals;
- exact Rust K2 IDs.

Python recomputes the same K2 IDs from the authority implementation only for parity.

## Final evaluator

`selector-s4-confirm-evaluate.yml` independently checks GitHub provider metadata for A and B:

- workflow_dispatch;
- completed/success;
- attempt 1;
- exact main implementation SHA;
- exact repeat workflow path;
- exactly one non-expired named artifact with SHA-256.

Artifact ZIP bytes are checked against GitHub's digest before extraction. The extracted file set is closed.

The final verdict is produced only by the evaluator at protocol authority
`abf6bd07540a132ddf2af4fa1001db103b27a9f8`.

Possible scientific verdicts remain exactly:

- `G5_SCOPED_PASS_K2`;
- `G5_REJECT_K2`;
- `INVALID`.

No result exists until both natural repeats and the immutable evaluator complete.
