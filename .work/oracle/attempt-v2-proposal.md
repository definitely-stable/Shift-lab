# Proposal: `delsk.oracle-contract.v2` — registered-attempt provenance

Статус: **PROPOSAL, НЕ FROZEN.** Это не контракт и не freeze record. Нормативная версия после решений D1–D5 — [contract-v2.md](contract-v2.md); где они расходятся, действует контракт (его §17.2). Frozen [contract.md](contract.md) v1, [freeze.json](freeze.json), codec lock, schemas, vectors, `C_t`, locks и thresholds не меняются. Natural oracle и G1 = **NOT_RUN**. Обоснование и литература — [desk research](../research/DELSK-ATTEMPT-V2-DESK-RESEARCH.md). Реализация начинается только после принятия решений §11 и отдельного задания.

## 1. Scope

v2 меняет только **experiment provenance**: что считается попыткой, кто authority её существования, как попытки попадают в G1. Measurement science v1 включается целиком по hash:

```text
v2 = { measurement_layer: v1 (contract.md, codec-lock.json, schemas.json, known-answer.json,
                              oracle_reference.py, test_oracle_contract.py — bytes по freeze.json v1),
       replaces: v1 §7 «G1 population» и строки pilot/repeat v1 §12,
       adds:     registry, binding, PRE classification, production/test API, R-vectors }
```

`measurement_identity` (v1 §9) строится **без изменений**, включая `contract_id = "delsk.oracle-contract.v1"`: это идентификатор правил измерения, и схемы v1 фиксируют его как `const`. G1 record несёт отдельное поле `g1_contract = "delsk.oracle-contract.v2"`. Попытки, записанные в v2 registry, оцениваются только v2 G1; v1 G1 для них остаётся `NOT_PASSED DISPATCH_HISTORY_UNVERIFIED` навсегда (нет verdict shopping).

## 2. Определения

- **Граница измерения `B`.** Первый шаг, исполняющий код измерительного аппарата (`oracle_build.py`) или читающий хотя бы один byte natural corpus, что раньше. В текущем pilot это шаг build.
- **Registry.** Orphan branch `delsk/registry` репозитория `definitely-stable/Shift-lab`; файл `entries.jsonl`, одна запись на строку, canonical compact JSON (`manifests.digest`).
- **Scientific attempt.** Запись registry. Существует тогда и только тогда, когда записана и прочитана обратно **до** `B` исполнения, которое она связывает.
- **Bind-before-measure.** Reviewed код до `B` проверяет, что registry содержит ровно одну запись с его `(run_id, run_attempt)`, совпадающими source/workflow/identity; иначе остановка до `B` с `REGISTRY_UNBOUND`.
- **`science_identity`.** `Hc(measurement_identity без measured_source_sha)`.

## 3. Registry entry `delsk.oracle.registry-entry.v1`

| Поле | Тип | Назначение |
|---|---|---|
| `schema` | const | закрытая схема |
| `sequence` | int ≥ 1 | 1 у первой записи после genesis, +1 далее |
| `previous_entry_sha256` | hex64 | `Hc` предыдущей записи; у первой — `Hc(genesis)` |
| `g1_contract` | const `delsk.oracle-contract.v2` | |
| `repository` | const | |
| `workflow_path`, `workflow_ref`, `workflow_sha` | str | `workflow_sha = measured_source_sha` |
| `measured_source_sha` | hex40 | |
| `measurement_identity_sha256` | hex64 | `git_source` на `measured_source_sha` |
| `science_identity_sha256` | hex64 | |
| `phase` | `pilot` \| `reveal` | |
| `run_id`, `run_attempt` | int | provider binding, известен `register` job из `GITHUB_RUN_ID`/`GITHUB_RUN_ATTEMPT` |
| `transition` | object \| null | transition record (§3.1); не null ровно у первой записи новой `science_identity` после natural попытки другой `science_identity` той же фазы |
| `entry_sha256` | hex64 | `Hc(запись без entry_sha256)` |

### 3.1 Transition record между `science_identity`

