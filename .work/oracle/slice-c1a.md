# DELSK-003A C1-A: registry / G1 v2 engine, synthetic conformance

| Элемент | Статус |
|---|---|
| `delsk.oracle-contract.v1` (measurement layer) | **FROZEN**, bytes не менялись |
| `delsk.oracle-contract.v2` (provenance/G1 layer) | **PROTOCOL V2 FROZEN**, bytes не менялись |
| C1-A | **IMPLEMENTED / SYNTHETIC CONFORMANCE** |
| v2 production | **V2 NOT_ACTIVE** (`g1_production` → `NOT_PASSED V2_NOT_ACTIVE`, без чтений) |
| Registry, genesis, rulesets | **NOT_ACTIVATED** (не созданы, не настроены) |
| Natural oracle | **NOT_RUN** |
| G1 | **NOT_RUN** |

Независимая реализация frozen [contract v2](contract-v2.md) ([freeze](freeze-v2.json)) без изменения протокола и vectors. Ни один natural byte не читался; `oracle-pilot.yml` не менялся и остаётся закрыт `DISPATCH_HISTORY_UNVERIFIED` ([Slice C0](slice-c.md)). Activation (contract §16 п. 6–12) — C1-B.

## Цепочка зависимостей

```text
v1 bundle verification (oracle_eval.verify / attempt_record)      bundle_projection
        ↓
v2 registry authority (validate 5.6 п.1–2, head, witness, stale)  oracle_registry_v2
        ↓
PRE / BUNDLE / MISSING + violations, unbound attempts (8.3–8.5)   oracle_g1_v2.classify / unbound_attempts
        ↓
series state machine (7.3) и series codes (7.4)                   series_machine / series_codes
        ↓
v1 G1 semantics (oracle_eval.g1, v1 §7 дословно)                  _g1_core
        ↓
v2 codes и gates: KAT на evaluator и measured commits (9.1 п.10)  _g1_core
        ↓
SCIENTIFIC_PASS (9.3) → test record TEST_ONLY_PASS (9.6)          g1_test
        ↓
production authority + KAT + activation → PASS                     _production_record (до activation — V2_NOT_ACTIVE)
```

## Код

| Файл | Contract | Содержание |
|---|---|---|
| [oracle_registry_v2.py](../tools/oracle_registry_v2.py) | §3, §5, §6, §7.1, §13 | authority constants §5.1; canonical parse genesis/`entries.jsonl`; closed schemas `schemas-v2.json`; `validate` (§5.6 п. 1: chain, sequence, `entry_sha256`, workflow/source, ancestry к pinned main, `git_source`, `science_identity`, phase, transition digest); `duplicate_keys`; `head`/`history`/`on_history` (level-1 witness); `stale`; физическая форма ветки §5.2; `make_entry`/`make_genesis`/`make_transition`; external checkpoint §13.2; неизменяемый `GitSnapshot` одного `main_head_sha` |
| [oracle_g1_v2.py](../tools/oracle_g1_v2.py) | §4, §7.2–§11 | `Evaluation`/`Evidence` (всё, что читает одна оценка, зафиксировано один раз); `analyze` (§5.6 п. 1–6 в фиксированном порядке, классификация всех entries, unbound attempts, series machine); `_g1_core` (§9.1 шаги 0–10, никогда не `PASS`); `g1_test`; `g1_production(measurement_identity_sha256)`; `_production_record`; `bundle_projection`, `read_evidence_root` (§8.1); `provider_observation` (§8.3); `kat_verified_v2` (§9.1 п. 10); `register_check`/`bind_check` (§5.7–§5.8, чистые решения без записи) |
| [oracle_attempts.py](../tools/oracle_attempts.py) | — | Actions-часть KAT вынесена в `kat_actions_green` (общая для v1 и v2); поведение v1 `kat_verified` прежнее |

Оба новых модуля вне v1 code manifest (`oracle_eval.CODE_FILES`), поэтому не меняют ни одну `science_identity` (§6). Production модуль не импортирует tests; fake providers и адаптер vectors живут только в `.work/tests`.

