# DELSK-P1: oracle, метрики и решение

Версия `delsk.protocol.v1`, проект протокола от 2026-10-04. Статус **PLANNED**. Он становится `FROZEN` только с привязанными issue, commit, corpus/candidate/scorer/baseline locks и preregistered contrasts. Изменение после evaluation создаёт P2 и новую evaluation split. Никакой результат пока не получен.

## 1. Единица исследования

Отдельные tracks: chunk (4–64 KiB), file (64 KiB–16 MiB), large-object sampled/hierarchical (позже). Нельзя усреднить их и объявить универсальность. Основная независимая единица статистики — lineage (проект/семейство, у model weights — общий ancestor). Внутри неё target/version pairs зависимы.

Для каждого target `t` заранее фиксируется universe `C_t`: уникальные bases, доступные до времени target в deployment track. Exact duplicates target исключаются в отдельную dedup-ветку и учитываются в coverage. Self-match запрещён. Для artificial direction-reversal challenge оба направления допустимы, но результаты не смешиваются с temporal deployment track.

Candidate policy использует время, lineage, size strata и seed, но не score Delsk и не оценённый patch. Нужны related bases, plausible decoys и hard negatives. Selector и все baselines видят один и тот же `C_t`; версия selector не меняет oracle universe. Поиск в полном каталоге `N` нельзя выдавать за exhaustive oracle по `N`, если ground truth проверен только на подмножестве.

## 2. Стоимость и ground truth

