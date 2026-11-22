# antara_alloc: SFIC allocation strategies (residual momentum and volatility management)

Author: Antara Chhabra

This folder contains a backtesting framework and three long-only strategies for the 1% cash allocation of the SFIC portfolio (about $15,400). Each strategy was built on 2000–2014 data, compared on 2015–2019 data using a version list written in advance and then frozen. Each frozen strategy was tested once on 2020 to November 2026 data. After the first holdout runs, the stock universe was corrected to use point-in-time S&P 500 membership, and all three strategies were revalidated and retested. The results below use the corrected universe.

The full write-up is in `docs/SFIC_Allocation_New_Iteration.pdf`. The working guide for anyone extending this code is `docs/HANDOFF.md`.

## Contents

| Path | Contents |
| --- | --- |
| `common/` | Shared code: data loader, universe, backtest engine, metrics, run logger, code fingerprinting, holdout runner |
| `config/` | Shared settings: data splits, costs and allocation, universe rule, data sources |
| `data/scripts/` | Data pipeline: download, cleaning, S&P 500 membership history, time split |
| `data/membership/` | S&P 500 membership by date (`sp500_membership.csv`) |
| `data/reference/` | Candidate ticker pool and the S&P 500 additions and removals table used to build the membership file |
| `strategy_1_residual_momentum/` | Strategy 1 code, configs, logs and results |
| `strategy_2_vol_managed/` | Strategy 2 code, configs, scripts, logs and results |
| `strategy_3_combined/` | Strategy 3 code, configs, scripts, logs and results |
| `tests/` | Checks for look-ahead, folder isolation, engine behaviour and data quality |
| `logs/` | Decision log, data log, holdout access log and the final results table |
| `docs/` | `PROJECT_SPEC.md` (rules), `HANDOFF.md` (working guide), the report PDF |

Each strategy folder contains `src/` (code, with `entrypoint.py: run(cfg, loader)`), `configs/` (one YAML file per tested version), `logs/` (`STATUS.md`, `preregistration.md`, `run_registry.csv`) and `outputs/` (`frozen/` validation results and freeze record, `holdout/` results). Price data is not stored in git; see "Reproducing the results".

## Strategies

| | Strategy 1 | Strategy 2 | Strategy 3 |
| --- | --- | --- | --- |
| Idea | Residual momentum (Blitz, Huij and Martens, 2011) | Volatility-managed portfolio (Moreira and Muir, 2017) applied to a rebuild of the current SFIC model | Strategy 1 stock selection with the Strategy 2 exposure rule |
| Selection | Top 15 by the sum of 11 monthly residuals from a 36-month regression on market, size and value factors, skipping the latest month (12-1) | 11 stocks by 126-day momentum and 4 by closeness to the 52-week high | Same as Strategy 1 |
| Exposure | 100% | c divided by the previous month's realized variance, capped at 100%, remainder in cash | Same rule as Strategy 2, with c fitted on Strategy 1 returns |
| Weights and rebalancing | Equal weight, monthly | Equal weight, monthly | Equal weight, monthly |
| Frozen config | `configs/v1_unscaled.yaml` | `configs/primary_pit.yaml` (c = 0.0371) | `configs/primary_pit.yaml` (c = 0.0487) |

The baseline used in Strategies 1 and 2 is a rebuild of the current SFIC model from its pitch description. The original code was not available, so the rebuild uses its own choices: an 11/4 split of 15 stocks, a 126-trading-day momentum window, dollar-volume ranking, daily data and both monthly and two-monthly rebalancing.

## Method

