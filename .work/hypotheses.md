# Проверяемые гипотезы

Все H1–H10 **не проверены**. Предлагаемые размеры и thresholds — research choices. Определения и общие gates берутся только из [DELSK-P1](protocol.md); описание ниже не создаёт альтернативных метрик.

| ID / задача | Гипотеза | Контроль и эксперимент | Успех / отрицательный исход |
|---|---|---|---|
| H1 · DELSK-006 | 128–256 B сохраняют почти всю полезную информацию | 64/128/256/512/1024 B, равный K, exact descriptor scan, одинаковый hash/feature pool | G3 и лучший Pareto point; если 512/1024 B тоже не дают headroom, прекращаем compact-library track |
| H2 · DELSK-007 | Directed length/containment/offset признаки полезнее дешёвых controls | symmetric resemblance vs +length vs length+target-normalized containment vs full directional; reverse-direction diagnostic отдельно от temporal | ≥20% p95 regret improvement либо +2 pp Useful Recall@8 на held-out, CI исключает ноль; если дешёвый control объясняет эффект, сложный scorer исключить |
| H3 · DELSK-007 | Один descriptor переносится между codecs с разными scorers | общий scorer vs per-codec vs specialized descriptor; два generic codecs, затем XOR отдельно | сопоставимое качество при меньшем суммарном representation cost; если нет — честный codec-specific scope |
| H4 · DELSK-006 | Positions/order/multi-scale добавляют signal сверх content overlap | nested + leave-one-feature-out ablation при том же byte budget, raw vs normalized positions | ≥20% p95-regret reduction или +2 pp Useful Recall@8; рост build cost учитывается; feature удаляется при отсутствии эффекта |
| H5 · DELSK-008 | Bounded inverted retrieval даёт экономию без потери reranker potential | exact scan как upper reference, posting caps и M=32/64/128, одинаковый K | G3/G4, cap hits/coverage и total RAM опубликованы; ANN не вводится, пока simple index не ограничивает результат |
| H6 · DELSK-009 | Можно безопасно отказаться от delta для невыгодных targets | always-encode vs threshold/abstain policy; compressed/random/near-threshold cases | false-negative≤1% среди useful-delta с CI, saved CPU и lost bytes; недостоверный filter → conservative fallback |
| H7 · DELSK-010 | Полезный descriptor можно строить bit-identically streaming на x64/arm64/WASM | canonical scalar vs optimized backend, arbitrary splits, malformed/degenerate inputs | все executed vectors совпадают; divergence → INVALID, performance не оправдывает смену semantics |
| H8 · DELSK-011 | Tensor-aware profile полезен сверх generic byte features | licensed held-out ancestor families, fixed layout/dtype, generic/XOR-aware/faithful BitX если доступен | +3 pp Useful Recall@8 или ≥20% regret improvement с metadata cost; synthetic-only → без model claim |
| H9 · DELSK-012 | Ranking окупается в настоящем update pipeline | historical/size baseline vs Delsk; full setup/query/encode/fetch costs, cold и amortized | положительный system benefit и неизменная correctness; локальный microbenchmark win недостаточен |
| H10 · DELSK-006 | CDC — полезный optional feature source, не обязательная зависимость | no-CDC vs pinned FastCDC anchors; ShiftCDC только при доступной воспроизводимой реализации | эффект при равном budget; если no-CDC не хуже, убрать зависимость; собственный chunker не получает privileged tuning |

## Порядок отбора

Сначала H1/H4/H10: one-pass scalar representation с exact scan. Затем H2/H3 и H6. Только после signal gate — H5/H7; затем H9. H8 запускается при реальных model data и достаточном signal generic scorer. 4096 B/hierarchy, custom ANN и neural training требуют отдельной мотивированной задачи.

Hyperparameters не выбираются на held-out. Family of tests и practical minimum effect замораживаются в issue, Holm применяется к заявленной семье ablations; negative и inconclusive результаты сохраняются. При p95=0 использовать заранее предусмотренный bytes endpoint, а не деление на ноль.

## Риски и действия

| Риск | Проверка / ограничение |
|---|---|
| Prior art уже содержит contribution | DELSK-001 source/section-level claim chart; число «новых флагов» не доказательство новизны |
| 99% recall за счёт одной большой lineage | macro/per-domain summaries, cluster CI и minimum lineage counts |
| Tiny sketches проваливаются на huge objects | size-stratified analysis, upper-size control, иерархия только после результата |
| Learned baseline недоступен на CPU | `UNAVAILABLE`, ограниченные claims, published numbers только context |
| Postings explosion/poisoning | cap budget, truncation evidence, safe fallback, DELSK-009/010 |
| Обновились codec/runtime/options | новые locks; старый scorer не объявляется совместимым автоматически |
| Дорогой oracle съедает CI | pilot pairs/s → deterministic shards; никаких нерегулируемых N² sweeps |
| Изменения метрик под результат | immutable protocol commit + amendment + fresh held-out |

Техническая novelty и ценность инженерной библиотеки различны. Даже известная комбинация может быть удобнее существующих решений; это доказывается costs и adoption experiment, а не заявлениями «впервые».
