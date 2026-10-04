# pilot-v1: acquisition locks (DELSK-002, Slice D)

Статус: **PROPOSED — discovery reviewed, verify pending**. Файлы получены CI run `materialize-discover` ([foundation.yml](../../../.github/workflows/foundation.yml)); правила и schemas — в [corpus contracts](../README.md#acquisition-и-materialization-slice-d). Natural data на рабочей станции не скачивались; payloads в git не попадают. Freeze — после независимого `materialize-verify`, воспроизводящего эти файлы байт в байт, и review maintainer.

| Файл | SHA-256 / содержание |
|---|---|
| `source-lock.json` | 18 archives, 33 624 735 B acquired, 174 109 815 B expanded; retained members, исключённые по globs и non-regular пути |
| `licenses.json` | license files, copyright lines и SPDX tags retained members с путями |
| `materialization.json` | полный `delsk.corpus.lock.v1`: SHA-256 `e5c288256bed…` (в artifact run как `corpus-lock.json.gz`), 32 391 occurrences, 28 477 content objects, 446 924 313 materialized bytes, 0 cross-split objects |
| `runs/<mode>-<run_id>-<attempt>.json` | `report.json` каждого run, включая superseded |

## Runs

| Run | Commit | Mode | Результат |
|---|---|---|---|
| [37185935970](https://github.com/definitely-stable/Shift-lab/actions/runs/37185935970) | `93c600e` | discover | ok; superseded: notices без путей не позволяли review |
| [37186057381](https://github.com/definitely-stable/Shift-lab/actions/runs/37186057381) | `4e8cbf5` | discover | ok; `source-lock.json` байт в байт равен run 37185935970 (другой runner и commit, тот же plan/policy); notices с путями выявили 4 foreign-origin members curl |
| [37186134266](https://github.com/definitely-stable/Shift-lab/actions/runs/37186134266) | `200b9c5` | discover | ok; **текущие файлы** после исключения этих members |

Все runs без retry downloads; workload ≤25 s.

## Review discovery

- **Upstream digests.** zstd 1.5.5/1.5.6/1.5.7: `archive_sha256` совпадает с опубликованными `.sha256` release assets. zlib.net публикует SHA-256 только для текущей версии, curl и bzip2 — только PGP/GPG подписи (не проверялись), libpng на SourceForge — SHA-1/MD5, SQLite — SHA3-256 только текущего release. Для остальных 15 archives SHA-256 — trust-on-first-use, закреплённый двумя discovery runs.
- **Inventory.** Каждый archive имеет одну top-level directory; hostile paths, duplicates и links на source paths не найдены. Non-regular members: только symlinks `tests/cli-tests/bin/{unzstd,zstdcat}` в zstd (не payload). AppleDouble/скрытых `.c/.h` нет.
- **Foreign origin (amendment source plan).** Review notices по путям нашёл в retained curl members код с иными условиями, того же класса, что уже исключённые `lib/inet_ntop.c`/`lib/krb5.c`: `tests/server/tftpd.c` (BSD tftpd, UC Regents, BSD-4-Clause-UC), `lib/md4.c`/`lib/md5.c` (public-domain реализация Alexander Peslyak), `lib/curl_path.c` (OpenSSH, Damien Miller, ISC). Они добавлены в `exclude_globs` curl по provenance до появления любых scores. Copyrights отдельных contributors под лицензией проекта (curl vtls/smb/sha256, zstd `lib/common/threading.*`, libpng `arm/`, `loongarch/`) — first-party вклады, retained.
- **File track.** bzip2 (evaluation) не имеет `.c/.h` ≥64 KiB → нет file-track targets, как и предсказано. Strata `f004m` заполняет только `sqlite3.c`. `zlib crc32.h` одинаков во всех трёх releases, `libpng pngwutil.c` — в 1.6.43 и 1.6.44 (одинаковый `object_id`): будущие identity-only targets. curl `src/tool_hugehelp.c` (f256k) — generated first-party help text, retained по policy; это генерированный payload, а не исходный код, и его доля в curl file track видна в coverage.
- **Caps.** acquired 32.1 MiB ≤ 256 MiB; materialized 426 MiB ≤ 1 GiB (все occurrences всех tracks); chunk tracks дают 32 328 из 32 391 occurrences.

## License review

Status каждой family остаётся `PENDING_SNAPSHOT_REVIEW`: tool evidence собрана, решение maintainer о совместимости snapshot (license files и notices из `licenses.json` против SPDX source plan) ещё не записано. zlib/libpng/curl/bzip2 LICENSE/COPYING хешируются по releases; у SQLite license file нет — public-domain заявление в заголовках (`The author disclaims copyright`); zstd несёт `LICENSE` (BSD) и `COPYING` (GPLv2), pilot опирается на BSD-3-Clause.
