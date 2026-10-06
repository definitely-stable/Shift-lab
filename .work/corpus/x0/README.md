# DELSK-002 X0: screening трудных классов корпуса

Статус: **RUN** — preregistration смержена в PR #45 (до acquisition и до любого score); run 37449333091, [результаты](results.md): verdict `NO_HEADROOM_AT_256`, ни одной `HARD` ячейки. Issue: [DELSK-002](https://github.com/definitely-stable/Shift-lab/issues/3), мотивация — [DELSK-004 Slice A](../../baselines/results-slice-a.md). Параметры — [params.json](params.json), roster — [source-plan.json](source-plan.json).

X0 — **exploratory screening**. Он не закрывает ни одного gate (G1–G5), не является oracle-evidence контракта v4 и не даёт held-out. Его единственный вопрос — на каких классах данных дешёвые baselines **не** насыщают oracle. Ответ определяет состав confirmatory корпуса X1 (§9).

## 1. Почему нужен screening

Slice A на pilot-v1 показал: `previous_version` и MinHash 1024 B при K = 1 дают SavingsCapture 1.000. Headroom для любого selector не измерить. Причины — свойства корпуса:

- три релиза на family, и у большинства targets есть база с тем же путём из соседнего релиза одной ветки;
- только исходники C, fixed-offset chunks и modeled архивы;
- calibration и evaluation — по одной family.

Наращивать pilot тем же способом бессмысленно: новые families того же вида снова насытятся. Полный confirmatory корпус с G1-цепочкой (freeze, registry, два прогона, импорт) дорог. Сначала дешёвый screening показывает, где трудно, и только эти классы идут в X1.

## 2. Классы трудности

Каждый класс — заранее названная гипотеза, почему дешёвый метод может ошибиться. Классы не смешиваются при агрегации.

| ID | Класс | Почему трудно | Данные |
|---|---|---|---|
| H1 | Чередующиеся ветки релизов | хронологически предыдущий релиз — из другой ветки (A1 < B1 < A2 < B2): `previous_version` по порядку релизов берёт B1 для A2 | 6 C-проектов с maintenance-ветками |
| H4 | Скомпилированные бинарники | малое изменение исходника сдвигает адреса и таблицы по всему файлу; byte-shingles теряют сходство | 6 проектов, официальные Linux x86_64 release binaries |
| L-meta / L-blind | Lane метаданных | deployment без путей и порядка версий (content-addressed store, backup): доступны только bytes и размер | все данные X0, два lane на одном `C_t` |
| T-cdc | Content-defined chunks | границы chunk зависят от содержимого; соответствующие chunks соседних версий сдвинуты, совпадение offset ничего не значит | track `cdc-16k` поверх file-track objects |

Классы H2 (renames/moves), архивы и containers, tabular и models в X0 не входят: для них нет готового ограниченного набора с проверенным временем. Это coverage gap, а не вывод.

## 3. Roster

[source-plan.json](source-plan.json) фиксирует 12 families по 4 релиза: URL, формат, дату публикации с evidence URL, лицензию и исключения путей. Release ordinal — хронологический. Бинарные families задают `install_path` (имя исполняемого файла, как его видит deployment, например `/usr/bin/rg` → `rg`) и путь члена архива.

- **Исключения путей** (H1): vendored и shared-origin каталоги из upstream tree, с причиной. Пример: `deps/*` у Redis содержит Lua, а Lua — отдельная family roster; без исключения Redis и Lua делили бы payload.
- **Shared origin бинарников.** Rust-бинарники собраны одним toolchain и делят код `std` и общих crates; Go-бинарники делят runtime. В X0 все families лежат в одном split, поэтому для screening это не leakage, а реалистичные трудные decoys. Для X1 split-независимость бинарных families требует отдельного audit (§9).
- **Burn rule.** Families X0 видны до X1. Они никогда не попадают в calibration или evaluation X1 и любых следующих корпусов, только в development.

Лицензии: только открытые проекты. Payload не попадает в git и в artifacts; в git — только hashes и метаданные. Публичный URL не даёт права на redistribution, поэтому X0 ничего не распространяет.

## 4. Представления и `C_t`

Все правила — детерминированные функции roster, seed и bytes; никаких scores, patch costs и выходов кодера.

