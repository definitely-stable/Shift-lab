# Корпус и baseline matrix

Статус: **exploratory acquisition pilot frozen (Slice D)**; source/corpus locks, snapshot license review и две совпавшие materializations — в [pilot-v1](corpus/pilot-v1/README.md). Ancestry audit и candidate construction design приняты в Slice E0 ([construction contract](corpus/e0/construction-spec.md)); sealed candidates (E1), expansion и confirmatory sufficiency ещё не завершены. Загружать данные и запускать эксперименты — только в Actions. Публичный URL не означает разрешение redistributing.

## Coverage

| Domain | Источник / единица lineage | Стартовый материал и ограничение |
|---|---|---|
| Sources/builds | GNU GCC, Linux, Node.js официальные source/releases; отдельный проект — lineage | небольшие подмножества файлов 3–5 версий, pinned archive/commit; обрезка до осмотра scores, не выбирать только хорошо сжимаемые файлы |
| Binaries/update artifacts | release artifacts открытых проектов, подходы corpus ChunkShift | ELF/PE, relocations/metadata, разные build versions; лицензию исходников нельзя автоматически приравнять к правам на все бинарные assets |
| Archives/tabular | воспроизводимые tar/zip/zstd representations тех же source families, открытые табличные revisions | logical и physical relatedness разделены; transformed variants остаются в той же split |
| Containers | официальные OCI manifests/layer digests | compressed blob и extracted layer — разные tracks; checksum по registry digest, size/expansion caps; provenance/redistribution review до включения |
| Models | публичные base/fine-tuned BF16/FP16 safetensors при совместимой лицензии | маленькие tensor slices, одна ancestor family в одной split; synthetic XOR не даёт model-domain claim; full checkpoint loading не требуется |
| Assets / VM / Stack Overflow | открытые versioned assets, traces из paper artifacts при доступности | deferred пока нет лицензированной, ограниченной и воспроизводимой выборки; отсутствие данных явно остаётся coverage gap |

Pilot-v1 (exploratory) — шесть небольших независимых C-проектов по три исторических release: zlib, Zstandard, curl, libpng, SQLite amalgamation, bzip2; recipe, publication time и license evidence — в [source plan](corpus/source-plan.json). Roster смещён к compression libraries и проверяет acquisition plumbing и contracts, не репрезентативность. GCC/Linux/Node.js и остальные domains таблицы — expansion backlog с отдельными acquisition/license budgets. Шесть lineages недостаточны для confirmatory вывода: G3 требует расширения и precision analysis до freeze. Уже проведённые исследования не определяют автоматически пригодность конкретного доступного snapshot.

Synthetic suite: empty, all 256 repeated bytes, periodic/zero regions, seeded random, insert/delete 1/8/64/4096 B, block permutation, containment в обе стороны, repeated motifs, metadata edit, recompression, equal-length XOR perturbation, unrelated high entropy. Генератор и seed фиксируются; это correctness/diagnostic evidence, не замена natural corpus.

## Manifest contract

Точные schemas, canonical JSON, identities, time intervals, splits и правила `C_t` — в [corpus contracts](corpus/README.md); детерминированные правила — в [selection policy](corpus/selection-policy.json), validators — в `tools/manifests.py` с тестами в Actions. Кратко: content identity `object_id=sha256(bytes)` отделена от provenance `occurrence_id`; release time — interval из publication evidence, база eligible только при `base.hi < target.lo`; split назначается ancestry component, transforms наследуют split; каждый `C_t` — sorted unique content IDs с `candidate_list_sha256`, self и target bytes исключены, identity-only targets идут в dedup branch. Target bytes не хранятся в results git, если лицензия не разрешает. Bad hash, missing member, unexpected expansion и недоступный URL прерывают materialization, без silent substitution.

Pilot caps: ≤256 MiB acquired, ≤1 GiB materialized, ≤64 targets ×64 candidates, максимум 4096 ordered pairs на codec. Shards confirmation ≤2 GiB materialized, ≤20,000 pairs/codec и time cap. Допускается меньший детерминированный sample; нельзя принудительно достичь pair limit за счёт утечки evaluation.

## Baselines

| Группа | Роль / обязательность | Правила сравнения |
|---|---|---|
| No-delta, exact duplicate lookup | обязательны | тот же framing и checksum; duplicates отдельно |
| Random(seed), size-nearest, previous-version/recency | дешёвые обязательные controls | metadata доступна всем; previous version только если deployment знает связь |
| Exact scan descriptors + MinHash/KMV | обязательный generic baseline | shingle sizes, hash seed, estimator и budget записаны; одинаковый corpus |
| Length + target-normalized containment | обязательный дешёвый directional control | отдельно от Jaccard и length-only; одинаковые feature/cardinality estimates и metadata budgets |
| N-transform/Finesse | обязательный non-ML reference | опубликованная реализация или явно labeled reimplementation; проверить совпадение алгоритма |
| Palantir/BePro | приоритет современного reproduction | доступность artifact/license и actual build проверяется DELSK-004; paper numbers не считаются нашим baseline |
| SpeedSketch | ближайший contemporary candidate с авторским кодом (GPL-2.0) | нужен adapter для общего `C_t`/Top-K; README-отклонения от paper (CDC 4/8/32 KiB) записываются как deviations; ускорение encoder не засчитывается ranking quality |
| Odess, Argus, Sonic, DCLC, CARD | contemporary claim coverage | unavailable code → `UNAVAILABLE` или отдельно paper-faithful reproduction; inspired heuristic не носит имя оригинала в chart |
| DeepSketch | главный learned reference | фиксировать модель/training data/cost; pretrained CPU inference если воспроизводимо. Отсутствие GPU не даёт основание заявить превосходство над ML |
| Exhaustive encoder | small-pool upper bound | все пары и failures; вне timed deployment lane |
| Tensor-aware/XOR | только optional model track | same-shape/dtype/tensor mapping и reconstruction metadata; не называть собственной XOR+zstd реализацией BitX без faithful reproduction |

Источники: [literature review](research/literature-review.md) и [claim matrix](research/claim-matrix.md). Проверенная доступность на 2026-10-04 — [baseline-availability.json](research/baseline-availability.json): provenance `AUTHOR / REIMPLEMENTED / PROXY / UNAVAILABLE` отделено от paper fidelity, license, data и reproduction status. Ни одна реализация пока не воспроизведена. Каждый baseline lock DELSK-004 добавляет к этим полям patch hash, build command, compiler, runtime, flags, tuning budget и supported track.

## Codecs

Первый oracle — pinned xdelta3, options/secondary compression/window sizes фиксированы. VCDIFF совместимость не означает byte equality разных encoders. Второй независимый generic codec — pinned open-vcdiff или bsdiff-class implementation после license/build review. ChunkShift.Patching добавляется как потребитель при доступном contract; его собственный формат не становится форматом Delsk.

XOR+lossless compressor — отдельная пара base/target одинаковой структуры; unequal length требует явно определённого mapping, иначе unsupported. Zstd dictionary — дополнительный codec-conditioned эксперимент с учётом dictionary bytes и подготовки, а не бесплатная база. Не нужно сразу запускать все codecs во всех tiers: двух generic достаточно для начала codec transfer, model class — отдельный gated track.

## Stop conditions

Запрещено помещать один lineage в train и held-out через разные упаковки; переводить отсутствующий baseline в победу; считать скачанные архивы дополнительными независимыми targets; удалять timeout/hard negatives. Все coverage holes отражаются в summary. Уменьшение corpus после просмотра результата требует нового lock и нового exploratory run.
