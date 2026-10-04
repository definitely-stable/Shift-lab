# DELSK-000 — Программа Delsk: от prior art до решения о самостоятельной библиотеке

**Приоритет:** P0. **Статус:** PLANNED. **Владелец:** maintainers Shift-lab (исполнитель назначается при старте).

## Вопрос / результат

Получить воспроизводимый ответ, даёт ли Delsk практическое преимущество при выборе delta-base.

## Основа

[Документ](https://github.com/definitely-stable/Shift-lab/blob/main/.work/roadmap.md) · [Протокол DELSK-P1](https://github.com/definitely-stable/Shift-lab/blob/main/.work/protocol.md) · [Программа](https://github.com/definitely-stable/Shift-lab/blob/main/.work/README.md).

**Зависимости:** нет; готово к исследовательской подготовке.

## Шаги

- [ ] Вести последовательность G0–G5 и ссылки на дочерние задачи, не закрывать программу по одной проверке документации.
- [ ] Зафиксировать область claims: unit size, домены, codecs, tested architectures.
- [ ] Сохранить положительные, отрицательные и неопределённые результаты и принять go/pivot/stop.

## Acceptance / evidence

- [ ] Все обязательные gate issues имеют evidence либо объяснённый stop.
- [ ] Итоговый verdict пересчитывается из retained data и привязан к source/protocol SHA.
- [ ] Ни novelty, ни скорость Delsk не заявлены без фактических измерений.

## CI и ресурсы

Оркестрация: без отдельного compute; общий лимит experimental dispatch 600 runner-min/week. Все тесты и измерения — GitHub Actions. Published paper numbers и локальные прогоны не заменяют CI evidence.

## Завершение

В комментарии/связанном PR сохранить source/protocol/corpus hashes, run URL/attempt, компактные входы evaluator, coverage/exclusions, limitations и verdict `ACCEPT / REJECT / INCONCLUSIVE / INVALID`. До выполнения шагов результат остаётся **не проверен**. Отрицательный результат закрывает вопрос только с явным stop/pivot и следом evidence.

## Дочерние задачи

- [ ] [DELSK-001](https://github.com/definitely-stable/Shift-lab/issues/2) — Проверить claim matrix и воспроизводимость современного prior art
- [ ] [DELSK-002](https://github.com/definitely-stable/Shift-lab/issues/3) — Заморозить лицензированный corpus и lineage/candidate manifests
- [ ] [DELSK-003](https://github.com/definitely-stable/Shift-lab/issues/4) — Реализовать настоящий multi-base encoder oracle и метрики
- [ ] [DELSK-004](https://github.com/definitely-stable/Shift-lab/issues/5) — Воспроизвести дешёвые и современные baselines на общем oracle
- [ ] [DELSK-005](https://github.com/definitely-stable/Shift-lab/issues/6) — Построить ограниченный CI harness и долговечную evidence
- [ ] [DELSK-006](https://github.com/definitely-stable/Shift-lab/issues/7) — H1/H4/H10: проверить размер sketches, features и CDC dependence
- [ ] [DELSK-007](https://github.com/definitely-stable/Shift-lab/issues/8) — H2/H3: проверить направленность и codec-conditioned scoring
- [ ] [DELSK-008](https://github.com/definitely-stable/Shift-lab/issues/9) — H5: исследовать retrieval/index и реальную экономику памяти
- [ ] [DELSK-009](https://github.com/definitely-stable/Shift-lab/issues/10) — H6: no-delta abstention и adversarial negative controls
- [ ] [DELSK-010](https://github.com/definitely-stable/Shift-lab/issues/11) — H7: portable streaming reference, robustness и SIMD parity
- [ ] [DELSK-011](https://github.com/definitely-stable/Shift-lab/issues/12) — H8: условный tensor-aware model-weight профиль
- [ ] [DELSK-012](https://github.com/definitely-stable/Shift-lab/issues/13) — H9: интеграционный эксперимент с ChunkShift
- [ ] [DELSK-013](https://github.com/definitely-stable/Shift-lab/issues/14) — Принять итоговый go/pivot/stop и подготовить воспроизводимый artifact

DELSK-011 условная: отсутствие model-profile результата ограничивает claims, но не блокирует byte-oriented verdict.