- **Data.** Daily prices and volume from Yahoo Finance (`yfinance`) for 885 candidate tickers (503 current S&P 500 members and 382 removed members). Factors and the risk-free rate are from the Kenneth French Data Library. Benchmark funds are SPY, EFA and AGG, with VGTSX and VBMFX before EFA and AGG started trading.
- **Cleaning.** Trading calendar from SPY dates. One-day spikes above 100% that fully reverse were removed, daily moves above 300% and returns across gaps of more than five trading days were set to missing. Details are in `logs/data_log.md`.
- **Universe.** Each month, the 500 stocks with the highest average dollar volume over the previous 63 trading days, among stocks that were S&P 500 members on that date.
- **Split.** Warm-up 1997–1999 (lookbacks only), fit 2000–2014, validation 2015–2019, holdout 2020-01-01 to 2026-11-16. Strategies read data only through a loader that refuses dates after its cutoff.
- **Execution.** Signals at the last close of each month, trades at the next day's close, 10 basis points per side (0, 5 and 25 as sensitivity checks), cash at the risk-free rate, no leverage or short positions.
- **Process.** Each strategy has a pre-registered version list and selection rule, every run is logged and the chosen version is frozen with SHA-256 fingerprints of its code and settings. The holdout runner checks the fingerprints, runs once and records each run in `logs/holdout_access.log`.
- **Correction.** The first candidate list was built from today's S&P 500 members, which made companies available before they joined the index. After this was found in the first holdout runs, the universe was restricted to point-in-time membership, designs were kept unchanged, c was re-fitted where it depends on the data and each holdout was run once more as a logged re-look.

## Results (corrected universe)

Holdout period 2 January 2020 to 16 November 2026, after 10 basis points per side, 1% allocation.

| Measure | Strategy 1 | Strategy 2 | Strategy 3 | SFIC benchmark |
| --- | --- | --- | --- | --- |
| Holdout Sharpe ratio | 0.61 | 0.41 | 0.34 | 0.56 |
| Holdout return per year | 18.6% | 9.0% | 8.0% | 11.0% |
| Holdout volatility per year | 31.7% | 18.5% | 21.0% | |
| Holdout maximum drawdown | −40.2% | −20.4% | −38.1% | |
| COVID crash, 19 Feb to 23 Mar 2020 | −37.8% | −19.3% | −35.6% | |
| Average amount invested | 100% | 66% | 75% | 100% |
| Alpha per year after market, size, value and momentum factors (t-statistic) | +6.2% (0.95) | +1.5% (0.31) | −3.2% (−0.69) | |
| Turnover per year | 5.2 times | 5.0 times | 4.6 times | |
| Validation Sharpe ratio, 2015–2019 | 0.57 | 0.31 | 0.44 | 0.79 |

The rebuilt baseline had a validation Sharpe ratio of about 0.41 to 0.44. None of the alphas or Sharpe ratio differences is statistically significant over this holdout length. The first holdout results, before the correction, are kept in each strategy's `outputs/holdout/` folder and in `logs/decision_log.md`.

## Reproducing the results

```bash
cd antara_alloc
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.lock
export PYTHONPATH="$PWD"

python data/scripts/download.py            # Yahoo, French and Wikipedia data into data/raw/ (about 20 minutes)
python data/scripts/build_processed.py     # cleaning into data/processed/
python data/scripts/build_membership.py    # S&P 500 membership by date
python data/scripts/split.py               # data/training/ and data/test_holdout/, then locks the holdout

python -m pytest -q
```

Without the data folders, the tests that need data are skipped. A fresh download runs up to the download date, so numbers can differ slightly from the committed results. Commands for running each strategy, freezing and the holdout are in `docs/HANDOFF.md`.

## Caveats

- Yahoo Finance has no data for 226 of the 382 removed S&P 500 members, so some survivorship bias remains, mostly before 2010.
- Wikipedia's table of index changes is sparse before about 2008, so early membership is only partly point-in-time. Renamed tickers are treated as members for the whole period.
- The baseline is a rebuild from the pitch description, not the fund's own code.
- The universe correction was prompted by the first holdout results. Strategy designs were not changed, and both sets of holdout results are reported.
- Yahoo data is retrieved through an unofficial API, and its terms restrict redistribution, so the data files are not committed.
