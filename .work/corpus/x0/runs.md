# DELSK-002 X0: журнал dispatch

Каждый dispatch `delsk-screening.yml`, включая failed, cancelled и отклонённые до compute, записывается сюда в порядке запуска. Строки не удаляются и не переписываются; исправление — новая строка. Правила — [README](README.md) §8.

| # | Run, attempt | Source | Итог | Evidence |
|---|---|---|---|---|
| 1 | [37449333091](https://github.com/definitely-stable/Shift-lab/actions/runs/37449333091), 1 | `1a1efaa` | `success`: 1 841 пар `ok`, conformance PASS, verdict `NO_HEADROOM_AT_256` | [results](results.md), `.work/results/DELSK-002-X0/37449333091-1/` |
