# R0 readiness: foundation handoff

Запись состояния R0 foundation (DELSK-002 Slice F, DELSK-005 milestone `005-foundation`). Это не quality verdict: oracle, scorer и encoder не запускались, G1–G5 не оцениваются.

**Gate: READY**

Gate вычисляется `python3 .work/tools/recompute_foundation.py readiness` и проверяется тестом `test_readiness_record_states_the_computed_gate`: строка выше обязана совпадать с вычисленным значением. Изменять её вручную без bundles нельзя.

## Что должно быть для READY

1. Freeze chain D → E0 → E1 (root records и все закреплённые ими файлы), tools и pinned locks пересчитываются без corpus payload: content, lineage и candidate accounting сверяются с независимо выведенными seal summary и coverage (`handoff.json`).
2. В `.work/results/R0-FOUNDATION/` лежат минимум два bundle `<run-id>-<attempt>` из **разных** run ID, у которых `handoff.json` совпадает байт в байт. Каждый bundle проходит `verify`: checksums, run/source/workflow identities (x64, admitted, status `ok`), схема, пересчёт, структура A/A timings.
3. Bundles попадают в репозиторий только через reviewed PR: workflow не получает права записи.

## Как получить bundles

```bash
# Actions → Foundation (experimental) → workload foundation-handoff, source_sha = head ветки; два независимых dispatch
gh run download <run-id> -D artifact-<run-id>
python3 .work/tools/recompute_foundation.py bundle artifact-<run-id>
python3 .work/tools/recompute_foundation.py readiness
```

## Состояние

| Элемент | Статус |
|---|---|
| Acquisition pilot-v1 (Slice D) | frozen, две совпавшие materializations |
| Ancestry audit и E0 freeze (Slice E0) | adopted |
| Sealed `C_t` (Slice E1) | sealed, 79 queries, 1 961 pairs/codec |
| Recompute и verify bundle (Slice F / PR #22) | реализованы, покрыты тестами |
| Bundles двух независимых Actions dispatch | **verified** — `37210886381-1` и `37210930669-1`; `handoff.json` byte-identical |
| A/A recorder (2 warmups, 5 blocks) | сохранён в обоих bundles; exact block/arm/position/warmup sequence verified |
| Native ARM | **не проверялась**; scope R0 остаётся x64 |

## Retained evidence

- source/workflow SHA обоих runs: `7ff8882e5143448a0be65ace6c27b009ae9ba0bd`;
- run IDs: [37210886381](https://github.com/definitely-stable/Shift-lab/actions/runs/37210886381) и [37210930669](https://github.com/definitely-stable/Shift-lab/actions/runs/37210930669), attempt 1;
- runners: GitHub-hosted Ubuntu 24.04 x64; CPU AMD EPYC 7763 и AMD EPYC 9V74;
- оба workload status `ok`, admission complete/admitted/within budget;
- canonical `handoff.json` SHA-256: `3157c401e2c12f281fb6f855c14faba89d8aade0b6675be451804a7fed51a4d0`;
- accounting: 32 391 occurrences, 28 477 content classes, 0 cross-split classes, 79 queries (64 near + 15 identity), 1 961 planned pairs/codec;
- ZIP/artifact digests различаются ожидаемо из-за run metadata и timing samples; readiness сравнивает normative retained bundles и byte-identical semantic handoff.

R0 foundation **READY** означает только воспроизводимый exploratory foundation. Oracle/scorer/encoder не запускались; это не G1–G5 verdict.

## Что этот gate не закрывает

Открытые пункты DELSK-005: A/A на реальной baseline workload, paired A/B/A, native ARM, пересчёт oracle evidence (отклонение пропущенной пары и decode mismatch), independent confirmation на реальном decision lane. A/A служебного SHA-256 проверяет только timing recorder и не калибрует будущий encoder; P1 noise gate не менялся.

Открытые пункты DELSK-002: confirmatory sufficiency не установлена, pilot — шесть singleton components и одна held-out lineage в calibration и в evaluation (см. [E1](../corpus/e1/README.md)).

## Expansion backlog

Domains вне pilot (binaries, tabular, OCI, models, VM assets), ≥10 held-out lineages на confirmatory domain и precision analysis — отдельные acquisition/license budgets после R1.