## Тесты

| Файл | Что проверяет |
|---|---|
| [test_oracle_v2_frozen.py](../tests/test_oracle_v2_frozen.py) | первый gate: явные SHA-256 frozen v1/v2 files, codec lock, schemas, KAT, corpus/candidate/source/protocol/seal locks; freeze records пинят ровно эти bytes; v2 код вне code manifest; нет registry/genesis/transition/v2 evidence; C0 guard `DISPATCH_HISTORY_UNVERIFIED` |
| [test_oracle_registry_v2.py](../tests/test_oracle_registry_v2.py) | canonical parser (BOM, float, exponent, NaN, duplicate key, non-canonical, blank line), fail-closed validation с проверкой причины (unknown field, bool-as-int, uppercase hash, short SHA, gap/repeat/zero sequence, previous hash, digest, workflow/source/identity/science/phase, transition digest), duplicates, witness/rollback/stale, физическая форма, SI01–SI05, XC01–XC05 и поддельные checkpoints |
| [test_oracle_g1_v2.py](../tests/test_oracle_g1_v2.py) | R01–R24: 51 case, 60 records — core verdict и полный record (attempts, unbound, series, transitions, `main_head_sha`, `registry_head`, `record_sha256`) байт в байт; R12/R21 runner; R17 и `V2_NOT_ACTIVE`; PRE/BUNDLE/MISSING; unbound; series machine; adversarial self-review; монотонность удаления; register/bind; KAT v2; evidence root; bundle projection |
| [test_oracle_v2_mutants.py](../tests/test_oracle_v2_mutants.py) | PM01–PM12: 28 source-мутантов (каждый — одно точное изменение одного правила), каждый убит vectors из frozen `killed_by` |

Vectors подаются ядру только как входы (registry, provider, evidence, environment); expected records используются лишь для сравнения. Генератор vectors не коммитился и не используется.

## Чтения контракта, зафиксированные реализацией

Не меняют frozen semantics и не влияют ни на один frozen vector; перечислены для review.

- Transition с `previous = new` — malformed record (§7.1 «различны») ⇒ `REGISTRY_INVALID`.
- Observation, не полученная для ключа, равна неполученному доказательству: не PRE, не BUNDLE. Два разных observation или PR record для одного ключа — неоднозначность: ключ отбрасывается, ни один не выбирается.
- `latest_run_attempt` run — максимум по всем observations этого `run_id`; PRE для unbound attempt требует run binding против каждой entry этого `run_id`. `unbound_attempts` в record — все unbound attempts registry (disclosure, как `attempts`).
- `REGISTRY_ROLLBACK` проверяет sidecars с well-formed `observed_head`; прочие отказывают на `EVIDENCE_ROOT_INVALID`.
- `checkpoint_sha256` — собственный digest провайдера checkpoint (технология не зафиксирована, D5); проверяется синтаксис, допустимость — по §13.2.
- `register` с нерезолвимой identity отказывает `DISPATCH_REJECTED`.

## Наблюдения для review (не blockers, контракт не меняется)

- Удаление provider run у retained INVALID bundle переводит entry в `MISSING`: verdict `INVALID` → `NOT_PASSED` (§8.4, таблица классов). Монотонность §9.4 определена относительно PASS и выполняется: тест удаляет каждый provider/bundle/sidecar каждого case и ни разу не получает pass.
- Остаточное окно level 1 (§13.1): усечение хвоста вместе со всеми его следами ядро не видит (тест фиксирует это явно); против non-admin его закрывает ruleset C1-B, а checkpoint, сделанный до усечения, перестаёт лежать на усечённой цепочке.

## Не сделано (C1-B и далее)

Remote reads production (pin `main` через константный remote, fetch registry ref, provider API, дерево `main_head_sha`), activation record (имена steps `bind`/`boundary`, KAT step), genesis, rulesets, real-GitHub synthetic registry smoke, rerun/cancel/delete сценарии, write-surface negative tests, изменения `oracle-pilot.yml`. Natural pilot — только отдельным решением после activation review.
