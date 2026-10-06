# DELSK-003A: журнал activation contract v4 (2026-10-06)

Основание: [contract-v4.md](contract-v4.md) §2, freeze PR [#38](https://github.com/definitely-stable/Shift-lab/pull/38) (merge `fca2c489034e292d050dbfc54f9ef6b59ac21f5e`), [issue #27](https://github.com/definitely-stable/Shift-lab/issues/27). Причина v4 — [activation-v3-log.md](activation-v3-log.md) §10–11. Журнал пояснительный, **не нормативный**; нормативны contract v4 и проверяемые файлы [activation-v4/](activation-v4/).

| §2 | Пункт | Статус | Evidence |
|---|---|---|---|
| 1 | freeze v4 смержен | **DONE**: PR #38 → `fca2c48` | `freeze-v4.json`, SHA-256 `9507f045…bb61` |
| 2 | tooling на константах v4, R01–R25 v4, PM01–PM20 | **DONE**: push CI на `fca2c48` зелёный, KAT (`oracle-smoke.yml`, run 37428879968) зелёный, `kat_actions_green = true` | — |
| 3 | ruleset покрывает `registry-v4` | **DONE**: ruleset 24498603 дополнен `refs/heads/delsk/registry-v4` и `registry-v4-smoke` (2026-10-06T07:24:58Z), rules `deletion` + `non_fast_forward`, bypass пуст; `main` — 24498754 без изменений; `verify-rulesets` PASS (admin read) | [rulesets.json](activation-v4/rulesets.json) |
| 4 | genesis v4 после ruleset | **DONE**: `refs/heads/delsk/registry-v4` = `c0b64888fb0c1db02724ad255c9ccc0fa1ed524d` (детерминированный root из PR #38), создан обычным push 2026-10-06T07:25:32Z — после изменения ruleset по часам GitHub; readback PASS | [genesis-readback.json](activation-v4/genesis-readback.json), [registry-refs.json](activation-v4/registry-refs.json), [registry-activity.json](activation-v4/registry-activity.json) |
| 5 | enable record + `ACTIVATION_RECORD` | этот PR: [activation-v4.json](activation-v4.json), SHA-256 `44cba89c2f853e91593b1239d86d7f3c5a90ed532754e7e82267a7d9ca84078e`; `verify-record` (genesis review PR #38 live) PASS | — |

Наследование от v3: smoke (7 сценариев) и write surface — по v3 infra record `8c70fd27…ddaf` (PR #33), без повторения. Refs v2/v3 retired и не двигались (`recheck` PASS).

После merge этого PR v4 **ACTIVE**: production `register` пишет в `registry-v4`, `initialize` пропускает pilot только при live-проверенной активации. Natural pilot — два dispatch `oracle-pilot.yml` на `main` с `source_sha` = head `main` (G1 требует два verified `COMPLETE` run с разными run ID), затем импорт bundles и bindings в `.work/results/ORACLE-G1-V4/` отдельным PR.

## Natural pilot (v4 ACTIVE)

Enable PR [#39](https://github.com/definitely-stable/Shift-lab/pull/39) смержен как `8d76774c23433a3a48e76c3fd61dbfcf1d57d99c`: `active_activation` на live `main` принимает record, `workflow_sha256` = bytes `oracle-pilot.yml` на `main`. KAT на `8d76774` зелёный (`kat_verified_v2 = true`).

| Entry | Run | Source | Итог | Bundle |
|---|---|---|---|---|
| 1 (`c48ab3a`) | [37434946174](https://github.com/definitely-stable/Shift-lab/actions/runs/37434946174), attempt 1 | `8d76774` | `success`: `COMPLETE`, conformance PASS, 1961/1961 пар `ok`, `invalid_reasons` пусто | `bundles/37434946174-1/` |
| 2 (`aa47f16`) | [37434993046](https://github.com/definitely-stable/Shift-lab/actions/runs/37434993046), attempt 1 | `8d76774` | `success`: `COMPLETE`, conformance PASS, 1961/1961 пар `ok`, `invalid_reasons` пусто | `bundles/37434993046-1/` |

Measurement identity обеих записей — `14c0a54eb916e10df92af7ab29a4ae2240449281c90ea72a49868cc3c7468314`, science identity `92be9c16…cdda`, без transition; сплит `evaluation` sealed (одинаковые sealed commitments). Bundles и binding sidecars — байт в байт из артефактов (zip digest = SHA-256 от GitHub, envelope checksums OK) в `.work/results/ORACLE-G1-V4/` (§8.1).

Production G1 на evidence этого PR (evaluator `8d76774`, evidence из дерева PR): **PASS**, blockers нет; обе entry `BUNDLE`, unbound attempts нет, серия pilot `CURRENT`. Окончательный record считается production-оценкой после merge (evaluator и pinned `main` с этим evidence).
