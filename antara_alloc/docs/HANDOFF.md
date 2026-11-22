# Handoff: SFIC Allocation Strategies

Antara Chhabra

> **Note for the repository copy.** This guide was written for the handout package, which also contains the data folders. In this repository, `data/training/` and `data/test_holdout/` are not stored in git because of their size and Yahoo's redistribution terms. Build them with the scripts in section 9 (or use the handout package), then follow the steps below from the `antara_alloc/` folder. In this copy the guide lives in `docs/`, next to `PROJECT_SPEC.md` and the report.

This folder has everything needed to run, test and improve the three strategies from my report: the shared backtest code, the code for each strategy, the cleaned data and the scripts that rebuild it. The report explains the reasoning and the results. This file explains how the code is set up, what each strategy does and where its code lives. It also sets out the exact order in which a new or improved strategy should be built and tested.

## 1. Quick start

I used Python 3.11.

```bash
cd antara_alloc
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.lock
export PYTHONPATH="$PWD"
chmod -R 000 data/test_holdout
python -m pytest -q
```

- `PYTHONPATH` needs to point at this folder so that `import common` and `import strategy_...` work from anywhere. Set it in every new terminal.
- The `chmod` line locks the holdout data so nothing can read it during development (section 5).
- The tests should show 24 passed and 1 skipped. The skipped test compares the benchmark against the raw downloads, which are not included.

## 2. What is in this folder

```text
antara_alloc/
├── README.md                   overview of this folder
├── requirements.txt            packages used
├── requirements.lock           exact versions (install this one)
├── pytest.ini
├── config/                     shared rules: splits.yaml, costs.yaml, universe.yaml, data_sources.yaml
├── common/                     shared code (section 6)
├── data/
│   ├── scripts/                download.py, build_processed.py, build_membership.py, split.py
│   ├── training/               cleaned data from 1997-01-02 to 2019-12-31 (warm-up, fit and validation years)
│   ├── test_holdout/           cleaned data from 2020-01-01 to 2026-11-16 (lock it, see section 1)
│   └── membership/             S&P 500 membership by date
├── docs/                       PROJECT_SPEC.md (rules), HANDOFF.md (this guide), the report PDF
├── logs/                       decision_log.md, data_log.md, holdout_access.log, final_results.md
├── strategy_1_residual_momentum/
├── strategy_2_vol_managed/
├── strategy_3_combined/
└── tests/                      checks for look-ahead, isolation and data quality
```

Every strategy folder has the same layout:

| Folder | What it holds |
| --- | --- |
| `src/` | The strategy code. `src/entrypoint.py` has the `run(cfg, loader)` function. |
| `configs/` | One YAML file per version that was tested. |
| `scripts/` | Scripts that fit constants and run validation (Strategies 2 and 3). |
| `logs/STATUS.md` | Where the strategy stands, its current numbers and open issues. |
| `logs/preregistration.md` | What was decided before validation: the main version, the alternatives and the selection rule. |
| `logs/run_registry.csv` | Every run, one line each. |
| `outputs/frozen/` | The frozen config, its freeze record and its validation results. |
| `outputs/holdout/` | Holdout results. Each strategy has two runs: the first with the old stock list and the later, corrected one. |

The individual run folders (`runs/`) are not included, since they can be regenerated and take up about 45 MB.

## 3. The three strategies

