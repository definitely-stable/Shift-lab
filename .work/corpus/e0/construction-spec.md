# DELSK-002 E0: candidate construction contract

Статус: **ADOPTED — E0 FROZEN_DESIGN** с момента merge в `main` (governance — §1). Идентичность принятых bytes и evidence — в [freeze.json](freeze.json). Документ нормативен для будущего E1 builder и независимого verifier. Он не запечатывает `C_t`, не содержит candidate lock и не разрешает scorer, encoder или oracle.

Исследовательская основа — [E0 adversarial specification](../../research/DELSK-002-E0-candidate-universe.md), SHA-256 `0d5b6137623651b5f6ff0ea92427bc217e5b348c889d8aeedfc5b986709203e9`. Её §§3–4, 6–7, 10–11, 13–14 и 17.2 становятся нормативными **с решениями ниже**. Где ниже сказано иначе, действует этот документ. Verdict `E0 NOT READY` в спецификации относится к её snapshot `e6c96bb`; его причины закрыты здесь.

## 1. Governance

- **Кто принимает.** Maintainer Shift-lab, merge PR с этим документом и `freeze.json` в `main`. Merge commit — акт adoption; hashes в `freeze.json` — идентичность принятого. Две внешние рецензии спецификации прочитаны до adoption. Их замечания учтены в §9; рецензии не являются evidence и не заменяют CI.
- **Когда решения приняты.** До реализации candidate selector, scorer и encoder. Ни одного candidate, score, patch cost или encoder result в репозитории нет. Поэтому решения A01–A10 не могли зависеть от utility.
- **Изменения.** Документ и вся привязанная evidence неизменяемы. Любое семантическое изменение оформляется новым versioned файлом (`construction-spec-v2.md`) и новым freeze record. Старые bytes и записи сохраняются. Изменение после просмотра evaluation results требует новой версии protocol и нового held-out, как в DELSK-P1.
- **Чего adoption не делает.** E0 freeze не делает E1 seal. Seal требует реализации по §7, adversarial и metamorphic tests в Actions и двух независимых пересчётов одного lock.

## 2. Привязанные inputs

| Input | SHA-256 exact repository bytes |
|---|---|
| Protocol `delsk.protocol.v1` | `a0c518247d111e8ad1294562d65eb34c28da87c7027c009efb64a39e6f4e0038` |
| Source plan | `75d879fd50ba8d7c749694ab091a61fa59c20ddc5fa3689a0e592692ae221074` |
| Selection policy (B) | `539642ffb9a65f4fe49f42ea99d26b416c2ab40583021b3fe8d2aa8d415cbd50` |
| Source lock | `2154224d9b8af255f4f48662b7f03a6b9865c3e976079dbad33c939eb3a5903c` |
| Corpus lock, decompressed canonical JSON | `e5c288256bed284572a9f111186411517b4c73d097d13aea4cf48e2fb9f6fffa` |
| Corpus lock, gzip file | `86009552183230ab13f9366684eedb4fcfcea746b25cbbed10ab2aabceb8f56b` |
| Acquisition freeze (D) | `8814ce0221b2b890f1710476da0c1a31771e7528d81cfc3a99ffa10acc88e8da` |

Ни один из этих файлов не изменён. Seed `20261004`, caps 2/30/32, `max_targets=64`, `planned_pairs_per_codec_max=4096`, roster, splits и thresholds DELSK-P1 остаются прежними.

## 3. Решения A01–A10

Каждое решение выбирает одну из интерпретаций спецификации §16.2. Альтернативная интерпретация отвергнута и не может использоваться под этим contract.

