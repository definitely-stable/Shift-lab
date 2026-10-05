# DELSK-003A C1-B: activation infrastructure до границы реальных GitHub settings

| Элемент | Статус |
|---|---|
| `delsk.oracle-contract.v1` / `delsk.oracle-contract.v2` | **FROZEN**, bytes не менялись |
| C1-A | **IMPLEMENTED / SYNTHETIC CONFORMANCE** (R01–R24, XC01–XC05, PM01–PM12 — без изменений) |
| C1-B (код, workflows, верификаторы evidence) | **IMPLEMENTED / LOCAL-GIT CONFORMANCE** |
| Activation §16 п. 6–12 | **NOT_DONE** — требуют реальных repository settings и maintainer actions (ниже) |
| v2 production | **V2 NOT_ACTIVE** (`ACTIVATION_RECORD = None`: production G1 без чтений, production `register` отказывает) |
| Registry, genesis, rulesets | **NOT_ACTIVATED** (ветки `delsk/registry*` не созданы, rulesets не настроены) |
| Natural oracle / G1 | **NOT_RUN** / **NOT_RUN** |

Граница C1-B: всё, что можно реализовать и проверить без записи в реальный репозиторий и без изменения его настроек. Ни один workflow не запускался, ни одна ветка/ruleset не создавались, ни один natural byte не читался. `oracle_pilot` worker и runner по-прежнему отказывают `DISPATCH_HISTORY_UNVERIFIED` ([Slice C0](slice-c.md)).

## Что реализовано

| Файл | Contract | Содержание |
|---|---|---|
| [oracle_registry_git.py](../tools/oracle_registry_git.py) | §5.2, §5.7, §5.8, §8.1, §8.3, §9.0, §11 | Git-транспорт registry: чтение полной истории ветки в приватный bare repo (не-`100644` записи дерева и merge commits ⇒ `REGISTRY_INVALID`), детерминированный genesis root commit (без push), append ровно одной строки и push только `HEAD:<registry ref>` без force, ≤ 3 раундов при non-fast-forward, идемпотентный повтор, readback; `bind` → binding sidecar (`O_EXCL`); production-чтения: pin `main` с константного remote, registry, live provider observations всех attempts зарегистрированных run ID, PRs transitions, evidence root из дерева `main_head_sha` (не working tree), KAT, `freeze-v2` из того же дерева, повторное чтение `main` и registry; smoke-оценка |
| [oracle_activation_v2.py](../tools/oracle_activation_v2.py) | §4.1, §12, §16 | статический witness §4.1/§12.2 для workflows (точный список шагов до `boundary`, запрет codec/fetch/corpus до `boundary`, `bind` без `if`/`continue-on-error`, `boundary` требует успешный `bind`, все шаги после `boundary` не стартуют без него); верификаторы evidence п. 7 (rulesets), п. 8–9 (smoke-сценарии), п. 10 (write-surface); runner write-surface с read-only preflight; closed schema activation record `delsk.oracle.v2-activation.v1` и его проверка в pinned tree |
| [oracle_registry_v2.py](../tools/oracle_registry_v2.py) | §5.1, §5.3 | authority profiles: `PRODUCTION` = константы §5.1 и frozen schemas (деривация схемы на production-значениях воспроизводит frozen schemas байт в байт); `SMOKE` = `refs/heads/delsk/registry-smoke`, `oracle-registry-smoke.yml`, domain-separated `g1_freeze_sha256` — smoke и production registries никогда не валидируются друг как друг |
| [oracle_g1_v2.py](../tools/oracle_g1_v2.py) | §11 | profile протянут через `Evaluation`/`analyze`/`register_check`/`bind_check`; `g1_production(identity)` после activation сам читает всё через `production_inputs`; до activation — `NOT_PASSED V2_NOT_ACTIVE` без единого чтения (строки, на которые нацелены PM07, не менялись) |
| [oracle_attempts.py](../tools/oracle_attempts.py) | §5.5 | `git_identity` (полный объект identity v1 для `GitSnapshot`); `git_source` — прежняя семантика поверх него |
| [oracle-pilot.yml](../../.github/workflows/oracle-pilot.yml) | §4.1, §12.2 | jobs `register` (`contents: write` только у job, token только у шага register, checkout без credentials, полная история) и `measure` (`needs: register`, read-only, `bind` до `boundary`, binding sidecar artifact до `boundary`, admission без `continue-on-error`); шаг `boundary` — `Measurement boundary (contract v2 boundary)`; C0-шаги после него стартуют только если стартовал `boundary` — позитивная проверка `contains(fromJSON('["success","failure","cancelled"]'), steps.workload.outcome)`: у шага, который не вычислялся, outcome пуст, и `!= 'skipped'` ошибочно пропустил бы его (иначе PRE недоказуем) |
| [oracle-registry-smoke.yml](../../.github/workflows/oracle-registry-smoke.yml) | §16 п. 8–9 | тот же register/bind код на SMOKE profile; сценарии `stop-before-boundary`, `cross-boundary`, `cancel-before-register`, `cancel-after-register` (+ rerun/delete через UI/API); `boundary` — маркер, ничего natural |
| [oracle-registry-write-surface.yml](../../.github/workflows/oracle-registry-write-surface.yml) | §12.1, §16 п. 10 | workflow token с `contents: write`: push в `main`, non-fast-forward (forced) push и удаление `delsk/registry`; preflight effective rules, иначе записи не делаются; изменившийся ref останавливает пробу |

