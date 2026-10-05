# DELSK-003 Slice C0: pilot infrastructure

| Элемент | Статус |
|---|---|
| R0 foundation | **READY** |
| Slice A `delsk.oracle-contract.v1` | **FROZEN** |
| Slice B | **IMPLEMENTED / CONFORMANCE PASS** |
| Slice C0 | **BLOCKED BY PILOT INFRASTRUCTURE** |
| Natural oracle (79 queries, 1 961 pairs/codec) | **NOT_RUN** |
| G1 | **NOT_RUN** |

Base: `35274dd14dc54a7b91cc3f5c151636fccd08c316`. Frozen contract, codec lock, C14 golden, acquisition locks, E1 seal, `C_t`, scientific evaluator semantics and thresholds unchanged. This Draft PR prepares adapters, gates and evidence tooling; it does not authorize dispatch or claim PILOT INFRASTRUCTURE READY.

## Blocking counterexample

GitHub run inventory cannot prove that every dispatch was retained. Suppose runs 1 and 2 are COMPLETE and failed run 3 is deleted before its first inventory observation. The API then lists contiguous runs 1 and 2. Pagination, repeated reads, timestamps and run-number gap checks cannot distinguish that history from a history in which run 3 never existed. A deleted rerun before observation has the same problem. Artifacts on the same service do not supply independent durable history; a destroyed runner cannot upload an attempt artifact.

The requested invariant, **no dispatched attempt can disappear from G1**, therefore remains unproven. Production pilot worker and the shared direct-runner gate unconditionally reject with `DISPATCH_HISTORY_UNVERIFIED`, before natural acquisition/encoding. Production G1 also cannot return PASS without independent dispatch history. There is no input, environment variable, CLI waiver or operator declaration to disable these guards. A later reviewed infrastructure change must define and verify independent durable capture of dispatches and reruns, including attempts lost before bootstrap; successful inventory alone is insufficient. This is an infrastructure blocker, not a frozen scientific contract defect.

## Implemented path

- [Dispatch registration design](dispatch-registration-design.md) and [implementation plan](dispatch-registration-plan.md) define a broker foundation with an append-only intent journal, independent publication/readback before submission, exact run/attempt binding and fail-closed handling of ambiguous responses. [oracle_dispatch.py](../tools/oracle_dispatch.py) is an offline state machine with injected storage/submission callbacks, not a deployed capture service. Actor execution policies can refuse execution while leaving a failed run; the current organization audit endpoint returned 404. Neither observation proves complete historical dispatch capture. Production guards remain closed pending the activation requirements in the design.
- [oracle_materialize.py](../tools/oracle_materialize.py) validates the D/E0/E1/oracle chain and E1 code hashes, verifies exact pinned HTTPS source size/hash before extraction, reproduces frozen transforms and occurrence witnesses, and emits only required object IDs. Archive traversal, expansion, links and unexpected inventory fail closed. The independent store verifier streams every file, verifies length/hash and requires exact expected/actual sets. Production modeled gzip requires frozen zlib 1.3; no replacement bytes or runtime waiver.
- [oracle-pilot.yml](../../.github/workflows/oracle-pilot.yml) accepts only manual branch dispatch on the exact lowercase 40-hex SHA, with source/workflow SHA and workflow-ref equality, Linux X64, standard `ubuntu-24.04`, pinned actions, read-only permissions and repository group `delsk-experimental` (`cancel-in-progress: false`). Inputs reach code via environment, never shell interpolation. Branch-only dispatch avoids ambiguous tag identity in API inventory.
- A bounded bootstrap dispatch artifact is uploaded before checkout. A richer attempt artifact is uploaded before codec setup. The supervisor requires an upload receipt, full budget admission and capped filesystem. Receipt presence is a workflow prerequisite, not independent proof of complete historical dispatches.
- [oracle_pilot.py](../tools/oracle_pilot.py) contains build/provenance, fresh C01–C14, materialize/full-store verification, expected-universe and admission gates. C14 compares the immutable golden projection; the fresh live conformance record must also be byte-identical on runner recheck. Gates are repeated at the direct runner entry and before execute; executable hashes are rechecked. The natural path stays closed by the history blocker.
- PR smoke uses synthetic archives/fault fetchers, synthetic stores, real pinned codec conformance and the synthetic mini-oracle. It rejects object IDs from the frozen natural corpus, including locks relabelled with synthetic schema names. It never dispatches pilot, downloads natural payloads or encodes natural pairs.

## Two-stage retention and ledger

[oracle_attempts.py](../tools/oracle_attempts.py) exposes `inventory REPOSITORY SNAPSHOT`, `reconcile SNAPSHOT RESULTS [BASE_RESULTS]`, `retain ENVELOPE RESULTS`, `audit-base BASE_SHA [RESULTS]` and the G1 integration. Inventory enumerates all pages and all rerun attempts, binds each exact source commit via git, rejects gaps/inconsistent concurrent reads and records a hashed immutable snapshot. These checks detect observed omissions; they do not close the counterexample above.

