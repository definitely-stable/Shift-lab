# DELSK-012 — H9: интеграционный эксперимент с ChunkShift

**Приоритет:** P2. **Статус:** PLANNED. **Владелец:** maintainers Shift-lab (исполнитель назначается при старте).

## Вопрос / результат

Окупается ли descriptor/index в настоящем binary-update pipeline?

## Основа

[Документ](https://github.com/definitely-stable/Shift-lab/blob/main/.work/charter.md) · [Протокол DELSK-P1](https://github.com/definitely-stable/Shift-lab/blob/main/.work/protocol.md) · [Программа](https://github.com/definitely-stable/Shift-lab/blob/main/.work/README.md).

**Зависимости:** [DELSK-008](https://github.com/definitely-stable/Shift-lab/issues/9), [DELSK-009](https://github.com/definitely-stable/Shift-lab/issues/10), [DELSK-010](https://github.com/definitely-stable/Shift-lab/issues/11).

## Шаги

- [ ] Pinned consumer adapter к ChunkShift.Patching, без изменения CSM/CSP/content identity.
- [ ] Сравнить existing previous-base/size policy и Delsk advisory top K при одинаковых encoders.
- [ ] Измерить cold setup, amortized repeated queries, fetched base bytes, encode/decode и metadata.
- [ ] Ничего не публиковать в production packages по одному microbenchmark result.

## Acceptance / evidence

- [ ] Exact target reconstruction и неизменная compatibility всех consumer fixtures.
- [ ] Сохранён system break-even и paired CI evidence, G5 либо отрицательный результат.
- [ ] Scope доступных форматов/lineages/architectures обозначен; consumer не становится обязательной dependency core.

## CI и ресурсы

≤95runner-min/decision плюс independent confirmation; corpus per job≤2GiB. Все тесты и измерения — GitHub Actions. Published paper numbers и локальные прогоны не заменяют CI evidence.

## Завершение

В комментарии/связанном PR сохранить source/protocol/corpus hashes, run URL/attempt, компактные входы evaluator, coverage/exclusions, limitations и verdict `ACCEPT / REJECT / INCONCLUSIVE / INVALID`. До выполнения шагов результат остаётся **не проверен**. Отрицательный результат закрывает вопрос только с явным stop/pivot и следом evidence.

## Программа

[DELSK-000](https://github.com/definitely-stable/Shift-lab/issues/1) — общий прогресс и go/pivot/stop.
