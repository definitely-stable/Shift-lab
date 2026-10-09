# H12-A — pinned first-attempt ROI sensitivity preflight (NOT a product verdict)

Tracks [issue #59](https://github.com/definitely-stable/Shift-lab/issues/59) and [DELSK-013](https://github.com/definitely-stable/Shift-lab/issues/14). This slice **does not run new measurements** and does not retroactively alter S4-C scientific gates. Original source: [S4-C retained evidence](../results/SELECTOR-S4C/README.md), first-attempt A/B/evaluator on pinned ChunkShift and bzip2 E1.

The tool `../tools/h12_roi_preflight.py` pins SHA-256 of retained original `evaluation/result.json`, `A/timing.json`, `B/timing.json`; checks the scientific verdict, 109199 vs 107263 physical CSP bytes, exactly 7 alternating paired timing rounds, and computes per-repeat median **absolute** additional create CPU and wall seconds from paired timing differences (not a ratio approximation). Only explicitly supplied **nonnegative scenario prices** are accepted; no universal prices are assumed.

Demonstration with hypothetical prices (not claimed market rates):

```bash
python3 .work/tools/h12_roi_preflight.py \
  --cpu-price-per-second 0.1 \
  --egress-price-per-byte 0.00001 \
  --extra-lifecycle-cost 0 \
  --mode shared-release
```

Run again with `--mode customized-per-recipient` to model one extra encode cost per recipient rather than amortized shared artifact creation. Optional `--wall-deadline-penalty-per-second` is a genuinely **independent latency opportunity cost**, default zero to avoid CPU + wall double-charging. Extra lifecycle cost is a scenario parameter, **not a measured index storage/RSS/build value**.

The strict win criterion is **net modeled cost < 0**, *never* a zero-difference tie. For shared release, the strict first integer fanout is `floor((CPU_cost+wall_penalty+lifecycle_cost)/(bytes_saved*egress_price)) + 1` when the denominator is positive. Customized encoding pays extra CPU/wall on every delivery; `N` cannot rescue a nonpositive per-delivery margin.

**Not acceptance evidence:** bzip2 E1 is opened and modeled as an **identical nine-target aggregate release per delivery**. Real patch transfer volumes, heterogeneous clients, peak RSS, discarded trial I/O, metadata persistence, cache hits, latency distributions, failure accounting and fresh multi-family measurements are unknown. The output's result is always `DESCRIPTIVE_ONLY_NOT_H12_ROI_ACCEPTANCE`. H12-B must preregister independent population and success gates first.
