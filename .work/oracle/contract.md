# DELSK-003: oracle sub-contract `delsk.oracle-contract.v1`

Статус: **FROZEN с момента merge в `main`**, scope — только DELSK-003 / G1 primary oracle. Идентичность принятых bytes — [freeze.json](freeze.json). Natural oracle measurements: **NOT_RUN**. Ни одного patch cost, oracle base или utility value по natural corpus в репозитории нет и при подготовке контракта не вычислялось.

**Slice A verdict: ORACLE CONTRACT FREEZE-READY**

Контракт фиксирует ground truth первого natural oracle run **до** реализации runner/evaluator и до любых реальных измерений: codec и framing, учёт bytes, pair universe, correctness, семантику oracle, evaluator, closed schemas, known answers, mutants и CI. [DELSK-P1](../protocol.md) остаётся `PLANNED`: scorer, baselines, contrasts и G2–G5 не заморожены (§14).

## 0. Governance

- **Отношение к DELSK-P1.** Контракт сужает P1 §2–§3 для G1 и не противоречит ему. `protocol.md` не меняется: его bytes привязаны в E0 freeze и candidate lock (`protocol_sha256`). Где P1 оставляет выбор (codec, framing, populations, классификация failures), действует этот контракт.
- **Неизменяемость.** Контракт, codec lock, schemas и vectors неизменяемы для первого natural oracle run и всех его повторов. Изменение accounting, codec, options, framing, failure semantics или evaluator semantics — только новый `delsk.oracle-contract.v2` с новым freeze record и новым run. Старые bytes, записи и результаты сохраняются и не переписываются. Это относится и к исправлениям **до** natural run (например, если recipe сборки не собирается): новая версия, а не правка v1.
- **Кто принимает.** Maintainer Shift-lab merge этого PR в `main`. Merge commit — акт adoption.
- **Что adoption не делает.** Не разрешает natural run. Natural measurement начинается только после отдельного подтверждения maintainer после merge и после зелёного Slice B (§15).

## 1. Привязанные inputs

| Input | SHA-256 |
|---|---|
| Candidate lock `delsk.candidate.lock.v2` ([E1](../corpus/e1/README.md)) | `cb16d53b164ff393187e0115bdf31c52ac717a5172fb1e91889b5988ac019d2e` |
| Corpus lock (decompressed canonical) | `e5c288256bed284572a9f111186411517b4c73d097d13aea4cf48e2fb9f6fffa` |
| E1 seal record | см. `bindings.seal_sha256` в [freeze.json](freeze.json) |
| Protocol `delsk.protocol.v1` | `a0c518247d111e8ad1294562d65eb34c28da87c7027c009efb64a39e6f4e0038` |
| Codec lock ([codec-lock.json](codec-lock.json)) | `bindings.codec_lock_sha256` в [freeze.json](freeze.json) |

`C_t`, corpus, splits, target roster, caps (2/30/32, `max_targets=64`, 4096 pairs/codec) и thresholds G1–G5 не меняются.

## 2. Codec и framing lock

### 2.1 Primary delta codec: xdelta3 3.2.1

Гипотеза `xdelta3` проверена по upstream источникам, а не по package manager. Существенной причины отказаться от него нет; STOP не нужен.

