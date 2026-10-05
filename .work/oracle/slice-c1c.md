# DELSK-003A C1-C: contract v3 и реализация (исправление PRE на реальном GitHub)

| Элемент | Статус |
|---|---|
| `delsk.oracle-contract.v1` / `v2` | **FROZEN**, bytes не менялись |
| `delsk.oracle-contract.v3` ([contract-v3.md](contract-v3.md), [freeze-v3.json](freeze-v3.json)) | **FROZEN on merge** (adoption — merge этого PR) |
| v2 | **SUPERSEDED, никогда не был active**: реализация заменена v3, refs v2 сохранены и раскрыты ([журнал](activation-c1b-log.md)) |
| Реализация v3 (C1-A движок + C1-B tooling) | **IMPLEMENTED / SYNTHETIC + LOCAL-GIT CONFORMANCE**, R01–R25 байт в байт, PM01–PM20 убиты |
| Activation v3 (§5 contract-v3) | **NOT_DONE**: шаги maintainer ниже |
| v3 production | **V3 NOT_ACTIVE** (`ACTIVATION_RECORD = None`: production G1 без чтений, production `register` отказывает) |
| Natural oracle / G1 | **NOT_RUN** / **NOT_RUN** |

Ни один natural byte не читался. Registry v3 не создан, rulesets для v3 не настроены, workflows v3 не запускались.

## Почему

Реальная activation-процедура v2 остановилась на smoke. GitHub Actions исполняет `Post <checkout>` и `Complete job` после step `boundary`, а frozen §8.3 п. 4 v2 требовал, чтобы после `boundary` не стартовал ни один step. Поэтому PRE был недоказуем для любого execution со стартовавшим `measure`. Подробности, run IDs и проверка — в [activation-c1b-log.md](activation-c1b-log.md). Ложного `PASS` дефект не давал, но делал activation невыполнимой.

## Что изменилось

| Файл | Изменение |
|---|---|
| [contract-v3.md](contract-v3.md) | delta-контракт: текст v2 по exact hash + подстановки (§0.2: `g1_contract` v3, `refs/heads/delsk/registry-v3`, results root `…-V3/`, observation tag v2, `V3_NOT_ACTIVE`); новый §8.3: роль `provider` для закрытого набора (`Complete job`, `Post <name>` steps до `boundary`, чей pinned action имеет `runs.post` — сейчас только checkout), PRE исключает только эти steps; `measure` `cancelled` без steps и с `runner_id = runner_name = null` не стартовал; §1.5: класс PRE/BUNDLE только для entries, чей source исполнял ровно активированные bytes `oracle-pilot.yml` (`workflow_sha256`), иначе MISSING; дополнение witness §4.1; activation §16 → §5 |
| [schemas-v3.json](schemas-v3.json), [registry-vectors-v3.json](registry-vectors-v3.json) | `D(schemas-v2)` и `T(registry-vectors) + R25 + PM13–PM20`; D/T/R25 нормативно определены и проверяются байт в байт в [test_oracle_contract_v3.py](../tests/test_oracle_contract_v3.py); тест доказывает, что T сохраняет все исходы v2 (эталонные предикаты PRE v2/v3 совпадают на каждой observation R01–R24) |
| [oracle_registry_v2.py](../tools/oracle_registry_v2.py), [oracle_g1_v2.py](../tools/oracle_g1_v2.py) | константы поколения v3 (имена модулей сохраняют суффикс `_v2` модели registered attempts); `pre_proven` по contract-v3 §1.3; KAT gate требует неизменные bytes v1, v2 и v3 freeze |
| [oracle_activation_v2.py](../tools/oracle_activation_v2.py) | имена steps `(contract v3 …)`, именованный checkout `Read-only source checkout`; reviewed карта post hooks (`checkout` — да, `upload-artifact` — нет) и закрытые наборы provider steps pilot/smoke; witness: все steps `measure` с явными уникальными именами, до `boundary` только pinned checkout/upload-artifact, зарезервированные имена запрещены, набор provider steps выводится из workflow; infra record фиксирует набор и `workflow_sha256` reviewed `oracle-pilot.yml`; retired refs v2 обязаны оставаться под ruleset; верификатор `cancel-before-register` принимает реальный отменённый `measure` без steps и без runner |
| [oracle_registry_git.py](../tools/oracle_registry_git.py) | freeze-v3, роли provider steps из activation record, smoke — свой набор ролей; `workflow_witnessed` — commits entries, чей workflow file (Git-объект pinned snapshot) имеет ровно digest activation record (smoke — smoke workflow pinned `main`) |
| workflows | имена steps v3, именованный checkout в `measure`; KAT step запускает `test_oracle_contract_v3` |
| тесты | fake providers в форме реального GitHub (`Set up job`, `Post <checkout>`, `Complete job`, переиспользованный `register` при failed-job rerun, `measure` без steps при cancel); [fixture](../tests/fixtures/github-actions-smoke-2026-10-05.json) с записанными ответами реальных runs 2026-10-05 проходит через настоящий транспорт, нормализацию, PRE и smoke-верификатор |

Genesis v3 (детерминированный, `GENESIS_DATE = 2026-10-05T00:00:00Z`, автор `delsk-registry`), закреплён в коде и тестах:

