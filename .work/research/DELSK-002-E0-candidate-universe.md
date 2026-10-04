# DELSK-002 Slice E0: adversarial specification candidate universe

Дата: 2026-10-04, Asia/Yekaterinburg. Scope: R0 exploratory pilot, ancestry audit и построение `C_t` **до implementation**. Статус документа: research specification на snapshot `e6c96bb`; verdict ниже — **E0 NOT READY** на тот момент. Решения A01–A10 приняты отдельно в [E0 construction contract](../corpus/e0/construction-spec.md), который закрепляет bytes этого документа по SHA-256 и закрывает A07/A08 фактической evidence. Сам документ не является действующим frozen contract.

## 1. Executive verdict

**Slice D существует и frozen в своей acquisition scope. E0 пока не freeze-ready.** На `main` сохранён полный metadata universe, поэтому отсутствие corpus lock больше не является блокером. Однако B/D artifacts и текущий candidate validator допускают разные candidate locks для одних входов. Кроме того, безусловная invariance к добавлению aliases несовместима с принятой cross-split policy и category precedence.

Ниже дан один точный **рекомендуемый** алгоритм, явно отделённый от уже принятых правил. Его новые решения обозначены `A01`–`A10` в §16. Они не применены к frozen plan/policy/locks. Пока решения не приняты и не связаны hash с E contract, второй implementer вправе получить другие bytes. Поэтому итог — `E0 NOT READY`, а не `BLOCKED BY SLICE D` и не разрешение начинать sealing.

Основные blockers:

1. Не определены полностью target scheduling с identity-only, состав identity rows и canonical `duplicate_of`.
2. Проверки v1 допускают недобор bases, неверный first-N и произвольное подмножество targets; canonical JSON сам по себе не доказывает canonical **selection**.
3. Требование «любой ineligible alias ничего не меняет» ложно при global cross-split exclusion; eligible alias может изменить category, representative и конкуренцию за cap.
4. Release dates и `FROZEN_ACQUISITION` не завершают доказательство historical availability exact bytes или retained-payload ancestry audit.
5. Нет принятой привязки construction specification, ancestry evidence и полноты universe к candidate artifact; дополнительные поля v1 не имеют закрытой schema.

В E0 не создавались `candidates.py`, `candidate-lock.json`, encoder/scorer results, patch costs или новые acquisition runs. Thresholds, denominators, verdict rules, seed, roster, splits и frozen B/D bytes не изменены. Таблицы ожидаемых исходов ниже — preregistration proposals, **не отчёт об исполненных tests**.

## 2. Repository truth / exact SHAs

GitHub API проверен 2026-10-04: `main = e6c96bbf47cf5349a66f5361f00253bd361260b3`; открытых PR нет; issues #1–#14 открыты, у каждой 0 комментариев. [PR #19](https://github.com/definitely-stable/Shift-lab/pull/19) merged, head `2c46490f20d5e27eddcf7171faaed00a58952756`, merge commit — указанный `main`; Git trees head и main совпадают. Локальный checkout перед работой чистый. Документ подготовлен на ветке `docs/delsk-002-e0-spec` от этого main.

