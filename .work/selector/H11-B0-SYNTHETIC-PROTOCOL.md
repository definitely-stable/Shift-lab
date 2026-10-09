# H11-B0 — certified index synthetic smoke and measurement-contract foundation

Tracks issue #58. Status: **SYNTHETIC CI SMOKE / NOT H11-B SCIENTIFIC DECISION**.
Frozen S4-C original E1 is ALREADY OPENED, and its retained measurements MUST NOT be reused as independent H11-B holdout.
Existing H11-A exactness code was merged in commit c4ffb121d2098d2c9b9ea49e051c890e9f565479.

## Source population and correctness

One deterministic Rust synthetic catalog generator with nested path/version families, popular full hash postings,
deliberate same-upper-32-bit fingerprint collisions, path-less data, and one unseen zero-overlap target.
All descriptors are canonical; no external data access and no ChunkShift encoder calls.
Cover three caps {2, 32, unlimited} and K {1, 2, 4}; for every target compare exact ordered IDs
from select_exact to select_indexed_certified and abort on ANY difference.
An approximate indexed comparator is measured only descriptively, not claimed exact.
Count IndexedExact, ExactFallbackSparse, ExactFallbackCapped, ExactFallbackInvalidInput
and approximate-index mismatches. Certification class counts must sum to query count.

## Descriptive-only cost-accounting dimensions

- Deterministic descriptor construction wall and Catalog::new build wall tracked separately.
- Query p50/p95/p99 wall microseconds by lane from a single pass; alternating lane order per query.
- Logical packed index bytes, process VmRSS after building, and process VmHWM after benchmark.
- VmHWM is process lifetime high-water, NOT incremental index-only memory.
- Descriptor allocation, target clones and resident object state are present and may affect RSS.
- No statistical uncertainty or economic speedup claim from this tiny synthetic smoke.
- JSON result schema: delsk.h11b0.synthetic-smoke.v1.
- All emitted verdict scopes are SYNTHETIC_ONLY_NOT_DECISION_EVIDENCE.

## Hosted smoke

PR selector parity CI runs cargo test --release --locked including H11-B0 binary
and a bounded cargo run --release --locked --bin delsk-h11b0 -- 256 8.
Smoke verifies JSON schema, nine cap/K cases, and exact certification/fallback count sums.
GitHub-hosted only; no experimental workflow_dispatch and no S4-C reruns.

## Future H11-B1: frozen independent experiment required

Before natural/economic measures, independently pin new multi-family corpus and source hashes,
complete target manifests, sample sizes and exclusion rules, K/cap grid, N=10^4/10^5/10^6
where admitted; separate poison/popular/zero-overlap strata; repeat count and rotation;
query p50/p95/p99, child CPU, cold/warm catalog, actual RSS accounting and amortization;
missing data policy and provider run/attempt identities; independent evaluator and thresholds.
Allowed outcomes only after such preregistration: INDEXED_EXACT_FAST,
CORRECT_BUT_NOT_ECONOMIC or INVALID. Failure of completeness/provenance is INVALID.
Do not infer standalone library demand or ChunkShift production-default benefit from H11-B0.
