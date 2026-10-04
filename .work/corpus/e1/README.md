# DELSK-002 E1: sealed candidate universe

Статус: **SEALED** с момента merge в `main`. Машиночитаемая запись — [seal.json](seal.json). Lock построен строго по [E0 construction contract](../e0/construction-spec.md) (A01–A10, §4, §7) из полного hash-bound U pilot-v1. Scorer, encoder, oracle, patch costs и utility results не существуют и не читались; seal не является measurement и не даёт quality verdict.

## Что запечатано

| Artifact | SHA-256 |
|---|---|
| [candidate-lock.json](candidate-lock.json) (`delsk.candidate.lock.v2`) | `cb16d53b164ff393187e0115bdf31c52ac717a5172fb1e91889b5988ac019d2e` |
| [selection.json](selection.json) — schedule trace и per-category pool evidence (§7.2) | `65740efb41f93688ccc5c8538117def770f73c119ad0cd3633771a6e17ee3b1b` |
| [coverage.json](coverage.json) — coverage contract (§8, research spec §17.2) | `5c2035694fb290004c98798ec2492c558eed6b5f4db35ef76eb5ce6320f9aa60` |

Bindings lock равны `candidate_lock_bindings` в [E0 freeze](../e0/freeze.json): corpus lock (decompressed canonical), selection policy, construction spec, protocol, ancestry audit, acquisition freeze и historical-bytes evidence. Seed `20261004`, caps 2/30/32, `max_targets=64`, pair cap 4096 не изменены.

## Реализация

- [candidates.py](../../tools/candidates.py) — builder. Admission закрытого набора frozen inputs по точным hashes; полный U; identity classification всех `T_all`; A02 round-robin; existential categories; total-order first-N; minimum representative; закрытые v2 bytes; coverage. Ключи world, sources, occurrences и params закрыты: score, codec или result field — ошибка (A10). `make_lock` отказывает без near query, при расхождении pair sum, превышении cap и неверной форме query.
- [candidate_verify.py](../../tools/candidate_verify.py) — независимый verifier (A09). Не импортирует builder. Из `manifests.py` берёт только strict loader и canonical serializer. Слой 1 строит ожидаемое множество позиций `(source, track, path, offset, length, options)` из `source-lock` retained members и сравнивает его с corpus lock как множества вместе с object/parent/stratum bindings и суммой bytes. Слой 2 заново выводит `T_all`, identities, traversal и полные category pools полным сканом U и сравнивает каждое поле query, canonical bytes lock и evidence.
- [e1_seal.py](../../tools/e1_seal.py) — workload `candidate-seal` foundation workflow. Builder получает world, порядок occurrences и sources которого переставлен ключом run ID. Lock записывается только после verifier status `ok`.
- [test_e1_candidates.py](../../tests/test_e1_candidates.py) — 85 tests: все 56 adversarial cases V01–V56 и 18 properties P01–P18 research spec §§13–14 (P16 — builder против verifier на 36 сгенерированных worlds). `test_matrix_complete` требует, чтобы каждый ID был привязан к test. [test_e1_seal.py](../../tests/test_e1_seal.py) offline пересчитывает lock, selection и coverage, прогоняет verifier и сверяет оба run.

Mutation check тестов: 25 из 28 мутантов builder/verifier убиты. Из трёх выживших два — неэффективные patches, третий эквивалентен (проверка split в `eligible` дублируется bucket по split и `X_U`). Review тестов нашёл две реальные недоработки до seal: `make_lock` не проверял форму query, а сравнение verifier не различало `true` и `1`. Обе исправлены до runs. Финальная byte-проверка verifier уже ловила второй случай.

## Actions evidence

Оба runs на commit `45d3bf1`, workload `candidate-seal`, status `ok`:

| Run | Order key | Builder iteration order | Lock |
|---|---|---|---|
| [37202367307](https://github.com/definitely-stable/Shift-lab/actions/runs/37202367307) | `37202367307-1` | `d6dcad9c…` | `cb16d53b…` |
| [37202375349](https://github.com/definitely-stable/Shift-lab/actions/runs/37202375349) | `37202375349-1` | `6dd7886c…` | `cb16d53b…` |

Lock, selection, coverage и verification report совпадают байт в байт при разных порядках итерации. Verifier: 32 391 ожидаемых и фактических позиций, 0 missing, 0 extra. Research-docs CI на том же commit прошёл со всеми tests. Seal reports, foundation `run.json` и verification reports сохранены в [runs](runs) и закреплены в seal record.

## Результат построения

Это structural accounting, а не результат качества.

- U: 32 391 occurrences, 28 477 content classes, 0 cross-split classes. `T_all` = 21 724; 10 667 occurrences не targets только по ordinal 1.
- Identity: 3 914 / 21 724 по всем targets; 15 / 79 среди посещённых. Ни одна из этих долей не является denominator near recall.
- Schedule: 50 groups, 2 rounds, остановка при 64 near targets. В lock 79 queries: 64 near и 15 identity. Near с пустым pool нет. `planned_pairs_per_codec` = 1 961.
- Selected bases: same-path 97, same-family 986, foreign 878. Shortage встречается у same-path в 30, same-family в 35 и foreign в 41 near queries. Truncation — у same-family в 28 и foreign в 23. Padding нет.

| Component / split | `T_all` | Identity (all) | Near selected | Identity visited | Pairs |
|---|---:|---:|---:|---:|---:|
| bzip2 / evaluation | 170 | 16 | 9 | 1 | 106 |
| curl / calibration | 5 448 | 1 568 | 12 | 1 | 232 |
| libpng / development | 1 280 | 508 | 9 | 2 | 383 |
| sqlite / development | 10 230 | 73 | 16 | 0 | 655 |
| zlib / development | 1 104 | 775 | 5 | 9 | 74 |
| zstd / development | 3 492 | 974 | 13 | 2 | 511 |

Pairs по lane: historical (file) 115, modeled 1 846. Полные cells, включая нулевые strata, — в [coverage.json](coverage.json).

## Ограничения

- Exploratory pilot. Шесть singleton components — верхняя граница независимости (A08). Held-out lineage — одна в calibration (curl) и одна в evaluation (bzip2). Confirmatory sufficiency не установлена.
- В evaluation нет file track. Calibration и evaluation содержат по одной family, поэтому их foreign pools всегда пусты. Это известно заранее и не является результатом.
- Temporal claim retrospective и version-indexed (A07). Chunk, tar и tar-gz — modeled lane, не historical replay.
- Оба runs используют один commit и одну реализацию каждого слоя. Независимость здесь — между кодом builder и verifier, а не между авторами.
- Seal не закрывает DELSK-002. Остаются Slice F (foundation handoff) и DELSK-003 oracle.
