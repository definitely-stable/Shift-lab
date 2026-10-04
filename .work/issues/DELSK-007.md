# DELSK-007 — H2/H3: проверить направленность и codec-conditioned scoring

**Приоритет:** P1. **Статус:** PLANNED. **Владелец:** maintainers Shift-lab (исполнитель назначается при старте).

## Вопрос / результат

Есть ли signal сверх size/containment и работает ли общий descriptor для разных codecs?

## Основа

[Документ](https://github.com/definitely-stable/Shift-lab/blob/main/.work/protocol.md) · [Протокол DELSK-P1](https://github.com/definitely-stable/Shift-lab/blob/main/.work/protocol.md) · [Программа](https://github.com/definitely-stable/Shift-lab/blob/main/.work/README.md).

**Зависимости:** [DELSK-006](https://github.com/definitely-stable/Shift-lab/issues/7).

## Шаги

- [ ] Symmetric overlap vs length-only vs length+target-normalized containment vs full directional scoring при неизменном descriptor budget.
- [ ] A→B/B→A diagnostic отдельно от temporal production universe.
- [ ] Shared scorer vs per-codec scorers vs codec-specific representation на двух generic codecs.
- [ ] Freeze calibration params и score ties; XOR symmetry не объявлять доказательством directional benefit.

## Acceptance / evidence

- [ ] H2/H3 приняты, отвергнуты или ограничены с paired held-out evidence.
- [ ] Улучшение не объясняется только дополнительными bytes/features или большим candidate budget.
- [ ] Codec options и scorer hashes задокументированы; отсутствие transfer приводит к узкому profile claim.

## CI и ресурсы

CPU-only, ≤95 runner-min/decision, затем отдельный confirmation run. Все тесты и измерения — GitHub Actions. Published paper numbers и локальные прогоны не заменяют CI evidence.

## Завершение

В комментарии/связанном PR сохранить source/protocol/corpus hashes, run URL/attempt, компактные входы evaluator, coverage/exclusions, limitations и verdict `ACCEPT / REJECT / INCONCLUSIVE / INVALID`. До выполнения шагов результат остаётся **не проверен**. Отрицательный результат закрывает вопрос только с явным stop/pivot и следом evidence.

## Программа

[DELSK-000](https://github.com/definitely-stable/Shift-lab/issues/1) — общий прогресс и go/pivot/stop.
