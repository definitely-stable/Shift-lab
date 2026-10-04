# Corpus и candidate contracts (DELSK-002, pilot-v1)

Статус: **PROPOSED**. Здесь зафиксированы identities, provenance, время, splits и sampling **до** acquisition и до просмотра любых scores. Ни один файл этой директории не является frozen corpus: source plan не содержит acquisition hashes, а locks появятся только из CI materialization (Slice D) и ancestry/candidate sealing (Slice E). Это private research interfaces, не public API Delsk.

| Файл | Содержание |
|---|---|
| [source-plan.json](source-plan.json) | Pilot roster: families, releases, archive URLs, publication-time evidence, license evidence, path exclusions, ancestry edges, deferred domains |
| [selection-policy.json](selection-policy.json) | Детерминированные правила: members, strata, tracks, splits, time, duplicates, targets, `C_t`, caps |
| [manifests.py](../tools/manifests.py) | Canonical JSON, identities, time intervals, ancestry/splits, member selection, validators lock/candidate schemas |
| [test_manifests.py](../tests/test_manifests.py) | Boundary fixtures; выполняются в Actions вместе с docs validation |

## Границы

- Pilot exploratory: шесть C-проектов, смещение к compression libraries. Он проверяет acquisition plumbing и contracts, не репрезентативность и не G3. Pilot families, просмотренные при tuning/evaluation, не становятся confirmatory holdout.
- Thresholds, denominators и verdict rules DELSK-P1 не меняются. Caps policy не могут быть выше P1 (`256 MiB` acquired, `1 GiB` materialized, `4096` pairs/codec) — это проверяет validator.
- Данные приобретаются только в GitHub Actions. Payloads не попадают в results Git. Публичный URL не разрешает redistribution: license status каждой family остаётся `PENDING_SNAPSHOT_REVIEW` до member-level review snapshot.
- Selection не читает patch bytes, encoder/scorer output или compressibility (`forbidden_selection_inputs`). Path exclusions выведены из provenance-инвентаря путей (vendored / shared-origin), не из содержимого.

## Canonical JSON

Все policy/lock файлы хранятся в одной точной форме: UTF-8 без BOM, ключи ASCII, `sort_keys`, отступ 2 пробела, LF, финальный перевод строки; только `null/bool/int/str/list/object`, строки в NFC. Floats, `NaN` и duplicate keys отклоняются. `loads_strict` требует, чтобы байты файла **уже** совпадали с canonical form, поэтому SHA-256 файла (`file_sha256`) однозначен. Для IDs, rank keys и `candidate_list_sha256` используется compact canonical JSON (`digest`). Порядок элементов списка семантичен; списки records сортируются по своему ID.

## Identity и provenance

