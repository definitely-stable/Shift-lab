# DELSK-011 — H8: условный tensor-aware model-weight профиль

**Приоритет:** P2. **Статус:** PLANNED. **Владелец:** maintainers Shift-lab (исполнитель назначается при старте).

## Вопрос / результат

Даёт ли структура tensor/bit planes преимущество, оправдывающее специализацию?

## Основа

[Документ](https://github.com/definitely-stable/Shift-lab/blob/main/.work/corpus-and-baselines.md) · [Протокол DELSK-P1](https://github.com/definitely-stable/Shift-lab/blob/main/.work/protocol.md) · [Программа](https://github.com/definitely-stable/Shift-lab/blob/main/.work/README.md).

**Зависимости:** [DELSK-002](https://github.com/definitely-stable/Shift-lab/issues/3), [DELSK-007](https://github.com/definitely-stable/Shift-lab/issues/8).

## Шаги

- [ ] Найти лицензированные revision-pinned base/fine-tune families и ancestor-heldout split.
- [ ] Сравнить generic descriptor, aligned XOR+lossless и faithful BitX artifact если воспроизводим.
- [ ] Учитывать mapping/dtype/shape/metadata; BF16 поддержка ZipLLM не означает все formats.
- [ ] Negative cases: quantization/layout changes, unrelated models; synthetic отдельно.

## Acceptance / evidence

- [ ] Достаточно независимых real model families либо результат только exploratory.
- [ ] ≥3pp useful recall или≥20% regret gain при тех же budgets и учтённой metadata.
- [ ] Нет заявления model support по одним synthetic tensors; conditional scope отражён в G5.

## CI и ресурсы

CPU tensor slices≤2GiB/job,≤45min; GPU training не входит в бюджет. Все тесты и измерения — GitHub Actions. Published paper numbers и локальные прогоны не заменяют CI evidence.

## Завершение

В комментарии/связанном PR сохранить source/protocol/corpus hashes, run URL/attempt, компактные входы evaluator, coverage/exclusions, limitations и verdict `ACCEPT / REJECT / INCONCLUSIVE / INVALID`. До выполнения шагов результат остаётся **не проверен**. Отрицательный результат закрывает вопрос только с явным stop/pivot и следом evidence.

## Программа

[DELSK-000](https://github.com/definitely-stable/Shift-lab/issues/1) — общий прогресс и go/pivot/stop.
