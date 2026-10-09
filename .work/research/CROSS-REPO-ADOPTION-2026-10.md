# DELSK cross-repository critical adoption audit — 2026-10-08

**Status:** DECISION DESIGN / no new S4-C science claim. **Implementation:** H11 Slice A in the accompanying draft branch; no hosted acceptance until CI confirms it.
**Authority:** Existing DELSK-P1, S4-D retained evidence and S4-C frozen confirmation remain authoritative. This document cannot alter their thresholds, K, input files, or two-run procedure.

Pinned repository sources (read 2026-10-08):

- DELSK Shift-lab main: https://github.com/definitely-stable/Shift-lab/tree/e1ee235fe08c7cc1f6e8ec8884b65439435adf92
- DeltaMeter main: https://github.com/definitely-stable/deltameter/tree/862579643fb44bfd3df3b65a863bfdc90b998611
- Mathlab main: https://github.com/definitely-stable/Mathlab/tree/94a8fb621ec638841c7112f7b8317b1539dedcf8
- Curated, pinned thematic catalog: https://github.com/definitely-stable/Mathlab/blob/94a8fb621ec638841c7112f7b8317b1539dedcf8/docs/research/catalog/INDEX.md

## Product boundary

DELSK solves codec-conditioned reference/base selection: find a few candidate bases for target t, create physical CSP candidates through pinned ChunkShift, compare with self-contained patch, verify reconstruction. It does NOT recover A symmetric-difference B as an end in itself, nor certify patch byte length from a cardinality sketch.

The S4-D DEVELOPMENT-only record (3,815 quality rows, zero failures) reports:
- previous1 physical bytes 20,750,611, create calls 238, wall 291.976 s, CPU 562.153 s;
- K2 physical bytes 20,531,317, calls 355, wall 488.530 s, CPU 948.294 s;
- saved 219,294 B (1.0568%); additional 117 calls, ~196.55 s wall and ~386.14 s CPU;
- K2 SavingsCapture 0.999924, only 1,913 B worse than exhaustive on DEVELOPMENT.
Evidence: ../results/SELECTOR-S4/retained-summary.json. None is a fresh bzip2 evaluation result.

S2 16.7 us p95 and ~40.7 logical index B/object were on a synthetic million-object catalog; its actual process RSS was ~419 MB, and top2 exact-index parity=1.0 is empirical only. S3 tested 119 natural targets and found five useful tar-gz targets with zero shared hashes, rejecting positive abstention thresholds. No global index completeness claim follows.

## Critical point-by-point transfer matrix (24 entries)

| ID | Research item / observed issue | Applicability and falsifier | Decision / gate |
| --- | --- | --- | --- |
| DL-01 | Indexed retrieval can omit all zero-overlap candidates and truncate relevant postings | Prove exact indexed top-K or take full-scan fallback. Counterexamples without path and with capped popular hashes | ADOPT H11-A; no v1 default change |
| DL-02 | S4-D K2 saved bytes but increased encoder calls ~1.49x and wall ~1.67x | Amortize cost over actual downloads; report CPU, wall, network, storage separately; no invented common unit | ADOPT H12 protocol, not a production victory |
| DL-03 | 40.7 B/object logical index vs 419 MB RSS at 1M | Track real allocations, IDs, metadata, peak RSS and serialization; capacity model must charge all bytes | H14 later, after H11-A |
| DL-04 | S4-C sealed bzip2 9 targets / 106 pairs, K2, two first-attempt independent runs | Draft PR #57 currently has failing research-docs CI; no read of sealed outcome or change in frozen gate | BLOCK: finish S4-C before H11/H12 decision runs |
| DM-01 | M6-D13B STOP_SYSTEM_PRODUCT: 3900 observations, 360 modeled cells, 0 qualifying non-direct cases | Sketch arithmetic savings do not imply full-system savings when exact verification still retransmits list | ADOPT full cost accounting, H12 |
| DM-02 | Strict Compact 32 KiB parity state + 16 KiB static lookup with ideal model theorem | 512x per-object state vs 64B descriptor; symmetric-difference cardinality does not upper-bound codec bytes | REJECT direct transplant; ADOPT clear guarantee vocabulary |
| DM-03 | One-sided finite-sample bounds use ideal independent randomness / explicit keyed oracle model | MinHash resemblance cannot certify physical CSP-byte improvement; require codec-specific theorem or mark estimated | RESEARCH only; no unearned guaranteed patch size |
| DM-04 | D11 45.9–66.1% d=8 decoder gain after isolated fixed reduction; D12 stopped remaining micro-optimization | Profile actual descriptor/query/encode/fetch costs; only optimize stable material phase | ADOPT profiler-first, no speculative SIMD/crypto swap |
| DM-05 | Maintained state occasionally helps native compute but loses modeled end-to-end | Bottom-8 cannot support arbitrary deletes with only eight minima; charge reservoir/invalidation/rebuild | H16 exploratory |
| DM-06 | Keyed BLAKE3 made computational oracle contract explicit | Fixed SplitMix64 is non-secret. Security threat distinct from naturally heavy postings. Hash change modifies descriptor compatibility | H18 later; DO NOT change v1 mixer |
| ML-01 | LENT sparse additive-state Hamming-ball bound | Requires exact injectivity for all sets <=d; DELSK approximate ranking has another model | ADOPT modeling discipline, REJECT direct lower-bound claim |
| ML-02 | HYP-001 odd-q two-cell ASET Theta_q(m^1.5) from C4-free graph incidence | Mathematical finite-field active-ID recovery, not codec reference selection; novelty not established | PARK in Mathlab |
| ML-03 | HYP-002 odd-q three-cell lower Omega(m^2) / upper O_q(m^2.5) | Quadratic sharp exponent remains CONJECTURE; q=5 finite result is interval 10..15, not exact | PARK in Mathlab |
| ML-04 | TOM O01 no-effect certificates | A cached unchanged descriptor does not by itself prove unchanged best-base selection; charge metadata, probes and false-reuse risk | H16 exact cache-reuse target |
| ML-05 | TOM O02 independent no-effect claims may not compose | Exact AND counterexample: two individually no-effect edits change aggregate; repeat or joint-verify against combined state | ADOPT batch/regression contract |
| ML-06 | O04/O06 history independence/canonical rope | Canonical serialized catalog is useful; physically history-independent Rust heap not required | H14 canonical serialization, no novelty claim |
| ML-07 | O05 Chonkers, periodic/edit-stable boundaries | CDC anchors may help hard file families and incremental update, but may be redundant with cheap metadata and sliding shingles | H17 independent ablation; primary source: https://arxiv.org/abs/2509.11121 |
| ML-08 | O07 multi-scale synchronizing sets | Static construction theorem != dynamic maintenance theorem; budget and codec-utility must be tested | H17 after hard-case signal; source: https://doi.org/10.4230/LIPIcs.STACS.2026.36 |
| ML-09 | O09/O14 compact ordered dictionaries | Compare packed ids, sorted postings, varints/Elias-Fano/bitmaps against real RSS and p95; broad theoretical novelty is known prior art | H14 engineering Pareto |
| ML-10 | O12 dynamic threshold edit distance | Too costly as general first-stage binary similarity; investigate restricted small windows only if evidence | PARK |
| ML-11 | O13 retained Merkle multiproofs | Orthogonal to codec ranking; relevant only if a verifiable distributed catalog product emerges | PARK |
| SYS-01 | Baseline-preserving selection inequality | Trial exact baseline and additional options, take minimum physical bytes. Result <= baseline bytes, but compute > baseline | H13 as new experiment, NOT frozen S4-C |
| SYS-02 | No exact top-K guarantee with truncated postings | Finite counterexample. Absence of shared hashes may still yield valid useful base | H11 contract and property tests |
| SYS-03 | Dynamic bottom-k deletion requires more than retained k minima | Two sets same first k but different (k+1)th yield distinct correct state on deletion | H16 memory/rebuild trade-off |