| ID | Решение | Отвергнуто | Следствие |
|---|---|---|---|
| A01 | Глобальный cross-split quarantine сохраняется. `X_U` вычисляется по всему raw U до query filtering, включая future, excluded и unknown-time aliases (B:22, M:538–557). Temporal claim — retrospective sample с per-pair eligibility, **не** online causal catalog simulation. Alias invariance — только три ограниченных свойства спецификации §6. | Требование «ineligible alias ничего не меняет» и «alias count не влияет на число кандидатов»: доказуемо несовместимо с B (§6, V53). | Causal simulation требует новой policy и отдельного lock. Тесты не могут утверждать blanket `seal(U+alias)=seal(U)`. |
| A02 | Группы `g=(family_id, track, stratum or "")` содержат **все** `T_all`, включая identity targets. За round каждая непустая группа отдаёт ровно одну occurrence. Identity потребляет turn группы, но не near quota. Остановка — сразу при 64 selected near targets или при исчерпании. В lock входят все посещённые queries: identity и near. Near с пустым `F_t` занимает slot. | Prefilter identities и добор из той же группы. | Целевая выборка однозначна; golden vector `identity-consumes-group-turn` (V40). |
| A03 | `duplicate_of = min{id(b) : b ∈ D_t}` по полному eligible `D_t`. | Любой eligible duplicate (v1 M:664–668). | Один lock на один universe (V39). |
| A04 | Category класса определяется экзистенциально по **всем** eligible aliases: `same_path_historical` если есть alias с `(family, member_path, offset)` = target; иначе `same_family_decoy` если есть alias той же family; иначе `foreign_family_decoy`. Representative на category не влияет. | Category по representative или по первому alias. | Сохраняет executable semantics M:612–619 (V38). |
| A05 | Все ranks — total orders с secondary key (§4). | Stable sort по порядку входа. | Нет зависимости от iteration order при совпадении digest (V52). |
| A06 | Только закрытый `delsk.candidate.lock.v2` ([schema](candidate-lock-v2.schema.json)). Bindings: `corpus_lock_sha256` (decompressed canonical D lock), `selection_policy_sha256`, `construction_spec_sha256` (bytes этого документа), `protocol_sha256`, `ancestry_audit_sha256` ([ancestry-audit.json](ancestry-audit.json)), `acquisition_freeze_sha256` (D freeze; транзитивно source lock, licenses, materialization) и `historical_bytes_sha256` ([historical-bytes.json](historical-bytes.json)). Каждый factual input этого contract привязан напрямую. Лишние ключи — ошибка. v1 и v1 extra keys для E sealing не используются. | Permissive v1 и sidecar. | Два исполнителя не могут разойтись extras или скрытыми правилами. Code SHA, run time и environment — только в run evidence. |
| A07 | Eligibility clock остаётся release interval из B. Evidence (§5) устанавливает **pairwise ordering**: для всех 62 пар sources, которые E может использовать, exact archive bytes base публично засвидетельствованы раньше `lo(target)`. Base никогда не берётся из будущего. Это **не** доказывает, что exact bytes каждого target существовали внутри его release interval: у 11 из 18 archives первая запись позже `hi(release)` (до ~203 дней). Такие snapshots — retrospective, version-indexed. Chunk, tar и tar-gz — modeled lane. | Безусловное «bytes были доступны в дату release»; literal historical availability для всех 18 archives. | Selection и time rule не меняются; claim ограничен тем, что доказано. |
| A08 | Ancestry проверен bounded audit всех 15 пар на acquired snapshots (§6): shared origin между families roster не установлен, каждый generated lead имеет reviewed disposition. Шесть singleton components — exploratory **upper-bound** assignment, не доказанная независимость. | «Шесть labels достаточно»; «singleton components confirmed». | Split assignment 4/1/1 без изменений; STOP не требуется. Confirmatory cohort требует второго, менее хрупкого clone signal (§6). |
| A09 | Seal допускается только из полного hash-bound U (corpus lock `e5c288…`) и проходит двухслойную независимую проверку (§7). Schema-valid subset, replacement или reduced reference не являются authority. | «Schema-valid supplied subset». | Недобор bases, неверный first-N и cherry-picked targets отвергаются (V42, V43, V46). |
| A10 | Construction API принимает только закрытые frozen metadata inputs §7.1. Score, patch cost, codec, encoder, result fields и callbacks — ошибка, а не молча отброшенные поля. Scorer получает проекцию `{object_id, bytes}` только после seal. | «Игнорировать result fields». | Score-free construction проверяема по API и imports (V29–V31). |

Exclusion attribution спецификации §17.2 — precedence `source → member → object → occurrence → unknown_time → target_ordinal` и для bases `self → split → track/unit → unknown_time → temporal → exact_target_class → category_truncation` — принимается как diagnostics. Eligibility по-прежнему определяется конъюнкцией predicates.

