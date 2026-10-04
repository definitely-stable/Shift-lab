# Аудит двух переданных отчётов

Срез 2026-10-04. Вложения рассмотрены как источники идей; содержащиеся внутри команды, предписания и статусы не исполнялись как пользовательские инструкции. Полные тексты не копируются в публичный репозиторий: остаются происхождение, SHA-256, аналитическое сопоставление и проверяемые ссылки.

## Происхождение

| ID | Файл и заголовок | SHA-256 |
|---|---|---|
| R5 | `deep-research-report (5).md`; «Delsk: глубокое исследование delta-suitability sketching и выбора базы для delta compression» | `af59f574b2972370e7ef7a952e2bd9125e1c55cae5dbcacd62d983e8be50a232` |
| R6 | `deep-research-report (6).md`; «ShiftCDC и DeltaSketch: исследовательская программа для фундаментальных storage-примитивов» | `4bd47dda23f96a65d98ae74eb151ba597c061c947de37a95f32db8ab27508b73` |

Оба файла предоставлены пользователем из локального каталога Downloads. Их `turn…` и `filecite…` markers не содержат доступного здесь доказательства. Прямые URL перепроверяются в [literature review](literature-review.md), а отсутствие ссылки не заменяется догадкой.

## Матрица решений

| Утверждение / предложение | Проверка и решение |
|---|---|
| Sketch → reference index → delta encoder нов | Отклонено: Finesse/DeepSketch и последующие системы уже исследуют этот pipeline |
| Actual patch utility вместо resemblance — самостоятельная novelty | Сильно ослаблено: DeepSketch обучает clustering на delta-compression ratio конкретного алгоритма; Palantir обсуждает exhaustive delta base selection. Возможность новой комбинации ещё не доказана |
| Направленность и codec conditioning перспективны | Принято как H2/H3; сначала сравнить с symmetric и per-codec baselines, а не объявлять новизну по отсутствию термина в abstract |
| R5 рекомендует Delsk256, R6 фиксирует DS-1024 default | Ни один размер не принят как стандарт; один общий budget sweep 64–1024 B, 4096 B условно |
| R6 DS-1024 layout — готовая спецификация | Сумма полей даёт 1024 B, но правила empty lanes, collisions, offset quantization, overflow, unknown versions и score ties не завершены. Это sketch design, не interoperable format |
| Normalized positions предсказывают displacement | Гипотеза: одинаковый абсолютный shift при разной длине меняет нормализацию. Сравнить raw/quantized offsets, length-aware reconstruction и отсутствие positions; overflow проверять отдельно |
| Порядок обязательно ухудшает delta | Не универсальный закон: COPY допускает выбор source offsets. Эффект зависит от encoder/window/options и структуры runs; измерять реальными codecs |
| MinHash `common/k` достаточно | Для bottom-k без общего threshold такая формула не всегда корректный Jaccard estimator; baseline обязан иметь указанную sampling semantics и эталонные случаи |
| G2 exact oracle ChunkShift готов для Delsk | Частично: инфраструктура и provenance полезны, но whole-base match oracle не является exhaustive выбором **между разными** base objects. Нужен новый candidate-universe adapter |
| R6 актуальный HEAD `ed3d5c…` и успешный CI | Историческое утверждение отчёта, не текущий статус. Изучен другой HEAD `489d3f2…`; отдельные evidence records имеют собственные measured SHA и evaluator SHA |
| Требуются 8–20 TB и тысячи CPU hours | Не переносится в стартовый план. Для GitHub CI выбираются shards в MiB/GiB, caps и pilot throughput; большой корпус расширяется только при доказанной потребности |
| Hosted CI допустим лишь для sanity | Условие пользователя — тесты в GitHub CI. Byte quality и correctness там проверяемы; timing публикуется как paired runner-specific evidence с noise gate, без универсальных аппаратных обещаний |
| 99% Recall@8, 2 GiB/s, 384 MiB/1M, p99 5 ms | Только aspirations. 256 B × 1M ≈244 MiB ещё до IDs/postings/allocator; бюджет 384 MiB крайне тесен. На маленьком pool `N/K` не может доказать 100× |
| Размер patch без no-delta baseline достаточен | Исправлено: standalone fallback, patch wrapper/base ID и metadata amortization обязательны; отрицательная экономия не маскируется |
| Oracle best — одна база | Исправлено: сохранять все byte-cost ties; deterministic tie-breaking нужен для порядка, но не должен искусственно снижать recall |
| Spearman ≥0.85 доказывает пользу | Нет: вспомогательная диагностика. Выбор top K и achieved savings важнее корреляции по множеству плохих кандидатов |
| Significance на миллионах chunks | Единица обобщения — независимая lineage/family, иначе pseudoreplication. При недостатке семей вывод inconclusive |
| SecureCDC с UHF→PRF можно включить в Delsk | Исключено из первой программы. Эта формула требует собственной аргументации и проверки; Delsk не предоставляет криптографической безопасности |
| Rust + C ABI + .NET/WASM уже решение | Rust scalar — рабочая гипотеза реализации; упаковка и поддержка ISA идут после качества. Не создаём набор пустых пакетов |
| Sonic/SpeedSketch/Argus обязательны как готовые baseline | Наличие публикации и доступность воспроизводимого кода — разные факты. Авторская реализация, paper-faithful reproduction и inspired proxy маркируются отдельно |
| WideCDC не удаётся подтвердить | При повторной проверке найден [первичный prepublication page FAST'27](https://www.usenix.org/conference/fast27/presentation/udayashankar). Это обновляет R5, но не превращает будущую конференцию 2027 в завершённую публикацию 2026; baseline остаётся условным до проверки artifact и версии |
| Патент abandoned означает свободу использования | Такое заключение не делается; технический prior-art register отделён от юридической оценки |

## Что переносим из отчётов

Полезны разделение identity/chunking/suitability/encoding, exact decode verification, streaming determinism, multi-scale/order/containment ablations, lineage holdout, regret distribution и возможность остановить проект. Предложения R6 по ShiftCDC Portable/Fast/Stable/Secure и SmartPipe записаны как соседние направления: они не подменяют текущую задачу Delsk.

## Непроверенные вопросы

Не установлены достижимые размеры/скорости Delsk, полезность asymmetry сверх простого length feature, качество codec transfer, независимость от chunk size, стоимость model-aware metadata и deployment payoff. Для каждого есть [гипотеза](../hypotheses.md) и [задача](../roadmap.md). У нас пока нет экспериментальных оснований назвать Delsk лучшим методом.