- `object_id = sha256(bytes)` — content identity. Одинаковые bytes = один content class.
- `occurrence_id = digest(["delsk.occurrence.v1", source_id, provenance])`, где `provenance = {member_path, transform, options, offset, length}`. Локальные пути, порядок download и mtime в identity не входят.
- Все aliases (одни bytes под разными provenance) сохраняются; в `C_t` content class учитывается один раз, representative — наименьший eligible `occurrence_id`.
- `member_path` — нормализованный POSIX путь относительно корня архива после удаления одной верхней директории: NFC, без `..`, `.`, пустых сегментов, `\`, drive prefix и control characters. Duplicate member paths внутри release — ошибка (hostile archive), а не выбор одного.
- Chunk occurrence записывает `parent_object_id` (SHA-256 member); если тот же member есть в file track, хеши обязаны совпасть.

## Время

Release time берётся только из publication evidence upstream (`time.value` + `evidence_url`). Дата без зоны превращается в UTC interval `[day−14h, day+1d+12h]` (любой local day UTC−12…UTC+14); timestamp обязан иметь offset и целые секунды. База eligible, только если `base.hi < target.lo`. Неизвестное время исключает объект из temporal deployment track и как базу, и как target. Acquisition time и mtime не используются.

## Ancestry и splits

Единица split — ancestry component: families, соединённые `ancestry_edges` с `resolution: merge`. Shared origin, устранённый исключением путей, записывается как `path_excluded` с именами globs; dependency без общего payload — `no_shared_payload`. Components сортируются по `rank("split", seed, наименьший family_id)` и заполняют `4 development / 1 calibration / 1 evaluation`. Другое число components **останавливает sealing** (validator и `assign_splits` падают); перераспределение требует review source policy. Все производные representations наследуют split своего release. Content, встречающийся в нескольких splits, обязан иметь object-level exclusion `cross_split_content` и не используется ни как база, ни как target.

## Members, strata и tracks

1. Retained member: regular file с суффиксом `.c`/`.h`, не совпадающий с `global_exclude_globs` и `exclude_globs` своей family (fnmatch, `*` пересекает `/`). Остальное — exclusions с причиной.
2. File track: strata `[64K,256K) [256K,1M) [1M,4M) [4M,16M)`. В каждой паре (release, stratum) выбирается member с наименьшим `rank("member", seed, family_id, path)`. Release не входит в key, поэтому один и тот же путь выбирается во всех releases, пока он остаётся в stratum. Пустые strata остаются пустыми.
3. Chunk tracks `chunk-4k … chunk-64k`: fixed offsets по всем retained members; short tail — exclusion `short_tail`. Каждый unit size — отдельный track.
4. Archive tracks `tar`, `tar-gz`: canonical ustar всех retained members release и его gzip. Они в lane `modeled`: сегодняшняя сборка архива не доказывает, что такие bytes существовали исторически, поэтому результаты lanes не объединяются.

## Targets и `C_t`

- Targets — только occurrences releases с ordinal 2/3; не более 64 near-duplicate targets, детерминированный round-robin по группам `(family, track, stratum)` (точный порядок — `targets.order`). Без padding до 64.
- Eligibility базы: тот же split, тот же track (значит тот же unit size и lane), `base.hi < target.lo`, не исключена. Self и target bytes в `C_t` запрещены.
- Если eligible база имеет те же bytes, target получает `status: identity_only` с `duplicate_of` и без pairs (dedup branch, отдельно в coverage, не тратит лимит 64).
- Audit categories на уровне content class: `same_path_historical` (та же family, path и offset) ≤2, `same_family_decoy` ≤30, `foreign_family_decoy` ≤32; отсутствующие категории не дополняются. `max_targets × Σcaps = 64 × 64 = 4096`, поэтому cap pairs нельзя превысить по построению, и validator это проверяет.
- Scorer видит только `object_id` и `bytes`. Categories, family, path, release и время — audit-only до отдельной deployment metadata policy.
- Synthetic negatives живут в diagnostic lane. До oracle слова «полезная база» и «hard negative» не означают измеренную классификацию.

## Схемы locks (заполняются Slices D/E)

`delsk.corpus.lock.v1`: `source_plan_sha256`, `selection_policy_sha256`, `materialized_bytes`, `sources[]` (`source_id = release_id`, `family_id`, `url`, `archive_sha256`, `archive_bytes`), `components[]` (`families`, `split` — должны совпасть с детерминированным назначением), `occurrences[]` (`occurrence_id`, `object_id`, `bytes`, `source_id`, `family_id`, `split`, `track`, `stratum`, `provenance`, `parent_object_id`), `exclusions[]` (`kind ∈ object/occurrence/member/source`, `subject`, `reason`, `detail`). Lock перечисляет все targets и все occurrences, на которые ссылается любой `C_t`.

`delsk.candidate.lock.v1`: `corpus_lock_sha256`, `selection_policy_sha256`, `planned_pairs_per_codec = Σ|C_t|` для near-duplicate, `queries[]` отсортированы по target: `target`, `status`, `duplicate_of`, `bases[]` (отсортированы по `object_id`: `object_id`, `representative`, `category`), `candidate_count`, `candidate_list_sha256 = digest(sorted object_ids)`.

Validator проверяет хеши policy/plan, детерминированные splits, occurrence IDs из provenance, transform/track/span/stratum согласованность, inheritance split, cross-split content, eligibility и representative каждой базы, categories, identity-only branch и caps. Он **не** может доказать по lock, что выбраны именно первые N баз по rank среди всех eligible chunks, если невыбранные occurrences не перечислены; это проверяет независимый пересчёт из materialization в Slice E.

## Известные ограничения pilot

- Roster смещён к C и compression libraries; GCC/Linux/Node.js, binaries, tabular, OCI, models, VM/assets — expansion backlog с отдельными acquisition/license budgets (`deferred_domains`).
- Детерминированное назначение (seed `20261004`, без merge edges): development — libpng, sqlite, zlib, zstd; calibration — curl; evaluation — bzip2. Оно вычислено один раз и не перебрасывается: смена seed или roster после просмотра назначения была бы selection.
- Calibration и evaluation cohorts по одной family: foreign-family decoys для них отсутствуют, и это coverage gap, а не ошибка.
- По git-tree инвентарю (2026-10-04) у bzip2 нет `.c/.h` ≥64 KiB, поэтому evaluation cohort не имеет file-track targets — только chunk и archive tracks. Strata `1–4 MiB` и `4–16 MiB` заполняет, вероятно, только SQLite amalgamation. Фактические размеры проверяются по release archives в Slice D.
- Сохранены project-owned tests, legacy decoders и generated first-party файлы (`crc32.h`, `sqlite3.c`); исключены только foreign/shared-origin пути, `contrib` и build scaffolding (см. `exclude_globs` с причинами). Неизменённый между releases файл даёт identity-only target, а не near-duplicate.
- Шесть components дают exploratory статус по P1 (`<10` held-out lineages на domain). Подтверждающая оценка требует новых families, estimand и precision analysis до freeze.