| Registry | ref | `genesis_sha256` | root commit |
|---|---|---|---|
| production | `refs/heads/delsk/registry-v3` | `e60e5bbce3a7e0b411bc36c937df04f098f07428d5e9e23fd66d10b61a06ac03` | `1a93f4ce71d9e4fbf5f21eaa9e66c660672ee258` |
| smoke | `refs/heads/delsk/registry-v3-smoke` | `c746e25a69febbfe3e38d0548c2a01952c94c56b68e156a839967039c3214f9a` | `62f79c1ceeb4f61615039104532e8dee251efaa3` |

SHA-256 `freeze-v3.json` = `39dede91e9ed6e12d298f5bd72f9d94fda9e0ac5c92f7a478815d210a0eb1c85` (`reg.G1_FREEZE_SHA256`).

## Activation v3: шаги maintainer (по порядку, после review/merge этого PR)

Выполнение шагов 1–4 и infra record (п. 6–10) — [activation-v3-log.md](activation-v3-log.md); v3 по-прежнему NOT_ACTIVE.

Процедура та же, что в [slice-c1b.md](slice-c1b.md), на refs v3:

1. **Rulesets (п. 7).** В ruleset `DELSK registry append-only` (id 24498603) **добавить** targets `delsk/registry-v3` и `delsk/registry-v3-smoke`. В UI вводить без `refs/heads/`, только ASCII. Существующие `delsk/registry` и `delsk/registry-smoke` не удалять: retired refs v2 обязаны оставаться под защитой. Ruleset `main` — без изменений. Evidence собирать `GET /rulesets/{id}` и `GET /rules/branches/{branch}` для `main`, `delsk/registry-v3`, `delsk/registry-v3-smoke`, `delsk/registry`, `delsk/registry-smoke`, затем `oracle_activation_v2.py verify-rulesets`.
2. **Genesis v3.** `oracle_registry_git.py genesis production DIR` и `genesis smoke DIR` на merged `main`; root commits обязаны совпасть с таблицей выше; push `<root>:refs/heads/delsk/registry-v3` и `<root>:refs/heads/delsk/registry-v3-smoke` без force.
3. **Smoke (п. 8–9)** на merged `main`, `oracle-registry-smoke.yml`: `stop-before-boundary` (run A) → «Re-run all jobs» A → «Re-run failed jobs» A; `cross-boundary`; `cancel-before-register` (cancel во время hold в `register`); `cancel-after-register` (cancel во время hold в `measure`); ещё один `stop-before-boundary` и удаление этого run. Каждый dispatch — только после завершения предыдущего: concurrency group вытесняет pending run. Затем manifest, `smoke-evaluate`, `verify-smoke`. Лишние dispatch'и дают постоянные лишние entries в smoke registry.
4. **Write surface (п. 10)**: dispatch `oracle-registry-write-surface.yml` (проба идёт на `refs/heads/delsk/registry-v3`).
5. **Infra PR, review, decision, enable PR (п. 6, 11, 12)** — как в slice-c1b.md, шаги 5–8: схемы `delsk.oracle.v3-activation-infra.v1` / `delsk.oracle.v3-activation.v1`, файл `.work/oracle/activation-v3.json`. `genesis_review` — этот PR: он вводит production root v3 в `oracle_activation_v2.py`.
6. Замена C0 guard `DISPATCH_HISTORY_UNVERIFIED` — отдельный reviewed change после activation.

## Проверка

- `python3 -m unittest discover -s .work/tests` (Python 3.12, как в CI) — 716 тестов, OK;
- `oracle_activation_v2.py check-workflows` — PASS; `validate.py` — PASS;
- R01–R25: 63 cases / 72 records воспроизведены байт в байт; PM14 (правило v2) убивают ровно R25.a, R25.d, R25.g — реальные формы, на которых v2 был недоказуем; PM18–PM20 (runner, привязка к workflow для PRE и для BUNDLE) — R25.j, R25.k, R25.l.

## Review PR #32 (head `c510115`)

| Замечание | Исправление |
|---|---|
| `cancelled + steps = []` не доказывает «runner не назначен» | observation несёт `runner_assigned` (`false` только при явных `runner_id = runner_name = null`); правило требует его; R25.j, PM18 |
| набор provider steps шире реальных post hooks (у `upload-artifact@043fb46…` нет `runs.post`) | `Post <name>` только для actions с post hook по reviewed карте (сейчас checkout); наборы pilot/smoke = `{Complete job, Post Read-only source checkout}`; тест, что `Post <upload>` не provider |
| static witness не привязан к точному исполненному `oracle-pilot.yml` | §1.5: activation record фиксирует `workflow_sha256`; класс PRE/BUNDLE (и PRE-доказательство rerun §8.5) только для witnessed source, иначе MISSING; R25.k, R25.l, PM19, PM20 |
| журнал: `3 entries` | `4 entries` |
| (head `5c40605`) нормативные метаданные говорили `PM13–PM17` / `PM01-PM17` (описание векторов, scope freeze, docstring, §4 контракта, slice, `oracle-smoke.yml`) | всё приведено к `PM01–PM20`; новый тест сверяет каждое такое утверждение с фактическим списком мутантов |
