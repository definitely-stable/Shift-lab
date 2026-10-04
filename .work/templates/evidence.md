# Evidence record

Этот файл — шаблон. До run не заменять unknown outcomes предполагаемыми результатами.

## Identity

Experiment / hypothesis / issue; protocol commit; measured source SHA; evaluator SHA; GitHub run URL + ID + attempt; UTC timestamps; host labels/image/CPU/ISA; corpus/candidate/tool/scorer hashes.

## Validity

Expected/actual pairs; missing/failed/unsupported/excluded counts с причинами; decode correctness; split leakage audit; noise result; executed architectures; artifact identity/hash/expiry. Любое нарушение и допустимость только части evidence указать до таблицы качества.

## Results

Per-domain и per-lineage counts; strict/useful/epsilon recall; bytes и normalized p50/p95 regret; savings captured; standalone wins; candidate encodes; retrieval vs reranker loss; build/query/index/total costs; baseline contrasts и 95% CI. `N/A` и малые sample sizes показывать явно.

## Verdict

`ACCEPT/REJECT/INCONCLUSIVE/INVALID`, каждый gate → observed evidence → решение. Отдельно limitations и какие claims не проверены. Отрицательный результат сохраняется наравне с положительным.

## Recompute / replay

Retained compact file inventory с SHA-256, exact evaluator command, input row counts, protocol/source/analysis hashes. Ссылка на большие raw artifacts и immutable corpus recipes. Пересчёт из compact metrics и полный повтор encoder runs — разные уровни воспроизведения.

## Next action

Связанная follow-up issue или обоснованный stop/pivot; изменения production/format по умолчанию отсутствуют, пока отдельная интеграционная задача не принята.
