# DELSK-009 — H6: no-delta abstention и adversarial negative controls

**Приоритет:** P1. **Статус:** PLANNED. **Владелец:** maintainers Shift-lab (исполнитель назначается при старте).

## Вопрос / результат

Уменьшает ли отказ от delta compute cost без заметной потери полезной экономии?

## Основа

[Документ](https://github.com/definitely-stable/Shift-lab/blob/main/.work/hypotheses.md) · [Протокол DELSK-P1](https://github.com/definitely-stable/Shift-lab/blob/main/.work/protocol.md) · [Программа](https://github.com/definitely-stable/Shift-lab/blob/main/.work/README.md).

**Зависимости:** [DELSK-006](https://github.com/definitely-stable/Shift-lab/issues/7).

## Шаги

- [ ] Always-encode vs simple entropy/size filter vs calibrated abstention.
- [ ] Random/recompressed/encrypted-like/periodic/containment и near-threshold cases.
- [ ] Зафиксировать useful-delta threshold и false-negative cost; учитывать потерянные bytes, а не только labels.
- [ ] Bounded postings/candidate policy с fallback при exhaustion; восстановление target остаётся exact.

## Acceptance / evidence

- [ ] Useful-delta FNR≤1% с95%CI либо policy не принята.
- [ ] SavingsCapture/CPU tradeoff лучше simple control, thresholds выбраны без holdout tuning.
- [ ] False positives и metadata cost учтены; hard negatives не исключены после scoring.

## CI и ресурсы

Pilot30min, decision≤95min; большие adversarial expansion запрещены caps. Все тесты и измерения — GitHub Actions. Published paper numbers и локальные прогоны не заменяют CI evidence.

## Завершение

В комментарии/связанном PR сохранить source/protocol/corpus hashes, run URL/attempt, компактные входы evaluator, coverage/exclusions, limitations и verdict `ACCEPT / REJECT / INCONCLUSIVE / INVALID`. До выполнения шагов результат остаётся **не проверен**. Отрицательный результат закрывает вопрос только с явным stop/pivot и следом evidence.

## Программа

[DELSK-000](https://github.com/definitely-stable/Shift-lab/issues/1) — общий прогресс и go/pivot/stop.
