# S4-C implementation: sealed holdout execution

Status: **IMPLEMENTED / NOT_RUN**.  
Protocol authority: `0027d521a48701e504438a3ba750594647358d55` (PR #62, preregistered S4-C v2 index-cost verdict erratum). Original v1: `abf6bd07540a132ddf2af4fa1001db103b27a9f8` (unchanged).  
Consumer: `definitely-stable/ChunkShift@74bb301b6d8ecc52cf0bc0e00d86fa174093d91b`.

This file describes execution only. It does not change [s4-confirmation.md](s4-confirmation.md), K=2, the sealed evaluation population or any G5 threshold.

## Execution graph

After this implementation PR is squash-merged directly on top of
`0027d521a48701e504438a3ba750594647358d55`:

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

Before artifact verification, a bounded read-only provider poll ensures both exact first-attempt runs have actually completed successfully. Repeat B dispatches the evaluator before the provider can necessarily mark its own workflow completed; this barrier avoids a scheduling race without dispatching any new run, retrying measurements, or weakening identity gates.

Artifact ZIP bytes are checked against GitHub's digest before extraction. The extracted file set is closed.

The final verdict is produced only by `selector_s4_confirmation_v2.py` at protocol authority
`0027d521a48701e504438a3ba750594647358d55` (the immutable original v1 evaluator remains preserved).

Possible scientific verdicts remain exactly:

- `G5_SCOPED_PASS_K2`;
- `G5_REJECT_K2`;
- `INVALID`.

No result exists until both natural repeats and the immutable evaluator complete.

## Independent preflight audit and protocol v2 handoff (2026-10-08; synthetic only)

- The Rust driver accepts 0..8 distinct bottom hashes for short, empty, or repetitive objects; the frozen descriptor storage cost still reserves 64 bytes per catalog object.
- The synthetic adversarial example with two disjoint 8-hash descriptors costs 192 index bytes (96 B/object), exceeding the unchanged 64 B/object gate. This does not predict the held-out bzip2 result.
- Before any E1 measurement, protocol-only PR #62 was merged as exact authority `0027d521a48701e504438a3ba750594647358d55`. Its v2 evaluator treats a structurally valid over-budget index as **G5_REJECT_K2**, not **INVALID**. Negative, missing, or malformed cost measurements remain INVALID. Original protocol v1 SHA `abf6bd07540a132ddf2af4fa1001db103b27a9f8` and its code remain immutable; quality/cost thresholds, selector K=2, consumer pin, dataset, and no-rerun policy are unchanged.
- Confirmation runtime and both independent plan/evaluator workflows pin the exact PR #62 authority; the first auto-start transition is restricted to `0027d521a48701e504438a3ba750594647358d55` → squash-merged implementation SHA.
- The index guardrail is global `Catalog::index_bytes` cost accounting; measured query timings in `delsk-confirm` are ranking already-materialized frozen per-target `C_t`, **not** H11 full-catalog indexed retrieval.
- Recheck the GitHub provider history before merge: no earlier S4-C E1 repeat/first-attempt dispatch may exist. If any is found, **stop**; the E1 split is no longer eligible for this new authority. Never manually retry failed repeat A/B/evaluator, never tune thresholds on opened evidence.

**Merge gate:** current `main` must still be exactly `0027d521a48701e504438a3ba750594647358d55`, all required GitHub-hosted checks must pass, and frozen test/evidence boundaries must be independently reviewed. PR #60 stays draft until first-attempt S4-C evidence is closed.
