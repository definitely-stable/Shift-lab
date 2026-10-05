# DELSK-003A C1-B: журнал реальной activation-процедуры (2026-10-05)

Основание: [slice-c1b.md](slice-c1b.md) (граница реальных GitHub settings), [contract-v2.md](contract-v2.md) §12, §16, `main` = `ba68ec73e1e2943005d372459742f063ea768e94` (merge PR #31), [issue #27](https://github.com/definitely-stable/Shift-lab/issues/27).

**Verdict: `ACTIVATION STOPPED` на шаге 3 (smoke, §16 п. 8–9). V2 NOT_ACTIVE (и никогда не активируется). Natural oracle / G1 — NOT_RUN.** Замороженный §8.3 п. 4 на реальных данных GitHub Actions не позволяет доказать PRE ни для одного execution, у которого стартовал job `measure` (ниже). Исправление меняет семантику классификации и по §0 возможно только новым G1 contract.

**Решение:** maintainer выбрал вариант 1 — G1 contract v3 ([contract-v3.md](contract-v3.md), реализация и процедура — [slice-c1c.md](slice-c1c.md)). v2 superseded до активации; этот журнал остаётся раскрытием v2-попытки.

| Шаг slice-c1b | §16 | Статус |
|---|---|---|
| 1. Rulesets | п. 7 | **DONE**, `verify-rulesets` → `PASS` |
| 2. Genesis | п. 6 (часть) | **DONE**: production и smoke root commits на remote |
| 3. Smoke | п. 8–9 | **STOPPED**: сценарии `stop-before-boundary`/`rerun-all`/`rerun-failed` не доказуемы по §8.3 |
| 4. Write surface | п. 10 | NOT_RUN |
| 5–8. Infra PR, review, decision, enable PR | п. 6, 11, 12 | NOT_DONE |

`ACTIVATION_RECORD = None`, `.work/oracle/activation/` отсутствует, production registry пуст.

## 1. Rulesets (п. 7)

| Ruleset | id | include | rules | bypass |
|---|---|---|---|---|
| DELSK registry append-only | 24498603 | `refs/heads/delsk/registry`, `refs/heads/delsk/registry-smoke` | `deletion`, `non_fast_forward` | пуст |
| DELSK main provenance protection | 24498754 | `~DEFAULT_BRANCH` | `deletion`, `non_fast_forward`, `pull_request` | пуст |

Effective rules (`GET /rules/branches/{branch}`): `main` — `deletion`, `non_fast_forward`, `pull_request`; `delsk/registry` и `delsk/registry-smoke` — `deletion`, `non_fast_forward`. Evidence `delsk.oracle.rulesets-evidence.v1` собран после последнего изменения ruleset (updated_at `2026-10-05T11:57:24Z`); `oracle_activation_v2.py verify-rulesets` → `PASS`.

До этого verifier дважды вернул `FAIL` по `refs/heads/delsk/registry` (effective rules `[]`): сначала include содержал кириллическую `к` (U+043A, bytes `D0 BA`) в `delsк`, затем — двойной префикс `refs/heads/refs/heads/delsk/registry`. Обе версии не защищали production registry; genesis до исправления не создавался.

## 2. Genesis

`oracle_registry_git.py genesis {production,smoke}` локально, затем push `<root>:<ref>` без force:

| Registry | ref | root commit | `genesis_sha256` |
|---|---|---|---|
| production | `refs/heads/delsk/registry` | `6cf2c6a7c35cee005f894366c97fca00230a5670` | `f3ce1f9e8b5f2a8cf373de1651920f58ef2a3ce064c8149fe220ba3568228484` |
| smoke | `refs/heads/delsk/registry-smoke` | `a429d34d67959e49af8f79da024ce6eed34cbc13` | `eca9394f3b40d157f3f5f78afc77d1951d02df34b1a5d6c673e3cec78be86fdb` |

Совпадают с закреплёнными в slice-c1b.md. Production `g1_freeze_sha256` = SHA-256 `freeze-v2.json` = `d8e3c33a…2a34b57`. Readback с remote: единственный commit без parents, дерево ровно `{genesis.json, entries.jsonl}` (`100644`, `entries.jsonl` 0 bytes); `registry_root()` возвращает закреплённый root для обоих profiles.

## 3. Smoke (п. 8–9): выполнено и остановлено

`oracle-registry-smoke.yml` на `main`, `source_sha = ba68ec7…`:

| Сценарий | run key | jobs / steps | smoke entry | `_scenario_facts` |
|---|---|---|---|---|
| `stop-before-boundary` | [37306997371](https://github.com/definitely-stable/Shift-lab/actions/runs/37306997371) / 1 | register ✓; measure ✗: bind ✓, sidecar ✓, stop ✗, boundary skipped | seq 1, класс **MISSING** | FAIL: должен быть PRE |
| `rerun-all` | 37306997371 / 2 | как attempt 1, register исполнен заново | seq 2, класс **MISSING** | FAIL: должен быть PRE |
| `rerun-failed` | 37306997371 / 3 | measure: bind ✗ (отказ), boundary skipped | нет | OK, но (A, 3) — **unbound attempt** |
| `cross-boundary` | [37307218114](https://github.com/definitely-stable/Shift-lab/actions/runs/37307218114) / 1 | bind ✓, boundary ✓ | seq 3, MISSING | OK |
| `cancel-before-register` | [37307308985](https://github.com/definitely-stable/Shift-lab/actions/runs/37307308985) / 1 | cancel во время hold; register не исполнялся | нет | FAIL: measure считается started |
| `cancel-after-register` | [37308739475](https://github.com/definitely-stable/Shift-lab/actions/runs/37308739475) / 1 | запущен после остановки, только чтобы записать реальную форму jobs для v3: cancel во время hold в `measure`, bind..boundary skipped, provider steps исполнены | seq 4, MISSING под v2 (PRE под v3) | не оценивался |
| `deleted-run` | — | не запускался | — | — |

Smoke registry head: `{sequence: 4, entry_sha256: 7b5648c5…0ce0659}`. Ответы GitHub API всех шести attempts записаны в [fixture](../tests/fixtures/github-actions-smoke-2026-10-05.json) и используются тестами v3. Smoke registry append-only и защищён ruleset: эти entries постоянны. На production registry не влияет: другой ref, domain-separated genesis.

### 3.1 Дефект: §8.3 п. 4 недоказуем на реальном provider

§8.3 п. 4: PRE требует, чтобы «job `measure` отсутствует, или `started = false`, или в нём ровно один step роли `boundary` и **каждый** step с `number ≥ boundary.number` имеет `started = false`». Нормализация §8.3: `started` ⇔ status `in_progress`/`completed` и conclusion ≠ `skipped`.

GitHub Actions добавляет в каждый стартовавший job служебные steps, которые исполняются всегда, в том числе после failed step, и нумеруются после всех steps workflow. Run 37306997371, attempt 1, job `measure`:

| # | step | status / conclusion | `started` |
|---|---|---|---|
| 7 | Measurement boundary (contract v2 boundary) | completed / skipped | false |
| 14 | Post Run actions/checkout@3d3c42e… | completed / success | **true** |
| 15 | Complete job | completed / success | **true** |

Поэтому `pre_proven` (реализация дословно следует §8.3) возвращает `False` для каждого execution со стартовавшим `measure`. Проверка на тех же observations: если убрать только steps 14–15, (A, 1) и (A, 2) становятся PRE, а (A, 3) перестаёт быть unbound; `cross-boundary` остаётся не PRE. `Complete job` есть в любом job, поэтому workflow-перестройкой (убрать `actions/checkout`, переставить steps) это не обойти.

Следствия под v2 как заморожено:

- любая остановка до `B` внутри `measure` (infra failure, отказ admission, синтетический stop) ⇒ entry `MISSING` ⇒ `NOT_PASSED`; в серии — carry-over §7.4;
- «Re-run failed jobs» после `register` ⇒ unbound attempt §8.5 ⇒ `INVALID UNBOUND_MEASUREMENT` для identity этого run, хотя `bind` отказал до `B`. Это противоречит §10.2 («не attempt, если `B` не пересечена»);
- PRE достижим только когда `measure` вообще не стартовал (отказ в `register`, но тогда нет entry).

Ложного PASS дефект не даёт: он делает G1 строже задуманного, то есть fail-closed. Но §16 п. 8–9 (сценарии stop-before-boundary, rerun-all, rerun-failed) с ним не выполнимы, и production G1 станет необратимо `NOT_PASSED`/`INVALID` при первой же infra-остановке. Поэтому активация остановлена до решения maintainer.

Почему не поймано тестами: fake providers C1-A/C1-B ([test_oracle_registry_git.py](../tests/test_oracle_registry_git.py), [test_oracle_activation_v2.py](../tests/test_oracle_activation_v2.py), R-vectors) моделируют только steps workflow, без служебных steps `Post Run …`/`Complete job`.

### 3.2 Второе расхождение (C1-B, не frozen)

`cancel-before-register`: GitHub возвращает job `measure` как `status = completed`, `conclusion = cancelled`, `steps = []`, `runner_name = null`. По нормализации §8.3 это `started = true`, а `_scenario_facts` требует `not _started(measure)`. На классификацию не влияет (entry нет), но verifier п. 9 этот сценарий на реальном GitHub не принимает.

## 4. Что требовалось (решение maintainer: вариант 1, выполнено в [slice-c1c.md](slice-c1c.md))

1. **G1 contract v3**, новый freeze (по §0 v2 bytes не меняются). Минимальная правка §8.3 п. 4: учитывать только steps, объявленные reviewed workflow (по именам из activation record), либо требовать, чтобы ни один step workflow после `boundary` не стартовал, а provider-служебные `Post …`/`Complete job` исключить по закрытому списку. Плюс vectors с реальной формой provider jobs. Новый contract — новый genesis и новые registry refs. Текущие `delsk/registry` (пуст) и `delsk/registry-smoke` (4 entries) остаются раскрытыми.
2. C1-B: `cancel-before-register` — принять `measure` с `steps = []` и `conclusion = cancelled` как не исполнявшийся, либо проверять это через отсутствие runner. Fake providers в тестах дополнить служебными steps.
3. После этого — повтор шагов 3–8 slice-c1b.md на новом contract.

Альтернатива без нового контракта — принять v2 как есть (PRE фактически недостижим) и смягчить verifier п. 8–9. Это не рекомендуется: activation evidence разошлось бы с нормой §10.2, а production серия терялась бы при первой infra-остановке.
