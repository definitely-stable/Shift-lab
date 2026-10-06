# DELSK-003A: журнал реальной activation-процедуры contract v3 (2026-10-05)

Основание: [contract-v3.md](contract-v3.md) §5, процедура [slice-c1c.md](slice-c1c.md), `main` = `13c7d74ede7e2fd41bade001ec0e88926882459c` (merge PR [#32](https://github.com/definitely-stable/Shift-lab/pull/32)), [issue #27](https://github.com/definitely-stable/Shift-lab/issues/27). Журнал пояснительный, **не нормативный**; нормативны contract v3 и проверяемые файлы [activation/](activation/).

**Verdict: §5 п. 1–12 выполнены; v3 активируется merge enable PR (§9).** Пункты 6–10 выполнены на реальном GitHub, расхождений с frozen v3 не найдено. Enable record `.work/oracle/activation-v3.json` и `oracle_g1_v2.ACTIVATION_RECORD` добавляет отдельный enable PR; до его merge в `main` v3 **NOT_ACTIVE**. Natural oracle — **NOT_RUN**, G1 — **NOT_RUN**: ни одного run `oracle-pilot.yml`, ни одного natural byte. Natural pilot закрыт C0 guard до отдельного reviewed change (§9).

| §5 | Пункт | Статус | Evidence |
|---|---|---|---|
| 1–5 | freeze, tooling, R01–R25, PM01–PM20, API separation | DONE в PR #32 (CI на `13c7d74`: 716 tests OK, 2 skipped; Oracle smoke 336 OK) | — |
| 6 | genesis v3 (reviewed PR #32 вводит root) | **DONE**: refs созданы обычным push после ruleset (по часам GitHub), readback PASS, `verify_genesis_review` live PASS | [genesis-readback.json](activation/genesis-readback.json), [registry-activity.json](activation/registry-activity.json), [infra.json](activation/infra.json) |
| 7 | rulesets, проверенные read-only API | **DONE**: `verify-rulesets` PASS | [rulesets.json](activation/rulesets.json), [rulesets-pre-genesis.json](activation/rulesets-pre-genesis.json) |
| 8–9 | synthetic smoke, 7 сценариев, live observations | **DONE**: `verify-smoke` PASS | [smoke-scenarios.json](activation/smoke-scenarios.json), [smoke-evaluation.json](activation/smoke-evaluation.json), [smoke-semantics.json](activation/smoke-semantics.json) |
| 10 | write-surface на `refs/heads/delsk/registry-v3` | **DONE**: три операции отклонены сервером | [write-surface.json](activation/write-surface.json), [write-surface-supplementary.json](activation/write-surface-supplementary.json) |
| 11 | review | **DONE**: infra PR #33 смержен в `main` как `3e69105` (решение maintainer 2026-10-05: в проекте один разработчик, approve другого пользователя не требуется) | PR #33 |
| 12 | maintainer decision | **DONE**: комментарий [6008353196](https://github.com/definitely-stable/Shift-lab/issues/27#issuecomment-6008353196) на #27, 2026-10-06T02:52:30Z | `activation-v3.json` |

## 1. Preconditions

- `main` = `13c7d74…`, локальная ветка без divergence; SHA-256 всех файлов freeze-v3/v2/v1 совпадают с записанными; `freeze-v3.json` = `39dede91…1c85` = `reg.G1_FREEZE_SHA256`.
- `python3.12 -m unittest discover -s .work/tests` — 716 OK, 2 skipped; `check-workflows` PASS; `validate.py` PASS.
- PR #32: merged, merge commit `13c7d74…`, final review «PASS / MERGE-READY» на head `3deacaa…`.

## 2. Rulesets (п. 7)

| Ruleset | id | include | rules | bypass | updated_at |
|---|---|---|---|---|---|
| DELSK registry append-only | 24498603 | `refs/heads/delsk/registry`, `…/registry-smoke`, `…/registry-v3`, `…/registry-v3-smoke` | `deletion`, `non_fast_forward` | пуст | `2026-10-05T15:29:07Z` |
| DELSK main provenance protection | 24498754 | `~DEFAULT_BRANCH` | `deletion`, `non_fast_forward`, `pull_request` | пуст | `2026-10-05T11:15:55Z` |

v3 targets добавлены в ruleset 24498603 в `15:29:07Z` **вне этой сессии** (история ruleset недоступна токену сессии: 403); сессия rulesets не меняла. Первый read в начале сессии вернул прежний include без v3 — поэтому collector делает два полных чтения и требует их равенства. Все include — ASCII. Effective rules (`GET /rules/branches/{branch}`): `main` — 3 правила ruleset 24498754; четыре registry refs — `deletion`, `non_fast_forward` ruleset 24498603; контрольные имена (`delsk/registryXYZ`, `delsk/registry-v3-foo`, …) — `[]` (точное совпадение, не префикс). Parent (org) rulesets нет. В bypass `main` нет GitHub Actions (`Integration` 15368). Evidence собран в `15:48:13Z` (до genesis) и повторно после smoke и write-surface; оба — `verify-rulesets` PASS.

**Порядок ruleset → genesis по часам GitHub, а не по локальным.** `collected_at` ставит collector, а root commits имеют детерминированное время `00:00Z`, поэтому сами по себе они порядок не доказывают. Серверные факты: `updated_at` ruleset 24498603 = `15:29:07Z` (последнее изменение); repository activity API ([registry-activity.json](activation/registry-activity.json)) фиксирует `branch_creation` `refs/heads/delsk/registry-v3` в `15:48:31Z` и `refs/heads/delsk/registry-v3-smoke` в `15:48:38Z` (`before` = нули, `after` = reviewed root). Ruleset после создания refs не менялся (иначе его `updated_at` был бы позже), значит при первом push действовала та же конфигурация, что в evidence. Дальше на обоих v3 refs — только `push` fast-forward (smoke: 5 appends от `github-actions[bot]`), на production — ни одного. Ни на одном из четырёх registry refs нет `force_push` и `branch_deletion`, v2 refs заканчиваются на раскрытых heads. Ограничение: содержимое прошлых версий ruleset недоступно (history API: 403). Но для порядка оно не нужно: изменений после создания refs не было.

## 3. Genesis v3 (п. 6)

`oracle_registry_git.py genesis {production,smoke}` на `13c7d74` воспроизвёл закреплённые значения; refs отсутствовали; push `<root>:<ref>` без force.

| Registry | ref | root commit | `genesis_sha256` | `g1_freeze_sha256` |
|---|---|---|---|---|
| production | `refs/heads/delsk/registry-v3` | `1a93f4ce71d9e4fbf5f21eaa9e66c660672ee258` | `e60e5bbc…ac03` | `39dede91…1c85` (= freeze-v3) |
| smoke | `refs/heads/delsk/registry-v3-smoke` | `62f79c1ceeb4f61615039104532e8dee251efaa3` | `c746e25a…14f9a` | `85dbb80d…a914` (domain `registry-smoke-domain.v1`) |

Remote readback (свежий bare fetch + Git Data API): единственный root без parents, дерево ровно `{entries.jsonl (0 B), genesis.json}` mode `100644`, `genesis.json` canonical и равен `make_genesis`, `registry_root()` = root, branch protected. Production registry после всех шагов — только genesis (0 entries).

## 4. Synthetic smoke (п. 8–9)

`oracle-registry-smoke.yml` на `main`, `source_sha = 13c7d74…`, каждый dispatch — после завершения предыдущего.

| Сценарий | run / attempt | Реальная форма (provider) | Entry | Класс |
|---|---|---|---|---|
| `stop-before-boundary` | [37335976976](https://github.com/definitely-stable/Shift-lab/actions/runs/37335976976) / 1 | bind ✓, sidecar ✓, stop ✗, boundary skipped; 14 `Post Read-only source checkout`, 15 `Complete job` | seq 1 | **PRE** |
| `rerun-all` | 37335976976 / 2 | register исполнен заново (новый runner), measure как в attempt 1 | seq 2 | **PRE** |
| `rerun-failed` | 37335976976 / 3 | register переиспользован (runner attempt 2), bind ✗ (отказ), boundary skipped | нет | не unbound |
| `cross-boundary` | [37336944596](https://github.com/definitely-stable/Shift-lab/actions/runs/37336944596) / 1 | bind ✓, boundary ✓ | seq 3 | **MISSING** |
| `cancel-before-register` | [37337045813](https://github.com/definitely-stable/Shift-lab/actions/runs/37337045813) / 1 | cancel во время hold в `register`; `measure` `completed/cancelled`, `steps=[]`, `runner_id = runner_name = null` | нет | — |
| `cancel-after-register` | [37337378535](https://github.com/definitely-stable/Shift-lab/actions/runs/37337378535) / 1 | cancel во время hold в `measure`; bind…boundary skipped; provider steps исполнены | seq 4 | **PRE** |
| `deleted-run` | 37337654750 / 1 | как `stop-before-boundary`, затем `DELETE /actions/runs/37337654750` (204, далее 404) | seq 5 | PRE до удаления → **MISSING** |

Smoke registry head: seq 5, `entry_sha256 = 96a9a6a6…0939`; unbound attempts — нет; test record — `NOT_PASSED` (никогда не PASS). `smoke-evaluate` детерминирован (повторный live-прогон даёт те же bytes); `verify-smoke` PASS. Raw ответы provider всех attempts сохранены до и после удаления (только disclosure).

Проверка исправлений v3 на реальных observations ([smoke-semantics.json](activation/smoke-semantics.json), неизменённый production-классификатор; counterfactuals только убирают входы или применяют frozen mutants PM14/PM18):

| | Проверка | Итог |
|---|---|---|
| A | `cancelled + steps=[]`: provider явно сообщает `runner_id`/`runner_name` = `null` ⇒ `runner_assigned = false`; тот же job с runner — не «не стартовал» | PASS |
| B | наблюдённые `Post …`/`Complete job` = `{Complete job, Post Read-only source checkout}`; `Post` для upload-artifact GitHub не создаёт | PASS |
| C | источник каждой entry несёт точные bytes witnessed workflow; без witness все entries MISSING, а rerun-failed attempt становится unbound | PASS |
| D | rerun-all — новая entry PRE; rerun-failed — без entry и не unbound (PRE доказан против каждой entry run); правило v2 (PM14) дало бы MISSING | PASS |
| E | cross-boundary — MISSING и не PRE, даже если бы все прочие steps считались provider | PASS |
| F | удалённый run — `run = null` ⇒ MISSING; без observations всё MISSING; удаление любой одной observation класс не улучшает | PASS |

## 5. Write surface (п. 10)

`oracle-registry-write-surface.yml`, run [37338024520](https://github.com/definitely-stable/Shift-lab/actions/runs/37338024520) / 1, GitHub-hosted `ubuntu-24.04`, `GITHUB_TOKEN contents: write`. Preflight effective rules PASSED. `push-main`, `non-fast-forward-registry` (`+orphan:refs/heads/delsk/registry-v3`, force-style) и `delete-registry` — `[remote rejected]`, ref до/после неизменен. Artifact `registry-write-surface-37338024520-1` (id 11357271652), zip SHA-256 `b0c0c82c…bad7` совпадает с digest GitHub; [write-surface.json](activation/write-surface.json) — его точные bytes.

Дополнительно (не нормативно) из сессии с admin-правами (`current_user_can_bypass = never`): `--force` и `--force-with-lease` orphan на `refs/heads/delsk/registry-v3` — `GH013 … Cannot force-push to this branch`. Удаление ref отсюда не проверяемо: egress proxy сессии отказывает до GitHub (HTTP 403) — записано как `INCONCLUSIVE` и не засчитано; нормативное доказательство удаления — run выше.

## 6. Refs и неизменность

| Ref | head | commits |
|---|---|---|
| `refs/heads/delsk/registry` (v2, retired) | `6cf2c6a7…` | 1 (genesis) — не изменился |
| `refs/heads/delsk/registry-smoke` (v2, retired) | `d3ec84c7…` | 5 — не изменился |
| `refs/heads/delsk/registry-v3` | `1a93f4ce…` | 1 (genesis) |
| `refs/heads/delsk/registry-v3-smoke` | `479cc9d9…` | 6: genesis + 5 entries, линейно, одна entry на commit, authoritative |

Frozen bytes v1/v2/v3 не менялись. Ни один ref не перезаписывался и не удалялся.

## 7. Infra record и перепроверка

[infra.json](activation/infra.json) (`delsk.oracle.v3-activation-infra.v1`, SHA-256 `8c70fd27d3013c4016bda62ae1e815ace129147014ab05e93e6e6f94693fddaf`): step names, закрытый набор provider steps, `workflow_sha256 = d01036fff8396b274e400fe9f02912473cd9997dab7b4a9f020a3bac346ea81d` (bytes `oracle-pilot.yml` в `13c7d74`), production genesis, `genesis_review` = PR #32 / `13c7d74`, evidence п. 7–10 по SHA-256. `verify-infra` PASS; тест `NotActivatedHere` проверяет его офлайн в каждом CI. Workflow [oracle-activation-evidence.yml](../../.github/workflows/oracle-activation-evidence.yml) перепроверяет всё read-only против live GitHub (`oracle_activation_evidence.py recheck`): rulesets и effective rules, provenance п. 6 так же, как enable path (`verify_genesis_review`: PR #32 смержен в `main` записанным commit и сам ввёл production-root binding; TreeView закреплён на live `main`, как в production), genesis, refs, серверную историю всех registry refs (activity API), повторный `smoke-evaluate` (без `main_head_sha`), семантики A–F, каждый smoke/write-surface attempt — dispatch нужного workflow на `main`, стартовавший после последнего изменения ruleset, и `write-surface.json` байт в байт из artifact своего run (zip digest от GitHub; после истечения artifact через 30 дней — fail closed); `bypass_actors` виден только admin, поэтому пустой bypass доказывает admin-собранный [rulesets.json](activation/rulesets.json).

## 8. Ограничения и что дальше

- Smoke registry и smoke runs не трогать: новый dispatch добавит постоянную entry без сценария, rerun любого smoke run — unbound attempt; оба ломают `verify-smoke` (fail closed).
- Изменение `oracle-pilot.yml` до активации требует нового infra record (`workflow_sha256`).
- **SIGTERM race в `oracle_run.py` — была blocker перед п. 12 и первым natural measurement, исправлена отдельным reviewed PR (BUG_FIX).** Найдена в CI PR #33. Если SIGTERM приходит во время записи строки, сигнал доставляется при снятии маски уже после fsync, но до возврата `Rows.write()`. Тогда `done` не увеличивается, и `except` пишет `not_run` для уже записанной задачи: получается дубликат и `INVALID DUPLICATE_PAIR` вместо контрактного `INCOMPLETE`. Механизм воспроизведён детерминированно. Ложного PASS дефект не даёт, но обычный cancel или infra-SIGTERM превращает инфраструктурный abort в зарегистрированный INVALID attempt. Это implementation bug против frozen v1 semantics (abort → `not_run` только для незаписанных задач), а не изменение semantics.
  **Исправлено отдельным PR после merge #33 (`BUG_FIX`, §7.1 v2).** `Rows` считает durable строки внутри того же замаскированного окна, что и сама запись. При abort `done` берётся из суммы этих счётчиков, а не из счётчика цикла. Это закрывает и второе окно: abort между возвратом `write()` и `done += 1`. Contract, freeze, schemas, accounting и failure semantics не менялись. Детерминированный regression на оба sink (`test_oracle_runner.Runner.test_sigterm_while_a_pair_row_becomes_durable_is_counted_once` — SIGTERM изнутри fsync 3-й строки pairs; `…_standalone_row_…` — изнутри fsync 2-й строки standalone, когда все pairs уже durable). До исправления оба падают (дубликат: 15 pair-строк вместо 14, 12 standalone вместо 11), после — проходят: каждая задача ровно один раз в каждом sink, durable строки сохранены, итог `INCOMPLETE` без `invalid_reasons`.
  Новый code manifest: `oracle_code_sha256` = `0a8b5af5982ab14c87cc2e3ac45a0ce273c16afcfe02d209a487235833a70df8` (было `b5ca0c6b…3505`, это значение во frozen vectors — синтетические данные, с живым кодом они не сверяются). Production `registry-v3` пока только genesis, поэтому первая production entry откроет серию с новой identity без transition. Activation-bound bytes не затронуты: `oracle-pilot.yml` (`workflow_sha256`), smoke и write-surface workflows, infra record. Smoke entries несут identity своего источника `13c7d74`, их классификация от кода runner не зависит. Infra evidence пересобирать не нужно, `recheck` PASS.
- Дальше — только по решению maintainer: merge этого infra PR (п. 11), maintainer decision на issue #27 с `infra_sha256` (п. 12), отдельный enable PR (`activation-v3.json`, `ACTIVATION_RECORD`). Natural pilot, production oracle и DELSK-004 — не начаты.
- П. 11 (решение maintainer 2026-10-05): в проекте один разработчик, поэтому approve другого пользователя не требуется. Enable record (`delsk.oracle.v3-activation.v2`) называет infra PR полем `infra_pr` (`pull_request`, `merge_commit_sha`) без `review_id`. Проверка провенанса остаётся: PR смержен в `main` ровно этим commit и сам ввёл ровно эти bytes `infra.json`.

## 9. П. 11–12 и enable

- **BUG_FIX перед п. 12.** PR #34 (SIGTERM atomicity в `oracle_run.py`) смержен как `c1cd959da88eebf10a9442a7f66dfe79dacee4d0`. KAT зелёный на этом commit: push `oracle-smoke.yml` run 37360154348, attempt 1; `kat_actions_green` и `kat_verified_v2` (pinned main = `c1cd959`) — true. Новая `oracle_code_sha256` = `0a8b5af5982ab14c87cc2e3ac45a0ce273c16afcfe02d209a487235833a70df8`.
- **П. 11.** Infra PR #33 смержен как `3e69105b57ebe47ef520bc758fb54093d2db14c5` и сам ввёл `infra.json` с SHA-256 `8c70fd27…ddaf` (`_verify_review` live PASS).
- **П. 12.** Комментарий `6008353196` на issue #27, автор MEMBER, создан 2026-10-06T02:52:30Z — позже merge PR #33. Не редактировался (`created_at` = `updated_at`). Содержит фразу `DELSK-003A NATURAL MEASUREMENT AUTHORIZED infra_sha256=8c70fd27d3013c4016bda62ae1e815ace129147014ab05e93e6e6f94693fddaf`. Сервер дописал к телу footer; verifier проверяет вхождение фразы и SHA-256 точных bytes тела: `ab11ff7107711882fc07ad5f1a5e15c8c6e6a938aa3e7608bfafd2c1da4815bb`.
- **Enable record** [activation-v3.json](activation-v3.json) (`delsk.oracle.v3-activation.v2`): infra record, `infra_pr` = #33 / `3e69105`, decision. `oracle_g1_v2.ACTIVATION_RECORD` = SHA-256 его bytes = `d374fa1ea9a11ab8317273bbcbb392eb5e0960b8586a5618419c0fa41fc82020`. `validate_activation` (п. 6, 11, 12 live) — `[]`, `activation_in_tree` принимает record. CI `oracle-activation-evidence.yml` перепроверяет это live на каждом изменении.
- Production перепроверяет п. 6, 11 и 12 live при каждой оценке. Отредактированный комментарий, не смерженный PR или другой merge commit снова делают v3 неактивным (fail closed).

**Замена C0 guard (отдельный reviewed change после enable).** `oracle_pilot.require_dispatch_history` (C0, всегда `DISPATCH_HISTORY_UNVERIFIED`) заменён v3 admission. Contract-v3 §5: до выполнения всех пунктов pilot отказывает; теперь все пункты выполнены, и natural run допускается только пока v3 активен.

- **До `bind` и `B`**, step `initialize` (`verify_v3_activation`, live): v3 активен на текущем `main` ровно так, как его проверяет production G1 (`oracle_registry_git.active_activation`: enable record по `ACTIVATION_RECORD`, п. 6, 11, 12 live, проверенный registry root); bytes исполняемого `oracle-pilot.yml` в дереве `GITHUB_SHA` имеют `workflow_sha256` infra record (§1.5); source лежит на этом `main`. Отказ (`V3_NOT_ACTIVE`, в том числе при любой недоступности фактов) останавливает job до `bind`: entry останется PRE, серия не портится. Результат — admission `delsk.oracle.v3-pilot-admission.v1` в `$RUNNER_TEMP/v3-activation.json`, вне экспортируемого конверта.
- **После `B`**, worker и runner gate (`require_v3_active`, offline): admission этого же run key и source, для `ACTIVATION_RECORD` этого кода, witness пересчитан из Git. Без сети, поэтому сбой GitHub API после `B` не превращает проверенный attempt в отказ.
- `oracle-pilot.yml` не менялся (`workflow_sha256` и активация в силе). Code manifest (`oracle_code_sha256`) не меняется: `oracle_pilot.py` в него не входит. v1 G1 path остаётся `NOT_PASSED DISPATCH_HISTORY_UNVERIFIED` навсегда.
- Остаточный риск: если активация перестанет проверяться между `initialize` и `B` (окно — секунды), attempt всё равно продолжится по admission. Production G1 при оценке проверит активацию live заново (fail closed).

Первый natural pilot — только по отдельному разрешению maintainer.

## 10. Первый natural pilot и STOP

- **Dispatch 1** ([run 37419440408](https://github.com/definitely-stable/Shift-lab/actions/runs/37419440408), 2026-10-06T05:37:15Z): `source_sha` введён как `7ff8882e…` (commit #22), а не head `main` `6c9de2d`. `register` отказал (`REFUSED DISPATCH_REJECTED`, `source_sha` ≠ `GITHUB_SHA`) до записи; `measure` skipped, `B` не пересечена. Registry не изменился. Run без entry в population не входит (§8.5 считает unbound attempts только зарегистрированных runs).
- **Dispatch 2** ([run 37419673183](https://github.com/definitely-stable/Shift-lab/actions/runs/37419673183), attempt 1, source `6c9de2db832ded84161fc48e0a97d21006ae1539`): production entry 1 (`8343a55`, `entry_sha256 = 8852bc986fad71ed51ea27095b6517711fdab586b11e9af1a9b3226a7d95593d`, phase `pilot`, measurement identity `13d0d5f4…251b`, science identity `92be9c16…cdda`, без transition). `bind` до `B` (`binding_sha256 = 359d541e…03e6`). Run `success`: `COMPLETE`, conformance PASS, 1961/1961 пар `ok`, 0 codec error / timeout / resource limit / missing, `invalid_reasons` пусто; сплит `evaluation` sealed. Артефакты (zip digest GitHub = SHA-256 скачанного zip): pilot `5d663d92…72a1`, binding `3417e40c…804d`, attempt-start `d2a79869…c0c5`, dispatch `04713a47…cfb9`; истекают 2026-11-05.
- **G1 live** (`main` = `6c9de2d`): `NOT_PASSED REPEAT_MISSING RESULT_MISSING`; entry 1 — `MISSING` без violations (evidence root §8.1 ещё пуст). С evidence этой ветки в дереве (evaluator `6c9de2d`): entry 1 — `BUNDLE`, `COMPLETE`, conformance true, единственный blocker `REPEAT_MISSING` (нужен второй verified `COMPLETE` run с другим run ID).
- **STOP (fail closed): противоречие во frozen v3.** Frozen [test_oracle_contract_v3.py](../tests/test_oracle_contract_v3.py) (`Freeze.test_no_v3_evidence_or_registry_exists`, строки 411–412) требует отсутствия `.work/results/DELSK-003-ORACLE-V3/` и `.work/oracle/series-transition.json`. Это pre-activation проверка состояния, но §8.1 требует хранить в этом root каждый bundle и binding, а D3 — transition record. Тест входит в KAT step `oracle-smoke.yml`, а G1 требует зелёный KAT на measured source и на commit evaluator (`oracle_g1_v2.py`, `KAT_NOT_VERIFIED`). Поэтому любой commit `main` с v3 evidence или transition record получает красный KAT, и v3 не может штатно дойти до PASS. Менять frozen bytes нельзя; отключать тест — тоже. То же делает frozen тест measurement layer v1 [test_oracle_contract.py](../tests/test_oracle_contract.py) (`Freeze.test_no_natural_oracle_evidence_exists`): в `.work/results/` не должно быть ни одного каталога с префиксом `DELSK-003`, а v3 results root `DELSK-003-ORACLE-V3` под него попадает. Полный прогон с evidence в дереве: 736 tests, ровно эти 2 failures. Нужен новый versioned contract. Рекомендация: v4 = v3 по hash, отличия — results root вне префикса `DELSK-003` (тогда v1 тест не задет) и собственный conformance test без проверки отсутствия root; новый freeze, genesis и activation. Либо иное решение maintainer.
- Эта ветка хранит evidence run 37419673183 байт в байт и демонстрирует противоречие (CI на ней красный по этой причине). Она не мержится до решения maintainer. Второй pilot не запускался.
