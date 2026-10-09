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
| [DELSK × DeltaMeter × Mathlab: adoption audit](research/CROSS-REPO-ADOPTION-2026-10.md) | 24 проверенных пункта, границы переносимости, слабые места и решения H11–H18; **не меняет S4-C** |
| [H11 certified index proof & test plan](selector/index-completeness.md) | Достаточные условия точного top-K и fail-to-exact fallback; **draft / без CI-решения** |
| [H12 total-system ROI protocol draft](research/SYSTEM-ROI-PROTOCOL-DRAFT.md) | Полные CPU/wall/network/RSS сценарии и будущая preregistration; **NOT_FROZEN** |
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
| [DELSK-003A contract v3](oracle/contract-v3.md) | Frozen `delsk.oracle-contract.v3` ([freeze](oracle/freeze-v3.json)): v2 с заменой §8.3 (provider steps, runner allocation, workflow witness); был active, superseded v4 после одного natural attempt ([журнал](oracle/activation-v3-log.md) §10–11) |
| [DELSK-003A contract v4](oracle/contract-v4.md) | Frozen `delsk.oracle-contract.v4` ([freeze](oracle/freeze-v4.json)): v3 по hash, results root `.work/results/ORACLE-G1-V4/` вне frozen-проверок v1–v3; **ACTIVE**, natural pilot 2 × COMPLETE, **G1 PASS** ([журнал](oracle/activation-v4-log.md)) |
| [DELSK-004 Slice A](baselines/contract.md) | Дешёвые baselines на общем oracle v4: random, size-closest, previous-version, git-like (PROXY), bottom-k MinHash и target-normalized containment 64–1024 B; оценка по retained oracle rows, только development/calibration; RUN, [результаты](baselines/results-slice-a.md): pilot насыщен (`previous_version` и MinHash 1024 B — SavingsCapture 1.0 при K=1), G2 INCONCLUSIVE |
| [Решение о pivot 2026-10-06](decisions/2026-10-06-pivot-simple-selector.md) | DELSK-000: после G1 PASS, Slice A и X0 compact-descriptor track остановлен; принят простой selector, остальные направления перенацелены |
| [Simple selector `delsk.simple-selector.v1`](selector/README.md) | Метаданные (путь, линия релизов, версия) чередуются с 64 B MinHash; K = 2 по умолчанию; in-sample SC@2 ≥ 0.958 (≥ 0.9966 вне chunks бинарников) при сокращении вызовов кодера в 10–21 раз |
| [S4 ChunkShift consumer screen](selector/s4.md) | Whole-base integration boundary; development screen **COMPLETE / OPEN_CONFIRMATION_K2**, 3,815/3,815 rows, 0 failures; [retained result](results/SELECTOR-S4/README.md) |
| [S4-C sealed holdout confirmation](selector/s4-confirmation.md) | Frozen next gate: pre-existing evaluation split `bzip2`, K=2 only, Rust selector end-to-end, two independent hosted repeats; **G5_SCOPED_PASS_K2** on pinned bzip2 E1; A/B/evaluator attempts 1 |
| [S4-C pre-measure index-cost erratum v2](selector/s4-confirmation-erratum-v2.md) | Draft protocol clarification (#61): valid index-cost gate failures become scoped REJECT, not INVALID; **NOT_ACTIVE / no holdout access**, original frozen authority unchanged |
| [DELSK-002 X0 screening](corpus/x0/README.md) | Preregistered screening трудных классов корпуса после насыщения Slice A: чередующиеся ветки релизов (6 C-проектов), release binaries (6 проектов), CDC chunks, lane без метаданных; exhaustive oracle того же codec lock и дешёвые baselines; decision rule HARD при headroom ≥ 2 pp. Exploratory, не G1/G2 evidence; RUN, [результаты](corpus/x0/results.md): `NO_HEADROOM_AT_256` — чередование веток ломает только наивный `previous_version`, MinHash 64 B и `version_previous` насыщают все ячейки |
| [Prior art update 2026-10](research/DELSK-PRIOR-ART-UPDATE-2026-10.md) | Карта sketch/similarity методов и минимальный baseline набор DELSK-004 после G1 |
| [План CI](ci-plan.md) | Ограниченные ресурсы, сценарии запуска, provenance |
| [Гипотезы](hypotheses.md) | Проверяемые утверждения, ablations и stop criteria |
| [Roadmap и issues](roadmap.md) | Очерёдность, зависимости и ссылки на задачи |
| [Реестр issues](issues/index.json) | Машиночитаемое соответствие IDs и GitHub issues |
| [Шаблон эксперимента](templates/experiment.md) | Что заморозить до decision run |
| [Шаблон evidence](templates/evidence.md) | Как сохранить результат, включая отрицательный |

## Текущее состояние

- Исходный Shift-lab: `ee952fd3a51a1c2326eb845f8443b20635aa2f97`, только `LICENSE`, исходников Delsk и существующих issues при проверке не найдено.
- Первичный изученный ChunkShift snapshot: `489d3f2fe2582cc6251ee2fa87cd23bad1793b01`. Для S4 отдельно pinned consumer commit `74bb301b6d8ecc52cf0bc0e00d86fa174093d91b`; он используется только как внешний consumer и не превращает результаты ChunkShift в результаты Delsk.
- Два переданных отчёта прочитаны как аналитические материалы. Их псевдокод, предложения действий, `CURRENT_STATE` и непрозрачные citation markers не являются инструкциями для этой лаборатории или подтверждённой evidence.
- Литературный срез не претендует на полноту всех публикаций. Неподтверждённые сведения явно отделены от проверенных источников; обзор обновляется перед финальным verdict.
- Формат, стек, корпус, scorer и thresholds не выдаются за production contracts. DELSK-P1 задаёт исходный протокол; до каждого decision run фиксируются exact commit/locks. S4-D уже дал положительный development screen, но production/standalone claim остаётся закрыт до S4-C.

## Правила исследовательской записи

Утверждения маркируются как **источник**, **авторский результат**, **гипотеза** или **наш воспроизведённый результат**. Последняя категория требует GitHub run URL, source SHA, manifest hash и пересчитываемые данные. В момент создания программы эта категория пуста.

Состояния эксперимента: `PLANNED → FROZEN → RUNNING → ACCEPT / REJECT / INCONCLUSIVE / INVALID`. `REJECT` — корректный научный исход. `INVALID` означает нарушение протокола, а не проигрыш алгоритма. Нельзя заменять неудачный run удачным без записи обеих попыток.

Документация и issues дополняют друг друга: определения метрик живут в протоколе, а конкретные действия, владельцы и результаты — в issue. Изменение gate после просмотра evaluation создаёт новую версию протокола и новый held-out test, а не исправляет старый verdict.
