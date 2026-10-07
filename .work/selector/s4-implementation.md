# S4 implementation: GitHub-hosted ChunkShift screen

Status: **IMPLEMENTED / AUTOCHAIN ARMED; authoritative S4-D rerun pending this PR merge**.  
Protocol authority: `ea35f16a0f52cd7c41df2763f0bd2794fbbdb476` (merge of PR #52).  
Consumer: `definitely-stable/ChunkShift@74bb301b6d8ecc52cf0bc0e00d86fa174093d91b`.

This document describes implementation only. It does not modify S4 sections 1–6 and contains no S4 result.

## Execution graph

S4-D uses three workflow surfaces.

### 1. `selector-s4-shard.yml`

One standard `ubuntu-24.04` job per dispatch, 30-minute cap, in the existing `delsk-experimental` concurrency group and runner-minute ledger.

Inputs:

- exact merged implementation `source_sha`;
- `shard_index ∈ [0,15]`.

Each dispatch:

1. requires `refs/heads/main` and `source_sha == GITHUB_SHA`;
2. passes normal experimental admission;
3. checks out the protocol authority separately at `ea35f16…`;
4. rebuilds the S4 plan with the authority copy of `selector_s4.py`;
5. re-materializes the pinned pilot and X0 stores inside the runner;
6. checks out exact ChunkShift `74bb301b…`;
7. builds its CLI in Release/net10.0 using its pinned `global.json`;
8. measures one deterministic target shard;
9. uploads **only evidence JSON**, never source objects, manifests, CSP files or reconstructed payloads.

The 119 targets are sorted by occurrence id and assigned round-robin by ordinal modulo 16. All rows for one target — self-contained plus its entire exhaustive `C_t` — stay in the same shard. Across the 16 shards the exact frozen workload is 3,815 measurement rows.

A pair produces exactly one closed `delsk.chunkshift-s4.measurement.v1` row. A create/apply/reconstruction failure is retained as failure evidence and is not retried inside the selected run.

Authoritative evidence uses only **first attempts**. A failed infrastructure run may be disclosed and a new workflow dispatch can be made, but a rerun attempt cannot replace the selected shard evidence.

## 2. `selector-s4-cost.yml`

One separate 30-minute standard hosted job on the exact S4-D object universe.

It scans every unique content object once with the authority implementation of `delsk.simple-selector.v1` and retains:

- unique objects and bytes scanned;
- descriptor wall/CPU time;
- descriptor bytes;
- postings/path-index construction wall/CPU;
- index bytes using the same accounting formula as Rust `Catalog::index_bytes`;
- peak RSS.

This timing is descriptive only and cannot affect S4-D eligibility.

## 3. `selector-s4-evaluate.yml`

No natural payload is acquired.

Inputs:

- exact implementation `source_sha`;
- exactly 16 successful first-attempt shard run IDs;
- one successful first-attempt selector-cost run ID.

The workflow obtains run and artifact metadata directly from GitHub, requires:

- `workflow_dispatch`;
- completed/success;
- attempt 1;
- `main`;
- same implementation SHA;
- exact expected workflow path;
- exactly one expected artifact;
- non-expired artifact with GitHub SHA-256 digest.

Downloaded ZIP bytes must match the GitHub artifact digest before extraction.

`selector_s4_collect.py` then requires all shard indices 0–15 exactly once, one implementation/protocol/consumer identity, admitted compute, retained row/digest counts and no duplicate pair across shards.

Finally, the verdict is produced **only** by:

`.work/tools/selector_s4.py evaluate`

from the separate protocol-authority checkout at `ea35f16…`.

The implementation checkout cannot redefine plan construction or eligibility after seeing ChunkShift bytes.

## Evidence boundary

Shard artifacts contain:

- `admission.json`;
- `measurements.jsonl`;
- `manifests.jsonl` (manifest metadata/timing only);
- `shard.json`;
- `run.json`.

They do not contain natural object bytes, CSM files, CSP files or reconstructed outputs.

The final evaluation artifact contains:

- merged `measurements.jsonl`;
- `collection.json`;
- GitHub `artifact-index.jsonl`;
- `selector-cost.json` and its artifact provenance;
- immutable `result.json`;
- evaluation run provenance.

## What is still forbidden

Until this implementation PR is merged:

- do not dispatch S4 shard or cost workflows;
- do not inspect S4 ChunkShift result bytes;
- do not change S4 protocol sections 1–6;
- do not open the sealed pilot evaluation split;
- do not claim G5, product readiness or a production ChunkShift integration.

## Automatic execution chain

The first manual smoke under implementation `d8bcbb5207702baf69b748edd4bafef7950d08ce` proved the cost and shard workflow surfaces, but those runs are retained only as activation/smoke evidence once this autochain PR changes main.

This PR adds a one-shot automatic chain:

`push(main from d8bcbb5...) → cost → shard 0 → shard 1 → ... → shard 15 → evaluator`.

Properties:

- the autostart workflow is armed only when `github.event.before == d8bcbb5207702baf69b748edd4bafef7950d08ce`; later edits cannot silently retrigger the experiment;
- `batch_id` must equal the new exact implementation SHA;
- cost dispatches shard 0 only after successful evidence upload;
- every shard receives the exact accumulated prior run IDs and requires their count to equal its shard index;
- every successful shard dispatches only the next shard; there is no waiting controller job and no queue of 15 pending runs;
- shard 15 requires exactly 16 unique run IDs before dispatching the immutable evaluator;
- any infrastructure/admission/artifact failure stops the chain instead of being silently retried;
- a scientific pair failure remains an explicit measurement row and reaches the frozen evaluator as `INVALID` if applicable;
- every child run remains an independent first-attempt `workflow_dispatch`, preserving the evidence model frozen in S4.

After this PR merges, the new implementation SHA becomes the only authoritative S4-D batch identity. The earlier `d8bcbb5...` cost/shard-0 runs are not mixed into the final collection.
