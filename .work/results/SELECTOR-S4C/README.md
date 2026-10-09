# DELSK-012 / S4-C — sealed first-attempt confirmation (retained)

Status: **G5_SCOPED_PASS_K2** (frozen, scoped positive; not a standalone crate or a ChunkShift production default).
Closed on 2026-10-08. All source evidence is retained here, including the three **original unmodified ZIP artifacts** under `source/`, complete raw A/B JSON/JSONL, original evaluator JSON, and independent frozen-v3 replay. There was **no holdout rerun**.

## Evidence and provenance

- Frozen protocol v3: `9ec28a0022651bb7416871089b0bcc4edd3454b8`.
- S4-C implementation SHA: `e002276e6820f2b2f2544a894d3de5c59da0d073`.
- Pinned consumer: `definitely-stable/ChunkShift@74bb301b6d8ecc52cf0bc0e00d86fa174093d91b`.
- Sealed bzip2 E1 modeled cohort: **9 target objects, 106 target/base comparisons and 115 complete quality rows** in each repeat; K=2; 7 paired timing rounds.
- Provider repeat A: [run 37804898028 / attempt 1](https://github.com/definitely-stable/Shift-lab/actions/runs/37804898028), artifact ID 11562547245, original ZIP SHA-256 `9b289cc785d2cbb14d0db9ec593aca431f743dd54db83c32455cb978ead24167`.
- Provider repeat B: [run 37805606542 / attempt 1](https://github.com/definitely-stable/Shift-lab/actions/runs/37805606542), artifact ID 11562722944, original ZIP SHA-256 `a5937bc8b488392c62a1f031ed3fcf6c8a94581572407a5a04259b817d5996b3`.
- Original evaluator: [run 37806374272 / attempt 1](https://github.com/definitely-stable/Shift-lab/actions/runs/37806374272), artifact ID 11563067146, original ZIP SHA-256 `30677da6695d84cb889fc4440885420c4452e414b3c3860d554fa72326c332b2`.
- `retained-manifest.json` binds all original ZIP digests, extracted file digests and immutable run identities. `independent-evaluation.json` is a separate replay using the existing frozen v3 evaluator, **not new CSP measurements**.

## Physical CSP quality

| Policy | Physical CSP bytes (9 targets) | SavingsCapture | Patch create calls |
| --- | ---: | ---: | ---: |
| previous1 | 109,199 | 0.975276 | 18 |
| size1 | 120,852 | 0.826461 | 18 |
| **Delsk K2** | **107,263** | **1.000000** | **26** |
| exhaustive oracle | 107,263 | 1.000000 | 115 |

Relative to previous1: K2 saves **1,936 physical bytes (1.773%)**, at 26/18 = **1.444×** create calls. The exhaustive oracle is a diagnostic reference, not a deployable competitor.

## Timing and index cost (independent repeat A / B)

| Quantity | A | B | Frozen gate |
| --- | ---: | ---: | ---: |
| Median paired create-wall ratio | 1.508439 | 1.476024 | ≤1.80 |
| Median paired create-CPU ratio | 1.531919 | 1.499049 | ≤1.80 |
| Median paired apply-wall ratio | 1.001430 | 1.000019 | ≤1.10 |
| Rust selector query p95, µs | 4.739 | 6.650 | ≤50 |
| Descriptor throughput, MiB/s | 359.799 | 341.140 | ≥250 |

Logical index cost: **4,956 bytes / 83 objects = 59.71 B/object**, within frozen 64 B/object budget. Descriptor representation is another 5,312 B; neither figure measures **process RSS, allocator overhead or lifecycle rebuild costs**.

## Post-hoc auditor's note: semantic versus raw byte identity

The two raw `measurements.jsonl` files are **not byte-identical**, because paired measurements contain independent CPU/wall times. They each contain 115 complete rows. The frozen evaluator compares the semantic quality signature **(target occurrence, base object, physical patch bytes, applied SHA-256)** and the selected K2 bases, not the raw timing JSONL byte stream. Both semantically match. Informal frozen prose saying "byte-identical quality tables" must not be reinterpreted as requiring CPU/wall timing byte equality. This ambiguity is disclosed *after* the experiment; the frozen protocol and evaluator are not amended.

## Reproducing verdict without rerunning sealed measurements

From the repository root, use the original frozen v3 evaluator over retained JSONL:

```bash
python3 .work/tools/selector_s4_confirmation_v3.py evaluate \
  .work/results/SELECTOR-S4C/evaluation/plan.json \
  .work/results/SELECTOR-S4C/A \
  .work/results/SELECTOR-S4C/B \
  /tmp/s4c-independent-result.json
```

The result must equal the retained original `evaluation/result.json` and `independent-evaluation.json` as structured JSON. The original ZIP digests remain checksummed in `retained-manifest.json`.

## Claim boundaries

The scoped PASS does not establish generalization beyond bzip2, positive lifecycle ROI, production reliability for unseen datasets, universal exactness of indexed retrieval, true full-catalog RSS, or demand for a standalone Rust library. Next gates: H11 correctness/snapshot assumptions; H12 full-system lifecycle break-even; independent preregistered multi-family cohort; DELSK-013 GO/PIVOT/STOP. Opened E1 is never fresh holdout for these follow-ups.