1. **Retained members.** H1: regular `.c`/`.h` вне исключённых путей (как pilot-v1). H4: ровно один член — исполняемый файл из plan; raw binary asset — сам файл. Unsafe path, duplicate path, links на retained path, bomb и truncated stream останавливают materialization (код `materialize.py` используется без изменений).
2. **Track `file`.** Strata `[16K,64K) [64K,256K) [256K,1M) [1M,4M) [4M,16M)` (нижний stratum добавлен: у Lua и nginx почти нет файлов ≥ 64 KiB). В каждой паре (release, stratum) — член с наименьшим `rank("member", seed, family_id, path)` (`manifests.select_members`), поэтому путь один и тот же во всех релизах, пока он в stratum. Бинарники попадают в stratum своего размера. Members > 16 MiB — exclusion `oversize`.
3. **Track `cdc-16k`.** Gear CDC (§4.1) по каждому object track `file`. Chunk provenance: `member_path`, `offset`, `length`, `parent_object_id`. Короткий хвост меньше `min` — отдельный последний chunk (CDC его допускает), не exclusion.
4. **Время.** Дата без зоны → UTC interval `[day−14h, day+1d+12h]`, как в pilot-v1. База eligible только при `base.hi < target.lo`.
5. **Targets.** Occurrences релизов с ordinal 2–4. Ячейка — (класс, track): H1-file, H1-cdc, H4-file, H4-cdc; квота каждой — 16 near targets. Внутри ячейки — round-robin по группам `(family, stratum)` в порядке `rank("target-group", seed, cell, family, stratum)`, внутри группы — по `rank("target", seed, occurrence_id)`. Identity (есть eligible база с теми же bytes) — dedup branch: потребляет ход группы (как E0 A02), но не квоту. Порядок измерения чередует ячейки по одному target в фиксированном порядке H1-file, H1-cdc, H4-file, H4-cdc.
6. **`C_t`.** Eligible: тот же track, `base.hi < target.lo`, другие bytes. Категории по content class (E0 A04): `same_path_historical` — та же family и тот же `member_path` (у `cdc-16k` — путь parent), `same_family_decoy`, `foreign_family_decoy`. Внутри категории берутся первые `cap` ([params.json](params.json): 3 / 21 / 24, всего ≤ 48). Порядок — `rank("candidate", seed, target, object_id)`. Исключение — `same_path_historical` у `cdc-16k`: chunks одного файла сотни, поэтому берутся 3 с ближайшей относительной позицией `|offset_b/parent_b − offset_t/parent_t|` (затем rank). Это metadata-правило, а не содержимое; без него случайные chunks того же файла почти никогда не были бы полезной базой. Shortage не заполняется.
7. **Compute cap.** `Σ(|b|+|t|)` по парам плюс `|t|` standalone по targets ≤ `encode_bytes_max` (4 GiB). Targets добавляются в порядке измерения из п. 5, пока cap не превышен. Target, который превысил бы cap, и все последующие не измеряются. Это score-free усечение suffix, оно записывается в coverage.

### 4.1 Gear CDC

```text
gear[i]   = mix(seed_cdc + (i+1)·0x9e3779b97f4a7c15 mod 2^64), i = 0..255; mix — финализатор splitmix64
h         = ((h << 1) + gear[byte]) mod 2^64
cut       если len ≥ min и старшие bits битов h равны нулю (h >> (64 − bits) == 0),
          или если len == max
min = 4096, bits = 14 (средний chunk ≈ 16 KiB + min), max = 65536; h сбрасывается в 0 после каждого cut
```

Golden vectors CDC (длины chunks на фиксированных входах) закрепляются тестом в PR реализации.

## 5. Измерение

- Кодер — закреплённый codec lock DELSK-003 (`xdelta3` с `-9 -S none`, standalone `zstd`) из [codec-lock.json](../../oracle/codec-lock.json), сборка тем же `oracle_build.py`. Каждая пара кодируется и декодируется, decoded SHA-256 сверяется с target. `D_E`, `S`, `O` — по протоколу §2. Failure или timeout — строка с `D_E = +∞`, из denominators не удаляется. Decode mismatch делает run `INVALID`.
- Методы: все методы Slice A ([contract](../../baselines/contract.md) §3) с теми же параметрами, плюс `version_previous` — metadata baseline, который знает версии: сначала базы того же `member_path` и той же ветки (`branch` из plan), ближайший offset, затем самая поздняя более ранняя версия той же ветки; потом остальные по правилу `previous_version`. У H4 ветка одна на family.
- **L-meta:** все методы. **L-blind:** `random`, `size_closest`, `minhash_resemblance`, `containment` — без путей, offsets, ветки и порядка релизов.
- Метрики — протокол §3 и реализация Slice A: SavingsCapture, Useful/Strict/ε Recall, regret p50/p95, K ∈ {1, 4, 8, 16}, budgets 64–1024 B. Bootstrap — cluster по families, 10 000 draws, seed 20261004.

