# pilot-v1: acquisition locks (DELSK-002, Slice D)

Статус: **PENDING DISCOVERY**. Файлы lock появляются только из CI run `materialize-discover` ([foundation.yml](../../../.github/workflows/foundation.yml)); правила и schemas — в [corpus contracts](../README.md#acquisition-и-materialization-slice-d). Natural data на рабочей станции не скачиваются; payloads в git не попадают.

| Файл | Источник |
|---|---|
| `source-lock.json`, `licenses.json`, `materialization.json` | outputs discovery run после review |
| `runs/<mode>-<run_id>-<attempt>.json` | `report.json` каждого discovery/verify run |

## Runs

Пока не выполнялись.

## License review

Status каждой family остаётся `PENDING_SNAPSHOT_REVIEW`, пока maintainer не сверит license files и notices из `licenses.json` с SPDX в source plan.
