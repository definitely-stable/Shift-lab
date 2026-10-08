# S4-C pre-measure erratum v2 — cost-bound verdict classification

Status: **DRAFT PREREGISTRATION / NOT_ACTIVE / E1 HOLDOUT NOT_OPENED**.
Parent authority: `abf6bd07540a132ddf2af4fa1001db103b27a9f8` (frozen S4-C v1; do not edit).
Tracks: [DELSK-012 #13](https://github.com/definitely-stable/Shift-lab/issues/13), [preflight correction #61](https://github.com/definitely-stable/Shift-lab/issues/61), implementation [PR #57](https://github.com/definitely-stable/Shift-lab/pull/57).

## Trigger and evidence boundary

The original preregistration says an otherwise valid cost-guardrail failure yields `G5_REJECT_K2`, not `INVALID` (see [s4-confirmation.md §§6,8](s4-confirmation.md)). The frozen v1 evaluator instead rejects any integer `index_bytes > 64 * objects` in the input validator. Current index accounting charges 8-byte keys and 4-byte posting IDs: for two valid 8-hash, no-overlap objects it reports 192 B = 96 B/object, violating the 64 B/object budget. This is a **deterministic synthetic structural example**, not a real bzip2 outcome.

Before first evaluation measurement, correct the v1 cost validation/decision inconsistency while explicitly retaining the original threshold. There is no data-dependent retuning, new candidate algorithm, K4 fallback or holdout inspection.

## Normative v2 delta (one decision class only)

- Preserve v1 cost input schema `delsk.chunkshift-s4-confirm.rust-cost.v1`, 9 targets, 106 pairs, K2, exact ChunkShift commit, paired seven rounds, every frozen quality/timing threshold, no rerun and no replacement attempt.
- `index_bytes` must be a nonnegative integer; malformed/missing/negative/boolean/non-integer fields are still `INVALID`.
- `index_budget_ok := index_bytes <= objects * 64`, unchanged bound.
- Valid cost evidence with `index_budget_ok == false` sets `cost.eligible = false`; if the remaining evidence passes validity checks, the **final** verdict is `G5_REJECT_K2`, not `INVALID`.
- Cold descriptor throughput ≥250 MiB/s and p95 query ≤50 µs are unchanged. They remain eligibility conditions, not validity criteria.
- Other `INVALID` causes (missing/duplicate pair, bad identity, failed decode, parity drift, incorrect SHA/provenance, first-attempt mismatch, malformed costs/timings) remain failures. No other v1 production/evaluation contract behavior changes.

Candidate evaluator: [`selector_s4_confirmation_v2.py`](../tools/selector_s4_confirmation_v2.py), a self-contained copy of immutable v1 with only this cost-gate classification change and a versioned module header. Synthetic-only tests: [`test_selector_s4_confirmation_v2.py`](../tests/test_selector_s4_confirmation_v2.py).

## Freeze / merge gate, before any E1 materialization

1. Run hosted `Research documentation` + `Simple selector parity` checks; review exact source diff versus parent frozen file, require no other change.
2. Independently approve the scientific classification correction and merge this **protocol-only** PR first. The resulting exact `main` commit becomes the v2 protocol authority and must be recorded in #61/PR #57 with source SHA and decision note.
3. Rebind **all** S4-C authority references in PR #57 (plan producer, runner pin, evaluator command, workflow checker, known-answer tests) to the new SHA and evaluator v2. Change the one-shot `github.event.before` SHA to the protocol merge commit. Confirm no earlier S4-C repeat was dispatched. Re-run all hosted CI and verify exact parent before merge.
4. Only then approve PR #57 for its one-shot `main push → repeat A → repeat B → evaluator`; disallow replay. Hold H11 PR #60 as draft until S4-C final evidence is closed.

If any first-attempt S4-C evaluation was dispatched before this protocol correction, **abort this amendment** as post-observation and handle the old run under its preexisting authority. The old authority is retained verbatim for history. No future v2 decision may treat the already-opened bzip2 split as a fresh holdout.
