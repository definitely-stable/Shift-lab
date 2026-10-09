# H12 — Full-system ROI protocol draft (NOT FROZEN)

Issue: https://github.com/definitely-stable/Shift-lab/issues/59
Status: DESIGN ONLY / NO NEW MEASUREMENTS / NO PRODUCTION CLAIM.
Depends on S4-C first-attempt confirmation closure; then a separate, independently preregistered cohort.
Rationale: ../results/SELECTOR-S4/retained-summary.json and DeltaMeter M6-D13B STOP_SYSTEM_PRODUCT:
https://github.com/definitely-stable/deltameter/blob/862579643fb44bfd3df3b65a863bfdc90b998611/docs/M6-D13B-SYSTEM-EVIDENCE.md

## Decision

When does the reduction in physical CSP bytes from Delsk K2 compensate for extra encoder CPU, wall/critical-path, index lifecycle and memory, in concrete consumer economics? The result must be conditioned on workload/deployment; a single speedup factor or raw SavingsCapture is insufficient.

S4-D development-only observations are baseline input, not evidence of heldout generalization:
- previous1: 20,750,611 B, 238 encode calls, 291.9758 wall s, 562.1529 CPU s;
- K2: 20,531,317 B, 355 calls, 488.5301 wall s, 948.2944 CPU s;
- marginal saved bytes 219,294, marginal wall ~196.55 s, marginal CPU ~386.14 s.

NOTE: the 20 MB aggregate is over a fixed DEVELOPMENT population, not one realistic downloadable file. Do not use its 219 kB delta as the hypothetical byte saving *per client* unless that exact population is delivered per client.

## Operational quantities and units

For release/workload W and policy p separately report:
- B_patch(p) physical CSP bytes actually retained and transmitted per selected target;
- B_trials(p) temporary bytes written/read during abandoned trials;
- T_cpu(p) native child/process CPU seconds including fallbacks, hashes, builds and checks;
- T_wall(p) measured critical-path wall seconds (not simply sum of thread wall clocks);
- B_catalog(p) resident and persisted index/descriptor bytes, peak RSS, setup I/O;
- N_download(t) actual or modeled number of target deliveries, cache hit ratio and link speed distribution;
- T_apply(p), exact reconstruction/hash integrity, failures and all trial attempts.

For a specified price model (prices are input assumptions, not facts):
C(p) = r_cpu*T_cpu(p) + r_net*sum_t(N_download(t)*B_patch(t,p)) + r_storage*B_catalog(p) + r_wall*T_wall_critical(p).
Avoid charging the same hardware time twice: if CPU dollars already include wall capacity, make r_wall an explicitly distinct latency penalty or set it to zero.

Break-even threshold in a simplified uniform-delivery model:
N >= (r_cpu*Delta_CPU + r_wall*Delta_Wall + r_storage*Delta_Storage) / (r_net*Delta_Bytes_per_delivery)
for positive Delta_Bytes_per_delivery and positive per-byte network rate. This formula is meaningless if codec-produced patches are not the same artifact per client, source state differs, or downloads are not repeated; then use per-target accounting.

## Pre-registered scenarios (proposal)

1. Individual updater: one client per patch, cold descriptor/catalog, latency-sensitive.
2. Enterprise fleet: repeated target deliveries, warm catalog, mixed cache-hit/fanout.
3. Mass distribution: long-lived release artifact and many installations, encode CPU amortized; egress/storage prices separate from wall release deadline.

For each: explicitly vary targets, patch sizes, network pricing, fanout, cold/warm, parallelism, CPU pricing and update frequency. Do not assert one price or bandwidth applies globally. Report dominance regions and sensitivity rather than a single universal winner.

## Policies and controls

- previous1 cheap metadata baseline is primary;
- size1 diagnostic only;
- frozen Delsk K2 and K4 exploratory;
- baseline-preserving K2 (primary baseline + one selected alternative) a new policy requiring own preregistration;
- exhaustive only a small finite oracle, not a deployable competitor.

All run on the same frozen ChunkShift commit/options and identical target/base universe; verify every produced artifact by apply and exact target hash. Results under different codecs cannot be pooled without fixed stratification.

## Measurement plan and quality gates (to freeze BEFORE H12-B)

- Prior-art, population, candidate manifests, all metric formulas and run order fixed on an immutable protocol SHA.
- Stage 0: deterministic accounting/oracle tests; malformed/failed jobs counted, no missing cost fields.
- Stage 1: bounded CI dry-run with no decision; freeze measurement source and artifact schema.
- Stage 2: multiple separately allocated GitHub-hosted paired workers, rotated control/candidate order, temperature/image/CPU descriptors, strict completeness.
- Stage 3: independent aggregation from retained raw rows, no post-hoc sample removal.
- Publish Pareto fronts for bytes/CPU/wall/RSS, per-family and weighted deployment cost. A policy wins only within a declared scenario and threshold, not just because savings capture is high.

Potential outcomes: SCOPED_ROI_PASS, SCOPED_ROI_REJECT, INCONCLUSIVE, INVALID. Draft thresholds must be independently preregistered, never chosen after evaluation.

## Restrictions

Do not modify current S4-C K2, its 0.5% physical bytes gate, 1.5x calls gate, 1.8x wall/CPU gates, 7 rounds, bzip2 evaluation split or two-attempt rule. Never fold H12 economics into the S4-C verdict retrospectively. GitHub-hosted CI only; no self-hosted runners or new dependencies justified solely by the protocol.