## 4. Total orders

```text
Hc(v) = SHA-256 compact canonical JSON (manifests.py; без пробелов, без final LF, Unicode не escaped)
candidate key(t, x)  = (Hc(["candidate", 20261004, id(t), x]), x)
target key(t)        = (Hc(["target", 20261004, id(t)]), id(t))
group key(g)         = (Hc(["target-group", 20261004, family_id, track, stratum or ""]), g)
representative(x)    = min id(b) over A_t(x)
duplicate_of(t)      = min id(b) over D_t
final storage order  = queries by target occurrence ID; bases by object ID
candidate_list_sha256 = Hc(sorted selected object IDs)
```

Hex digests сравниваются как ASCII-строки, что эквивалентно unsigned digest bytes. При равенстве digest решает второй элемент tuple. `""` вместо null stratum используется только в group key, не в serialized stratum. Запрещённые inputs ranking: score, patch cost, codec identity и options, compressibility, порядок перечисления, время acquisition или run, representative ID, utility.

Алгоритм — спецификация §4, шаги 1–13. Категории — §10. Prefix каждой категории содержит ровно `min(cap_k, |F_t^k|)` классов. Shortage не заполняется другой категорией. `planned_pairs_per_codec` равен сумме `candidate_count` только near queries; identity добавляет 0. Seal требует хотя бы одной near query (M:700–703); near queries с пустым pool допустимы.

## 5. A07: historical-byte evidence

Вопрос: были ли **именно эти** bytes публично доступны раньше, чем target, который их использует как base? Два скачивания 2026 года доказывают только воспроизводимость acquisition.

Метод ([historical-bytes.json](historical-bytes.json)). Run 37197318303 заново получил все 18 archives (SHA-256 и size равны D source lock) и записал их SHA-1 и MD5. Эти digests сравнены с датированными публичными записями трёх видов:

| Вид записи | Sources | Что даёт |
|---|---|---|
| Wayback Machine CDX: payload SHA-1 захватов archive URL, его mirrors и прежних официальных адресов | bzip2, curl, SQLite, zlib (12) | Третья сторона: эти bytes отдавались публично в момент захвата |
| SourceForge RSS: MD5, size и время upload файла | libpng (3) | Запись платформы: upload в день release, MD5 и size совпадают |
| GitHub release assets: archive и SHA-256 sidecar, загруженные с release, `updated_at` = `created_at` | zstd (3) | Запись платформы: asset не заменялся с публикации; SHA-256 sidecar равен D lock |

Результат:

- Для всех 18 archives есть хотя бы одна запись с теми же bytes. Архивных захватов с **другими** bytes по проверенным URL нет; найденные несовпадения — только HTML redirect или error pages.
- Не позже `hi(release)` засвидетельствованы 7 archives: SQLite и libpng (по 3) и zstd-1.5.6. Ещё 3 — сразу после `hi`: zstd-1.5.5 и 1.5.7 (asset загружен через 35 и 26 с после момента release) и zlib-1.3.1 (захват zlib.net через 2,3 ч). У остальных 8 первая запись на 10–203 дня позже: bzip2 (1.0.6 — bzip.org, 2010-11-20), curl, zlib-1.2.13 и 1.3.
- E может использовать 62 ordered пары sources (одна split, target ordinal 2/3, `hi(base) < lo(target)`). Во **всех 62** archive bytes base засвидетельствованы раньше `lo(target)`.

Что из этого следует. Доказано **pairwise no-future-base ordering**: ни одна пара E не использует base, чьи exact bytes не были публичны до cutoff target. Не доказано, что exact bytes каждого target существовали внутри его release interval: для 11 archives замена файла до первой записи не исключена, хотя ни одна contrary capture её не показывает. Такие target snapshots считаются retrospective, version-indexed. Leakage это не создаёт: если target на самом деле появился позже даты release, eligibility только консервативнее. Selection и time rule не меняются.

