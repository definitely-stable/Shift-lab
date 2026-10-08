# S4-C: sealed holdout confirmation for `delsk.simple-selector.v1`

Status: **PREREGISTRATION / NOT_RUN**.  
Owner: [DELSK-012](https://github.com/definitely-stable/Shift-lab/issues/13).  
Precondition: S4-D = `OPEN_CONFIRMATION_K2` ([retained result](../results/SELECTOR-S4/README.md)).  
Selector candidate: **K = 2 only**.  
Consumer: `definitely-stable/ChunkShift@74bb301b6d8ecc52cf0bc0e00d86fa174093d91b`.

S4-C is the first held-out system confirmation. It asks:

> Does the already-frozen K=2 selector retain a meaningful physical-patch advantage over the cheap `previous1` policy on data that was sealed before the selector and never used by S2/S3/S4-D, while keeping the extra build cost bounded?

A PASS closes G5 only for the explicitly tested **scoped ChunkShift heuristic**. It does not by itself justify a universal/standalone Delsk library.

## 1. Information boundary

The confirmation population is fixed to the already-sealed E1 **evaluation** split. It was selected before Delsk scoring and was not opened by S4-D.

Bound authority:

- E1 candidate seal: `.work/corpus/e1/seal.json`;
- candidate lock SHA-256: `cb16d53b164ff393187e0115bdf31c52ac717a5172fb1e91889b5988ac019d2e`;
- coverage SHA-256: `fff71554f28fea2b1628ac9f430e4d542f0147e30bcdc43e64887265f6cade5c`;
- corpus lock SHA-256: `e5c288256bed284572a9f111186411517b4c73d097d13aea4cf48e2fb9f6fffa`.

Known metadata before confirmation:

- family/component: **bzip2** only;
- selected near targets: **9**;
- frozen base pairs: **106**;
- no file-track targets;
- non-empty modeled tracks: chunk-4k, chunk-8k, chunk-16k, chunk-32k, tar, tar-gz.

These structural facts are not utility results. No delta score, ChunkShift patch byte count, MinHash resemblance result or confirmation selector output from the evaluation split may be inspected before this protocol is merged.

The evaluation split is a true pre-existing holdout relative to Delsk v1/S4-D, but it is only one family. Therefore even a PASS remains scoped; standalone-library claims require a later multi-family cohort frozen independently of this result.

## 2. Frozen selector and controls

No model selection occurs in S4-C.

### Delsk lane

Exactly `delsk.simple-selector.v1` with:

- 64-byte descriptor = eight smallest distinct splitmix64-mixed 8-byte shingles;
- seed `20261006`;
- metadata order unchanged;
- content order unchanged;
- interleave unchanged;
- **K = 2**;
- abstention disabled, `L = 0`.

K=4 is not evaluated as a decision candidate. It was already rejected by the S4-D smallest-eligible-K rule.

The authoritative confirmation selector is the Rust implementation in `.work/selector/rust`. Python remains a semantic oracle only. Before any ChunkShift encoding, Rust and Python must select byte-for-byte identical ordered K=2 object IDs for all 9 targets. Parity failure makes the confirmation `INVALID`; it may not be repaired after patch bytes are observed.

### Controls

- `previous1`: the frozen strong metadata policy already used by S4-D;
- `size1`: retained as a diagnostic control only;
- `exhaustive`: every base in frozen `C_t`, used only to compute system oracle/SavingsCapture.

The final G5 quality comparison is **K2 vs previous1**. `size1` and exhaustive cannot replace `previous1` after results are seen.

## 3. ChunkShift lane

Use exactly the same consumer lane as S4-D:

- ChunkShift commit `74bb301b6d8ecc52cf0bc0e00d86fa174093d91b`;
- Release / net10.0 / consumer `global.json`;
- whole object bytes unchanged;
- BLAKE3 manifests, no BIDX;
- ordinary public `chunkshift patch create/apply`;
- production `CspEncoderPolicy.Default`;
- no `ICspResearchCandidateSelector`;
- CSP v1 unchanged.

Keeping the consumer fixed isolates selector generalization. Updating ChunkShift is a different experiment.

## 4. Confirmation execution

Confirmation consists of **two separately allocated GitHub-hosted runs**, `A` and `B`.

Both runs:

1. are `workflow_dispatch`, attempt 1, on the same exact merged confirmation implementation SHA;
2. use standard GitHub-hosted `ubuntu-24.04`;
3. independently rematerialize the sealed evaluation bytes;
4. independently build the Rust selector and pinned ChunkShift;
5. independently produce the full 9-target / 106-pair quality table;
6. produce identical target/base identities, Rust K2 selections, physical CSP bytes and final reconstructed SHA-256 values.

The two runs must have different GitHub run IDs and different runner names. Equal image versions are allowed.

Runs A and B are one-shot authoritative dispatches. **No rerun and no replacement dispatch is admissible**, including for pre-measure infrastructure failure. Any failure/cancellation/admission failure in A or B makes S4-C `INVALID` under this protocol. A later attempt requires a new versioned confirmation slice that retains the failed run instead of silently replacing it.

## 5. Quality measurements

For every target:

- create one self-contained CSP;
- create one CSP for every base in frozen `C_t`;
- apply and SHA-256 verify every created CSP;
- derive `previous1`, `size1`, `delsk2` and exhaustive from the same pair table.

The same equations as S4-D define physical patch bytes and SavingsCapture.

The confirmation quality table must be byte-identical between runs A and B.

## 6. Real Rust selector cost

S4-D's Python construction timing was descriptive only. S4-C measures the actual Rust selector path.

Before patch timing, retain:

- unique object count and bytes scanned;
- descriptor build wall/CPU;
- Rust catalog build wall/CPU;
- descriptor bytes;
- `Catalog::index_bytes`;
- K2 query latency for all 9 targets;
- exact Rust/Python selected-ID parity.

Guardrails:

- descriptor representation remains exactly **64 bytes/object**;
- `Catalog::index_bytes <= 64 bytes/object`;
- descriptor throughput must be at least **250 MiB/s** in each run;
- K2 query p95 must be at most **50 µs** in each run.

These are conservative regressions bounds relative to S2, not tuned from evaluation payload results.

## 7. Paired system timing

Quality creates are not treated as a timing experiment.

After the quality table is complete, each run executes **7 paired performance rounds** over all 9 targets:

- `previous1` and `delsk2` use the already-built manifests;
- each lane creates exactly the patches it would normally try: one self-contained create plus its selected base creates;
- the order alternates by round: P→D, D→P, P→D, D→P, P→D, D→P, P→D;
- output files are removed between lanes/rounds;
- no exhaustive pairs run inside timing rounds;
- Rust catalog is built before warm rounds and reused within the run.

Retain per-round wall and child CPU for:

- selector query;
- patch creates;
- final chosen-patch apply.

Also retain one cold Rust descriptor+catalog build measurement.

Decision timing quantities are the medians of the seven paired round ratios:

`R_wall = median(Delsk K2 patch-create wall / previous1 patch-create wall)`

`R_cpu = median(Delsk K2 patch-create CPU / previous1 patch-create CPU)`

`R_apply = median(Delsk chosen-patch apply wall / previous1 chosen-patch apply wall)`

Cold selector construction is reported separately and must not be hidden inside an assumed amortization count.

## 8. Frozen G5 decision

Each run A and B must independently satisfy all gates. The final evaluator does not pool a passing run with a failing run.

### Correctness / identity

1. all planned measurements are present exactly once;
2. every created patch reconstructs the exact target;
3. A and B have byte-identical quality tables and K2 selections;
4. Rust/Python selector parity is exact.

### Quality

Let `B_P` be aggregate `previous1` physical CSP bytes and `B_D` K2 bytes.

5. `SavingsCapture_K2 >= 0.98`;
6. `B_D <= 0.995 * B_P` — at least **0.5%** aggregate physical-byte improvement over `previous1`.

The 0.5% threshold was frozen before evaluation results and is the same meaningful-system-signal floor used to open confirmation from S4-D.

### Cost

7. K2 create-call count may not exceed **1.5×** `previous1`;
8. paired median `R_wall <= 1.80`;
9. paired median `R_cpu <= 1.80`;
10. paired median `R_apply <= 1.10`;
11. Rust selector guardrails in §6 all pass.

Possible verdicts:

- `G5_SCOPED_PASS_K2` — both A and B satisfy every gate;
- `G5_REJECT_K2` — evidence is valid but at least one run fails a quality/cost gate;
- `INVALID` — evidence/provenance/correctness/parity/repeat requirements fail.

There is no threshold tuning, K tuning or fallback to K4 after the evaluation split is opened.

## 9. Interpretation after the verdict

### If `G5_SCOPED_PASS_K2`

DELSK-012 may close with a scoped positive result:

> On the frozen tested ChunkShift consumer and the preregistered bzip2 modeled holdout, K=2 preserves the byte benefit with bounded extra build cost.

This opens DELSK-013 go/pivot/stop. It does **not** by itself authorize:

- a universal standalone Delsk crate/package;
- a ChunkShift production default change;
- public API/wire-format changes;
- claims for arbitrary binaries, model weights, or unseen families.

A standalone-library claim requires a later, separately frozen multi-family cohort.

### If `G5_REJECT_K2`

The default recommendation is to stop the standalone Delsk line and retain the selector only as exploratory/consumer-specific evidence. No rescue experiment with K4 or new thresholds is allowed on this holdout.

### If `INVALID`

Fix only the evidence/implementation defect that caused invalidity. If that fix can affect selection, timing, patch bytes or the measurement boundary, create a new versioned confirmation protocol before any rerun.
