# DELSK-002 — Заморозить лицензированный corpus и lineage/candidate manifests

**Приоритет:** P0. **Статус:** PLANNED. **Владелец:** maintainers Shift-lab (исполнитель назначается при старте).

## Вопрос / результат

Можно ли получить репрезентативную, ограниченную и независимую выборку без leakage?

## Основа

[Документ](https://github.com/definitely-stable/Shift-lab/blob/main/.work/corpus-and-baselines.md) · [Протокол DELSK-P1](https://github.com/definitely-stable/Shift-lab/blob/main/.work/protocol.md) · [Программа](https://github.com/definitely-stable/Shift-lab/blob/main/.work/README.md).

**Зависимости:** нет; готово к исследовательской подготовке.

Milestone Slice D: acquisition exploratory pilot заморожена в [pilot-v1](../corpus/pilot-v1/README.md): source/corpus locks, snapshot license review, две независимые совпавшие materializations в Actions и offline integrity checks. Полный metadata universe сохранён в git в compressed lock. Milestone Slice E0: candidate construction design принят в [e0](../corpus/e0/construction-spec.md) — решения A01–A10, закрытая candidate-lock v2 schema, golden vectors, ancestry audit всех 15 пар на acquired snapshots и historical-byte scope. Issue остаётся открытой: frozen `C_t` — Slice E1; полный foundation handoff — Slice F; confirmatory sufficiency не установлена.

## Шаги

- [ ] Выбрать source/binary/archive families и synthetic diagnostics; model/OCI добавлять при проверенной лицензии.
- [ ] Создать version-pinned source manifest, checksums, transforms и лицензии; materialization с archive traversal/expansion caps.
- [ ] Разделить development/calibration/evaluation по ancestor lineage, сохраняя transformed variants вместе.
- [ ] Зафиксировать каждый C_t до scoring: temporal eligibility, related/decoy/negative bases, duplicates/exclusions, sorted IDs.
- [ ] Показать coverage и число независимых held-out lineages, deferred domains и причины.

## Acceptance / evidence

- [ ] CI materializes один lock дважды с одинаковыми IDs и hashes.
- [ ] Нет пересечения lineage между splits; self/exact duplicates отдельно.
- [ ] Pilot ≤256 MiB acquired/1 GiB materialized и ≤4096 ordered pairs/codec.
- [ ] Для confirmatory domain ≥10 held-out lineages либо явно exploratory статус.

## CI и ресурсы

Pilot x64 ≤30 min; shard≤2GiB позже по утверждённому lock. Все тесты и измерения — GitHub Actions. Published paper numbers и локальные прогоны не заменяют CI evidence.

## Завершение

В комментарии/связанном PR сохранить source/protocol/corpus hashes, run URL/attempt, компактные входы evaluator, coverage/exclusions, limitations и verdict `ACCEPT / REJECT / INCONCLUSIVE / INVALID`. До выполнения шагов результат остаётся **не проверен**. Отрицательный результат закрывает вопрос только с явным stop/pivot и следом evidence.

## Программа

[DELSK-000](https://github.com/definitely-stable/Shift-lab/issues/1) — общий прогресс и go/pivot/stop.