```text
transition = { previous_science_identity_sha256, new_science_identity_sha256,
               reason: BUG_FIX | SEMANTIC_CHANGE | IMPLEMENTATION_CHANGE,
               change_review: { pull_request_url, merge_commit_sha } }
```

- **Когда обязателен.** Если registry уже содержит запись фазы с другой `science_identity` и классом не `PRE` (natural попытка была), первая запись новой `science_identity` обязана нести `transition`. `previous_science_identity_sha256` — `science_identity` последней такой записи; `new_science_identity_sha256` — своей.
- **Откуда берётся.** Reviewed файл `.work/oracle/series-transition.json` в дереве `measured_source_sha`. `register` job копирует его в запись до `B`; если файл обязателен, но отсутствует или не совпадает с registry history, `register` отказывает: нет записи, нет измерения.
- **`change_review`.** `merge_commit_sha` — предок `measured_source_sha`; PR — тот, которым изменён код. Проверяется G1 через git и provider API.
- **Семантика.** Transition прекращает carry-over старой серии (реальный bug fix не тащит старый `INVALID` навечно), но старая серия и причина перехода входят в disclosure каждого G1 record. Повторный transition из той же старой серии в другую новую запрещён (`SERIES_FORK`): одна серия заменяется одной.

Genesis: `{"schema":"delsk.oracle.registry-genesis.v1","repository":…,"g1_contract":…,"v1_freeze_sha256":…}` — первый коммит ветки, создаётся reviewed PR вместе с v2 freeze **до** первой v2 попытки.

Валидация (fail-closed, иначе `REGISTRY_INVALID`, вердикт не вычисляется): каждая запись закрыта по схеме; `sequence` непрерывна; цепочка `previous_entry_sha256` сходится к genesis; `(run_id, run_attempt)` уникальны (`REGISTRY_DUPLICATE`); каждый коммит ветки добавляет ровно одну строку в конец и ничего не меняет; оцениваемый head равен текущему remote head (`REGISTRY_STALE` иначе); каждый registry head, записанный в retained sidecars в `main` (witness уровень 1), — префикс оцениваемой истории (`REGISTRY_ROLLBACK` иначе).

### 3.2 Rulesets и write surface

`contents: write` у `GITHUB_TOKEN` — permission на contents всего репозитория, не на одну ветку. На 2026-10-05 у Shift-lab rulesets = `[]` и `main` не защищён, поэтому до активации обязательны (настраивает maintainer, проверяется read-only API):

| Ruleset | Target | Rules | Bypass |
|---|---|---|---|
| registry | `refs/heads/delsk/registry` | `deletion`, `non_fast_forward` | пуст |
| scientific refs | `refs/heads/main` (и любые будущие refs с frozen scientific bytes) | `deletion`, `non_fast_forward`, `pull_request` (direct push отклоняется) | по решению maintainer; workflow token — никогда |

Remote URL, ref и форма дерева registry (orphan tree ровно с `genesis.json` и `entries.jsonl`) — константы reviewed кода. Push только явным refspec `HEAD:refs/heads/delsk/registry`. Readback с другой формой дерева = отказ.

## 4. Workflow topology (B2 self-registration)

```text
oracle-pilot.yml (workflow_dispatch, exact source_sha, concurrency delsk-experimental)
  job register   permissions: только contents: write (остальные scopes не указаны → none);
                 checkout кода с persist-credentials: false; без corpus, codecs и сторонних actions;
                 token передаётся только шагу push
                 identity = git_source(GITHUB_SHA); transition из series-transition.json (§3.1);
                 fetch registry; append entry (run_id, run_attempt);
                 fast-forward push; при отказе — fetch, проверить что ключа нет, повторить (≤ 3);
                 readback: ls-remote head содержит entry; output entry_sha256
  job measure    needs: register; permissions: contents: read, actions: read
                 до B: fetch registry; ровно одна запись для (GITHUB_RUN_ID, GITHUB_RUN_ATTEMPT);
                 поля = run env; digest = needs.register.outputs.entry_sha256; иначе REGISTRY_UNBOUND
                 далее — существующий pilot без изменений scientific кода;
                 sidecar attempt.json (v2) несёт entry_sha256 и registry head
```