| | Strategy 1 | Strategy 2 | Strategy 3 |
| --- | --- | --- | --- |
| Name | Residual momentum | Volatility-managed baseline | Combination |
| What it does | Picks the 15 stocks with the strongest company-specific momentum | Holds the fund's current picks but invests less after volatile months | Strategy 1's picks with Strategy 2's volatility rule |
| Folder | `strategy_1_residual_momentum/` | `strategy_2_vol_managed/` | `strategy_3_combined/` |
| Main code | `src/signals.py`, `src/entrypoint.py` | `src/baseline.py`, `src/overlay.py`, `src/entrypoint.py` | `src/entrypoint.py`, `src/s1_frozen/`, `src/s2_frozen/` |
| Frozen config | `outputs/frozen/config.yaml` (same as `configs/v1_unscaled.yaml`) | `outputs/frozen/config.yaml` (same as `configs/primary_pit.yaml`) | `outputs/frozen/config.yaml` (same as `configs/primary_pit.yaml`) |
| Rebalancing | Monthly | Monthly | Monthly |
| Holdout Sharpe, 2020 to Nov 2026 | 0.61 | 0.41 | 0.34 |
| Validation Sharpe, 2015 to 2019 | 0.57 | 0.31 | 0.44 |

The SFIC benchmark had a holdout Sharpe of 0.56 and a validation Sharpe of 0.79. The rebuilt baseline (the fund's current model without the volatility rule) had a validation Sharpe of about 0.41 to 0.44. All figures are after 10 basis points per side on a 1% allocation of about $15,400. More detail is in `logs/final_results.md` and in each strategy's `logs/STATUS.md`.

### 3.1 Strategy 1: Residual momentum

**What it does.** At the end of each month, for every eligible stock with 36 months of history, it regresses the stock's monthly excess return on the market, size and value factors. It adds up the residuals from the 11 months before the most recent month (the 12-1 window), ranks the stocks on that sum and buys the top 15 in equal amounts.

**Files.**
- `src/signals.py`: `monthly_returns`, `residual_momentum_scores` (the regression and the score), `baseline_scores` and `pick_baseline` (the rebuilt fund model), `pick_top`.
- `src/entrypoint.py`: `build_targets` (monthly weights), `backtest` and `run`. `cfg["model"]` is `residual_momentum` or `baseline_70_30`.
- `src/run_experiments.py`: runs any config on fit or validation, logged.
- `configs/`: `primary.yaml` (paper version, scores divided by residual volatility), `v1_unscaled.yaml` (frozen), `v2_buffer30.yaml` (keeps held stocks while in the top 30), `baseline_monthly.yaml`, `baseline_2monthly.yaml`.

**Frozen settings.** `reg_months: 36`, `mom_months: 11`, `skip_months: 1`, `standardize: false`, `n_holdings: 15`, `every_n_months: 1`.

**Run it.**

```bash
python -m strategy_1_residual_momentum.src.run_experiments --config v1_unscaled --split validation \
    --purpose "why this run" --hypothesis "what you expect" --sensitivity
```

`--split fit` scores 2000 to 2014 with a loader that cannot see later dates. `--split validation` scores 2015 to 2019. `--sensitivity` adds 0, 5 and 25 basis point costs and whole-share rounding.

**Known issues.** High volatility (about 32% a year), a market beta above 1, a tilt towards smaller stocks and heavy trading (about 40% of the portfolio replaced each month).

### 3.2 Strategy 2: Volatility-managed baseline

**What it does.** It rebuilds the fund's current model: each month, 11 stocks by six-month (126 trading day) momentum and 4 by closeness to their 52-week high, held in equal amounts. At each month end it measures how volatile the baseline's daily returns were that month and sets next month's exposure to c divided by that variance, capped at 100%. The rest is held in cash at the risk-free rate.

**Files.**
- `src/baseline.py`: `baseline_targets`, the rebuilt fund model.
- `src/overlay.py`: `realized_variance`, `exposure` and `estimate_c`.
- `src/entrypoint.py`: `run`, which scales the baseline by the overlay. With `overlay.enabled: false` it runs the plain baseline.
- `scripts/fit_c_pit.py`: estimates c on 2000 to 2014 and writes `configs/primary_pit.yaml`.
- `scripts/validate_pit.py`: runs validation for the frozen version and the plain baseline, and writes `outputs/frozen/`.

**Frozen settings.** `rv_window_months: 1`, `cap: 1.0`, `floor: 0.0`, `c_method: mm_vol_match`, `c: 0.0371`.

**Run it.**

```bash
python -m strategy_2_vol_managed.scripts.fit_c_pit
python -m strategy_2_vol_managed.scripts.validate_pit
```

**Known issues.** It returned less than the benchmark. It only reacts to last month's volatility, so it cuts exposure after a sell-off has started and can miss the recovery.

### 3.3 Strategy 3: Combination

**What it does.** It runs Strategy 1's stock picks and applies Strategy 2's volatility rule to them. Only c is fitted again, on Strategy 1's returns from 2000 to 2014.

**Files.**
- `src/s1_frozen/`: an exact copy of Strategy 1's `signals.py` and `entrypoint.py`. `SOURCE_SHA256.txt` holds the fingerprints of the originals.
- `src/s2_frozen/overlay.py`: an exact copy of Strategy 2's overlay.
- `src/entrypoint.py`: `estimate_fit_c`, `managed_targets` and `run`. It refuses any settings that differ from the two frozen strategies, except c.
- `configs/s1_frozen_config.yaml` and `configs/s2_frozen_overlay.yaml`: the frozen settings it inherits.
- `scripts/fit_c_pit.py` and `scripts/validate_pit.py`: the same jobs as in Strategy 2.

**Frozen settings.** Strategy 1's V1 settings plus the Strategy 2 overlay, with `c: 0.0487`.

**Run it.**

```bash
python -m strategy_3_combined.scripts.fit_c_pit
python -m strategy_3_combined.scripts.validate_pit
```

**Known issues.** In the March 2020 crash it was still about 90% invested, because February had been calm. It then cut to about 7% for April, when the market recovered. It had the lowest holdout Sharpe of the three.

**Note for all three.** The `validate_pit` scripts rewrite `outputs/frozen/`, and `fit_c_pit` rewrites `configs/primary_pit.yaml`. Copy those first if you want to keep my versions for comparison. The scripts without `_pit` are the versions from before the stock-list correction and should not be used.

## 4. The data

### 4.1 Sources

| Data | Source |
| --- | --- |
| Daily stock prices and volume | Yahoo Finance, through `yfinance` |
| Stock list | Wikipedia: List of S&P 500 companies and Historical components of the S&P 500 |
| Market, size, value and momentum factors and the risk-free rate | Kenneth French Data Library |
| Benchmark funds | SPY, EFA and AGG from Yahoo, with VGTSX and VBMFX before EFA and AGG existed |

### 4.2 Files

Both `data/training/` and `data/test_holdout/` hold the same four files for their dates:

| File | Contents |
| --- | --- |
| `prices.parquet` | One row per stock per day: date, ticker, close, adj_close, volume, dollar_volume, ret |
| `factors_daily.parquet` and `factors_monthly.parquet` | MKT_RF, SMB, HML, MOM and RF as decimals (monthly values dated at month end) |
| `benchmarks_daily.parquet` | Daily returns of SPY, EFA, AGG and the SFIC benchmark (65/15/20, reset monthly) |
| `_split_manifest.json` | Row counts, dates and checksums |

`data/membership/sp500_membership.csv` lists when each stock was in the S&P 500. The universe on any date only includes stocks that were members on that date.

### 4.3 The split

| Segment | Dates | Where | Used for |
| --- | --- | --- | --- |
| Warm-up | 1997 to 1999 | `data/training/` | History for lookbacks only, never scored |
| Fit | 2000 to 2014 | `data/training/` | Building, debugging and estimating any constants |
| Validation | 2015 to 2019 | `data/training/` | Comparing a short list of versions written down in advance |
| Holdout | 2020-01-01 to 2026-11-16 | `data/test_holdout/` | One final test of each frozen strategy |

### 4.4 Getting data in code

A strategy never opens these files directly. It gets everything through a loader:

```python
from common.data_access import TrainingLoader

fit_loader = TrainingLoader(max_date="2014-12-31")   # fit years only; refuses any later date
loader = TrainingLoader()                            # up to 2019-12-31 (fit and validation)

loader.universe("2012-06-29")             # eligible tickers on that date
loader.prices(field="adj_close")          # wide table, date x ticker
loader.returns()                          # daily returns
loader.factors("monthly")                 # MKT_RF, SMB, HML, MOM, RF
loader.benchmarks()                       # SPY, EFA, AGG, SFIC_BENCH
loader.cash_rate()                        # daily risk-free rate
loader.trading_days(); loader.max_date
```

Asking for a date after `max_date` raises `LookaheadError`. The holdout loader is only created by `common/run_holdout.py`.

## 5. The workflow: when to do what

Follow these stages in order for any new or improved strategy. Each stage says which data it may use.

**Stage 1. Build on the fit years only (2000 to 2014).**
- Use `TrainingLoader(max_date="2014-12-31")`.
- Write the code, debug it and try ideas freely. Estimate any constant (betas, scaling factors such as c) here, then keep it fixed.
- Anything estimated over time must only use data up to that date, for example a rolling window.
- Log every run with `RunLogger` (section 6).

**Stage 2. Write the pre-registration before touching validation.**
- In `logs/preregistration.md`, write the main version with its exact settings, up to 12 alternative versions, the hypothesis, the metrics you will compare and the rule for choosing the final version.
- Go through the leakage checklist in `docs/PROJECT_SPEC.md` (section 8).

**Stage 3. Run validation (2015 to 2019), once per listed version.**
- Use `TrainingLoader()`.
- Run only the versions on your list. If you run anything else, log it and mark it as exploratory.
- Compare against the SFIC benchmark, the rebuilt baseline and the existing strategies.
- Apply your selection rule. Do not go back and change the design because of the validation numbers. If you do, you are back at stage 1 and the validation years are no longer clean.

**Stage 4. Freeze.**
- Copy the chosen config to `outputs/frozen/config.yaml` and save its validation results there.
- Run `write_freeze_record` (section 6). This records the fingerprints of the config and the code.
- After freezing, do not edit `src/`, `configs/`, `common/` or `config/`. The holdout runner will refuse to run if anything has changed.

**Stage 5. Run the holdout once.**

```bash
python -m common.run_holdout --strategy <strategy_folder_name> --confirm-freeze
```

- The runner checks the freeze, unlocks `data/test_holdout/`, runs the strategy, locks the folder again and saves the results in `outputs/holdout/<timestamp>/`.
- It refuses a second run. A repeat needs `--override --reason "..."` and is logged as a re-look.
- Do not change the strategy because of the holdout result. Report it as it is.

**Stage 6. Report.**
- Update `logs/STATUS.md` with the validation and holdout results, the number of versions tried and any caveats.

**About the 2020 to 2026 holdout.** It has already been used for each of my three strategies twice: once with the old stock list and once after the correction (see `logs/holdout_access.log`). It is still the agreed test period, but every extra look makes it less reliable. The most honest test of an improved strategy is data after 16 November 2026, through paper trading or by rebuilding the data later (section 9).

## 6. The shared code

| File | What it does |
| --- | --- |
| `common/data_access.py` | `TrainingLoader` and the gated `HoldoutLoader` |
| `common/universe.py` | Picks the top 500 S&P 500 members by dollar volume on a date |
| `common/backtest_engine.py` | `rebalance_dates` and `run_backtest`: fills trades at the next day's close, charges costs, pays the risk-free rate on cash, refuses leverage and short positions |
| `common/metrics.py` | Sharpe, Sortino, drawdown, turnover, factor loadings and bootstrap confidence intervals (`summary`) |
| `common/costs.py` | Reads costs and allocation size from `config/costs.yaml` |
| `common/run_logger.py` | `RunLogger`, `count_variants` and `write_freeze_record` |
| `common/codehash.py` | The code fingerprint used for freezing |
| `common/run_holdout.py` | The one-shot holdout runner |

Every run should go through `RunLogger`:

```python
from common.run_logger import RunLogger, write_freeze_record

with RunLogger("strategy_4_new_idea", variant="primary", split="validation", cfg=cfg,
               purpose="why this run", hypothesis="what you expect") as run:
    result = entrypoint.run(cfg, loader)
    run.record(result, metrics_dict)
    run.note(outcome="what happened", next_decision="what you will do next")

write_freeze_record("strategy_4_new_idea")   # after placing outputs/frozen/config.yaml
```

The code fingerprint covers the strategy's `src/` and `configs/` plus `common/` and `config/`. A change to any shared file means every frozen strategy has to be frozen again.

## 7. Adding a new strategy

1. Create a folder named `strategy_<n>_<name>/` with the same layout as the others (`src/`, `configs/`, `logs/` and `outputs/`, plus an empty `__init__.py` in the folder and in `src/`).
2. Write `src/entrypoint.py` with `run(cfg, loader) -> dict`. It must return:
    - `daily_returns`: a table with date, gross, net and exposure.
    - `positions`: date, signal_date, ticker, weight, shares, price and value_usd.
    - `trades`: date, ticker, side, weight_before, weight_after, delta_weight, notional_usd, shares and reason.
    - The easiest way to get all three is to build monthly target weights and pass them to `common.backtest_engine.run_backtest`, as the existing strategies do.
3. Use only `loader.max_date` and `loader.trading_days()` for dates, never fixed end dates, so the same code works with the training and holdout loaders.
4. Import only your own folder, `common` and normal packages, never another strategy folder. If you want to reuse another strategy's code, copy it in the way Strategy 3 does.
5. Add the folder name to `STRATEGIES` in `common/run_holdout.py` and to `STRATS` in `tests/test_imports.py`. Changing `common/run_holdout.py` changes every strategy's fingerprint, so then rerun `write_freeze_record` for each existing frozen strategy. That only updates the record; their settings and code stay the same.
6. Follow the stages in section 5.

## 8. Where I would start improving

1. **Strategy 1's trading.** A rule that keeps a stock while it stays near the top of the ranking (`configs/v2_buffer30.yaml`) could lower costs.
2. **Strategy 1's risk.** Sector limits or a limit on the smallest stocks could reduce its volatility and its tilt towards smaller stocks.
3. **The overlay's speed.** A shorter window (two or three weeks) or a trigger based on how far the portfolio has fallen could help Strategies 2 and 3 react during a crash instead of a month later.
4. **Better data.** A survivorship-free source such as CRSP would add the 226 removed companies that Yahoo has no data for and would give accurate index membership before 2008.
5. **More factors.** Adding profitability and investment factors to the Strategy 1 regressions would show whether the residuals capture something new.

## 9. Rebuilding the data

The raw downloads and the cleaned full dataset are not included. To rebuild everything, or to get data up to a later date, run these from the `antara_alloc/` folder. The download takes about 20 minutes.

```bash
python data/scripts/download.py            # raw data into data/raw/
python data/scripts/build_processed.py     # cleaning into data/processed/
python data/scripts/build_membership.py    # S&P 500 membership by date
python data/scripts/split.py               # writes data/training/ and data/test_holdout/, then locks the holdout
```

`split.py` refuses to run if `data/test_holdout/` is already locked, so move the existing one aside first. Rebuilt data runs up to the day you download it, so it will not match my files exactly. The cleaning steps are listed in `logs/data_log.md` and in the report.

## 10. Known limitations

- The baseline is my rebuild of the fund's model from the pitch description, not the fund's own code.
- Yahoo has no data for 226 of the 382 companies that left the index, so some survivorship bias remains, mostly before 2010.
- Wikipedia's table of index changes is nearly complete from about 2008 but sparse before that, so the early fit years are only partly corrected.
- Companies that changed their ticker (for example Facebook to Meta) are treated as members for the whole period.
- With under seven years of holdout data, none of the Sharpe ratio differences is statistically significant yet.
