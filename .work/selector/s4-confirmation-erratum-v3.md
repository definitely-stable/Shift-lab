# S4-C pre-measure erratum v3 — runner-name independence witness

Status: **DRAFT / NOT_ACTIVE / E1 HOLDOUT NOT OPENED**. Protocol-only preregistration for [issue #63](https://github.com/definitely-stable/Shift-lab/issues/63); requires independent review and GitHub-hosted CI before freeze/activation.

Parent v2 authority: `0027d521a48701e504438a3ba750594647358d55` (pre-measure memory-cost classification fix, PR #62).
Historical v1 authority: `abf6bd07540a132ddf2af4fa1001db103b27a9f8` (unchanged).
Neither historical evaluator is edited.

## Observed structural defect (no natural data)

S4-C §4 requires different run IDs and different runner names. The authoritative v2 evaluator rejects equal `run.runner_name`. GitHub's official `RUNNER_NAME` and `runner.name` references explicitly state that a runner name **may not be unique**, even within one workflow run. This attribute is a display name, not a unique worker or VM identifier. Independent job runs on standard hosted runners use fresh VMs.

Primary sources:
- https://docs.github.com/en/actions/reference/workflows-and-actions/variables
- https://docs.github.com/en/enterprise-cloud@latest/actions/reference/workflows-and-actions/contexts
- https://docs.github.com/en/actions/reference/runners/github-hosted-runners

Two independently executed, valid jobs with separate GitHub `workflow_dispatch` run IDs and attempt=1 may have identical runner display names. The old criterion can therefore produce `INVALID` without any observed scientific defect. No E1 measurements were accessed to formulate this change.

## Normative v3 delta — one provenance class only

1. Remove the *cross-repeat inequality* `runner_name_A != runner_name_B` from the v3 evaluator.
2. Continue to require a nonempty runner-name field in every run as informative evidence.
3. Continue to require distinct GitHub run IDs, exact implementation SHA, run attempt=1, `workflow_dispatch`, `main`, independently materialized store, GitHub-hosted `ubuntu-24.04`, exact run and artifact identity, SHA-256 provenance, identical 9-target/106-pair/115-measurement quality, Rust/Python parity, reconstruction and all frozen cost/performance thresholds.
4. Preserve v2 `index_budget_ok` handling of over-limit valid numeric index cost as `G5_REJECT_K2`; invalid cost stays `INVALID`.
5. Preserve frozen S4-C v1 authority, v2 versioned authority, K=2, all 7 paired rounds, thresholds, data split, pinned ChunkShift SHA, no rerun/replacement, and final verdict enum.

Evaluator candidate: `.work/tools/selector_s4_confirmation_v3.py` (direct copy of v2; only introductory provenance comment and the single uniqueness check differ). Synthetic-only regression: `.work/tests/test_selector_s4_confirmation_v3.py`.

## Ordered merge / scientific integrity gate

1. Independently diff v3 versus v2: only runner-name inequality removal and comment changes are allowed. Test distinct run IDs with equal display names (valid v3, INVALID v2); equal run IDs (INVALID under v3); missing runner name (INVALID); unequal names (same decision v2/v3); all scientific constants unchanged.
2. Both hosted CI checks must pass. Confirm the sealed E1 has **never** been materialized for S4-C. If prior first attempt was observed, cancel this amendment — do not retrospectively rescue data.
3. Merge this **protocol-only** PR first. Record its exact merged main SHA as v3 frozen authority in #63/#57.
4. Rebind PR #57's autostart parent, repeat A/B plan producer, independent evaluator, runner pin and tests to the exact new authority, then review and rerun hosted CI. Do not merge PR #60 first.
5. **Only after** independent review may PR #57 be squash-merged, enabling the irrevocable A → B → evaluator chain. No manual dispatch or reruns.

If no further valid pre-measure correction is necessary, this v3 is final for S4-C. A failure after the first attempt is retained as historical evidence; no in-place protocol change or replacement attempt is allowed.
