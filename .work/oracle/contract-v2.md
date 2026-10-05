# DELSK-003A: provenance/G1 contract `delsk.oracle-contract.v2`

Статус: **FROZEN с момента merge в `main`**. Идентичность принятых bytes — [freeze-v2.json](freeze-v2.json). Implementation: **NOT_ACTIVE**. Natural oracle: **NOT_RUN**. G1: **NOT_RUN**. Ни один natural byte не читался, ни один patch cost не вычислялся, registry не создан, rulesets не настроены, `oracle-pilot.yml` не запускался.

**Verdict: `DELSK-003A PROTOCOL V2 FROZEN` / `V2 IMPLEMENTATION NOT_ACTIVE`.**

Основание: [issue #27](https://github.com/definitely-stable/Shift-lab/issues/27) с принятыми maintainer decisions D1–D5, research PR [#28](https://github.com/definitely-stable/Shift-lab/pull/28) (merge `2c89c8d9edb3c3dec02f45c07a2efa5c7623d053`). [Desk research](../research/DELSK-ATTEMPT-V2-DESK-RESEARCH.md) и [proposal](attempt-v2-proposal.md) — пояснительные, **не нормативные**; где этот документ расходится с proposal, действует этот документ (отличия — §17.2).

Ключевые слова: «обязан», «запрещено», «только» — нормативны. Вне нормативного текста — примечания.

## 0. Governance и layering

```text
measurement_contract   = delsk.oracle-contract.v1     (bytes по .work/oracle/freeze.json, без изменений)
g1_provenance_contract = delsk.oracle-contract.v2     (этот документ и freeze-v2.json)
```

- **v2 не заменяет measurement layer v1.** Всё, что v1 определяет про измерение, остаётся нормой v1 и включается по exact hash (§1); v2 это не пересказывает.
- **Неизменяемость.** Этот контракт, [schemas-v2.json](schemas-v2.json), [registry-vectors.json](registry-vectors.json) и [test_oracle_contract_v2.py](../tests/test_oracle_contract_v2.py) неизменяемы после merge. Любое изменение семантики registry, классификации, population, series rules, codes или record — только новый G1 contract с новым freeze record. Старые bytes, registry и records сохраняются.
- **Кто принимает.** Maintainer merge этого PR в `main` — акт adoption.
- **Что adoption не делает.** Не активирует v2 (активация — §16), не создаёт registry, не настраивает rulesets, не разрешает natural run. До активации действует текущее fail-closed поведение: production pilot и v1 G1 отказывают с `DISPATCH_HISTORY_UNVERIFIED` ([Slice C0](slice-c.md)).
- **Нет смешивания v1 G1 и v2 G1.** Попытки, записанные в v2 registry, оцениваются только v2 G1. v1 G1 path (ledger `attempts.json`, `oracle_attempts.g1_root`) остаётся навсегда `NOT_PASSED DISPATCH_HISTORY_UNVERIFIED` и не может выпустить PASS ни для какой identity. Каждый v2 G1 record несёт `g1_contract = "delsk.oracle-contract.v2"`; run key из v2 registry в v1 evidence root делает v2 evidence root недопустимым (§8.1).
- **Trust model (D4).** P1 защищается от honest-but-fallible оператора, crash/infra и non-admin writers/automation. Malicious repository admin — вне scope P1; защита от него требует отдельного trust domain (§13.2) и нужна для более сильных внешних claims.

### 0.1 D1–D5 → нормы

| Решение | Где закреплено |
|---|---|
| D1 — v2 как отдельный G1/provenance layer над неизменным v1 | §0, §1, §2, §6 (`measurement_identity` v1 не меняется), `g1_contract` в каждом record |
| D2 — B2 self-registration: `register` job, durable запись + readback, `measure` не пересекает `B` без binding | §4.3, §5.7, §5.8, §12 |
| D3 — carry-over внутри `science_identity`, обязательный transition между science identities, молчаливый reset запрещён | §6, §7 |
| D4 — P1 trust model | §0, §13, §17 |
| D5 — witness level 1 обязателен; independent immutable checkpoint перед внешней публикацией, технология не фиксируется | §13 |

## 1. Привязанный measurement layer v1

| Input | SHA-256 |
|---|---|
| `.work/oracle/freeze.json` (`delsk.oracle-contract.freeze.v1`) = `measurement_layer_sha256` | `c56fc053b103cecd38446b3791db104a12b9fafabacdfc6b71f6f23c0bf7f729` |
| `.work/oracle/contract.md` | `d3bde26f6abf642dacc1ea8b767c0d3262928a9d27547d0e311c682b542c8387` |
| `.work/oracle/codec-lock.json` | `9823e4c933c27fb4116bfce5add59ef6e926e43d2f0ebae258d7bb869a38f7b1` |
| `.work/oracle/schemas.json` | `bdd46170b426161e7b455cc4b93545de7e46354df1a5fe072c9af46168698124` |
| `.work/oracle/known-answer.json` | `911eab6897a72fd9bf3cd27bed8ce9733b4da45a2bebc8f974a9a2e3c8fab3d6` |
| `.work/tests/oracle_reference.py` | `be84b37e66916b1172a575b842b327a018fbac2c24154b06e6ffef8caaed338f` |
| `.work/tests/test_oracle_contract.py` | `2b5e60c69829588f502575cf45175e3d13ecc58192ac176cb2e80fb11937d8f1` |

Bindings v1 (candidate lock `cb16d53b…`, corpus lock `e5c28825…`, protocol `a0c51824…`, E1 seal `0c87fd5c…`, codec lock `9823e4c9…`) — как в v1 freeze, без изменений. Если bytes любого из этих файлов отличаются от этих hashes, v2 не применяется (STOP, а не адаптация).

## 2. Scope

| Остаётся нормой v1 (по hash §1) | Меняет / добавляет v2 |
|---|---|
| candidate universe, `C_t`, pair universe (v1 §4) | определение scientific attempt (§4.3) |
| codec lock, frame v1, `D_E`, `S(t)` (v1 §2–§3) | authority существования attempts: registry (§5) |
| `O_delta`, `O`, ties, useful (v1 §6) | bind-before-measure (§4.4, §5.8) |
| pair/standalone accounting, decode correctness, failure classes (v1 §4–§5) | классы PRE / BUNDLE / MISSING (§8.4) |
| sealing/reveal, commitments (v1 §9.1) | построение G1 population (§9) |
| rows/schemas/bundles measurement evidence, `verify` (v1 §8–§9) | series, `science_identity`, transitions (§6–§7) |
| oracle/ties, recall/regret/SavingsCapture (v1 §8) | production/test provenance API (§11) |
| run status и G1 priority table v1 §7 (применяется дословно к population §9) | registry/witness/ruleset/write-token requirements (§12–§13) |
| K01–K42, G01–G09, M01–M30, C01–C14, metamorphic | R01–R22, PM01–PM10 (§14–§15), activation (§16) |

`measurement_identity` и `measurement_identity_sha256` строятся **без изменений** по v1 §9, включая `contract_id = "delsk.oracle-contract.v1"` и `contract_freeze_sha256` = hash v1 `freeze.json`. v2 не вводит новых полей в rows, bundles или `run.json`.

## 3. Канонизация и общие правила

- **`Hc(x)`** — SHA-256 compact canonical JSON v1 (`manifests.digest` = `oracle_eval.hc`): ключи сортированы, разделители `,`/`:`, UTF-8 без `\u`-escaping не-ASCII, строки NFC, ключи ASCII. Canonical file form — те же значения, `indent=2`, sorted keys, финальный LF (`oracle_eval.canonical`); canonical JSONL — по одной compact строке с LF (`oracle_eval.parse_jsonl`).
- **Числа.** Только integers в signed 64-bit (`-2^63 ≤ x < 2^63`); floats, `NaN`, exponent запрещены; `true`/`false` никогда не integer. Все v2 integers ≥ 1, кроме `registry_head.sequence` ≥ 0.
- **Hashes.** `hex64` / `hex40` — только lowercase `[0-9a-f]`, ровно 64 / 40 символов.
- **Строки.** Patterns в [schemas-v2.json](schemas-v2.json) заканчиваются `(?![\s\S])` — конец строки и в ECMA-262, и в Python `re` (Python `$` допускает финальный `\n`, это запрещено). Match — от начала строки.
- **Закрытость.** Каждый object schema v2 — `additionalProperties: false`; неизвестное поле, отсутствующее обязательное, duplicate key, BOM или неканонические bytes — отказ. Порядок полей объекта не значим (canonical сортирует ключи); порядок элементов массивов значим там, где он задан (entries по `sequence`, lists в record — §9.6).
- Digest объекта с self-digest полем `X_sha256` = `Hc(объект без X_sha256)`.

## 4. Определения

### 4.1 Execution и measurement boundary `B`

**Execution** — один GitHub Actions run attempt `(run_id, run_attempt)` reviewed workflow `.github/workflows/oracle-pilot.yml` репозитория `definitely-stable/Shift-lab`, со всеми его jobs.

**`B`** — первый момент, когда execution делает **любое** из:

1. **читает хотя бы один byte natural corpus**: byte любого source archive из pilot-v1 source lock или любого byte, выведенного из него (materialized objects, store, patches, rows, costs), включая получение первого byte сетевого ответа, восстановление cache и скачивание artifact, содержащего такие bytes;
2. **запускает measurement apparatus, способный получить natural-dependent результат**: сборку или исполнение любого codec executable, materialization/fetch natural sources, oracle runner, finalize/bundle над natural rows — любой код, вывод которого в этом execution может зависеть от natural bytes;

что произошло раньше. Определение семантическое и не зависит от YAML layout.

Не пересекают `B`: checkout source tree; чтение committed metadata (locks, freeze, contract, schemas, workflow); вычисление identity digests из committed files (`git_source`); чтение/валидация registry; budget admission без natural fetch; запись binding sidecar.

**Implementation witness.** Reviewed workflow job `measure` обязан иметь ровно один step роли `bind` (§5.8) и ровно один step роли `boundary` — первый step, после начала которого `B` может быть пересечена; `bind` идёт раньше `boundary`. Имена этих steps — константы reviewed кода, фиксируемые activation record (§16). При activation статически доказывается, что ни один step до `boundary` не пересекает `B` по определению выше. Step `boundary` — свидетель, а не определение: если `B` пересечена раньше `boundary`, implementation дефектна, и activation недействительна.

### 4.2 Registry

Authoritative append-only registry (§5) — **единственная authority существования scientific attempts**. Execution provider (GitHub Actions) не является authority полноты scientific population; его данные используются только для binding reconciliation, доказательства PRE (§8.3) и обнаружения unbound reruns зарегистрированных runs (§8.5).

### 4.3 Scientific attempt

Scientific attempt существует **тогда и только тогда**, когда registry содержит durable entry (§5.3), привязанную к execution `(run_id, run_attempt)`, и эта binding проверена в этом execution до `B` (§5.8). Execution без такой entry — не attempt (§10).

### 4.4 Bind-before-measure

Без valid unique registry binding execution не имеет права пересечь `B`. Reviewed код обязан остановиться до `B` с `REGISTRY_UNBOUND`, если binding не проверен. Зарегистрировать execution после пересечения `B` невозможно: такая entry не может быть bound до `B` и даёт `UNBOUND_MEASUREMENT` (§8.4).

### 4.5 Классы entries

- **PRE** — entry, для которой authoritative provider evidence доказывает, что execution не пересекла `B` (§8.3). Self-reported sidecar, retained status или заявление оператора PRE не дают. Если provider evidence утеряна (run удалён, данные недоступны), entry — **не PRE**.
- **BUNDLE** — entry с admissible retained evidence: binding sidecar и bundle прошли binding checks (§8.4) и v1 bundle verification (`oracle_eval.verify`, v1 §8).
- **MISSING** — любая entry, которая не PRE и не BUNDLE. **`MISSING ⇒ NOT_PASSED`.**

## 5. Registry

### 5.1 Authority constants

Нормативные константы production; не параметры, не environment, не CLI:

| Константа | Значение |
|---|---|
| repository | `definitely-stable/Shift-lab` |
| registry remote | `https://github.com/definitely-stable/Shift-lab.git` |
| registry ref | `refs/heads/delsk/registry` |
| provider API | `https://api.github.com` |
| workflow path | `.github/workflows/oracle-pilot.yml` |
| jobs | `register`, `measure` |
| scientific source branch | `refs/heads/main` |
| v2 results root | `.work/results/DELSK-003-ORACLE-V2/` |
| transition file | `.work/oracle/series-transition.json` |

### 5.2 Физическая форма

Orphan branch `delsk/registry`. Root commit (без parents) содержит дерево ровно `{genesis.json, entries.jsonl}`, `entries.jsonl` пуст (0 bytes). Каждый следующий commit имеет ровно одного parent; его дерево — ровно те же два файла, `genesis.json` byte-identical, `entries.jsonl` = parent `entries.jsonl` + ровно одна строка. Merge commits, другие файлы и иные изменения запрещены. `genesis.json` — canonical file form; `entries.jsonl` — canonical JSONL, строка *i* — entry с `sequence = i`.

### 5.3 Genesis `delsk.oracle.registry-genesis.v1`

| Поле | Значение |
|---|---|
| `schema` | const `delsk.oracle.registry-genesis.v1` |
| `g1_contract` | const `delsk.oracle-contract.v2` |
| `measurement_contract` | const `delsk.oracle-contract.v1` |
| `measurement_freeze_sha256` | const `c56fc053…f7f729` (v1 freeze, §1) |
| `g1_freeze_sha256` | hex64; production обязан требовать равенство SHA-256 bytes `freeze-v2.json` в `main` |
| `repository` | const |
| `registry_ref` | const `refs/heads/delsk/registry` |

`genesis_sha256 = Hc(genesis)`. Genesis создаётся только при activation (§16), reviewed PR и тем же maintainer decision; в этом freeze — не создаётся.

### 5.4 Entry `delsk.oracle.registry-entry.v1`

| Поле | Тип / правило |
|---|---|
| `schema` | const `delsk.oracle.registry-entry.v1` |
| `sequence` | integer ≥ 1; = номер строки |
| `previous_entry_sha256` | hex64; `sequence = 1` → `genesis_sha256`; иначе `entry_sha256` строки `sequence − 1` |
| `g1_contract` | const `delsk.oracle-contract.v2` |
| `repository` | const `definitely-stable/Shift-lab` |
| `workflow_path` | const `.github/workflows/oracle-pilot.yml` |
| `workflow_ref` | `definitely-stable/Shift-lab/.github/workflows/oracle-pilot.yml@refs/heads/<branch>`, branch `[A-Za-z0-9][A-Za-z0-9._/-]{0,199}` (= `GITHUB_WORKFLOW_REF`) |
| `workflow_sha` | hex40; обязан равняться `measured_source_sha` |
| `measured_source_sha` | hex40; ancestor-or-equal head `refs/heads/main` |
| `measurement_identity_sha256` | hex64; = `git_source(measured_source_sha)` (§5.5) |
| `science_identity_sha256` | hex64; = `Hc(science_identity)` той же identity (§6) |
| `phase` | `pilot` \| `reveal`; = `measurement_identity.phase`. Под этим freeze `git_source` выдаёт только `pilot`, поэтому entry `reveal` нарушает §5.5 (`REGISTRY_INVALID`) и `register` её не пишет; reveal требует нового G1 contract |
| `run_id`, `run_attempt` | integers ≥ 1 (`GITHUB_RUN_ID`, `GITHUB_RUN_ATTEMPT` job `register`) |
| `transition` | `null` или полный series-transition record (§7.1) |
| `entry_sha256` | `Hc(entry без entry_sha256)` |

Uniqueness: `(run_id, run_attempt)` уникальна во **всём** registry.

### 5.5 Источник identity

`git_source(sha)` — функция Slice C0 (`oracle_attempts.git_source`): measurement identity v1 из Git object bytes commit `sha` без build/fetch/measurement; требует, чтобы `freeze.json` и `codec-lock.json` в commit были byte-identical v1 (§1), а locks — bindings v1. Commit, который не разрешается или не ancestor-or-equal `main`, — нарушение entry.

### 5.6 Validation и коды без verdict

Порядок проверок фиксирован; первая неудача — единственный blocker, verdict `NO_VERDICT` (§9.5):

1. **`REGISTRY_INVALID`** — нарушена форма §5.2; genesis не canonical/не по schema/`g1_freeze_sha256` ≠ freeze-v2 (production); любая строка не canonical JSON или не по schema; `sequence` ≠ номер строки (gap, повтор, начало не с 1); `previous_entry_sha256` не сходится к предыдущей строке/genesis; `entry_sha256` ≠ `Hc`; `workflow_sha` ≠ `measured_source_sha`; `measured_source_sha` не ancestor-or-equal `main` или не разрешается; `measurement_identity_sha256` ≠ `git_source`; `science_identity_sha256` ≠ §6; `phase` ≠ identity phase; `transition` не по schema или `transition_sha256` ≠ `Hc`.
2. **`REGISTRY_DUPLICATE`** — две entries с одинаковым `(run_id, run_attempt)`.
3. **`REGISTRY_STALE`** — head оцениваемого registry ≠ head, повторно прочитанный с registry remote после завершения оценки.
4. **`REGISTRY_ROLLBACK`** — witnessed head любого retained binding sidecar (§8.2) не является prefix оцениваемой истории: entry с его `sequence` отсутствует или её `entry_sha256` другой (`sequence = 0` → `genesis_sha256`).
5. **`EVIDENCE_ROOT_INVALID`** — §8.1.

Head registry: `registry_head = {sequence, entry_sha256}` последней entry; пустой registry — `{0, genesis_sha256}`.

Повреждённый registry необратим внутри v2 (append-only): `REGISTRY_INVALID` постоянен для этого registry; восстановление — только новым G1 contract с новым genesis, старый registry остаётся раскрытым. Поэтому `register` обязан валидировать весь registry до append и не писать в невалидный.

### 5.7 `register` job (нормативно)

Для своего execution `(GITHUB_RUN_ID, GITHUB_RUN_ATTEMPT)`, до любого другого job:

1. `workflow_dispatch`, repository, `GITHUB_SHA = GITHUB_WORKFLOW_SHA`, branch ref (как C0 `validate_dispatch`); `measured_source_sha` ancestor-or-equal `main`; иначе отказ `DISPATCH_REJECTED` / `SOURCE_NOT_ON_MAIN`.
2. `identity = git_source(GITHUB_SHA)`; `science_identity` по §6.
3. Fetch registry с константного remote/ref; полная validation §5.6 п. 1–2; иначе отказ `REGISTRY_INVALID` / `REGISTRY_DUPLICATE`.
4. Transition (§7.2): если обязателен — прочитать transition file из дерева `measured_source_sha`, проверить schema, digest, `phase`, `new = своя science`, `previous = current series`, ancestry `merge_commit_sha`; включить запись в entry. Обязателен, но отсутствует/невалиден — отказ `TRANSITION_REQUIRED` / `TRANSITION_INVALID`. Не обязателен — `transition = null` (наличие файла игнорируется).
5. Append entry, commit по §5.2, push только явным refspec `HEAD:refs/heads/delsk/registry` на константный remote, без force. Отказ push (не fast-forward) — fetch, повтор с п. 3 (≤ 3 раз). Если entry со своим run key уже есть и все её поля, кроме `sequence`/`previous_entry_sha256`/`entry_sha256`, равны своим, — она принимается как своя (идемпотентность после потерянного ответа).
6. Readback: повторный fetch; head содержит свою entry ровно один раз. Output `entry_sha256`.

Любой отказ — entry не записана, `measure` не начинается (needs), execution — не attempt.

### 5.8 Bind в `measure` job (нормативно, до `B`)

Step роли `bind`:

1. Fetch registry с константного remote/ref; validation §5.6 п. 1–2.
2. Ровно одна entry с `(GITHUB_RUN_ID, GITHUB_RUN_ATTEMPT)`; её `measured_source_sha`, `workflow_sha`, `workflow_ref`, `measurement_identity_sha256` (`git_source(GITHUB_SHA)`), `science_identity_sha256`, `phase` равны своему execution; `entry_sha256` = output `register` того же attempt.
3. Записать binding sidecar `delsk.oracle.attempt-binding.v1` (§8.2) с `observed_head` = head прочитанного registry.
4. Иначе — остановка до `B`, failure class `REGISTRY_UNBOUND`.

«Re-run failed jobs» не исполняет `register` для нового `run_attempt`: entry нет → `bind` останавливается до `B` (§10.2).

## 6. `science_identity`

Конструкция (exact):

```text
mi   = measurement_identity v1 (объект, Hc которого = measurement_identity_sha256; schema v1 run.measurement_identity)
si   = { k: mi[k] for k in mi if k != "measured_source_sha" } ∪ { "schema": "delsk.oracle.science-identity.v1" }
science_identity_sha256 = Hc(si)
```

Поля `si` (closed schema `science_identity`): `schema`, `contract_id`, `contract_freeze_sha256`, `codec_lock_sha256`, `delta {codec_id, options_sha256}`, `standalone {codec_id, options_sha256}`, `corpus_lock_sha256`, `candidate_lock_sha256`, `oracle_code_sha256`, `phase`, `sealed_splits`. Порядок — canonical (sorted keys `Hc`); `sealed_splits` — как в `mi` (v1: `["evaluation"]`).

| Компонент | Входит | Почему |
|---|---|---|
| `measured_source_sha` | **нет** | docs/infra commit не должен создавать новую серию (identity hopping, research CE6) |
| `phase` | да | pilot и reveal — разные процедуры; серии и transitions ведутся по фазе |
| `oracle_code_sha256` | да | measurement apparatus (code manifest v1: `oracle_build.py`, `oracle_run.py`, `oracle_eval.py`, `manifests.py`, `materialize.py`); смена кода — новая серия только через transition |
| locks | да, через `contract_freeze_sha256` (v1 freeze, связывает codec/candidate/corpus/protocol/seal) и явные `codec_lock_sha256`, `corpus_lock_sha256`, `candidate_lock_sha256`, codec refs | |
| schema tag | да | domain separation: `science_identity_sha256` не совпадает ни с одним `measurement_identity_sha256` |

Код вне manifest (`oracle_pilot.py`, workflow, `budget.py`, G1 tooling) серию не меняет. Следствие: реализация v2 G1 tooling **не** должна находиться в файлах v1 code manifest.

Reference vectors SI01–SI04 — [registry-vectors.json](registry-vectors.json) `science_identity_vectors`. SI01 — реальная identity commit `2c89c8d9…` (`git_source`, phase `pilot`):

```text
measurement_identity_sha256 = 07416d16d4e6dc972e6d43ecb79394458804d8afbe77266696e251b2cfd85b02
science_identity_sha256     = f536b5909ec9bd051db91f6c73d9b59cf279562a2637a5e1437aa9160d55944d
```

Тест пересчитывает SI01 через `git_source` на этом commit. SI02/SI03 — другой `measured_source_sha`, та же серия; SI04 — другой `oracle_code_sha256`; SI05 — phase `reveal`: обе — другие серии.

## 7. Series и transitions

**Series** — множество entries одной `science_identity_sha256` (phase входит в identity). Серии каждой фазы образуют цепочку.

### 7.1 Transition record `delsk.oracle.series-transition.v1`

| Поле | Тип |
|---|---|
| `schema` | const |
| `g1_contract` | const `delsk.oracle-contract.v2` |
| `phase` | `pilot` \| `reveal` |
| `previous_science_identity_sha256`, `new_science_identity_sha256` | hex64, различны |
| `reason` | `BUG_FIX` \| `SEMANTIC_CHANGE` \| `IMPLEMENTATION_CHANGE` |
| `change_review` | `{pull_request: integer ≥ 1, merge_commit_sha: hex40}` |
| `transition_sha256` | `Hc(record без transition_sha256)` |

Reviewed transition file — этот record в canonical file form в дереве `measured_source_sha`. Reasons: `BUG_FIX` — код не реализовывал frozen v1 semantics; `IMPLEMENTATION_CHANGE` — изменение, задуманное как сохраняющее semantics; `SEMANTIC_CHANGE` — изменение измеряемой semantics, допустимо только при разных `contract_freeze_sha256` предыдущей и новой серий, т. е. только с новым frozen measurement contract (v1 §0); под этим freeze (`git_source` допускает только v1) такой transition всегда `MISMATCH`.

### 7.2 Когда transition обязателен

Transition обязателен ровно у **первой entry новой `science_identity`** в фазе, где уже есть хотя бы одна entry. Первая entry фазы открывает первую серию без transition.

Решение принимается только по registry (без provider), поэтому `register` может его исполнить. Это строже D3 («после natural attempt»): серия, где были только PRE-попытки, тоже заменяется только через transition (§17.2).

### 7.3 State machine (детерминированная, по `sequence`)

Для каждой фазы: `current` (нет), `retired` (∅), `orphans` (∅), `taint[S]` (∅). Для entry `e` фазы со science `S` и transition `T`:

```text
T = null:
  current нет            → current := S
  S = current            → —
  S ∈ retired            → taint[S] += SERIES_REENTRY
  S ∈ orphans            → —
  S новая                → orphans += S; taint[S] += SERIES_TRANSITION_MISSING
T ≠ null (status T):
  current нет            → current := S; taint[S] += SERIES_TRANSITION_MISMATCH;     status MISMATCH
  S = current или S ∈ orphans → taint[S] += SERIES_TRANSITION_MISMATCH;              status MISMATCH
  S ∈ retired            → taint[S] += SERIES_REENTRY;                               status REENTRY
  S новая:
     T.previous ∈ retired                       → orphans += S; taint[S] += SERIES_FORK;  status FORK
     иначе нарушено любое из V1–V6               → orphans += S; taint[S] += SERIES_TRANSITION_MISMATCH; status MISMATCH
     иначе                                       → retired += current; current := S;      status VALID
```

Условия валидности transition новой серии `S` при `current = C`:

- **V1** `T.phase = e.phase`, `T.new = S`, `T.previous = C`.
- **V2** provider: pull request `change_review.pull_request` репозитория merged, его `merge_commit_sha` = `T.change_review.merge_commit_sha`, base ref `refs/heads/main`.
- **V3** `merge_commit_sha` ancestor-or-equal `e.measured_source_sha` и ancestor-or-equal `main`.
- **V4** science identity `git_source(merge_commit_sha)` = `S` (reviewed merge порождает новую серию).
- **V5** reason: `SEMANTIC_CHANGE` ⇔ `contract_freeze_sha256` у `C` и `S` различаются (§7.1).
- **V6** `S` ещё не имеет entries (переход только в новую серию; переход в существующую — `MISMATCH` или `REENTRY` выше).

Свойства: одна серия заменяется не более одного раза (fork запрещён), возврат к retired серии запрещён (`REENTRY`), цепочка фазы линейна; orphan серия никогда не становится current и не блокирует законную цепочку. Malformed transition (не по schema/digest) — `REGISTRY_INVALID` (§5.6); stale (`previous` ≠ current) — `MISMATCH`.

### 7.4 Series codes для identity `I` серии `S`

- `taint[S]` целиком;
- `SERIES_SUPERSEDED`, если `S ∈ retired` (серия заменена; её G1 не может быть PASS после замены);
- carry-over (D3), где **siblings** = entries серии `S` с identity ≠ `I` и классом ≠ PRE, плюс unbound attempts (§8.5) серии `S` с identity ≠ `I`, в любой момент registry (раньше и позже entries `I`):
  - sibling с нарушениями или outcome `INVALID` → `SERIES_INVALID`;
  - sibling `MISSING` (без нарушений), outcome `INCOMPLETE` / `COMPLETE_WITH_FAILURES`, или `COMPLETE` без conformance PASS → `SERIES_FAILURE`;
  - среди всех `BUNDLE` `COMPLETE` entries серии (включая `I`) больше одного `series_repeat = (series_projection_sha256, sealed_commitments_sha256)` → `SERIES_REPEAT_MISMATCH`.

`series_projection_sha256` = SHA-256 canonical JSONL всех unsealed rows (`delsk.oracle.pair.v1`, `delsk.oracle.standalone.v1`, `delsk.oracle.target.v1`) bundle без ключей `RUN_SPECIFIC` v1 §9, в canonical order v1 §9. Нужен потому, что v1 `cost_projection_sha256` содержит `measured_source_sha` и не сравним между identities серии; `sealed_commitments_sha256` v1 уже не зависит от source.

Legit transition прекращает carry-over: исходы retired серии не переходят в новую. Старая серия, её entries, классы и transition остаются в disclosure каждого record (§9.6).

## 8. Evidence

### 8.1 Retained results root

`.work/results/DELSK-003-ORACLE-V2/` в `main`, только через reviewed PR. Production читает root из дерева текущего head `refs/heads/main`, полученного с константного remote, а не из рабочего дерева вызывающего. Допустимое содержимое — ровно:

```text
bundles/<run_id>-<run_attempt>/     v1 evidence bundle байт в байт (v1 §12, проверяется oracle_eval.verify)
bindings/<run_id>-<run_attempt>.json  delsk.oracle.attempt-binding.v1, canonical file form
```

`EVIDENCE_ROOT_INVALID` (verdict не выпускается), если: любой другой path, symlink или имя не `^[1-9][0-9]*-[1-9][0-9]*$`; binding sidecar не canonical/не по schema или его run key ≠ имени файла; run key любого bundle или binding отсутствует в registry (Model 1, §10.1); run key из v2 registry присутствует в v1 root `.work/results/DELSK-003-ORACLE/` (bundle, sidecar или ledger) — смешивание v1/v2.

### 8.2 Binding sidecar `delsk.oracle.attempt-binding.v1`

Поля: `schema`, `g1_contract`, `repository`, `run_id`, `run_attempt`, `measured_source_sha`, `measurement_identity_sha256`, `entry_sequence`, `entry_sha256`, `observed_head {sequence, entry_sha256}`, `binding_sha256 = Hc(без binding_sha256)`. Пишется step `bind` до `B` (§5.8). `observed_head` — witness level 1 (§13.1).

### 8.3 Provider observation и PRE

Provider observation `delsk.oracle.provider-observation.v1` — нормализованная проекция provider API для `(run_id, run_attempt)`, полученная production с константного provider API по всем страницам: `run = null` (run не найден/удалён) или `run = {head_sha, head_branch, workflow_path, event, status, latest_run_attempt, jobs[]}`; job = `{name, started, conclusion, steps[]}`; step = `{number, role ∈ {bind, boundary, other}, started, conclusion}`. Нормализация: `started = true` ⇔ provider сообщает status `in_progress`/`completed` и conclusion ≠ `skipped`; role — по именам steps из activation record; неизвестный job name сохраняется как есть.

**Run binding.** Observation соответствует entry `e`, если `head_sha = e.measured_source_sha`, `workflow_path = e.workflow_path`, `event = workflow_dispatch`, `e.workflow_ref = <repository>/<workflow_path>@refs/heads/<head_branch>`.

**PRE(e)** ⇔ все условия:

1. observation получена в текущей оценке от production provider (retained копии и sidecars — только disclosure);
2. `run ≠ null`, run binding выполнен, `status = completed`;
3. все job names ∈ `{register, measure}`, job `measure` не более одного;
4. job `measure` отсутствует, или `started = false`, или в нём ровно один step роли `boundary` и каждый step с `number ≥ boundary.number` имеет `started = false`.

Иначе — не PRE. Потерянное доказательство (run удалён, run не `completed`, неполные данные) — не PRE.

### 8.4 Классификация entry и нарушения

Для entry `e` с run key `k`, observation `o(k)`, bundle `bundles/k` (может отсутствовать), binding `bindings/k` (может отсутствовать). **Нарушения** (`violations`, INVALID-класс):

- `DUPLICATE_EXECUTION` — `e.entry_sha256` указан более чем в одном retained binding sidecar (получают все entries, чьи sidecars входят в группу, и сама `e`);
- `BINDING_MISMATCH` — `o(k).run ≠ null` и run binding не выполнен; binding sidecar есть и его `run_id`, `run_attempt`, `repository`, `measured_source_sha`, `measurement_identity_sha256`, `entry_sequence`, `entry_sha256` ≠ entry; verified bundle, чей `run.json` (`github.repository/run_id/run_attempt/sha/workflow_sha/workflow_ref`, `measurement_identity_sha256`) ≠ entry; bundle есть, `o(k).run ≠ null`, но step `boundary` job `measure` не начинался (bundle не может происходить из этого execution);
- `UNBOUND_MEASUREMENT` — bundle есть, а binding sidecar нет; binding sidecar с `observed_head.sequence < e.sequence` (binding не мог видеть свою entry); bundle есть, `o(k).run ≠ null`, а step `bind` не начинался, не `success` или не раньше `boundary`.

Класс:

```text
violations ≠ ∅                                         → MISSING (outcome INVALID для G1)
bundle есть, verified, o(k).run ≠ null                  → BUNDLE, outcome = summary.run_status
bundle есть, но не verified или o(k).run = null          → MISSING
bundle нет, PRE(e)                                      → PRE
иначе                                                   → MISSING
```

«Verified» — `oracle_eval.verify(bundle) = []` и имя каталога = run key `run.json`; для verified bundle проекция `bundle_projection` (schemas-v2) даёт v1 attempt record (`run_status`, `cost_projection_sha256`, `targets_sha256`, `sealed_commitments_sha256`, `conformance`, `bundle_verified`) и `series_projection_sha256`.

### 8.5 Unbound attempts зарегистрированных runs

Для каждого `run_id`, имеющего entry, и каждого `n ∈ 1..latest_run_attempt` этого run без entry `(run_id, n)`: если PRE-условия §8.3 (с run binding по entry этого run_id) не доказаны для observation `(run_id, n)` — это **unbound attempt** identity entries этого run (`UNBOUND_MEASUREMENT`, outcome INVALID). Это ограниченная проверка только зарегистрированных run IDs, а не перечисление всей provider history (§10.1). Удаление run делает его entries `MISSING`, а не улучшает verdict.

## 9. G1 v2

### 9.1 Алгоритм для measurement identity `I`

1. Прочитать registry с константного remote/ref; validation §5.6 п. 1–4.
2. Validation evidence root §8.1. Любая неудача 1–2 → `NO_VERDICT`, единственный blocker.
3. `E(I)` = entries с `measurement_identity_sha256 = I`; `U(I)` = unbound attempts identity `I` (§8.5).
4. Классифицировать **каждую** entry registry (все identities и фазы): PRE / BUNDLE / MISSING + violations (§8.4); построить series state machine (§7.3). Если `E(I) = U(I) = ∅` → `NOT_RUN` (blockers пусты, disclosure полный); шаги 5–10 не применяются.
5. PRE исключить из scientific population; оставить в disclosure.
6. Records: каждая BUNDLE entry `E(I)` → её v1 attempt record; каждая entry `E(I)` с violations и каждый `U(I)` → record `run_status = INVALID`.
7. `MISSING` без violations в `E(I)` → ledger keys без record.
8. v1: `(v1_verdict, v1_blockers) = g1(records)` — v1 §7 дословно (функция `oracle_eval.g1`: `INVALID` precedence с `RUN_INVALID`/`REPEAT_MISMATCH`, `RUN_<status>`, `CONFORMANCE_OR_BUNDLE`, `REPEAT_MISSING` по различным `github_run_id`); если `v1_verdict ≠ INVALID` и есть missing keys → `NOT_PASSED`, добавить `RESULT_MISSING` (семантика `g1_inventory` `ATTEMPT_NOT_RETAINED`).
9. v2 codes: violations entries `E(I)`; `UNBOUND_MEASUREMENT`, если `U(I) ≠ ∅`; series codes §7.4.
10. Gates: `KAT_NOT_VERIFIED`, если KAT suite не зелёный на `measured_source_sha` `I` по существующему `oracle_attempts.kat_verified` (Actions API, exact commit, every attempt counts); `V2_NOT_ACTIVE` в production до activation (§16).
11. Verdict (§9.3) и record (§9.6).

Caller не выбирает entries, bundles или subset: population выводится из registry, evidence — из фиксированного root (§11).

### 9.2 Codes

| Класс | Codes |
|---|---|
| `NO_VERDICT` | `REGISTRY_INVALID`, `REGISTRY_DUPLICATE`, `REGISTRY_STALE`, `REGISTRY_ROLLBACK`, `EVIDENCE_ROOT_INVALID` |
| `INVALID` | v1: `RUN_INVALID`, `REPEAT_MISMATCH`; v2: `BINDING_MISMATCH`, `UNBOUND_MEASUREMENT`, `DUPLICATE_EXECUTION`, `SERIES_INVALID`, `SERIES_REPEAT_MISMATCH`, `SERIES_TRANSITION_MISMATCH`, `SERIES_FORK`, `SERIES_REENTRY` |
| `NOT_PASSED` | v1: `RUN_INCOMPLETE`, `RUN_COMPLETE_WITH_FAILURES`, `CONFORMANCE_OR_BUNDLE`, `REPEAT_MISSING`; v2: `RESULT_MISSING`, `SERIES_FAILURE`, `SERIES_TRANSITION_MISSING`, `SERIES_SUPERSEDED`, `KAT_NOT_VERIFIED`, `V2_NOT_ACTIVE` |

Runner-level (не G1) коды отказа: `DISPATCH_REJECTED`, `SOURCE_NOT_ON_MAIN`, `REGISTRY_INVALID`, `REGISTRY_DUPLICATE`, `TRANSITION_REQUIRED`, `TRANSITION_INVALID` (`register`); `REGISTRY_UNBOUND` (`bind`).

### 9.3 Verdict combination

```text
X = v2 codes класса INVALID; Y = v2 codes класса NOT_PASSED
v1_verdict = INVALID или X ≠ ∅ → INVALID,    blockers = (v1_blockers если v1_verdict = INVALID) ∪ X
иначе v1_verdict = NOT_PASSED или Y ≠ ∅ → NOT_PASSED, blockers = v1_blockers ∪ Y
иначе                              → SCIENTIFIC_PASS, blockers = []
```

Blockers — sorted unique. Core verdicts: `SCIENTIFIC_PASS`, `NOT_PASSED`, `INVALID`, `NOT_RUN`, `NO_VERDICT`. Никакой code path core не выдаёт `PASS`.

### 9.4 Монотонность

PASS требует: все non-PRE entries `I` — BUNDLE verified `COMPLETE` с одним repeat tuple, ≥ 2 различных run ID, conformance PASS; нет unbound attempts; все siblings серии чисты и совпадают по `series_repeat`; серия current и без taint; KAT зелёный. Удаление provider данных или evidence может только перевести entry в `MISSING` (или снять доказательство PRE) — оба исхода блокируют PASS. Добавление entry не может превратить non-PASS в PASS (v1 lemma 3 + carry-over).

### 9.5 `NO_VERDICT`

Record с `verdict = NO_VERDICT`, одним blocker, пустыми `attempts`/`unbound_attempts`/`series`/`transitions`, `science_identity_sha256 = null`. `registry_head` и `genesis_sha256` = `null` только при `REGISTRY_INVALID`, иначе — значения оцениваемого registry.

### 9.6 G1 record `delsk.oracle.g1-record.v1`

Поля: `schema`, `g1_contract` (const v2), `measurement_contract` (const v1), `measurement_identity_sha256`, `science_identity_sha256` (hex64 или null при `NOT_RUN`/`NO_VERDICT`), `verdict`, `blockers`, `registry_head`, `genesis_sha256`, `attempts` (все entries registry по `sequence`: `sequence`, `entry_sha256`, `run_id`, `run_attempt`, `phase`, `measurement_identity_sha256`, `science_identity_sha256`, `class`, `outcome` (`run_status` для BUNDLE, иначе null), `conformance` (bool для BUNDLE, иначе null), `violations`), `unbound_attempts` (по `(run_id, run_attempt)`), `series` (по `(phase, first_sequence)`: `phase`, `science_identity_sha256`, `first_sequence`, `state ∈ {CURRENT, RETIRED, ORPHAN}`, `codes` = taint), `transitions` (по `sequence`: `sequence`, `status ∈ {VALID, MISMATCH, FORK, REENTRY}`, `transition`), `authority`, `evaluator`, `external_checkpoint`, `record_sha256 = Hc(без record_sha256)`.

Production record: `authority` = константы §5.1, `evaluator = {g1_code_sha256, evaluator_source_sha}`, verdict ∈ {`PASS`, `NOT_PASSED`, `INVALID`, `NOT_RUN`, `NO_VERDICT`}. Test record: `authority = evaluator = null`, verdict ∈ {`TEST_ONLY_PASS`, `NOT_PASSED`, `INVALID`, `NOT_RUN`, `NO_VERDICT`}. Schema запрещает `PASS` при `authority = null` и `TEST_ONLY_PASS` при `authority ≠ null`. `external_checkpoint` — §13.2.

## 10. Незарегистрированные executions и reruns

### 10.1 Model 1

Unregistered provider execution (нет entry для её run key):

- не является scientific attempt и не принимается как evidence;
- её bundle или sidecar в retained results root → `EVIDENCE_ROOT_INVALID`;
- не может быть зарегистрирована после пересечения `B` (§4.4: binding до `B` невозможен; поздняя entry даёт `UNBOUND_MEASUREMENT`).

Обнаруживать **все** unregistered provider runs не требуется: это вернуло бы недоказуемую полноту provider history. Единственная provider-проверка unregistered attempts — ограниченная §8.5 для run IDs, уже присутствующих в registry. Частные вычисления на публичных inputs вне reviewed workflow — вопрос leakage/sealing v1 §9.1, не provenance.

### 10.2 Reruns

| Действие | Registry | Следствие |
|---|---|---|
| Re-run all jobs | `register` исполняется для нового `run_attempt` → новая entry | отдельный scientific attempt; тот же `run_id` не является independent repeat (v1 `REPEAT_MISSING` по различным run ID) |
| Re-run failed jobs / один job | `register` для нового `run_attempt` не исполняется → entry нет | `bind` останавливается до `B` (`REGISTRY_UNBOUND`); не attempt, если `B` не пересечена; если implementation пересекла `B` — unbound attempt, `INVALID UNBOUND_MEASUREMENT` (§8.5) |
| Новый dispatch | новая entry, новый `run_id` | может быть independent repeat при остальных условиях v1 §7 |

## 11. Production / test separation

- **Production entry point** — `g1_production(measurement_identity_sha256)`: ровно этот параметр. Не принимает HTTP getter, provider implementation, registry path, remote URL, repository, results root, список bundles/entries/snapshot или иной subset. Authority hard-bound к константам §5.1 в reviewed коде; registry и evidence root (§8.1) получает сам с константного remote; env/CLI их не меняют (credential для rate limit из `GITHUB_TOKEN` допустим и authority не меняет).
- **Internal/test core** — `_g1_core(...)` с injected registry/provider/evidence/git/KAT; возвращает core verdict §9.3 и никогда `PASS`. Fake providers живут только в `.work/tests`.
- **Test wrapper** — `SCIENTIFIC_PASS → TEST_ONLY_PASS`, record с `authority = null`. Test result никогда не превращается в production `PASS`: production не принимает records/verdicts как input и вычисляет всё сам.
- `PASS` выдаёт только `g1_production`: `SCIENTIFIC_PASS` core над данными, которые он сам получил от констант, и пройденный activation gate. Production модуль не импортирует test модули; v1 `oracle_attempts.g1_root(get=…)` не является v2 path.
- Проверяется при activation: `inspect.signature`, отсутствие `PASS` в core, R17.

## 12. Rulesets и write-token isolation (требования; в этом PR не настраиваются)

### 12.1 Rulesets

| Ruleset | Target | Rules | Bypass |
|---|---|---|---|
| registry | `refs/heads/delsk/registry` | `deletion`, `non_fast_forward` | пуст |
| scientific source | `refs/heads/main` (и любые refs с frozen scientific bytes) | `deletion`, `non_fast_forward`, `pull_request` (direct write запрещён) | по решению maintainer; workflow token / `github-actions` — никогда |

`contents: write` у `GITHUB_TOKEN` — **repository-level capability**, не branch-scoped. Поэтому activation требует server-side negative test тем же credential, которым пишет `register`: push в `main`, удаление registry branch и non-fast-forward push в registry — все три отклонены сервером, ответы сохранены как activation evidence. Этот test относится к activation (§16), не к protocol-freeze CI.

### 12.2 Workflow (минимум)

`register`: `permissions: contents: write`, остальные scopes не указаны (= none); без natural corpus, codec, measurement, сторонних actions кроме pinned checkout; `persist-credentials: false`; token доступен только step registry update; константы remote/ref/tree; push только explicit refspec `HEAD:refs/heads/delsk/registry`.

`measure`: `needs: register`; `permissions: contents: read` (+ `actions: read` для admission); нет registry write; step `bind` (§5.8) до step `boundary`; corpus и codecs только после `boundary`. Concurrency `delsk-experimental`, как C0.

## 13. Witness

### 13.1 Level 1 (обязателен для P1)

Каждый retained binding sidecar несёт `observed_head`. Validation требует, чтобы каждый witnessed head был prefix текущей valid history (`REGISTRY_ROLLBACK`, §5.6). Остаточное окно: усечение хвоста, ещё не засвидетельствованного retained evidence; против non-admin его закрывает registry ruleset (§12.1), против admin — только §13.2.

### 13.2 Independent immutable checkpoint (интерфейс; провайдер не фиксируется)

Перед внешней публикацией G1 record обязан иметь `external_checkpoint = {head, locator, checkpoint_sha256}`, где checkpoint: (1) в trust domain, не управляемом admin Shift-lab; (2) immutable/append-only с собственной tamper evidence; (3) доступен третьей стороне по `locator` (`https://…`); (4) коммитит exact `registry_head`; (5) его head — prefix оцениваемой истории, `sequence ≥` head record. Record с `external_checkpoint = null` (все P1 records) не является evidence для внешней публикации. Технология выбирается отдельным решением (D5).

## 14. Reference vectors R01–R22

Нормативно — [registry-vectors.json](registry-vectors.json) (`delsk.oracle.registry-vectors.v1`): для каждого case — exact synthetic registry (genesis + entries), `registry_remote_head`, provider observations, evidence (bundle projections, binding sidecars, foreign paths, v1 root keys), environment (git_source identities, ancestry, `main` head, pull requests, KAT), expected core verdict и **полный expected test record** с `record_sha256` для каждой оцениваемой identity, плюс runner-level ожидания (R12, R21). Expected outputs заморожены до implementation; implementation обязана воспроизвести их байт в байт (`record_sha256`). Records в vectors — test records (`authority = evaluator = null`, `TEST_ONLY_PASS`). Genesis vectors несёт synthetic `g1_freeze_sha256`: test core его не проверяет, production проверяет (§5.3). Bundle в vectors задан проекцией `bundle_projection` — выходом v1 `verify` + `attempt_record`, который v1 KATs уже покрывают; `cost_projection_sha256`/`targets_sha256` в проекциях различаются между identities, как в v1.

| # | Сценарий | Ожидание |
|---|---|---|
| R01 | genesis + 2 entries, 2 run ID, оба COMPLETE identical; вторая identity без entries | `SCIENTIFIC_PASS` → `TEST_ONLY_PASS`; `NOT_RUN` |
| R02 a–d | разрыв chain; `entry_sha256` ≠ Hc; gap sequence; повтор sequence | `NO_VERDICT REGISTRY_INVALID` |
| R03 a–b | witnessed head дальше head (усечение); witnessed head с другим digest | `NO_VERDICT REGISTRY_ROLLBACK` |
| R04 | две entries одного `(run_id, run_attempt)` | `NO_VERDICT REGISTRY_DUPLICATE` |
| R05 | A, B COMPLETE; C зарегистрирован, run и evidence удалены | `NOT_PASSED RESULT_MISSING` |
| R06 | A, B COMPLETE; C retained INVALID | `INVALID RUN_INVALID` |
| R07 a–c | bundle/sidecar unregistered run; только sidecar; run key v2 в v1 root | `NO_VERDICT EVIDENCE_ROOT_INVALID` |
| R08 a–b | C PRE: `bind` упал, `boundary` не начинался; `measure` не стартовал | `TEST_ONLY_PASS`, C в disclosure как PRE |
| R09 a–c | C: только pre-B sidecar, run удалён; run `in_progress`; неизвестный job | `NOT_PASSED RESULT_MISSING` (self-report не даёт PRE) |
| R10 a–b | C: provider показывает старт `boundary`; started `measure` без `boundary` step | `NOT_PASSED RESULT_MISSING` |
| R11 | `(X,1)` и `(X,2)` COMPLETE | `NOT_PASSED REPEAT_MISSING` |
| R12 a–b | failed-job rerun `(X,2)` без entry: остановка до `B`; пересёк `B` | a: `TEST_ONLY_PASS` + runner `REGISTRY_UNBOUND`; b: `INVALID RUN_INVALID UNBOUND_MEASUREMENT` |
| R13 a–c | bundle SHA ≠ entry; provider SHA ≠ entry; bundle при не начатом `boundary` | `INVALID BINDING_MISMATCH RUN_INVALID` |
| R14 | sidecar `entry_sha256` ≠ entry | `INVALID BINDING_MISMATCH RUN_INVALID` |
| R15 a–e | carry-over серии: sibling INVALID; sibling MISSING; sibling другой projection; sibling PRE; legit transition | `SERIES_INVALID`; `SERIES_FAILURE`; `SERIES_REPEAT_MISMATCH`; PASS; новая серия PASS, старая INVALID |
| R16 a–c | binding после `B`: `observed_head` < entry; bundle без sidecar; `bind` не success | `INVALID RUN_INVALID UNBOUND_MEASUREMENT` |
| R17 | `_g1_core` с fake provider, всё зелёное | core `SCIENTIFIC_PASS`, test `TEST_ONLY_PASS`, authority null; production signature `(measurement_identity_sha256)` |
| R18 | head ≠ remote head | `NO_VERDICT REGISTRY_STALE` |
| R19 a–b | лишняя entry без provider run той же identity; другой серии | `NOT_PASSED RESULT_MISSING`; другая серия orphan, `I` — PASS |
| R20 | два sidecar с одним `entry_sha256` | `INVALID BINDING_MISMATCH DUPLICATE_EXECUTION RUN_INVALID` |
| R21 a–b | новая серия без transition после natural / после только PRE | `NOT_PASSED SERIES_TRANSITION_MISSING`; runner `TRANSITION_REQUIRED` |
| R22 a–e | `previous` ≠ current; merge commit не ancestor; fork; reentry; PR не merged | `SERIES_TRANSITION_MISMATCH`; `…MISMATCH`; `SERIES_FORK` + старая `SERIES_SUPERSEDED`; `SERIES_REENTRY`; `…MISMATCH` |

## 15. Mutation obligations PM01–PM10

Implementation (не этот PR) обязана применить каждый mutant к production/core коду и показать, что указанные vectors его убивают. Если mutant выживает, implementation не активируется.

| Mutant | Дефект | Убивают | Если выживает |
|---|---|---|---|
| PM01 | MISSING игнорируется (ledger без records не блокирует) | R05, R09a, R10a, R19a | удалённый run даёт PASS |
| PM02 | population из bundles, а не из registry | R05, R07a, R19a | attempt исчезает из population |
| PM03 | bundle/sidecar unregistered run принимается или игнорируется | R07a, R07b | evidence без attempt влияет на verdict |
| PM04 | PRE по sidecar/status или неполным provider данным | R09a, R09b, R09c | пересёкший `B` run объявлен пустым |
| PM05 | rerun того же run ID — independent repeat | R11 | два attempts одного run дают PASS |
| PM06 | hash chain / `entry_sha256` / sequence не проверяются | R02a–d | подменённая или усечённая история принята |
| PM07 | PASS через injected provider/core | R17 | fake provider даёт production PASS |
| PM08 | нет carry-over внутри серии | R15a, R15b, R15c | identity hopping обнуляет неудачу |
| PM09 | binding после `B` принят | R16a–c, R12b | регистрация задним числом / unbound rerun |
| PM10 | смена `science_identity` без transition принята | R21a, R21b | молчаливый reset серии |

Машиночитаемо — `mutants` в [registry-vectors.json](registry-vectors.json).

## 16. Activation criteria

v2 implementation становится active только после выполнения **всех**:

1. этот v2 freeze смержен;
2. registry tooling реализован (register, bind, validation, классификация, G1 core/production) вне файлов v1 code manifest;
3. R01–R22 воспроизведены байт в байт (`record_sha256`) независимой реализацией без импорта генератора vectors;
4. PM01–PM10 убиты;
5. production/test API separation проверена (§11, R17);
6. registry genesis создан reviewed PR (`g1_freeze_sha256` = этот freeze);
7. rulesets §12.1 реально настроены и проверены read-only API (правила, пустой bypass registry, отсутствие workflow token в bypass `main`);
8. synthetic real-GitHub registry smoke выполнен без corpus;
9. сценарии rerun all, rerun failed (остановка до `B`), cancel до и после `register`, удаление synthetic run → `MISSING` выполнены;
10. write-surface negative tests §12.1 — PASS;
11. independent review;
12. отдельное maintainer decision разрешает natural measurement.

Activation record фиксирует имена steps `bind`/`boundary` (§4.1) и evidence п. 6–10. До выполнения всех пунктов: pilot worker и runner отказывают с `DISPATCH_HISTORY_UNVERIFIED` (C0), v1 G1 — `NOT_PASSED DISPATCH_HISTORY_UNVERIFIED`, v2 production — не PASS (`V2_NOT_ACTIVE`).

## 17. Adversarial self-review

### 17.1 Найденные пути и закрытие

| Попытка | Закрыто |
|---|---|
| attempt исчезает из population | population из registry (§9.1 п. 3), append-only; PRE только по provider (§8.3); PM02 |
| provider deletion улучшает verdict | deletion ⇒ `MISSING`/потеря PRE ⇒ NOT_PASSED; sibling MISSING ⇒ `SERIES_FAILURE` (§7.4; в proposal этого не было — §17.2); R05, R15b |
| PRE по self-report | только live provider observation; sidecar = disclosure; R09 |
| binding создан после `B` | `observed_head` < entry, нет sidecar, `bind` не success ⇒ `UNBOUND_MEASUREMENT`; R16 |
| rerun laundering | каждая entry в population; failed-job rerun без entry, пересёкший `B`, ⇒ unbound INVALID (§8.5); тот же run ID не repeat; R11, R12 |
| identity reset без transition | новая серия без transition ⇒ orphan `SERIES_TRANSITION_MISSING`; docs-commit внутри серии ⇒ carry-over всех нечистых исходов; R15, R21 |
| transition fork | `previous ∈ retired` ⇒ `SERIES_FORK`; R22c |
| возврат к старой серии | `SERIES_REENTRY`; R22d |
| registry tail truncation | ruleset non-FF; level-1 witness ⇒ `REGISTRY_ROLLBACK`; R03 |
| stale registry принят | повторное чтение remote head ⇒ `REGISTRY_STALE`; R18 |
| unregistered bundle принят | `EVIDENCE_ROOT_INVALID`; R07 |
| fake provider ⇒ production PASS | production без injectable параметров; core без `PASS`; R17 |
| caller выбирает subset | нет параметров subset; registry и root читаются с константного remote (root — из head `main`), не из рабочего дерева |
| register credential считается branch-scoped | §12.1: repository-level; negative test при activation |
| test result ⇒ production PASS | `TEST_ONLY_PASS`, `authority = null`, schema-запрет; production не принимает records |
| docs-commit вне `main` как новая identity | `measured_source_sha` обязан быть на `main` (§5.4) |
| copy bundle на чужую entry | sidecar ≠ entry ⇒ `BINDING_MISMATCH`, повтор `entry_sha256` ⇒ `DUPLICATE_EXECUTION`, bundle без начатого `boundary` ⇒ `BINDING_MISMATCH`; R13c, R20 |
| повреждённая entry используется частично | любая ошибка entry ⇒ весь registry `REGISTRY_INVALID` (fail closed) |

### 17.2 Отличия от proposal (исправлено до freeze)

| Proposal | Контракт | Почему |
|---|---|---|
| carry-over только `INVALID`, `CWF`, `REPEAT_MISMATCH` | + `MISSING`, `INCOMPLETE`, COMPLETE без conformance | **контрпример:** sibling INVALID run удалён до retention ⇒ при proposal серия получает PASS, при retained — `SERIES_INVALID`: deletion улучшал verdict |
| `REPEAT_MISMATCH` внутри серии → NOT_PASSED | `SERIES_REPEAT_MISMATCH` → INVALID | как v1 `REPEAT_MISMATCH`: недетерминированное измерение одной науки |
| repeat серии по v1 digests | `series_projection_sha256` | v1 `cost_projection_sha256` содержит `measured_source_sha` и различается между identities серии |
| transition после non-PRE attempt | после любой entry другой серии | решение только по registry, исполнимо в `register`, не зависит от изменчивых provider данных; строже |
| `science_identity = Hc(identity без source)` | + `schema` tag | domain separation |
| B = шаг build | семантическое определение §4.1 + witness step | не зависит от YAML |
| `RESULT_MISSING` вместо `ATTEMPT_NOT_RETAINED` | `RESULT_MISSING` | v2 класс MISSING; семантика та же |
| unregistered rerun registered run — не рассмотрено | §8.5 unbound attempts | закрывает failed-job rerun, пересёкший `B` |
| — | `measured_source_sha` на `main`, `SERIES_SUPERSEDED`, `SERIES_REENTRY`, V4–V5 | identity commits неудаляемы; retired серия не PASS; нет циклов; reason проверяем |

Проблем в D1–D5, требующих STOP, не найдено: все исправления усиливают proposal внутри принятых решений.

## 18. Не заморожено и ограничения

- Реализация registry, workflow, G1 tooling; имена steps `bind`/`boundary`; genesis; rulesets — activation (§16).
- Phase `reveal`: schemas и series machine её допускают, но под этим freeze entry `reveal` невалидна (§5.4), G1 v2 определён только для `pilot`.
- Провайдер external checkpoint (§13.2).
- Malicious admin (D4); частные вычисления на публичных inputs.
- Повреждение registry необратимо внутри v2 (§5.6). Любой writer с `contents: write` может fast-forward добавить в registry мусор: это постоянный `REGISTRY_INVALID` (DoS, никогда не PASS); restrict-updates для registry не замораживается, восстановление — новым G1 contract.
- Provider data — authority binding и PRE только пока run существует: удаление run или истечение provider retention метаданных jobs/steps делает его entries `MISSING` при любой последующей оценке; G1 record — состояние на момент оценки.
- Vectors и контракт написаны одним автором; независимость даёт отдельная implementation (§16 п. 3, 11).
