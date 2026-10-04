# DELSK-003 — Реализовать настоящий multi-base encoder oracle и метрики

**Приоритет:** P0. **Статус:** PLANNED. **Владелец:** maintainers Shift-lab (исполнитель назначается при старте).

## Вопрос / результат

Какова достижимая экономия выбора базы в фиксированном C_t для конкретного кодера?

## Основа

[Документ](https://github.com/definitely-stable/Shift-lab/blob/main/.work/protocol.md) · [Протокол DELSK-P1](https://github.com/definitely-stable/Shift-lab/blob/main/.work/protocol.md) · [Программа](https://github.com/definitely-stable/Shift-lab/blob/main/.work/README.md).

**Зависимости:** [DELSK-002](https://github.com/definitely-stable/Shift-lab/issues/3), [DELSK-005](https://github.com/definitely-stable/Shift-lab/issues/6).

## Шаги

- [ ] Pinned xdelta3 + одинаковый standalone/framing baseline; перечислить все ordered pairs.
- [ ] Для каждой пары encode→decode→exact target equality; сохранить total/payload bytes и failures.
- [ ] Реализовать tie-aware recall, ε recall, byte/normalized regret, savings capture и candidate-call reduction по DELSK-P1.
- [ ] Добавить known-answer CI cases: tied bases, empty pool/target, no useful delta, incomplete pair coverage, timeout, mismatch.
- [ ] Второй codec подключить с отдельными options hashes; не объявлять oracle глобально оптимальной delta.

## Acceptance / evidence

- [ ] Все expected пары учтены; decode mismatch делает run INVALID.
- [ ] Ties и no-delta fallback корректны; zero denominator даёт N/A.
- [ ] Metric evaluator пересчитывается по retained rows; measured source и evaluator SHA разделены.
- [ ] Ни sampled universe, ни ChunkShift whole-base match oracle не названы полным catalog oracle.

## Staging внутри R1

- **Slice A — oracle contract (этот этап).** Узкий frozen sub-contract `delsk.oracle-contract.v1` ([contract](../oracle/contract.md), [freeze](../oracle/freeze.json)): primary codec xdelta3 3.2.1 и standalone zstd 1.5.7 с exact source/build/options lock, frame v1 cost accounting, pair universe 1 961 pairs/codec из sealed E1, correctness и failure semantics, oracle и tie semantics, evaluator с точными denominators, closed schemas, known-answer vectors K01–K42/G01–G09, mutants M01–M30, sealing evaluation split и CI plan. Natural oracle не запускался. DELSK-P1 остаётся `PLANNED`.
- **Slice B — implementation без natural data.** Сборка и conformance codecs, runner, независимый evaluator, KAT/mutant/fault-injection tests, PR smoke lane ([contract §15](../oracle/contract.md#15-следующий-slice-b-implementation-без-natural-data)).
- **Slice C — pilot oracle и независимый повтор.** Только после отдельного подтверждения maintainer; G1 по [contract §7](../oracle/contract.md#7-run-status-и-g1).

## CI и ресурсы

Pilot ≤4096 pairs/codec/30min; decision shards≤20k pairs/codec/45min/job. Все тесты и измерения — GitHub Actions. Published paper numbers и локальные прогоны не заменяют CI evidence.

## Завершение

В комментарии/связанном PR сохранить source/protocol/corpus hashes, run URL/attempt, компактные входы evaluator, coverage/exclusions, limitations и verdict `ACCEPT / REJECT / INCONCLUSIVE / INVALID`. До выполнения шагов результат остаётся **не проверен**. Отрицательный результат закрывает вопрос только с явным stop/pivot и следом evidence.

## Программа

[DELSK-000](https://github.com/definitely-stable/Shift-lab/issues/1) — общий прогресс и go/pivot/stop.
