# DELSK-002 E1: sealed candidate universe

Статус: **SEALED** с момента merge в `main`. Машиночитаемая запись — [seal.json](seal.json). Lock построен строго по [E0 construction contract](../e0/construction-spec.md) (A01–A10, §4, §7) из полного hash-bound U pilot-v1. Scorer, encoder, oracle, patch costs и utility results не существуют и не читались; seal не является measurement и не даёт quality verdict.

## Что запечатано

| Artifact | SHA-256 |
|---|---|
| [candidate-lock.json](candidate-lock.json) (`delsk.candidate.lock.v2`) | `cb16d53b164ff393187e0115bdf31c52ac717a5172fb1e91889b5988ac019d2e` |
| [selection.json](selection.json) — schedule trace, per-category pool evidence (§7.2), per-target base accounting и category/representative witnesses (§17.2) | `23db37338d3c9413ddb4186f2d7a86d3a480c02cc15808f0b5eff34f0f99eb8e` |
| [coverage.json](coverage.json) — coverage contract (§8, research spec §17.2) | `fff71554f28fea2b1628ac9f430e4d542f0147e30bcdc43e64887265f6cade5c` |

Bindings lock равны `candidate_lock_bindings` в [E0 freeze](../e0/freeze.json): corpus lock (decompressed canonical), selection policy, construction spec, protocol, ancestry audit, acquisition freeze и historical-bytes evidence. Seed `20261004`, caps 2/30/32, `max_targets=64`, pair cap 4096 не изменены.

**Closed inputs.** Spec §7.1 перечисляет восемь inputs, а A06 привязывает `protocol_sha256`. Поэтому builder и verifier дополнительно принимают точные bytes protocol, закреплённые в E0 freeze. Других inputs нет. Это прочтение записано в `seal.json` (`interpretations`) и не меняет construction spec.

## Реализация

- [candidates.py](../../tools/candidates.py) — builder. Admission закрытого набора frozen inputs по точным hashes; полный U; identity classification всех `T_all`; A02 round-robin; existential categories; total-order first-N; minimum representative; закрытые v2 bytes; coverage. Для каждой selected near query evidence хранит stage accounting всего U (первый непройденный этап, eligible aliases, классы полного pool, exact duplicates), а для каждой base — category witness (минимальная eligible occurrence, доказывающая category) рядом с representative. Ключи world, sources, occurrences и params закрыты: score, codec или result field — ошибка (A10). `make_lock` проверяет закрытую v2-форму: SHA-256 IDs, status, целые counts и pair sum, caps и сортировку. Отказ — без near query, при расхождении pair sum и превышении cap.
- [candidate_verify.py](../../tools/candidate_verify.py) — независимый verifier (A09). Не импортирует builder. Из `manifests.py` берёт только strict loader и canonical serializer. Слой 1 строит ожидаемое множество позиций `(source, track, path, offset, length, options)` из `source-lock` retained members и сравнивает его с corpus lock как множества вместе с object/parent/stratum bindings и суммой bytes. Слой 2 заново выводит `T_all`, identities, traversal и полные category pools полным сканом U и сравнивает каждое поле query, canonical bytes lock и evidence целыми строками. Evidence должна быть закрытым списком без повторов target. Verifier сам перепроверяет I33: license-excluded member внутри tar запрещён.
- [e1_seal.py](../../tools/e1_seal.py) — workload `candidate-seal` foundation workflow. Builder получает world, порядок occurrences и sources которого переставлен ключом run ID. Lock записывается только после verifier status `ok`.
- [test_e1_candidates.py](../../tests/test_e1_candidates.py) — все 56 adversarial cases V01–V56 и 18 properties P01–P18 research spec §§13–14 (P16 — builder против verifier на 36 сгенерированных worlds), плюс regression tests review. `test_matrix_complete` требует, чтобы каждый ID был привязан к test.
- [test_e1_mutants.py](../../tests/test_e1_mutants.py) — закоммиченный mutation check в CI. 37 semantic mutants (23 builder, 14 verifier) должны быть убиты. Каждый patch обязан встречаться в исходнике ровно один раз, поэтому не может молча стать no-op. Два эквивалентных мутанта записаны отдельно с обоснованием, и тест требует, чтобы они выживали. Пробелы, найденные этим check, закрыты тестами там же.
- [test_e1_seal.py](../../tests/test_e1_seal.py) offline пересчитывает lock, selection и coverage, прогоняет verifier, сверяет оба run и проверяет lock по [candidate-lock-v2.schema.json](../e0/candidate-lock-v2.schema.json) test-only evaluator используемых keywords. Все три test files закреплены в `seal.json`.

## Actions evidence

Seal runs на commit `aebf467`, workload `candidate-seal`, status `ok`:

| Run | Order key | Builder iteration order | Lock |
|---|---|---|---|
| [37205165066](https://github.com/definitely-stable/Shift-lab/actions/runs/37205165066) | `37205165066-1` | `f9bf4b9e…` | `cb16d53b…` |
| [37205172692](https://github.com/definitely-stable/Shift-lab/actions/runs/37205172692) | `37205172692-1` | `659068cc…` | `cb16d53b…` |

Lock, selection, coverage и verification report совпадают байт в байт при разных порядках итерации. Первые runs [37202367307](https://github.com/definitely-stable/Shift-lab/actions/runs/37202367307) и [37202375349](https://github.com/definitely-stable/Shift-lab/actions/runs/37202375349) на `45d3bf1` дали те же lock bytes. Их selection evidence не содержала accounting и witnesses §17.2, поэтому они superseded. Записи сохранены и закреплены, но seal на них не опирается. Verifier: 32 391 ожидаемых и фактических позиций, 0 missing, 0 extra. Research-docs CI на `aebf467` ожидаемо падал только на `test_e1_seal`: seal record ещё ссылался на старый код. Финальный head с обновлённым seal зелёный. Seal reports, foundation `run.json` и verification reports сохранены в [runs](runs) и закреплены в seal record.

## Результат построения

Это structural accounting, а не результат качества.

- У всех 1 961 selected bases natural pilot category witness совпадает с representative, а exact duplicates у near queries нет: mixed-alias classes в этом U отсутствуют (research spec §17.1). Расхождение witness и representative проверяется на synthetic fixtures (golden vector A04).

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

## Разбор review PR #21

| Замечание | Решение |
|---|---|
| Durable evidence не покрывала §17.2: per-target accounting и category/representative witnesses (blocking) | Добавлены в `selection.near_queries`. Verifier выводит их независимо и сравнивает строки целиком. Evidence перегенерирована двумя новыми runs; lock bytes не изменились |
| `make_lock` не проверял всю v2-форму | Проверяются SHA-256 IDs, status и целые типы counts и pairs (`CandidateError` вместо `TypeError`) |
| Verifier схлопывал повторный evidence row | Rows и lock queries должны быть закрытым списком без повторов target с точным числом строк |
| `seal.json` не закреплял `test_e1_seal.py` | Закреплены все три E1 test files |
| Closed inputs шире §7.1 (`protocol`) | Принято как прочтение A06 и записано в `seal.json`; spec не меняется |
| I33 проверялся только builder | Verifier проверяет I33 независимо (`derive`) |
| Mutation claim невоспроизводим | Заменён закоммиченным [test_e1_mutants.py](../../tests/test_e1_mutants.py) |
| Workload писал `refused` при исключении; lock не проверялся по schema | Status `failed`; schema test в `test_e1_seal.py` |