Пусть `P_E(b,t)` — реальные bytes encoded patch при фиксированных версии, options и window limits кодера `E`. VCDIFF — формат, а не единственный оптимальный encoder: RFC специально оставляет matching/windowing реализации. Поэтому oracle — лучший результат **этой версии и конфигурации кодера на этом конечном universe**, не математически минимальная delta. [RFC 3284](https://www.rfc-editor.org/info/rfc3284/).

`D_E(b,t) = patch_payload + wrapper + base_reference + required_codec_metadata`.

`S(t) = min(raw representation, standalone lossless-compressed representation)` с одинаковой политикой framing/checksum. Стоимость обязательных decoder dictionaries включается; dictionary reference отдельно от самих bytes, если dictionary уже гарантированно имеется у consumer. В первой фазе chain depth = 1; fetch/storage cost базы публикуется отдельно.

Oracle для каждого target:

```text
for each eligible base b in frozen C_t:
    encode(b, t, frozen codec/options) with fixed timeout/memory cap
    decode(b, patch) and compare length + exact bytes + SHA-256(t)
    record payload bytes, total bytes, status, timings and provenance
O_delta(t) = min D_E(b,t) over all valid bases
O(t) = min(S(t), O_delta(t))
```

Полнота: должны присутствовать **все** пары из lock. Crash/timeout фиксируется как failure; его нельзя просто удалить из denominator. При заранее определённом resource-bounded oracle такое outcome имеет cost `+infinity`, но итог называется bounded oracle и содержит failure rate. Decode mismatch делает run `INVALID`. Для unbounded-quality claims хотя бы одна пропущенная пара делает oracle incomplete и запрещает exact claim.

Если успешных пар с конечной стоимостью нет, `O_delta=+infinity`, множество delta argmin пусто, `O=S`. Strict/ε recall для такого target — `N/A`, не успех по совпадению бесконечностей; all-failure coverage публикуется отдельно. При пустом `C_t` действует та же конвенция без codec failure. Любой success по recall требует конечной стоимости; failure coverage не скрывается за conditional recall. В обычном exhaustive track codec failures не позволяют закрыть G1.

`R_K(t)` — до K разных eligible bases. Missing retrieval не подменяется oracle-best. `A(t) = min(S(t), min D_E(b,t) for b in R_K(t))`; для пустого списка `A=S`. Все выбранные bases действительно кодируются. Вариант «предсказал одну» отдельно называется K=1.

## 3. Метрики

| Метрика | Точное определение и denominator |
|---|---|
| Strict delta Recall@K | доля targets с конечным `O_delta`, где `R_K` пересекается с **всем** множеством argmin `D_E`; ties считаются успехом; all-failure coverage рядом |
| Useful-delta Recall@K | та же метрика только для `O_delta < S`; отдельно указывается число полезных targets |
| ε Recall@K | есть выбранная база с `D_E ≤ O_delta + max(64 B, ε·O_delta)`; ε=1/2/5%; явная 64 B tolerance отличает её от strict |
| Byte regret | `A(t)-O(t)` ≥0, bytes/target |
| Normalized regret | `(A(t)-O(t))/max(O(t),64 B)`; основной p50/p95 и per-domain CDF |
| SavingsCapture | `Σ(S-A)/Σ(S-O)` по указанной population; denominator=0 → `N/A`, не 100% |
| Macro quality | среднее по lineage внутри domain, затем равновесное среднее по domains; рядом pooled/byte-weighted значения |
| Encoder-call reduction | `Σ |C_t| / Σ actual_candidate_encodes`; no-delta policy/extra retries учесть; denominator=0 → `N/A` |
| Retrieval vs rerank | recall oracle base среди top M retrieval, затем среди top K; measured M/K, scanned bytes/postings, caps и их truncation rate |
| Build/search cost | ns, bytes/s, peak RSS, descriptor/index bytes, per-query distribution; build index отдельно от query |
| End-to-end benefit | build descriptors + index + query + K encodes + decode checks; разложение cold setup и amortized reuse, break-even queries |

`N/K` — теоретический верхний ориентир для фиксированного K, не измеренное ускорение. При N=64 и K=8 предел 8×, а не 100×. Публикуется grid `K=1,4,8,16` и фактический effective K. Единицы GiB/s (2^30) и GB/s (10^9) не смешиваются.

Metadata storage: `catalog_delta = total descriptors + postings + IDs + scorer + allocator/container overhead`. Его amortized share прибавляется отдельно к экономике системы. Нельзя вычитать sketch bytes от одного target, забывая каталог; нельзя включать огромный oracle training cost как deployment query latency. Отчёт обязан показать оба lifecycle costs.

`C_t=∅`, пустые targets, exact duplicates, невозможный codec и targets без полезной delta — отдельные строки coverage, не скрытые исключения. Identity-only branch не участвует в near-duplicate recall.

## 4. Разделение данных и подбор параметров

На уровне lineage фиксируются development/calibration/held-out partitions до tuning (ориентир 60/20/20 по числу семей при достаточном наборе). Связанные checkpoints, исходники и их compiled/archived variants принадлежат одной split. По времени базы всегда доступны раньше target. Версии внутри evaluation lineage дают bases, но не участвуют в training scorer.

Для каждого метода одинаковый tuning budget, descriptor budget и доступ к metadata. Scorer выбирается на calibration, затем hash параметров фиксируется. Evaluation открывается один раз для финалиста; последующие решения — новая split/protocol. Baseline reproductions используют published settings и отдельно budget-matched tuning; обе версии сохраняются.

## 5. Статистика и noise

Первичный contrast: выбранный Delsk против сильнейшего воспроизведённого baseline при одинаковых K/bytes. Список дополнительных contrasts предварительно фиксируется; Holm correction применяется к family ablations. Главный критерий — практический эффект и 95% interval, а не только p-value.

Cluster bootstrap: resample lineages (с сохранением всех их targets), stratified by domain, 10,000 draws, фиксированный seed 20261004. Для разницы методов resample те же lineage IDs попарно. Для p95 указать quantile convention (linear/type 7), population/weights; сохранять исходные target-level rows. При меньше 10 независимых held-out lineages на domain вывод exploratory; confirmatory gate не закрывается. Для редких ошибок 99% recall маленький sample не даёт узкий interval — отчёт содержит numerator/denominator и CI.

При all-success/all-zero-error observations обычный bootstrap даёт вырожденный interval и не ограничивает вероятность ненаблюдённой ошибки. Такой interval сам по себе не закрывает 99% recall/FNR gate: необходима заранее обоснованная conservative bound по независимым lineage units с явно указанным estimand, иначе `INCONCLUSIVE`. Exact binomial bound по зависимым chunks недопустим. Увеличение trials в одной lineage не заменяет новые families.

Timing: 2 warm-up rounds, 5 измерительных paired blocks; baseline A → candidate B → baseline A, порядок кандидатов между blocks детерминированно перемешан. Только один измерительный процесс на job. Full repeat в отдельном Actions run для независимого runner allocation. In-job timing samples не превращаются в независимые lineage observations.

Noise gate как начальная policy: если baseline brackets расходятся более чем на 10% в более чем одном из пяти blocks, timing run `INCONCLUSIVE`; raw quality bytes остаются допустимы, если provenance/correctness валидны. Не выбрасывать отдельные медленные blocks. До evaluation pilot проверяет длительность blocks и overhead. Нет обещания закреплённой frequency, эксклюзивного physical core или единой CPU модели на hosted runners.

## 6. Gates и stop/pivot

Это исходные **предлагаемые** thresholds; freeze после baseline pilot, до candidate evaluation. Изменение обосновано в decision log.

| Gate | Условие перехода |
|---|---|
| G0 evidence | доступные первичные источники, claim matrix, лицензии и честная baseline availability |
| G1 oracle | frozen lineage/candidate locks; 100% expected pair accounting; decode equality; valid fallback; воспроизводимый evaluator |
| G2 signal | сравнение с size/recency/MinHash/Finesse и минимум одним доступным современным методом; candidate даёт измеримый headroom на calibration |
| G3 held-out quality | SavingsCapture ≥0.98 в каждом заявленном byte-oriented domain, p50 regret ≤1%, p95 ≤5%; 95% CI публикуются, недостаточная точность → inconclusive |
| G4 comparative effect | ≥20% relative p95-regret reduction при положительном baseline p95 **или** ≥1.5× paired search speed при SavingsCapture noninferiority margin 0.5 pp; CI для эффекта исключает отсутствие улучшения; ни один domain не теряет >2 pp Useful Recall@8 |
| G5 system | end-to-end benefit после amortization, bounded memory, adversarial fallback, tested deterministic backends, repeat decision run; чётко указанные coverage/limits |

Absolute gates G3 дополнительно требуют point estimate и confidence bounds в пользу заявленного threshold (для минимального savings — lower bound, для максимального regret — upper bound); иначе verdict `INCONCLUSIVE`, не pass. При нулевом baseline p95 relative reduction не определён: использовать bytes regret как заранее зарегистрированный secondary endpoint, не заменять gate постфактум.

Для speed branch G4 quality noninferiority проверяется отдельно: lower 95% CI bound парной разницы `SavingsCapture(candidate)−SavingsCapture(baseline)` ≥−0.005 в каждом заявленном domain; для Useful Recall@8 нижняя граница разницы ≥−0.02. Speedup CI не заменяет эти условия. Interval timing учитывает blocks внутри run и независимые runner allocations между runs; двух allocations недостаточно для широких hardware claims, и при неустойчивой оценке вывод остаётся описательным/inconclusive.

Recall 99/97%, 100× encode reduction, 2 GiB/s AVX2, 1 GiB/s NEON, 1M index/p99≤5ms и ≤384MiB из R5 — **stretch targets**, не критерии закрытия документации и не обязательные ограничения первой CI фазы. Масштаб 1M относится к index benchmark; он не доказывает 1M exhaustive base oracle.

Stop: G1 невалиден → исправлять измерение. G2 не показывает выигрыш даже у 512/1024 B после замороженного tuning budget → сохранить negative evidence и pivot к простому selector. Выигрыш только в одном domain/codec → сузить claims/profile. Отсутствие достаточных lineages или доступного contemporary baseline → inconclusive/limited scope, без заявления SOTA. Production/public format — только после G5.
