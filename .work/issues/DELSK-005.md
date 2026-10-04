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

## CI и ресурсы

Smoke≤8min, pilot≤30min, decision2×45+5=95min; 2 concurrent measurement jobs. Все тесты и измерения — GitHub Actions. Published paper numbers и локальные прогоны не заменяют CI evidence.

## Завершение

В комментарии/связанном PR сохранить source/protocol/corpus hashes, run URL/attempt, компактные входы evaluator, coverage/exclusions, limitations и verdict `ACCEPT / REJECT / INCONCLUSIVE / INVALID`. До выполнения шагов результат остаётся **не проверен**. Отрицательный результат закрывает вопрос только с явным stop/pivot и следом evidence.

## Программа

[DELSK-000](https://github.com/definitely-stable/Shift-lab/issues/1) — общий прогресс и go/pivot/stop.
