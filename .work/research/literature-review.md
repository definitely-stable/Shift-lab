# Delsk: проверка литературы и границ исследовательской новизны

Дата проверки: **2026-10-04**, Asia/Yekaterinburg. Статус: исследовательский обзор, **без запуска экспериментов и без доказанного преимущества Delsk**.

## Вывод для программы исследований

Компактное описание блока для поиска delta-base — давно существующая задача. Достаточно Finesse и DeepSketch, чтобы исключить этот общий принцип из claims новизны. Более того, DeepSketch использует результаты настоящего delta-кодера при формировании обучающих групп, а Palantir сравнивается с перебором баз. Поэтому переход к encoder oracle сам по себе также не является новой идеей. [Finesse](https://www.usenix.org/conference/fast19/presentation/zhang), [DeepSketch, §4.1](https://www.usenix.org/system/files/fast22-park.pdf), [Palantir, §2.3](https://henryhxu.github.io/share/hongming-asplos24.pdf).

Рабочая гипотеза Delsk: при фиксированном бюджете descriptor/index/search **направленный, обусловленный кодером scorer** лучше простых resemblance/containment baseline сохраняет фактическую экономию байтов на независимых семействах данных. Это проверяемая гипотеза, не установленная новизна. Удобный API, portable wire format и одинаковые scalar/SIMD результаты могут быть инженерным вкладом; их наличие не доказывает научный вклад.

## Метод и происхождение свидетельств

Прочитан целиком предоставленный отчёт `deep-research-report (5).md` (1222 строки; SHA-256 `af59f574b2972370e7ef7a952e2bd9125e1c55cae5dbcacd62d983e8be50a232`). Он использован как список проверяемых утверждений. Его внутренние ссылки вида `turn…`, рекомендации и таблицы novelty не считаются первичными доказательствами.

Поиск: точные названия работ и DOI; комбинации `delta compression`, `reference search`, `resemblance detection`, `source code`, `github`, `data availability`; просмотр конференционных страниц, PDF авторов/издателей, репозиториев авторов; обратный переход по библиографиям. Отдельно проверены неоднозначные названия Sonic/SONIC, SpeedSketch, Argus и WideCDC. Случайные одноимённые проекты исключены. Патенты включены только как описание известной архитектуры, без юридического заключения.

Уровни проверки:

- **P** — прочитан первичный текст/официальный abstract либо код/README автора. Отдельно указано, если доступен только abstract.
- **M** — проверена библиография/наличие публикации; техническая часть не установлена в доступном первичном тексте.
- **R** — авторский результат, приведённый с условиями; **не воспроизведён нами**.
- **U** — осталось непроверенным: отсутствие найденного артефакта не доказывает, что его нет.

Это целевой обзор, а не доказательство исчерпывающего покрытия literature/patent landscape. Полные тексты ACM/IEEE местами возвращали 403/anti-bot; MDPI — 429, но индексированный текст страницы издателя был доступен через поиск. Для таких источников ниже различаются просмотренный материал и недоступный оригинал. Ни один загруженный сторонний скрипт не запускался; датасеты не скачивались; benchmarks не выполнялись. Ссылки на ветки репозиториев отражают состояние при проверке, а не зафиксированные commit SHA: перед воспроизведением нужны отдельные pins.

## Основная evidence matrix

| Работа и дата | Проверенная идея / связь с Delsk | Кодер, корпус и воспроизводимость | Статус и первичные источники |
|---|---|---|---|
| **Broder, On the Resemblance and Containment of Documents, 1997** | Сэмплированные fingerprints для resemblance и containment. Асимметричный containment уже известен; его нельзя выдавать за новое свойство Delsk. | Математическая основа generic baseline; не универсальная оценка стоимости delta-кодера. | **P**, оригинальная статья в [академическом PDF](https://www.cs.princeton.edu/courses/archive/spring13/cos598C/broder97resemblance.pdf); DOI `10.1109/SEQUEN.1997.666900`. |
| **Stream-Informed Delta Compression, FAST 2012** | Поиск и delta reduction в потоке backup данных; locality/candidate policy — существенная часть системы. | Производственная система Data Domain; опубликованный результат не является открытым воспроизведением. | **P** abstract, [USENIX](https://www.usenix.org/conference/fast12/wan-optimized-replication-backup-datasets-using-stream-informed-delta-compression). |
| **Finesse, FAST 2019** | Делит chunk на фиксированные subchunks, формирует features и super-features; обязательный традиционный baseline. | Оригинал: Rabin CDC, средний chunk 8 KB, Xdelta, first-fit, шесть workload-категорий (web/source/database/VM). Реализация в DeepSketch — сторонний по отношению к Finesse artifact, не автоматически идентичный оригиналу. | **P**; [paper, §5.1](https://www.usenix.org/system/files/fast19-zhang.pdf), [USENIX](https://www.usenix.org/conference/fast19/presentation/zhang). **R:** similarity computation 3.2–3.5× относительно N-transform; это не общая скорость Delsk. |
| **Odess, ICDE 2021; journal follow-up TOS 2023** | Gear rolling hash и content-defined sampling уменьшают набор hash, к которому применяются transforms. | Точный codec/corpus и artifact pins требуют проверки full text. Для baseline нельзя смешивать конфигурации 2021 и 2023. | **P** abstract 2021: [IEEE](https://ieeexplore.ieee.org/document/9458911/), DOI `10.1109/ICDE51399.2021.00048`. **M** follow-up: [TOS DOI](https://doi.org/10.1145/3584663), техническая сверка полного издательского текста не завершена. |
| **DeepSketch, FAST 2022** | Learning-to-hash descriptor + ANN reference search. DK-clustering использует delta compression ratio выбранного кодера; существующая работа уже delta-aware. | Xdelta и fallback LZ4; фиксированные 4 KiB блоки; 11 I/O workloads. [Репозиторий](https://github.com/postech-caoslab/deepsketch-fast2022) содержит training, brute-force, Finesse, multi-candidate, NGT и xdelta3; README обещает позднее открыть часть данных из-за privacy. Полное воспроизведение не подтверждено. | **P**, [paper](https://www.usenix.org/system/files/fast22-park.pdf). **R:** до 33%, среднее 21% улучшения DRR в авторском опыте — [USENIX abstract](https://www.usenix.org/conference/fast22/presentation/park). |
| **Palantir, ASPLOS 2024** | Иерархические super-features, фильтр невыгодных delta и ограничение lifetime metadata. | FastCDC, xDelta-3 (local compression level 1), Zstd 1.3.1 level 10; пять cloud-derived наборов с синтетическими backup revisions и Linux 5.0.1–5.0.21 tar. Открытый исходный artifact в просмотренном paper не найден. | **P**, [авторский PDF, §2.3/§3.3/§5.1](https://henryhxu.github.io/share/hongming-asplos24.pdf), DOI `10.1145/3620665.3640353`. |
| **BePro, IPDPS 2025** | Flexible feature matching; современный baseline с доступным авторским кодом. | README даёт ссылки Scilab, Linux, GNU tar, VM images, Stack Overflow и SYN backups; это указатели на corpus, не полный checksum manifest. Код/лицензия/параметры кодера ещё не прошли репродукционный аудит. | **P** repo и конференционная запись, full paper не прочитан: [авторский репозиторий](https://github.com/FengkuiYang-hust/BePro), [IPDPS program](https://www.ww.ipdps.org/ipdps2025/2025-advance-program.html), [IEEE paper](https://ieeexplore.ieee.org/document/11078474/). |
| **SpeedSketch, ICPP 2025** | Название прямо связывает sketch generation и delta encoding: требуется отдельная проверка overlap. Конкретные алгоритмические детали пока не приняты как доказанные. | Оригинальный full text недоступен в этой проверке (ACM 403); открытый авторский artifact не установлен. Codec/corpus/цифры остаются **U**. | **M**: [DOI публикации](https://doi.org/10.1145/3754598.3754628); название, страницы 168–177 и online date 08.09.2025 видны в [ACM publisher cited-by metadata](https://doi.org/10.1145/3035918.3064056). Конференция [8–11 сентября 2025](https://icpp2025.sdsc.edu/). |
| **Argus, TOS 22(1), 2026** | Не следует пропускать при завершении claim chart, но технические утверждения отчёта здесь не выдаются за проверенный full-text review. | **U** codec/corpus/repository и performance claims. Издательский DOI/PDF недоступен (403); получен текстовый preview оригинальной статьи на агрегаторе, который не заменяет сверку издательского экземпляра. | **M/partial**: [канонический DOI](https://doi.org/10.1145/3747839). Рабочая библиография: Han Xu et al., article 3, 29 pp.; январь 2026 указан в preview. Проверка первичного оригинала — открытая задача, не основание исключать работу. |
| **Once Rolling Hashing is Enough, EuroSys 2026** | Reuse rolling hashes — уже опубликованное направление; общая идея совместить CDC/features не может быть заявлена новой. | Подтверждены название, авторы и venue; полный paper/artifact требуют доступа. Из названия нельзя выводить степень совместимости с Delsk. | **M** первичная авторская библиография: [Wen Xia](https://cswxia.github.io/), [данные страницы](https://raw.githubusercontent.com/cswxia/cswxia.github.io/master/scripts/selected_pub.js); [DOI](https://doi.org/10.1145/3767295.3803596), EuroSys 27–30.04.2026. |
| **Sonic, Computers 15(9):607, 10.09.2026** | Fine features, bounded candidate postings и approximate selection; reuse hash; intra-chunk redundancy path. | FastCDC ~4 KB, xxHash, Xdelta; GCC/Linux/Node.js, VM images/backups, Stack Overflow. Код и данные закрыты, возможны по запросу авторам. Поэтому paper-inspired implementation нельзя маркировать официальным Sonic. | **P** индексированный текст издателя: [статья и Data Availability](https://www.mdpi.com/2073-431X/15/9/607), DOI `10.3390/computers15090607`. **R:** 5.5× throughput к DeepSketch при сопоставимом DCR в опыте авторов. |
| **ZipLLM / BitX, NSDI 2026** | Tensor deduplication + family grouping + lossless XOR delta. Специализированное направление model storage, а не готовый generic sketch oracle. | [Авторский Rust/Python repo](https://github.com/ds2-lab/ZipLLM) доступен, Apache-2.0; README реализации указывает **BF16 only**, model list и scripts. Это не гарантирует доступность каждого исторического checkpoint. | **P**, [финальный USENIX abstract](https://www.usenix.org/conference/nsdi26/presentation/wang-zirui) сообщает **R: 54%** storage reduction. Старый [project site](https://storageai.github.io/ZLLM/) сообщает 49.5%; версии результата различаются. |

### Что обязательно добавить к узкому списку исходного отчёта

| Источник | Почему нужен |
|---|---|
| **MeGA, ATC 2022** — [USENIX](https://www.usenix.org/conference/atc22/presentation/zou) | Locality и layout влияют на ingest/restore. Минимум patch bytes не обязательно минимизирует стоимость всей системы. Прочитан официальный abstract; paper-specific цифры не переносятся в gates Delsk. |
| **LoopDelta, ATC 2023** — [USENIX](https://www.usenix.org/conference/atc23/presentation/zhang-yucheng) | Locality, cache-aware filtering и inversed delta уже обсуждаются. Само слово «направление» ещё не отделяет Delsk от системного prior art. |
| **Is Low Similarity Threshold A Bad Idea in Delta Compression?, HotStorage 2024** — [авторская университетская запись](https://research.cuhk.edu.hk/en/publications/is-low-similarity-threshold-a-bad-idea-in-delta-compression-2/), [программа](https://www.hotstorage.org/2024/accepted.html), DOI `10.1145/3655038.3665940` | Low-threshold retrieval, false-positive criterion и расширение base соседними данными. Эту альтернативу нужно учитывать, прежде чем объяснять все ошибки нехваткой descriptor features. |
| **CARD, Engineering Applications of Artificial Intelligence 144:110116, 2025** — [издатель](https://www.sciencedirect.com/science/article/pii/S0952197625001162), DOI `10.1016/j.engappai.2025.110116` | Chunk-context aware neural representation — дополнительный contemporary learned baseline. Проверены abstract/section snippets, full reproduction не выполнено; отсутствие этой статьи в исходном отчёте показывает ограниченность его покрытия. |
| **FastCDC, ATC 2016** — [оригинальный PDF](https://www.usenix.org/system/files/conference/atc16/atc16-paper-xia.pdf), [авторский код](https://github.com/wxiacode/FastCDC-c) | Вспомогательный chunker, не конкурент reference scorer. Размер/алгоритм chunking необходимо зафиксировать независимо от Delsk. |
| **SeqCDC 2024, VectorCDC 2025, journal extensions 2026, DedupBench 2023** — [WASL project bibliography](https://wasl.uwaterloo.ca/projects/deduplication/) | Подтверждённые CDC-направления для отдельных экспериментов с feature source; результаты chunking нельзя смешивать с качеством base ranking. |
| **WideCDC / Taking a Bigger Byte** — [USENIX FAST'27 prepublication](https://www.usenix.org/conference/fast27/presentation/udayashankar) | Найден первичный abstract и ссылка prepublication. Это **будущая конференция 2027**, не FAST'26. Дата первой публичной доступности не установлена. Следовательно, тезис отчёта «источник WideCDC не подтверждён» уже нельзя повторять без оговорки. |
| **US20170038978A1**, publication 09.02.2017, priority 05.08.2015 — [текст заявки](https://patents.google.com/patent/US20170038978A1/en) | Явно описывает block sketch → reference index → delta encoder. Это архитектурный prior art. Поле `Abandoned` на Google Patents не является заключением о свободе использования или патентной семье. |

## Исправления и ограничения исходного отчёта

1. **Encoder-derived supervision и exhaustive oracle уже встречаются.** В DeepSketch DK-clustering выбирает группы по результату delta compression; Palantir перебирает bases в motivation experiment. Введение метрики regret полезно, но требуется показать дополнительный алгоритмический результат, а не переименовать существующий objective. [DeepSketch §4.1](https://www.usenix.org/system/files/fast22-park.pdf), [Palantir §2.3](https://henryhxu.github.io/share/hongming-asplos24.pdf).
2. **Sonic существует, но доступность ограничена.** Его числам нельзя приписывать независимую репликацию. Термин DCR в статье означает долю сэкономленных байтов, тогда как Finesse использует отношение размера до/после delta. В Sonic §6.3 throughput ниже Finesse/Odess: формулировку abstract о comparable throughput нельзя превращать в универсальное превосходство. [Sonic §6](https://www.mdpi.com/2073-431X/15/9/607), [Finesse §5.1](https://www.usenix.org/system/files/fast19-zhang.pdf).
3. **Новизна не измеряется числом галочек.** Правило «ни одна статья не покрывает 4/5 свойств» не доказывает новый вклад. Нужны ближайший baseline, чёткая изменённая конструкция и проверка её эффекта. `deterministic + portable + multi-codec` может оказаться обычной комбинацией известных решений.
4. **Не установлен единственный “самый свежий SOTA”.** Разные works используют разные candidates, chunk size, fallback compression, hardware, threading и closed traces. Дата Sonic сама по себе не делает его сильнейшим baseline во всех условиях.
5. **Гейты отчёта — пожелания, не evidence.** 99% Recall@8, 2 GiB/s/core, 100× candidate reduction и 384 MiB/1M описывают предполагаемую цель. Их достижимость не следует из литературы. Сначала нужны измеренные baseline curves и общий memory accounting, включая postings/IDs/allocator.
6. **Corpus ≥100 GiB не является научной необходимостью первого шага.** Малый frozen corpus достаточен для проверки harness и фальсификации грубых гипотез. Он недостаточен для generalization claims, но позволяет выявить ошибки до дорогих экспериментов.

## Где именно может быть полезна асимметрия

Пусть `P_E(b,t)` — полный размер сохранённого patch для target `t` относительно base `b` при фиксированной версии и настройках encoder `E`. В него входят framing и необходимые для восстановления metadata. VCDIFF разделяет source и target и содержит ADD/COPY/RUN; формат не требует равенства стоимости двух направлений. При этом RFC описывает формат, а не единственный алгоритм поиска совпадений. [RFC 3284](https://www.rfc-editor.org/info/rfc3284/).

Иллюстративная формализация, а не результат существующего эксперимента. Нормативные определения и первичный endpoint конкретного run фиксируются в [DELSK-P1](../protocol.md); здесь показана связь bytes и нормализованных показателей:

```text
L(t)     = min(raw storage, independently compressed storage), включая headers
P*(t)    = min(L(t), min_{b in C_t} P_E(b,t))
P_K(t)   = min(L(t), min_{b in TopK(t)} P_E(b,t))
regret   = P_K(t) - P*(t)                         # bytes
relregret= (P_K(t) - P*(t)) / max(P*(t), floor)    # floor заранее фиксируется
savings  = L(t) - P_K(t)
```

`C_t` должен быть одинаковым для всех algorithms; для causal storage — только уже доступные bases. При пустом Top-K действует fallback. Если несколько bases дают один минимум, strict recall считается по множеству ties, а не по произвольно выбранному `b*`. Savings capture не определён при нулевой oracle savings: такие targets учитываются отдельно. Выполняется побайтовая проверка decode каждого patch, попавшего в oracle.

Три ограничения этой гипотезы:

- Разница `P_E(A,B)` и `P_E(B,A)` может полностью объясняться длиной target; нужно сравниваться с length+containment baseline. Существование асимметрии не доказывает полезность сложного scorer.
- Для равной длины `A XOR B == B XOR A`. Если lossless compressor и framing одинаковы, чистая XOR payload cost симметрична. Направленные преимущества здесь могут возникнуть из normalization, metadata, выбора tensors и candidate constraints, а не из XOR как такового.
- Перестановка больших блоков не обязана ухудшать delta радикально: COPY способен ссылаться на разные source offsets. Пользу position/ordering features следует измерять для конкретного codec; нельзя заранее записывать permutation в категорию плохих bases.

## Фальсифицируемые эксперименты для Shift-lab

Все пункты ниже — предложения для последующих запусков GitHub Actions через workflow_dispatch. Здесь они не выполнялись.

| ID | Гипотеза | Сравнение и необходимое свидетельство | Что опровергает гипотезу |
|---|---|---|---|
| LIT-E1 | Направление несёт сигнал сверх размера/overlap | Оба направления containment, append/delete и independent version pairs; равные budgets; symmetric scorer vs length+containment vs directional scorer. Сохранять paired patch matrix. | Выигрыш исчезает после добавления target length/containment или на held-out lineages. |
| LIT-E2 | Position/run features уменьшают regret | Одинаковые anchors/bytes; baseline без positions; shifts, local edits, permutations, reordered archives. Сравнивать patch bytes, не только feature overlap. | Descriptor дороже, а paired regret CI не показывает практически значимого выигрыша. |
| LIT-E3 | Один descriptor переносится между codecs | Зафиксировать descriptor; отдельно обучать/калибровать scorers; Xdelta/VCDIFF плюс независимый COPY/ADD codec и equal-length XOR+compressor profile. Cross-codec rankings и decoder roundtrip. | Эффект остаётся только на кодере калибровки; остальные нуждаются в другом descriptor. Это основание сузить scope. |
| LIT-E4 | Улучшение идёт от scorer, а не индекса | Сначала exhaustive descriptor comparison внутри малого `C_t`; затем один shared candidate generator для всех rerankers. Отдельно retrieval miss и reranking miss. | При общих кандидатах результат равен простому baseline; улучшение объясняется большим search budget. |
| LIT-E5 | Hash reuse полезен без ущерба quality | Отдельное построение и reuse CDC features при одинаковых boundaries; no-CDC вариант; фиксировать полный pipeline CPU. | Экономия исчезает в общем pipeline или качество зависит только от собственного chunker. |
| LIT-E6 | Calibrated abstention экономит encode calls | Предсказывать возможность выиграть у `L(t)`; calibration/test разделены по lineage; negative controls: random, already-compressed, recompressed variants. | Дешёвый entropy/size filter даёт ту же curve либо пропускается существенная часть oracle savings. |
| LIT-E7 | Generic byte descriptor пригоден для моделей | Open, revision-pinned base/fine-tune families; отдельно aligned BF16 и формат/quantization changes; generic scorer vs tensor-aware profile. | Результат держится на одном семействе/известной mapping; lineages-held-out дают нулевой incremental gain. |

Минимальный сопоставимый ряд: random deterministic seed; size/recency/locality; MinHash/bottom-k; length+containment; Finesse reproduction или честно названная Finesse-inspired реализация; затем Odess/BePro, DeepSketch при наличии воспроизводимого training artifact. Palantir, Argus, SpeedSketch и Sonic — обязательные пункты claim review; недоступность артефактов нужно отражать в таблице результатов, а не заменять их названием поверх собственного кода.

Сначала оценивать **descriptor budget × Top-K × patch-regret**, отдельно quality и elapsed time. Для generalization единица разбиения — lineage/repository/model family; chunks одной линии нельзя случайно распределять между train и test. Показывать paired outcomes, macro по доменам и confidence intervals по независимым lineages. Throughput на shared CI runner — диагностический результат с environment metadata, а не достоверная hardware Pareto claim.

## Остаточные вопросы перед публикацией claims

1. Получить и сверить первичные full texts Argus, SpeedSketch, BePro, Odess journal и rolling-hash reuse; зафиксировать точные sections/algorithms, codec options и сравниваемые systems.
2. Отдельно изучить patent claims/families при необходимости commercialization; этот обзор не делает FTO заключения.
3. Для каждого воспроизводимого baseline закрепить commit, лицензию, artifact instructions, corpus revisions/checksums и список отклонений от paper. Доступный README не означает успешную сборку или совпадение published result.
4. Проверить, предлагают ли существующие работы явную calibration patch bytes, asymmetric reranking и generalization нескольких codecs. Пока отсутствие найденного примера означает **open question**, а не доказательство отсутствия prior art.
5. После общей baseline matrix выбрать измеримый effect-size gate. Замораживать Delsk256 wire format, обещать универсальность или production adoption до этого преждевременно.
