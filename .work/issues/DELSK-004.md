# DELSK-004 — Воспроизвести дешёвые и современные baselines на общем oracle

**Приоритет:** P0. **Статус:** PLANNED. **Владелец:** maintainers Shift-lab (исполнитель назначается при старте).

## Вопрос / результат

Сколько headroom остаётся над сильными внешними методами при равных budgets?

## Основа

[Документ](https://github.com/definitely-stable/Shift-lab/blob/main/.work/corpus-and-baselines.md) · [Протокол DELSK-P1](https://github.com/definitely-stable/Shift-lab/blob/main/.work/protocol.md) · [Программа](https://github.com/definitely-stable/Shift-lab/blob/main/.work/README.md).

**Зависимости:** [DELSK-001](https://github.com/definitely-stable/Shift-lab/issues/2), [DELSK-003](https://github.com/definitely-stable/Shift-lab/issues/4).

## Шаги

- [ ] Реализовать random/size/recency, корректный MinHash/KMV, length+target-normalized containment, Finesse/N-transform.
- [ ] Приоритет BePro/Odess либо другой доступный современный author artifact; DeepSketch CPU inference только при reproducible model.
- [ ] Зафиксировать commits/licenses/build commands/tuning budgets и deviations от paper.
- [ ] Прогнать один и тот же C_t, K grid, descriptor cost и downstream codec; author settings и budget-matched settings отдельно.

## Acceptance / evidence

- [ ] Есть baseline table с raw rows и same-input comparisons.
- [ ] Не менее одного contemporary baseline воспроизведён для широкого G2 claim; иначе verdict ограничен.
- [ ] PROXY не носит имя официального алгоритма в chart; published paper numbers не смешаны с CI timings.
- [ ] Best baseline для primary contrast выбран только на calibration.

## CI и ресурсы

Не более 3 candidate methods в decision shard; CPU-only, ≤95 runner-min/run. Все тесты и измерения — GitHub Actions. Published paper numbers и локальные прогоны не заменяют CI evidence.

## Завершение

В комментарии/связанном PR сохранить source/protocol/corpus hashes, run URL/attempt, компактные входы evaluator, coverage/exclusions, limitations и verdict `ACCEPT / REJECT / INCONCLUSIVE / INVALID`. До выполнения шагов результат остаётся **не проверен**. Отрицательный результат закрывает вопрос только с явным stop/pivot и следом evidence.

## Программа

[DELSK-000](https://github.com/definitely-stable/Shift-lab/issues/1) — общий прогресс и go/pivot/stop.
