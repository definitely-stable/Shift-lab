# DELSK-005 — Построить ограниченный CI harness и долговечную evidence

**Приоритет:** P0. **Статус:** PLANNED. **Владелец:** maintainers Shift-lab (исполнитель назначается при старте).

## Вопрос / результат

Можно ли надёжно проверять quality и paired performance только на GitHub hosted runners?

## Основа

[Документ](https://github.com/definitely-stable/Shift-lab/blob/main/.work/ci-plan.md) · [Протокол DELSK-P1](https://github.com/definitely-stable/Shift-lab/blob/main/.work/protocol.md) · [Программа](https://github.com/definitely-stable/Shift-lab/blob/main/.work/README.md).

**Зависимости:** [DELSK-002](https://github.com/definitely-stable/Shift-lab/issues/3).

## Шаги

- [ ] Smoke/pilot/decision workflows с frozen refs, read-only permissions, pinned actions и caps.
- [ ] Ввести source/corpus/candidate/tool provenance, safe cache reuse и completeness validation.
- [ ] Выполнить A/A noise pilot, затем paired A/B/A 5 blocks после 2 warmups; policy freeze до evaluation.
- [ ] Записывать image/CPU/ISA и actual job duration; budget reservation/accounting ≤600 experimental runner-min/week.
- [ ] Экспортировать компактные rows/hashes/evaluator до artifact expiry; separate independent confirmation dispatch.

## Acceptance / evidence

- [ ] x64 pilot выполнен; native arm64 availability проверена либо support ограничен.
- [ ] Пропущенная пара, чужой SHA/lock или decode mismatch отклоняются.
- [ ] Cost/retention caps enforceable; no paid larger runners/GPU/self-hosted dependency.
- [ ] Verdict пересчитывается после удаления локально скачанной raw archive copy из retained metrics; полный replay имеет отдельную recipe.

## Staging внутри R0

Milestone `005-foundation` зависит от corpus/candidate **contracts** DELSK-002 (Slice B), а не от закрытия всей DELSK-002; это снимает круговую зависимость 002↔005 для acquisition pilot. Он даёт admission до compute: ledger 600 runner-min за скользящие 7×24 ч UTC (все attempts, reservation полного cap) — telemetry по умолчанию и emergency guardrail при `DELSK_BUDGET_MODE=enforce`; жёсткие timeout, сериализацию и artifact cap без автоудаления; frozen identities dispatch и limits time/RAM/disk с failure evidence — см. [CI plan](../ci-plan.md). Milestone не закрывает issue: шаги и acceptance выше (x64 pilot с данными, ARM, A/A, decode mismatch, пересчёт verdict, durable export) остаются открытыми.

## CI и ресурсы

Smoke≤8min, pilot≤30min, decision2×45+5=95min; 2 concurrent measurement jobs. Все тесты и измерения — GitHub Actions. Published paper numbers и локальные прогоны не заменяют CI evidence.

## Завершение

В комментарии/связанном PR сохранить source/protocol/corpus hashes, run URL/attempt, компактные входы evaluator, coverage/exclusions, limitations и verdict `ACCEPT / REJECT / INCONCLUSIVE / INVALID`. До выполнения шагов результат остаётся **не проверен**. Отрицательный результат закрывает вопрос только с явным stop/pivot и следом evidence.

## Программа

[DELSK-000](https://github.com/definitely-stable/Shift-lab/issues/1) — общий прогресс и go/pivot/stop.
