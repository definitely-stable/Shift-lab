# DELSK-003 Slice B: production oracle на synthetic data

| Элемент | Статус |
|---|---|
| Slice A `delsk.oracle-contract.v1` | **FROZEN** (файлы [freeze.json](freeze.json) не менялись) |
| Slice B | **IMPLEMENTED / CONFORMANCE PASS** |
| Natural oracle (1 961 pairs) | **NOT_RUN** |
| G1 | **NOT_RUN** (не пройден; synthetic runs G1 не дают) |

Реализация [contract §15](contract.md#15-следующий-slice-b-implementation-без-natural-data). Все измерения — GitHub Actions `ubuntu-24.04`, только synthetic data; ни один natural patch cost не вычислялся.

## Код

| Файл | Назначение |
|---|---|
| [oracle_build.py](../tools/oracle_build.py) | Скачивание закреплённых archives (https release asset репозитория и tag из lock, cap = locked size), проверка размера и SHA-256, распаковка в памяти без traversal/дубликатов/второго root, только regular files (links и special members пропускаются и записываются), точные build argv и environment lock, `tools.json`: archive/executable SHA-256, compiler и make identity, argv, env, self report, source/workflow SHA |
| [oracle_run.py](../tools/oracle_run.py) | Conformance C01–C14, synthetic smoke corpus, runner: expected set из candidate lock в canonical order, проверка SHA-256 и длины каждого input перед каждым вызовом, вызов абсолютного проверенного executable в свежем каталоге с `LC_ALL=C`, stdin `/dev/null`, `RLIMIT_AS`, `RLIMIT_FSIZE`, SIGKILL process group по timeout и после каждого вызова, peak RSS из `wait4`; full rows в private каталог с fsync на row; abort/SIGTERM/workload limit превращают невыполненные задачи в `not_run`; pessimistic `run.json` пишется до первого вызова |
| [oracle_eval.py](../tools/oracle_eval.py) | Независимый evaluator (stdlib, не импортирует runner и reference): closed schemas, canonical JSON/JSONL, universe из locks, validation, targets, coverage, summary, evaluation (self-retrieval sanity), sealing evaluation split, `finalize`, `verify`, транзакционный `bundle`, `g1` |
| [conformance.json](conformance.json) | Golden SHA-256 patch/frame C02–C09 (C14), привязанные к codec lock и synthetic inputs |
| [oracle-smoke.yml](../../.github/workflows/oracle-smoke.yml) | PR smoke: один job ≤ 8 min, сборка codecs, conformance, synthetic mini-run → finalize → verify → bundle, все oracle tests |

Phase `smoke` принимает только synthetic locks и отказывает на natural `C_t`; phase `pilot` требует frozen natural locks, conformance PASS и `workflow_dispatch`. Workflow pilot (Slice C) не добавлен: natural run только после отдельного подтверждения maintainer.

## Evidence

- Первый smoke [run 37224572612](https://github.com/definitely-stable/Shift-lab/actions/runs/37224572612): обе сборки, C01–C13 PASS на собранных xdelta3 3.2.1 и zstd 1.5.7 (включая пустые inputs C04–C06), C14 `CANDIDATE` (golden ещё не закреплён). Его candidate после проверки закреплён как [conformance.json](conformance.json): inputs воспроизводятся на другой платформе и Python, bundle этого run повторно verified evaluator локально.
- С закреплённым golden: smoke [run 37224987102](https://github.com/definitely-stable/Shift-lab/actions/runs/37224987102) на `b1e854c` — C01–C14 PASS, verdict PASS, 82 oracle tests OK (0 skipped, включая pinned codecs), job 1 min 34 s.
- С закреплённым golden C14 сравнивает точные digests; расхождение (например, другой compiler) — `FAIL`, run не получает conformance PASS (contract A20).
- Synthetic mini-run (11 queries, 14 pairs, все три split, evaluation sealed): `COMPLETE`, `exhaustive`, verify и bundle зелёные.
- Production evaluator воспроизводит K01–K42 и G01–G09 без reference; compact vectors раскрываются независимо и сверяются с reference построчно.
- Mutants M01–M30 и production P01–P07 применяются к исходнику `oracle_eval.py` и все убиты.
- Fault injection (shim codecs): decode corruption, decoder exit, malformed patch → `INVALID DECODE_MISMATCH`; encoder exit → bounded `codec_error`; encode/decode timeout → bounded `timeout`, потомки убиты; allocation failure и file cap → `resource_limit`; неверный SHA input и symlink в store → `INVALID INPUT_INTEGRITY`; foreign/duplicate/missing pair → `INVALID`/`INCOMPLETE`; SIGTERM и SIGKILL → `not_run`/missing, `INCOMPLETE`, bundle verifiable.
- Leakage: sealed costs, patch/frame SHA и sizes evaluation split отсутствуют в artifact, stdout/stderr и step summary.

## Gates после review PR #25

- **Pilot gate.** Runner принимает conformance record только closed (C01–C14, `{status, detail}`, executables по ролям, verdict = checks, PASS = committed golden и inputs). Для `pilot` он дополнительно заново выполняет C01–C14 на тех же executables и требует byte-equal PASS record до первого natural вызова; поддельный record отклоняется до любого codec call.
- **Build provenance.** `tools.json` каждой роли обязан равняться recipe codec lock: archive URL/size/SHA-256/root/path, build argv, cwd, env и путь executable; runner и verifier проверяют это независимо.
- **Evaluator identity.** Builder пишет code manifest (`oracle_build.py`, `oracle_run.py`, `oracle_eval.py`, `manifests.py`, `materialize.py`); `oracle_code_sha256 = Hc(manifest)` входит в measurement identity каждой row. `finalize` работает только с evaluator этого manifest, а `verify` берёт `evaluator_sha256` и `evaluator_source_sha` из manifest и measured commit, не из проверяемых `evaluation.json`/`summary.json`.
- **G1 по всем attempts.** `oracle_eval.py g1 IDENTITY [RESULTS_DIR]` сам перечисляет все bundles в results root и сверяет их с durable ledger `attempts.json` (`delsk.oracle.attempts.v1`: `measurement_identity_sha256`, `run_id`, `run_attempt` каждого dispatched attempt, ведётся reviewed PR). Список bundles передать нельзя; dispatched attempt без retained bundle блокирует PASS (`ATTEMPT_NOT_RETAINED`), retained bundle вне ledger останавливает verdict. Ledger создаёт Slice C вместе с первым pilot dispatch.

## Ограничения

- Процессы codec ограничены process group; codec, который сам вызывает `setsid()`, вышел бы из group (собранные codecs этого не делают; изоляция cgroup — upgrade path).
- `RLIMIT_AS` распознаётся по тексту ошибки allocation; codec, падающий по signal на NULL, записывается как `codec_error/signal` — оба bounded `+inf`.
- Natural materialization в object store для pilot (адаптер к pilot-v1 recipe) — часть Slice C: в этом slice natural payloads не скачивались.
- Smoke conformance и mini-run подтверждают корректность на synthetic inputs, не качество oracle и не G1.
