# DELSK-013 — Принять итоговый go/pivot/stop и подготовить воспроизводимый artifact

**Приоритет:** P2. **Статус:** PLANNED. **Владелец:** maintainers Shift-lab (исполнитель назначается при старте).

## Вопрос / результат

Достаточны ли evidence и преимущество для самостоятельной библиотеки Delsk?

## Основа

[Документ](https://github.com/definitely-stable/Shift-lab/blob/main/.work/protocol.md) · [Протокол DELSK-P1](https://github.com/definitely-stable/Shift-lab/blob/main/.work/protocol.md) · [Программа](https://github.com/definitely-stable/Shift-lab/blob/main/.work/README.md).

**Зависимости:** [DELSK-001](https://github.com/definitely-stable/Shift-lab/issues/2), [DELSK-004](https://github.com/definitely-stable/Shift-lab/issues/5), [DELSK-007](https://github.com/definitely-stable/Shift-lab/issues/8), [DELSK-008](https://github.com/definitely-stable/Shift-lab/issues/9), [DELSK-009](https://github.com/definitely-stable/Shift-lab/issues/10), [DELSK-010](https://github.com/definitely-stable/Shift-lab/issues/11), [DELSK-012](https://github.com/definitely-stable/Shift-lab/issues/13).

## Шаги

- [ ] Повторить literature delta search и актуализировать claim matrix.
- [ ] Оценить G0–G5 по frozen protocol, пересчитать retained evidence независимым evaluator.
- [ ] Составить per-domain/codec Pareto matrix quality/search/build/RAM с uncertainty.
- [ ] Выбрать standalone library, scoped profile/ChunkShift heuristic или stop; model claim только после DELSK-011.

## Acceptance / evidence

- [ ] Все заявленные gates имеют проверяемую evidence, не только green CI.
- [ ] Publication artifact включает recipe, licenses, hashes, raw compact rows, evaluator и limitations.
- [ ] Production API/wire freeze отложен до положительного scoped verdict; no result → no release.

## CI и ресурсы

Анализ retained данных≤5min; final confirmation≤95min если нет уже пригодного run. Все тесты и измерения — GitHub Actions. Published paper numbers и локальные прогоны не заменяют CI evidence.

## Завершение

В комментарии/связанном PR сохранить source/protocol/corpus hashes, run URL/attempt, компактные входы evaluator, coverage/exclusions, limitations и verdict `ACCEPT / REJECT / INCONCLUSIVE / INVALID`. До выполнения шагов результат остаётся **не проверен**. Отрицательный результат закрывает вопрос только с явным stop/pivot и следом evidence.

## Программа

[DELSK-000](https://github.com/definitely-stable/Shift-lab/issues/1) — общий прогресс и go/pivot/stop.