DeltaMeter anchors:
- https://github.com/definitely-stable/deltameter/blob/862579643fb44bfd3df3b65a863bfdc90b998611/docs/M6-D13B-SYSTEM-EVIDENCE.md
- https://github.com/definitely-stable/deltameter/blob/862579643fb44bfd3df3b65a863bfdc90b998611/docs/research/STRICT-COMPACT-002-EVIDENCE.md
- https://github.com/definitely-stable/deltameter/blob/862579643fb44bfd3df3b65a863bfdc90b998611/docs/M6-D11-FIXED-REDUCTION-EVIDENCE.md
- https://github.com/definitely-stable/deltameter/blob/862579643fb44bfd3df3b65a863bfdc90b998611/docs/M6-D12-POST-D11-PROFILE-EVIDENCE.md
Mathlab anchors:
- https://github.com/definitely-stable/Mathlab/blob/94a8fb621ec638841c7112f7b8317b1539dedcf8/docs/research/HYP-001-002-LOCALITY-TRANSITION.md
- https://github.com/definitely-stable/Mathlab/blob/94a8fb621ec638841c7112f7b8317b1539dedcf8/docs/research/LENT-001-G2B-A-EVIDENCE.md
- https://github.com/definitely-stable/Mathlab/blob/94a8fb621ec638841c7112f7b8317b1539dedcf8/docs/research/TOM-001-B-PRIOR-ART-AUDIT.md
- https://github.com/definitely-stable/Mathlab/blob/94a8fb621ec638841c7112f7b8317b1539dedcf8/docs/research/TOM-001-OPPORTUNITY-MAP.md

## Useful elementary claims (not scientific novelty)

**A — baseline dominance under tested alternatives.** For fixed physical codec/target, P=previous1 and candidate bases b1..bk, min(S,P,b1..bk) <= min(S,P). Proof: the minimized set contains the baseline set. It does NOT bound compute cost or make a useful estimate without encoding.

**B — positive-overlap completeness sufficient condition.** If no query posting is truncated, all metadata matches are indexed, and >=K distinct non-target bases share >=1 descriptor hash with the target, then indexed select_top(K) equals a full select_top(K). Every unseen base has score zero and cannot precede any positive-overlap base in the content order. All metadata candidates remain available, and the final interleave uses only the first K of each ordering. Conservative fallback if any premise fails.

**C — exact dynamic deletion obstruction.** Store only k minimum distinct elements of an arbitrary feature set. Two sets can share these k minima but have different (k+1)th. Deleting their common smallest leaves different correct k-minimum states, so no update operator on just the stored k values can be correct for both. This does not prohibit maintaining a larger reservoir/source index.

## Promotion rules

1. Frozen S4-C first: PR #57 completion is an independent release gate, with no new threshold, new holdout inspection, new K or repaired-after-observation reattempt.
2. H11-A is a research implementation with deterministic exact-oracle tests; no quality/performance decision until a separate preregistered H11-B CI run.
3. H12 first freezes operational costs and environments, then runs matched scenarios; do not infer client economics from a constant Mbps assumption alone.
4. H13–H18 remain candidate questions. No production/public API, on-disk format, ChunkShift default or guaranteed-byte claim is authorized.
5. Failures and null results must be retained; numerical claims require GitHub-hosted exact source/artifact binding. New heldout families must be independent of revealed earlier evaluation.
