# SFIC quant allocation: momentum model rebuild and v2 tests

Rebuilds the SFIC long-only momentum sleeve (15 stocks, 70% 180-day momentum / 30% 52-week-high nearness, monthly rebalance)
from the original spec and tests four proposed improvements ("layers") one at a time. Rigor over Sharpe: honest point-in-time
universe, no look-ahead, fixed parameters, every trial logged.

**Headline: the pitch's ~1.7 Sharpe does not reproduce (rebuilt baseline = 0.91 over 2002-present vs 0.48 for the benchmark), and layer 1 (rank-average signal) hurts.**
Layer 3 (rank buffer + swap cap) brings trades within the <= 20/quarter promise at no Sharpe cost. See `docs/RESULTS.md`.

## Layout
```
config.yaml        global frozen parameters (data, universe, signals, costs, periods, stats)
configs/           one YAML per model (baseline, 2b, 4b): which layers are on
run_model.py       runs any config:  python run_model.py configs/4b.yaml [--costs 0 5 10]
src/               data.py (single data interface) universe.py signals.py portfolio.py backtest.py metrics.py models.py
scripts/           stage runners (run_stage1/2/3, run_diagnostics), dedupe_trials, make_results_md, verify_models, export_data
tests/             no-look-ahead, buffer / swap cap / sector cap, weight cap, quality filter, determinism
results/<stage>/   outputs per stage; results/trials_log.csv = one row per (trial tag, cost)
docs/              RESULTS.md (all models), DECISIONS.md, CAVEATS.md
data/              caches (parquet, git-ignored) + small reference files
```

## Reproduce
```bash
pip install -r requirements.txt
python -m scripts.run_stage1          # download prices (Yahoo, slow, rate-limited), build point-in-time universe, coverage report
python -m scripts.fetch_sectors       # today's sectors
python -m pytest tests                # no-look-ahead and layer unit tests
python run_model.py configs/baseline.yaml configs/2b.yaml configs/4b.yaml
python -m scripts.verify_models       # configs reproduce the diagnostics run bit-for-bit
python -m scripts.run_stage2; python -m scripts.run_stage3; python -m scripts.run_diagnostics   # earlier stages / full 14-variant table
python -m scripts.dedupe_trials; python -m scripts.make_results_md                               # tidy log, regenerate docs/RESULTS.md
```
Yahoo data drifts slightly between downloads, so a fresh download may not match the committed numbers exactly. `python -m scripts.export_data` bundles the exact inputs used here (about 124 MB zip, not in git).

## Models
| config | model |
|---|---|
| `baseline` | original pitch: 10 by 180-day return + 5 by 52-week-high nearness, equal weight |
| `2b` | baseline + layer 3 (rank buffer: keep while top-18 momentum / top-7 high; max 6 swaps) |
| `4b` | baseline + layer 2 (inverse-vol, 4/sector, quality filter, 10% weight cap) + layer 3 |

Layers: L1 rank-average signal, L2 inverse-vol weights + sector cap, L3 rank buffer + swap cap, L4 vol-target overlay (L4 is the next step).
