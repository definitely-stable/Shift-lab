# Решение DELSK-000: pivot к простому selector (2026-10-06)

**Решение maintainer:** вариант 1 из трёх предложенных («простой селектор»), 2026-10-06. Альтернативы — новый screening непроверенных классов и остановка программы — отклонены.

## Основание

Протокол DELSK-P1 §6: «G2 не показывает выигрыш даже у 512/1024 B после замороженного tuning budget → сохранить negative evidence и pivot к простому selector». Evidence:

| Эксперимент | Итог |
|---|---|
| G1 oracle, contract v4 ([журнал](../oracle/activation-v4-log.md)) | **PASS**: oracle воспроизводим и полон |
| DELSK-004 Slice A ([результаты](../baselines/results-slice-a.md)) | pilot-v1 насыщен: `previous_version` и MinHash 1024 B — SavingsCapture 1.000 при K = 1; G2 `INCONCLUSIVE` |
| DELSK-002 X0 ([результаты](../corpus/x0/results.md)) | preregistered screening трудных классов: `NO_HEADROOM_AT_256`; MinHash 64 B и `version_previous` насыщают все ячейки |

Charter: «Отдельная библиотека оправдана только устойчивым Pareto advantage… Первый результат программы может быть … полезная эвристика внутри ChunkShift либо отрицательный результат». Pareto advantage сложного descriptor не найден. Найдена дешёвая эвристика, близкая к oracle.

## Что меняется

| Направление | Статус |
|---|---|
| H1, H4, H10 (DELSK-006): размер sketches, positions, CDC features | **STOPPED**: negative evidence; 64 B MinHash уже насыщает проверенные классы |
| H2, H3 (DELSK-007): directional и codec-conditioned scorer | **STOPPED**: нечего улучшать при SC ≈ 1.0 у дешёвых методов |
| H8 (DELSK-011): tensor-aware профиль | **PARKED**: нет данных и сигнала |
| H5 (DELSK-008): retrieval и экономика памяти | **RESCOPED** → S2: стоимость простого selector на большом каталоге |
| H6 (DELSK-009): abstention и negative controls | **CONTINUES** → S3 |
| H7 (DELSK-010): portable deterministic reference | **RESCOPED**: parity только для 64 B descriptor и порядка selector |
| H9 (DELSK-012): интеграция с ChunkShift | **CONTINUES** → S4 |
| DELSK-013: итоговый go/pivot/stop | остаётся; этот документ — промежуточное решение pivot |

Принятый selector — [`delsk.simple-selector.v1`](../selector/README.md). Frozen контракты (oracle v1–v4, E0/E1, Slice A, X0) и их evidence не меняются. Negative evidence остаётся в репозитории.

## Чего это решение не утверждает

- Что compact learned descriptor не может выиграть на непроверенных классах: архивах, containers, tabular, models, переименованиях. Они не измерялись.
- Что selector подтверждён на held-out: его оценка in-sample.
- Что отдельная библиотека Delsk оправдана. Пока это эвристика для потребителя (ChunkShift), а не публичный формат.