Live [DELSK-000](https://github.com/definitely-stable/Shift-lab/issues/1), [DELSK-002](https://github.com/definitely-stable/Shift-lab/issues/3), [DELSK-003](https://github.com/definitely-stable/Shift-lab/issues/4), [DELSK-005](https://github.com/definitely-stable/Shift-lab/issues/6) сверены с локальными bodies. Локальный DELSK-002 уже содержит milestone D, live issue ещё сохраняет первоначальную постановку; статус issue не отменяет freeze record. PR #19 не содержит comments/reviews/review comments. Это отсутствие дополнительного обсуждения, не независимое scientific approval.

### 2.1 Primary-source map

Все line references далее относятся к **этому main**, а не к будущему состоянию файлов.

| ID | Первичный источник и точные места | Что устанавливает |
|---|---|---|
| P | [protocol.md](../protocol.md), §§1–5 | Unit/lineage, temporal universe, dedup, empty pools, unchanged statistics |
| B | [selection-policy.json](../corpus/selection-policy.json), lines 2–24, 90–130 | Categories/caps, aliases, target order, time, lanes |
| R | [corpus/README.md](../corpus/README.md), «Canonical JSON», «Targets и C_t», «Схемы locks» | Prose contracts; validator first-N limitation |
| M | [manifests.py](../tools/manifests.py), lines 44–111, 137–203, 288–413, 427–708 | Executable canonical/rank/time/split/schema/selection validation |
| D | [materialize.py](../tools/materialize.py), lines 214–282, 296–435, 438–466 | Transform construction, all retained chunks, source/corpus outputs |
| S | [source-plan.json](../corpus/source-plan.json), lines 3–22, 244, 319–366 | Ancestry edges, acquisition provenance, SQLite historical-byte limitation |
| F | [freeze.json](../corpus/pilot-v1/freeze.json), [pilot README](../corpus/pilot-v1/README.md) | Reviewed acquisition identities/licenses; E/F expressly outstanding |
| T | [test_manifests.py](../tests/test_manifests.py), lines 59–149, 262–336, 660–844, 937–1026 | Existing positive/negative fixtures; no complete sealing implementation |
| TD | [test_materialize.py](../tests/test_materialize.py), lines 159–535; [test_pilot_freeze.py](../tests/test_pilot_freeze.py), lines 14–53 | Hostile archives, transforms, committed freeze checks |
| CI | [ci-plan.md](../ci-plan.md), [foundation.yml](../../.github/workflows/foundation.yml), [evidence template](../templates/evidence.md) | Identity/caps/retention and limits of CI claims |

The code, tests, full compressed corpus metadata, source/license locks, materialization summary and saved run reports were inspected. [Roadmap](../roadmap.md), [corpus/baseline matrix](../corpus-and-baselines.md) and issues constrain scope; they do not replace validators or evidence.

### 2.2 Identity ledger

`source SHA` означает Git commit, `protocol SHA` — SHA-256 exact repository blob `protocol.md`, а не protocol ID. Для JSON hash ниже используется canonical file form, для compressed lock отдельно raw gzip и decompressed canonical JSON. Git blob bytes следует читать через Git, без Windows CRLF conversion.

| Artifact | SHA-256 exact repository bytes |
|---|---|
| Protocol | `a0c518247d111e8ad1294562d65eb34c28da87c7027c009efb64a39e6f4e0038` |
| Source plan | `75d879fd50ba8d7c749694ab091a61fa59c20ddc5fa3689a0e592692ae221074` |
| Selection policy | `539642ffb9a65f4fe49f42ea99d26b416c2ab40583021b3fe8d2aa8d415cbd50` |
| Source lock | `2154224d9b8af255f4f48662b7f03a6b9865c3e976079dbad33c939eb3a5903c` |
| Licenses | `c7e7d7d85e17d2b4bcd31ca08c985a128fcc947f16bb1e49f99e345bc0d55f7c` |
| Materialization summary | `11e5913293bedcf74d801f5d69afd0879115c30c811fa7c45b8acbcbaab6942b` |
| Corpus lock, raw gzip | `86009552183230ab13f9366684eedb4fcfcea746b25cbbed10ab2aabceb8f56b` |
| Corpus lock, decompressed canonical JSON | `e5c288256bed284572a9f111186411517b4c73d097d13aea4cf48e2fb9f6fffa` |
| Acquisition freeze record | `8814ce0221b2b890f1710476da0c1a31771e7528d81cfc3a99ffa10acc88e8da` |
| `materialize.py` | `853a7516a1b7e8b160bd799bbfc35b578313e0fb54341977a418b89b2b2bfef8` |
| `manifests.py` | `c1b394781b2cf55e347dca5cf25b00cea422b03df695f7aea83b5283a85c30b4` |
| Foundation workflow | `bfb843591c7d76f98b90d3d7e99bd7311ca93c511b42bf9a94d6733a3dcb4ee0` |

D toolchain: Python `3.12.3`, zlib `1.3`, combined materializer identity `7f2cf01a71605769ccdb3061d478a4c10c5ba9c20426ba12281ba466f79d7da6`. Discovery source/workflow SHA `200b9c5e22d2cace1db60b932b18ccfdb86712a1`; verification SHA `ac9037ccefd316ea4e6b5c7c040cffddb2215cd0`.

Candidate lock SHA: **NOT CREATED**. E0 freeze SHA: **NOT FROZEN**. Protocol остаётся `delsk.protocol.v1`, status `PLANNED`. Source plan и selection policy сохраняют `PROPOSED` как исторические inputs; D review status находится в отдельном `freeze.json` и не требует переписывать их bytes.

### 2.3 Действительная evidence D

Discovery [37186134266 / attempt 1](https://github.com/definitely-stable/Shift-lab/actions/runs/37186134266) и verify [37186222325 / attempt 1](https://github.com/definitely-stable/Shift-lab/actions/runs/37186222325) дают одинаковые source/license/materialization identities. Verify использовал committed source lock. Сохранён полный metadata lock: **32 391 occurrences, 28 477 content classes, 446 924 313 materialized bytes, 0 cross-split content objects**. Metadata gzip — 3 924 534 B, canonical JSON — 22 414 998 B; payload в Git отсутствует.

[PR CI 37192294639](https://github.com/definitely-stable/Shift-lab/actions/runs/37192294639), head `2c46490…`, attempt 1: `success`. Это существующая проверка D, не E0/E1 scientific validity. Retained verify admission: budget mode `warn`, accounting complete, 4 used + 30 reserved runner-min; отсутствие hard refusal в этом режиме не подменяется заявлением об `enforce`. В E0 выполнены чтение и локальный read-only metadata audit. Все контрпримеры ниже выведены статически из исходного кода; никакие локальные вызовы validator на mutations не сохранены и не используются как evidence. Это не Actions evidence, не test-suite pass и не prerequisite для freeze. Encoders/scorers, benchmark и новые Actions workloads не запускались.

## 3. Formal model

Все множества конечны. Обозначения определены на **validated, hash-bound, complete** B/D inputs; при нарушении preconditions sealing не существует, а не возвращает усечённый universe.

| Сущность | Определение |
|---|---|
| Source `s` | Одна release record `source_id = release_id`, связанная с exact acquired archive SHA/size и source-plan release evidence |
| Family `f` | Versioned project identity из plan; имя не доказывает независимость |
| Ancestry component `a` | Connected component по **reviewed retained shared-origin** merge edges; minimal sorted family ID — component key |
| Split `σ` | `development/calibration/evaluation`, assigned component целиком по B; не свойство пути или transform |
| Occurrence `o` | Source + exact provenance `{member_path,transform,options,offset,length}`, ID `Hc(["delsk.occurrence.v1",source_id,provenance])`; привязка к bytes/track/family/split |
| Content class `x` | Все occurrences с одним `object_id = SHA256(payload)`; equality предполагает отсутствие обнаруженной hash collision/identity corruption |
| Representation/track `τ` | Policy track с transform/options/unit и lane; equality track обязательна, same size её не заменяет |
| Target `t` | Допустимая occurrence ordinal 2/3, известное время, нет exclusions; target unit — occurrence, не collapsed content class |
| Full materialized universe `U` | Все D occurrences всех planned releases/tracks после member construction; **не** все файлы archives и **не** storage catalog |
| Eligible occurrence | `b ∈ U`, удовлетворяющая `E(b,t)` ниже |
| Eligible content class | `x` с непустым `A_t(x)`; exact target class сначала используется для dedup |
| Identity-only target | Допустимый `t` с `A_t(x(t)) ≠ ∅`; не планирует encoder pairs |
| Full eligible universe `F_t` | Все distinct classes `x ≠ x(t)` с `A_t(x) ≠ ∅` до category caps |
| Category `k_t(x)` | Class-level relation to target, с precedence same-path → same-family → foreign, только по eligible aliases |
| Representative `r_t(x)` | Occurrence с минимальным ID в `A_t(x)`; не определяет category |
| Sampled/sealed `C_t` | Union первых `cap(k)` content classes каждой категории по fixed rank; `C_t ⊆ F_t` |

`Hc(v)` — SHA-256 compact canonical JSON; `Hf(v)` — SHA-256 canonical file bytes. `id(o)`, `x(o)`, `f(o)`, `σ(o)`, `τ(o)` — поля occurrence. `I(o)=availability(plan[source(o)].time)`. Для modeled lane это **интервал parent release**, не доказательство существования transformed bytes в прошлом (§8).

`X_U = {x : |{σ(o) : o ∈ U, x(o)=x}| > 1}`. Он вычисляется по **всем raw materialized occurrences до query filtering**, как M:552–558 и D:383–388. Даже excluded или future alias входит в этот raw membership, если он присутствует в U. Это фиксированная retrospective decontamination policy, с ограничением A01.

`L(o)` — occurrence не затронута валидным exclusion вида source/member/object/occurrence, `x(o) ∉ X_U`, license clearance данного source/retained member подтверждён D freeze, а зависимые transforms не обходят exclusion (§9). `Valid(U)` дополнительно требует approved ancestry/time scope; отсутствие этих proofs — отказ seal всего input, не новый незаписанный per-target filter.

Нормализованные predicates:

```text
T(t) := t ∈ U ∧ L(t) ∧ ordinal(source(t)) ∈ {2,3} ∧ I(t) ≠ unknown

E(b,t) := Valid(U) ∧ T(t) ∧ b ∈ U ∧ L(b)
          ∧ id(b) ≠ id(t)
          ∧ σ(b) = σ(t) = assigned_split(component(f(t)))
          ∧ σ(b) = assigned_split(component(f(b)))
          ∧ τ(b) = τ(t)
          ∧ compatible_transform_lane_unit(b,t)
          ∧ I(b) ≠ unknown ∧ I(t) ≠ unknown ∧ hi(I(b)) < lo(I(t))

A_t(x) := {b ∈ U : x(b)=x ∧ E(b,t)}
D_t := A_t(x(t))
F_t := {x : A_t(x) ≠ ∅ ∧ x ≠ x(t)}
```

Same component для base/target **не требуется**: foreign-family decoys из другого component допустимы внутри той же split. Require same component ошибочно уничтожил бы foreign category. Compatibility означает exact policy track, lane и options; chunks дополнительно full aligned span с тем же unit. File bases не обязаны иметь target stratum: B требует same track, а strata используются для materialization/target grouping. Self-content **не** удаляется из `E`: иначе identity-only branch всегда пуста. После dedup `F_t` удаляет target class целиком.

## 4. Exact candidate construction algorithm

Ниже recommended specification `E0-R1`; новые решения из §16 ещё требуют принятия. Pseudocode — design, не implementation `candidates.py`.

1. **Admit frozen inputs.** Проверить exact hashes, canonical bytes, schemas, source membership, identities, component assignment, transform closure, source→occurrence completeness (§11), reviewed license/ancestry/time scope. Unknown fields/unknown policy recipe/несогласованные hashes → failure. Никаких best-effort locks.
2. **Compute global exclusions.** Определить `X_U` на полном U; сверить object exclusions; применить scoped lock exclusions. Illegal/manual post-hoc exclusion без принятой provenance evidence → failure. Short tails и невыбранные file members не добавлять в U.
3. **Enumerate all potential targets** `T_all={t:T(t)}`. Не collapse targets по object ID. Сохранить все причины неeligibility отдельно; ordinal — только roster criterion, не clock.
4. **Classify identity for every `t ∈ T_all`** через полный `D_t`: empty → near-duplicate opportunity, nonempty → identity-only. Предлагаемый A03: `duplicate_of = min_id(D_t)`; `bases=[]`. Полная классификация нужна coverage; inclusion query в lock определяется следующим шагом.
5. **Schedule target occurrences.** Предлагаемый A02 уточняет буквальное «one per group per round»: группы содержат **все** T_all, включая identities. Группа `g=(family_id,track,stratum-or-empty-string)`. Sort groups by `(Hc(["target-group",seed,*g]),g)`; sort each queue by `(Hc(["target",seed,id(t)]),id(t))`. За round посещать каждую непустую группу один раз и снимать ровно один target, записывая query. Identity consumes group turn, но не near quota; немедленно добирать из той же группы нельзя. Остановиться немедленно при 64 selected near-duplicate targets либо exhaustion. Только encountered identity queries входят в lock; остальные остаются в all-target coverage. Empty `F_t` не удаляет near target и consumes slot.
6. **Enumerate full base pool** для каждого selected near-duplicate t: сначала все E-eligible occurrences, затем group by `object_id`. `F_t` — все классы, не только ранее записанные bases или выбранные target occurrences.
7. **Assign disjoint categories** каждому `x∈F_t` по всем `A_t(x)`, как §10. Category не может меняться при выборе representative.
8. **Rank full category pools** по `(Hc(["candidate",seed,id(t),x]),x)`. Hash rank не зависит от enumeration order, representative или scorer.
9. **Truncate each category independently:** keep exactly `min(cap(k),|F_t^k|)`. Caps 2/30/32, padding запрещён. Нельзя переносить потерянный slot в другую категорию. Shortage и truncation — разные counters.
10. **Pick representative** `min_id(A_t(x))` только для selected classes. Preserve class category; representative может иметь другую occurrence relation.
11. **Canonical order:** bases sorted by object ID; queries (encountered identities + selected near targets) sorted by target occurrence ID. Scheduling order не становится storage order. Каждая query содержит все объявленные keys, null явно.
12. **Hash and count:** `candidate_list_sha256=Hc(sorted object IDs)`; `candidate_count=len(bases)`; `planned_pairs_per_codec=Σ len(bases)` только near queries. Проверить ≤4096, целые числа без bool; identity adds 0.
13. **Independent verification:** verifier заново выводит target membership, identities и exact category first-N из полного D universe, сравнивает полные query records и canonical artifact bytes. Несовпадение → no freeze, сохраняется failure evidence. Output file записывается только после полной успешной проверки.

Минимальное число near queries для seal — 1, как M:700–703. Universe с near targets, у которых все `C_t=∅`, допустим и имеет 0 pairs; universe только с identities/без targets не sealable, но diagnostics/coverage всё равно сохраняются. Это не изменение P1 empty-pool metric rules.

## 5. Operation-order proof

| Порядок | Почему перестановка опасна / минимальный counterexample |
|---|---|
| Schema/hash/completeness → selection | Удалить лучший по rank unselected chunk и пересчитать локальные counts: subset становится «первым». Проверка только listed records этого не обнаружит |
| Ancestry/exclusions → transforms/admission | Удалить shared member после сборки tar оставляет его bytes внутри tar. После такого изменения D нужно rematerialize (§9) |
| Raw cross-split detection → temporal/track filtering | Historical development alias + future evaluation alias: global policy исключает object; фильтрация future сначала ошибочно сохраняет его |
| Scoped eligibility → representative | `id(future)<id(old)` для одинакового object: collapse-to-min сначала выбирает future или удаляет весь допустимый class |
| Scoped eligibility → category | Только future alias имеет target path: category-before-eligibility ошибочно повышает eligible foreign class до same-path |
| Identity detection → target quota/candidate removal | Удаление target bytes до dedup скрывает identity; identity consumes slot при преждевременном target truncation |
| Identity classification → quota, без удаления identity из traversal (A02) | Группа A: identity затем near; B: near. При quota 1 scan-per-occurrence отдаёт слот B, prepartition — A, если A первая |
| Full class grouping → cap | cap=2, rank order occurrences `x1,x2,y1`: truncate occurrences выдаёт только x, class truncation выдаёт x и y |
| Category precedence → category rank/cap | Один x имеет same-path и foreign eligible aliases: независимые occurrence categories дадут два slots или неверное вытеснение |
| Full ranking → cap | input order `y,x`, `rank(x)<rank(y)`, cap=1: streaming first-seen выбирает y вместо x |
| Class category → representative projection | Минимальный eligible alias foreign, другой eligible alias same-path: category(rep) ошибочна |
| Cap/representatives → canonical sorting/hash | Hash rank-ordered IDs отличается от hash object-ID ordered IDs; hash до truncation считает не `C_t` |
| Final disjoint queries → pair sum | Сумма occurrence counts или identity bases завышает число ordered encoder pairs |

Grouping всех aliases **без потери записей** может выполняться заранее как index optimization: `filter(group(U))=group(filter(U))` после удаления пустых classes. Выбирать representative/категорию заранее нельзя. Rank key class не зависит от category, поэтому можно кешировать hash раньше, но first-N определяется только после class eligibility/category. Representative selection коммутирует с cap лишь если для каждого class используется одинаковое полное `A_t(x)` и representative не участвует в ranking. Эти допустимые перестановки не разрешают сокращать universe.

При принятых A01–A10 доказательство uniqueness индуктивно: fixed inputs → fixed predicates → fixed sets → total orders с explicit tie-breaks → fixed prefixes → fixed representatives → fixed serialized bytes. Пока A02/A03/A06 не приняты, переходы target sequence и artifact bytes не единственны. Отсутствие hash collisions — явно указанное cryptographic assumption; обнаруженная identity corruption останавливает pipeline.

## 6. Alias semantics

Для object `x`, target `t` и aliases old/future/other-split/excluded/other-path/other-family:

- Old alias участвует только при E=true. Future/unknown-time/excluded alias не может быть representative и не является category witness.
- Other path/same source даёт другую occurrence ID, но не второй class. Other family может быть eligible, если split/track/time совместимы; family name сам по себе не разрешает inclusion.
- Other-split alias в raw U делает `x∈X_U`: исключаются **все** его aliases, даже historical same-split. Это не «ineligible alias сделал eligible class ineligible» внутри уже зафиксированного U: global exclusion меняет сам domain E. Но именно поэтому безусловное требование пользователя математически несовместимо с B.
- Representative = minimum только среди eligible aliases. Если его relation foreign, а другая eligible occurrence same-path, category class остаётся same-path; witness можно записать в отдельном audit, не менять representative.
- Permutation одного и того же множества aliases ничего не меняет. Повтор одного occurrence ID в manifest — invalid input, а не новый alias, который следует молча collapse.

**Три разных invariance, которые нельзя смешивать:**

1. `C_ids(t)` не содержит повторов object IDs при любом числе aliases.
2. Добавление alias, не меняющего global exclusions, E-membership существующих classes и class categories, не меняет selected object IDs. Минимальный eligible alias может изменить representative и поэтому **полные query bytes**.
3. Добавление любого нового provenance меняет corpus-lock SHA, следовательно даже при том же `C_ids(t)` полный candidate-lock не может оставаться byte-identical. Byte invariance утверждается для перестановок внутренних views одного frozen input, не для другого corpus lock.

Counterexample к «alias count не влияет на число кандидатов»: в chunk track 31 eligible same-family-decoy class `x,d1,…,d30`, x первый по rank, same-path pool пуст. Сначала selected count=30. Добавить historical same-path alias x на свободную позицию prior release. Теперь same-path pool={x}, decoy pool={d1,…,d30}; selected count=31. x учитывается один раз, но category reassignment меняет total size. Здесь не требуется невозможный третий earlier release. Требование unconditional count invariance невозможно совместить с B caps и `_category` (A01/A04). Target pool при таком сравнении должен быть фиксирован: alias в ordinal 2/3 может сам стать новым target. Ни один такой adversarial case не разрешает менять реальный roster для удобства.

## 7. Identity-only semantics

Для каждого `T(t)`:

```text
status(t) = identity_only  iff  D_t ≠ ∅
duplicate_of(t) = min {id(b): b∈D_t}                 [A03]
bases(t) = []; candidate_count(t)=0
candidate_list_sha256(t)=Hc([])
otherwise status=near_duplicate; duplicate_of=null
```

| Exact-byte case | Ожидаемая ветка |
|---|---|
| Те же bytes в strictly earlier release, same split/track | identity-only, независимо от path |
| Другой path/другая eligible family | identity-only; category не применяется к dedup |
| Только future duplicate или тот же uncertain time interval | Не identity-only; near при T=true |
| Те же bytes в другой split | Global content exclusion: target не входит T; нельзя назвать его near или identity |
| Несколько eligible duplicates | Один canonical `duplicate_of=min_id`, 0 pairs |
| Eligible + future/excluded alias, без global exclusion | identity-only по eligible minimum |
| Eligible + cross-split alias | Global exclusion, обе роли removed |

Текущий M:664–668 проверяет membership `duplicate_of∈D_t`, но не minimum. Это два легально принимаемых byte-различных v1 locks. Если `D_t` ищется только в уже selected bases, identity branch неполна. Если E отвергает `x(b)=x(t)` до проверки, identity branch невозможна. По A02 только encountered identities входят в lock, а полная identity classification относится ко всей T population; coverage различает all-target, encountered и selected-near denominators (§17).

## 8. Temporal model

Время — closed uncertainty interval в целых UTC seconds. Exact timestamp `s` означает `[s,s]`; date D означает `[D 00:00 UTC−14h, D 00:00 UTC+36h]`. База допускается только по строгому `hi_b < lo_t`. Файл mtime, момент acquisition, version string и ordinal в сравнении не участвуют (M:137–161).

| Пример | Результат |
|---|---|
| `[100,100]` → `[101,101]` | eligible |
| `[100,100]` → `[100,100]` | ineligible: equal boundary |
| `[0,10]` → `[10,20]` | ineligible: touching intervals |
| `[0,10]` → `[11,20]` | eligible |
| `[0,20]` → `[10,30]` | ineligible: overlap |
| date 2024-01-01 → date 2024-01-02 | intervals overlap; ineligible |
| date 2024-01-01 → date 2024-01-03 | hi Jan 2 12:00 > lo Jan 2 10:00; ineligible |
| date 2024-01-01 → date 2024-01-04 | hi Jan 2 12:00 < lo Jan 3 10:00; eligible |
| Unknown base / unknown target | base excluded / target excluded, отдельно в coverage |
| Версия base `1.0`, published позже target `2.0` | ineligible независимо от version comparison |
| Два разных offsets обозначают один UTC instant | equal intervals, ineligible |
| Transform создан сейчас из old source | Parent chronology допустима только в explicitly modeled lane; historical transformed-byte availability не доказана |

Внутри одной family source validator дополнительно требует строго возрастающие disjoint intervals по ordinal (M:338–340); same-day/overlap/reversed-time plan **невалиден целиком**, а не проходит с удалённой парой. Между families такие intervals возможны и E исключает соответствующие pairs. Version labels сами могут быть немонотонными — используются evidence times. Это различие должно сохраняться в adversarial fixtures.

**Предел доказательства.** Два одинаковых скачивания в 2026 году доказывают acquisition reproducibility, не first public availability exact retained bytes в 2024 году. S:319 прямо говорит, что SQLite equality с 2024 uploads не проверена; S:244/F limitations не утверждают libpng archive/git-tree equality. Это не доказательство, что bytes изменились; это отсутствие нужной historical-byte evidence. Рекомендуемый A07: либо привязать retained member hashes к immutable historically published source evidence, либо отдельным reviewed amendment сузить claim до release-indexed modeled replay/unknown historical availability. Молчаливо заменить дату на download/mtime или исключить неудобную family запрещено. D acquisition freeze остаётся действительным, E temporal claim — unresolved.

Global cross-split decontamination использует весь fixed corpus, включая future releases. Поэтому нельзя одновременно обещать prefix-causal candidate construction: появление future cross-split alias может исключить historical object. Рекомендуемое A01 сохраняет B как retrospective sampling с temporal eligibility каждой пары и явно запрещает называть его online causal catalog simulation. Если требуется строго причинная simulation, нужна новая policy и отдельный lock, не незаметное изменение E.

## 9. Ancestry model

| Отношение retained bytes | Решение до seal | Почему |
|---|---|---|
| Fork / renamed project / copied first-party source | Merge ancestry components с evidence | Общий ancestor связывает statistical units |
| Vendored/common upstream component | Path exclusion до transforms, если полное удаление доказано; иначе merge affected families | Частичное удаление оставляет shared payload |
| Shared generated origin | Проследить generator inputs/templates; retained common payload → merge или preregistered path removal | Разные output names не создают независимость |
| Build/link dependency без retained shared bytes | `no_shared_payload`; dependency сама по себе не merge | Linking relation не означает общий corpus payload |
| Transformed copy (chunk, tar, compression) | Inherits source component/split; не новая independent lineage | Transform сохраняет общий source origin |
| Identical bytes cross-family | Retain aliases; cross-split exclusion при разных splits; расследовать origin | Equality chunk сама по себе не доказывает genealogy |
| Common contributor/copyright name | Не автоматическая merge; нужна provenance retained payload | Авторство не тождественно shared source ancestry |
| Неясный copied/generated origin | BLOCKING audit finding; не `no_shared_payload` по умолчанию | Unknown нельзя превратить в independence |

Source plan содержит две resolved edges: libpng↔zlib `no_shared_payload` и zlib↔zstd `path_excluded` для `zlibWrapper/*`. D license review расширил curl path exclusions. Это полезная evidence, но label `independent_project`, 0 cross-split exact objects или root license **не доказывают** отсутствие partial copied/shared payload. `path_excluded` validator проверяет наличие glob в одной из двух families, а не его достаточность для устранения origin (M:341–350). Generic free-text relation допускает противоречивые пары edges; required audit должен отвергнуть unresolved conflict.

Предлагаемый A08: отдельный pinned ancestry audit для всех 15 unordered pairs шести families, плюс external-origin register (один внешний origin может связывать два проекта, даже если не входит в roster). Каждая строка: families/origin, exact retained paths или scope, source release IDs, immutable evidence/hash, relation, resolution, исключённые globs, residual uncertainty. Negative finding формулируется «в проверенной retained scope shared origin не установлен», не доказательство абсолютной независимости. Проверка должна относиться к **acquired snapshots**, особенно libpng/curl, а не только git trees.

Если audit добавляет merge, число components может стать 5 при pinned counts 4/1/1. B требует **STOP**, не reroll/redistribution. Changes split/component/member retention требуют нового source/policy/corpus binding и повторной D verification. Нельзя разделить fork ради сохранения шести components.

**Exclusion closure.** Member-level license exclusion убирает file/chunks с тем же path через M:592–598, но `tar` имеет `member_path=null` и уже содержит этот member. Source exclusion убирает все tracks source; chunk object exclusion не доказывает очистку parent file/tar. Поэтому новый member-origin/license finding после D требует пересборки affected representations либо явного консервативного excluded-source amendment; query filter не может «очистить» уже созданные tar bytes. На текущем D corpus `exclusions=[]`; это adversarial contract hole, не утверждение о найденном запрещённом tar payload.

## 10. Category model

Для `x∈F_t` определить:

```text
pos(o) = (family_id, member_path, offset)
P_t(x) = exists b∈A_t(x): pos(b)=pos(t)
S_t(x) = exists b∈A_t(x): family(b)=family(t)
k_t(x) = same_path_historical  if P_t(x)
         same_family_decoy    if not P_t(x) and S_t(x)
         foreign_family_decoy if not S_t(x)
```

`P⇒S`, поэтому категории mutually exclusive и exhaustive на непустом `A_t(x)`. Это executable precedence M:612–619; B:4 сам по себе не описывает mixed-alias precedence полностью. Codification A04 сохраняет текущую code semantics. Categories — audit relation, не measured usefulness/hardness и не scorer feature.

`file`: offset null, path exact normalized string; rename → same-family decoy, пока другой eligible alias не свидетельствует same-path. `chunk`: требуется тот же family/path/**offset**, плюс same track/unit из E; совпадение offset при разных paths не делает same-path. `tar/tar-gz`: position `(family,null,null)`; внутри family все earlier same-track releases same-path, same-family-decoy pool пуст. `tar` и `tar-gz` несовместимы между собой. File strata не ограничивают bases.

Одна family в split → foreign pool пуст, даже если в других splits есть «подходящие» bases. Category size 0/1/cap/cap+1 даёт 0/1/cap/cap; shortage не заполняется другой category. Eligible aliases разных families дают same-family priority, если есть такой witness. Ineligible aliases не участвуют в `P/S`, но могут менять global exclusion при переходе к другому U (§6).

## 11. Ranking / truncation / independent completeness

### 11.1 Точные total orders

```text
candidate key(t,x) = (Hc(["candidate",20261004,id(t),x]), x)
target key(t) = (Hc(["target",20261004,id(t)]), id(t))
group key(g) = (Hc(["target-group",20261004,family,track,stratum_or_empty]), g)
representative key(b) = id(b)
```

Hash hex сравнивается lexicographically ASCII (эквивалентно unsigned digest bytes), tie — второй tuple element. `g` состоит только из strings; null преобразуется в `""` **только для group key**, не в serialized stratum. Добавление tie-breaks — A05: existing rank helper возвращает только digest; fixed pilot ties не утверждаются, но contract обязан определять их. Component split ties resolved по minimum family ID; member rank ties — normalized path; для D нельзя менять уже принятую materialization, дополнительное правило нужно для будущих контрпримеров.

Ranking domain — content classes **после E и category assignment**, не occurrences. Target occurrence ID входит в key: один object у разных targets **не обязан** иметь одинаковый rank. Object/content hash, fixed seed и target ID разрешены; category не входит в hash, но определяет отдельную prefix selection. Forbidden inputs: score, patch cost, codec identity/options, compressibility, file enumeration order, acquisition/run time, representative ID, utility-based preferred path. Scorer вообще не аргумент этих функций.

`F_t^k={x∈F_t:k_t(x)=k}`, `n_k=min(cap_k,|F_t^k|)`, `C_t^k=prefix_nk(sort_key(F_t^k))`, `C_t=∪C_t^k`. Prefix обязан содержать **все** n_k, поэтому «валидный under-cap subset» не равен valid selection.

### 11.2 Почему сохранённого subset недостаточно

M:622–708 проверяет listed bases и upper caps. Удаление одной valid base с обновлением count/hash/pair sum не нарушает эти predicates. Замена lowest-ranked class на higher-ranked eligible class той же категории тоже не проверяется. Arbitrary target subset с allowed ordinals не проверяется против schedule. Эти статические counterexamples показывают предел validator, а не выполненные E1 результаты.

D теперь хранит full metadata, но digest полного файла доказывает equality **этого файла**, а не сам по себе полноту генерации. Рекомендуемый independent checker должен не импортировать candidate selector/category scheduler E1 как свою oracle и выполнить два слоя:

1. **Source→U closure.** По `source-lock.sources[].retained` независимо построить expected provenance positions: file winner в каждом stratum по member rank; каждый full chunk каждого retained parent для каждого unit; ровно по одному tar/tar-gz per release. Сравнить complete key set `(source,track,path,offset,length,options)` и source/object/parent bindings с corpus lock. Проверить total bytes как сумму occurrence bytes, all 18 releases, missing/extra/duplicate positions, cross-split exclusions. Counts без exact set equality недостаточны. Byte hashes chunks/tar проверить без payload заново невозможно: их proof остаётся в двух D materializations и source digests.
2. **U→queries closure.** Независимо перечислить T, identity population, target schedule и для каждого selected t весь `F_t^k`; проверить category cardinalities и exact prefixes. Эквивалентный witness: selected count=n_k и каждая unselected key ≥ последней selected key; при n_k=0 checked cardinality/cap объясняет пустоту. Одного «boundary hash» без independently checked full pool недостаточно.

Сохранять в E evidence для каждого selected target/category full-pool count и `Hc(sorted full-pool object IDs)`, selected IDs, last-selected key (null при пустоте), shortage `max(0,cap−|F|)` и truncation `max(0,|F|−cap)`. Эти summaries позволяют сверить recomputation, но не заменяют retained U. Independent Actions runs должны получить тот же **semantic lock** при разных input iteration orders; timestamps/CPU/run metadata хранятся отдельно.

### 11.3 Canonical bytes / proposed private binding A06

Canonical JSON уже определён M:44–104: UTF-8 no BOM, NFC string values, ASCII keys, sorted keys, 2-space indent, LF и final LF; floats/NaN/duplicate keys/lone surrogates invalid. Compact hash form: no spaces, no final LF, Unicode не ASCII-escaped. Arrays имеют явный semantic order. IDs — lowercase 64-hex. Integers не bool.

Для независимого cross-language writer дополнительно фиксировать JSON string escaping по Python `ensure_ascii=False`: `"`/`\\` escaped, backspace/formfeed/LF/CR/tab — `\b/\f/\n/\r/\t`, остальные U+0000–001F — lowercase `\u00xx`, slash и остальной Unicode literal UTF-8. Empty arrays/objects — `[]`/`{}`. Golden byte fixtures должны охватывать Unicode/control characters и empty list hash; нельзя полагаться на имя «canonical JSON» другой библиотеки.

Предлагаемый `delsk.candidate.lock.v2` сохраняет query shape v1 и вводит closed top-level key set:

```text
schema = "delsk.candidate.lock.v2"
corpus_lock_sha256                 # Hf(decompressed D lock)
selection_policy_sha256            # exact frozen B bytes
construction_spec_sha256           # adopted E specification blob SHA256
protocol_sha256                    # exact P blob SHA256
ancestry_audit_sha256               # adopted audit canonical file SHA256
planned_pairs_per_codec            # integer
queries                           # sorted by target
```

Query exact keys: `target,status,duplicate_of,bases,candidate_count,candidate_list_sha256`. Base exact keys: `object_id,representative,category`. `status∈{identity_only,near_duplicate}`; `duplicate_of` null именно у near. No extra keys. Canonical file hash включает всё. `candidate_list_sha256` включает **только IDs** и не доказывает category/representative/scope; поэтому нельзя использовать его вместо lock hash.

Это **proposal**, не поддержанная сегодня schema. Вариант sidecar вместо v2 возможен лишь как отдельное принятое решение с полной binding chain; использовать ignored v1 extra keys нельзя. Binding spec SHA относится к adopted document bytes (hash хранится снаружи документа, чтобы не создавать self-reference); его adoption в E freeze record имеет fixed source commit и corpus/ancestry/source-lock hashes. Implementation и independent-checker commit SHAs, run times и environment остаются в run evidence: разные реализации не должны делать разные semantic candidate bytes только из-за своего code SHA. Семантическое изменение E spec меняет construction SHA даже при случайно одинаковом selected pool; изменение policy — selection SHA и D-binding review.

## 12. Invariants table

`Axx` — design decision из §16; `Vxx` — adversarial case §13. «Evidence для freeze» здесь разделяет **E0** (принятый contract/expected output) и **E1** (фактический Actions assertion/recompute). Нельзя требовать уже написанный E1 как условие завершения самого E0 design, но нельзя закрыть E1 одним design document.

| ID | Statement | Scientific reason | Enforcement point | Adversarial case | Evidence для freeze |
|---|---|---|---|---|---|
| I01 | `x(t)∉C_t` | Self/exact dedup не улучшает near quality | Identity branch / full verifier | V01–05 | E0 predicate; E1 exact-ID assertion |
| I02 | Каждый selected x имеет непустое A_t(x) | Нет недоступных bases | E / full verifier | V06,08 | Witness eligibility по полному U |
| I03 | Object ID встречается в C_t не более раза | Aliases не размножают calls | Group before cap | V23,38 | Unique-ID output assertion |
| I04 | Representative — min eligible ID | Byte reproducibility без future alias | Representative projection | V06,39 | Golden query включая representative |
| I05 | Base и target одной split | Нет training/evaluation crossing | E / component admission | V04,07,34 | Split audit + all-pair metadata check |
| I06 | `hi_b < lo_t` | Temporal eligibility | E | V05,13–16 | Fixed interval fixtures + source evidence |
| I07 | Unknown time не используется | Unknown не равно old | Target/base admission | V14,15 | Exclusion counters и no-pair assertions |
| I08 | Identity iff D_t nonempty для всякого T(t) | Complete dedup branch | Full identity classification | V01–08 | All-target classifications; no truncated lookup |
| I09 | Identity rows дают 0 pairs и не near quota | Верные populations/accounting | Schedule / lock | V40,41 | Traversal fixture и independent counts |
| I10 | `duplicate_of=min_id(D_t)` | Unique lock bytes | Identity projection A03 | V39 | Два duplicates, exact expected ID |
| I11 | Alias multiplicity не даёт повторного slot одному class | Content-level sample | Class grouping | V23,38 | Restricted property §6; без ложного total-count claim |
| I12 | Permutation internal input view не меняет result | Нет order selection bias | Все total orders | V25–28 | Metamorphic Actions cases с теми же frozen bindings |
| I13 | Archive entry order не меняет representations при тех же members | Reproducibility transforms | D canonical construction | V26 | Existing D fixtures + representation comparison |
| I14 | Scorer data не входят construction API | Нет score selection | Closed inputs/module boundary | V29,30 | A10 + forbidden-input rejection/import check |
| I15 | Encoder/patch/codec не входят construction API | Нет utility selection | То же | V31 | No encoder imports/callbacks; lock identical across later codecs |
| I16 | Category из всех eligible aliases, не representative | Правильная relation semantics | Category partition | V38 | Mixed-family witness fixture |
| I17 | Categories disjoint и exhaustive F_t | Нет double quota | Priority predicates P/S | V38 | Set partition assertion |
| I18 | Selected category count = min(cap,full size) | Нет cherry-picked underfill | Independent first-N checker | V17–21,42 | Full-pool count/digest и exact prefix |
| I19 | Category shortage не padded | Equal sampling budgets | Independent per-category cap | V21,44 | Shortage сохраняется; нет borrowed IDs |
| I20 | Candidate ranking выполняется по full class pool | Full-pool first-N | Source/U closure + verifier | V42,43 | Full authority + independent prefix equality |
| I21 | Targets совпадают с exact round-robin prefix | Нет target cherry-picking | Schedule A02 | V28,40,46 | Exact visited target IDs/order trace |
| I22 | Planned pairs = sum selected near class counts | Complete future oracle denominator | Final accounting | V22,41,45 | Independent integer sum; ≤4096 |
| I23 | List hash = compact hash sorted object IDs | Canonical candidate identity | Serialization | V27,47 | Golden bytes/hash and permutation check |
| I24 | File hash binds categories, representatives и construction spec | List hash недостаточен для semantics | Closed v2 A06 | V39,47,48 | Exact key set, adopted hashes, complete file comparison |
| I25 | Изменение frozen policy/spec меняет binding identity | Нельзя silent post-hoc policy | Admission / hash ledger | V48 | Old/new identities recorded; no overwrite |
| I26 | Incomplete U не sealable | Пропущенные лучшие bases невидимы subset checker | Completeness join A09 | V43 | Exact expected position set, не только counts |
| I27 | Empty C_t сохраняется как near query | Нет conditioning on useful pool | Scheduling/coverage | V22 | Query c count 0, hash Hc([]), slot consumes |
| I28 | Только identity / no-target corpus не sealable | Не подменять near experiment dedup | Final admission | V41 | Diagnostic output + explicit refusal |
| I29 | Все exclusions/shortages имеют denominators | Coverage не скрывает bias | Coverage artifact | V14,15,21,22 | Reconciled stage counts; zeros retained |
| I30 | Derived representations наследуют ancestry/split | Нет transformed-copy leakage | D/E admission | V09,11,35,36 | Component/path lineage audit |
| I31 | Source/parent content и positions согласованы | Не принимать fabricated chunk metadata | Source-lock join | V32,43,49 | Parent hash/size and complete offsets checks |
| I32 | Global cross-split membership computed before query filtering | Не скрывать cross-cohort bytes future фильтром | X_U | V04,07 | Explicit A01 ruling; raw-U witness set |
| I33 | Source/member exclusion не оставляет affected composite payload | Нет license/ancestry обхода через tar | Transform closure admission | V10,50 | Rematerialized D или reviewed source exclusion |
| I34 | Lane-specific claims/coverage; no historical claim для modeled bytes | Не выдавать retrospective model за deployment replay | Scope/temporal audit | V36,51 | A07 evidence/claim ruling до seal |
| I35 | Duplicate IDs/positions, inconsistent identity → fail | Не зависит от first/last writer | Strict schema/identity admission | V24,32 | Rejection fixture, no partial lock |
| I36 | Никакая family reroll при ancestry mismatch | Не выбирать удобный holdout | assign_splits admission | V09,33,34 | Stop record, reviewed amended source lineage |

## 13. Adversarial test matrix

Это **bounded exhaustive matrix обязательных классов ошибок**, не утверждение, что конечные примеры исчерпывают все возможные manifests. Expected outputs заданы до E1. Реальные pilot data для tests не нужны: маленькие synthetic metadata fixtures, byte identities из заранее фиксированных synthetic bytes.

Общие preconditions если не сказано иначе: valid complete U; same split/track; source times `[0,0]`, `[100,100]`, `[200,200]`; t из ordinal 2/3; distinct objects кроме explicit alias. Обозначения x/y/d — символические IDs concrete fixture objects; `rep(x)=min_id(A_t(x))`, `sort_id` — canonical final order. Упомянутый порядок rank — precondition fixture с заранее закреплёнными bytes/IDs, не override production ranking. Вектор expected IDs вычисляется независимо и фиксируется в reviewed test data; строки без concrete byte vector пока являются design cases, не исполнившимися golden tests. `ERROR` всегда означает отказ seal без частичного lock.

| ID | Вход / attack | Exact expected behavior |
|---|---|---|
| V01 | Same bytes, same path, earlier release | t identity-only; duplicate_of=rep(x(t)); empty bases; 0 pairs |
| V02 | Same bytes, другой path в earlier release | Тот же identity outcome, path не блокирует dedup |
| V03 | Same bytes, другая family, та же split, earlier | Identity-only; ancestry reviewed; другой family name не мешает equality |
| V04 | Same bytes в другой split | x(t)∈X_U; t excluded до queries; обе роли excluded; counter cross-split увеличен |
| V05 | Same bytes только в future release | D_t empty; t near; future duplicate не candidate, даже если smallest ID |
| V06 | Base class x имеет eligible old и future alias | x eligible один раз; rep из old aliases; future не меняет category |
| V07 | Base class x имеет old local и future other-split alias | x globally excluded, C_t не содержит x; правило не смягчается temporal filtering |
| V08 | У x только ineligible aliases | x∉F_t; ни representative, ни slot |
| V09 | Fork family, retained shared payload, merge делает 5 components | ERROR component count mismatch; no 4/1/1 redistribution |
| V10 | Vendored source под excluded glob | Не materialize как retained member/chunk; tar строится без него; если уже в D — ERROR pending corrected D |
| V11 | Shared generated source/templates в двух families | Unresolved relation → ERROR ancestry audit; reviewed merge/exclusion требуется до seal |
| V12 | Build dependency, доказано no shared retained payload | No merge; components/splits остаются B-derived |
| V13 | Overlapping intervals | Cross-family pair ineligible; если same-family known releases нарушают ordinal chronology — ERROR source plan |
| V14 | Unknown target time | t не входит T_all, no query, unknown-target counter; нельзя fallback на ordinal |
| V15 | Unknown base time | Этот alias вне A_t; другие eligible aliases x сохраняют x при неизменном X_U |
| V16 | Lower semantic version base опубликован позже t | Pair ineligible; если same-family plan reverses known ordinal intervals — ERROR; version string не clock |
| V17 | Category pool size 0 | Selected 0; shortage=cap; truncation=0 |
| V18 | Category pool size 1, cap>0 | Selected exact sole class; shortage=cap−1 |
| V19 | Pool size=cap | Все classes, serialized sort_id; shortage=truncation=0 |
| V20 | Pool size=cap+1 | Первые cap по total candidate key; последний excluded; truncation=1 |
| V21 | Все categories short | Union именно их pools; shortage по каждой; no padding, sum меньше 64 |
| V22 | Total F_t empty, D_t empty | Near query с bases=[], candidate_count=0, hash=Hc([]), duplicate_of=null; consumes near slot; pairs 0 |
| V23 | Несколько distinct occurrence aliases same class, same category | Один selected object ID, если prefix выбирает x; rep minimum eligible; count не равен alias count |
| V24 | Duplicate occurrence ID, даже одинаковая record; duplicate provenance position | ERROR до selection; не first/last-wins |
| V25 | Filesystem iteration permutation | После canonical ingest тот же semantic U и output query bytes; acquisition paths не ranking input |
| V26 | Tar member order permutation при тех же member bytes | Canonical transformed bytes/occurrence IDs одинаковы; acquired archive SHA может отличаться, поэтому **полный D/candidate file hash не обязан совпасть между разными archives** |
| V27 | JSON object-key / occurrence array permutation | Direct noncanonical frozen bytes rejected; permutation internal parsed view с сохранённой identity authority и canonical sorting даёт тот же lock |
| V28 | Target iteration permutation | Scheduled prefix по explicit total order прежний, final queries sorted by target ID |
| V29 | Reversed mock scores | Construction API не принимает scores: ERROR unexpected input; attach scores только после seal не меняет frozen output |
| V30 | Random mock scores с разными seeds | То же; randomness не передаётся construction кроме fixed B seed |
| V31 | Mock encoder gains / codec option fields | ERROR input outside closed contract; никакие gains не computed или used |
| V32 | Один object ID, разные lengths; либо same-length different bytes forced hash collision | Length conflict ERROR в metadata. Same-length collision обнаруживается только при byte comparison/materialization fixture; ERROR, не merge. Metadata-only validator не может доказать невозможность collision |
| V33 | Ancestry unknown family / unresolved or conflicting relation | ERROR; nonempty evidence string не делает relation scientifically valid |
| V34 | Split occurrence не равен component assignment | ERROR corpus admission; нельзя query-time «поправить» поле |
| V35 | Transform пытается сменить split | ERROR; все variants source сохраняют split |
| V36 | Tar и tar-gz same source/family | Разные tracks; не bases друг другу. Earlier same-track same-family → same-path. Lane modeled, no historical transformed-byte assertion |
| V37 | Parent length=2u+3, unit=u | Ровно offsets 0,u, length u; tail 3 excluded. Offset 2u full chunk или misaligned offset → ERROR. Equal offset на другом path → decoy |
| V38 | x имеет eligible same-path, same-family и foreign aliases | Единственный class category same-path; rep smallest eligible даже если foreign; no multi-category duplication |
| V39 | Eligible identical aliases i1<i2, плюс smaller future i0 | duplicate_of=i1. Для ordinary base representative=i1. i0 никогда не rep |
| V40 | Ordered groups A=[I,N1], B=[N2], synthetic near quota=1 | A02: visited queries I,N2; N1 не selected; final sorted by target ID; all-target coverage знает I,N1,N2. Prefilter identities ошибочно выбирает N1 |
| V41 | T_all содержит только identity targets / пуст | Coverage сохраняется; no seal because near_count=0. All-empty-pool **near** queries V22, напротив, sealable |
| V42 | В готовом lock удалить eligible selected base или заменить на rank cap+1; hashes/counts обновить | Current v1 может принять; independent selection check ERROR exact prefix/count mismatch |
| V43 | Удалить unreferenced occurrence из U, обновить aggregate bytes | Frozen digest mismatch ERROR; для произвольно rebinding input exact source→position set check тоже ERROR |
| V44 | Foreign pool пуст в one-family split, decoy pool переполнен | Foreign count=0, shortage=32; decoy максимум30. Не переносить foreign quota |
| V45 | Identity query содержит bases или claimed pair sum отличается | ERROR. Count bool=true вместо1 тоже ERROR |
| V46 | Удалить target из scheduled prefix / выбрать unscheduled target | ERROR target membership mismatch, даже если все listed queries independently eligible |
| V47 | Hash rank-order IDs вместо sorted IDs; либо изменить rep/category при том же list hash | Первый ERROR list hash. Второй list hash может совпасть, но full-record verifier/file hash обнаруживает change |
| V48 | Изменить seed/cap/spec prose/ancestry audit, оставить старую binding identity | ERROR expected hash/recipe mismatch; no automatic acceptance because output happens to agree |
| V49 | Chunk parent hash corrupted, parent не выбран file track | ERROR join against source-lock retained member; current corpus schema-only check может пропустить |
| V50 | Member license_blocked после materialization, tar с null path retained | ERROR transform exclusion closure; corrected D/explicit reviewed source exclusion нужен до seal |
| V51 | Source release date есть, historical member-byte provenance unresolved | ERROR historical-scope admission либо отдельный **заранее adopted** modeled-scope amendment; не silently accept literal history |
| V52 | Candidate/group/target rank collision fixture | Sort by specified secondary identity; same result for permutations. Mock digest только в test reference, не runtime option |
| V53 | Новый eligible same-path alias продвигает x из 31 decoys | §6: count 30→31, x один раз; blanket count invariance test должен быть отвергнут как ложный |
| V54 | Новый smaller eligible alias без смены category | C_ids прежний, rep изменился; corpus/full lock hash изменился. Не утверждать full-lock alias invariance |
| V55 | Same bytes только в wrong track той же split | Не identity для t; этот alias не base. Same content class global grouping не отменяет same-track E |
| V56 | Два target aliases в одном release и track | Два potential target occurrences; взаимно не historical bases. Не deduplicate target pool по object ID |

Ни V40 synthetic quota, ни synthetic digest ties, ни fabricated source times не переносятся в real pilot policy. Эти fixtures проверяют алгоритм на независимых маленьких worlds; real fixed seed/caps остаются неизменными. Перед E0 adoption зафиксировать portable concrete fixtures для V39/V40/V47/V52 с exact bytes; ожидаемые outputs нельзя впервые выбирать по E1 builder.

### 13.1 Canonical primitive golden vectors

Эти concrete vectors вычислены непосредственно SHA-256 над указанными byte strings, без candidate selection. Символы `a/b/t/x` проверяют hash primitives и не являются валидными 64-hex occurrence IDs.

| Exact compact UTF-8 bytes, без final LF | SHA-256 |
|---|---|
| `[]` | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` |
| `["a","b"]` | `0473ef2dc0d324ab659d3580c1134e9d812035905c4781fdd6d529b0c6860e13` |
| `["candidate",20261004,"t","x"]` | `eaaa8d943ff497e203d33b8734638634b76d1752b1083747b0523b045959615c` |

Canonical file form для object с `a = U+0410 + U+000A`, `b = empty list`:

```json
{
  "a": "А\n",
  "b": []
}
```

После closing brace ровно один LF; кириллическая А записана UTF-8 bytes `d0 90`, newline внутри string — два ASCII bytes `5c 6e`. File SHA-256: `a7d01cca0478587a89049f9bcd2d23fed1450944f90d7b20fd825948230b07aa`. Эти vectors не являются candidate-lock artifact и не заявляют E1 conformance pass.

## 14. Metamorphic / property tests

Пусть `S(U,B,A)` означает semantic selection при одинаковых frozen bindings, `Q` — full query records, `Ids_t` — selected base object IDs. Доступ к serialized frozen artifacts всегда начинается с strict byte validation. Ниже properties для будущих Actions tests, не результаты текущего исполнения.

| Property | Условие и проверка |
|---|---|
| P01 Input permutation | `S(view_permutation(U),B,A)=S(U,B,A)`, где authority остаётся canonical U; сравнивать full Q и final bytes |
| P02 Alias permutation | Permute occurrences внутри каждого class — same Q. Duplicate occurrence record invalid, не equivalent permutation |
| P03 Base-ineligible alias | При неизменных T_all, X_U и approved scope добавить future/wrong-track/scoped-excluded alias: `Ids_t`/Q не меняются, кроме внешней corpus binding. Если alias создаёт X_U, premise false |
| P04 Eligible alias, stable category | При stable target pool/global exclusion/category: Ids_t неизменны; rep только min старого rep и нового eligible ID; full file может меняться |
| P05 Query isolation | Computing query t alone из **полного U** даёт те же bases, что batch; порядок обработки других targets не влияет. Target membership всё равно определяется global schedule |
| P06 Scorer/encoder isolation | API rejects scorer/encoder/result fields; import/capability surface не содержит их. Разные later scores/codec runs используют один frozen lock; unit hash projection test сам по себе недостаточен |
| P07 Category locality | Добавить новый **distinct eligible class** в category k при fixed t: other categories unchanged; new selected prefix соответствует total order. Не распространяется на alias, меняющий категорию старого class |
| P08 Prefix/cap relation | На synthetic policy увеличение cap k на1 меняет только prefix k на максимум один class; caps не меняются на real pilot после results |
| P09 Order direction | Если key(x)<key(y), y selected в k и x∈same full k, то x тоже selected; нарушение — first-N bug |
| P10 Identity masking | Добавление eligible exact target class переводит t в identity и даёт0 pairs; adding только future equal class не переводит. Проверять query-level, не ожидать unchanged target schedule |
| P11 Representative robustness | Добавить ineligible alias с меньшим ID не меняет rep; удалить nonrepresentative eligible alias при stable category не меняет Q |
| P12 Time zones | Equivalent offset timestamp strings дают те же UTC intervals и E outcomes; source-plan bytes/hash могут отличаться, поэтому это predicate invariance, не file identity |
| P13 Unit boundary | Parent длины ku+r имеет ровно k full chunks для 0≤r<u; увеличение r без пересечения boundary не добавляет full chunk, но payload/parent hashes могут меняться |
| P14 Deterministic failure | Invalid occurrence/order/schema produces rejection before write для любых internal iteration permutations; не требовать случайного порядка diagnostics, error list сортировать |
| P15 Binding sensitivity | Semantic spec/policy changes меняют соответствующий binding SHA/full lock identity, даже если bases coincidentally прежние |
| P16 Two independent derivations | Slow reference enumeration и optimized E1 builder дают exact same query bytes на всех generated valid worlds; нельзя обоим импортировать одну category/schedule функцию |
| P17 No codec dimension | Number of planned pairs for each codec равен одному N из lock; число codecs не умножает поле `planned_pairs_per_codec` |
| P18 Corruption fail-closed | Любой missing expected provenance position, подмена parent binding или неизвестный manual exclusion даёт ERROR, не меньший «успешный» sample |

Не являются допустимыми properties: `seal(U+alias)==seal(U)` без условий; «append future ничего не меняет» при global cross-split decontamination; «shuffle actual frozen JSON bytes accepted»; «archive permutation сохраняет acquired archive SHA»; «same object имеет одинаковый rank для всех targets». Каждое неверное обобщение имеет counterexample выше.

## 15. Leakage audit

| Channel | Mechanism → consequence | Prevention до freeze | Detectable evidence |
|---|---|---|---|
| Evaluation-aware roster changes | Удалить слабую family → selection bias | Immutable roster и exposure log, amendment workflow | Plan/source hash diff; сохранение old roster |
| Split reroll | Менять seed пока holdout удобен | Seed fixed, ancestry component assignment; mismatch=stop | All attempted policy versions, assignments |
| Ancestry adjustment after targets/results | Объявить похожие projects независимыми → inflated sample size | Origin decisions до utility inspection, retained-path audit | Dated audit hashes и relation evidence |
| Utility-driven path exclusions | Вычеркнуть плохо сжимаемый/сложный path | Allowlisted provenance/license reasons, no scores in review | Reason/evidence per path; old/new manifests |
| Score-selected bases | Select high scorer outputs → apparent recall gain | No score input; independent full first-N | Full pool hashes, rank prefix, strict API rejection |
| Encoder-selected bases | Filter low gains/failures → impossible oracle advantage | No codec/patch fields or callbacks | Frozen candidates predate encoder results |
| Compressibility filtering | Payload entropy/ratio influences sample | Metadata-only construction, exact frozen member policy | No payload access; code/import audit |
| Shortage padding | Borrow foreign/other split slots → unequal budget | Caps independently, keep zeros | Per-category eligible/selected/shortage counts |
| Alias leaks cohort metadata | Class-level future/other-split witness changes decisions | Explicit A01 global decontamination; scope documented | X_U witnesses; no online-causality claim |
| Privileged target metadata in scorer | Family/path/time reveals relatedness | Separate audit artifact, explicit scorer projection | Projection schema/object-level API tests |
| Pilot-evaluation tuning | Reuse examined evaluation family as confirmation | Exposure tracking, fresh confirmatory holdout | Pilot labels и future cohort provenance |
| Rank/cap change after first results | Refit sample to gain headroom | Bound construction hash + immutable policy | New hash invalidates old seal; decision log |
| Truncated universe | Omit outranking base/identity alias | Full D authority + source→U closure | Exact positions/parent joins + independent enumeration |
| Future byte assertion | Assign old release date to later replaced content | Historical byte provenance or explicit modeled claim | Source/member hash/time evidence and A07 ruling |
| Same-origin transformed copies | Count tar/chunks as independent domains/lineages | Inherit component; report by lane/track | Parent/component bindings, cluster counts |
| Hidden missing targets | Discard empty/unknown/identity cases without counts | Stage reconciliations + schedule equality | All-target vs encountered vs selected counts |
| Manual license exclusion after D | Exclude member, retain bytes inside tar | Dependency closure before seal/rematerialization | Affected parent/archive inventory + corrected lock |
| Repeated runs cherry-picked | Publish only convenient repeat | Retain all attempts and mismatch reports | Run/attempt ledger, both same-lock reports |

`object_id` и будущий доступ к payload сами могут позволить модели узнавать материал; allowed visibility не заменяет lineage split или запрет memorization/tuning на evaluation. В **manifest** поле `bytes` — integer length, не payload: exact metadata projection B равна `{object_id,bytes}`. Payload в Git отсутствует; будущий scorer получает его через отдельную привязку object ID к verified bytes. Family/path/ordinal/time/categories не могут попасть через audit bundle. E0 не определяет public scorer API.

## 16. Ambiguity / contradiction register

Classification: `SPECIFIED` — однозначно в B/P; `DERIVED` — логически или executable code следует из них; `AMBIGUOUS` — ≥2 интерпретации; `CONTRADICTORY` — одновременно требуемые свойства несовместимы; `BLOCKING` — evidence/precondition отсутствует. Указание `blocking: yes` ниже относится к E0 adoption, не аннулирует прошлую acquisition evidence.

### 16.1 Уже определённые significant rules

| Rule | Class | Exact source | Consequence |
|---|---|---|---|
| Content vs occurrence identity | SPECIFIED | B:19–24; M:125–127 | Object grouping и provenance IDs разные |
| Same split/track, strict interval | SPECIFIED | B:10–12,119–122; M:601–604 | Ordinal/mtime не base eligibility |
| Cross-split global exclusion | SPECIFIED | B:22; M:538–557; D:383–388 | Raw U, включая non-query aliases |
| 2/30/32 caps, no padding | SPECIFIED | B:5–9 | Три independent prefixes |
| Representative minimum | SPECIFIED | B:7; M:683–689 | Только eligible occurrences |
| Category precedence | DERIVED | M:612–619 | Existential class partition; prose уточнить A04 |
| Member-less position | SPECIFIED | B:130 | Same family archive history is same-path |
| File bases may cross strata | DERIVED | M:601–604; R «Targets» | Same track, не same stratum |
| Fixed chunk boundaries | SPECIFIED | B:127–128; M:130–133,518–528 | Full chunks, no tail padding |
| Targets are occurrences | SPECIFIED | B:112; M:642–653 | Same-release target aliases не collapse |
| Empty near pools permitted | DERIVED | P §§2–3; M:697–707 | Empty list ≠ absence of near queries |
| No-near lock rejected | SPECIFIED | R «Схемы»; M:700–703 | Identity-only collection не near experiment |
| Canonical serialization/list hash | SPECIFIED | M:44–104; M:657–661 | Byte syntax fixed, selection ещё требует proofs |
| Changed split component count stops | SPECIFIED | B splits; M:186–202 | No silent redistribution |
| Scientific denominators/thresholds unchanged | SPECIFIED | P §§3,5,6 | E0 не пересматривает P1 |

### 16.2 Pending amendments / rulings

В графе «D impact» слово **retain** означает оставить existing D как исторически valid acquisition artifact; это не разрешение использовать его под изменёнными inputs. Все recommendations ниже подготовлены до scorer/encoder results, но exposure history будущих исполнителей нужно проверять отдельно.

| ID / class / blocking | Exact source locations и две интерпретации | Scientific consequence и recommended amendment | D impact | Новый holdout/split/seed? |
|---|---|---|---|---|
| A01 CONTRADICTORY / yes | B:22, M:538–557 vs E0 brief §§5,20: (a) global quarantine; (b) eligible historical alias всегда спасает class, future не влияет | Одновременно невозможно. Сохранить (a); сузить alias invariants и claim до retrospective temporal sample (§6/8). Для causal catalog требуется отдельная policy | Retain при scope clarification; при (b) new corpus exclusions/binding, verify again | Не менять seed автоматически; policy change до results reviewed; после evaluation новый protocol/holdout |
| A02 AMBIGUOUS / yes | B:112 и23: (a) one occurrence/group/round, identity consumes turn; (b) prefilter identities/refill group | Разный target sample без score. Рекомендовать (a), немедленный stop at64 near; identity rows только visited prefix; full identity coverage separately | Retain D: generation неизменна; bind accepted construction supplement | Нет result-driven reroll; тот же seed/splits |
| A03 AMBIGUOUS / yes | M:664–668 vs B:7 (только base rep): (a) any eligible duplicate; (b) minimum eligible ID | Разные bytes при одном universe. Явно принять (b) для duplicate_of | Retain D; E binding новый | Нет |
| A04 CONTRADICTORY requirement / yes | E0 brief «aliases не увеличивают count» vs B:4/5/8/9, M:612–619: (a) class existential priority; (b) category по rep/immutable first alias | Category/caps меняют membership. Сохранить executable (a), formalize precedence и restricted invariance; reject representative-derived category | Retain D при codification, no new data | Нет |
| A05 AMBIGUOUS / yes | M:107–109, B:3,112: (a) stable-sort tied input order; (b) rank+identity total order | Permutation dependence при rank collision. Принять total keys §11 и exact collision fixtures | Retain current D при доказанном отсутствии affected D ties; новый D если member/split output меняется | Seed не менять для обхода collision |
| A06 AMBIGUOUS / yes | R candidate v1 shape; M:622–708 допускает extra keys, не binds E spec: (a) permissive v1; (b) closed/bound E artifact | Два serializers сохраняют разные extras или разные rules под одной policy. Предложить private v2 §11.3; не silently add ignored keys | Retain immutable D; no plan/policy rewrite; E schema/validator отдельно | Нет |
| A07 BLOCKING / yes | S:244,319; B:119–129; M:137–159; F:176–180: (a) exact historical byte availability; (b) parent-release retrospective model | Разные temporal claims. Adopt evidence requirement и lane-specific scope; actual proof или explicit modeled/unknown amendment до seal | Corroboration-only retain; changed time/track/member inputs → new D-dependent lock+verification; старый сохранить | Не новый seed; fresh confirmatory data при будущих quality claims/после exposure |
| A08 BLOCKING / yes | S:3–22, M:341–350, F:193–194: (a) six labels sufficient; (b) reviewed retained-origin graph required | Labels/hash inequality не independence. Adopt audit scope §9 и закрыть unresolved relations; merge либо proven exclusion | Findings без изменения U retain; merge/exclusion меняет plan/components/U → reviewed new D binding | Component mismatch stop; redesign cohort reviewed, не reroll; после evaluation fresh holdout |
| A09 BLOCKING admission gap / yes | R:60,75 допускает reduced references, D:255–282, M:469–471,539–544: (a) schema-valid supplied subset; (b) full hash-bound U+source closure | (a) скрывает rank/identity/category witnesses. Принять (b), exact expected positions и transform exclusion closure; no canonical subset authority | Current durable D retain; source/corpus changes require new D verification | Нет при unchanged universe |
| A10 AMBIGUOUS enforcement / yes | B forbidden inputs/visibility; T:829–843 adds scores after selection: (a) ignore result fields; (b) construction accepts closed metadata only | Hash projection не доказывает score-free sampling. Принять closed API + explicit scorer projection, no callbacks/results; archive order property на representation level | Retain D; reject future incompatible extras rather than silently discard | Нет; после фактического utility inspection применить P1 exposure rule |

A02 recommended encounter traversal выбран как минимальное уточнение буквального B, **не как уже установленная истина**. Ни спецификация, ни approval E0 не могут ретроспективно сделать оба possible target schedules одной policy. Adoption record должен перечислить все Axx и выбранную interpretation.

Важная hash consequence: D source/corpus lock содержит SHA **всего** selection-policy file. Даже изменение только prose, `status` или candidate rule в нём инвалидирует совпадение D input hashes. Поэтому recommended supplement/v2 binds отдельно уже принятые B bytes и новые E rules. Если вместо supplement редактируется B, требуется versioned new D-bound artifacts; «данные не изменились» не оправдывает старые несовпадающие hashes.

## 17. Coverage / statistical interpretation

### 17.1 Что уже известно из D metadata

Ниже read-only metadata facts, не E selected targets и не quality results. Exact position reconciliation against frozen source-lock retained members дала 3 357 source-member records, 32 391 expected и actual representation positions, 0 missing/extra; file choices/parent hash+size согласованы. Это локальный аудит metadata, не новый Actions run. Он подтверждает, что **текущий** full-U artifact пригоден для дальнейшего independent checker; не доказывает completeness произвольного schema-valid replacement и не проверяет payload hashes заново.

| Planned component | Split | Occurrences | Content objects | File occurrences |
|---|---|---:|---:|---:|
| bzip2 | evaluation | 255 | 239 | 0 |
| curl | calibration | 8 133 | 6 565 | 6 |
| libpng | development | 1 909 | 1 401 | 3 |
| sqlite | development | 15 245 | 15 172 | 6 |
| zlib | development | 1 666 | 891 | 6 |
| zstd | development | 5 183 | 4 209 | 6 |

Tracks: file 27; chunk-4k 17 682; chunk-8k 8 309; chunk-16k 3 850; chunk-32k 1 730; chunk-64k 757; tar18; tar-gz18. Ordinal2/3 occurrences **до target eligibility/scheduling**: 21 724. File `f001m` пуст; `f004m` только SQLite. Bzip2 evaluation не содержит file track, следовательно этот pilot не может дать held-out historical file quality даже после oracle. Calibration/evaluation содержат по одной planned family → foreign-family-decoy pools всегда пусты. Это structural coverage facts, без candidate sealing.

Alias multiplicity histogram: 25 631 classes с одной occurrence, 1 778 с двумя, 1 068 с тремя. В текущем U 0 classes cross-family/cross-split/cross-track/different-member-path. Поэтому сложные mixed-category/future-cross-split scenarios **не проверяются фактом успеха materialization pilot**: нужны synthetic fixtures.

Шесть singleton components — mechanical assignment и верхняя граница независимых lineage units до A08, не доказанные шесть независимых samples. Chunks, releases, source members, exact objects, transformed archives, encoder pairs и in-job timing samples **не** independent statistical units. Историческая и modeled lane не объединяются; file/chunk/tar tracks не создают новые независимые domains. Нельзя выводить effective sample size=32 391 или28 477; statistical ESS без estimand/correlation model не определён. Planned held-out lineage count=1, это далеко от P1 confirmatory requirement ≥10 на domain.

### 17.2 Обязательный E coverage contract

Сохранять rows для всех planned `(component,family,split,track,stratum)` cells, включая нули и отсутствующие strata. `stratum=null` для non-file tracks; missing file stratum нельзя записывать в null и тем самым скрывать hole.

| Population/stage | Required counts / denominators |
|---|---|
| Full source inventory | Acquired archives/bytes, retained members, path exclusions by reason, non-source counts, short-tail count/bytes; inventory hash limitations |
| Full U | Occurrences, unique content, alias histogram, parent bindings, component counts, lane/track/stratum counts |
| Target universe | Ordinal2/3 before exclusions; excluded counts по reason; T_all after exclusions/time; identity and near-opportunity classification |
| Visited prefix | Encountered identities, selected near targets, not-visited remaining per group, group rounds, max_targets stop/exhaustion |
| Bases per target | Raw occurrences, exclusion reason counts, temporal/track/split eligibility, eligible alias count, unique classes, exact duplicate count, F_t size |
| Categories | Full count/digest, selected count, cap, shortage, truncation, representative/category witnesses |
| Empty pool | Empty near count / selected near count; отдельно empty rate across all near opportunities if computed, явно другой denominator |
| Identity rate | All identity targets / T_all; отдельно encountered identities / visited total. Ни одна из них не near recall denominator |
| Cross-split/time | Number content classes и occurrences excluded; unknown-target и unknown-base counts отдельно; no phantom encoder failures |
| Independence | Reviewed components per split/domain, targets per component, unresolved origins; effective independent units unknown до audit |
| Pair plan | Sum candidate counts, per-lane/track/component totals, codec-independent N; executed encoder pairs в E0 не существуют |

Для overlapping exclusion reasons сохранять **две** формы: multiset всех применимых reason flags и exclusive primary reason по заранее fixed precedence `source → member → object → occurrence → unknown_time → target_ordinal`. Для query bases после scoped exclusions: `self → split → track/unit → unknown_time → temporal → exact_target_class → category_truncation`. Эти primary counters — diagnostics attribution, не изменение E: eligibility определяется conjunction. Полный reason vector остаётся authority для аудита; суммы primary outcomes дают stage totals. Внутри одного scope несколько reasons сортируются lexical по `(kind,subject,reason)`.

Exact duplicate и category truncation — query outcomes, не новые corpus exclusions. Category shortage не exclusion. Unknown source time может одновременно иметь source exclusion и unknown flag; две формы не позволяют дважды вычитать occurrence из population. Proposed attribution rule является частью A09/A10 supplement, а не скрытым изменением frozen D.

G3/G4 evaluation здесь не проводится. Ни имя `near_duplicate`, ни наличие historical same-path base не устанавливает полезный patch. Zero denominators/empty pools/identity treatment для будущих metrics остаются P1.

## 18. E0 freeze checklist

| Gate | Состояние в этом документе | Что нужно для закрытия |
|---|---|---|
| Repository truth / source and exact input hashes | Established at stated snapshot | Refresh main/open PR state перед adoption; изменения анализировать отдельно |
| D acquisition frozen + full U durable | Established в D scope | Preserve pinned inputs; не объявлять E frozen по D record |
| Все blocking ambiguities закрыты | **OPEN** | Явное adoption A01–A10 и отсутствие unresolved alternatives |
| Exact algorithm / operation order | Recommended, conditional | Принять §§3–5, в частности target/identity traversal |
| Aliases semantics | Contradictions exposed | Принять restricted properties; не требовать математически ложное blanket claim |
| Time arithmetic | Specified | Historical-byte/parent chronology claim A07 unresolved |
| Ancestry scope | Model specified, actual audit incomplete | Retained-origin evidence A08, no unresolved merge/exclusion conflict |
| Target/candidate total ranking | Proposed total keys | Принять tie rules и concrete golden rank fixtures |
| Category/representative semantics | Code-derived, explicit | Принять class precedence и independent representative rule |
| Canonical byte contract / hashes | v1 syntax established; v2 proposed | Adopt closed E schema/binding и cross-language golden byte fixtures |
| Full-U admission / first-N proof plan | Defined | Adopt exact source→U closure and independent reference verification contract |
| Adversarial expected outputs preimplementation | 56 cases + 18 properties specified | Review cases, pin concrete portable fixtures для identity/schedule/serialization/ties до E1 |
| No utility/result-dependent rule | Design complies | Freeze exposure statement и API/import contract; ни один amendment по encoder/scorer results |
| E0 adopted artifact identity | **Absent** | Reviewed source commit/spec SHA/audit SHA, decision record; никаких самоприсвоенных FROZEN |

**E0 freeze** означает однозначность принятого scientific design и preregistered expected outputs. **E1 seal** дополнительно требует implemented closed validators, actual adversarial/metamorphic Actions tests, two independent same-lock recomputations и durable coverage/selection evidence. E0 не ждёт oracle, encoder, G1–G5 или quality measurements. Если D input действительно отсутствовал бы/не совпадал по hash, verdict был бы `BLOCKED BY SLICE D`; здесь это условие не наблюдается.

Минимальный порядок закрытия: принять semantics A01–A06/A09/A10 без просмотра utility; закрыть factual A07/A08 по primary provenance; зафиксировать concrete expected fixtures и adopted hashes; только затем разрешить E1. Если factual audit меняет retained members/components/time claims, сначала versioned upstream amendment с необходимой D verification. Смена seed/thresholds для прохождения gate не является решением.

## 19. Recommended E1 implementation contract

Ниже **design-only private research API** после adoption. Минимальное функциональное ядро, stdlib, без public Delsk types, storage catalog API, scorer/encoder imports, subprocess, network, clocks, environment reads или callback hooks. I/O adapter отдельно читает только allowlisted frozen metadata artifacts. Raw payload/patch costs ему не нужны. Arbitrary fields не молча выбрасываются: closed validation отвергает их. Python не является capability sandbox против злонамеренной модификации программы; гарантия — reviewed closed dataflow, pinned source и CI tests, а не невозможность monkeypatch языка.

| Функция | Inputs / outputs | Preconditions / postconditions | Determinism / failure semantics |
|---|---|---|---|
| `admit_universe(plan, policy, source_lock, corpus_lock, acquisition_freeze, ancestry_audit, construction_spec)` | Strict parsed canonical metadata и expected hashes → validated immutable view + indexes + stage coverage | All exact bindings, approved scope, source→position closure, licenses/ancestry/components valid; full U, no dropped aliases | No selection/scoring; sorted diagnostics. Любая ambiguity/mismatch/unknown input → error, no partial admitted universe |
| `eligible_occurrences(universe, target)` | Valid universe, one admitted potential target → map object ID → sorted eligible occurrence IDs | T(t); return exactly A_t for all nonempty classes, включая target class | Pure E; no callbacks; invalid target → error, legitimate empty map → empty |
| `classify_target(target, eligible_map)` | t и полное A_t → `(status,duplicate_of)` | Map only из admitted full U, проверенная provenance; exact D_t branch; minimum duplicate | Pure, no cap; malformed map rejected at internal boundary; unknown time не near fallback |
| `schedule_targets(universe, classifications)` | All T_all classifications → visited target sequence + coverage | Classifications complete; exact A02 round-robin; stop immediately at64 near or exhaustion | Sorting by total keys; identity consumes turn. No-near status возвращает diagnostics, final seal запрещён |
| `select_classes(target, eligible_map, policy)` | Full A_t, target near, fixed policy → bases + category audit counts/digests | Remove target class; categories из eligible sets; exact min(cap,pool) prefix; representative min; output sorted by object ID | No scores/codec/alternate rank function. Incomplete map/identity target misuse → error; true empty pool valid |
| `make_lock(bindings, queries)` | Adopted hashes и complete scheduled query records → canonical bytes, full file SHA | Exact closed schema, full target sequence accounting, bases/count/hash agreement, ≥1 near, ≤4096 pairs | Deterministic bytes, no timestamp/code-version fields; errors before write. Caller atomically persists only complete verified result |
| `verify_selection(inputs, candidate_bytes)` | Same full frozen inputs + strict candidate artifact → independent structured check report | Independently enumerate targets/E/categories/first-N, compare **all** query fields и bytes | Separate simple reference algorithm, не calls selector/scheduler helpers; mismatch → reject with exact target/category reason |

`eligible_map` — internal value из admitted universe, не external caller-supplied subset. Можно реализовать функции как обычные маленькие функции/словари с defensive assertions; новый framework или generic plugin abstraction не нужен. Indexed optimization разрешена после reference equivalence: например индекс по `(split,track)` и content, но ни один index не может потерять excluded/global witnesses в authoritative U.

Test implementation отделить от natural pilot sealing. Existing World helpers T:52–56/117–122 выбирают category по одной occurrence и representative без полного E; их нельзя использовать как expected-output oracle для новых mixed-alias cases. Existing score test T:829–843 добавляет scores к **уже выбранным** bases и проверяет projection hash — это не проверка независимости candidate construction.

E1 evidence bundle должен связать source/workflow/checker SHA, adopted spec/protocol/plan/policy/source-lock/corpus/ancestry/candidate SHA, run ID/attempt, all diagnostics, full-U checks, canonical query comparison и coverage. Sampling correctness проверять independently от будущего encoder oracle. Повторный запуск одного selector — reproducibility check, но не independent semantics check. Новый Actions workload требует отдельного scoped изменения allowlist/admission; текущий foundation workflow не поддерживает E sealing. R0 F handoff и DELSK-003 oracle остаются отдельными задачами.

## 20. Final verdict

**`E0 NOT READY`.** Design audit выполнен: сформулированы predicates, operation-order proof, точные recommended semantics, 36 invariants, 56 adversarial cases, 18 metamorphic properties, leakage channels и E1 contract. Текущий D acquisition lock существует, durable и воспроизводим в своей scope; missing Slice D не является причиной отказа.

Freeze блокируют **непринятые semantic rulings и незакрытая provenance evidence** A01–A10, особенно target/identity traversal, alias exceptions, closed construction binding, exact historical-byte scope и retained-origin ancestry audit. Документ не присваивает решениям статус FROZEN и не запускает E1. Два исполнителя смогут гарантированно получить byte-identical candidate artifact только после принятия одного contract и одинаковых complete input bindings; current v1 acceptance этого ещё не обеспечивает.

