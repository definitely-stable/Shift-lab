# Prior art update для DELSK-004/006 (2026-10)

Дата: **2026-10-05**. Статус: literature/engineering mapping. Ничего не реализовано, не собрано и не запущено. Дополняет [literature-review.md](literature-review.md), [claim-matrix.md](claim-matrix.md) и [baseline-availability.json](baseline-availability.json); их выводы не пересматриваются. Цель — после G1 не начинать DELSK-004 с устаревшего baseline.

Уровни: **P** — первичный текст/официальная страница просмотрены (в этом или предыдущем срезе); **M** — библиография проверена, содержание не перечитано в этом срезе; **U** — не проверено. Авторские цифры не воспроизведены.

## 1. Что изменилось с 2026-10-04

| Находка | Почему важно для Delsk | Ур. |
|---|---|---|
| Git 2.49: `--name-hash-version=2` для `pack-objects`/`repack` и path-walk **API**, используемый `git backfill` ([GitHub blog 2.49](https://github.blog/open-source/git/highlights-from-git-2-49/)). Git 2.51: опция `--path-walk` для `pack-objects`/`repack` ([GitHub blog 2.51](https://github.blog/open-source/git/highlights-from-git-2-51/)) | крупнейший развёрнутый «selector» delta-баз: эвристики пути/размера + окно. Пример name-hash v2 из поста 2.49: repack `microsoft/fluentui` 439 → 160 MiB. По посту 2.51, `--path-walk` часто даёт packs меньше, чем name-hash v2. Это сильный дешёвый engineering baseline, а не sketch | P |
| FED (arXiv 2501.01046, 2025), LSHBloom (arXiv 2411.04257) | MinHash-LSH в масштабе LLM dedup: переиспользуемые хэши на GPU; LSH-индекс на Bloom filters. Авторские claims LSHBloom различаются между версиями preprint: abstract v1 (2024-11-06) — на peS2o на 270% быстрее MinhashLSH и 0.6% его disk space, при экстраполяции на миллиарды документов — 250% speedup и 54× по месту; abstract v4 (2026-01-27) — на peS2o 12× быстрее и 18× меньше диска, преимущество сохраняется при экстраполяции. Версии не смешивать, ссылаться с номером версии. Для Delsk — индексная часть DELSK-008, не scorer | P (abstract v1, v4) |
| *Sampling-Based Estimation of Jaccard Containment and Similarity*, arXiv 2507.10019 (2025) | поправка MinHash при выборочных входах и анализ ошибки containment; прямо относится к направленности H2 | P (abstract) |
| Chunk2vec, IET Communications 2024, DOI 10.1049/cmu2.12719 | Sentence-BERT embeddings для resemblance detection. Практическая ценность для CPU-only P1 сомнительна; пункт claim review, не baseline | P (abstract) |
| Argus (TOS 22(1), 2026), FastDelta (EuroSys 2026), Sonic (Computers 15(9), 2026), DCLC (2026) | уже в literature review; новых artifacts не найдено | P |

## 2. Карта семейств методов

| Семейство | Ключевые работы | Что даёт для `C_t`-ranking | Роль в DELSK-004 | Ур. |
|---|---|---|---|---|
| Size / recency / lineage order | git pack heuristics; Git 2.49 name-hash v2; Git 2.51 `pack-objects --path-walk` | бесплатный ranking; при версионных lineages часто доминирует | **обязательный baseline** (size-closest, previous version, git-like window) | P |
| MinHash и плотные варианты | Broder 1997; b-bit MinHash (Li & König, WWW 2010); one-permutation hashing (Li, Owen, Zhang, NIPS 2012) и densification (Shrivastava & Li, ICML 2014; Shrivastava, ICML 2017); C-MinHash (Li & Li, ICML 2022); SuperMinHash (Ertl 2017); fast similarity sketching (Dahlgaard, Knudsen, Thorup, FOCS 2017) | symmetric resemblance при фиксированных bytes | **обязательный**: bottom-k/OPH; equal-byte срезы внутри sketch-семейства (H1) | M |
| Containment и асимметрия | asymmetric minwise hashing (Shrivastava & Li, WWW 2015); LSH Ensemble (Zhu et al., PVLDB 9(12), 2016); JOSIE (Zhu et al., SIGMOD 2019); GB-KMV (arXiv 1809.00458); Mash Screen (Ondov et al., Genome Biology 2019) | target-normalized containment — дешёвый контроль для H2 | **обязательный**: length + containment control | M |
| FracMinHash / scaled sketches | sourmash; Hera, Pierce-Ward, Koslicki, Genome Research 2023 | размер sketch растёт с объектом, containment без фиксированного k; честный контроль для больших файлов | рекомендуемый | M |
| Weighted / consistent sampling | ICWS (Ioffe, ICDM 2010); BagMinHash (Ertl, KDD 2018); ProbMinHash (Ertl, TKDE 2022); DartMinHash (Christiani, arXiv 2005.11547); обзор Wu et al. (TKDE, arXiv 1811.04633) | веса по частоте feature (повторы, редкие anchors) | опционально в DELSK-006 после H1 | M |
| Множества и кардинальность | SetSketch (Ertl, PVLDB 14(11), 2021); HyperMinHash (Yu & Weber, TKDE 2022); UltraLogLog (Ertl, PVLDB 17(7), 2024); ExaLogLog (Ertl); Odd Sketch (Mitzenmacher, Pagh, Pham, WWW 2014) для высокой similarity | sketch, совмещающий оценку размера пересечения и cardinality; Odd Sketch точнее MinHash в near-duplicate режиме | кандидаты representation для H1 (SetSketch, Odd Sketch) | M/P (SetSketch, ULL abstract) |
| SimHash | Charikar, STOC 2002; Manku, Jain, Das Sarma, WWW 2007 | Hamming-близость; сильна для документов, слабее для бинарных правок | baseline второго ряда | M |
| Fuzzy hashes | ssdeep (Kornblum, DFRWS 2006); sdhash (Roussev 2010); TLSH (Oliver, Cheng, Chen, CTC 2013); оценка Pagani, Dell'Amico, Balzarotti (CODASPY 2018) | готовые CPU-инструменты для бинарей; Pagani et al. показывают сильную зависимость от типа правки | **обязательный** TLSH и ssdeep как off-the-shelf baselines | M |
| Compression-based similarity | NCD (Cilibrasi & Vitányi, IEEE TIT 2005); LZJD (Raff & Nicholas, KDD 2017) | LZ-словарь как feature set ближе к поведению кодера, чем k-grams | **обязательный** LZJD | M |
| Trial encode proxy | `zstd --patch-from` на низком уровне; xdelta3 `-1` | дешёвый настоящий delta encode как scorer; потолок для «скетч предсказывает кодер» | **обязательный**: если proxy уже близок к oracle при малом CPU, sketch-путь должен это превзойти по cost | — |
| Post-dedup resemblance | Finesse (FAST 2019), Odess (ICDE 2021/TOS 2023), Palantir (ASPLOS 2024), BePro (IPDPS 2025), SpeedSketch (ICPP 2025), Argus (TOS 2026), FastDelta (EuroSys 2026), Sonic (2026) | super-features, иерархии, фильтры невыгодной delta | Finesse и Odess (reimplemented, маркированы); BePro/SpeedSketch при CLEAR лицензии | P |
| Learned | DeepSketch (FAST 2022); CARD (arXiv 2106.01273 / EAAI 2025); DCLC (2026); Chunk2vec (2024); neural LSH partitions (Dong et al., ICLR 2020) | обучение на результатах кодера или контрастно | только claim review; CPU reproduction DeepSketch BLOCKED (register) | P/M |
| CDC как источник features | FastCDC (ATC 2016; TPDS 2020); RapidCDC (SoCC 2019); SeqCDC (Middleware 2024); VectorCDC (FAST 2025); WideCDC (FAST'27 prepub) | anchors для H10; не scorer | H10, отдельно | M |
| Locality-sensitive orderings | Chan, Har-Peled, Jones (arXiv 1809.11147, SoCG 2019) | теоретическая основа сортировки как замены ANN | вне P1; только если DELSK-008 упрётся в индекс | M |

## 3. Минимальный baseline набор сразу после G1

Все методы — на одном frozen `C_t`, retained rows, оценка frozen evaluator. Единого «равного бюджета» для всех методов нет: у TLSH, ssdeep, LZJD, FracMinHash и trial encode другая cost model, чем у фиксированных sketches. Поэтому DELSK-004 preregister-ится как **Pareto comparison** по осям:

| Ось | Метрики |
|---|---|
| Quality | Strict/Useful/ε Recall@K, byte и normalized regret, SavingsCapture (frozen evaluator) |
| Representation | descriptor bytes на объект, index bytes |
| Construction | CPU на построение descriptor/index |
| Query | CPU на запрос, bytes read |
| Encoder | encode calls (`R_K`), CPU trial encode для proxy |

Equal-byte срезы (64/128/256/512/1024 B) применяются только внутри сравнимых fixed-size семейств (bottom-k, OPH, SetSketch, Odd Sketch). Для остальных методов публикуется их собственная точка или кривая на Pareto-плоскости, а не принудительное приведение к одному budget. Порядок по стоимости:

1. random-seed, size-closest, previous version в lineage, git-like (size sort + window 10, name/path hash);
2. bottom-k MinHash resemblance и target-normalized containment, equal-byte срез 64–1024 B;
3. Odd Sketch / SetSketch в том же срезе; FracMinHash containment при нескольких scale (размер растёт с объектом);
4. TLSH, ssdeep, LZJD (off-the-shelf, pinned, собственные точки cost);
5. trial encode proxy (`zstd --patch-from -1`, xdelta3 `-1`), CPU — отдельная ось;
6. Finesse и Odess (reimplemented, provenance `REIMPLEMENTED`); BePro/SpeedSketch — после license review в [register](baseline-availability.json).

Окно для Delsk существует, только если Pareto-фронт методов 1–5 не проходит G3 thresholds в нужной области cost или оставляет p95 regret, который заранее записанная Hx предсказывает сократить при не худших representation/query/encoder costs.

## 4. Что не делать

- Не вводить neural embeddings до того, как дешёвые baselines покажут headroom (P1 G2).
- Не смешивать индексную скорость (FED, LSHBloom) с качеством ranking.
- Не объявлять SOTA: разные работы используют разные кодеры, chunk sizes и закрытые traces (literature review, исправление 4).
- Не начинать Rust: milestone в [desk research §18](DELSK-ATTEMPT-V2-DESK-RESEARCH.md#18-milestone-для-rust).
