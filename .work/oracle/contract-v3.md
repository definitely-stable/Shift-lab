# DELSK-003A: provenance/G1 contract `delsk.oracle-contract.v3`

Статус: **FROZEN с момента merge в `main`**. Идентичность принятых bytes — [freeze-v3.json](freeze-v3.json). Implementation: **NOT_ACTIVE**. Natural oracle: **NOT_RUN**. G1: **NOT_RUN**. Ни один natural byte не читался, registry v3 не создан, rulesets для v3 не настроены.

**Verdict: `DELSK-003A PROTOCOL V3 FROZEN` / `V3 IMPLEMENTATION NOT_ACTIVE`.**

Основание: реальная activation-процедура v2 ([activation-c1b-log.md](activation-c1b-log.md), PR [#32](https://github.com/definitely-stable/Shift-lab/pull/32)) нашла, что §8.3 п. 4 v2 недоказуем на данных GitHub Actions; maintainer decisions D1–D5 ([issue #27](https://github.com/definitely-stable/Shift-lab/issues/27)) не меняются. Журнал activation — пояснительный, **не нормативный**.

Ключевые слова: «обязан», «запрещено», «только» — нормативны. Вне нормативного текста — примечания.

## 0. Governance и layering

```text
measurement_contract   = delsk.oracle-contract.v1   (bytes по .work/oracle/freeze.json, без изменений)
g1_provenance_contract = delsk.oracle-contract.v3   (этот документ и freeze-v3.json)
base_text              = delsk.oracle-contract.v2   (contract-v2.md по exact hash через freeze-v2.json)
```

- **v3 = текст v2 с заменами.** Нормативное содержание v3 — §0–§18 [contract-v2.md](contract-v2.md) (bytes закреплены [freeze-v2.json](freeze-v2.json), SHA-256 `d8e3c33a8eeaed7c112189b98bd8bd7f7d2a422aa8efca6733528738f2a34b57`) с подстановками §0.2 и заменами §1–§6 этого документа. Где этот документ молчит, действует текст v2 после подстановок. Measurement layer v1 включается так же, как в v2 (§1 v2, SHA-256 `freeze.json` = `c56fc053b103cecd38446b3791db104a12b9fafabacdfc6b71f6f23c0bf7f729`).
- **v2 заменён до активации.** v2 никогда не был active: ни одной production-оценки, ни одной entry в `refs/heads/delsk/registry`. Реализация v2 заменяется реализацией v3; v2 production entry point не существует и не может выпустить `PASS`. Refs v2 `refs/heads/delsk/registry` (только genesis) и `refs/heads/delsk/registry-smoke` (синтетические entries activation-попытки) сохраняются под rulesets и раскрыты в журнале; v3 их не читает и не оценивает.
- **Нет смешивания v2 и v3.** Каждый объект v3 (genesis, entry, transition, binding sidecar, G1 record) несёт `g1_contract = "delsk.oracle-contract.v3"`; объект с `g1_contract` v2 по schemas-v3 невалиден, поэтому v2 registry или v2 binding в v3 — `REGISTRY_INVALID` / `EVIDENCE_ROOT_INVALID`. v1 G1 path остаётся навсегда `NOT_PASSED DISPATCH_HISTORY_UNVERIFIED`, как в §0 v2.
- **Неизменяемость.** Этот контракт, [schemas-v3.json](schemas-v3.json), [registry-vectors-v3.json](registry-vectors-v3.json) и [test_oracle_contract_v3.py](../tests/test_oracle_contract_v3.py) неизменяемы после merge; bytes v1 и v2 — тоже (v3 включает их по hash). Любое изменение семантики — только новый G1 contract с новым freeze record.
- **Кто принимает.** Maintainer merge этого contract в `main` — акт adoption.
- **Что adoption не делает.** Не активирует v3 (активация — §5), не создаёт registry, не настраивает rulesets, не разрешает natural run. До активации production pilot и v1 G1 отказывают с `DISPATCH_HISTORY_UNVERIFIED` ([Slice C0](slice-c.md)), v3 production — `NOT_PASSED V3_NOT_ACTIVE` без единого чтения.
- **Trust model** — D4 без изменений.

### 0.1 Почему нужен v3

Нормализация §8.3 v2 сохраняет каждый step job, а п. 4 PRE требует `started = false` для **каждого** step с `number ≥ boundary.number`. GitHub Actions добавляет в каждый стартовавший job собственные steps, которых нет в workflow: `Complete job` (всегда, последним) и `Post <имя step>` для каждого исполненного step с action, у которого есть post hook (`actions/checkout`). Они исполняются после остановки и нумеруются после всех steps workflow. Поэтому под v2 PRE недоказуем для любого execution, у которого стартовал job `measure`. Каждая остановка до `B` давала `MISSING`, а «Re-run failed jobs» с отказом `bind` — unbound attempt `INVALID`, что противоречит §10.2 v2. Воспроизведено на реальных runs 2026-10-05 (журнал, fixture [github-actions-smoke-2026-10-05.json](../tests/fixtures/github-actions-smoke-2026-10-05.json)). Ложного `PASS` дефект не давал, но делал §16 п. 8–9 v2 невыполнимыми.

Второе расхождение: job `measure`, отменённый до получения runner, GitHub сообщает как `completed` / `cancelled` без единого step. По нормализации это `started = true`, и PRE для него v2 тоже не доказывал.

### 0.2 Подстановки в тексте v2

| В тексте v2 | В v3 |
|---|---|
| `delsk.oracle-contract.v2` — идентификатор G1 contract во всех объектах, schemas, records, `g1_contract` | `delsk.oracle-contract.v3` |
| «v2 G1», «v2 production», «v2 registry», «v2 evidence root», «v2 freeze» | то же для v3 |
| `freeze-v2.json` как freeze **этого** контракта (§5.3 `g1_freeze_sha256`, §9.0, §9.1 п. 10) | `freeze-v3.json` (§5.4 этого документа: KAT дополнительно требует неизменные bytes `freeze-v2.json`) |
| `schemas-v2.json`, `registry-vectors.json`, `test_oracle_contract_v2.py` | `schemas-v3.json`, `registry-vectors-v3.json`, `test_oracle_contract_v3.py` |
| registry ref `refs/heads/delsk/registry` | `refs/heads/delsk/registry-v3` |
| v2 results root `.work/results/DELSK-003-ORACLE-V2/` | `.work/results/DELSK-003-ORACLE-V3/` |
| `delsk.oracle.provider-observation.v1` | `delsk.oracle.provider-observation.v2` |
| code `V2_NOT_ACTIVE` | `V3_NOT_ACTIVE` |
| R01–R24, PM01–PM12 | R01–R25, PM01–PM20 (§4) |

Прочие schema tags (`delsk.oracle.registry-genesis.v1`, `…registry-entry.v1`, `…series-transition.v1`, `…attempt-binding.v1`, `…g1-record.v1`, `…science-identity.v1`) не меняются: эти объекты различаются полем `g1_contract`. Provider observation этого поля не имеет, поэтому её tag повышается.

## 1. Замена §8.3 v2: provider observation и PRE

Provider observation `delsk.oracle.provider-observation.v2` — нормализованная проекция provider API для `(run_id, run_attempt)`, полученная production с константного provider API по всем страницам: `run = null` (run не найден/удалён) или `run = {head_sha, head_branch, workflow_path, event, status, latest_run_attempt, jobs[]}`; job = `{name, started, conclusion, runner_assigned, steps[]}`; step = `{number, role ∈ {bind, boundary, provider, other}, started, conclusion}`.

Нормализация: `started = true` ⇔ provider сообщает status `in_progress`/`completed` и conclusion ≠ `skipped`; `runner_assigned = false` ⇔ provider сообщает поля job `runner_id` и `runner_name` и оба равны `null`, иначе `true` (отсутствующее поле — `true`; `runner_group_id` не учитывается: у job с runner он бывает `null`); role — по точным именам steps из activation record: имя step `bind` → `bind`, имя step `boundary` → `boundary`, имя из закрытого набора provider steps (§1.1) → `provider`, любое другое имя → `other`. Неизвестный job name сохраняется как есть.

### 1.1 Provider steps

Provider steps — steps, которые provider создаёт сам и которых нет в reviewed workflow. Закрытый набор имён фиксирует activation record (§5). Он равен ровно:

- `Complete job`;
- `Post <N>` для каждого step reviewed job `measure`, который стоит **до** step `boundary` и использует pinned action **с post hook**, где `<N>` — его `name:`. Action имеет post hook ⇔ его metadata (`action.yml`) по точному pinned SHA объявляет `runs.post`. Для actions, допустимых §2: `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1` — `runs.post: dist/index.js`, post hook есть; `actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a` — только `runs.main`, post hook нет. Reviewed карта «action → post hook» — часть witness (§2); новый action или новый pinned SHA требует её review.

Других provider steps нет. Step с любым другим именем — `other`, в том числе переименованный provider step, `Post <N>` step'а после `boundary` и `Post <N>` step'а, чей action не имеет post hook. Если GitHub изменит имена своих steps, они станут `other`, и PRE перестанет доказываться (fail closed: `MISSING`, никогда `PASS`).

### 1.2 Run binding

Как в v2: observation соответствует entry `e`, если `head_sha = e.measured_source_sha`, `workflow_path = e.workflow_path`, `event = workflow_dispatch`, `e.workflow_ref = <repository>/<workflow_path>@refs/heads/<head_branch>`.

### 1.3 PRE

**PRE(e)** ⇔ все условия:

1. observation получена в текущей оценке от production provider (retained копии и sidecars — только disclosure);
2. `run ≠ null`, run binding выполнен, `status = completed`;
3. все job names ∈ `{register, measure}`, job `measure` не более одного;
4. job `measure`:
   - отсутствует, или
   - `started = false`, или
   - имеет `conclusion = cancelled`, пустой `steps` и `runner_assigned = false` (job отменён до получения runner: provider сообщает его без единого step и без runner), или
   - содержит ровно один step роли `boundary`, и каждый step с `number ≥ boundary.number` и role ≠ `provider` имеет `started = false`.

5. `e.measured_source_sha` witnessed (§1.5).

Иначе — не PRE. Потерянное доказательство (run удалён, run не `completed`, неполные данные) — не PRE. Job без steps — неполные данные, если он не `cancelled` или у него есть runner: не PRE.

§8.5 v2 (unbound attempts зарегистрированных runs) применяет эти условия без изменений текста: failed-job rerun, остановленный `bind` до `B`, теперь PRE-доказуем и unbound attempt не образует; rerun, пересёкший `B`, по-прежнему unbound (`INVALID UNBOUND_MEASUREMENT`); rerun исполнения, чей workflow не witnessed, PRE не доказывает и тоже unbound.

### 1.4 Почему исключение безопасно

- `Complete job` — служебный step runner после всех steps job: workflow-кода он не исполняет и natural bytes не читает.
- `Post <N>` исполняет post hook action step'а `N`, который стоит до `boundary`. По §2 такие actions входят в статическое доказательство §4.1: ни один step до `boundary`, включая post hooks его actions, не пересекает `B`.
- Исключение действует только на роль `provider`, то есть на точные имена закрытого набора. Witness (§2) запрещает reviewed workflow давать step такое имя, поэтому workflow-step им не замаскировать.
- Job без steps и без runner, отменённый до его назначения, не исполнял ни одного step: код workflow исполняется только на runner. Пустой `steps` сам по себе этого не доказывает, поэтому дополнительно требуется явный `runner_id = runner_name = null` от provider.

### 1.5 Привязка к точному исполненному workflow

Static witness §4.1/§2 доказывает свойства **конкретных bytes** `.github/workflows/oracle-pilot.yml`. Activation record фиксирует `workflow_sha256` — SHA-256 этих reviewed bytes, на которых выполнен witness. Commit `c` **witnessed** ⇔ SHA-256 файла `.github/workflows/oracle-pilot.yml` в дереве `c` равен `workflow_sha256`. Production получает bytes из Git-объектов pinned snapshot (§9.0) и строит множество `workflow_witnessed` commits entries.

Замена §8.4 v2 (класс): entry `e`, у которой `e.measured_source_sha` не witnessed, — **MISSING**: ни PRE, ни BUNDLE, независимо от provider facts и retained evidence. Violations §8.4 v2 вычисляются как прежде. Для такой entry нет статического доказательства bind-before-`B`: другая версия workflow могла пересечь `B` до `bind` при тех же именах steps. Любое изменение `oracle-pilot.yml` после activation требует нового activation record (новый `workflow_sha256`). Иначе attempts новой версии — MISSING, а не PRE.

## 2. Дополнение §4.1 v2: implementation witness

К witness §4.1 добавляется. Reviewed job `measure`:

1. Каждый step job `measure` имеет явное `name:`, и все имена попарно различны: provider steps сопоставляются по имени, поэтому ни одно имя (и производное `Post <имя>`) не может относиться к двум steps.
2. Actions steps до `boundary` — только pinned (full commit SHA) `actions/checkout` и `actions/upload-artifact`. Их post hooks (по reviewed карте §1.1 — только у checkout) входят в статическое доказательство «до `boundary` `B` не пересекается».
3. Ни один step job `measure` не называется `Set up job` или `Complete job` и не начинается с `Post `.
4. Набор provider steps activation record равен набору, выведенному из reviewed workflow по §1.1.
5. `workflow_sha256` activation record равен SHA-256 bytes `oracle-pilot.yml`, на которых выполнен witness (§1.5).

Нарушение любого пункта — implementation дефектна, activation недействительна.

## 3. Замена строк §5.1 и §12.1 v2

| Константа (§5.1) | v3 |
|---|---|
| registry ref | `refs/heads/delsk/registry-v3` |
| v3 results root | `.work/results/DELSK-003-ORACLE-V3/` |

Остальные константы §5.1 (repository, remote, provider API, workflow path `.github/workflows/oracle-pilot.yml`, jobs `register`/`measure`, source branch, transition file) — без изменений.

§12.1: registry ruleset обязан включать `refs/heads/delsk/registry-v3` (rules `deletion`, `non_fast_forward`, bypass пуст). Refs v2 сохраняют свою защиту: удалять или переписывать их запрещено, раскрытие v2 activation-попытки должно оставаться проверяемым.

## 4. Vectors и mutants (замена ссылок §14–§15 v2)

`registry-vectors-v3.json` строится так: `T(registry-vectors.json)`, затем `R25`, затем `PM13–PM17`. `schemas-v3.json` = `D(schemas-v2.json)`. D, T и построение R25 нормативно определены в [test_oracle_contract_v3.py](../tests/test_oracle_contract_v3.py), который проверяет оба файла байт в байт.

### 4.1 D

Подстановки §0.2 к каждому string value schemas-v2; `$id = delsk.oracle.schemas.v3`; новая `description`; `provider_step.role` = `[bind, boundary, provider, other]`; `provider_job` получает обязательное boolean `runner_assigned`; `environment` — обязательный, `environment_override` — необязательный массив `workflow_witnessed` (hex40); шаблоны id: vector `R01–R25`, case и `killed_by` `R01–R25` с суффиксом `.a–.l`, mutant `PM01–PM20`.

### 4.2 T: R01–R24

T применяет подстановки §0.2 к каждому string value документа v2 и перевычисляет digests. Для каждого объекта v2 с **корректным** собственным digest строится отображение старого digest в Hc преобразованного объекта: genesis — `Hc(genesis)`, entry — `entry_sha256`, transition — `transition_sha256`. Каждое вхождение такого digest в документе заменяется новым: цепочка `previous_entry_sha256`, `observed_head`, `registry_remote_head`, `registry_head`, attempts, history external checkpoint. `binding_sha256` и `record_sha256`, корректные в v2, перевычисляются. Некорректный в v2 digest (намеренный дефект вектора) копируется буквально, поэтому каждый дефект R01–R24 сохраняется. Затем T добавляет два входа, которых v2 не знает: `runner_assigned = started` каждого job (стартовавший job имел runner) и `environment.workflow_witnessed` = все commits окружения (каждый вектор v2 исполнял reviewed workflow).

**Сохранение исходов.** v3 меняет только §8.3 п. 4 и добавляет §1.5. Ни одна observation R01–R24 не имеет роли `provider` и не содержит отменённого `measure` без steps, а все commits witnessed. На них п. 4 v3 ≡ п. 4 v2, поэтому `T` сохраняет каждый verdict, blocker, класс, violation, unbound attempt и series state (проверяется). Независимая реализация обязана воспроизвести R01–R24 v3 байт в байт (`record_sha256`). XC01–XC05 — по `expected` после T. SI01–SI05 не меняются.

### 4.3 R25: реальная форма jobs GitHub Actions

R25.a–j — base case после T, в котором заменена ровно одна observation. В ней jobs `register` и `measure` имеют реальную форму: `Set up job`, named checkout, steps workflow, provider steps `Post <checkout>` (14) и `Complete job` (15), `runner_assigned`. Ожидаемые records равны records base case. R25.k–l — base case с `environment_override.workflow_witnessed` без commit `085bbd6` (source entry 1 серии S1). Их ожидание — records R15.b: тот же registry и evidence, entry 1 MISSING. Исход каждый раз выводится из уже замороженного ожидания, а не из реализации.

| Case | Base | Run key | Форма | Класс / исход |
|---|---|---|---|---|
| R25.a | R08.a | C | остановка до `B`: bind ✓, sidecar ✓, последний step до `boundary` ✗, `boundary` skipped, provider steps исполнены | PRE |
| R25.b | R10.a | C | как R25.a, но стартовал step после `boundary` вне закрытого набора | MISSING |
| R25.c | R10.a | C | `boundary` ✓ (пересечение), ничего не retained | MISSING |
| R25.d | R12.a | (RA, 2) | failed-job rerun: bind ✗, `boundary` skipped, provider steps исполнены | не unbound |
| R25.e | R12.b | (RA, 2) | failed-job rerun без entry пересёк `B` | unbound, INVALID |
| R25.f | R08.b | C | `measure` `completed`/`cancelled`, `steps = []` | PRE |
| R25.g | R08.a | C | cancel после `register`, во время hold до `bind` | PRE |
| R25.h | R10.a | C | cancel после старта `boundary` (`boundary` cancelled) | MISSING |
| R25.i | R10.a | C | `measure` `failure`, `steps = []` (неполные данные) | MISSING |
| R25.j | R10.a | C | `measure` `cancelled`, `steps = []`, но `runner_assigned = true` | MISSING |
| R25.k | R15.d | entry 1 | PRE-доказуемые provider facts, но `085bbd6` не witnessed | MISSING (как R15.b) |
| R25.l | R15.a | entry 1 | verified bundle, но `085bbd6` не witnessed | MISSING (как R15.b) |

### 4.4 PM13–PM20

| Mutant | Дефект | Убивается |
|---|---|---|
| PM13 | исключение действует на любой step после `boundary`, независимо от роли | R25.b |
| PM14 | provider steps не исключаются (правило v2) | R25.a, R25.d, R25.g |
| PM15 | отменённый `measure` без steps не считается нестартовавшим | R25.f |
| PM16 | любой отменённый `measure` считается нестартовавшим | R25.h |
| PM17 | любой `measure` без steps считается нестартовавшим, независимо от conclusion | R25.i |
| PM18 | отменённый `measure` без steps считается нестартовавшим и при назначенном runner | R25.j |
| PM19 | PRE не проверяет, что исполненный `oracle-pilot.yml` — активированный | R25.k |
| PM20 | BUNDLE не проверяет, что исполненный `oracle-pilot.yml` — активированный | R25.l |

PM01–PM12 — как в v2, над R01–R24 v3.

## 5. Замена §16 v2: activation criteria

v3 implementation становится active только после выполнения **всех**:

1. этот v3 freeze смержен;
2. registry tooling реализован (register, bind, validation, классификация, G1 core/production) вне файлов v1 code manifest;
3. R01–R25 воспроизведены байт в байт (`record_sha256`), XC01–XC05 — по `expected`, реализацией без импорта построения vectors;
4. PM01–PM20 убиты;
5. production/test API separation проверена (§11 v2, R17);
6. registry genesis v3 создан reviewed PR (`g1_freeze_sha256` = SHA-256 `freeze-v3.json`) на `refs/heads/delsk/registry-v3`;
7. rulesets §3 реально настроены и проверены read-only API (правила, пустой bypass registry, отсутствие workflow token в bypass `main`);
8. synthetic real-GitHub registry smoke выполнен без corpus;
9. сценарии rerun all, rerun failed (остановка до `B`, PRE-доказуема), cancel до и после `register`, удаление synthetic run → `MISSING` выполнены и доказаны live provider observations по §1;
10. write-surface negative tests §12.1 — PASS на `refs/heads/delsk/registry-v3`;
11. independent review;
12. отдельное maintainer decision разрешает natural measurement.

Activation record фиксирует имена steps `bind`/`boundary` (§4.1 v2), закрытый набор provider steps (§1.1, §2), `workflow_sha256` (§1.5), имя KAT step (§9.1 п. 10 v2) и evidence п. 6–10.

§5.4 — KAT (§9.1 п. 10 v2 после подстановок): проверяемая suite включает v1 frozen files, v2 frozen files (bytes `freeze-v2.json` и его `provenance_layer` не изменены) и v3 frozen files, а также воспроизведение R01–R25, XC, PM01–PM20.

До выполнения всех пунктов: pilot worker и runner отказывают с `DISPATCH_HISTORY_UNVERIFIED` (C0), v1 G1 — `NOT_PASSED DISPATCH_HISTORY_UNVERIFIED`, v3 production — не `PASS` (`V3_NOT_ACTIVE`). **`MISSING ⇒ NOT_PASSED`** — как в v2.

## 6. Adversarial self-review v3

| Попытка | Закрыто |
|---|---|
| назвать workflow step после `boundary` `Complete job` или `Post …`, чтобы скрыть пересечение `B` | §2 п. 3 запрещает такие имена в job `measure`; набор provider steps выводится из workflow и сверяется с activation record (§2 п. 4); PM13, R25.b |
| дать step'у с action после `boundary` имя step'а до `boundary` (или оставить его безымянным), чтобы его `Post …` попал в набор | §2 п. 1: все имена явные и попарно различны |
| post hook action до `boundary` пересекает `B` | §2 п. 2: до `boundary` только pinned checkout и upload-artifact, их post hooks входят в статическое доказательство §4.1 |
| `Post <upload>` (несуществующий post hook) освобождает started step после `boundary` | provider step только для action с `runs.post` по reviewed карте §1.1: upload-artifact его не имеет ⇒ `other` |
| пустой `steps` у отменённого job выдаётся за «runner не назначен» | требуется явный `runner_id = runner_name = null` от provider (§1); PM18, R25.j |
| attempt, исполнившая другую версию `oracle-pilot.yml` (например, natural read перенесён до `boundary` без смены имён steps), оценивается ролями и witness текущего activation record | §1.5: класс требует witnessed source (точные bytes = `workflow_sha256`), иначе MISSING; PM19, PM20, R25.k, R25.l |
| `Post <N>` step'а после `boundary` (main step исполнялся) | не в закрытом наборе ⇒ `other` ⇒ не PRE; R25.b |
| GitHub переименовал provider steps | имена ⇒ `other` ⇒ PRE не доказывается ⇒ `MISSING` (fail closed) |
| усечённый ответ API без steps выдаётся за PRE | правило без steps действует только для `conclusion = cancelled`; иначе не PRE; PM17, R25.i |
| cancel после старта `boundary` выдаётся за PRE | `boundary` cancelled ⇒ `started = true` ⇒ не PRE; правило без steps требует пустой `steps`; PM16, R25.h |
| v2 registry/bindings подаются v3 как свои | `g1_contract` v2 и registry ref v2 невалидны по schemas-v3 ⇒ `REGISTRY_INVALID` / `EVIDENCE_ROOT_INVALID` |
| вернуть правило v2 (PRE никогда) | PM14; R25.a, R25.d, R25.g |
| failed-job rerun, остановленный до `B`, загрязняет серию | теперь PRE-доказуем ⇒ не unbound (R25.d); пересёкший `B` — unbound (R25.e) |

Остальные пути и закрытия §17 v2 сохраняются: v3 меняет только условия PRE и идентификаторы.

## 7. Не заморожено и ограничения

- Реализация, workflow, имена steps `bind`/`boundary`, конкретные имена provider steps, genesis, rulesets — activation (§5).
- Ожидаемые records R25 выведены автором v3 из records base cases (не из реализации); независимость даёт отдельная проверка §5 п. 3, 11. Fixture реальных runs — только иллюстрация формы данных, не evidence activation.
- Набор provider steps опирается на текущие имена GitHub Actions (`Complete job`, `Post <name>`) и поля `runner_id`/`runner_name`; их изменение ведёт к fail closed, не к ложному `PASS`.
- Привязка §1.5 — по точным bytes: любое, даже безобидное, изменение `oracle-pilot.yml` после activation требует нового activation record.
- Ограничения §18 v2 (reveal, external checkpoint, malicious admin, DoS мусором в registry, provider retention) сохраняются.