| Свойство | Evidence (проверено 2026-10-04) |
|---|---|
| Upstream | [github.com/jmacd/xdelta](https://github.com/jmacd/xdelta), автор Joshua MacDonald; активен (релизы 3.2.0 2026-06-21, 3.2.1 2026-09-28) |
| License | Apache-2.0: `xdelta3/LICENSE` и заголовки всех компилируемых файлов. Ветка 3.0.x и tag `v3.1.0` на main — GPL-2.0+ |
| Version | tag `v3.2.1` (annotated, unsigned), tag object `3f577112b873d363f9b8d544d1ae37740195d9f3`, commit `2c36417e6d09bf700d3d1cca44ed3e42101016c3`, tree `4a7e05ea9beb44cfbda4b3ad5a4b20e7b2d2217e` |
| Source archive | release asset `xdelta3-3.2.1.tar.gz`, 225 056 B, SHA-256 `936e10fc9f2be9e18c9fd6719895ff2055e67e47a155776badc6aa8c25ba70fa`. Все 52 файла архива byte-identical blobs `commit:xdelta3/` (`git hash-object --no-filters`) |
| Hosted Ubuntu | upstream [CI run 36437176010](https://github.com/jmacd/xdelta/actions/runs/36437176010) на этом commit: success на `ubuntu-latest` x64 и `ubuntu-24.04-arm`, `-DXD3_WERROR=ON`, LZMA on/off. Это evidence buildability, не наш run |
| Формат | VCDIFF RFC 3284. Oracle — лучший результат **этой версии и конфигурации** на конечном `C_t`, не математически минимальная delta (P1 §2) |
| Детерминизм | В кодеке нет времени, случайности и потоков; при выключенном app header выход не зависит от имён файлов. Проверяется conformance C12–C14 (§10.3) и независимым повтором (§7) |

**Опасности, найденные в исходниках 3.2.1, и как lock их закрывает.**

| Hazard (файл upstream) | Последствие без lock | Решение |
|---|---|---|
| Secondary compression: LZMA по умолчанию, если собрано с liblzma (`xdelta3-main.h`, `-S`) | payload зависит от системной liblzma | сборка `SECONDARY_LZMA=0` и явный `-S none` |
| Application header по умолчанию содержит имена source/target (`-A`) | одинаковый patch получает разный payload от путей | `-A=` (header выключен) |
| Armor mode по умолчанию в CMake build: BLAKE3 digests в app header, decode exit 2 «already up to date» | два BLAKE3 hex digest (2×64 B) плюс framing в каждом patch, особый exit code | `XD3_ARMOR=0` и `-a` |
| External compression: gzip/bzip2/xz inputs автоматически распаковываются внешней программой и перепаковываются при decode | 9 near targets track `tar-gz` пошли бы через системный gzip; перепаковка не byte-exact | `EXTERNAL_COMPRESSION=0` и `-D -R` |
| Environment `XDELTA` дописывает аргументы (`setup_environment`) | options вне lock | окружение не наследуется (§2.3) |
| Adler-32 на каждое окно (4 B/окно) | checksum bytes в одной representation, но не в другой | `-n` на encode и decode; та же политика у zstd (§3) |
| `-B` source window: default 64 MiB, clamp к размеру source (3.2.0 #291) | неявная зависимость от default | явные `-B 67108864`; pilot max base 10 936 320 B < 64 MiB, вся база адресуема |
| `-W` input window default 8 MiB | targets > 8 MiB кодируются несколькими окнами | явные `-W 8388608 -P 262144 -I 32768`, равные defaults |
| Уровни `-7…-9` отображаются в один `XD3_SMATCH_SLOW` | — | фиксирован `-9` |
| Exit codes: 0 success, 1 error или help, 2 только armor | — | успех только 0; иное — failure (§5) |
| Decoder warning о missing checksum | — | подавлен `-n` на decode |

### 2.2 Standalone compressor: zstd 1.5.7

| Свойство | Evidence |
|---|---|
| Upstream | [github.com/facebook/zstd](https://github.com/facebook/zstd) |
| License | BSD-3-Clause OR GPL-2.0-only (dual) |
| Version | tag `v1.5.7` (2025-02-19), tag object `ac66b19e6bd6b83238bf008eecc1298105298532`, commit `f8745da6ff1ad1e7bab384bd1f9d742439278e99`, tree `1a3cb277e9b9b37b01811a3c65f6c25d46a8f241` |
| Source archive | release asset `zstd-1.5.7.tar.gz`, 2 434 947 B, SHA-256 `eb33e51f49a15e023950cd7825ca74a4a2b43db8354825ac24fc1b7ee09e6fa3` (= upstream `.sha256` sidecar). Все C sources `lib/` и `programs/` byte-identical tag tree; 4 Windows-only файла отличаются и не собираются |
| Формат | один Zstandard frame (RFC 8878) |

Hazards: CLI по умолчанию пишет XXH64 checksum (`--no-check`); content size пишется только при известном размере (input всегда regular file и явный `--content-size`); `ZSTD_CLEVEL`/`ZSTD_NBTHREADS` меняют параметры (env не наследуется); `-T1` даёт другой frame, чем `--single-thread` (сборка `HAVE_THREAD=0` и `--single-thread`); Makefile автодетектит zlib/lzma/lz4 (`HAVE_*=0`); dictionary не используется.

### 2.3 Точная сборка и вызов

Нормативно — [codec-lock.json](codec-lock.json) (`delsk.oracle.codec-lock.v1`). `options_sha256 = Hc(codec entry без options_sha256)`, где `Hc` — SHA-256 compact canonical JSON (`manifests.digest`).

| Codec | `codec_id` | `options_sha256` |
|---|---|---|
| xdelta3 | `xdelta3-3.2.1-l9-snone-v1` | `90f3a41324301de60f1acda061fbe101fb2c11b14029de341aa21fbd58ee4d5a` |
| zstd | `zstd-1.5.7-l19-v1` | `e50e7710e1f91ed9b5046cd3e7607c0008f675061fc8e51af5263e9c6a77d9bb` |

```text
build xdelta3 (cwd xdelta3-3.2.1, env LC_ALL=C PATH=/usr/bin:/bin):
  cc -std=gnu99 -O3 -DNDEBUG -DXD3_MAIN=1 -DXD3_DEBUG=0 -DREGRESSION_TEST=1 -DSECONDARY_DJW=1
     -DSECONDARY_FGK=0 -DSECONDARY_LZMA=0 -DEXTERNAL_COMPRESSION=0 -DXD3_ARMOR=0 -DXD3_POSIX=1
     -DXD3_USE_LARGESIZET=1 -DXD3_USE_LARGEFILE64=1 -DSIZEOF_SIZE_T=8 -DSIZEOF_UNSIGNED_INT=4
     -DSIZEOF_UNSIGNED_LONG=8 -DSIZEOF_UNSIGNED_LONG_LONG=8 -o xdelta3 xdelta3.c -lm
encode: xdelta3 -e -9 -S none -A= -n -a -D -R -B 67108864 -W 8388608 -P 262144 -I 32768 -f -q -s base.bin target.bin patch.bin
decode: xdelta3 -d -n -a -D -R -B 67108864 -f -q -s base.bin patch.bin decoded.bin

build zstd (cwd zstd-1.5.7, same env):
  make -C programs zstd-release HAVE_THREAD=0 HAVE_ZLIB=0 HAVE_LZMA=0 HAVE_LZ4=0 ZSTD_LEGACY_SUPPORT=0
encode: zstd -19 --single-thread --no-check --content-size --no-progress -q -f target.bin -o payload.bin
decode: zstd -d --no-progress -q -f payload.bin -o decoded.bin
```

Сборка xdelta3 — один translation unit с флагами upstream CMake target `xdelta3` (Release `-O3 -DNDEBUG`, C99 с GNU extensions), без CMake: upstream CMake на Linux включает external compression, автодетектит liblzma и скачивает BLAKE3 через FetchContent по tag. Флаги проверяются в run через вывод `xdelta3 config` (self report) и `zstd -vV`.

Вызов: окружение не наследуется, только `LC_ALL=C`; запрещены `XDELTA`, `ZSTD_CLEVEL`, `ZSTD_NBTHREADS`, `CFLAGS`, `CPPFLAGS`, `LDFLAGS`; абсолютный путь проверенного executable; свежий пустой cwd на вызов; stdin `/dev/null`; один codec process одновременно; timeout — SIGKILL process group; peak RSS — `os.wait4` `ru_maxrss`.

Compiler не закреплён: `cc` образа `ubuntu-24.04` (системный GCC 13.x). Имя/версия compiler и SHA-256 executable пишутся в `run.json`. Независимость результата от compiler проверяет golden conformance (C14): другой compiler, давший другие golden digests, делает run `INVALID`.

### 2.4 Отвергнутые варианты

| Вариант | Почему нет |
|---|---|
| apt `xdelta3` Ubuntu 24.04 (3.0.11) | floating package, GPL-2.0+, без hardening 3.2.x |
| tag `v3.1.0` (2016) | на main это GPL-2.0+ код без allocation hardening и исправлений GCC warnings |
| `v3.2.0` | не содержит исправлений 3.2.1 (GCC warnings #306, decoder hardening #309/#316, decoder `clen` layout в DJW) |
| upstream CMake build | external compression on, liblzma autodetect, BLAKE3 FetchContent по tag (сеть, не hash) |
| `-S djw` / `-S lzma` | djw — нестандартное расширение xdelta (не RFC 3284), lzma — системная liblzma; оба допустимы только как отдельный codec ID (§2.5) |
| Python `lzma`/`zlib` как standalone | версия системной библиотеки образа не закреплена |
| `zstd --ultra -22`, `--long` | больше памяти и времени без закрепляемой выгоды; уровень 19 — максимум без `--ultra` |

### 2.5 Второй codec: admission requirements (будущий sub-slice A2)

Второй codec не входит в Slice A и не сравнивается. Admission требует: независимый upstream и license; exact source archive SHA-256 и build recipe без сетевых fetch по tag; собственные `codec_id`/`options_sha256`; тот же frame v1 (§3) с обоснованием каждого нулевого компонента и тем же 32 B base reference; conformance C01–C14 analogs; отдельный oracle run и отдельные rows (codecs не смешиваются в одном run); новая версия контракта или addendum с собственным freeze. Выбор и rationale не могут ссылаться на natural результаты xdelta3; codec, выбранный после просмотра natural xdelta3 costs, маркируется post-hoc и не участвует в cross-codec claims. Кандидаты (не решено): `zstd --patch-from`, open-vcdiff, HDiffPatch, xdelta3 с `-S djw`.

## 3. Cost accounting: frame v1

`delsk.oracle.frame.v1` — нотационный container одинаковый для всех representations. Он задаёт точную длину, а не wire format Delsk.

| Компонент | raw | standalone (zstd) | delta (xdelta3) |
|---|---|---|---|
| `payload_bytes` | `n` = длина target | длина файла `payload.bin` (весь zstd frame) | `patch_payload_bytes` = длина файла `patch.bin` (весь VCDIFF stream, включая magic и header) |
| `wrapper_bytes` | `1 + uleb128_len(n)` | `1 + uleb128_len(payload)` | `1 + uleb128_len(patch_payload)` |
| `base_reference_bytes` | 0 | 0 | **32** |
| `codec_metadata_bytes` | 0 | 0 | 0 |
| total | `raw_total_bytes` | `compressed_total_bytes` | `delta_total_bytes` |

- `uleb128_len(x)` — число bytes unsigned LEB128 записи `x` (1 при `x<128`, 2 при `x<2^14`, …); `uleb128_len(0)=1`.
- `wrapper_bytes` = 1 byte representation kind (raw=0, standalone=1, delta=2) + длина payload. Длина target не дублируется: она восстанавливается из raw payload, из zstd frame (content size) и из VCDIFF windows.
- `base_reference_bytes = 32`: raw binary SHA-256 object ID базы (content address из corpus lock). Не hex (64), не catalog index (зависит от размера и порядка каталога). Одинаков для всех delta, поэтому argmin не меняет, но участвует в сравнении с `S`.
- `codec_metadata_bytes = 0` — frozen rule: VCDIFF header (magic, indicator, secondary ID, code table, window descriptors) и zstd frame header (window descriptor, content size) находятся **внутри** payload; options encoder decoder не нужны; dictionary нет; codec identity несёт kind byte.
- **Checksum policy.** Ни одна representation не содержит codec-internal checksum: xdelta3 `-n` (нет Adler-32), zstd `--no-check` (нет XXH64). Integrity — SHA-256 target object ID, который catalog хранит для любой representation одинаково; он не начисляется ни одной из них и проверяется oracle при каждом decode.
- Не входят: fetch/storage базы (chain depth = 1, база хранится standalone; публикуется отдельно, P1 §2), catalog metadata, descriptors.

Формулы:

```text
raw_total(t)        = n + 1 + uleb128_len(n)
compressed_total(t) = z + 1 + uleb128_len(z)                         (z = zstd payload bytes)
S(t)                = min(raw_total, compressed_total)                standalone_total_bytes
D_E(b,t)            = p + 1 + uleb128_len(p) + 32 + 0                 (p = patch_payload_bytes)
```

`standalone_total_bytes` — это `S(t)` на том же accounting level, что `delta_total_bytes`. Сравнивать `patch_payload_bytes` с `S` или с zstd payload запрещено (mutant M06). Если zstd не дал успешный roundtrip, `compressed_total = +inf` и `S = raw_total` (raw не требует codec). При `raw_total = compressed_total` выбирается raw (стоимость та же). Пример: payload 100 → `D = 100+1+1+32 = 134`; zstd payload 400 → `403`; пустой target → `raw_total = 2`.

**Одна интерпретация на payload.** Total — детерминированная функция `(representation, payload_bytes)`; одинаковый patch не может получить два total. Варианты, дающие разный payload для одних bytes (app header с путями, armor, checksum, external compression, stdin vs file для zstd), исключены lock (§2).

## 4. Pair universe

- Только sealed E1 `C_t`. Expected set на codec: `{(q.target, b.object_id) : q ∈ lock.queries, q.status = near_duplicate, b ∈ q.bases}` — 64 near targets, **1 961** ordered pairs. 15 identity-only queries имеют 0 bases и не дают пар; `planned_pairs_per_codec = 1961`.
- `pair_id = Hc(["delsk.oracle.pair.v1", codec_id, target_occurrence_id, base_object_id])`.
- Canonical order: `(target_occurrence_id, base_object_id)` по ASCII — это порядок хранения candidate lock. Pair rows и `pairs.jsonl` записываются в этом порядке; evaluator результат от порядка не зависит (P1 метаморфное свойство, M11).
- Standalone rows: ровно одна на каждую из 79 queries, включая identity-only.
- Materialization: target bytes — bytes object `target_object_id` occurrence target из corpus lock; base bytes — bytes object `base_object_id`, материализованные через `representative`. До encode обязательна проверка `SHA-256(bytes) = object_id` и длины; иначе status `input_integrity` и run `INVALID`.
- Ни одна пара не исчезает из evidence: каждая expected пара получает row с любым status. Пара, не выполненная из-за abort runner, получает `not_run` и считается missing. Отсутствие row тоже missing.

## 5. Per-pair procedure и correctness

```text
for (t, b) in canonical order:
    materialize t, b; verify length + SHA-256 against lock          -> input_integrity
    encode(b, t) under limits                                       -> patch
    decode(b, patch) under limits                                   -> decoded
    verify len(decoded) = len(t), decoded == t byte-for-byte, SHA-256(decoded) = object_id(t)
    row: payload/total bytes, patch SHA-256, decoded SHA-256, exit codes, signals, wall ns, peak RSS
```

| Фаза | Причина | `status` (`error_class`) | Стоимость | Следствие |
|---|---|---|---|---|
| materialize | SHA/длина ≠ lock | `input_integrity` (`base_integrity`/`target_integrity`) | — | run `INVALID` |
| encode | wall timeout | `timeout` (`wall_timeout`) | `+inf` | bounded failure |
| encode | exit ≠ 0, signal, нет output | `codec_error` (`nonzero_exit`/`signal`/`missing_output`) | `+inf` | bounded failure |
| encode | RLIMIT_AS, work-dir cap | `resource_limit` (`address_space`/`work_dir`) | `+inf` | bounded failure |
| decode | wall timeout | `timeout` (`wall_timeout`) | `+inf` | bounded failure |
| decode | exit ≠ 0, signal, нет output, длина/bytes/SHA ≠ | `decode_mismatch` | — | run `INVALID` |
| runner | abort до выполнения | `not_run` (`runner_abort`) | — | missing → `INCOMPLETE` |

- `decode mismatch ⇒ весь oracle run INVALID`. Он не превращается в `+inf`, и quality verdict не выпускается.
- Ошибка декодера на patch, который только что выдал encoder (non-zero exit, signal, ENOMEM), — нарушение roundtrip и классифицируется как `decode_mismatch`, а не `codec_error` (§13 A11). Так decode errors нельзя «отмыть» в bounded `+inf`.
- Строка `ok` обязана иметь все cost fields; строка не `ok` — ни одного (schema `if/then/else`).
- Limits на вызов (оба codec): encode 120 s wall, decode 60 s wall, `RLIMIT_AS` 2 GiB. Это часть определения bounded oracle.
- Standalone: тот же цикл с zstd (`compress`/`decompress`); decode mismatch → `INVALID`; timeout/codec/resource failure → `S = raw_total`, bounded failure.
- Timing (`*_wall_ns`, peak RSS) — descriptive: включает spawn процесса, не является P1 timing evidence и не входит в cost projection.

## 6. Семантика oracle

Для near target `t` с finite set `F_t = {b : row(t,b).status = ok}`:

```text
O_delta(t) = min D_E(b,t) over b ∈ F_t;            +inf if F_t = ∅
ties(t)    = { b ∈ F_t : D_E(b,t) = O_delta(t) }    (все bases с точным минимумом, sorted by object ID)
O(t)       = min(S(t), O_delta(t))
useful(t)  = O_delta(t) < S(t)                       (строго; равенство → standalone)
oracle_choice = delta if useful else standalone
```

- `F_t = ∅` (`all_pairs_failed`) или `C_t = ∅` (`empty_candidate_set`): `O_delta = +inf` (null в rows), ties пусто, `O = S`, strict/ε recall для `t` — `N/A`, это не успех. Coverage публикует оба случая отдельно.
- Никакого arbitrary first winner: tie set полный (M03).
- Identity-only queries: `oracle_delta_status = identity_only`, `O = S`, вне всех near populations (dedup cost не оценивается этим контрактом).

## 7. Run status и G1

Precedence: `INVALID` > `INCOMPLETE` > `COMPLETE_WITH_FAILURES` > `COMPLETE`.

| `run_status` | Условие | Что выпускается |
|---|---|---|
| `INVALID` | любая invalid reason: `IDENTITY_MISMATCH`, `OPTIONS_MISMATCH`, `FOREIGN_PAIR`, `DUPLICATE_PAIR` (даже byte-identical), `PAIR_ID_MISMATCH`, `LOCK_FIELD_MISMATCH`, `SEALING_VIOLATION`, `ACCOUNTING_MISMATCH`, `DECODE_MISMATCH`, `INPUT_INTEGRITY`, `INCONSISTENT_ROW` (в том числе опубликованная target row ≠ пересчёту или sealed target с чужими counts), `FOREIGN_STANDALONE`, `DUPLICATE_STANDALONE`, `FOREIGN_TARGET`, `DUPLICATE_TARGET`, `SCHEMA`, `BINDING_MISMATCH`, `NONCANONICAL` | только reasons; coverage, targets и metrics — нет |
| `INCOMPLETE` | валидные rows, но missing pair (нет row или `not_run`), missing standalone или нет published target row для query | coverage; targets и metrics — нет (incomplete oracle запрещает exact claim) |
| `COMPLETE_WITH_FAILURES` | все пары и standalone есть, ≥1 timeout/codec/resource failure | coverage, failure rate, targets, metrics с меткой `bounded` |
| `COMPLETE` | все пары `ok`, все standalone `ok` | всё, метка `exhaustive` |

**G1 (primary codec)** — по всем attempts одной measurement identity (§9):

| Ситуация | G1 |
|---|---|
| любой attempt `INVALID` | `INVALID` (исправлять измерение; хорошие runs его не перекрывают) |
| `COMPLETE` runs с разными `cost_projection_sha256`, `targets_canonical_sha256` **или `sealed_commitments_sha256`** | `INVALID` (`REPEAT_MISMATCH`: недетерминированное измерение, в том числе скрытое в sealed evaluation split, G09) |
| любой attempt `INCOMPLETE` или `COMPLETE_WITH_FAILURES` | `NOT_PASSED` |
| `COMPLETE` run без conformance PASS или без verified bundle | `NOT_PASSED` (`CONFORMANCE_OR_BUNDLE`) |
| меньше двух verified `COMPLETE` runs с **разными** GitHub run ID (attempts одного run не считаются) | `NOT_PASSED` (`REPEAT_MISSING`) |
| иначе | `PASS` |

`PASS` дополнительно требует: evaluator пересчитал targets/coverage/summary из retained rows байт в байт (bundle verify), KAT suite зелёный на evaluator commit. Все attempts сохраняются; неудачный run нельзя заменить удачным без записи обоих. Codec failures в обычном exhaustive G1 не позволяют закрыть G1.

## 8. Evaluator

Evaluator — отдельный код (Slice B) со своей identity. Он не читает patch payloads и пересчитывает всё из retained rows: `pairs.jsonl`, `standalone.jsonl`, committed candidate/corpus locks, codec lock и (для метода) `retrieval.jsonl`.

**Validation (fail-closed).** Rows проверяются по [schemas.json](schemas.json), затем семантически: identity и options каждой row = run identity; pair ∈ expected set; нет дубликатов; `pair_id`; target object/bytes/split/representative/base bytes = lock; `delta_total = p + wrapper(p) + 32 + 0` и `compressed_total` аналогично; `ok ⇒ decoded_bytes = target_bytes ∧ decoded_sha256 = target_object_id`; sealing (§9.1). Ошибка → `INVALID` с reason. Expected set и populations выводятся из lock, а не из rows: строка, отсутствующая в rows, не может исчезнуть из denominator.

**Retrieval input** (`delsk.oracle.retrieval.v1`): на каждый unsealed near target ровно одна row `{method_id, K, bases[], encode_calls}`; все rows одного файла имеют одинаковые `method_id` и `K` (иначе `SCHEMA`). Ошибки (`RETRIEVAL_COVERAGE` — нет row или лишняя/повторная, `RETRIEVAL_FOREIGN_BASE` — база вне `C_t`, `RETRIEVAL_DUPLICATE_BASE`, `RETRIEVAL_OVER_K`, `RETRIEVAL_CALLS` — `encode_calls < |R_K|`) делают retrieval `INVALID`, metrics не выпускаются, oracle status не меняется. Пустой список допустим и даёт `A = S`. Отсутствующая row никогда не заменяется oracle-best (M09).

```text
A(t) = min(S(t), min{ D_E(b,t) : b ∈ R_K(t), row(t,b).status = ok })     failed/+inf bases не дают стоимость
```

**Populations** (только unsealed): `N` — near targets; `F ⊆ N` — `O_delta` конечен; `U ⊆ F` — `useful`.

| Метрика | Формула (exact rational) | Denominator / N/A |
|---|---|---|
| Strict delta Recall@K | `#{t∈F : R_K(t) ∩ ties(t) ≠ ∅} / |F|` | `|F|=0 → N/A` |
| Useful-delta Recall@K | то же по `U` | `|U|=0 → N/A`; `|U|` публикуется |
| ε Recall@K, ε∈{1,2,5}% | `#{t∈F : ∃b∈R_K, ok: 100·D ≤ 100·O_delta + max(6400, e·O_delta)} / |F|` | `|F|=0 → N/A`; граница `≤` (K15 hit, K16 miss) |
| Byte regret | `A(t)−O(t) ≥ 0`; sum, p50, p95, max | по `N` и отдельно по `U`; пусто → `N/A` |
| Normalized regret | `(A−O)/max(O, 64)`; p50, p95, max; per-target values для CDF | по `N` и по `U` |
| SavingsCapture | `Σ_N (S−A) / Σ_N (S−O)` | denominator 0 → `N/A`, не 1 (M08) |
| Candidate-call reduction | `Σ_N |C_t| / Σ_N encode_calls` | denominator 0 → `N/A` |

- Квантили — Hyndman–Fan type 7 (linear) на exact rationals: `h=(n−1)p`, `x_⌊h⌋ + (h−⌊h⌋)(x_⌊h⌋+1 − x_⌊h⌋)`.
- Все отношения хранятся как reduced `{num, den}` (canonical JSON запрещает floats); `N/A` — строка.
- Targets без finite delta не входят в `F`, но остаются в `N` (regret 0, `S−A = S−O = 0`) и в coverage. Failures не удаляются ни из одного denominator, который их содержит по определению (M10).
- Byte-weighted, per-domain macro и lineage aggregation (P1 Macro quality) — не заморожены (§14); evaluator публикует per-target rows, достаточные для них.
- **Identity evaluator.** `evaluator_sha256` = SHA-256 bytes кода evaluator; `evaluator_source_sha` = commit, на котором он выполнен. Это отдельные identities от `measured_source_sha` (commit runner). Смена evaluator при неизменных rows создаёт новую evaluation record; measurement identity не меняется; verdict, полученный одним evaluator, не переносится на другой без пересчёта (K20).

### 8.1 Retained outputs

`targets.jsonl` — ровно одна row на каждую query lock, в canonical order по `target_occurrence_id`. Для unsealed split — `delsk.oracle.target.v1`: `S`, `standalone_choice`, finite `O_delta` или null + `oracle_delta_status`, `O`, полный tie set, `oracle_choice`, `useful_delta`, pair coverage и failure counts по классам; evaluator пересчитывает её из retained rows и требует точного равенства (иначе `INCONSISTENT_ROW`, K41). Для sealed split — `delsk.oracle.target-sealed.v1` (§9.1). Отсутствующая row → `INCOMPLETE` (K42). `coverage.json`, `summary.json`, `evaluation.json` — schemas в [schemas.json](schemas.json).

## 9. Identities, digests и schemas

```text
measurement_identity = { contract_id, contract_freeze_sha256, codec_lock_sha256,
                         delta: {codec_id, options_sha256}, standalone: {codec_id, options_sha256},
                         corpus_lock_sha256, candidate_lock_sha256, measured_source_sha,
                         oracle_code_sha256, phase, sealed_splits }
measurement_identity_sha256 = Hc(measurement_identity)          (GitHub run ID и время сюда не входят)
canonical JSONL = rows в canonical order, compact canonical JSON + "\n"
canonical order    = (target_occurrence_id, base_object_id или "", schema) по ASCII
pairs_canonical_sha256, standalone_canonical_sha256 = SHA-256(canonical JSONL unsealed rows)
targets_canonical_sha256  = SHA-256(canonical JSONL unsealed full target rows)
cost_projection_sha256    = то же для unsealed pair rows без encode/decode wall ns и peak RSS
RUN_SPECIFIC              = { encode/decode/compress/decompress wall ns, peak RSS,
                              measurement_identity_sha256, measured_source_sha }
commitment(row)           = Hc(row без RUN_SPECIFIC)                         (row_sha256 sealed rows)
sealed_commitments_sha256 = SHA-256(canonical JSONL всех sealed rows — pair_sealed, standalone_sealed,
                              target_sealed — без RUN_SPECIFIC)
```

Repeat equality G1 (§7) — кортеж `(cost_projection_sha256, targets_canonical_sha256, sealed_commitments_sha256)`. Третий элемент обязателен: изменение стоимости или patch не-победителя в sealed split не меняет ни unsealed projection, ни tie set, но меняет commitment его pair row (тест `test_repeat_gate_sees_hidden_evaluation_changes`).

Каждая pair row несёт `measurement_identity_sha256`, `measured_source_sha`, `corpus_lock_sha256`, `candidate_lock_sha256`, `codec_id`, `options_sha256`, status, payload/total bytes, `patch_sha256`, decoded SHA-256, encode/decode wall ns, peak RSS и failure class. GitHub run/attempt — в `run.json`.

[schemas.json](schemas.json) — JSON Schema 2020-12, по одному `$defs` на artifact: `codec_lock`, `run`, `pair`, `pair_sealed`, `standalone`, `standalone_sealed`, `target`, `target_sealed`, `coverage`, `summary`, `retrieval`, `evaluation`. Все object schemas закрыты (`additionalProperties: false`, тест `test_every_object_schema_is_closed`). Evidence bundle v1 [CI plan](../ci-plan.md#evidence-bundle-v1) дополняется `standalone.jsonl`, `evaluation.json` и `codec-lock.json`.

### 9.1 Sealing evaluation split (leakage)

Опубликованные oracle costs evaluation lineage до freeze scorer/baselines — прямой путь leakage held-out (P1 §4). Поэтому для `sealed_splits = ["evaluation"]`:

- runner измеряет **все** 1 961 пар (полнота и correctness G1 проверяются на всех), но для evaluation split публикует только sealed rows. `pair_sealed`: identity, codec/options, `pair_id`, target, base, split, status, failure phase/class, `decoded_sha256`, `row_sha256 = commitment(полная pair row)`. `standalone_sealed`: identity, codec/options, target, split, query status, status, failure phase/class, `decoded_sha256`, `row_sha256 = commitment(полная standalone row)`. `decoded_sha256` обязателен для `ok` (= публичный target object ID, поэтому ничего не раскрывает) и null для failure (schema `if/then/else`). Cost fields, `patch_sha256`, `compressed_sha256`, target/decoded size и standalone sizes этого split не попадают ни в artifact, ни в лог;
- **target sealing.** Внутри job, до sealing, evaluator того же commit выводит полную `target.v1` row каждой evaluation target из полных pair/standalone rows (§6, §8.1). Публикуется только `target_sealed`: `measurement_identity_sha256`, `target_occurrence_id`, split, query status, `candidate_count`, `pairs_expected/ok/timeout/codec_error/resource_limit`, `standalone_status` и `row_sha256 = commitment(полная target row)`. `S`, `O`, `O_delta`, ties, `useful_delta`, `oracle_choice`, `target_bytes` и `candidate_list_sha256` не публикуются. Sealed target rows не входят в `targets_canonical_sha256`; они входят в `sealed_commitments_sha256`;
- evaluator считает sealed rows в completeness и correctness: status `decode_mismatch`/`input_integrity`, `ok` pair или standalone с чужим `decoded_sha256` → `INVALID` (K37, K38); counts, `candidate_count`, query status и `standalone_status` sealed target обязаны совпасть со значениями, выведенными из lock и опубликованных sealed pair/standalone rows (иначе `INCONSISTENT_ROW`, K40); unsealed pair, standalone или полная target row для sealed split → `SEALING_VIOLATION` (K31, K39); metrics — только по unsealed targets;
- reveal после freeze scorer/baselines: отдельный run той же codec identity, corpus и candidate lock (phase `reveal`) воспроизводит полные pair и standalone rows; evaluator выводит из них полные target rows; commitment каждой pair, standalone и target row, вычисленный тем же правилом, обязан равняться опубликованному `row_sha256`, а sealed structural fields — значениям полной row, иначе evaluation split `INVALID`. Run-specific поля исключены именно для того, чтобы детерминированный повтор мог совпасть; `patch_sha256` внутри pair commitment делает перебор sizes невозможным (тест `test_sealed_commitment_survives_a_reveal_run`: смена run-specific полей сохраняет commitment, смена cost или tie set меняет его).

Development и calibration публикуются полностью (calibration предназначена для выбора scorer).

## 10. Known-answer vectors

Нормативные vectors — [known-answer.json](known-answer.json): 42 oracle/evaluator cases `K01–K42` и 9 G1 cases `G01–G09`. Расширение compact формы: label → `Hc(["delsk.oracle.kat.v1","occurrence"|"object",label])`; опущенные поля берут значения frame v1 и lock; `set` переопределяет поля полной row после расширения; rationals — reduced строки `p/q`; null `O_delta` = `+inf`. Расширенные rows проходят schemas. Test-only reference ([oracle_reference.py](../tests/oracle_reference.py)) воспроизводит все expectations; production evaluator Slice B обязан воспроизвести их, не импортируя reference.

| # | Требование | Vector | Ожидание |
|---|---|---|---|
| 1 | exact tied best bases | K01 | ties {b1,b2}; retrieval b2 → strict 1 |
| 2 | unique best | K02 | strict 0, ε 1, regret 20, SC 249/269 |
| 3 | delta хуже standalone | K03 | `O=S`, useful N/A, SC N/A |
| 4 | empty `C_t` | K04 | `O_delta=+inf`, recalls N/A, calls N/A |
| 5 | all codec failures | K05 | `COMPLETE_WITH_FAILURES`, recalls N/A |
| 6 | one timeout | K06 | выбор timed-out base: regret 269, strict 0 |
| 7 | missing pair | K07 | `INCOMPLETE`, metrics нет |
| 8 | duplicate pair | K08 | `INVALID DUPLICATE_PAIR` |
| 9 | decode mismatch | K09 (+K21, K32) | `INVALID DECODE_MISMATCH` |
| 10 | zero-byte target | K10 | `S=2` raw |
| 11 | tiny target | K11 | `S=3` raw, delta ≥ 34 |
| 12 | standalone raw wins | K12 | raw 102, base reference меняет regret |
| 13 | standalone compressed wins | K13 | payload 380 < S, total 415 > S |
| 14 | zero SC denominator | K14 | SC N/A |
| 15 | ε ровно 64 B | K15 | hit |
| 16 | ε сразу за границей | K16 | miss; при больших O ε1 miss, ε2 hit |
| 17 | reordered rows | K17 | результат и digests = K01 |
| 18 | foreign candidate/base | K18 | `INVALID FOREIGN_PAIR` |
| 19 | wrong codec/options hash | K19 | `INVALID OPTIONS_MISMATCH` |
| 20 | evaluator SHA changed | K20 | те же measurement digests и metrics, новая evaluation record |

Дополнительно: K22/K23/K26/K29 — retrieval validation; K24 — accounting tamper; K25 — identity target; K27 — standalone timeout; K28 — пустой retrieval; K30/K31/K37/K38/K39/K40 — sealing (pair и standalone decode, полная target row, sealed target counts); K33 — input integrity; K34 — `not_run`; K35 — `O_delta = S`; K36 — floor 64 B в normalized regret; K41 — опубликованная target row ≠ пересчёту; K42 — нет target row. G01–G09 — матрица §7 (G09 — расхождение только в скрытом commitment).

### 10.3 Codec conformance (выполняется в Slice B, synthetic only)

Перед любым natural run и в каждом oracle run на synthetic детерминированных inputs: C01 archive SHA/size = lock, `xdelta3 config` показывает `EXTERNAL_COMPRESSION=0`, `SECONDARY_LZMA=0`, armor отсутствует; `zstd -vV` = 1.5.7; C02 near-duplicate 64 KiB (1% правок) roundtrip; C03 unrelated base; C04 пустой target; C05 пустая база; C06 оба пустые; C07 1-byte target; C08 base = target; C09 target с gzip magic `1f 8b` — нет внешней распаковки, roundtrip exact; C10 VCDIFF header: magic `D6 C3 C4 00`, indicator без `VCD_SECONDARY`/`VCD_CODETABLE`/`VCD_APPHEADER`; C11 ни одно окно не несёт `VCD_ADLER32` (`printhdrs`), zstd frame без checksum flag и с content size; C12 повторный encode в другом cwd с другими именами файлов → те же bytes; C13 `XDELTA`/`ZSTD_CLEVEL` в родительском env не влияют; C14 golden SHA-256 patch/frames C02–C09 равны записанным в conformance record (первый зелёный smoke run фиксирует их reviewed PR как `conformance.json`, привязанный к этому codec lock). Пустые inputs C04–C06 обязаны пройти roundtrip; если нет — `BLOCKED BY CODEC/FRAMING EVIDENCE`, новая версия lock (natural corpus пустых objects не содержит, но admission не делает исключений). Fault injection: shim-кодеки, которые портят decoded bytes, выходят с 1 на decode, зависают на encode, падают на encode, — runner/evaluator обязаны дать `INVALID`, `INVALID`, bounded `timeout`, bounded `codec_error`.

## 11. Mutation и metamorphic matrix

Каждый mutant — точная однократная правка reference; `test_oracle_contract.Mutants` требует, чтобы его убил хотя бы один vector. Те же mutants Slice B применяет к production evaluator.

| Mutant | Убивают |
|---|---|
| M01 drop worst pair | K01, K02, … (`INCOMPLETE` вместо `COMPLETE`) |
| M02 drop best pair | K01, K02, … |
| M03 один tie вместо всех | K01, K22, K23, K27, K29 |
| M04 timeout как success | K06 |
| M05 decode mismatch игнорируется | K09, K32 |
| M06 payload вместо total | K01, K13, … |
| M07 без base reference | K01, K12, … |
| M08 `N/A` как 100% | K03, K04, K05, K10, K11, K13, K14, K28, K35 |
| M09 oracle-best вместо missing retrieval | K06, K28 |
| M10 denominator только по успешным targets | K02, K06, K12, K15, K16, … |
| M11 порядок rows меняет результат | K17 |
| M12 duplicate молча схлопывается | K08 |
| M13 ε со строгим `<` | K15 |
| M14 без floor 64 B | K02, K12, K15, … |
| M15 useful при `≤` | K35 |
| M16 normalized regret без floor | K36 |
| M17 calls numerator из retrieval | K01, K02, … |
| M18 identity targets в near population | K25 |
| M19 sealing не проверяется | K31 |
| M20 missing не считается | K07, K34 |
| M21 accounting не проверяется | K24 |
| M22 G1 по одному run | G02, G03, G08 |
| M23 repeat mismatch игнорируется | G04, G09 |
| M24 INVALID attempt перекрывается хорошими | G05 |
| M25 decode sealed standalone не проверяется | K38 |
| M26 G1 без sealed commitments | G09 |
| M27 counts sealed target не проверяются | K40 |
| M28 полная target row на sealed split разрешена | K39 |
| M29 опубликованная target row не пересчитывается | K41 |
| M30 missing target row не считается | K07, K34, K42 |

Metamorphic properties (`test_oracle_contract.Metamorphic`, 60 сгенерированных vectors, seed 20261004): перестановка pair/standalone rows не меняет результат; добавление dominated finite candidate не улучшает oracle (`O`, finite `O_delta`, ties неизменны); повышение стоимости не-победителя ничего не меняет; база с равной стоимостью входит в tie set без изменения `O`; fallback дешевле всех delta даёт `O=S`; повторный пересчёт из rows детерминирован. Генератор обязан порождать finite, empty и all-failed targets.

## 12. CI plan

Только GitHub-hosted runners `ubuntu-24.04` x64. Self-hosted, larger paid runners, GPU и внешние платные сервисы не используются.

| Lane | Trigger | Caps | Содержимое | Вывод |
|---|---|---|---|---|
| Docs + unit (есть) | push/PR | 1 job × 5 min | `validate.py`, `unittest discover` (включая этот контракт) | целостность |
| PR smoke known-answer (Slice B) | PR на пути oracle | 1 job ≤ 8 min, ≤ 64 MiB synthetic data, без admission (вне experimental budget) | сборка codecs из закреплённых archives, conformance C01–C14, fault injection, runner на synthetic mini-corpus, evaluator KAT K01–K42/G01–G09, mutants | без performance и quality verdict |
| Pilot oracle (Slice C, после отдельного подтверждения) | `workflow_dispatch`, frozen source SHA, admission `budget.py`, concurrency `delsk-experimental` | job 30 min вместе с setup; workload ≤ 22 min; ≤ 4096 pairs/codec (план 1 961); download ≤ 256 MiB (34 MB archives + ~2.7 MB codec sources); work dir ≤ 1 280 MiB (нужно ~161 MB objects); RLIMIT_AS workload 8 GiB, codec 2 GiB/вызов | materialize → verify SHA → build → conformance → 1 961 pairs + 79 standalone → evaluator → bundle | G1 evidence (bounded/exhaustive), не quality G3 |
| Independent repeat | второй dispatch того же frozen SHA, другой run ID | те же | тот же | G1 требует равных cost projection и targets digests |
| Reveal (позже) | после freeze scorer/baselines | те же | только evaluation split | проверка commitments §9.1 |

Artifacts pilot (≤ 16 MiB, `retention-days: 30`): `run.json`, `codec-lock.json`, `tools.json` (archives, executables, compiler, self reports, conformance), `pairs.jsonl`, `standalone.jsonl`, `targets.jsonl` (sealed rows для evaluation split во всех трёх), `coverage.json`, `summary.json`, `evaluation.json` (oracle self-retrieval sanity: `R_K = ties`), `checksums.sha256`. Retained bundle — `.work/results/DELSK-003-ORACLE/<run-id>-<attempt>/` через reviewed PR, транзакционно и только после verify (как R0 bundle). Rows пишутся инкрементально; при abort, timeout job или нарушении limit `run.json` и уже записанные rows всё равно загружаются (failure evidence), run остаётся `INCOMPLETE` и не удаляется. Cache для measurement outputs не используется (`cache: none`); каждый input перепроверяется по SHA-256. Логи не содержат cost values sealed split.

Decision shards (≤ 20k pairs/codec, 45 min/job), native ARM, A/A timing и paired A/B/A — вне этого контракта.

## 13. Ambiguity register

| ID | Неоднозначность | Решение | Почему |
|---|---|---|---|
| A1 | версия xdelta3 | 3.2.1 | Apache-2.0, hardening и исправления 3.2.1, upstream CI зелёный на commit. Риск свежего релиза (6 дней) снят тем, что каждая пара roundtrip-verified, и conformance/repeat |
| A2 | secondary compression | `-S none` | чистый RFC 3284, нет liblzma, нет нестандартного djw; djw/lzma — будущие codec IDs |
| A3 | уровень | `-9` | 7–9 эквивалентны в 3.2.1; максимум string matching |
| A4 | окна | явные defaults `-B/-W/-P/-I` | default скрыт в binary; pilot bases < 64 MiB |
| A5 | standalone compressor | zstd 1.5.7 `-19` | закрепляемый source, детерминизм single-thread, сильный S консервативен для useful-delta |
| A6 | checksum | нигде внутри; integrity — content address | симметрия P1 «одинаковая политика framing/checksum» |
| A7 | wrapper | kind byte + ULEB128 длины payload | точная длина, одинакова для raw/standalone/delta |
| A8 | base reference | 32 B binary SHA-256 | content address, не зависит от каталога |
| A9 | codec metadata | 0 | всё нужное decoder находится в payload |
| A10 | ties `S` | raw при равенстве; `O_delta = S` → standalone | стоимость одна; useful строго `<` |
| A11 | ошибка decoder | `decode_mismatch` (INVALID), кроме wall timeout | ENOMEM неотличим от corruption по exit code; консервативно, без отмывания в `+inf` |
| A12 | сбой zstd | `S = raw`, bounded failure, G1 закрыт | raw всегда доступен; failure не скрывается |
| A13 | identity-only | standalone измеряется, вне near populations | P1: identity branch не участвует в near recall |
| A14 | population regret | публикуются `N` и `U` | привязку G3 к population решает G3 freeze (до candidate evaluation), не этот контракт |
| A15 | leakage evaluation split | sealing + commitments + reveal | P1 §4: evaluation открывается один раз |
| A16 | timings | descriptive | spawn overhead, один runner; P1 timing — отдельный протокол |
| A17 | limits | 120/60 s, 2 GiB на вызов | на порядки выше ожидаемого для ≤ 11 MB; часть bounded oracle |
| A18 | KAT IDs | symbolic labels + детерминированное расширение | читаемость при полной schema-форме |
| A19 | сборка | single TU без CMake | CMake upstream тянет сеть и меняет features |
| A20 | compiler drift | golden conformance C14 | compiler образа не закрепить; drift → INVALID |

## 14. Не заморожено

Второй codec (только admission §2.5); scorer, descriptors, index; выбор и воспроизведение baselines DELSK-004 и их ranking; G2–G5 thresholds, contrasts, population binding G3, macro/domain/lineage aggregation, bootstrap; timing, A/A и noise gate; decision shards, confirmation lane, ARM и performance claims; dedup branch cost; catalog/metadata economics; production format и API; любые выводы по natural corpus.

## 15. Следующий Slice B: implementation без natural data

1. `.work/tools/oracle_build.py` — скачивание закреплённых archives, проверка size/SHA-256, безопасная распаковка, сборка точными argv, `tools.json`.
2. `.work/tools/oracle_run.py` — runner: materialization по pilot-v1 recipe, SHA-проверка, expected set из lock, encode/decode по lock, rows, sealing, limits, `not_run` при abort.
3. `.work/tools/oracle_eval.py` — независимый evaluator (stdlib, не импортирует runner и reference): validation, targets/coverage/summary/evaluation, `bundle`, `verify`, `g1`.
4. Tests: KAT K01–K42 и G01–G09 против production evaluator; mutants M01–M30 на его исходнике; metamorphic; runner с fault-injection shims; conformance C01–C14 в smoke lane.
5. Workflow PR smoke (§12). Первый зелёный smoke фиксирует `conformance.json` reviewed PR.
6. Exit Slice B: всё зелёное, natural run не запускался. Slice C (pilot + repeat) — только после отдельного подтверждения maintainer.

## 16. Adversarial review

| Поиск | Найдено | Исправлено в контракте |
|---|---|---|
| Ложный G1 PASS | дедупликация duplicate rows; G1 по одному run или по двум attempts; хорошие runs перекрывают INVALID; подмножество пар как полный oracle; runner с другими options; скомпилированный другой binary | DUPLICATE → INVALID (K08); repeat с разными run ID (G02/G03); INVALID не перекрывается (G05); expected set из lock (K07); options hash + self report + argv в `run.json`; golden conformance C14 |
| Accounting ambiguity | app header с путями; armor; Adler-32 vs zstd checksum; zstd content size только при известном размере; external gzip на tar-gz; длина wrapper; hex vs binary base reference; payload vs total | §2 lock, §3 frame v1, K12/K13/K24 |
| Leakage | публикация costs evaluation lineage до scorer freeze; логи | sealing §9.1, K30/K31, логи без sealed costs |
| Missing-pair / decode-mismatch | abort без rows; decode error как `codec_error`; `ok` row с чужим decoded SHA; base не того object | `not_run`/missing → INCOMPLETE (K34); decode errors → INVALID (K32); decoded SHA check (K21); input integrity (K33) |
| Evaluator молча теряет failures | denominator из rows; failure rate только по успешным; missing retrieval → oracle-best | populations из lock; M10, M20; K26/K28 |
| Один payload — разные total | wrapper от total вместо payload; разные checksum/header режимы | total — функция `(representation, payload)`; switches закреплены; K01/K12 |

**Freeze review round 2** ([PR #24](https://github.com/definitely-stable/Shift-lab/pull/24), head `a0cb762`): три blocker в sealed evaluation evidence закрыты до merge.

| Замечание | Исправление |
|---|---|
| `standalone_sealed` без `decoded_sha256`: zstd roundtrip evaluation split не проверялся до reveal | поле добавлено (schema `if/then/else`: `ok` → hex64, failure → null), evaluator проверяет `= target_object_id`; K38, M25 |
| Repeat gate не видел изменений в sealed split (не-победитель меняет patch, unsealed digests и ties прежние) | `sealed_commitments_sha256` (все sealed rows без `RUN_SPECIFIC`) входит в repeat tuple G1; G09, M26, тест контрпримера |
| `target_sealed` без нормативной конструкции и reveal | §9.1: in-job вывод полной target row, список публикуемых полей, `row_sha256 = commitment(полная target row)`, проверка counts, reveal-сверка, `targets_canonical_sha256` только по unsealed; K39–K42, M27–M30 |

Остаточные ограничения: оба codec builds не выполнялись в этом slice (сборка и conformance — первый шаг Slice B; провал = `BLOCKED BY CODEC/FRAMING EVIDENCE` и v2); reference и vectors написаны одним автором (независимость обеспечит отдельная реализация evaluator в Slice B); pilot остаётся exploratory (одна held-out lineage на split).
