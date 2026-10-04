# DELSK-002 — Заморозить лицензированный corpus и lineage/candidate manifests

**Приоритет:** P0. **Статус:** R0 COMPLETE (EXPLORATORY). **Владелец:** maintainers Shift-lab.

## Вопрос / результат

Можно ли получить репрезентативную, ограниченную и независимую выборку без leakage?

## Основа

[Документ](https://github.com/definitely-stable/Shift-lab/blob/main/.work/corpus-and-baselines.md) · [Протокол DELSK-P1](https://github.com/definitely-stable/Shift-lab/blob/main/.work/protocol.md) · [Программа](https://github.com/definitely-stable/Shift-lab/blob/main/.work/README.md).

**Зависимости:** нет. R0 exploratory corpus/candidate foundation завершён; confirmatory expansion остаётся отдельным последующим acquisition budget.

Milestone Slice D: acquisition exploratory pilot заморожена в [pilot-v1](../corpus/pilot-v1/README.md): source/corpus locks, snapshot license review, две независимые совпавшие materializations в Actions и offline integrity checks. Полный metadata universe сохранён в git в compressed lock. Milestone Slice E0: candidate construction design принят в [e0](../corpus/e0/construction-spec.md) — решения A01–A10, закрытая candidate-lock v2 schema, golden vectors, ancestry audit всех 15 пар на acquired snapshots и historical-byte scope. Milestone Slice E1: `C_t` запечатан в [e1](../corpus/e1/README.md) — candidate lock v2 (64 near и 15 identity queries, 1 961 pairs/codec), независимый verifier source→U и U→queries, 56 adversarial cases и 18 properties в CI, два Actions runs с одинаковым lock при разных порядках итерации. Milestone Slice F завершён: два независимых `foundation-handoff` run (`37210886381`, `37210930669`) на merged SHA дали byte-identical semantic handoff (`3157c401…`), retained bundles сохранены, R0 gate = `READY`. Confirmatory sufficiency по-прежнему не установлена и не является условием exploratory R0.

## Шаги

- [x] Выбрать source/binary/archive families и synthetic diagnostics; model/OCI deferred до отдельного license/acquisition budget.
- [x] Создать version-pinned source manifest, checksums, transforms и лицензии; materialization с archive traversal/expansion caps.
- [x] Разделить development/calibration/evaluation по ancestor lineage, сохраняя transformed variants вместе.
- [x] Зафиксировать каждый C_t до scoring: temporal eligibility, related/decoy/negative bases, duplicates/exclusions, sorted IDs.
- [x] Показать coverage и число независимых held-out lineages, deferred domains и причины.

## Acceptance / evidence

- [x] CI materializes один lock дважды с одинаковыми IDs и hashes.
- [x] Нет пересечения lineage между splits; self/exact duplicates отдельно.
- [x] Pilot ≤256 MiB acquired/1 GiB materialized и ≤4096 ordered pairs/codec.
- [x] Для confirmatory domain ≥10 held-out lineages либо явно exploratory статус — текущий R0 явно exploratory.

## CI и ресурсы

Pilot x64 ≤30 min; shard≤2GiB позже по утверждённому lock. Все тесты и измерения — GitHub Actions. Published paper numbers и локальные прогоны не заменяют CI evidence.

## Завершение

В комментарии/связанном PR сохранить source/protocol/corpus hashes, run URL/attempt, компактные входы evaluator, coverage/exclusions, limitations и verdict `ACCEPT / REJECT / INCONCLUSIVE / INVALID`. R0 verdict: **ACCEPT для exploratory foundation только** — corpus/lineage/candidate universe и durable handoff воспроизводимы. Это не verdict о полезности Delsk: oracle/scorer/encoder и G1–G5 ещё не запускались. Confirmatory cohort расширяется отдельным будущим acquisition/license budget.

## Программа

[DELSK-000](https://github.com/definitely-stable/Shift-lab/issues/1) — общий прогресс и go/pivot/stop.
