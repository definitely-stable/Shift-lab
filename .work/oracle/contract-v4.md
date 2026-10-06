# DELSK-003A: provenance/G1 contract `delsk.oracle-contract.v4`

Статус: **FROZEN с момента merge в `main`**. Идентичность принятых bytes — [freeze-v4.json](freeze-v4.json). Implementation: **NOT_ACTIVE**. Natural oracle под v4: **NOT_RUN**. G1: **NOT_RUN**.

**Verdict: `DELSK-003A PROTOCOL V4 FROZEN` / `V4 IMPLEMENTATION NOT_ACTIVE`.**

Основание: первый natural pilot под v3 ([run 37419673183](https://github.com/definitely-stable/Shift-lab/actions/runs/37419673183), PR [#37](https://github.com/definitely-stable/Shift-lab/pull/37), журнал [activation-v3-log.md](activation-v3-log.md) §10) показал, что frozen bytes v1 и v3 запрещают evidence root, который требует сам контракт (§0.1). Решения maintainer D1–D5 ([issue #27](https://github.com/definitely-stable/Shift-lab/issues/27)) не меняются. Журналы — пояснительные, **не нормативные**.

Ключевые слова: «обязан», «запрещено», «только» — нормативны. Вне нормативного текста — примечания.

## 0. Governance и layering

```text
measurement_contract   = delsk.oracle-contract.v1   (bytes по .work/oracle/freeze.json, без изменений)
g1_provenance_contract = delsk.oracle-contract.v4   (этот документ и freeze-v4.json)
base_text              = delsk.oracle-contract.v3   (contract-v3.md по exact hash через freeze-v3.json)
```

- **v4 = текст v3 с подстановками.** Нормативное содержание v4 — [contract-v3.md](contract-v3.md) (bytes закреплены [freeze-v3.json](freeze-v3.json), SHA-256 `39dede91e9ed6e12d298f5bd72f9d94fda9e0ac5c92f7a478815d210a0eb1c85`; v3 сам включает текст v2 по hash) с подстановками §0.2 и заменой §5 v3 (activation) на §2 этого документа. Где этот документ молчит, действует текст v3 после подстановок. Measurement layer v1 — по hash, SHA-256 `freeze.json` = `c56fc053b103cecd38446b3791db104a12b9fafabacdfc6b71f6f23c0bf7f729`.
- **Семантика не меняется.** Registry, классификация (PRE / BUNDLE / MISSING, §8.3 v3, witness §1.5 v3), population, series, transition, codes и record semantics — ровно v3. Меняются только идентификаторы, пути и activation.
- **v3 заменён.** v3 был active с 2026-10-06 (PR #35) до merge этого контракта; под ним выполнен один natural attempt: entry 1 в `refs/heads/delsk/registry-v3` (run 37419673183, `COMPLETE`, conformance PASS). Он раскрыт в журнале и остаётся под ruleset, но v4 его не читает и не оценивает: серия v4 начинается с нуля. Refs v2 и v3 удалять или переписывать запрещено.
- **Нет смешивания.** Каждый объект v4 несёт `g1_contract = "delsk.oracle-contract.v4"`; объект v3 по schemas-v4 невалиден (`REGISTRY_INVALID` / `EVIDENCE_ROOT_INVALID`).
- **Неизменяемость.** Этот контракт, [schemas-v4.json](schemas-v4.json), [registry-vectors-v4.json](registry-vectors-v4.json) и [test_oracle_contract_v4.py](../tests/test_oracle_contract_v4.py) неизменяемы после merge; bytes v1, v2 и v3 — тоже. Любое изменение семантики — только новый G1 contract.
- **Кто принимает.** Maintainer merge этого contract в `main` — акт adoption. Adoption не активирует v4 (§2).
- **Trust model** — D4 без изменений.

### 0.1 Почему нужен v4

§8.1 требует хранить каждый retained bundle и binding sidecar в results root на `main`, D3 — transition record в файле транзиции. Но frozen conformance tests, которые входят в KAT gate (§5.4 v3), утверждают состояние «до активации»:

- `test_oracle_contract.py` (v1, measurement layer): в `.work/results/` нет ни одного каталога с префиксом `DELSK-003`;
- `test_oracle_contract_v3.py` (v3): нет `.work/results/DELSK-003-ORACLE-V3/` и `.work/oracle/series-transition.json`;
- `test_oracle_contract_v2.py` (v2): нет `.work/results/DELSK-003-ORACLE-V2/` и того же файла транзиции.

G1 требует зелёный KAT на measured source и на commit evaluator. Поэтому под v3 любой commit `main` с evidence или transition record даёт `KAT_NOT_VERIFIED`, и v3 не может штатно дойти до `PASS`. Ложного `PASS` дефект не даёт. Frozen bytes не меняются, тесты не отключаются: v4 переносит пути за пределы этих проверок, а его собственный conformance test не утверждает ничего о состоянии рабочего дерева.

### 0.2 Подстановки в тексте v3

| В тексте v3 (и v2 через v3) | В v4 |
|---|---|
| `delsk.oracle-contract.v3` — идентификатор G1 contract во всех объектах, schemas, records, `g1_contract` | `delsk.oracle-contract.v4` |
| «v3 G1», «v3 production», «v3 registry», «v3 evidence root», «v3 freeze» | то же для v4 |
| `freeze-v3.json` как freeze **этого** контракта (`g1_freeze_sha256`, §9.0, §9.1 п. 10 v2) | `freeze-v4.json` |
| `schemas-v3.json`, `registry-vectors-v3.json`, `test_oracle_contract_v3.py` | `schemas-v4.json`, `registry-vectors-v4.json`, `test_oracle_contract_v4.py` |
| registry ref `refs/heads/delsk/registry-v3` | `refs/heads/delsk/registry-v4` |
| results root `.work/results/DELSK-003-ORACLE-V3/` | `.work/results/ORACLE-G1-V4/` |
| transition file `.work/oracle/series-transition.json` | `.work/oracle/series-transition-v4.json` |
| code `V3_NOT_ACTIVE` | `V4_NOT_ACTIVE` |

Прочие schema tags (`delsk.oracle.registry-genesis.v1`, `…registry-entry.v1`, `…series-transition.v1`, `…attempt-binding.v1`, `…g1-record.v1`, `…science-identity.v1`, `delsk.oracle.provider-observation.v2`) не меняются. Имена steps `(contract v3 register)`, `(contract v3 bind)`, `(contract v3 boundary)` — часть reviewed workflow, а не контракта: activation record фиксирует их как есть.

## 1. Vectors и mutants

`schemas-v4.json` = D4(`schemas-v3.json`): подстановки §0.2 к каждому string value, `$id = delsk.oracle.schemas.v4`, новая `description`. `registry-vectors-v4.json` = T4(`registry-vectors-v3.json`): подстановки §0.2 и перевычисление каждого корректного digest тем же правилом, что T в §4.2 v3 (некорректный digest копируется буквально), новая `description`. D4 и T4 нормативно определены в [test_oracle_contract_v4.py](../tests/test_oracle_contract_v4.py), который проверяет оба файла байт в байт.

**Сохранение исходов.** T4 — только переименование, поэтому каждый verdict, blocker (с точностью до `V4_NOT_ACTIVE`), класс, violation, unbound attempt и series state R01–R25 сохраняется (проверяется). Независимая реализация обязана воспроизвести R01–R25 v4 байт в байт (`record_sha256`); XC01–XC05 — по `expected`; SI01–SI05 не меняются. Mutants PM01–PM20 — те же, над R01–R25 v4.

## 2. Замена §5 v3: activation

v4 implementation становится active только после выполнения **всех**:

1. этот v4 freeze смержен;
2. registry tooling переключён на константы v4; R01–R25 v4 воспроизведены байт в байт, XC01–XC05 — по `expected`, PM01–PM20 убиты (KAT);
3. registry ruleset включает `refs/heads/delsk/registry-v4` (rules `deletion`, `non_fast_forward`, bypass пуст), ruleset `main` — как в v3; оба проверены read-only API, evidence закоммичен;
4. genesis v4 создан на `refs/heads/delsk/registry-v4` после того, как ruleset его покрывает; его root commit детерминирован и закреплён в reviewed коде, введённом PR этого freeze (genesis review);
5. enable record `.work/oracle/activation-v4.json` (`delsk.oracle.v4-activation.v1`) и константа кода `ACTIVATION_RECORD` = SHA-256 его bytes смержены в `main` одним PR; **merge этого PR maintainer — решение о natural measurement** (в проекте один разработчик; отдельный комментарий и approve второго пользователя не требуются).

Enable record фиксирует: имена steps `register`/`bind`/`boundary`, закрытый набор provider steps (§1.1, §2 v3), `workflow_sha256` (§1.5 v3) reviewed `oracle-pilot.yml`, имя KAT step, registry ref, genesis и root commit, genesis review (PR, merge commit), SHA-256 rulesets evidence, а также SHA-256 v3 infra record (`.work/oracle/activation/infra.json`, `8c70fd27d3013c4016bda62ae1e815ace129147014ab05e93e6e6f94693fddaf`).

**Smoke и write surface наследуются от v3.** v4 не меняет ни §8.3 v3, ни классификацию, ни механику register/bind/boundary, ни workflows. Synthetic real-GitHub smoke (7 сценариев) и write-surface negative tests v3 доказали поведение provider и registry на реальном GitHub; v4 ссылается на их evidence по hash v3 infra record и не повторяет их. Live при каждой оценке production проверяет: enable record по `ACTIVATION_RECORD`, genesis review, registry root, witness workflow (§1.5 v3). Любой сбой — v4 не активен (`V4_NOT_ACTIVE`, fail closed).

KAT (§5.4 v3 после подстановок) дополнительно требует неизменные bytes `freeze-v3.json` и его слоёв. До выполнения всех пунктов production pilot отказывает до `bind` (`V4_NOT_ACTIVE`), v4 production — не `PASS`. **`MISSING ⇒ NOT_PASSED`** — как в v3.

## 3. Не заморожено и ограничения

- Реализация, workflow, имена steps, genesis, rulesets — activation (§2).
- Наследование smoke от v3 опирается на неизменность workflows и классификации; любое изменение `oracle-pilot.yml` требует нового enable record (§1.5 v3).
- Entry 1 v3 не входит в серию v4; v4 не переоценивает и не переносит attempts v3.
- Ограничения §7 v3 и §18 v2 сохраняются.
