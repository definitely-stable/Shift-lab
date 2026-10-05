# DELSK-003A: registered-attempt model — desk research

Issue: [DELSK-003A #27](https://github.com/definitely-stable/Shift-lab/issues/27). Дата: **2026-10-05**. Base: `main` = `c27678f02a661d118c7d37f11017523282de5226` (PR #26 merged). Статус: **desk research и protocol design**. Ничего не реализовано, natural oracle и G1 = **NOT_RUN**, frozen `delsk.oracle-contract.v1` не менялся, Rust не начинался.

Спецификация предложения — [attempt-v2-proposal.md](../oracle/attempt-v2-proposal.md). Обновление prior art для DELSK-004/006 — [DELSK-PRIOR-ART-UPDATE-2026-10.md](DELSK-PRIOR-ART-UPDATE-2026-10.md).

**Verdict: `V2 REGISTERED-ATTEMPT MODEL RECOMMENDED`** — при четырёх обязательных условиях (§4.3): append-only registry, **bind-before-measure** (без записи в registry измерение физически не начинается), `MISSING ⇒ NOT_PASSED`, классификация «до границы измерения» только по данным provider. Без bind-before-measure модель небезопасна (контрпример CE1).

## 1. Текущее состояние и причинная цепочка блокировки

Прочитаны: [contract.md](../oracle/contract.md) (§0, §7, §9, §12), [freeze.json](../oracle/freeze.json), [slice-b.md](../oracle/slice-b.md), [slice-c.md](../oracle/slice-c.md), [slice-c0-plan.md](../oracle/slice-c0-plan.md), [dispatch-registration-design.md](../oracle/dispatch-registration-design.md), [dispatch-registration-plan.md](../oracle/dispatch-registration-plan.md), [oracle_attempts.py](../tools/oracle_attempts.py), [oracle_dispatch.py](../tools/oracle_dispatch.py), [oracle_pilot.py](../tools/oracle_pilot.py), [oracle_eval.py](../tools/oracle_eval.py) (`g1`, `g1_inventory`), [oracle-pilot.yml](../../.github/workflows/oracle-pilot.yml), [oracle-smoke.yml](../../.github/workflows/oracle-smoke.yml), [R0-readiness.md](R0-readiness.md), [roadmap.md](../roadmap.md), [protocol.md](../protocol.md), issues [#4](https://github.com/definitely-stable/Shift-lab/issues/4) и [#6](https://github.com/definitely-stable/Shift-lab/issues/6).

| Шаг | Где | Что именно |
|---|---|---|
| 1. v1 all-attempt rule | contract §7 | «G1 по всем attempts одной measurement identity»; «все attempts сохраняются; неудачный run нельзя заменить удачным». Слово *attempt* в v1 **не определено**; §12 называет repeat «вторым dispatch того же SHA» |
| 2. Интерпретация attempt = GitHub dispatch | Slice B gates, `attempts.json` | ledger `delsk.oracle.attempts.v1` содержит «каждый dispatched attempt»; `g1_inventory` блокирует PASS при `ATTEMPT_NOT_RETAINED` |
| 3. Полнота через GitHub inventory | `oracle_attempts.inventory` | все страницы runs, все `run_attempt`, `run_number` без пропусков, два чтения подряд |
| 4. Контрпример | slice-c.md | runs 1, 2 `COMPLETE`; failed run 3 удалён до первого наблюдения. API показывает непрерывные 1, 2: история неотличима от истории без run 3. Удалить run может любой с write access ([GitHub docs](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/delete-a-workflow-run)) |
| 5. Completeness недоказуема | dispatch-registration-design | pre-registration CLI обходится UI/API; actor policies оставляют failed runs; webhooks не redeliver; org audit log на Free = HTTP 404 |
| 6. `DISPATCH_HISTORY_UNVERIFIED` | `oracle_pilot.require_dispatch_history`, `oracle_attempts.g1_root` | безусловный отказ worker/runner до natural acquisition; production G1 никогда не PASS |
| 7. Natural oracle blocked | slice-c.md | G1 = NOT_RUN; DELSK-004 ждёт G1 |

Наблюдения 2026-10-05 (read-only API): `oracle-pilot.yml` runs = **0**; org plan `free`, `filled_seats = 1` (единственный участник — admin); repository rulesets endpoint отвечает `[]` (rulesets доступны, не настроены); Repository Activity API отдаёт pushes/force pushes/branch deletions.

**Корень проблемы — не GitHub, а выбор population.** v1-реализация определила научную историю как множество объектов, которыми владеет и которые может удалять execution provider. Любое определение attempt через provider inventory наследует его семантику удаления. Значит, вопрос не «как доказать полноту GitHub», а «какое множество попыток научно обязано попасть в G1 и кто им владеет».

## 2. Что считать attempt: три определения

| | A. Все execution attempts на CI provider | B. Все зарегистрированные intents до начала измерения | C. Только успешно стартовавшие jobs |
|---|---|---|---|
| Кто владеет множеством | GitHub (удаляет write-access) | append-only registry проекта | GitHub + исполнитель |
| Защита от выбрасывания неудачного | только при полной недоказуемой inventory | да, если measurement невозможен без записи (§4) | нет: «не стартовал» — рычаг отбора |
| Требует знать внутреннюю историю provider | да | нет (только reconciliation) | да |
| Научный аналог | «все пациенты, когда-либо прошедшие через клинику» | randomized participants (ITT) / registered trial | per-protocol analysis |
| Вердикт | правильно по смыслу, неисполнимо на Free GitHub | **корректно и исполнимо** при условиях §4.3 | **некорректно** (survivorship/retry bias) |

Почему C отвергается: job, упавший до старта, неотличим для читателя от job, отменённого исполнителем после неблагоприятного сигнала. Per-protocol анализ известен как источник смещения; CONSORT требует отчитываться обо всех рандомизированных, включая выбывших ([CONSORT 2025, BMJ 389:e081123](https://research.bond.edu.au/en/publications/consort-2025-statement-updated-guideline-for-reporting-randomised/)).

Почему A правильно по смыслу, но избыточно: научно важны не все *submissions*, а все исполнения, которые **могли дать информацию об исходе**. Submission, не дошедший до измерения, информации не несёт. A требует большего, чем нужно, и именно лишняя часть (доказать отсутствие удалённых пустых runs) недоказуема.

Вывод: правильное определение — B с **точной временной границей**: attempt — каждое исполнение, пересёкшее (или не доказавшее, что не пересекло) границу измерения `B`, и каждое такое исполнение обязано иметь запись в registry, сделанную **до** `B`.

## 3. Literature: что говорят preregistration, trials и benchmarking

Уровни: **P** — первичный текст/официальная страница просмотрены в этом или предыдущем срезе; **M** — библиография проверена, текст в этом срезе не перечитывался.

| Источник | Что берём | Ур. |
|---|---|---|
| Nosek et al., *The preregistration revolution*, PNAS 115(11), 2018, DOI 10.1073/pnas.1708274114 | preregistration отделяет confirmatory от exploratory; это commitment device против непреднамеренного forking paths, **не** защита от fraud | M |
| Chambers & Tzavella, *The past, present and future of Registered Reports*, Nat Hum Behav 6:29–42, 2022, DOI 10.1038/s41562-021-01193-7 | протокол принимается до сбора данных; результат публикуется независимо от исхода — аналог «зарегистрированная попытка остаётся в истории при любом исходе» | P (abstract) |
| Ernst & Baldassarre, *Registered Reports in Software Engineering*, EMSE 28:55, 2023, DOI 10.1007/s10664-022-10277-5 | registered reports в SE с MSR 2020 | P (abstract) |
| ICMJE, De Angelis et al., NEJM 2004, DOI 10.1056/NEJMe048225 | регистрация **до включения первого участника**, иначе не публикуется. Граница — начало сбора данных, а не подача заявки; незарегистрированное испытание не запрещено, оно **непубликуемо** (= Model 1, §6) | M |
| Turner et al., NEJM 358:252–260, 2008, DOI 10.1056/NEJMsa065779 | FDA registry как authoritative denominator выявил publication bias антидепрессантов: registry, а не публикации, определяет популяцию | M |
| Chan et al., JAMA 291:2457, 2004; Goldacre et al. (COMPare), Trials 20:118, 2019 | outcome switching обнаруживается сравнением отчёта с заранее зарегистрированным протоколом | M |
| Simmons, Nelson, Simonsohn, Psych Sci 22, 2011; Kerr, PSPR 2(3), 1998; Armitage, McPherson, Rowe, JRSS A 132, 1969 | researcher degrees of freedom, HARKing, optional stopping: проверка «до первого успеха» раздувает ошибку I рода | M |
| CONSORT 2025 (Hopewell et al.) | flow diagram: все allocated учитываются; исключения **до** allocation допустимы, если отчитаны | P (abstract) |
| van der Kouwe et al., *SoK: Benchmarking Flaws in Systems Security*, EuroS&P 2019 | группа flaws «selective benchmarking»; почти все 50 изученных papers имеют хотя бы один flaw | P (abstract) |
| Georges et al., OOPSLA 2007; Mytkowicz et al., ASPLOS 2009; Kalibera & Jones, ISMM 2013; Hoefler & Belli, SC15 | повторы, отчёт всех измерений, контроль скрытых факторов среды | M |
| Collberg & Proebsting, CACM 59(3), 2016; Vitek & Kalibera, EMSOFT 2011 | repeatability требует сохранения артефактов и процедур, а не только итогов | M |
| Dodge et al., *Show Your Work*, EMNLP 2019; Bouthillier et al., MLSys 2021; Henderson et al., AAAI 2018; Agarwal et al., NeurIPS 2021 | лучший из N trials без N — смещённая оценка; отчёт по всем trials | M |
| Luo et al., FSE 2014; Parry et al., TOSEM 31(1), 2022 | rerun-until-green маскирует flaky tests = retry laundering | M |
| Mohan et al., ARIES, TODS 17(1), 1992 | write-ahead logging: запись намерения до действия, recovery по журналу — инженерная форма «register before submit» | M |
| Haber & Stornetta, J. Cryptology 1991; Schneier & Kelsey, TISSEC 1999; Crosby & Wallach, USENIX Security 2009 | hash chain даёт tamper evidence **префикса**, но не защищает хвост без внешнего anchor | M |
| RFC 6962 / RFC 9162 (Certificate Transparency); C2SP `tlog-checkpoint`, `tlog-witness`; Meiklejohn et al., arXiv 2011.04551 | signed checkpoints + witness cosigning против rollback и split view | M |
| Sigstore (Newman et al., CCS 2022); [Rekor v2 GA](https://blog.sigstore.dev/rekor-v2-ga/) | публичный append-only log; v2 — tile-based, **search API удалён**, клиент хранит inclusion proof сам | P |
| W3C PROV-O (2013); MLflow RunStatus (`SCHEDULED/RUNNING/FINISHED/FAILED/KILLED`); Sacred observers (`QUEUED/RUNNING/COMPLETED/FAILED/INTERRUPTED`) | run создаётся **до** исполнения, неуспешные runs — полноправные записи со статусом | M |
| SLSA v1.0 provenance; in-toto (Torres-Arias et al., USENIX Security 2019); [GitHub artifact attestations](https://docs.github.com/en/actions/concepts/security/artifact-attestations) | подписанная provenance связывает artifact с workflow/run; для public repos bundle пишется в публичный immutable log | P |

Синтез: во всех зрелых практиках **популяция определяется заранее зарегистрированным реестром, а не каналом доставки результатов**. Регистрация должна предшествовать первому сбору данных (ICMJE, CONSORT allocation), а не административной подаче. Неудачи не исключаются (ITT), исключения до allocation допустимы при отчёте. Preregistration защищает от непреднамеренного отбора; против намеренной подделки нужны внешние свидетели (CT/witness), и это отдельный, более дорогой уровень.

## 4. Проверка registered-attempt hypothesis

### 4.1 Формальная модель

- `R` — append-only последовательность записей registry; запись `r` содержит identity `I(r)`, source SHA и provider binding `(run_id, run_attempt)`.
- `B` — **граница измерения**: первый шаг, который исполняет код измерительного аппарата (`oracle_build`) или читает byte natural corpus, что раньше. До `B` об исходе ничего не известно.
- `X(I)` — множество исполнений reviewed workflow на source SHA identity `I`, пересёкших `B`.
- `A(I) = {r ∈ R : I(r) = I} \ PRE(I)`, где `PRE(I)` — записи, для которых **provider-данные** доказывают, что исполнение не дошло до `B`.
- Исход `o(r)` вычисляется только из evidence, привязанного к `r`: `INVALID`, `COMPLETE(d)` (d — repeat tuple v1 §9), `COMPLETE_WITH_FAILURES`, `INCOMPLETE`, `MISSING`.
- `G1(A)` — frozen v1 §7 над `A(I)`, где `MISSING` ведёт себя как v1 `ATTEMPT_NOT_RETAINED` (NOT_PASSED).

### 4.2 Proposed invariant и доказательство

> Научная попытка существует тогда и только тогда, когда исполнение записано в authoritative append-only registry **до** `B`. Исполнение без записи не может пересечь `B` (bind-before-measure). Запись нельзя удалить. Отсутствие evidence для записи даёт `MISSING`.

**Лемма 1 (покрытие).** Bind-before-measure ⇒ каждое `x ∈ X(I)` имеет ровно одну запись в `R` с binding `x`: reviewed код до `B` читает `R` и останавливается, если записи нет или она привязана к другому исполнению. Значит `X(I) ⊆ A(I) ∪ PRE(I)`, а `PRE` по построению не содержит пересёкших `B`. Итог: `X(I) ⊆ A(I)`.

**Лемма 2 (монотонность по информации provider).** Удаление run, artifact или ответа API может только превратить `o(r)` в `MISSING` или перевести `r` из `PRE` в `A` (доказательство «не дошло до B» исчезло). Обе операции не улучшают вердикт: `MISSING ⇒ NOT_PASSED`. В v1 удаление run **сокращало** популяцию (сдвиг к PASS); в v2 удаление **сокращает evidence** (сдвиг к NOT_PASSED).

**Лемма 3 (монотонность G1 по популяции).** Для v1 §7: если `G1(A ∪ {x}) = PASS`, то `x` — verified `COMPLETE` с тем же tuple. Добавление попытки не может превратить NOT_PASSED/INVALID в PASS. Значит, единственный рычаг отбора — **убрать** попытку из `A`.

**Теорема.** При допущениях D1–D4 production `G1_v2(R) = PASS` ⇒ каждое исполнение из `X(I)` дало verified `COMPLETE` с одинаковым tuple, conformance PASS и verified bundle.

Доказательство: PASS ⇒ все `r ∈ A(I)` verified COMPLETE с одним tuple (v1 §7). По лемме 1 `X(I) ⊆ A(I)`. Убрать элемент из `A(I)` можно только (a) удалив запись — запрещено D1; (b) переклассифицировав её в `PRE` — требует provider-данных «до B», которые оператор не может подделать (D2); (c) подменив evidence чужим — запрещено binding (`run_id`, `run_attempt`, digest записи, source SHA, проверка provider) (D3); (d) зарегистрировав задним числом — бессмысленно: без записи исполнение не дошло до `B` (D4). ∎

Допущения:

- **D1** registry append-only и durable: ruleset запрещает force push и удаление; запись проверяется readback; хвост дополнительно защищает witness (V2-Hardened).
- **D2** записи provider о runs/jobs/steps оператор может удалить, но не подделать.
- **D3** evidence принимается только с точным binding к записи и provider run.
- **D4** reviewed workflow на registered SHA исполняет bind-before-measure до `B`; workflow-код других SHA неприемлем (его source ≠ registered).

**Контрпример пользователя.** A → COMPLETE, B → COMPLETE, C → FAILED, затем GitHub run C удалён полностью. Запись C осталась в `R`; evidence нет ⇒ `o(C) = MISSING` ⇒ G1 `NOT_PASSED`. Если bundle C успели сохранить, исход C (`INCOMPLETE`/`INVALID`) блокирует сам. Ни в одном случае C не исчезает.

### 4.3 Минимальные контрпримеры: какие условия необходимы

| CE | Модель без условия | Атака | Необходимое условие |
|---|---|---|---|
| CE1 | intent зарегистрирован, но исполнение привязывается позже | intent `I`; controller dispatch + ручной UI run с тем же input; хуже run удалить, лучший привязать к `I` | **bind-before-measure**: binding записан до `B`, одна запись = одно исполнение |
| CE2 | workflow измеряет без проверки registry | измерить, увидеть исход, зарегистрировать только удачные | измерение невозможно без записи (то же условие) |
| CE3 | registry mutable | удалить запись C | append-only + ruleset (+ witness для admin) |
| CE4 | запись без evidence игнорируется | удалить run C → C «пропал» | `MISSING ⇒ NOT_PASSED` |
| CE5 | «не дошло до B» по self-reported sidecar | пересёкший run объявить пустым | классификация `PRE` только по provider jobs/steps API |
| CE6 | G1 только внутри identity | неудача на SHA X; docs-коммит → SHA Y → новая identity → повтор до PASS | **уже есть в v1**; закрывается disclosure, carry-over и transition record (§8) |

Без CE1/CE2-условия registered-attempt model **не** заменяет v1: отбор переезжает внутрь intent. С ним — заменяет.

## 5. Trust boundary

```text
scientific authority   append-only registry (что существует и что считается)
       │  запись до B, readback
execution provider     GitHub Actions (исполняет; его inventory — не источник истины)
       │  run_id/attempt, jobs/steps, artifacts
evidence               retained bundle + sidecar, binding к записи
       │  reconciliation registry ↔ provider (только binding, не полнота)
verdict                G1 v2 = frozen v1 §7 над A(I)
```

GitHub inventory остаётся в двух ролях: (1) подтвердить, что bundle пришёл из provider run с правильным SHA/workflow/attempt; (2) доказать `PRE` (job/step не стартовал). Ни в одной роли его неполнота не может дать PASS.

Минимальный набор полей записи **до** `B`: `sequence`, `previous_entry_sha256`, `repository`, `workflow_path`, `workflow_ref`, `workflow_sha`, `measured_source_sha`, `measurement_identity_sha256`, `science_identity_sha256` (identity без `measured_source_sha`, §8), `run_id`, `run_attempt`, `phase`, `registry_schema`, `g1_contract`, `transition` (null, кроме первой записи новой `science_identity` после natural попытки другой серии, §8). Не нужны: отдельные corpus/candidate/codec bindings (входят в identity и выводятся из source SHA через `git_source`), timestamp как доверенное поле (runner clock не authority; порядок задаёт sequence/цепочка; время — информативно), «reservation state» (в self-registration не нужен, §7).

## 6. Bypass: ручной `Run workflow` или API вне controller

**Model 1 — unregistered runs irrelevant.** Unregistered исполнение не является попыткой и не может стать evidence. Что должно быть доказано и чем:

| Требование | Механизм |
|---|---|
| не пишет в authoritative result store | workflows read-only к `main`; retention только reviewed PR через tool, который требует запись registry |
| bundle невозможно принять | retention и G1 требуют binding `(run_id, run_attempt) → запись` и digest записи в sidecar |
| run ID отсутствует в registry | binding проверяется против registry, а не против bundle |
| evaluator отказывает | unregistered bundle в results root = `EVIDENCE_ROOT_INVALID` (fail closed, не «игнор») |
| не влияет на G1 | популяция берётся из registry |
| нельзя подобрать удачный и зарегистрировать постфактум | reviewed workflow без записи останавливается до `B`; запись после `B` даёт `UNBOUND_MEASUREMENT` |

**Model 2 — unregistered run = protocol violation (experiment INVALID).** Требует обнаруживать unregistered runs, а это снова полнота GitHub inventory: удалённый unregistered run невидим. Хуже того, асимметрия создаёт обратный стимул: видимый bypass блокирует, удалённый — нет. Model 2 возвращает исходную недоказуемую задачу.

**Решение: Model 1.** Она проще и даёт ту же научную защиту, потому что unregistered исполнение reviewed workflow не может пересечь `B`, а исполнение другого кода неприемлемо по source binding. Наблюдённые unregistered runs допустимо перечислять в G1 record как диагностику, без влияния на вердикт.

Чего не делает ни одна модель: не запрещает частные вычисления на **публичных** inputs (corpus — открытые архивы). Модифицированный workflow или локальный скрипт может посчитать natural costs. Это вопрос P1 leakage/sealing (§9.1 v1) и процедурной дисциплины, а не provenance попыток. Для G1 (validity gate детерминированного измерения) предварительный отладочный run на другом коде не создаёт смещения: G1 всё равно требует, чтобы **все** registered исполнения были COMPLETE и одинаковы.

## 7. Граница preregistration и crash cases

Обязательная временная граница — **информационная**: запись durable (push + readback) ⇒ потом `B`. Регистрация до submission в GitHub — достаточное, но не необходимое условие: submission не несёт информации об исходе (ICMJE: до первого участника, не до подачи заявки).

Отсюда два варианта controller:

- **B1 pre-submission broker** (исходная гипотеза): CLI/broker пишет intent, затем POST dispatch. Недостатки: нужен отдельный controller и credential, неоднозначный POST (`UNRESOLVED`), bypass через UI требует bind-before-measure всё равно.
- **B2 self-registration** (рекомендуется): первый job pilot workflow `register` (`contents: write`, без corpus) пишет запись для **собственного** `(run_id, run_attempt)` и читает её обратно; job `measure` (`needs: register`, `contents: read`) перед `B` проверяет запись. Ручной `Run workflow` — штатный путь; обойти регистрацию reviewed workflow нельзя; неоднозначного POST нет. Измерительный job ставится в очередь GitHub только после durable записи, так что порядок «ACK → submission измерения → измерение» выполняется на уровне job.

Crash matrix (B2; для B1 — в [proposal](../oracle/attempt-v2-proposal.md#b1-pre-submission-broker-альтернатива)):

| Случай | Запись | Исход в G1 | Почему корректно |
|---|---|---|---|
| run создан, `register` не стартовал (нет runner, cancel, concurrency, удалён) | нет | не attempt | `B` не пересечён, информации нет |
| push отклонён / ошибка до записи | нет | не attempt | `measure` не запускается |
| push принят, ответ потерян, job упал | есть | `PRE`, если provider показывает, что `measure` не стартовал; иначе `MISSING` | монотонно |
| записан, `measure` не стартовал (runner, cancel) | есть | `PRE` по jobs API | исключение до allocation, отчитано |
| `measure` стартовал, упал до `B` (checkout, admission) | есть | `PRE` по steps API (шаг `B` не начинался) | |
| `measure` убит после `B` | есть | `INCOMPLETE`/`MISSING` ⇒ NOT_PASSED | v1 |
| run удалён после `B` | есть | `MISSING` ⇒ NOT_PASSED (или исход retained bundle) | лемма 2 |
| artifact истёк до retention | есть | `MISSING` ⇒ NOT_PASSED | |
| run удалён, `PRE` не доказать | есть | `MISSING` ⇒ NOT_PASSED | консервативно |

Ни один случай не убирает попытку, пересёкшую `B`.

## 8. Reruns и identity hopping

Каждый `run_attempt` — отдельное исполнение. В B2 запись ключуется `(run_id, run_attempt)`, поэтому каждый rerun — **новая запись**, если он пересекает `B`.

| Вид rerun | Поведение GitHub | v2 |
|---|---|---|
| Re-run all jobs | новый `run_attempt`, тот же SHA/ref | `register` пишет `(run_id, n)`; полноправная попытка; не независимый repeat (v1: тот же run ID) |
| Re-run failed jobs | новый `run_attempt`; outputs успешных jobs предыдущей попытки переиспользуются ([docs](https://docs.github.com/en/enterprise-server@3.8/actions/managing-workflow-runs/re-running-workflows-and-jobs)) | `register` не повторяется ⇒ записи `(run_id, n)` нет ⇒ `measure` останавливается до `B` ⇒ не attempt. Штатно: только «Re-run all jobs» |
| Re-run one job | то же | то же |
| Новый dispatch после infra failure | новый `run_id` | новая запись; независимый repeat |

Infrastructure-only retry: попытки класса `PRE` остаются в истории и в отчёте, но не считаются ни неудачей, ни repeat. Попытки после `B` (включая cancel) — всегда в популяции. Retry не может исчезнуть: запись создаётся до `B`.

**Identity hopping (CE6) — дефект v1, не только v2.** `measured_source_sha` входит в identity, поэтому docs-коммит создаёт новую identity с пустой популяцией. Registry делает это видимым и дешёво закрываемым: `science_identity` = identity без `measured_source_sha` (тот же `oracle_code_sha256`, locks, phase). Предложение (решение maintainer, D3 в proposal): исходы `INVALID`, `REPEAT_MISMATCH` и `COMPLETE_WITH_FAILURES` любой записи переносятся на все identity той же `science_identity`; каждый G1 record перечисляет весь registry этой фазы. Смена кода (новая `science_identity`) остаётся легитимным путём «исправлять измерение» (P1 §6). Но она не должна молча обнулять серию: после любой natural попытки (не `PRE`) в фазе первая запись новой `science_identity` обязана нести **transition record** — `previous_science_identity`, `new_science_identity`, reviewed reason (`BUG_FIX | SEMANTIC_CHANGE | IMPLEMENTATION_CHANGE`) и ссылку на change review (PR и merge commit). Декларация лежит в reviewed коде на `measured_source_sha`, `register` job копирует её в запись до `B`, а без неё отказывается регистрировать. Старый `INVALID` не переносится через реальный bug fix, но переход виден в registry и в каждом G1 record (proposal §6, D3). Злонамеренный no-op в коде этим не остановить — только раскрыть и заставить назвать причину.

## 9. Нужно ли знать все GitHub runs

**Нет.** Требование «все GitHub dispatches известны» заменяется на «все записи registry известны и неизменяемы, и без записи измерение невозможно». GitHub inventory нужен только для reconciliation `запись ↔ provider run` и для доказательства `PRE`. Неполнота inventory в v2 может только блокировать PASS (лемма 2). Это центральный результат.

## 10. Варианты authoritative registry

| Вариант | Durability | Append-only | Tamper evidence | CAS / concurrency | Free | Зависит от GitHub | Secrets | Mobile | Вывод |
|---|---|---|---|---|---|---|---|---|---|
| Git branch в Shift-lab + ruleset | высокая | ruleset: нет force push/удаления для не-bypass; admin может снять | hash chain; Activity API видит force push; клоны, Software Heritage | fast-forward push атомарен | да | да | нет (`GITHUB_TOKEN`) | да | **V2-Minimal** |
| Custom ref `refs/delsk-attempts/*` | высокая | **нет**: rulesets покрывают только branches/tags | слабая | per-ref | да | да | нет | плохо видно | отвергнуто |
| Tag на попытку (ruleset на tags) | высокая | можно запретить update/delete | нет порядка без цепочки | нет общего CAS | да | да | нет | средне | хуже branch |
| Issue/comments | средняя | admin удаляет комментарии | edit history | нет | да | да | нет | хорошо | не authority |
| Releases / immutable releases | высокая | immutable после publish (admin выключает настройку) | средняя | нет | да | да | нет | средне | шумно, без выигрыша |
| Actions artifacts | 90 дней max | удаляются | нет | нет | да | да | нет | — | отвергнуто (исходная проблема) |
| S3 Object Lock (compliance) | высокая | даже root не удаляет до retention | да | conditional writes | платно | нет | да | плохо | избыточно для P1 |
| Cloudflare R2 | высокая | bucket locks / conditional PUT | частично | ETag CAS | free tier | нет | да | плохо | лишний vendor и secret |
| Внешняя БД | разная | зависит от вендора | нет без log | да | частично | нет | да | плохо | отвергнуто |
| Свой Merkle log + checkpoints | — | да | да | да | хостинг | — | ключ | плохо | V2-Hardened, только как witness |
| Sigstore Rekor (public good) | высокая | да | signed checkpoints, witnesses | — | да | нет | keyless OIDC из Actions | — | witness для V2-Hardened; search API в v2 нет |
| GitHub App controlled registry | высокая | как branch | как branch | как branch | да | да | App key | средне | лишняя идентичность без выигрыша в Minimal |
| Signed local request + remote ACK | — | — | — | — | — | — | ключ оператора | **нет** | противоречит mobile-only, ничего не добавляет к B2 |

Самый простой механизм, удовлетворяющий D1–D4 для honest-operator модели: **orphan branch `delsk/registry` в Shift-lab**, ruleset «restrict deletions» + «block force pushes» (без bypass), запись только из `register` job через `GITHUB_TOKEN`. Rulesets доступны в public repositories на GitHub Free ([docs](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/creating-rulesets-for-a-repository)).

## 11. Можно ли использовать сам Git

| Вопрос | Ответ |
|---|---|
| Удаление / rewrite ref | branch с ruleset: запрещено всем без bypass; admin может изменить или удалить ruleset. Custom refs rulesets не защищают |
| Кто имеет права | писать: write access, workflows с `contents: write`. Запрещать FF-push в registry не нужно: лишняя запись даёт только `MISSING` (DoS, не PASS). Но `contents: write` — permission на contents **всего репозитория**, не capability одной ветки ([workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)); см. §11.1 |
| Branch protection / force push | ruleset `non_fast_forward` + `deletion` |
| Reflog | у GitHub нет пользовательского reflog; [Repository Activity API](https://docs.github.com/en/rest/repos/repos#list-repository-activities) перечисляет `push`, `force_push`, `branch_deletion` с before/after. Retention не документирована — сигнал обнаружения, не authority |
| GitHub GC | достижимые коммиты не собираются; переписанная история становится недостижимой и со временем пропадает — поэтому нужен внешний snapshot |
| Discoverability | ветка видна в UI/API; `git fetch` read-only без credential |
| Race | push fast-forward = compare-and-swap на ref; проигравший делает fetch, проверяет, что его ключа нет, append, повтор. Concurrency group `delsk-experimental` и так сериализует pilot |
| Mobile / API | запись делает workflow; оператор только нажимает `Run workflow` |
| Malicious maintainer | может снять ruleset и переписать. Обнаружимо: Activity API, клоны, Software Heritage snapshot, уже retained bundles в `main` со ссылкой на digest записи. Не предотвращаемо в одном trust domain |

### 11.1 Write surface `register` job

`GITHUB_TOKEN` с `contents: write` может писать в **любую** ветку и tag репозитория, которые не защищены ruleset. На 2026-10-05 у Shift-lab rulesets = `[]`, `main` не защищён. Значит, ошибочный или скомпрометированный `register` job мог бы не только добавить запись в registry, но и изменить `main` (frozen contract, locks, retained evidence) или создать ветку/tag с подменённым кодом. Для научной модели это опаснее DoS: правка frozen файлов или evidence root в `main` меняет то, на что опираются identity и G1.

Обязательные условия **до** активации v2 (входят в activation criteria proposal):

1. Registry ruleset: target `refs/heads/delsk/registry`, `deletion` + `non_fast_forward`, bypass list пуст.
2. Ruleset на `main` (и на ветки/tags с frozen scientific bytes, если появятся): `deletion`, `non_fast_forward`, изменения только через pull request. Тогда direct push workflow token в `main` отклоняется сервером.
3. `register` job: `permissions: contents: write`, все остальные scopes не указаны (по правилам GitHub они становятся `none`); checkout с `persist-credentials: false`; token передаётся только шагу push; corpus, codecs и сторонние actions в этом job не исполняются.
4. Hardcoded registry: remote URL, ref `refs/heads/delsk/registry` и форма дерева (orphan tree ровно с `genesis.json` и `entries.jsonl`) — константы reviewed кода; push только явным refspec `HEAD:refs/heads/delsk/registry`; любая другая форма дерева при readback = отказ.
5. Synthetic negative test на реальном GitHub до natural pilot: тот же `register` credential пытается push в `main`, удалить registry, сделать non-FF push в registry — все три попытки отклонены сервером; результат сохраняется как evidence активации.

Остаточный риск после 1–5: credential может создавать новые незащищённые ветки. Это не влияет на G1, потому что попытки привязаны к `measured_source_sha` reviewed commit, а retention идёт только через reviewed PR в защищённый `main`.

Вывод: Git **достаточен** для honest-operator модели (D1 выполняется против всех, кроме admin) и **недостаточен** против malicious admin без внешнего witness. При единственном участнике org admin и оператор — одно лицо, поэтому защита от admin — это защита для третьих лиц (publishable), а не для внутренних решений.

## 12. Transparency log и witness

Hash chain `entry_n = H(entry_{n-1} ‖ …)` доказывает целостность префикса, но не наличие хвоста: усечение до `n-1` даёт валидную цепочку. Нужен внешний свидетель последнего head.

| Уровень | Механизм | Окно необнаружимого rollback | Стоимость |
|---|---|---|---|
| 0 | только ruleset | admin в любой момент | 0 |
| 1 | head digest в каждом retained sidecar в `main` (reviewed PR) + Activity API | между записью и следующим retention PR | 0, уже в плане |
| 2 | Software Heritage Save Code Now перед G1 verdict; G1 record требует, чтобы SWH snapshot ветки registry был префиксом оцениваемого head | до snapshot | 0, асинхронно, rate limited |
| 3 | `register` job подписывает checkpoint keyless (Sigstore, GitHub OIDC); inclusion proof хранится в записи и проверяется до `B` | witness Rekor; enumeration — по своим proofs, не search | без secrets, внешняя зависимость |
| 4 | независимый witness cosigning (C2SP), второй trust domain | ≈0 | второй оператор/сервис |

Для P1 сейчас нужен уровень 1 (бесплатен, уже совпадает с retention flow); уровень 2 — для publishable; 3–4 — для release claims.

## 13. Provider injection (`get=fake`)

Сегодня `oracle_attempts.g1_root(..., get=None, resolve_source=None)` принимает injectable provider. Это безопасно только пока `DISPATCH_HISTORY_UNVERIFIED` безусловно блокирует PASS. v2 обязан:

1. production entry point без провайдерских параметров: `g1_production(identity)` сам строит клиента к `https://api.github.com`, repository и registry ref — константы модуля;
2. registry читается `git fetch` с фиксированного remote URL, не из переданного пути;
3. fakes живут только в test-модуле и вызывают `_g1_core`, который возвращает `TEST_ONLY_*` и **не** имеет кода, выдающего `PASS`;
4. `PASS` выдаёт только `g1_production` после `_g1_core`; test vector проверяет сигнатуру (`inspect.signature`) и то, что core никогда не возвращает `PASS`;
5. G1 record содержит registry head SHA, provider base URL и evaluator SHA — сторонний verifier пересчитывает.

## 14. KAT authority

Exact-commit KAT через Actions API (`kat_verified`) — другая trust problem: KAT детерминирован на synthetic данных и **переисполним** на том же commit в любой момент. Удалённый красный smoke run — тот же класс пробела, что и dispatch, но с низким риском: результат можно воспроизвести. Вывод: **GitHub KAT API достаточен** как verification signal; registry для KAT не нужен. Опциональное упрощение без доверия к истории: G1 evaluation job исполняет KAT suite на evaluator commit в том же job. Signed CI attestation KAT — только V2-Hardened.

## 15. Adversary model и уровни evidence

| Уровень | Назначение | Adversary | Механизм |
|---|---|---|---|
| Exploratory | отладка, synthetic | никакой | smoke, без G1 |
| Internal decision | G1 → DELSK-004 → выбор Hx | honest-but-fallible оператор, crash/infra, non-admin writers и автоматизация | **V2-Minimal** |
| Publishable | статья, внешний отчёт | + сомневающийся рецензент | V2-Minimal + уровень 2 (§12) + полный registry в отчёте |
| Production/release claim | обещания пользователям | + malicious admin | V2-Hardened |

**Delsk P1 обязан защищаться от honest-but-fallible оператора и crash/infra adversary, включая ошибочные ручные dispatch, reruns, удаление runs любым write-access и потерю artifacts.** Malicious admin вне scope P1 явно, потому что: (1) единственный участник org — сам экспериментатор; preregistration как commitment device работает и в этом случае (Nosek et al.); (2) публичные inputs позволяют admin любые частные вычисления независимо от provenance; (3) защита требует второго trust domain. Это **явное протокольное решение**, записанное в proposal, а не обход.

## 16. Threat model

| Угроза | V2-Minimal | Механизм |
|---|---|---|
| cherry-picking runs | prevent | популяция из registry; bind-before-measure |
| удаление failed GitHub run | fail-closed | `MISSING ⇒ NOT_PASSED` |
| unregistered manual run | prevent | reviewed workflow регистрирует себя (B2) или останавливается до `B` |
| регистрация после исхода | prevent | без записи до `B` нет измерения; `UNBOUND_MEASUREMENT` |
| duplicate registration | detect → fail-closed | ключ `(run_id, run_attempt)` уникален; повтор = `REGISTRY_DUPLICATE` |
| retry laundering | prevent | rerun после `B` — новая запись в популяции |
| controller crash | fail-closed | crash matrix §7 |
| lost POST response | n/a в B2; в B1 fail-closed + bind-before-measure | |
| forged registry entry | fail-closed | лишняя запись без evidence = `MISSING` |
| rewriting registry history | prevent (non-admin) / detect (admin, уровни 1–2) | ruleset; witness |
| stale writer | prevent | FF-only CAS |
| replay | prevent | binding к `(run_id, run_attempt)`, digest записи, source SHA |
| fabricated bundle | detect | provider binding, bundle verify, checksums от artifact API; V2-Hardened: attestation |
| bundle unregistered run | prevent | `EVIDENCE_ROOT_INVALID` |
| mismatched source SHA | prevent | binding check → `BINDING_MISMATCH` (INVALID) |
| fake provider в production | prevent | §13 |
| compromised `GITHUB_TOKEN` (`register` job) | prevent при условиях §11.1; иначе **unresolved** | `contents: write` действует на весь репозиторий: без rulesets token мог бы изменить `main` (frozen files, evidence root). §11.1 п. 1–5 обязательны до активации; после них остаются только лишние записи registry (DoS → `MISSING`) и незащищённые новые ветки, не влияющие на G1 |
| молчаливый сброс серии сменой кода | detect / fail-closed | transition record обязателен до `B` первой записи новой `science_identity`; без него `register` отказывает, G1 даёт `SERIES_TRANSITION_MISSING` |
| compromised admin token | unresolved в Minimal; detect в Hardened | |
| operator error (не тот rerun, не тот branch) | fail-closed | неверный путь останавливается до `B` |

## 17. Два проекта

| | V2-Minimal | V2-Hardened |
|---|---|---|
| Guarantees | теорема §4.2 против honest-but-fallible оператора, crash, non-admin; ни одна потеря provider данных не даёт PASS | + обнаружение rollback/rewrite admin с окном ≈ время до checkpoint; provenance bundle переживает удаление run |
| Infra | orphan branch; rulesets на registry и на `main` (§11.1); два jobs в pilot workflow | + Sigstore keyless checkpoints/attestations (`id-token: write`, `attestations: write`), witness/SWH, OIDC-проверка claims |
| Объём (оценка) | ~150–250 строк Python (registry validate/append, population, `PRE` классификация) + ~80 строк workflow + R-vectors; удаляется inventory-as-completeness | +200–400 строк и внешняя зависимость |
| Operational cost | 0 secrets, 0 $, одно нажатие `Run workflow` | 0 $, внешние сервисы без SLA |
| Failure modes | admin снимает ruleset; ruleset на `main` не настроен — workflow token получает write surface всего репозитория (§11.1); GitHub недоступен (нет записи ⇒ нет измерения) | + недоступность Rekor/witness блокирует измерение |
| Защищает | всё из §16, кроме admin | + admin rewrite, удалённый provider run для bundle authenticity |
| Не защищает | malicious admin; частные вычисления на публичных inputs | частные вычисления на публичных inputs; сговор admin и witness |

**Рекомендация: V2-Minimal сейчас**, с уровнем 1 witness (digest head в retained sidecars) бесплатно. Уровень 2 включить перед любой публикацией. V2-Hardened — только при внешних release claims или появлении второго maintainer.

## 18. Milestone для Rust

Rust `delsk-core` (Cargo.toml, crates, FFI, SIMD, index, sketch) **не начинается**, пока не существует всё перечисленное:

1. принятый и замороженный provenance/G1 path (v2 freeze record в `main`);
2. natural oracle G1 = `PASS` (G1 record с registry head, двумя независимыми run ID, KAT);
3. DELSK-004 baseline matrix на том же `C_t` с retained rows и CIs по calibration;
4. измеренное окно: лучший дешёвый baseline (size/recency/git-like/MinHash/FracMinHash/Finesse/trial-encode, см. [prior art update](DELSK-PRIOR-ART-UPDATE-2026-10.md)) не достигает G3 thresholds либо оставляет p95 regret, который Hx предсказывает сократить;
5. выбранная гипотеза Hx с заранее записанным prediction и Python reference prototype, показавшим эффект на calibration.

До этого Rust — premature optimization/productization.

## 19. Ответы

1. **Нужен ли `delsk.oracle-contract.v2`?** Да. Меняется определение G1-популяции (v1 §7, §12), а v1 §0 требует новую версию для изменения evaluator/failure semantics. v2 — тонкий слой: measurement layer v1 включается по hash без изменений, включая `contract_id` внутри `measurement_identity` (иначе меняются frozen schemas `const`).
2. **Научно корректно ли считать attempt только после durable preregistration?** Да, если граница — информационная (`B`), измерение без записи невозможно (bind-before-measure), запись неудаляема, а отсутствие evidence = NOT_PASSED. Без bind-before-measure — нет (CE1).
3. **Нужно ли знать все GitHub runs?** Нет. Inventory — только reconciliation и доказательство `PRE`.
4. **Unregistered runs?** Model 1: не attempts, неприемлемы как evidence, в results root — `EVIDENCE_ROOT_INVALID`. Reviewed workflow не даёт им пересечь `B`.
5. **Reruns?** Каждый `run_attempt`, пересёкший `B`, — новая запись в популяции, не независимый repeat. Только «Re-run all jobs»; failed-job rerun останавливается до `B`. `PRE`-попытки отчитываются, но нейтральны.
6. **Adversary model P1?** Honest-but-fallible оператор + crash/infra + non-admin writers. Malicious admin — явно вне scope P1, обязателен для release claims.
7. **Минимальный registry?** Orphan branch `delsk/registry` в Shift-lab, ruleset без force push/удаления, hash-chained JSON entries, запись из `register` job (только `contents: write`, hardcoded ref и форма дерева). Обязателен и ruleset на `main`: `contents: write` действует на весь репозиторий (§11.1).
8. **Нужен ли внешний сервис?** Нет для internal decision. Для publishable — бесплатный Software Heritage snapshot; для release — Sigstore/witness.
9. **Что reuse без изменений?** Codec lock, conformance C01–C14 и golden, schemas, evaluator scientific logic, K01–K42, G01–G09 (ядро `g1`), M01–M30, metamorphic, frame/oracle/metrics/sealing, `C_t`, locks, thresholds. Slice A/B не повторяются.
10. **Новые vectors?** R01–R22 и mutants PM01–PM10 (proposal §8): цепочка registry, population, `PRE`, binding, reruns, carry-over, transition records, injection; плюс synthetic negative test write surface (§11.1 п. 5).
11. **Когда снять `DISPATCH_HISTORY_UNVERIFIED`?** Никогда для v1 G1. В v2 production path он заменяется на `REGISTRY_BINDING_REQUIRED` только после: freeze v2, настроенных и проверенных через API rulesets на registry и `main` (§11.1), negative test write surface, genesis registry, synthetic registry dry-run на реальном GitHub (UI dispatch, rerun all, rerun failed, cancel, удаление synthetic run → NOT_PASSED) и review.
12. **Когда natural oracle?** После п. 11 и отдельного подтверждения maintainer.
13. **Baselines сразу после G1?** random-seed, size-closest, recency/lineage order, git-like (size sort + window, path/name hash), bottom-k MinHash resemblance и containment, FracMinHash containment, SimHash, TLSH, LZJD/ssdeep, Finesse и Odess (reimplemented, с маркировкой), trial-encode proxy (дешёвый delta encode как scorer); затем BePro/SpeedSketch при CLEAR лицензии.
14. **Evidence перед Rust?** §18: v2 freeze, G1 PASS record, DELSK-004 matrix с CIs, измеренное окно над лучшим baseline, Hx с prediction и Python prototype.
