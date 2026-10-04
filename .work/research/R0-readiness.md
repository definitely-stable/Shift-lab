# R0 readiness: foundation handoff

Запись состояния R0 foundation (DELSK-002 Slice F, DELSK-005 milestone `005-foundation`). Это не quality verdict: oracle, scorer и encoder не запускались, G1–G5 не оцениваются.

**Gate: NOT READY**

Gate вычисляется `python3 .work/tools/recompute_foundation.py readiness` и проверяется тестом `test_readiness_record_states_the_computed_gate`: строка выше обязана совпадать с вычисленным значением. Изменять её вручную без bundles нельзя.

## Что должно быть для READY

1. Sealed E1 и все pinned locks пересчитываются без corpus payload: content, lineage и candidate accounting сверяются с независимо выведенными seal summary и coverage (`handoff.json`).
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
| Recompute и verify bundle (этот PR) | реализованы, покрыты тестами |
| Bundles двух независимых Actions dispatch | **нет** — dispatch ещё не выполнялись |
| A/A recorder (2 warmups, 5 blocks) | реализован в workload; timings появятся с первым bundle |
| Native ARM | **не проверялась**; scope R0 остаётся x64 |

## Что этот gate не закрывает

Открытые пункты DELSK-005: A/A на реальной baseline workload, paired A/B/A, native ARM, пересчёт oracle evidence (отклонение пропущенной пары и decode mismatch), independent confirmation на реальном decision lane. A/A служебного SHA-256 проверяет только timing recorder и не калибрует будущий encoder; P1 noise gate не менялся.

Открытые пункты DELSK-002: confirmatory sufficiency не установлена, pilot — шесть singleton components и одна held-out lineage в calibration и в evaluation (см. [E1](../corpus/e1/README.md)).

## Expansion backlog

Domains вне pilot (binaries, tabular, OCI, models, VM assets), ≥10 held-out lineages на confirmatory domain и precision analysis — отдельные acquisition/license budgets после R1.
