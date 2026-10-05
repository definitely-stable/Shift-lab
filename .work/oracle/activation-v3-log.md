# DELSK-003A: журнал реальной activation-процедуры contract v3 (2026-10-05)

Основание: [contract-v3.md](contract-v3.md) §5, процедура [slice-c1c.md](slice-c1c.md), `main` = `13c7d74ede7e2fd41bade001ec0e88926882459c` (merge PR [#32](https://github.com/definitely-stable/Shift-lab/pull/32)), [issue #27](https://github.com/definitely-stable/Shift-lab/issues/27). Журнал пояснительный, **не нормативный**; нормативны contract v3 и проверяемые файлы [activation/](activation/).

**Verdict: `V3 ACTIVATION INFRA EVIDENCE COLLECTED` / `V3 NOT_ACTIVE`.** Пункты §5 п. 6–10 выполнены на реальном GitHub, расхождений с frozen v3 не найдено. `ACTIVATION_RECORD = None`, `.work/oracle/activation-v3.json` (enable record) отсутствует. Natural oracle — **NOT_RUN**, G1 — **NOT_RUN**: ни одного run `oracle-pilot.yml`, ни одного natural byte.

| §5 | Пункт | Статус | Evidence |
|---|---|---|---|
| 1–5 | freeze, tooling, R01–R25, PM01–PM20, API separation | DONE в PR #32 (CI на `13c7d74`: 716 tests OK, 2 skipped; Oracle smoke 336 OK) | — |
| 6 | genesis v3 (reviewed PR #32 вводит root) | **DONE**: refs созданы обычным push, readback PASS, `verify_genesis_review` live PASS | [genesis-readback.json](activation/genesis-readback.json), [infra.json](activation/infra.json) |
| 7 | rulesets, проверенные read-only API | **DONE**: `verify-rulesets` PASS | [rulesets.json](activation/rulesets.json), [rulesets-pre-genesis.json](activation/rulesets-pre-genesis.json) |
| 8–9 | synthetic smoke, 7 сценариев, live observations | **DONE**: `verify-smoke` PASS | [smoke-scenarios.json](activation/smoke-scenarios.json), [smoke-evaluation.json](activation/smoke-evaluation.json), [smoke-semantics.json](activation/smoke-semantics.json) |
| 10 | write-surface на `refs/heads/delsk/registry-v3` | **DONE**: три операции отклонены сервером | [write-surface.json](activation/write-surface.json), [write-surface-supplementary.json](activation/write-surface-supplementary.json) |
| 11 | independent review | **NOT_DONE** (review этого infra PR) | — |
| 12 | maintainer decision | **NOT_DONE** | — |

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

[infra.json](activation/infra.json) (`delsk.oracle.v3-activation-infra.v1`, SHA-256 `8c70fd27d3013c4016bda62ae1e815ace129147014ab05e93e6e6f94693fddaf`): step names, закрытый набор provider steps, `workflow_sha256 = d01036fff8396b274e400fe9f02912473cd9997dab7b4a9f020a3bac346ea81d` (bytes `oracle-pilot.yml` в `13c7d74`), production genesis, `genesis_review` = PR #32 / `13c7d74`, evidence п. 7–10 по SHA-256. `verify-infra` PASS; тест `NotActivatedHere` проверяет его офлайн в каждом CI. Workflow [oracle-activation-evidence.yml](../../.github/workflows/oracle-activation-evidence.yml) перепроверяет всё read-only против live GitHub (`oracle_activation_evidence.py recheck`): rulesets и effective rules, genesis, refs, повторный `smoke-evaluate` (без `main_head_sha`), семантики A–F, каждый smoke/write-surface attempt — dispatch нужного workflow на `main`, стартовавший после последнего изменения ruleset, и `write-surface.json` байт в байт из artifact своего run (zip digest от GitHub; после истечения artifact через 30 дней — fail closed); `bypass_actors` виден только admin, поэтому пустой bypass доказывает admin-собранный [rulesets.json](activation/rulesets.json).

## 8. Ограничения и что дальше

- Smoke registry и smoke runs не трогать: новый dispatch добавит постоянную entry без сценария, rerun любого smoke run — unbound attempt; оба ломают `verify-smoke` (fail closed).
- Изменение `oracle-pilot.yml` до активации требует нового infra record (`workflow_sha256`).
- Дальше — только по решению людей: independent review этого infra PR (п. 11), maintainer decision на issue #27 с `infra_sha256` (п. 12), отдельный enable PR (`activation-v3.json`, `ACTIVATION_RECORD`). Natural pilot, production oracle и DELSK-004 — не начаты.
