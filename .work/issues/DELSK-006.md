# DELSK-006 — H1/H4/H10: проверить размер sketches, features и CDC dependence

**Приоритет:** P1. **Статус:** PLANNED. **Владелец:** maintainers Shift-lab (исполнитель назначается при старте).

## Вопрос / результат

Дают ли multi-scale, positions/order и CDC anchors выигрыш при том же byte budget?

## Основа

[Документ](https://github.com/definitely-stable/Shift-lab/blob/main/.work/hypotheses.md) · [Протокол DELSK-P1](https://github.com/definitely-stable/Shift-lab/blob/main/.work/protocol.md) · [Программа](https://github.com/definitely-stable/Shift-lab/blob/main/.work/README.md).

**Зависимости:** [DELSK-003](https://github.com/definitely-stable/Shift-lab/issues/4), [DELSK-004](https://github.com/definitely-stable/Shift-lab/issues/5).

## Шаги

- [ ] Scalar experimental representation без public format freeze; budgets64/128/256/512/1024B incl header.
- [ ] Nested и leave-one-out ablations: content→positions→order→entropy; raw/normalized positions.
- [ ] No-CDC vs pinned external FastCDC, одинаковый tuning budget; exact descriptor scan, K1/4/8/16.
- [ ] Зафиксировать primary contrasts и multiple-testing correction; оценить size strata и hard negatives.

## Acceptance / evidence

- [ ] Каждая feature имеет incremental quality/cost evidence и holdout lineage CI.
- [ ] G3 либо обоснованный inconclusive/reject; ≥20% p95 reduction или +2pp useful recall для сохранённой сложной feature.
- [ ] Если 512/1024B не дают headroom после фиксированного tuning budget, записан stop/pivot.
- [ ] Никакой SIMD до полезного scalar signal.

## CI и ресурсы

Pilot/decision shards по CI plan; максимум3 candidates/run, полный grid разбит заранее. Все тесты и измерения — GitHub Actions. Published paper numbers и локальные прогоны не заменяют CI evidence.

## Завершение

В комментарии/связанном PR сохранить source/protocol/corpus hashes, run URL/attempt, компактные входы evaluator, coverage/exclusions, limitations и verdict `ACCEPT / REJECT / INCONCLUSIVE / INVALID`. До выполнения шагов результат остаётся **не проверен**. Отрицательный результат закрывает вопрос только с явным stop/pivot и следом evidence.

## Программа

[DELSK-000](https://github.com/definitely-stable/Shift-lab/issues/1) — общий прогресс и go/pivot/stop.