## 6. Decision rule (preregistered)

Ячейка — (класс H1 или H4) × track × lane. Для каждой ячейки и каждого budget `b ∈ {64, 128, 256, 512, 1024}`:

```text
B(b)       = методы lane, у которых descriptor budget ≤ b; metadata methods имеют budget 0
best(b)    = argmax SavingsCapture@K=1 по B(b); ties — Useful Recall@1, затем меньший budget, затем имя
headroom(b) = 1 − SavingsCapture@K=1 of best(b)
HARD(b)    ⇔ headroom(b) ≥ 0.02 и в ячейке ≥ 8 useful targets из ≥ 3 families
```

Рядом публикуются headroom@K=4, Useful Recall@1 лучшего метода и 95 % интервал. Решение:

- Ячейки `HARD(1024)` — трудны даже для лучшего дешёвого метода на максимальном budget. Они идут в X1 первыми.
- Ячейки только `HARD(b)` при малом `b` — трудны для компактных дескрипторов. Они идут в X1, если гипотеза Delsk о малых budgets остаётся в scope (DELSK-006).
- Ни одной `HARD(256)` ячейки → negative evidence: на этих классах дешёвые методы почти достигают oracle. По протоколу §6 это довод за pivot к простому selector; вывод записывается и не прячется.

Порог 2 pp выбран заранее: он в 4 раза больше noninferiority margin G4 (0.5 pp), поэтому выигрыш в такой ячейке в принципе измерим. Изменить rule после просмотра результатов нельзя — только новый screening X0b с другим roster.

## 7. Запуск

Workflow `delsk-screening.yml` (добавляется в PR реализации, входит в `EXPERIMENTAL_WORKFLOWS`): только `workflow_dispatch` на `main`, `source_sha` = head, standard GitHub-hosted `ubuntu-24.04`, очередь `delsk-experimental`, admission по runner-minute ledger, `timeout-minutes: 30`, artifact cap. Один job: build codecs → acquisition и materialization → `C_t` → oracle → baselines → summary. Payload живёт только в `$RUNNER_TEMP`.

Код — новые модули `x0_corpus.py` и `x0_screen.py`. Модули из code manifest oracle (`oracle_build.py`, `oracle_run.py`, `oracle_eval.py`, `manifests.py`, `materialize.py`) и `baselines.py` импортируются, но **не меняются**: их bytes входят в science identity серии v4 и в params Slice A.

Caps ([params.json](params.json)): acquisition ≤ 256 MiB, materialized ≤ 1 GiB, 4 × 16 near targets × ≤ 48 баз = ≤ 3072 пары, `encode_bytes_max` = 4 GiB, workload ≤ 22 мин. Превышение — failed run, а не тихое сокращение.

## 8. Evidence и журнал

- Каждый dispatch, включая failed и cancelled, записывается в [runs.md](runs.md) с run ID и исходом.
- Retained-импорт успешного run — отдельный PR в `.work/results/DELSK-002-X0/<run>-<attempt>/`: `run.json`, `corpus.json` (occurrences без payload), `candidates.json`, `pairs.jsonl`, `targets.jsonl`, `rankings.jsonl`, `rows.jsonl`, `summary.json`, `decision.json`, `admission.json`. Evaluation по retained файлам пересчитывается локально байт в байт.
- X0 не использует registry v4 и не является production oracle. Все его числа помечены `SCREENING`; их нельзя цитировать как G1/G2 evidence.

## 9. После X0: X1

X1 — confirmatory корпус. Его дизайн пишется после X0 и до acquisition X1:

- состав — ячейки `HARD` из §6 плюс новые families: ≥ 10 held-out lineages на каждый заявленный domain (протокол §5), сплиты 60/20/20 по ancestry components, ≥ 3 lineages в calibration;
- ancestry audit с вторым clone signal (normalized-token или winnowing), для бинарников — audit общего toolchain-кода;
- oracle — новый frozen контракт, который привязывает corpus и candidate locks параметром серии, чтобы следующие корпуса не требовали новой activation registry;
- критерий выбора сильнейшего baseline на calibration — заранее и не насыщаемый: SavingsCapture@K=1, затем normalized regret p95 (урок Slice A).
