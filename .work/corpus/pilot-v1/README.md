# pilot-v1: acquisition locks (DELSK-002, Slice D)

Статус: **FROZEN_ACQUISITION — Slice D**. Решение, точные hashes и snapshot license review записаны в [freeze.json](freeze.json). Файлы получены CI run `materialize-discover` ([foundation.yml](../../../.github/workflows/foundation.yml)); правила и schemas — в [corpus contracts](../README.md#acquisition-и-materialization-slice-d). Natural data на рабочей станции не скачивались; payloads в git не попадают. Независимый `materialize-verify` воспроизвёл committed manifests байт в байт. Freeze относится к acquisition и transforms exploratory pilot; ancestry audit, frozen `C_t` и confirmatory sufficiency здесь не установлены.

| Файл | SHA-256 / содержание |
|---|---|
| `source-lock.json` | 18 archives, 33 624 735 B acquired, 174 109 815 B expanded; retained members, исключённые по globs и non-regular пути |
| `licenses.json` | license files, copyright lines и SPDX tags retained members с путями |
| `materialization.json` | полный `delsk.corpus.lock.v1`: SHA-256 `e5c288256bed…`, 32 391 occurrences, 28 477 content objects, 446 924 313 materialized bytes, 0 cross-split objects |
| `corpus-lock.json.gz` | полный canonical JSON metadata lock из verification artifact; 3 924 534 B gzip, 22 414 998 B после распаковки; payload отсутствует |
| [freeze.json](freeze.json) | acquisition freeze, license review шести families, hashes и ограничения; hash corpus lock считается отдельно для compressed file и canonical JSON |
| `runs/<mode>-<run_id>-<attempt>.json` | `report.json` каждого run, включая superseded |

## Runs

| Run | Commit | Mode | Результат |
|---|---|---|---|
| [37185935970](https://github.com/definitely-stable/Shift-lab/actions/runs/37185935970) | `93c600e` | discover | ok; superseded: notices без путей не позволяли review |
| [37186057381](https://github.com/definitely-stable/Shift-lab/actions/runs/37186057381) | `4e8cbf5` | discover | ok; `source-lock.json` байт в байт равен run 37185935970 (другой runner и commit, тот же plan/policy); notices с путями выявили 4 foreign-origin members curl |
| [37186134266](https://github.com/definitely-stable/Shift-lab/actions/runs/37186134266) | `200b9c5` | discover | ok; **текущие файлы** после исключения этих members |
| [37186222325](https://github.com/definitely-stable/Shift-lab/actions/runs/37186222325) | `ac9037c` | verify | ok; только committed lock: 18/18 archives совпали по size и SHA-256, `source-lock.json`, `licenses.json`, `materialization.json` воспроизведены байт в байт, полный corpus lock — тот же SHA-256 `e5c288256bed…` |

Все runs без retry downloads; workload ≤25 s; image `ubuntu-24.04` 20260927.320.1; CPU AMD EPYC 9V45 (run 37185935970) и EPYC 7763 (остальные) — `source-lock.json` совпал на обоих.

## Review discovery

- **Upstream digests.** zstd 1.5.5/1.5.6/1.5.7: `archive_sha256` совпадает с опубликованными `.sha256` release assets. zlib.net публикует SHA-256 только для текущей версии, curl и bzip2 — только PGP/GPG подписи (не проверялись), libpng на SourceForge — SHA-1/MD5, SQLite — SHA3-256 только текущего release. Для остальных 15 archives SHA-256 — trust-on-first-use, закреплённый двумя discovery runs.
- **Inventory.** Каждый archive имеет одну top-level directory; hostile paths, duplicates и links на source paths не найдены. Non-regular members: только symlinks `tests/cli-tests/bin/{unzstd,zstdcat}` в zstd (не payload). AppleDouble/скрытых `.c/.h` нет.
- **Foreign origin (amendment source plan).** Review notices по путям нашёл в retained curl members код с иными условиями, того же класса, что уже исключённые `lib/inet_ntop.c`/`lib/krb5.c`: `tests/server/tftpd.c` (BSD tftpd, UC Regents, BSD-4-Clause-UC), `lib/md4.c`/`lib/md5.c` (public-domain реализация Alexander Peslyak), `lib/curl_path.c` (OpenSSH, Damien Miller, ISC). Они добавлены в `exclude_globs` curl по provenance до появления любых scores. Copyrights отдельных contributors под лицензией проекта (curl vtls/smb/sha256, zstd `lib/common/threading.*`, libpng `arm/`, `loongarch/`) — first-party вклады, retained.
- **File track.** bzip2 (evaluation) не имеет `.c/.h` ≥64 KiB → нет file-track targets, как и предсказано. Strata `f004m` заполняет только `sqlite3.c`. `zlib crc32.h` одинаков во всех трёх releases, `libpng pngwutil.c` — в 1.6.43 и 1.6.44 (одинаковый `object_id`): будущие identity-only targets. curl `src/tool_hugehelp.c` (f256k) — generated first-party help text, retained по policy; это генерированный payload, а не исходный код, и его доля в curl file track видна в coverage.
- **Caps.** acquired 32.1 MiB ≤ 256 MiB; materialized 426 MiB ≤ 1 GiB (все occurrences всех tracks); chunk tracks дают 32 328 из 32 391 occurrences.

## License review

Все шесть families имеют `REVIEWED_FOR_PILOT` в [freeze.json](freeze.json). Root LICENSE/COPYING всех 15 архивов bzip2/curl/libpng/zlib/zstd сверены с официальными release tags: SHA-256 совпали с acquired snapshots. Прочитаны условия и notices retained members; ни один family notice set не обрезан. У SQLite license file нет: retained notices отказываются от copyright, а [официальное заявление](https://sqlite.org/copyright.html) распространяет public-domain dedication на код и документацию. zstd несёт BSD `LICENSE` и альтернативный GPLv2 `COPYING`; для pilot выбрана BSD-3-Clause. Лицензии исключённых `contrib`, `build` и foreign-origin paths не переносятся на retained payload.

Review разрешает acquisition и исследовательские transforms этих snapshots. Payload не публикуется. Для будущей redistribution нужно сохранить исходные notices/license files и явно пометить derived representations; это не project-wide legal/FTO verdict и не разрешение binary/model track. Статусы исходного source plan оставлены историческими: его bytes уже закреплены в двух runs, текущий review state читается из freeze record.

## Offline verification и границы

`python -m unittest discover -s .work/tests -p test_pilot_freeze.py` распаковывает сохранённый lock, проверяет полный SHA-256, schema, occurrence/content/byte accounting и plan/policy contracts; отдельно проверяет freeze hashes, license review coverage и discovery/verification identities. Network и corpus payload не нужны. Сохранены admission и runner evidence verification run в `runs/verify-37186222325-1-{admission,run}.json`: accounting complete, 4 used + 30 reserved runner-min ≤600, artifact storage ≤cap. Budget mode этого run — `warn`, но accounting и budget проверки фактически полны и успешны.

Independent branch review обнаружил два недостающих acceptance пункта: durable полный lock и записанный snapshot license review. Оба закрыты этим freeze record и offline checks. Upstream подписи, libpng archive/git-tree equivalence и юридическая оценка вне этого review; ограничения сохранены. Linux resource enforcement проверяется в CI; локально эти семь тестов пропускаются на Windows. Следующие Slices E/F выполняют ancestry/candidate audit и durable foundation handoff; DELSK-002 и весь R0 здесь не закрываются.