«Re-run failed jobs» не повторяет `register`, поэтому `measure` новой попытки не находит записи и останавливается до `B`. Штатный rerun — «Re-run all jobs». Corpus и codecs никогда не обрабатываются в job с write token.

### B1 pre-submission broker (альтернатива)

Если maintainer предпочтёт регистрацию до submission: broker пишет `REGISTERED`, затем `SUBMITTING` (durable до POST), POST dispatch (документирован ответ 200 с `workflow_run_id`), затем `ACKNOWLEDGED(run_id)`. Bind-before-measure обязателен и здесь: run ждёт `ACKNOWLEDGED` со своим `run_id` ограниченное время, иначе останавливается до `B`. Тогда потерянный ответ не опасен: без ACK ни один run не пересёк `B`, и `UNRESOLVED` классифицируется как `PRE`. B1 добавляет credential оператора, CLI и состояние `UNRESOLVED` без научного выигрыша; [oracle_dispatch.py](../tools/oracle_dispatch.py) остаётся foundation на этот случай.

## 5. Классификация записей

| Класс | Условие (только из provider API и bound evidence) | Роль в G1 |
|---|---|---|
| `PRE` | provider jobs/steps API для `(run_id, run_attempt)`: `measure` не стартовал, или его шаг `B` не имеет `started_at` | нейтрален, перечисляется в record |
| `BUNDLE` | retained bundle `<run_id>-<run_attempt>`, sidecar `entry_sha256` = записи, provider run: тот же SHA, workflow path, event, attempt | исход по v1 (`COMPLETE`/`CWF`/`INCOMPLETE`/`INVALID`) |
| `MISSING` | всё остальное, включая удалённый run без retained bundle | `NOT_PASSED` (`RESULT_MISSING`) |

Self-reported sidecar без provider-подтверждения не даёт `PRE`.

## 6. G1 v2

Для identity `I`:

1. Прочитать и провалидировать registry (§3) с фиксированного remote.
2. Results root: каждый bundle и sidecar обязан иметь запись; иначе `EVIDENCE_ROOT_INVALID` (вердикт не выпускается).
3. `A(I)` = записи с `measurement_identity_sha256 = I` минус `PRE`.
4. `records` = attempt records `BUNDLE` из `A(I)`; `ledger` = ключи всех `A(I)`.
5. `verdict, blockers = oracle_eval.g1_inventory(records, ledger)` — **frozen функция без изменений** (`MISSING` = её `ATTEMPT_NOT_RETAINED`).
6. Carry-over (решение D3): если любая запись той же `science_identity` (другой `measured_source_sha`) имеет исход `INVALID` → `INVALID (SERIES_INVALID)`; `COMPLETE_WITH_FAILURES` или `REPEAT_MISMATCH` между COMPLETE записями серии → `NOT_PASSED (SERIES_FAILURE)`.
7. Transitions (§3.1): первая запись `science_identity` `I` после natural попытки другой серии без валидного `transition` → `NOT_PASSED (SERIES_TRANSITION_MISSING)`; `transition`, не совпадающий с registry history или с `change_review` → `INVALID (SERIES_TRANSITION_MISMATCH)`; второй transition из одной старой серии → `INVALID (SERIES_FORK)`. Валидный transition прекращает carry-over старой серии.
8. KAT: существующий `kat_verified` (Actions API) без изменений; иначе `KAT_NOT_VERIFIED`.
9. Record: verdict, blockers, `g1_contract`, registry head SHA и последний `entry_sha256`, полный список записей фазы (все identity) с классами, все transition records с причинами и change review, evaluator SHA, provider base URL.

v1 G1 таблица §7 остаётся ядром дословно: INVALID-приоритет, `REPEAT_MISMATCH`, NOT_PASSED для `INCOMPLETE`/`CWF`, `CONFORMANCE_OR_BUNDLE`, `REPEAT_MISSING` (два разных `run_id`). v2 меняет только откуда берётся популяция и добавляет `PRE`, carry-over, transitions и disclosure.

