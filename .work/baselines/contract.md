# DELSK-004 Slice A: дешёвые baselines на общем oracle

Статус: **IMPLEMENTED, NOT_RUN**. Контракт `delsk.baselines.slice-a.v1`; параметры — [params.json](params.json) (SHA-256 параметров записывается в каждый результат). Issue: [DELSK-004](https://github.com/definitely-stable/Shift-lab/issues/5). Основа: [протокол DELSK-P1](../protocol.md) §2–§4, [corpus и baselines](../corpus-and-baselines.md), [prior art update](../research/DELSK-PRIOR-ART-UPDATE-2026-10.md) §3. Oracle: retained bundles `delsk.oracle-contract.v4` с G1 PASS (`.work/results/ORACLE-G1-V4/`, [журнал](../oracle/activation-v4-log.md)).

## 1. Что измеряется

Качество выбора баз из frozen `C_t`. Oracle исчерпывающий: `D_E(b,t)` известен для каждой пары, поэтому выбранные базы не кодируются заново. Для ranking `R` и `K`: `A_K(t) = min(S(t), min D_E(b,t) по первым K базам R)`, как в протоколе §2. Метрики — протокол §3, без изменений определений:

- Strict, Useful и ε Recall@K (ε = 1/2/5 %, floor 64 B). Strict и Useful берут множество ties oracle.
- Byte regret и normalized regret (floor 64 B), p50 и p95 по Hyndman–Fan type 7.
- SavingsCapture `Σ(S−A)/Σ(S−O)`; при нулевом знаменателе — `N/A`.
- Encoder-call reduction `Σ|C_t| / Σ min(K, |C_t|)`.
- Macro по lineage (`family_id`).
- Cluster bootstrap по lineages: 10 000 draws, seed 20261004, 95 % интервал для SavingsCapture и Useful Recall.

K grid: 1, 4, 8, 16. Цифры paper и CI timings не смешиваются: время в этом срезе — только CPU построения дескрипторов, для информации.

## 2. Population

- Только splits `development` и `calibration`, только `near_duplicate` targets (55 targets, 1855 пар на pilot).
- Identity-only targets — dedup branch, в recall не входят.
- `evaluation` split sealed: его targets не читаются, не ранжируются и не оцениваются. Его строки oracle sealed, и он открывается один раз для финалиста (протокол §4).
- Каждый ranking — перестановка всего `C_t`. Population каждой группы (метод, budget, K, split) обязана быть полной, иначе прогон падает.
- Оценщик сверяет минимум `D_E`, `O(t)` и множество ties с target-строками oracle (fail closed).

## 3. Методы

Все методы видят один и тот же `C_t` и одинаковые метаданные: размер, порядок релиза, `member_path` и `offset`. Категория кандидата из candidate lock им недоступна: это разметка построения, а не знание deployment.

| Метод | Provenance | Правило |
|---|---|---|
| `random` | — | порядок по SHA-256(`seed:target:base`), seed 20261006 |
| `size_closest` | — | `|len(b) − len(t)|` по возрастанию |
| `previous_version` | — | сначала базы с тем же `member_path` (ближайший `offset`, затем последний более ранний релиз), потом size-closest; у whole-archive tracks пути нет |
| `git_like` | **PROXY** | сначала базы с тем же git name-hash v1 пути, затем size-closest; это не `git pack-objects` (окно и порядок типов git не воспроизводятся) |
| `minhash_resemblance` | **REIMPLEMENTED** (bottom-k MinHash) | Jaccard по bottom-k 8-байтовых shingles (splitmix64), budgets 64/128/256/512/1024 B = k 8…128 хэшей по 8 B |
| `containment` | **REIMPLEMENTED** | target-normalized containment `|S_t∩S_b|/|S_t|` из Jaccard и KMV-оценок мощностей при том же budget; это и есть baseline «length + target-normalized containment» |

Bottom-k sketches вложены: первые k' значений — это bottom-k' sketch. Поэтому один проход по bytes даёт все budgets. Равные ties ломаются детерминированно: size gap, затем `object_id`.

## 4. Выбор baseline для primary contrast

Сильнейший baseline выбирается **только на calibration**: максимальный SavingsCapture при K = 8, при равенстве — меньший descriptor budget, затем имя метода. Выбор записывается в `summary.json` (`best_on_calibration`).

## 5. Запуск и evidence

Workflow `delsk-baselines.yml` запускается только вручную (dispatch на `main`):

1. Admission по runner-minute ledger.
2. Materialization pinned natural store (тот же код и проверки, что у oracle pilot).
3. `baselines.py rank`, затем `baselines.py evaluate` против retained oracle bundle (`37434946174-1`; `D_E` двух G1-прогонов совпадают).
4. Upload `rankings.jsonl`, `costs.json`, `rows.jsonl`, `summary.json` под artifact cap.

Natural bytes и descriptors в artifact не попадают. Результат становится evidence только после retained-импорта в отдельном PR.

## 6. Ограничения и что дальше

- Pilot — шесть lineages, calibration — одна lineage: любой вывод exploratory (протокол §5). Confirmatory G2 требует расширения корпуса.
- Методы, отложенные в следующие срезы (prior art §3, п. 3–6):
  - Odd Sketch / SetSketch и FracMinHash;
  - TLSH, ssdeep, LZJD;
  - trial-encode proxy;
  - Finesse и Odess (REIMPLEMENTED);
  - BePro и SpeedSketch после license review.
- Exact-scan Jaccard (полные множества shingles) не входит: память на объектах до 11 MB. Это кандидат следующего среза.
- Отсутствующий baseline не превращается в победу Delsk.
