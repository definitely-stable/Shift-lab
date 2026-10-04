# GitHub Actions: план лаборатории

Все correctness tests, benchmark pilots и decision measurements выполняются в GitHub Actions. Локально допустима подготовка документов/кода и чтение результатов; она не даёт decision evidence. Никакие платные runners или дополнительные сервисы не нужны для начальной программы.

## Что реализовано сейчас

`.github/workflows/research-docs.yml` запускает `.work/tools/validate.py`: проверка локальных Markdown-ссылок, обязательных документов, уникальности IDs, связности backlog, dependency cycles и непереносимых citation markers. Это **проверка исследовательского пакета**, не benchmark Delsk. Все tiers ниже, кроме docs check, — задания DELSK-005 и последующих issues.

## Tiers и caps

| Tier | Trigger и runner | Hard cap | Содержимое / право делать вывод |
|---|---|---|---|
| Docs (готов) | push/PR/dispatch, ubuntu-24.04 | 1 job ×5 min | целостность пакета |
| PR smoke (план) | PR, x64 | ≤8 min; ≤64 MiB corpus | fixtures/decoder/metric known answers; synthetic diagnostics, без performance verdict |
| Pilot (план) | workflow_dispatch, x64 | ≤30 min; download≤256MiB; materialized≤1GiB; 4096 pairs/codec | стоимость oracle, noise A/A, baseline calibration; не финальное качество |
| Decision shard (план) | workflow_dispatch, frozen source SHA, x64+native arm64 | 2×45min + summary≤5min =95 runner-min; ≤2GiB materialized/job; ≤20k pairs/codec/job | natural held-out quality и platform-scoped timing |
| Confirmation (план) | отдельный dispatch того же lock | ещё ≤95 runner-min | независимое выделение runner, оба runs сохраняются |
| Portability/fuzz (план) | dispatch; x64, arm64; WASM на x64 | ≤20 min/platform; bounded input size | только выполненные backends получают supported статус |

Time cap включает setup/build/download, а не только core loop. Initial policy ≤600 runner-min/week на экспериментальные dispatch; 2 одновременных измерительных jobs, `strategy.max-parallel: 2`, `fail-fast: false`, `contents: read`. Контроль бюджета реализует DELSK-005 по API run/job durations и reservation перед dispatch; таблица сама лимит не обеспечивает. PR workflows имеют отдельный short cap и concurrency cancellation.

Не предполагается 100% доступность Actions или фиксированная CPU ISA. Runner labels фиксируются `ubuntu-24.04`/`ubuntu-24.04-arm`; image revision и CPU записываются при запуске. Доступность ARM64 проверяется в pilot. AVX-512 отсутствие → `UNSUPPORTED`, не скрытый scalar timing. Запуск эмуляции проверяет semantics, но не скорость native target.

Официальные спецификации стандартных public runners и правила оплаты/retention проверены в [lab practices](research/lab-practices.md). Free public standard compute не означает безграничный диск/параллелизм/хранение и не распространяется автоматически на larger runners. 600 минут — собственная policy, не тариф GitHub.

## Выполнение и воспроизводимость

1. Freeze protocol/corpus/candidate list/codec locks и planned pair counts в issue до запуска. Dispatch использует этот commit, а не подвижный `main` без привязки.
2. Проверить source/workflow SHA и отсутствие неизвестных inputs; передавать dispatch values через env с allowlist, не интерполировать как shell code. Cache ускоряет acquisition/build, но каждый cached input снова проверяется по hash.
3. Проверить доступный диск и RAM до materialization; extraction запрещает traversal/symlinks вне workspace и имеет expanded-size cap. Крупные sources обрабатываются по shards. Corpus fetch и compilation исключаются из measured timing, но входят в budget.
4. Записать compiler/runtime versions, executable hashes, dependency locks, exact commands, CPU/ISA, image/OS/kernel, process/thread count. Если frequency/perf counters недоступны, писать `unavailable`, а не нули.
5. A/A calibration и paired A/B/A по [DELSK-P1](protocol.md), warm/cold отдельно, raw rounds сохраняются. Hosted runner speed нельзя сравнивать с опубликованными paper numbers как apples-to-apples speedup.
6. Все expected pairs получают строки результата, включая skipped/failed; correctness mismatch запрещает gate. Re-run attempt сохраняется с attempt number; independent confirmation — новый run ID.
7. Summary загружает shards по run/source/lock identities; несовместимые shards не агрегируются. В metadata отдельно measured source SHA и evaluator SHA.
8. До expiry сохранять compact per-target/per-pair metrics, manifest hashes, summary inputs, evaluator и artifact inventory в `.work/results/<experiment>/<run-id>/`. Большие payloads не попадают в git. Для независимого полного replay нужны recipe+источники/доступные лицензированные snapshots; компактная evidence подтверждает только пересчёт verdict из retained metrics.

## Evidence bundle v1

Обязательные файлы будущего run: `run.json`, `corpus-lock.json`, `candidate-lock.json`, `tools.json`, `pairs.jsonl`, `targets.jsonl`, `timings.jsonl`, `coverage.json`, `summary.json`, `verdict.json`, `checksums.sha256`. `run.json` включает experiment/protocol ID, source+workflow+evaluator SHA, GitHub run/attempt/URL, timestamps, seeds, runner label/image, CPU/ISA/runtime/compiler, limits и actual duration.

`pairs.jsonl`: target/base IDs, codec/options hash, status, payload/total bytes, decoded SHA, encode/decode wall ns, memory method, error class. `targets.jsonl`: candidate universe hash/N, descriptor/scorer/index versions, R_K IDs, oracle tie IDs, S/O/A costs, useful flag и exclusions. `timings.jsonl`: block/order/phase, A-before/B/A-after raw values, warmup flag, cache mode. Secrets/credentials и исходные private payloads в evidence не записываются.

Artifacts содержат source/experiment/run/attempt в имени, `retention-days: 30` pilot и `90` decision при разрешённой repository policy. С 2026-10-01 официальная политика retention охватывает также run/check/status history; URL в issue не заменяет durable evidence. [GitHub retention](https://docs.github.com/en/organizations/managing-organization-settings/configuring-the-retention-period-for-github-actions-artifacts-and-logs-in-your-organization).

## Ограничения доказательств

Зелёный workflow проверяет выполненные assertions. Он не доказывает novelty, отсутствие дефектов, универсальную производительность или G3 на неподключённых domains. Отсутствующий artifact, истёкший run, license-blocked dataset и недоступный baseline описываются явно. Для decision effect, превосходящего noise, допускаются runner-specific выводы; для физического throughput SOTA нет основания без сопоставимых условий.
