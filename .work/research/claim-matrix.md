# DELSK-001: claim matrix и границы prior art

Срез: **2026-10-04**. Статус: исследовательский register для [DELSK-001](../issues/DELSK-001.md). Это не novelty verdict, не SOTA claim и не воспроизведение: ничего не собиралось и не запускалось. Доступность реализаций с отдельными полями provenance/fidelity/license/data/reproduction — в [baseline-availability.json](baseline-availability.json). Предыдущий обзор и его общий контекст — в [literature review](literature-review.md).

## Метод и ограничения

- **Search cutoff 2026-10-04.** Обзор целевой, а не исчерпывающий. Перед итоговым verdict его нужно повторить (forward citations Finesse/Odess/DeepSketch, venues FAST/ATC/EuroSys/TOS/ICPP/IPDPS после cutoff).
- **Primary texts.** Full text читался в издательской или авторской версии. Версия и способ доступа указаны в таблице ниже. Разделы сопоставлены с claims при постатейном чтении 2026-10-04. Каждое claim → section соответствие — пункт PR review, а не самоочевидный факт.
- **Repositories.** Деревья читались статически на pinned commits; на дату проверки каждый pin совпадал с HEAD default branch. Код не выполнялся.
- `UNKNOWN` означает «не установлено в прочитанном материале», а не «нет». Отсутствие найденного artifact не доказывает его отсутствия.
- Patent text — только технический prior art; FTO или юридический вывод из него не делается.

## Источники: версия, доступ, проверенные разделы