Intended flow: Actions → immutable dispatch/status/envelope artifacts → inspect/download → reviewed evidence PR → retained bundles and append-only ledger → independent G1 inventory. Workflows never write main. Before any attempt, `.work/results/DELSK-003-ORACLE/` is absent, as required by the frozen no-natural-evidence test. First reviewed reconciliation creates `attempts.json` (`delsk.oracle.attempts.v1`), immutable `.inventory/<digest>.json` and its current pointer. There is no fabricated initial attempt or tracked empty results directory.

Every dispatch entry retains measurement identity, run ID/attempt, source/workflow SHA and creation metadata. Immutable dispatch identity is distinct from changing status observations in snapshots and from verified scientific bundles. Retention verifies closed checksums and bindings, preserves attempt/materialization sidecars under `.attempts/<run-id>-<attempt>/`, and retains normative bundles through the existing independent verifier. PR CI compares against the immutable base commit: prior entries, snapshots, sidecars and bundles cannot be deleted, rewritten or cherry-picked. A status-only artifact records existence but never counts as a verified oracle bundle. Missing bundle blocks PASS with `ATTEMPT_NOT_RETAINED`; INVALID cannot be replaced by later success. Reruns do not count as independent run IDs; identities cannot be mixed.

Synthetic A–J tests preserve frozen G1 outcomes (two independent identical COMPLETE → scientific pass; INVALID precedence; incomplete/missing/extra/identity/rerun rejection; commitments/cost/target mismatches → INVALID). Production `g1_root` takes no snapshot: it always refreshes the independent inventory. Supplied snapshots go only to the separate offline `g1_offline`, which reports a scientific pass as `TEST_ONLY_PASS`, never `PASS`.

Frozen §7 also requires a green KAT suite on the evaluator commit. Production G1 checks this from the independent Actions API, never from bundle fields: the reviewed `oracle-smoke.yml` and the frozen KAT files must be byte-identical at the exact measured commit, and at least one push/dispatch smoke run for that commit in this repository must have a successful KAT step. Every attempt counts; a red or pending attempt is not outvoted by a green rerun, and pull_request runs (merge refs) do not count. Missing, red or unverifiable evidence adds `KAT_NOT_VERIFIED`.

## Bounds, failures and leakage

Job ≤30 min; supervised setup/workload ≤22 min; frozen per-codec timeout; per-process `RLIMIT_AS` 8 GiB and `RLIMIT_FSIZE` 1280 MiB; hard tmpfs work cap 1280 MiB; free disk ≥2× cap; ≤4 096 pairs/codec (locked universe 1 961). Supervisor tracks descendants including new sessions and kills them on termination. Artifact envelope cap is 16 MiB minus 16 KiB reserved for bootstrap/status artifacts; repository artifact admission remains 256 MiB. Pilot budget forces enforce mode and shares accounting with foundation. Caps cannot grow implicitly after failure.

| Trigger | Closed evidence class |
|---|---|
| HTTP/network 404/5xx | `SOURCE_FETCH_FAILED` |
| Source bytes/hash mismatch | `SOURCE_IDENTITY_MISMATCH` |
| Traversal/unsafe archive | `ARCHIVE_UNSAFE` |
| Expansion limit | `EXPANSION_CAP` |
| Object hash/length or missing/extra object | `OBJECT_INTEGRITY` / `OBJECT_SET_MISMATCH` |
| Build / conformance / runner-gate refusal | `CODEC_BUILD_FAILED` / `CONFORMANCE_FAILED` / `INFRASTRUCTURE_FAILED` |
| Budget / free disk or tmpfs refusal | `BUDGET_REFUSED` / `DISK_ADMISSION_REFUSED` |
| Killed runner / wall limit | `RUNNER_KILLED` / `PROCESS_WALL_TIMEOUT` |
| Artifact upload failure | `ARTIFACT_UPLOAD_FAILED` |
| Unprovable historical dispatch coverage | `DISPATCH_HISTORY_UNVERIFIED` |
| No green exact-commit KAT evidence (G1 blocker) | `KAT_NOT_VERIFIED` |

Before the first pair, failures leave bounded attempt/status evidence when upload is possible. Partial runs recover missing rows as INCOMPLETE via the frozen finalizer; they never count as COMPLETE. Runner loss or upload failure still needs independently captured dispatch evidence, which is why production remains blocked.

Natural subprocess stdout/stderr are discarded; exception strings are replaced by closed machine classes. Export permits only the normative sealed bundle, attempt, materialization verification/provenance and checksum files. No private costs, corpus objects, patches, env/token dumps, build/debug logs or step summaries are exported. Synthetic smoke output cannot expose natural costs.

## Review and validation

Adversarial review covered direct worker/runner bypass, forged conformance/provenance, binary/object substitution, custom results roots, unretained attempts, stale/mixed rows, rerun independence and leakage. Regression tests cover the fixed bypasses and the trailing-deletion blocker. Frozen bindings are revalidated without natural fetch. Local tests are engineering checks; Actions runs pinned conformance and the complete synthetic path. CI links and final test counts belong in the Draft PR. No natural measurement, utility/cost publication, DELSK-004 work or pilot dispatch was performed.
