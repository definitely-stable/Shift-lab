# H12-B0 — independent cohort intake (DISCOVERY ONLY)

Status: **UNFROZEN, NOT ACQUIRED, NOT READY FOR MEASUREMENT**. Owner: H12 issue #59 / DELSK-013 #14.
Stage H12-A descriptive ROI script and the opened E1 bzip2 result are *not* a fresh H12-B holdout.

## Required scientific separation

The exposed prior DELSK pilot/development families were zstd, zlib, curl, libpng and sqlite;
the S4-C evaluation family was bzip2. H12-B must exclude all six as independent *evaluation* families,
even if someone changes targets or reorders versions. Split at family level, not file/target level.
Do not allow training/tuning on any selected evaluation family's ancestors or source asset metadata
after the family is assigned to the sealed evaluation population.

## Source-family candidates (not frozen or accepted)

- google/brotli — upstream https://github.com/google/brotli , MIT source license candidate,
  see https://github.com/google/brotli/blob/master/LICENSE. Individual archive license review PENDING.
- ebiggers/libdeflate — upstream https://github.com/ebiggers/libdeflate , MIT source license candidate,
  see https://github.com/ebiggers/libdeflate. Individual archive license review PENDING.
- lz4/lz4 — upstream https://github.com/lz4/lz4 , **mixed member licensing**:
  library is BSD-2-Clause; command-line/test files are GPL-2.0-or-later unless exceptions,
  see https://github.com/lz4/lz4/blob/dev/LICENSE. All member-level exclusions/attribution PENDING.

The three sources above are all **source-code compression libraries** and are NOT three independent
data modalities. They are a *candidate list only*, not a natural holdout or a multi-family scientific gate.
Do not silently promote them to production or generalize to game files, application binaries, model weights.
No source release tags, assets, SHA-256, member-level source licenses or version ancestry have been pinned.

## Separate release-asset cohort acceptance before H12-B1

- Add independent version-paired application executable/binary assets and non-code large assets;
  justify each license and redistribution permission. Until then the mandatory modality gate is unmet.
- Acquire **only through bounded GitHub-hosted CI**, record upstream immutable URLs/tags, SHA-256 archive
  and expanded members; ensure exact member lists, exclusions, license notices and source provenance.
- Freeze exact versions and acquisition transforms before candidate/encoder policy probing; keep disjoint
  pilot/evaluation groups at full family/release lineage granularity.
- Freeze finite population, size bins, target/base ancestry and null controls, transfer fanout regimes,
  codec/encoder options, CPU/latency/RSS and per-file outcomes, required pair counts and budgets.
- Repeat across independent hosted workers and preserve first-attempt run IDs and artifacts.
  Do not substitute failed runs or tune selection/K after observing held-out quality.

## Machine gate

The manifest H12-B0-CANDIDATE-DISCOVERY.json has explicit stage DISCOVERY_ONLY_NOT_FROZEN
and unmet modalities application-binary + non-code-large-object. The validator
.work/tools/h12_corpus_intake.py fails closed on leaked prior-family IDs, duplicate fields,
invalid/sneaked SHA or decision status, unsorted candidates, unsupported source URLs and
falsely claimed modality/license approval. All expected outcomes are NOT READY.
The associated .work/tests/test_h12_corpus_intake.py runs in existing GitHub Research documentation CI.
No network or source acquisition is performed by the gate. The intake does not freeze a future
experimental protocol or authorize H12 quality/ROI claims.