Step names, предлагаемые для activation record: `bind` = `Bind registry entry before the measurement boundary (contract v2 bind)`, `boundary` = `Measurement boundary (contract v2 boundary)`, KAT = `Oracle tests (contract, production KAT/G1, mutants, metamorphic, faults, pinned codecs)` (существующий шаг `oracle-smoke.yml`, теперь также запускает тесты C1-B).

Genesis (детерминированный, `GENESIS_DATE = 2026-10-05T00:00:00Z`, автор `delsk-registry`), закреплён в коде и тестах:

| Registry | ref | `genesis_sha256` | root commit |
|---|---|---|---|
| production | `refs/heads/delsk/registry` | `f3ce1f9e8b5f2a8cf373de1651920f58ef2a3ce064c8149fe220ba3568228484` | `6cf2c6a7c35cee005f894366c97fca00230a5670` |
| smoke | `refs/heads/delsk/registry-smoke` | `eca9394f3b40d157f3f5f78afc77d1951d02df34b1a5d6c673e3cec78be86fdb` | `a429d34d67959e49af8f79da024ce6eed34cbc13` |

## Тесты (offline, локальный Git)

| Файл | Что проверяет |
|---|---|
| [test_oracle_registry_git.py](../tests/test_oracle_registry_git.py) | константный remote перенаправлен на локальный bare repo только через тестовый `HOME` (`url.insteadOf`), код остаётся на константах; genesis детерминирован и равен закреплённым SHA; profiles не валидируют друг друга; append/readback/физическая форма; идемпотентность; гонка двух writers (refetch + retry); отклонённый сервером push — ровно 3 раунда, ничего не записано; отказы `SOURCE_NOT_ON_MAIN`/`DISPATCH_REJECTED`/`REGISTRY_INVALID`/`TRANSITION_REQUIRED` без записи; production `register` до activation — `DISPATCH_REJECTED` без единого чтения; production-путь со stand-in activation; bind (witness head, rerun failed jobs, чужая entry, `O_EXCL`); merge/исполняемый/symlink в истории registry; полная smoke-классификация через fake provider (PRE/MISSING, rerun-all, rerun-failed, cancel, delete) и `verify_smoke`; failed-job rerun, пересёкший `B`, ⇒ unbound ⇒ INVALID; `REGISTRY_STALE`/`main` меняются во время сбора; evidence root только из pinned tree |
| [test_oracle_activation_v2.py](../tests/test_oracle_activation_v2.py) | witness на реальных workflows проходит; 14 мутаций `oracle-pilot.yml` отклоняются по своей причине (boundary без bind, `always()`, fail-open bind, build/curl до boundary, post-boundary без guard, write token в measure, token в checkout, push trigger, unpinned action, переименование, порядок, shallow checkout); rulesets (пустой bypass registry, GitHub Actions в bypass `main`, evaluate, exclude, effective rules, org look-alike); write-surface против локального remote с server-side отказом (pre-receive), отсутствие rulesets ⇒ ни одной записи, принятая запись ⇒ проба остановлена и FAIL, client-side отказ не считается; полный synthetic activation record в temp tree проходит и связывается по digest, любой пробел ⇒ v2 не активен; в репозитории нет activation record, evidence, genesis |

Обновлены C1-A/C0 тесты, которые фиксировали отсутствие register job: [test_oracle_v2_frozen.py](../tests/test_oracle_v2_frozen.py) теперь требует, чтобы `oracle-pilot.yml` проходил witness, `contents: write` встречался ровно один раз и activation record отсутствовал; [test_oracle_pilot.py](../tests/test_oracle_pilot.py) — порядок bootstrap внутри job `measure` и новый boundary step.

