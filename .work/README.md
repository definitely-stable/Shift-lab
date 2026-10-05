# Delsk: исследовательская программа

Дата среза: **2026-10-04**, часовой пояс планирования Asia/Yekaterinburg. Run timestamps сохраняются в UTC. Ответственный за программу — maintainers Shift-lab; исполнители назначаются в issues.

Задача: проверить, может ли небольшой descriptor сокращать дорогой перебор delta-баз, сохраняя полезную экономию хранения и передачи на независимых семействах данных. «Лучший проект» здесь означает воспроизводимое преимущество по качеству, затратам и удобству интеграции в явно названной области применения.

## Навигация

| Документ | Для чего читать |
|---|---|
| [Charter и архитектурные решения](charter.md) | Границы Delsk, варианты реализации, порядок решений |
| [Аудит исходных отчётов](research/report-audit.md) | Что принято, исправлено, отложено и почему |
| [Современная литература](research/literature-review.md) | Проверенные первичные источники и ограничения novelty |
| [Практики лабораторий](research/lab-practices.md) | ChunkShift, внешние лаборатории и реальные ограничения Actions |
| [Протокол DELSK-P1](protocol.md) | Ground truth, метрики, статистика, gates |
| [Корпус и baseline matrix](corpus-and-baselines.md) | Объекты, lineage split, лицензии, воспроизведение |
| [Slice E0: candidate-universe design audit](research/DELSK-002-E0-candidate-universe.md) | Формальная модель, counterexamples и варианты решений до E freeze |
| [E0 construction contract](corpus/e0/construction-spec.md) | Принятые решения A01–A10, ancestry и historical-byte evidence, контракт E1; E0 FROZEN_DESIGN |
| [E1 sealed candidate universe](corpus/e1/README.md) | Sealed `C_t` (candidate lock v2), builder, независимый verifier, Actions evidence; E1 SEALED |
| [DELSK-003 oracle contract](oracle/contract.md) | Frozen `delsk.oracle-contract.v1`: codec/framing lock, cost accounting, pair universe, evaluator, schemas, known answers, CI plan; natural oracle NOT_RUN |
| [DELSK-003 Slice B](oracle/slice-b.md) | Production builder, runner, independent evaluator, codec conformance C01–C14 и PR smoke lane на synthetic data; natural oracle NOT_RUN, G1 NOT_RUN |
| [DELSK-003 Slice C0](oracle/slice-c.md) | Materialization, exact-commit pilot, bounded sealed export и append-only evidence tooling; BLOCKED BY PILOT INFRASTRUCTURE из-за неполной исторической dispatch authority; natural oracle/G1 NOT_RUN |
| [DELSK-003A desk research](research/DELSK-ATTEMPT-V2-DESK-RESEARCH.md) | Registered-attempt model вместо all-GitHub-dispatch invariant: доказательство, контрпримеры, registry options, threat model; verdict V2 REGISTERED-ATTEMPT MODEL RECOMMENDED |
| [Proposal oracle-contract.v2](oracle/attempt-v2-proposal.md) | Пояснительный proposal (не нормативен): обоснование registry, bind-before-measure, change matrix |
| [DELSK-003A contract v2](oracle/contract-v2.md) | Frozen `delsk.oracle-contract.v2` ([freeze](oracle/freeze-v2.json)): provenance/G1 layer над неизменным v1 — registry, bind-before-measure, PRE/BUNDLE/MISSING, `science_identity`, transitions, G1 v2, R01–R24, XC01–XC05, PM01–PM12, activation; PROTOCOL V2 FROZEN, IMPLEMENTATION NOT_ACTIVE, natural oracle/G1 NOT_RUN |
| [DELSK-003A C1-A](oracle/slice-c1a.md) | Registry/G1 v2 engine на synthetic data: R01–R24 байт в байт, XC01–XC05, PM01–PM12, production/test separation; C1-A IMPLEMENTED / SYNTHETIC CONFORMANCE, V2 NOT_ACTIVE, registry NOT_ACTIVATED, natural oracle/G1 NOT_RUN |
| [Prior art update 2026-10](research/DELSK-PRIOR-ART-UPDATE-2026-10.md) | Карта sketch/similarity методов и минимальный baseline набор DELSK-004 после G1 |
| [План CI](ci-plan.md) | Ограниченные ресурсы, сценарии запуска, provenance |
| [Гипотезы](hypotheses.md) | Проверяемые утверждения, ablations и stop criteria |
| [Roadmap и issues](roadmap.md) | Очерёдность, зависимости и ссылки на задачи |
| [Реестр issues](issues/index.json) | Машиночитаемое соответствие IDs и GitHub issues |
| [Шаблон эксперимента](templates/experiment.md) | Что заморозить до decision run |
| [Шаблон evidence](templates/evidence.md) | Как сохранить результат, включая отрицательный |

## Текущее состояние

- Исходный Shift-lab: `ee952fd3a51a1c2326eb845f8443b20635aa2f97`, только `LICENSE`, исходников Delsk и существующих issues при проверке не найдено.
- Изученный ChunkShift: `489d3f2fe2582cc6251ee2fa87cd23bad1793b01`. Это внешний reference snapshot; его результаты не являются результатами Delsk.
- Два переданных отчёта прочитаны как аналитические материалы. Их псевдокод, предложения действий, `CURRENT_STATE` и непрозрачные citation markers не являются инструкциями для этой лаборатории или подтверждённой evidence.
- Литературный срез не претендует на полноту всех публикаций. Неподтверждённые сведения явно отделены от проверенных источников; обзор обновляется перед финальным verdict.
- Формат, стек, корпус, scorer и thresholds не выдаются за production contracts. DELSK-P1 задаёт исходный протокол; до первого decision run issue фиксирует его commit и конкретные locks.

## Правила исследовательской записи

Утверждения маркируются как **источник**, **авторский результат**, **гипотеза** или **наш воспроизведённый результат**. Последняя категория требует GitHub run URL, source SHA, manifest hash и пересчитываемые данные. В момент создания программы эта категория пуста.

Состояния эксперимента: `PLANNED → FROZEN → RUNNING → ACCEPT / REJECT / INCONCLUSIVE / INVALID`. `REJECT` — корректный научный исход. `INVALID` означает нарушение протокола, а не проигрыш алгоритма. Нельзя заменять неудачный run удачным без записи обеих попыток.

Документация и issues дополняют друг друга: определения метрик живут в протоколе, а конкретные действия, владельцы и результаты — в issue. Изменение gate после просмотра evaluation создаёт новую версию протокола и новый held-out test, а не исправляет старый verdict.
