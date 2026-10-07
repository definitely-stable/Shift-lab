# S4-D results: ChunkShift consumer development screen

Status: **COMPLETE — OPEN_CONFIRMATION_K2**.  
Owner: [DELSK-012](https://github.com/definitely-stable/Shift-lab/issues/13).  
Protocol authority: `ea35f16a0f52cd7c41df2763f0bd2794fbbdb476`.  
Implementation/batch: `a7d2d1346c70cb72adb62fdb221288414ea2132a`.  
ChunkShift consumer: `74bb301b6d8ecc52cf0bc0e00d86fa174093d91b`.

S4-D was the preregistered development screen in [s4.md](../../selector/s4.md). It did not open the sealed pilot evaluation split and cannot by itself close G5.

## Evidence

- selector-cost run: `37586176282/1`;
- shard runs: 16/16, all first attempts, all on the same implementation SHA;
- evaluator: `37597358766/1`;
- final evaluation artifact: id `11471047037`, GitHub SHA-256 `55a018575eb7a87c5334500723d362555123057ead7dfc53f372062db0eabb4c`;
- rows: **3,815 / 3,815**;
- failed rows: **0**;
- merged measurement SHA-256: `e8e0c0fae1e373a074441c26e2efbf7cfc199b43ad11a1453ec5e4f694f9ce57`;
- ChunkShift CLI SHA-256: `1ea0a5f018058d93417d8794dd3b343d419c8e018e415b3bc676a18e7e7f5b20`;
- .NET SDK: `10.0.401`.

Compact machine-readable bindings are in [retained-summary.json](retained-summary.json). Raw compact measurement rows are retained separately in deterministic compressed form; their decompressed bytes must hash to the measurement SHA above.

## Aggregate result

| lane | CSP bytes | SavingsCapture | create calls | create wall | create CPU |
|---|---:|---:|---:|---:|---:|
| `previous1` | 20,750,611 | 0.991262 | 238 | 291.98 s | 562.15 s |
| `size1` | 20,982,367 | 0.982108 | 238 | 293.35 s | 564.61 s |
| **`delsk2`** | **20,531,317** | **0.999924** | **355** | **488.53 s** | **948.29 s** |
| `delsk4` | 20,530,127 | 0.999971 | 584 | 808.31 s | 1,572.13 s |
| exhaustive | 20,529,404 | 1.000000 | 3,815 | 2,706.48 s | 4,819.77 s |

Against the best one-base control `previous1`, K=2:

- saves 219,294 physical CSP bytes, **1.0568%**;
- raises SavingsCapture from 0.991262 to 0.999924;
- uses 355 vs 238 create calls, ratio **1.4916×**;
- has descriptive aggregate create wall/CPU ratios **1.673× / 1.687×**;
- is only **1,913 bytes** above the exhaustive system oracle while using **10.746× fewer** create calls.

K=4 is also eligible under the development-screen gates, but the frozen rule chooses the smallest eligible K. Its extra 229 calls improve only another 1,190 bytes over K=2. The resulting verdict is therefore:

`OPEN_CONFIRMATION_K2`.

## Interpretation

This is the first evidence that the simple selector can improve a real ChunkShift patch-building workload, not just an offline oracle metric.

It is **not** yet evidence that Delsk should ship as a standalone library:

1. the population was already burned during selector development/X0 work;
2. the Python selector construction timing is descriptive and is not a production Rust performance claim;
3. K=2 pays for its byte improvement with a second base trial on many targets;
4. no held-out system confirmation has been run.

The next permitted decision experiment is the separately frozen K=2 holdout confirmation in [s4-confirmation.md](../../selector/s4-confirmation.md). K=4, abstention, thresholds and descriptor semantics are no longer tunable from confirmation results.
