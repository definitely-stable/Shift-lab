# Delsk simple selector `delsk.simple-selector.v1`

Статус: **ADOPTED** (решение maintainer 2026-10-06, [decision record](../decisions/2026-10-06-pivot-simple-selector.md)). Реализация-эталон: [simple_selector.py](../tools/simple_selector.py), тесты: [test_simple_selector.py](../tests/test_simple_selector.py). Оценка на development-данных: [dev-eval.json](dev-eval.json).

Selector выбирает K баз для delta-кодирования target из множества кандидатов `C_t`. Он заменяет программу compact learned descriptor: два screening (Slice A, X0) не нашли headroom, который такой descriptor мог бы закрыть.

## 1. Входы

| Что | Для каждого объекта | Обязательно |
|---|---|---|
| Descriptor | 64 B: 8 наименьших различных splitmix64-хэшей 8-байтовых shingles, seed 20261006, по возрастанию (`descriptor`) | да |
| Размер | длина в bytes | да |
| Логический путь | путь в дереве или имя установленного файла | нет |
| Линия релизов | ветка или линия версий (`3.0`, `stable`); при одной линии — id проекта | нет |
| Порядок версий | целое: позднее = больше, внутри линии | нет, если пути нет |
| Offset | смещение chunk внутри файла | только для chunks |

Объект короче 8 bytes даёт один shingle из всего содержимого. Пустой объект даёт пустой descriptor. Descriptor — не content identity и не authentication: совпадение descriptors ничего не доказывает.

## 2. Порядок

```text
meta(t)    = базы с path(b) = path(t) и line(b) = line(t),
             по (|offset_b − offset_t|, −version_b, |size_b − size_t|, object_id); пусто, если path(t) неизвестен
content(t) = все базы по (−resemblance(t, b), |size_b − size_t|, object_id),
             resemblance = доля общих среди 8 наименьших хэшей объединения двух descriptors
order(t)   = meta[0], content[0], meta[1], content[1], … без повторов
select(t)  = первые K элементов order(t)
```

При K = 1 выбирается лучший metadata-кандидат, а без метаданных — лучший по содержимому. При K = 2 кодируются оба. Ties детерминированы. `order(t)` содержит весь `C_t`, поэтому K = |C_t| — исчерпывающий перебор.

## 3. Использование результата

Каждую выбранную базу нужно реально закодировать, раскодировать и сверить с target. Из закодированных вариантов и standalone-представления берётся самый дешёвый. Standalone остаётся всегда допустимым fallback, поэтому selector не может ухудшить корректность, только экономию. **По умолчанию K = 2.** K = 4 — если важнее bytes, чем CPU кодера.

## 4. Качество на development-данных (in-sample)

Пересчёт из retained oracle rows и rankings, без новых прогонов: `python3 .work/tools/simple_selector.py evaluate`. Правило выбрано **после** просмотра этих же данных, поэтому числа in-sample. Они показывают, что selector не хуже лучших компонентов, но не являются held-out claim.

| Population | targets (useful) | SC@1 | SC@2 | SC@4 | UR@2 | calls ÷ при K=2 |
|---|---|---|---|---|---|---|
| pilot-v1 development | 43 (37) | 0.994 | 1.000 | 1.000 | 1.000 | 18.9 |
| pilot-v1 calibration | 12 (10) | 1.000 | 1.000 | 1.000 | 1.000 | 10.5 |
| X0 H1-file (ветки вперемешку) | 16 (16) | 0.997 | 1.000 | 1.000 | 1.000 | 10.4 |
| X0 H1-cdc | 16 (15) | 1.000 | 1.000 | 1.000 | 1.000 | 20.9 |
| X0 H4-file (бинарники) | 16 (10) | 1.000 | 1.000 | 1.000 | 1.000 | 12.7 |
| X0 H4-cdc | 16 (5) | 0.857 | 0.958 | 1.000 | 0.800 | 13.5 |

SC — SavingsCapture, UR — Useful Recall. «calls ÷» — во сколько раз меньше вызовов кодера, чем при исчерпывающем переборе `C_t`. Слабое место — chunks бинарников при K ≤ 2. Там 5 useful targets, вывод неустойчив.

## 5. Ограничения

- Development evidence remains in-sample/burned. S4-D improved real ChunkShift bytes but still used development+calibration/X0. The pre-existing sealed E1 evaluation lineage (`bzip2`) remained unopened and is reserved for S4-C holdout confirmation.
- Один кодер (xdelta3 `-9`, standalone `zstd -19`), `C_t` ≤ 64 кандидатов. Масштаб каталога (тысячи–миллионы объектов) не проверялся: content-order здесь — exact scan по 64 B.
- Python-эталон описывает semantics, а не скорость. Portable native реализация и parity-тесты — отдельный шаг.

## 6. Что дальше

1. **S2 · стоимость в системе** (бывшая DELSK-008, перенацелена): Rust-прототип с parity к этому эталону, индекс `path → объекты` и inverted index по хэшам с cap против exact scan на каталогах 10⁴–10⁶ объектов — [s2.md](s2.md); **RUN** ([результаты](results-s2.md)): на 10⁶ объектов запрос p95 16.7 µs, top-2 совпадает с полным перебором, ≈ 41 B индекса на объект.
2. **S3 · fallback и негативные случаи** (DELSK-009): когда selector не должен кодировать delta (сжатые и случайные данные), и экономия CPU ценой потерянных bytes — [s3.md](s3.md); **RUN** ([результаты](results-s3.md)): preregistered правило выбрало `L = 0` — отказ по 64 B descriptor теряет useful delta сжатых архивов, поэтому selector кодирует всегда.
3. **S4-D · интеграция с ChunkShift** (DELSK-012): [development screen](s4.md) **COMPLETE / `OPEN_CONFIRMATION_K2`**; [retained evidence](../results/SELECTOR-S4/README.md): 3,815 rows, 0 failures, K2 saves 1.0568% physical CSP bytes vs `previous1` and is only 1,913 bytes above exhaustive.
4. **S4-C · sealed holdout confirmation**: [frozen protocol](s4-confirmation.md), **NOT_RUN**. K=2 fixed; evaluation split `bzip2` only; Rust selector is authoritative; two independent hosted repeats. A PASS closes only scoped ChunkShift G5, not a universal standalone-library claim.
