# DELSK-008 — H5: исследовать retrieval/index и реальную экономику памяти

**Приоритет:** P1. **Статус:** PLANNED. **Владелец:** maintainers Shift-lab (исполнитель назначается при старте).

## Вопрос / результат

Можно ли ускорить поиск, не потеряв лучшие базы до directional reranking?

## Основа

[Документ](https://github.com/definitely-stable/Shift-lab/blob/main/.work/protocol.md) · [Протокол DELSK-P1](https://github.com/definitely-stable/Shift-lab/blob/main/.work/protocol.md) · [Программа](https://github.com/definitely-stable/Shift-lab/blob/main/.work/README.md).

**Зависимости:** [DELSK-006](https://github.com/definitely-stable/Shift-lab/issues/7), [DELSK-007](https://github.com/definitely-stable/Shift-lab/issues/8).

## Шаги

- [ ] Exact descriptor scan upper reference; bounded inverted index, rare-feature weighting и posting caps.
- [ ] M32/64/128 при K1/4/8/16; отдельно retrieval recall и rerank recall.
- [ ] Index scales10k/100k, 1M только если pilot memory/time permits; IDs/postings/allocator included.
- [ ] Измерить build/query/RSS и end-to-end amortization; ANN только как отдельный justified baseline.

## Acceptance / evidence

- [ ] Caps/truncation rates и misses опубликованы; G3/G4 и no hidden budget advantage.
- [ ] 1M synthetic index timing явно отделён от natural-corpus quality oracle.
- [ ] Фактический encode-call reduction не подменён N/K или обещанием100×.

## CI и ресурсы

RAM process-tree4GiB, disk6GiB; ≤45min/job; max-parallel2. Все тесты и измерения — GitHub Actions. Published paper numbers и локальные прогоны не заменяют CI evidence.

## Завершение

В комментарии/связанном PR сохранить source/protocol/corpus hashes, run URL/attempt, компактные входы evaluator, coverage/exclusions, limitations и verdict `ACCEPT / REJECT / INCONCLUSIVE / INVALID`. До выполнения шагов результат остаётся **не проверен**. Отрицательный результат закрывает вопрос только с явным stop/pivot и следом evidence.

## Программа

[DELSK-000](https://github.com/definitely-stable/Shift-lab/issues/1) — общий прогресс и go/pivot/stop.
