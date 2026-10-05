# DELSK-003 Slice C0 implementation plan

Goal: prepare the reviewed production pilot path without performing any natural encoder measurement.

Spec: the user's Slice C0 request; frozen authority is `contract.md`, `freeze.json`, codec lock, C14 golden, acquisition freeze and E1 seal. Base commit: `35274dd14dc54a7b91cc3f5c151636fccd08c316`.

Constraints: no changes to frozen files, identities, candidate universe, thresholds or G1 scientific semantics; no natural downloads/measurements in PR tests; no pilot dispatch; Draft PR only, never merge. Standard `ubuntu-24.04` X64, read-only permissions, repository concurrency `delsk-experimental`, 30 minute job, 22 minute workload, 8 GiB process address space, 1280 MiB workdir, 16 MiB artifact.

Architecture: a deterministic adapter reconstructs only oracle objects from pinned acquisition records and independently verifies the whole store. A pilot supervisor registers an attempt before setup, executes gates and bounded workload, and exports only allowlisted sealed evidence. A separate inventory/retention tool reconciles every GitHub dispatch and rerun attempt with append-only reviewed evidence before G1.

Review focus: runner loss before checkout/upload; deleted runs/reruns and cherry-picked ledger rows; evaluation cost leakage through failure messages; runtime-dependent modeled gzip bytes; a direct pilot invocation bypassing infrastructure gates.

1. Materialization adapter (`oracle_materialize.py`, `test_oracle_materialize.py`): first failing tests for pinned archive identity, traversal/links/caps, each transform and occurrence identity, exact object set, wrong sizes/hashes/missing/extra. Implement frozen-chain validation, expected objects, deterministic construction and independent verification. Synthetic archives only.
2. Attempts (`oracle_attempts.py`, `test_oracle_attempts.py`): first failing tests for complete paginated dispatch inventory, all rerun attempts, gaps/ref mismatches, immutable entries, missing artifacts, checked import and A–J G1 inventory. Keep the frozen scientific evaluator and its closed bundle unchanged; infrastructure metadata belongs in a separate envelope.
3. Pilot (`oracle_pilot.py`, `test_oracle_pilot.py`, `oracle-pilot.yml`): exact dispatch checks, bootstrap status artifact before checkout, build/conformance/materialize/verify/admit/register gates, bounded quiet subprocesses, finalize/verify, envelope artifact allowlist, emergency status export. Extend PR smoke with synthetic supervisor and fault tests.
4. Integrate and review: run offline tests, pinned conformance and synthetic mini-oracle in Actions; verify frozen hashes again; adversarial review and regression fixes; document lifecycle/failure matrix/status; create Draft PR and inspect CI. Natural oracle and G1 remain NOT_RUN.

Review outcome: **BLOCKED BY PILOT INFRASTRUCTURE**. A never-observed trailing deleted run leaves a contiguous GitHub API history; API reconciliation cannot prove all-dispatch coverage. Worker, direct runner gate and production G1 fail closed with DISPATCH_HISTORY_UNVERIFIED, without a waiver. Independent durable dispatch/rerun capture needs a later reviewed design before any natural run. Details and implemented lifecycle: [Slice C0](slice-c.md). No natural results directory is committed before the first attempt.