## 7. Production / test API

```text
g1_production(identity) -> (verdict, blockers, record)    # без get/resolve_source/registry параметров
_g1_core(identity, registry, provider, kat) -> CoreVerdict  # возвращает SCIENTIFIC_PASS, не PASS
test helper: offline_g1(...) -> TEST_ONLY_PASS | ...        # только в .work/tests
```

`PASS` формируется только в `g1_production`, которая сама строит provider (`https://api.github.com`, константный repository) и читает registry `git fetch` с константного remote. Проверки: сигнатура без параметров провайдера; ни один путь `_g1_core` не возвращает `PASS`; `g1_root(get=…)` v1 удаляется из production модуля.

## 8. Vectors (новый набор, synthetic only)

| # | Сценарий | Ожидание |
|---|---|---|
| R01 | genesis + 2 записи, 2 run ID, оба COMPLETE identical | `PASS` (через `TEST_ONLY_PASS` в тесте) |
| R02 | разрыв hash chain | `REGISTRY_INVALID` |
| R03 | head короче зафиксированного witness head (усечение хвоста) | `REGISTRY_ROLLBACK` |
| R04 | две записи с одним `(run_id, run_attempt)` | `REGISTRY_DUPLICATE` |
| R05 | A, B COMPLETE; C записан, run и bundle удалены | `NOT_PASSED RESULT_MISSING` |
| R06 | A, B COMPLETE; C retained INVALID | `INVALID` |
| R07 | bundle без записи в results root | `EVIDENCE_ROOT_INVALID` |
| R08 | A, B COMPLETE; C `PRE` (jobs API: `measure` не стартовал) | `PASS`, C в disclosure |
| R09 | C: sidecar говорит `bootstrap`, provider данных нет | `MISSING → NOT_PASSED` |
| R10 | C: provider показывает старт шага `B` | не `PRE` |
| R11 | `(X,1)` и `(X,2)` COMPLETE, один run ID | `NOT_PASSED REPEAT_MISSING` |
| R12 | failed-job rerun: `measure` без своей записи | runner-level: остановка до `B`, запись не создаётся |
| R13 | bundle source SHA ≠ записи | `INVALID BINDING_MISMATCH` |
| R14 | sidecar `entry_sha256` ≠ записи | `INVALID BINDING_MISMATCH` |
| R15 | серия: ранний SHA INVALID, новый SHA два COMPLETE | `INVALID SERIES_INVALID` |
| R16 | evidence: binding найден после старта `B` | `INVALID UNBOUND_MEASUREMENT` |
| R17 | `_g1_core` с fake provider, всё зелёное | `SCIENTIFIC_PASS`, наружу `TEST_ONLY_PASS`; production сигнатура без провайдера |
| R18 | оцениваемый head ≠ remote head | `REGISTRY_STALE` |
| R19 | лишняя запись без provider run | `MISSING → NOT_PASSED` |
| R20 | два bundle ссылаются на одну запись | `INVALID DUPLICATE_EXECUTION` |
| R21 | серия S1 имела natural попытку; первая запись S2 без `transition` | `NOT_PASSED SERIES_TRANSITION_MISSING`; runner-level: `register` отказывает |
| R22 | `transition` ссылается не на последнюю серию, `merge_commit_sha` не предок source, или второй transition из S1 | `INVALID SERIES_TRANSITION_MISMATCH` / `SERIES_FORK` |

Mutants (каждый обязан быть убит): PM01 missing игнорируется (R05); PM02 популяция из bundles (R05, R07); PM03 unregistered bundle принимается (R07); PM04 `PRE` по sidecar (R09); PM05 reruns как независимые (R11); PM06 цепочка не проверяется (R02); PM07 PASS через injected provider (R17); PM08 без carry-over (R15); PM09 binding после `B` принят (R16); PM10 смена `science_identity` без transition принята (R21).

Reuse без изменений: K01–K42, G01–G09, M01–M30, metamorphic, C01–C14 и golden, fault injection. Slice A/B не повторяются.

## 9. Change matrix v1 → v2

