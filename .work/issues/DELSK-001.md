# DELSK-001 — Проверить claim matrix и воспроизводимость современного prior art

**Приоритет:** P0. **Статус:** PLANNED. **Владелец:** maintainers Shift-lab (исполнитель назначается при старте).

## Вопрос / результат

Есть ли вклад сверх encoder-aware DeepSketch, hierarchical Palantir и современных feature methods?

## Основа

[Документ](https://github.com/definitely-stable/Shift-lab/blob/main/.work/research/literature-review.md) · [Протокол DELSK-P1](https://github.com/definitely-stable/Shift-lab/blob/main/.work/protocol.md) · [Программа](https://github.com/definitely-stable/Shift-lab/blob/main/.work/README.md).

**Зависимости:** нет; готово к исследовательской подготовке.

## Шаги

- [ ] Составить section-level matrix: objective, directionality, codec conditioning, descriptor/index budgets, oracle, cross-domain, portability.
- [ ] Дочитать Argus, SpeedSketch, BePro, Odess journal и rolling-hash reuse при доступе; недоступность явно пометить.
- [ ] Проверить author code/license/data для Finesse, DeepSketch, BePro и современных alternatives; отдельно учесть Sonic closed artifact, WideCDC FAST27 prepublication и ZipLLM BF16.
- [ ] Отделить технический prior art от юридических patent/FTO conclusions; обновить литературу перед итоговым verdict.

## Acceptance / evidence

- [ ] Каждый центральный claim имеет primary URL и section/ограничение доступа.
- [ ] Matrix не объявляет actual patch objective и containment новыми сами по себе.
- [ ] Реализации разделены AUTHOR/REIMPLEMENTED/PROXY/UNAVAILABLE; scope comparison честный.

## CI и ресурсы

Чтение источников; benchmark compute не требуется. Все тесты и измерения — GitHub Actions. Published paper numbers и локальные прогоны не заменяют CI evidence.

## Завершение

В комментарии/связанном PR сохранить source/protocol/corpus hashes, run URL/attempt, компактные входы evaluator, coverage/exclusions, limitations и verdict `ACCEPT / REJECT / INCONCLUSIVE / INVALID`. До выполнения шагов результат остаётся **не проверен**. Отрицательный результат закрывает вопрос только с явным stop/pivot и следом evidence.

## Программа

[DELSK-000](https://github.com/definitely-stable/Shift-lab/issues/1) — общий прогресс и go/pivot/stop.
