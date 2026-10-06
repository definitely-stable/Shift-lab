# DELSK-002 X0: результаты screening

Run [37449333091](https://github.com/definitely-stable/Shift-lab/actions/runs/37449333091), attempt 1. Source и workflow — `1a1efaa34b83ea5ee59fd816cdd33b2a96e73f4a` (merge PR [#45](https://github.com/definitely-stable/Shift-lab/pull/45)). Artifact digest — `sha256:9c4e6d74dd433f6e9e9bf5508c6942d2b6a193f96915e193422ff43d721fd006`, совпадает с тем, что сообщает GitHub. Retained файлы лежат в [`.work/results/DELSK-002-X0/37449333091-1/`](../../results/DELSK-002-X0/37449333091-1/), их SHA-256 — в [`37449333091-1.sha256`](../../results/DELSK-002-X0/37449333091-1.sha256). Правила — [README](README.md), параметры — [params.json](params.json).

**Verdict по preregistered rule (§6): `NO_HEADROOM_AT_256`.** Ни одна ячейка не `HARD` ни при одном budget. Это negative evidence для гипотезы, что на этих классах есть место для selector лучше дешёвых методов. Метка всех чисел — `SCREENING`: это не G1/G2 evidence.

## Проверки

- Admission: `admitted`, учёт полный. Codec conformance C01–C14: `PASS` на тех же executables.
- Acquisition: 48 archives, 162 828 008 B. Materialized: 227 624 280 B, 5 685 occurrences. Exclusions вне правил путей нет.
- Population: 4 ячейки по 16 near targets, 1 841 пара. Все пары `ok`: timeouts и decode mismatch нет. Compute cap не сработал (2.55 GB из 4 GiB).
- `candidates.json` совпадает с локальным dry-run до запуска: тот же `C_t` при независимом скачивании.
- `rows.jsonl`, `summary.jsonl` и `decision.json` пересчитываются из retained `pairs`, `targets` и `rankings` байт в байт на Python 3.12 (как в CI). На Python 3.11 `rows` и `decision` совпадают, а 13 macro-средних в `summary` отличаются в последнем знаке: в 3.12 `sum()` для float компенсированный. Тест это учитывает (см. `test_x0.py`).

## Главная таблица (K = 1)

SC — SavingsCapture, UR — Useful Recall@1. Полные строки (K = 1/4/8/16, все budgets, ε-recall, regret, bootstrap) — в `summary.jsonl`.

| Ячейка | useful / targets (families) | `previous_version` | `version_previous` | MinHash 64 B | containment 64 B | лучший SC |
|---|---|---|---|---|---|---|
| H1-file | 16/16 (6) | SC 0.947, UR 0.81 | 0.997, 0.94 | 0.999, 0.94 | 0.999, 0.94 | 0.9993 |
| H1-cdc | 15/16 (6) | 0.900, 0.80 | 0.981, 0.93 | **1.000, 1.00** | 0.977, 0.93 | 1.0000 |
| H4-file | 10/16 (4) | **1.000, 1.00** | 1.000, 1.00 | 1.000, 0.90 | 0.960, 0.70 | 1.0000 |
| H4-cdc | 5/16 (3) | 0.857, 0.60 | 0.857, 0.60 | 0.958, 0.80 | 0.958, 0.80 | 0.9576 при ≤ 256 B; 1.000 при 512 B |

Decision по ячейкам (оба lane, budgets 64–1024 B): headroom ≤ 0.0007 у H1-file, 0 у H1-cdc и H4-file. У H4-cdc headroom 0.042 при budget ≤ 256 B, но там 5 useful targets при минимуме 8, поэтому ячейка не `HARD`. При 512 B headroom 0.

## Что это значит

1. **Гипотеза H1 подтвердилась только для наивных метаданных.** Чередование веток действительно ломает `previous_version`: SC 0.947 и p95 normalized regret 28.6 на файлах, SC 0.900 на CDC. Но знание ветки (`version_previous`) и любой content-метод уже на 64 B возвращают SC ≥ 0.98–1.00. Трудность снимается дешёвыми средствами.
2. **Бинарники (H4) мало дают delta.** Только 10 из 16 файловых targets и 5 из 16 CDC-chunks имеют delta лучше standalone `zstd -19`. Экономия oracle на файлах — 28 % bytes (20.9 → 15.2 MB). Там, где delta полезна, `previous_version` и MinHash 64 B её находят.
3. **CDC без путей (L-blind) не трудна.** На H1-cdc MinHash 64 B даёт SC 1.000.
4. **Единственный сигнал** — H4-cdc при budget ≤ 256 B: 4.2 pp ниже oracle, CI [0.81, 1.00]. Но 5 useful targets из 3 families — меньше порога, и интервал широкий. По правилу это не `HARD`. Задним числом порог не меняется.

По протоколу (§6) и README (§6): если ни одна ячейка не `HARD` при 256 B, это довод за pivot к простому selector. Вывод записан. Решение о pivot принимает программа (DELSK-000), не этот screening.

## Ограничения

- Exploratory: 12 families, 16 targets на ячейку, одна split. Classes вне X0 (renames, архивы, containers, tabular, models) не проверены. Отсутствие headroom здесь не доказывает его отсутствие везде.
- Codec один (xdelta3 `-9`, standalone `zstd -19`). Для другого кодера лучшая база может быть другой.
- Rust-бинарники делят код toolchain. Это может облегчать задачу foreign decoys, но не затрагивает вывод о same-family выборе.
- Budgets ≤ 1024 B и K ≤ 16 — как в Slice A. Методы дороже MinHash (TLSH, Finesse, trial-encode) не запускались: они не нужны, если и MinHash 64 B насыщает ячейку.
