# DELSK-010 — H7: portable streaming reference, robustness и SIMD parity

**Приоритет:** P1. **Статус:** PLANNED. **Владелец:** maintainers Shift-lab (исполнитель назначается при старте).

## Вопрос / результат

Можно ли сохранить точно одинаковые descriptor/score semantics во всех заявленных backends?

## Основа

[Документ](https://github.com/definitely-stable/Shift-lab/blob/main/.work/charter.md) · [Протокол DELSK-P1](https://github.com/definitely-stable/Shift-lab/blob/main/.work/protocol.md) · [Программа](https://github.com/definitely-stable/Shift-lab/blob/main/.work/README.md).

**Зависимости:** [DELSK-006](https://github.com/definitely-stable/Shift-lab/issues/7).

## Шаги

- [ ] Определить empty/short inputs, arithmetic overflow, endian, collisions, missing lanes и score ties.
- [ ] One-shot/stream partitions, serialize roundtrip, malformed input/fuzz и canonical vectors.
- [ ] Сначала x64/arm64 scalar, затем available SIMD; WASM execution correctness отдельно.
- [ ] Добавлять optimized backend только при measured benefit; unsupported ISA не эмулировать ради timing claims.

## Acceptance / evidence

- [ ] 100% совпадение executed golden/metamorphic cases, независимая проверка scalar reference.
- [ ] Mismatch делает run INVALID, vectors не перегенерированы ради зелёного CI.
- [ ] Поддержка заявлена только для реально выполненных targets; unsafe parsing limits описаны.

## CI и ресурсы

Portability/fuzz≤20min/platform; deterministic seeds/limits; никакого unlimited fuzz. Все тесты и измерения — GitHub Actions. Published paper numbers и локальные прогоны не заменяют CI evidence.

## Завершение

В комментарии/связанном PR сохранить source/protocol/corpus hashes, run URL/attempt, компактные входы evaluator, coverage/exclusions, limitations и verdict `ACCEPT / REJECT / INCONCLUSIVE / INVALID`. До выполнения шагов результат остаётся **не проверен**. Отрицательный результат закрывает вопрос только с явным stop/pivot и следом evidence.

## Программа

[DELSK-000](https://github.com/definitely-stable/Shift-lab/issues/1) — общий прогресс и go/pivot/stop.