| Area | v1 (frozen + C0) | v2 proposal | Reason | Scientific impact |
|---|---|---|---|---|
| Definition of attempt | не определено; C0: каждый GitHub dispatch/rerun | запись registry до `B` | dispatch population принадлежит provider и удаляема | нет; закрывает невидимое удаление |
| Authority | GitHub Actions inventory | append-only registry branch | provider ≠ научная история | нет |
| Dispatch history | обязана быть полной → недоказуемо | не требуется | лемма покрытия через bind-before-measure | нет |
| Reruns | не independent; каждый attempt в ledger | каждый `run_attempt`, пересёкший `B`, — запись; failed-job rerun не измеряет | rerun не исчезает | нет |
| G1 population | ledger всех dispatched attempts | `A(I)` = записи минус `PRE` | исключение только до получения информации | ослабление только для доказуемо пустых попыток |
| Missing bundle | `ATTEMPT_NOT_RETAINED` | `RESULT_MISSING` (та же семантика) | | нет |
| Unresolved dispatch | permanent blocker | B2: не существует; B1: `PRE` благодаря bind-before-measure | | нет |
| Provider inventory | доказательство полноты | reconciliation и `PRE` | | нет |
| Attempt identity | `(run_id, run_attempt)` | то же + `entry_sha256` | binding к записи | нет |
| Identity hopping | возможно незаметно | disclosure + carry-over внутри `science_identity` + обязательный transition record между ними (D3) | v1 дефект | ужесточение |
| Write surface | workflows read-only | `register` job с `contents: write` (весь репозиторий) при обязательных rulesets на registry и `main` | registry пишется workflow token | нет, при выполнении §3.2 |
| Production/test API | injectable `get` | hard-bound `g1_production`; test → `TEST_ONLY_*` | | нет |
| KAT | Actions API exact commit | без изменений | KAT переисполним | нет |
| Evidence retention | reviewed PR, append-only | то же + sidecar с `entry_sha256` и registry head | witness уровень 1 | нет |

Byte/semantic compatible: pair universe, oracle, `D_E`, `S/O/O_delta`, frame v1, codecs и options, `C_t`, rows и schemas, sealing и reveal, metrics, measurement identity, evaluator scientific logic, frozen `g1`/`g1_inventory`.

## 10. Activation criteria (до снятия блокера в v2 path)

1. v2 freeze record принят maintainer merge (отдельный PR после этого research).
2. Оба ruleset §3.2 настроены; read-only API подтверждает правила, пустой bypass registry и отсутствие bypass для workflow token на `main`.
3. Genesis в registry; v2 attempts tooling и R-vectors зелёные в CI.
4. Synthetic-only `registry-smoke` workflow на реальном GitHub: UI dispatch, rerun all, rerun failed (остановка до `B`), cancel до и после `register`, удаление synthetic run → G1 `NOT_PASSED`. Negative test write surface: тот же `register` credential пытается push в `main`, удалить registry и сделать non-FF push в registry — все три отклонены сервером, результат сохранён как evidence активации. Corpus не используется.
5. Review. После этого v2 path заменяет `DISPATCH_HISTORY_UNVERIFIED` на `REGISTRY_BINDING_REQUIRED`; v1 path остаётся заблокирован.
6. Natural pilot — только после отдельного подтверждения maintainer.

## 11. Решения maintainer

| ID | Вопрос | Рекомендация |
|---|---|---|
| D1 | v2 как G1-слой с неизменной `measurement_identity` (contract_id v1) или полный bump identity | G1-слой: bump меняет frozen schemas `const`, evaluator и vectors без научной причины |
| D2 | B2 self-registration или B1 pre-submission broker | B2 |
| D3 | carry-over внутри `science_identity` и обязательный transition record (`BUG_FIX \| SEMANTIC_CHANGE \| IMPLEMENTATION_CHANGE` + change review) между ними | принять |
| D4 | adversary model P1 = honest-but-fallible оператор + crash/infra + non-admin writers; malicious admin вне scope до release claims | принять явно |
| D5 | witness | уровень 1 сейчас, уровень 2 (Software Heritage snapshot) перед публикацией |