| Работа | Версия и доступ | Проверенные разделы и что они устанавливают |
|---|---|---|
| [Finesse, FAST 2019](https://www.usenix.org/system/files/fast19-zhang.pdf) | USENIX camera-ready, full text | §4.1–4.2, Algorithm 2: фиксированные subchunks, по одному feature, SF группируются по рангу. §5.1: Rabin CDC (8 KB), Xdelta, FirstFit, 3 SF × 4 features, 400 MB LRU cache базовых chunks, шесть datasets в четырёх типах workloads, прототип на Destor. §5.2: 3.2–3.5× ускорение SF — разброс по двум CPU, не по datasets |
| [DeepSketch, FAST 2022](https://www.usenix.org/system/files/fast22-park.pdf) | USENIX, full text | §3.1: brute-force reference search против SF sketch, FNR/FPR. §4.1: k-means DK-clustering с delta-compression ratio вместо евклидова расстояния; кодер в §4.1 не назван, platform encoder Xdelta — §5.1. §5.1: блоки 4 KiB, LZ4 fallback, 11 workloads; inference на RTX 2080; Finesse baseline выбирает базу по максимуму совпавших SF, а не FirstFit. §5.6: стоимость inference и памяти, offline training < 4 ч. Footnote 4: обещано открыть platform и data |
| [Palantir, ASPLOS 2024](https://henryhxu.github.io/share/hongming-asplos24.pdf) | Авторский PDF ACM camera-ready, full text | §2.3: brute-force vs N-Transform/Finesse/Odess **только на DB_Stock**. §3.2: три tiers SF, FirstFit внутри tier. §3.3: adaptive false-positive filter сравнивает delta ratio с средним по предыдущим записям — оценка, а не точная проверка выгоды. §3.4: lifecycle metadata по версиям. §5.1: FastCDC, xDelta-3 level 1, Zstd 1.3.1 level 10, пять backup datasets с синтетическими revisions и Linux 5.0.1–5.0.21 tar |
| [Odess, ACM TOS 19(3):22, 2023](https://doi.org/10.1145/3584663) | Издательская версия, full text. Черновик на ResearchGate — pre-publication draft, а не accepted manuscript | §3.2: content-defined sampling Gear hashes по mask. §3.3: сохранение similarity при sampling. §3.4: SWPR; Odess = Gear + sampling, Odess+ = SWPR + sampling. §4.3: FirstFit и модифицированный Xdelta3 без inner compression. Ускорение генерации features различается по версиям: ICDE 2021 abstract — 5.4× к Finesse и 26.9× к N-Transform, TOS — 7.9× и 31.4×; цитировать нужную версию |
| [BePro, IPDPS 2025](https://ieeexplore.ieee.org/document/11078474/) | Только abstract и metadata (paywall) | Abstract: flexible feature matching, gain filtering high-gain chunks, LSH-Delta index, load balancer. Технические детали **UNKNOWN** до чтения full text; код доступен (см. register) |
| [SpeedSketch, ICPP 2025](https://doi.org/10.1145/3754598.3754628) | ACM, CC BY 4.0, full text | Abstract и §4.3: Bloom-filter-подобный sketch одновременно ищет базы и ускоряет delta encoding, пропуская нередуцируемые данные. §5.6: exclusion и false-positive rate. Sketch и encoder связаны: ускорение encoder нельзя относить к качеству ranking |
| [Argus, ACM TOS 22(1), 2026](https://doi.org/10.1145/3747839) | ACM, CC BY 4.0, full text | Сопоставление с осями Delsk. **Objective** (§3.1.1, §4.1–4.2, §5.2): точность features/Jaccard и охват похожих chunks; DCR — только итоговая метрика; при выборе базы вывод кодера не используется. **Выбор базы** (§4.2): до 3 Plain Features (по одной на bin), до 3 кандидатов, берётся кандидат с максимумом совпавших features (приближённый Best-Fit); правило ties не задано. **Directionality**: не рассматривается, similarity — симметричная оценка Jaccard. **Codec** (§5.1): только Xdelta3 без inner compression, без настройки под кодер. **Budgets** (§4.2–4.3): равенство индекса заявлено как 3 features против 3 SF, байты не измерены. **Oracle** (§3.1.2): brute-force с перебором всех баз — только как мотивация против N-Transform, Argus с ним не сравнивается. **Datasets** (§5.1): LNX, RDB, VMA, VMB, SOF0–4, FastCDC 4/8/16 KB; held-out оценки нет. Artifact не указан |
| [Once Rolling Hashing is Enough, EuroSys 2026](https://doi.org/10.1145/3767295.3803596) | ACM, CC BY 4.0, full text | FastDelta. §4.2: sampled hashes записываются внутри FastCDC. §4.3: similarity detection использует их повторно. §4.4: delta encoding тоже использует их повторно (Xdelta-style word-hash index). Reuse покрывает и encoder, а не только CDC/features |
| [CARD preprint, arXiv 2106.01273v1](https://arxiv.org/abs/2106.01273) | arXiv v1 2021-06-02, единственная версия, full text | §4.2, Algorithm 1: N-sub-chunk shingles — упорядоченная структура внутри chunk. §4.3: BP-сеть предсказывает признак центрального chunk по 2K соседям (self-supervised, CBOW-подобно), а не по patch gain. Обобщение между datasets не заявлено |
| [CARD journal, EAAI 144:110116, 2025](https://doi.org/10.1016/j.engappai.2025.110116) | Abstract и highlights; body за paywall | Другое название и состав авторов; ускорение указано как 5.6–86.7× против 5.6–17.8× в preprint. Это отдельная version row |
| [Sonic: Efficient Similarity Detection for Delta Compression, Computers 15(9):607](https://www.mdpi.com/2073-431X/15/9/607) | MDPI, published 2026-09-10, full text | §5.1.1: bounded postings (≤N chunks на bucket, M=8, N=30). §5.1.2: intra-chunk path через delta с пустой базой. §5.2: rolling hash для CDC и features. §6.1: DCR = доля сэкономленных байтов. §6.3: throughput ниже Finesse/Odess, хотя abstract говорит о comparable throughput. §6.6: byte/index accounting. Data Availability: code/data по запросу |
| [DCLC, JKSU-CIS 38, 2026](https://link.springer.com/article/10.1007/s44443-026-01042-5) | Springer, online 2026-07-11, full text | §1 и §2.2 **заявляют** supervision от delta-compression gains и locality. §3.1–3.2, §4.1: описано обучение self-supervised InfoNCE, label — признак центрального chunk. Формулы gain-labeling нет. Позиционное кодирование и контекстное окно — §3.1–3.2. Multi-reference delta (MRD) — §3.4. DCR = before/after. Указанный repository отвечает 404 |
| [ZipLLM/BitX, NSDI 2026](https://www.usenix.org/system/files/nsdi26-wang-zirui.pdf) | USENIX, full text | §4.1: tensor-level dedup. §4.2: BitX XOR + generic compressor. §4.3–4.4: clustering по bit distance, lineage из model cards. §5.1: 3,048 fine-tuned репозиториев, 43.19 TB. §5.2.1: 54.1%. Paper называет BitX dtype-agnostic; реализация поддерживает только BF16 |
| [US20170038978A1](https://patents.google.com/patent/US20170038978A1/en) | Google Patents, full text | Claim 1: signature sketch → reference index (hash table + reference list) → delta encoding. Status `Abandoned` — поле базы, не юридический вывод |
| [WideCDC, FAST'27 prepublication](https://www.usenix.org/conference/fast27/presentation/udayashankar) | USENIX prepub PDF, full text | Hashless CDC: feature-source control, не ranking. На странице показаны artifact badges Available/Functional; где лежит artifact, не установлено. Дата первой публичной доступности не установлена; страница и PDF расходятся в максимальном dedup ratio (2.95× и 3.07×) |

Не перечитывались по разделам в этом проходе: Broder 1997, Stream-Informed Delta, MeGA, LoopDelta, HotStorage 2024, FastCDC, SeqCDC/VectorCDC. Для них действуют уровни проверки из [literature review](literature-review.md).

## Claims Delsk против prior art

Статусы: **COVERED** — идея опубликована, её нельзя заявлять вкладом. **PARTIAL** — есть пересекающаяся работа, вклад возможен только в конкретной отличающейся конструкции с измеренным эффектом. **OPEN** — пересечение не найдено в прочитанном, это исследовательская гипотеза без novelty verdict. OPEN не означает «prior art отсутствует»: для непрочитанного материала действует `UNKNOWN`, список таких источников — в Claim blockers.

| Возможный claim | Ближайший prior art (раздел) | Статус | Допустимая формулировка |
|---|---|---|---|
| Sketch → reference index → delta encoder | Finesse §4–5; DeepSketch §5.1; US20170038978A1 claim 1 | COVERED | Общая архитектура, не вклад |
| Encoder/gain-aware objective при обучении или фильтрации | DeepSketch §4.1 (delta ratio как расстояние offline-кластеризации); Palantir §3.3 (post-match filter по delta ratio поверх FirstFit); BePro gain filtering (abstract) | COVERED | Использование выигрыша кодера как сигнала обучения или фильтра — не вклад |
| Ранжирование `C_t` во время deployment по предсказанным patch bytes | Прямого prior art не найдено: DeepSketch ранжирует learned sketch/ANN, Palantir и Argus — по совпадениям features (§3.2; §4.2), BePro прочитан только по abstract, у DCLC нет механизма gain-labeling | PARTIAL | Не заявлять «выбор базы по выигрышу кодера» как вклад. Узкий claim (calibrated byte prediction для Top-K при равных budgets) возможен только после BePro full text и измеренного эффекта против gain-aware baselines |
| Exhaustive encoder oracle как эталон | DeepSketch §3.1; Palantir §2.3; Argus §3.1.2 | COVERED | Вклад возможен в протоколе: общий `C_t`, ties, fallback, regret. Название oracle вкладом не является |
| Обучение descriptor на метках от delta gains | DCLC §1/§2.2 заявляет, но механизм §3–4 self-supervised; DeepSketch §4.1 строит обучающие кластеры по delta ratio | PARTIAL | Запрещено «первое gain-supervised представление». Отличие от предыдущей строки: здесь речь о метках для descriptor, а не о ранжировании кандидатов |
| Позиции, порядок, контекст | CARD §4.2 (ordered shingles), §4.3 (context); DCLC §3.1–3.2 (positional encoding); Palantir §3.2 (tiers) | PARTIAL | Разделять порядок внутри chunk, иерархию descriptor и иерархию retrieval. Каждое требует отдельной ablation |
| Ограниченные candidate postings и byte budget | Sonic §5.1.1, §6.6; BePro LSH-Delta index (abstract); Palantir §3.4 | PARTIAL | Нужна отличающаяся конструкция и paired эффект при равных budgets |
| Reuse CDC/rolling hash | Rolling-hash reuse §4.2–4.4 (включая encoder); Sonic §5.2; Odess §3.2 | COVERED | Не заявлять. Hash reuse допустим как инженерная деталь |
| Отказ от невыгодной delta (abstention) | Palantir §3.3; BePro gain filtering; SpeedSketch §4.3 (bypass) | PARTIAL | Отличие возможно в calibration и экономике false negatives (LIT-E6) |
| Совместная оптимизация sketch и encoder | SpeedSketch abstract, §4.3; rolling-hash reuse §4.4 | COVERED | Изменение encoder не приписывать качеству scorer |
| Tensor-aware family delta | ZipLLM §4.1–4.4 | COVERED | Generic XOR+compressor не называть BitX |
| Multi-reference delta | DCLC §3.4 (MRD) | COVERED | Вне scope single-base Top-K, пока протокол не определит иное |
| Направленный scorer: `P_E(b,t)` ≠ `P_E(t,b)` при выборе базы | Не найдено в прочитанном. Argus: симметричный Jaccard, direction не рассматривается. Направленность определений DeepSketch §4.1, Palantir §3.3 и BePro не установлена | OPEN | Гипотеза LIT-E1. Должна побить length+containment control |
| Scorer, обусловленный кодером, с переносом между codecs | Не найдено; все прочитанные работы используют один encoder pipeline (Argus §5.1 — только Xdelta3) | OPEN | Гипотеза LIT-E3. Поддержка двух codecs сама по себе не доказывает codec conditioning |
| Равные descriptor/index/K budgets между методами | Finesse/Odess/Palantir используют фиксированные 12 features/3 SF; Argus §4.2 заявляет равенство индекса (3 features против 3 SF), но байты не измеряет; общего budget-matched протокола не найдено | OPEN | Методологический вклад протокола, а не алгоритма |

Направленный вызов encoder, два поддержанных codecs и отсутствие фразы в abstract **не доказывают** соответственно directional predictor, codec-conditioned scorer и отсутствие prior art.

## Поправки к плану R0 после проверки

1. **SpeedSketch, Argus и rolling-hash reuse доступны в full text** (ACM, CC BY 4.0). Их нельзя держать в `UNKNOWN` по причине недоступности. Строки обзора обновлены.
2. **Rolling-hash reuse покрывает и delta encoder** (§4.4), а не только CDC/features. Claim «CDC/hash reuse» переходит из PARTIAL в COVERED.
3. **Odess:** прочитана издательская версия. ResearchGate copy — pre-publication draft, а не accepted manuscript. FirstFit и модификация Xdelta описаны в §4.3, а не в §3.
4. **DCLC:** заявление о gain supervision есть, механизма нет. Это блокирует безусловный claim «первое gain-supervised», но не показывает совпадения с Delsk.
5. **CARD:** Algorithm 1 находится в §4.2 и описывает shingles внутри chunk. Context objective — §4.3, self-supervised. Journal version — отдельная row с другим названием, авторами и цифрами.
6. **Finesse:** шесть datasets в четырёх типах workloads (а не шесть категорий). Прототип построен на Destor. Ускорение 3.2–3.5× — разброс по CPU.
7. **DeepSketch:** его Finesse baseline выбирает базу по большинству совпавших SF, а не FirstFit. В репозитории `COPYING` xdelta3 — dangling symlink. Ссылка paper `dgist-datalab` перенаправляет на тот же repository.
8. **Palantir:** brute-force motivation — один dataset. Filter оценочный. Найден сторонний framework без лицензии, заявляющий реализации N-Transform/Finesse/Odess/Palantir; это не author code.
9. **ZipLLM:** ссылка на код в paper (`ds2lab`) отвечает 404, рабочий репозиторий — `ds2-lab`. Paper заявляет dtype-agnostic BitX, а реализация поддерживает только BF16.
10. **SpeedSketch** содержит prebuilt `lib/libzd.a` и vendored zdelta/edelta. Основной `speedsketch` binary их не линкует, а отдельная утилита `odess/` линкует `-lzd`. Схемы `od-g/od-x` реализованы в `speedsketch.cpp`. License review должен учитывать оба build path.
11. **Gain-aware objective и gain-ranked selection разделены.** Prior art покрывает выигрыш кодера как сигнал обучения или фильтра. Ранжирование `C_t` по предсказанным patch bytes во время deployment получило статус PARTIAL, а не COVERED.
12. **Argus содержит brute-force oracle** (§3.1.2, против N-Transform). Это ещё один prior art для строки oracle.
13. **WideCDC** имеет artifact badges; поиск artifact — открытый пункт, до этого `UNAVAILABLE`.

## Claim blockers

| Blocker | Что закрывает | Как закрыть |
|---|---|---|
| BePro full text не прочитан | Directionality, gain filter formula, budgets BePro; закрывает или понижает PARTIAL для gain-ranked selection | Institutional/author copy; до этого строки BePro — `UNKNOWN` |
| CARD journal body не прочитан | Отличия journal version от preprint | Доступ к EAAI full text |
| Directionality в DeepSketch §4.1 и Palantir §3.3 не установлена | OPEN-статус directional claim | Целевое перечитывание определений ratio (base→target или симметрично) |
| Forward-citation sweep после cutoff | Полнота OPEN-строк | Повторный поиск перед final verdict |
| Лицензии DeepSketch/BePro, xdelta3 notice conflict | Использование author modules в CI | Ответ правообладателей или чистая reimplementation с отдельной fidelity evidence; в R0 outreach не выполняется |
| Ни одна реализация не собрана | Любой статус `VERIFIED` | DELSK-004 в GitHub Actions после codec lock |
