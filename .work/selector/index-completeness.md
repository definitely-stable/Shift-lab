# H11 — Certified indexed retrieval: correctness-first foundation

Issue: https://github.com/definitely-stable/Shift-lab/issues/58
Status: SLICE A CODE CANDIDATE WITH IMMUTABLE-SNAPSHOT GUARD / NOT A MEASURED PRODUCT VERDICT.
Scope: research-only Rust API; frozen S4-C PR #57 is now merged, with first-attempt A/B and evaluator all successful and G5_SCOPED_PASS_K2 scoped verdict. The frozen holdout is already open and cannot be treated as a new confirmation.
Reference: ./README.md and ./results-s2.md, ./results-s3.md.

## Failure model of current approximate index

Catalog::select_indexed starts with (1) all matching path+line objects and (2) union of postings for target descriptor hashes, each list truncated to a fixed cap. It does not include other objects.

1. Zero-overlap target without path: no candidates are returned; select_exact still chooses bases by zero resemblance, size and id. S3 demonstrates useful compressed-archive delta candidates with zero shared hashes, so this is relevant to quality, not necessarily rare.
2. A popular hash can have a long posting list, cap truncates it, and a base with highest exact rank can be excluded even though query has retrieved other matches.
3. S2 full/index top-2 equality (1.000) was synthetic; it is not a universal exactness theorem.

These are candidate-search losses; standalone fallback preserves output correctness but does NOT preserve byte optimality.

## Safety proof for the first opt-in implementation

Assume K > 0 and:
- every target hash posting list was read in full (capped_postings == 0);
- all matching path+line metadata candidates are included;
- at least K DISTINCT non-target retrieved objects share >=1 target hash.

Every base outside the retrieved set then has zero descriptor intersection and therefore zero positive resemblance. The K-th positive-resemblance candidate strictly precedes any omitted zero-resemblance candidate in full content order, regardless of size/id tie breaks. The first K entries of full content order are present in the retrieved set; every metadata candidate is also present. Since the final selection is the duplicate-removing interleave of these two orders, indexed top K equals exact top K.

When K = 0, empty result is exact by definition. If ANY premise is missing, do not claim that a short list implies exactness: perform full catalog scan and return its ordered top K.

This is intentionally SUFFICIENT, not necessary. For K=1 with a deterministic path winner, a more permissive proof is possible but must be separately reviewed.

## API semantics (research prototype, no public freeze)

- Existing select_indexed: unchanged approximate behavior; QueryStats now additionally records positive_candidates (a counter, not a proof).
- Catalog::objects() exposes only &[Object] (read-only immutable snapshot); field Catalog.objects is private. To change objects, build a new Catalog and its index atomically in caller-owned state.
- Catalog::new disables indexed certification (but keeps exact scanning and legacy approximate retrieval available) when duplicate IDs or noncanonical descriptors are found. Target descriptors are likewise validated before certification. Independently, the existing S4-C packed-index constructor rejects catalogs exceeding u32::MAX objects with an assertion; it does **not** return an exact fallback in that allocation-limit case.
- New select_indexed_certified(t, k) -> CertifiedSelection:
  - IndexedExact: proof premises hold, selected ids come from indexed subset.
  - ExactFallbackCapped: at least one truncated posting, full select_exact run.
  - ExactFallbackSparse: too few unique positive-overlap candidates, full select_exact run.
  - ExactFallbackInvalidInput: mutable/index consistency cannot be proven due to malformed snapshot/target input; full select_exact run.
- No descriptor/hash/metadata/interleave/K or wire contract changes.
- This is correctness of exact ORDERED top K versus select_exact. It does NOT imply that selected K are actual smallest-physical-patch K, or that the selection has speedup over exact scanning.
- Catalog loading and external signature/version pin remain out of scope. A catalog can no longer mutate its indexed objects through safe Rust accessors. Object ID uniqueness and sorted/distinct descriptor shape (up to 8 entries) are checked before certifying; invalid inputs fall back to full exact scan. Cross-thread state changes must publish a new, fully built Catalog snapshot instead of modifying existing postings.
- This shape guard does not attempt to prove external object bytes match claimed hashes. A separate authenticated content-provenance layer is still needed if inputs are adversarial.

## Independent tests

Add tests/certified_retrieval.rs, run by hosted cargo test --release --locked:
- zero-overlap + absent path returns empty under approximate index and non-empty exact result under certified path;
- metadata-only candidate does not falsely count as positive resemblance;
- uncapped and >=K positive candidates takes IndexedExact and matches exact sequence;
- deliberately capped shared hash with better omitted candidate forces exact fallback;
- K=0, empty/short/repetitive content; multiple K/cap, repeated deterministic adversarial fixture matrix.

Negative/falsification conditions:
- any IndexedExact result unequal to select_exact: INVALID;
- any fallback result unequal to select_exact: INVALID;
- tests using only generated random data do NOT prove all input correctness; rely on explicit proof premises for claim;
- any change to frozen S4-C runner/selector semantics: INVALID scope.

## Next independent measured slice H11-B (NOT RUN)

Preregister on fresh natural catalogs and adversarially saturated postings:
- exactness over all queries (must remain 1.0);
- IndexedExact share, ExactFallbackCapped share, ExactFallbackSparse share;
- query p50/p95/p99, candidate count, cap hit distribution;
- total RSS including strings/metadata/object state/allocator, not just logical postings bytes;
- cold index construction, rebuild, and one-million-object scaling.

Compare approximate indexed, certified indexed, exact scanning, and size/path fallback proposals at same catalog/source commit. An empty or mostly fallback result is a valid CORRECT_BUT_NOT_ECONOMIC verdict. New evidence must not use opened E1 as a fresh holdout.

## Deferred correctness/engineering risks

- PR #60 research fix: replace signed unary negation by `Reverse(i64)` in both metadata orderings, preserving all existing bounded-input ordering while handling `i64::MIN`; adversarial test covers `i64::MIN/0/i64::MAX`. Object ID uniqueness and catalog input validation still require independent production hardening. This does not affect frozen bounded version-rank corpus.
- current clone-heavy string metadata and logical index_bytes() underestimate resident memory.
- concurrent catalog mutation is not modeled; snapshot generation and atomic index swap need a separate slice.
- hash-poisoning and deterministic seed choice need a threat model, not just a swap to keyed BLAKE3.
