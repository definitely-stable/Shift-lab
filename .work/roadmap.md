# Roadmap: evidence до production

Это последовательность решений, не обещание завершить научное исследование к календарной дате. Стартовый срез — 2026-10-04. Compute ограничен [CI plan](ci-plan.md); длительности ниже — ориентир активной работы, не SLA.

| Этап | Задачи | Выход / критерий |
|---|---|---|
| R0 · foundation, 1–2 итерации | 001, 002, 005 | prior-art map, licensed corpus, CI pilot, frozen locks |
| R1 · measurement, 1–3 итерации | 003, 004 | полный small-universe oracle и comparable baseline evidence |
| R2 · scalar signal, 2–4 итерации | 006, 007, 009 | descriptor/scorer Pareto; stop если нет headroom |
| R3 · deployment cost, 1–3 итерации | 008, 010 | bounded index, deterministic executed platforms |
| R4 · consumer verdict, 1–2 итерации | 012, 013 | системная польза и воспроизводимый go/pivot/stop |
| Optional model track | 011 после 007 | отдельный профиль только при реальных data/evidence |

Итерация = один заранее ограниченный вопрос, pilot/decision и evidence review; она не требует полного grid и не равна неделе. Один active decision experiment одновременно; подготовка источников/корпуса может идти параллельно. DELSK-000 отслеживает всю программу и остаётся открытой после завершения первоначальной документации.

## Очередь issues

Назначение исполнителя происходит при старте; по умолчанию accountable maintainers Shift-lab. Таблица ниже задаёт dependency graph; фактический статус каждого issue ведётся в его body/GitHub. R0 foundation уже завершён как exploratory evidence, остальные научные результаты не следует считать измеренными без соответствующего gate.

| ID | Priority | Задача | Зависимости |
|---|---|---|---|
| [DELSK-000](https://github.com/definitely-stable/Shift-lab/issues/1) | P0 | Программа Delsk: от prior art до решения о самостоятельной библиотеке | — |
| [DELSK-001](https://github.com/definitely-stable/Shift-lab/issues/2) | P0 | Проверить claim matrix и воспроизводимость современного prior art | — |
| [DELSK-002](https://github.com/definitely-stable/Shift-lab/issues/3) | P0 | Заморозить лицензированный corpus и lineage/candidate manifests | — |
| [DELSK-003](https://github.com/definitely-stable/Shift-lab/issues/4) | P0 | Реализовать настоящий multi-base encoder oracle и метрики | DELSK-002, DELSK-005 |
| [DELSK-004](https://github.com/definitely-stable/Shift-lab/issues/5) | P0 | Воспроизвести дешёвые и современные baselines на общем oracle | DELSK-001, DELSK-003 |
| [DELSK-005](https://github.com/definitely-stable/Shift-lab/issues/6) | P0 | Построить ограниченный CI harness и долговечную evidence | DELSK-002 |
| [DELSK-006](https://github.com/definitely-stable/Shift-lab/issues/7) | P1 | H1/H4/H10: проверить размер sketches, features и CDC dependence | DELSK-003, DELSK-004 |
| [DELSK-007](https://github.com/definitely-stable/Shift-lab/issues/8) | P1 | H2/H3: проверить направленность и codec-conditioned scoring | DELSK-006 |
| [DELSK-008](https://github.com/definitely-stable/Shift-lab/issues/9) | P1 | H5: исследовать retrieval/index и реальную экономику памяти | DELSK-006, DELSK-007 |
| [DELSK-009](https://github.com/definitely-stable/Shift-lab/issues/10) | P1 | H6: no-delta abstention и adversarial negative controls | DELSK-006 |
| [DELSK-010](https://github.com/definitely-stable/Shift-lab/issues/11) | P1 | H7: portable streaming reference, robustness и SIMD parity | DELSK-006 |
| [DELSK-011](https://github.com/definitely-stable/Shift-lab/issues/12) | P2 | H8: условный tensor-aware model-weight профиль | DELSK-002, DELSK-007 |
| [DELSK-012](https://github.com/definitely-stable/Shift-lab/issues/13) | P2 | H9: интеграционный эксперимент с ChunkShift | DELSK-008, DELSK-009, DELSK-010 |
| [DELSK-013](https://github.com/definitely-stable/Shift-lab/issues/14) | P2 | Принять итоговый go/pivot/stop и подготовить воспроизводимый artifact | DELSK-001, DELSK-004, DELSK-007, DELSK-008, DELSK-009, DELSK-010, DELSK-012 |

GitHub URLs и номера хранятся в [реестре](issues/index.json); после публикации ссылки в таблице ведут прямо в issues. Bodies сохранены как первоначальные постановки; текущие обсуждения и статусы ведутся в GitHub.

## Первый следующий шаг

Claim register DELSK-001 и corpus contracts DELSK-002 приняты; milestone `005-foundation` (admission до compute и bounded foundation workflow) — в [CI plan](ci-plan.md). Acquisition DELSK-002 (Slice D) frozen: source/corpus locks, snapshot license review и две совпавшие materializations — в [pilot-v1](corpus/pilot-v1/README.md). Candidate construction design и ancestry audit приняты (Slice E0, [construction contract](corpus/e0/construction-spec.md)). Sealed `C_t` (Slice E1) — [candidate lock v2](corpus/e1/README.md): builder, независимый verifier и два совпавших Actions runs. Durable foundation evidence (Slice F) закрыта: два независимых Actions `foundation-handoff` на merged SHA сохранены как retained bundles, [R0 readiness](research/R0-readiness.md) = **READY**. R0 exploratory foundation завершён. R1 начат с DELSK-003 Slice A: узкий frozen [oracle contract](oracle/contract.md) `delsk.oracle-contract.v1` (codec/framing lock, cost accounting, evaluator, vectors) до реализации и до любых natural измерений. Следующий шаг — Slice B (реализация runner/evaluator и codec conformance без natural data), затем pilot oracle по отдельному подтверждению; только после G1 — DELSK-004 baselines. Наличие READY foundation и frozen contract само по себе не закрывает G1–G5.