## Граница: что требует реальных GitHub settings (maintainer, по порядку)

Каждый шаг — отдельное действие maintainer после review/merge этого PR. Ни один из них не выполнялся.

1. **Rulesets (п. 7).** Создать repository rulesets: registry — include `refs/heads/delsk/registry` и `refs/heads/delsk/registry-smoke`, rules `deletion` + `non_fast_forward`, bypass пуст, enforcement `active` (без `creation`/`update`: `register` дописывает fast-forward workflow token'ом); `main` — include `~DEFAULT_BRANCH`, `deletion` + `non_fast_forward` + `pull_request`, bypass без GitHub Actions (integration 15368). Rulesets до genesis, чтобы registry был защищён с первого байта. Evidence собирается admin-токеном (`bypass_actors` возвращается только с правом записи на ruleset): `GET /repos/{repo}/rulesets/{id}` для каждого ruleset и `GET /repos/{repo}/rules/branches/{branch}` для `main`, `delsk/registry`, `delsk/registry-smoke` → `.work/oracle/activation/rulesets.json` (`delsk.oracle.rulesets-evidence.v1`) → `oracle_activation_v2.py verify-rulesets`.
2. **Genesis (п. 6).** `oracle_registry_git.py genesis production DIR` и `genesis smoke DIR` локально; root commits обязаны совпасть с таблицей выше; затем push `<root>:refs/heads/delsk/registry` и `<root>:refs/heads/delsk/registry-smoke` в `https://github.com/definitely-stable/Shift-lab.git`. Это первая запись в реальный репозиторий.
3. **Smoke (п. 8–9)** на merged `main` (`source_sha` = head `main`): dispatch `oracle-registry-smoke.yml` — `stop-before-boundary` (run A), `cross-boundary`, `cancel-before-register` (cancel во время hold), `cancel-after-register` (cancel во время hold перед `boundary`); «Re-run all jobs» run A (`rerun-all`), затем «Re-run failed jobs» run A (`rerun-failed`: `bind` обязан отказать до `boundary`); ещё один `stop-before-boundary` и удаление этого run (`deleted-run`). Затем локально `oracle_registry_git.py smoke-evaluate smoke.json`, manifest `scenarios.json` (`delsk.oracle.registry-smoke-scenarios.v1`), `oracle_activation_v2.py verify-smoke`.
4. **Write surface (п. 10).** Dispatch `oracle-registry-write-surface.yml`; шаг завершается PASS только если все три записи отклонены сервером и refs не изменились; artifact `write-surface.json` → evidence.
5. **Activation PR (п. 11).** Evidence в `.work/oracle/activation/`, `activation-v2.json` (`oracle_activation_v2.py verify-record`), `ACTIVATION_RECORD` = SHA-256 его bytes, обновление not-activated тестов; independent review.
6. **Natural measurement (п. 12)** — отдельное maintainer decision; замена C0 guard `DISPATCH_HISTORY_UNVERIFIED` на v2-binding в `oracle_pilot` — отдельный reviewed change после activation, не часть C1-B.

## Чтения и решения реализации (для review)

- Production `register` до activation отказывает `DISPATCH_REJECTED` (ближайший закрытый runner-код §9.2) до любых чтений: production registry не получает entries до activation, smoke покрывает тот же код. Без этого dispatch после genesis мог бы открыть серию PRE-entries до решения п. 12.
- Ошибка записи/сети в `register` — infrastructure failure (job падает, `measure` не стартует), а не contract-код; повтор того же attempt идемпотентен (§5.7 п. 5).
- `evaluator_source_sha` = HEAD checkout только если все файлы evaluator совпадают с этим commit; иначе `None`, что никогда не проходит KAT gate.
- Live provider observation считается полученной только для 404 ⇒ `run = null`; любая другая ошибка API — infrastructure failure без verdict (оценку можно повторить).
- Witness §4.1 синтаксический: точный reviewed список шагов до `boundary` плюс denylist; он не заменяет review, а не даёт незаметно его обойти.
- `GET /rules/branches/{branch}` для `delsk/registry` вызывается с именем ветки как есть; если API не примет слэш, preflight закроется без записей — проверяется на шаге 4.
- Smoke/write-surface workflows вне budget admission (`budget.EXPERIMENTAL_WORKFLOWS`): ручные, ≤ 15 мин, без natural compute.
