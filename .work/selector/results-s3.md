# S3: результаты (run 37458783363)

Run [37458783363](https://github.com/definitely-stable/Shift-lab/actions/runs/37458783363), attempt 1, `selector-s3.yml`, source и workflow `906dc0adc8b43545baa633876d4a2bb69998c962` (merge PR [#50](https://github.com/definitely-stable/Shift-lab/pull/50), где правило было зафиксировано до прогона). Artifact digest — `sha256:276c4388dbce3f2959f73e3ea684bbf158a01cfb7520149c7b8ef1f9b0c6f801`, совпадает с тем, что сообщает GitHub. Retained файлы: [`.work/results/SELECTOR-S3/37458783363-1/`](../results/SELECTOR-S3/37458783363-1/), их SHA-256 — в [`37458783363-1.sha256`](../results/SELECTOR-S3/37458783363-1.sha256). Правило — [s3.md](s3.md).

**Verdict по preregistered rule: уровень `L = 0` — отказ от кодирования не вводится.** Ни один уровень `L ≥ 1` не проходит оба порога: потеря экономии ≤ 0.5 % и FN ≤ 1 %. Selector v1 остаётся без изменений: кодирует до K баз всегда, standalone — fallback.

## Проверки

- `abstention.json` пересчитывается из retained `features.jsonl` байт в байт (`simple_selector.py abstention`).
- Пересобранный X0 store дал те же queries `C_t`, что retained run 37449333091 (проверка в workflow).
- Population: 119 natural targets (pilot-v1 dev/cal 55, X0 64), из них 93 useful-delta, 236 вызовов кодера при K = 2. Adversarial: 8 random и 8 zlib.

## Уровни

| L | Сэкономлено вызовов | Отказ useful-delta | Потеряно экономии | Проходит пороги |
|---|---|---|---|---|
| 0 | 0 | 0 | 0 | да (выбран) |
| 1 | 4.7 % | 5 из 93 (5.4 %) | 0.59 % | нет: FN и потеря |
| 2 | 6.4 % | 7 (7.5 %) | 0.93 % | нет |
| 3 | 7.2 % | 8 (8.6 %) | 0.94 % | нет |
| 4 | 8.1 % | 9 (9.7 %) | 2.25 % | нет |

## Почему отказ не работает

1. **Почти все бесполезные targets имеют metadata-кандидата.** Delta не окупается у 26 natural targets. У 25 из них есть база с тем же путём и линией, а правило по построению их не трогает: такая база дешёвая и обычно полезна. Вызовы на бесполезных targets — 52 из 236 (22 %), но почти все они на этой стороне.
2. **Нулевое сходство descriptor не значит «delta бесполезна».** При `L = 1` отказ получают 5 useful targets. Все они — `tar-gz` треки pilot-v1: gzip-потоки архивов без пути, где 8 минимальных хэшей не совпадают ни с одной базой. Delta при этом всё же даёт 0.4–4.9 % экономии.
3. **Adversarial цели сигнал отличает, но не отделяет.** У всех 8 random и 8 zlib целей `best_shared = 0`, и при `L ≥ 1` они получили бы отказ. Но `best_shared = 0` бывает и у реальных сжатых архивов с полезной delta. Пороговое правило по 64 B descriptor не разделяет эти случаи.

## Что дальше

- Для S4 (ChunkShift) selector используется как есть: K = 2 без отказа. Если CPU кодера станет узким местом, нужен другой сигнал, а не порог по descriptor: например, дешёвый пробный encode префикса или признак «вход уже сжат». Это отдельная гипотеза с новой preregistration.
- Ограничения: in-sample, 119 targets из 18 families; сжатые данные представлены только треками `tar-gz` pilot-v1.