Допущения: целостность записей Wayback и платформ; стойкость SHA-1 и MD5 ко второму прообразу (для уже существующих archives она не нарушена); для SourceForge дополнительно совпадает size. Members извлекаются из archive детерминированно, поэтому ordering переходит на retained members и file track. Временная модель B (release intervals, strict `hi_b < lo_t`) не меняется; записи не стали новым clock.

## 6. A08: ancestry audit

Workload `ancestry-audit` ([ancestry_audit.py](../../tools/ancestry_audit.py)) в foundation job заново получил все 18 frozen archives, сверил bytes, inventories и retained-member ledgers с D source lock и просканировал каждый из 3 357 retained members. Три runs, все status `ok`, с одинаковыми SHA-256 и SHA-1 всех 18 archives:

| Run | Commit | Изменение | Статус |
|---|---|---|---|
| [37196309671](https://github.com/definitely-stable/Shift-lab/actions/runs/37196309671) | `3b620c1` | первый audit | superseded: нет positive control |
| [37196505949](https://github.com/definitely-stable/Shift-lab/actions/runs/37196505949) | `960e9e5` | + within-family positive control | evidence `14bb698f…` |
| [37197318303](https://github.com/definitely-stable/Shift-lab/actions/runs/37197318303) | `abaaf6d` | + MD5 archives для §5 | **текущий**; evidence байт в байт та же `14bb698f…` |

Совпадение evidence двух runs на разных commits показывает детерминизм workload. Evidence `origin-evidence.json.gz` и все run reports сохранены в [runs](runs) и закреплены в freeze.

Результат, записанный в [ancestry-audit.json](ancestry-audit.json):

- **Exact shared text.** 0 общих 12-line windows и 0 одинаковых member objects для всех 15 пар. Positive control того же detector: между releases одной family найдено от 4 325 (bzip2) до 187 563 (SQLite) общих windows. Ноль между families — не отказ detector.
- **Leads по упоминаниям проектов.** bzip2→zlib (описание zlib-like API), curl↔zlib и curl↔zstd (опциональная линковка; zstd regression tests используют libcurl API), libpng→zlib (линковка; bound «based on deflateBound()» вычисляется собственным кодом), SQLite→zlib (shell extensions). Все — `no_shared_payload`. zlib↔zstd: plan edge `shared origin`, `path_excluded zlibWrapper/*`; после исключения общего текста нет — исключение достаточно на проверенном уровне.
- **Внешние origins.** LibTomCrypt, libmicrohttpd, rtmpdump, DJTAR и Heimdal gssapi.h (curl), Fossil и Keccak (SQLite), FSE/Huff0, xxHash references, folly CpuId и код G. Ottaviano (zstd). Каждый встречается ровно в одной family roster и не связывает две families. OpenSSL, SHA-1 и Unicode — стандартная лексика без общего текста.
- **Полнота review.** [origin_leads.py](../../tools/origin_leads.py) детерминированно выводит из evidence 598 leads со стабильными ID: упоминания других проектов по (family, path), provenance markers и notices с именами авторов других families. В audit у каждого ID ровно одна disposition; `unresolved` вычисляется из dispositions. CI требует точного равенства множеств generated и reviewed leads ([test_e0_freeze.py](../../tests/test_e0_freeze.py)). Unresolved leads нет.
- **Итог.** В пределах этого bounded audit shared origin между families roster не установлен; merges и новых exclusions нет. Split counts development 4 / calibration 1 / evaluation 1 без изменений.

Границы: detector находит только точный последовательный текст. Positive control показывает чувствительность к почти неизменённым копиям, но не оценивает false negatives для изменённого или переформатированного shared code. Поэтому шесть singleton components — exploratory **upper-bound** assignment, а не подтверждённая независимость. Held-out lineage count = 1 per split, exploratory статус pilot не меняется. Для confirmatory cohort нужен второй, менее хрупкий clone signal (normalized-token или winnowing fingerprints) с disposition найденных leads.

## 7. E1 contract

### 7.1 Inputs

`plan, policy, source_lock, corpus_lock, acquisition_freeze, ancestry_audit, historical_bytes, construction_spec` — strict canonical bytes с ожидаемыми hashes из §2 и [freeze.json](freeze.json). Других inputs нет. Unknown field, unknown recipe или mismatch hash → отказ без частичного вывода.

### 7.2 Двухслойная независимая проверка (A09)

Verifier не импортирует selector, category или scheduler E1 и не использует их как oracle.

1. **Source → U.** Из `source-lock.sources[].retained` независимо построить ожидаемое множество позиций `(source, track, path, offset, length, options)`: file winner в каждом stratum по member rank, каждый полный chunk каждого retained parent для каждого unit, ровно один tar и один tar-gz на release. Сравнить точное множество с corpus lock, привязки source/object/parent и сумму bytes. Совпадение counts без равенства множеств недостаточно.
2. **U → queries.** Независимо перечислить `T_all`, классификацию identity, traversal A02 и для каждой выбранной near query полный `F_t^k` по категориям. Проверить cardinalities, точные prefixes, representatives, `duplicate_of`, list hashes, pair sum и canonical bytes всего lock.

Для каждой selected near query и категории evidence хранит размер полного pool, `Hc(sorted full-pool IDs)`, selected IDs, последний selected key, shortage и truncation. Два независимых Actions runs должны получить один semantic lock при разных iteration orders.

### 7.3 Обязательные tests до seal

Все 56 adversarial cases и 18 properties спецификации §§13–14 с ожидаемыми исходами оттуда. Concrete golden vectors V01, V23, V28, V38, V39, V40, V47, V52 уже закреплены в [golden-vectors.json](golden-vectors.json) и проверяются в CI ([test_e0_vectors.py](../../tests/test_e0_vectors.py)): каждый hash пересчитывается, а ожидаемые queries и traversal воспроизводит медленный test-only reference evaluator правил этого документа. Mutant tests там же показывают, что vectors различают правила: max вместо min для `duplicate_of` и representative, нестрогая граница времени, identity в near quota и отключённый same-family precedence — каждый проваливает хотя бы один vector. E1 builder обязан давать те же bytes, но не может импортировать этот evaluator.

## 8. Coverage contract

Спецификация §17.2 принимается без изменений: rows для всех planned `(component, family, split, track, stratum)` cells, включая нули; раздельные denominators all-target, encountered и selected-near; identity rate не является near recall denominator. Структурные факты пилота известны заранее и не являются результатом: в evaluation (bzip2) нет file track; в calibration и evaluation по одной family, поэтому foreign pools там всегда пусты.

## 9. Учёт рецензий

| Замечание | Решение |
|---|---|
| A01–A06, A09, A10 — semantic decisions, принимаются до encoder/scorer | Приняты в §3 |
| A07 и A08 нельзя «принять решением», нужна evidence | Закрыты фактами в доказанном объёме: §5 (pairwise ordering для 62/62 пар по датированным публичным записям) и §6 (bounded audit всех 15 пар на acquired snapshots) |
| Нужна двухслойная проверка source→U и U→queries | §7.2 нормативно |
| Нет governance для rulings | §1 |
| Противоречие в спецификации §2.3 о локальных probes | Исправлено: контрпримеры выведены статически, локальные вызовы validator evidence не являются |
| Не оценена трудоёмкость ancestry audit | Фактически: три foundation runs по ~1 мин и review leads. Метод масштабируется на новые families тем же workload |
| Независимость двух аудитов недоказуема изнутри workspace | Принято как ограничение процесса. Решения опираются на воспроизводимые hashes и Actions evidence, а не на согласие аудитов |
| PR review: A07 overclaim (target bytes вне release interval у 11/18) | A07 сужен до pairwise no-future-base ordering; delayed target snapshots — retrospective, version-indexed (§3, §5) |
| PR review: lock v2 не привязывал D freeze и A07 evidence | `acquisition_freeze_sha256` и `historical_bytes_sha256` добавлены в schema, golden lock vector, freeze и tests (A06) |
| PR review: полнота A08 review не проверялась CI | Stable lead IDs и exact set closure generated = reviewed; `unresolved` выводится (§6) |
| PR review: «components confirmed» сильнее exact-text evidence | Формулировка сужена до bounded audit и upper-bound assignment; второй clone signal — требование confirmatory cohort (A08, §6) |
| PR review: утверждение о mutation tests не подкреплено кодом | Добавлены `MutantTests` в test_e0_vectors.py (§7.3) |
