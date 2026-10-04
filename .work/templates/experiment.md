# Experiment preregistration

Этот файл — шаблон, не frozen experiment. Скопировать в конкретный issue/protocol record и заполнить до decision run.

- Experiment ID и owning issue; hypothesis ID; owner.
- Статус `PLANNED/FROZEN`; protocol version и commit; дата freeze.
- Один главный вопрос и primary endpoint; practical effect threshold и stop/pivot.
- Candidate/baseline implementations, commit, license, build/runtime/options hashes.
- Corpus/object/candidate manifests и SHA-256; track; unit size; lineage splits; число независимых families.
- Codec и standalone policy; patch/wrapper/base metadata accounting; ties/failures/empty cases.
- Descriptor byte budgets, K/M, retrieval caps; одинаковый tuning budget.
- Разрешённые calibration trials; выбранный scorer lock; запрет evaluation tuning.
- Paired order, warmups/rounds, cache mode, noise gate; statistical unit/CI/contrasts/correction.
- Actions workflow/source ref; hard time/RAM/disk/pair caps; ожидаемые runner-minutes и artifact bytes.
- Expected rows и completeness assertions; decoder verification; cross-platform support.
- Exact invocation и inputs; source/workflow/evaluator SHA; evidence bundle paths.
- Вердикты `ACCEPT/REJECT/INCONCLUSIVE/INVALID` и следующий шаг для каждого.
- Amendment log: что и почему менялось; было ли evaluation уже просмотрено.
