# DELSK-004 Slice A: результаты (pilot-v1, exploratory)

Контракт: [contract.md](contract.md) (`delsk.baselines.slice-a.v1`, params SHA-256 `2e58c0609879d0a3b9f0840f84ae3bf2feff556c7a79946228973e4bbccc8873`). Oracle: retained bundle `37434946174-1` контракта v4 (G1 PASS). Run: [37443926816](https://github.com/definitely-stable/Shift-lab/actions/runs/37443926816), attempt 1, source `ce377aaaa75b141690a6a2f8d2384806b5540b53`. Artifact digest: `sha256:ecb3c6a6b3e0af41efdcfd44339e84cd8269cc6d434d831c179e8aa05270adc5`. Retained файлы: [`.work/results/DELSK-004-BASELINES-A/37443926816-1/`](../results/DELSK-004-BASELINES-A/37443926816-1/).

**Verdict: `INCONCLUSIVE` для G2 (exploratory, нет headroom на pilot).** Это таблица baselines, а не сравнение с Delsk.

## Проверки

- Population полная: development 43 targets (37 с useful delta), calibration 12 (10), 1855 пар. Evaluation split не читался.
- `rows.jsonl` и `summary.json` пересчитываются локально из `rankings.jsonl` и retained oracle bundle байт в байт. Со вторым G1-bundle (`37434993046-1`) метрики те же.
- Descriptors: 1458 объектов, 159 MB, 63 s CPU на все bottom-k sketches (k = 128). Это информационная оценка, а не timing benchmark.

## Таблица (K = 1 и 8)

SavingsCapture дан с 95 % cluster-bootstrap интервалом по lineages. Calibration — одна lineage, поэтому её интервал вырожден.

| Split | Метод | Budget, B | K | Useful Recall | Strict Recall | SavingsCapture [95 % CI] | Normalized regret p95 |
|---|---|---|---|---|---|---|---|
| development | `containment` | 64 | 1 | 0.865 | 0.837 | 0.989 [0.987, 1.000] | 0.569 |
| development | `containment` | 64 | 8 | 1.000 | 0.953 | 1.000 [1.000, 1.000] | 0.000 |
| development | `containment` | 1024 | 1 | 0.973 | 0.930 | 1.000 [1.000, 1.000] | 0.000 |
| development | `containment` | 1024 | 8 | 1.000 | 0.977 | 1.000 [1.000, 1.000] | 0.000 |
| development | `git_like` | — | 1 | 0.703 | 0.628 | 0.995 [0.965, 0.999] | 16.677 |
| development | `git_like` | — | 8 | 0.973 | 0.884 | 1.000 [1.000, 1.000] | 0.000 |
| development | `minhash_resemblance` | 64 | 1 | 0.865 | 0.837 | 0.989 [0.987, 1.000] | 0.569 |
| development | `minhash_resemblance` | 64 | 8 | 1.000 | 0.953 | 1.000 [1.000, 1.000] | 0.000 |
| development | `minhash_resemblance` | 1024 | 1 | 1.000 | 0.953 | 1.000 [1.000, 1.000] | 0.000 |
| development | `minhash_resemblance` | 1024 | 8 | 1.000 | 0.977 | 1.000 [1.000, 1.000] | 0.000 |
| development | `previous_version` | — | 1 | 1.000 | 0.907 | 1.000 [1.000, 1.000] | 0.000 |
| development | `previous_version` | — | 8 | 1.000 | 1.000 | 1.000 [1.000, 1.000] | 0.000 |
| development | `random` | — | 1 | 0.135 | 0.116 | 0.035 [0.002, 0.324] | 116.966 |
| development | `random` | — | 8 | 0.459 | 0.395 | 0.960 [0.854, 0.974] | 91.251 |
| development | `size_closest` | — | 1 | 0.486 | 0.442 | 0.985 [0.907, 0.997] | 94.242 |
| development | `size_closest` | — | 8 | 0.649 | 0.581 | 0.992 [0.934, 0.998] | 50.477 |
| calibration | `containment` | 64 | 1 | 0.900 | 0.833 | 1.000 [1.000, 1.000] | 0.228 |
| calibration | `containment` | 64 | 8 | 1.000 | 0.917 | 1.000 [1.000, 1.000] | 0.000 |
| calibration | `containment` | 1024 | 1 | 0.900 | 0.917 | 1.000 [1.000, 1.000] | 0.109 |
| calibration | `containment` | 1024 | 8 | 1.000 | 1.000 | 1.000 [1.000, 1.000] | 0.000 |
| calibration | `git_like` | — | 1 | 0.700 | 0.667 | 0.994 [0.994, 0.994] | 13.168 |
| calibration | `git_like` | — | 8 | 1.000 | 0.917 | 1.000 [1.000, 1.000] | 0.000 |
| calibration | `minhash_resemblance` | 64 | 1 | 0.900 | 0.833 | 1.000 [1.000, 1.000] | 0.228 |
| calibration | `minhash_resemblance` | 64 | 8 | 1.000 | 0.917 | 1.000 [1.000, 1.000] | 0.000 |
| calibration | `minhash_resemblance` | 1024 | 1 | 1.000 | 1.000 | 1.000 [1.000, 1.000] | 0.000 |
| calibration | `minhash_resemblance` | 1024 | 8 | 1.000 | 1.000 | 1.000 [1.000, 1.000] | 0.000 |
| calibration | `previous_version` | — | 1 | 1.000 | 0.917 | 1.000 [1.000, 1.000] | 0.000 |
| calibration | `previous_version` | — | 8 | 1.000 | 0.917 | 1.000 [1.000, 1.000] | 0.000 |
| calibration | `random` | — | 1 | 0.400 | 0.417 | 0.962 [0.962, 0.962] | 14.764 |
| calibration | `random` | — | 8 | 0.400 | 0.417 | 0.969 [0.969, 0.969] | 13.168 |
| calibration | `size_closest` | — | 1 | 0.400 | 0.417 | 0.962 [0.962, 0.962] | 14.764 |
| calibration | `size_closest` | — | 8 | 0.600 | 0.583 | 0.979 [0.979, 0.979] | 14.764 |

Полные строки (K = 1, 4, 8, 16, все budgets 64–1024 B, ε-recall, macro, encoder-call reduction) — в `summary.json`.

## Что это значит

1. **Pilot насыщен дешёвыми методами.** `previous_version` (путь + порядок релизов) уже при K = 1 даёт на development Useful Recall 1.000 и SavingsCapture 1.000. Bottom-k MinHash на 1024 B при K = 1 — тоже 1.000/1.000, а на 64 B при K = 4. Random и size-closest заметно хуже: при K = 1 normalized regret p95 > 90 на development. Поэтому метрики различают методы, и насыщение лучших — свойство корпуса.
2. **Причина — состав pilot-v1.** Шесть C-проектов по три релиза, где у большинства targets есть база с тем же путём из соседнего релиза. Это проверка plumbing, а не репрезентативный корпус ([corpus-and-baselines](../corpus-and-baselines.md)).
3. **G2 на pilot не проверяем.** Для любого selector (включая Delsk) нет измеримого headroom над `previous_version` и MinHash 1024 B. По протоколу §6 это не stop, а `INCONCLUSIVE`: lineages мало (6, calibration 1), а корпус не содержит трудных случаев.
4. **Выбор сильнейшего baseline.** По preregistered правилу (calibration SavingsCapture при K = 8) им стал `git_like`. Но при K = 8 у нескольких методов ничья на 1.000, и решил её tie-break по имени. Правило насыщается. Менять его постфактум нельзя: следующий срез должен заранее зарегистрировать критерий, различающий методы (например, K = 1 и normalized regret p95).

## Что дальше

- Расширение корпуса до G2 (DELSK-002 expansion): targets без path/версионной подсказки, бинарные артефакты, архивы, межфайловые и межпроектные кандидаты, hard negatives. Без этого любая разница методов не измерима.
- Следующие срезы baselines (prior art §3, п. 3–6) имеют смысл только на расширенном корпусе.
