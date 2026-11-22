# PROJECT_SPEC — SFIC Quant "Allocation: New Iteration"

This is the contract every strategy follows. Read it fully before writing code.
Single sources of truth: `config/splits.yaml`, `config/costs.yaml`, `config/universe.yaml`,
`config/data_sources.yaml`. Decisions and their reasons: `logs/decision_log.md`. Data provenance: `logs/data_log.md`.

Context: the existing SFIC model (baseline) = top-500-by-volume universe, 70% 6-month momentum / 30%
52-week-high proximity, 15 stocks equal-weight, long-only, rebalanced ~every 2 months.
Strategy 1 = residual momentum (Blitz, Huij & Martens). Strategy 2 = volatility-managed overlay on the
baseline (Moreira & Muir). Both are long-only, no leverage (exposure in [0, 1], rest in cash at French RF).

## 1. Splits (time-based only)

| Segment | Dates | Use |
|---|---|---|
| warm-up | 1997-01-01 .. 1999-12-31 | lookback history only; never scored |
| fit | 2000-01 .. 2014-12 | design, estimation, debugging |
| validation | 2015-01 .. 2019-12 | pre-registered comparison of a capped list of variants |
| holdout | 2020-01-01 .. latest | LOCKED. One run per frozen strategy via `common/run_holdout.py` |

Fit and validation both live in `data/training/` (≤ 2019-12-31). Any parameter estimated from data
(betas, scaling constant c, z-score moments, …) must be estimated with data available at that date
(rolling/expanding), or on fit only and then held fixed. Never random/k-fold splits.
For fit-only work use `TrainingLoader(max_date="2014-12-31")`, which physically refuses later dates.

## 2. Universe and survivorship caveat

`loader.universe(asof)`: among stocks that were **S&P 500 members on `asof`** (point-in-time membership,
`data/membership/sp500_membership.csv`, rebuilt backwards from today's list through the changes table), the top 500
by mean raw Close×Volume over the 63 trading days ending at `asof` (inclusive), requiring ≥ 50 valid days and a
price on the last trading day ≤ asof. Benchmarks/proxies are excluded. Uses only data ≤ asof (tested).
The changes table is sparse before ~2008, so fit-period (2000–2007) membership still contains some future members.

Candidate pool = current S&P 500 members + every ticker in Wikipedia's S&P 500 additions/removals table
(now on the article "Historical components of the S&P 500"). **Survivorship bias:** Yahoo Finance has no data
for most delisted/acquired names and for tickers that were later reused, and the changes table is
incomplete for early years. The pool therefore over-represents firms that survived to today. Expect
backtested returns of any stock-selection strategy to be biased upward, mostly in the early years.
Counts are in `logs/data_log.md`. Report this caveat with every result; compare strategies to each other
on the same universe (relative comparisons are less affected than absolute levels).

## 3. Execution timing, costs, rounding (common/backtest_engine.py)

- Signal at month-end t uses data through the close of t (last trading day of the month).
- Trade fills at the CLOSE of the next trading day (t+1). t+1's return is earned by the old weights.
  Never trade at the same close that produced the signal.
- Costs: 10 bps per side on traded notional (Σ|Δw|), base case. Sensitivity: 0 / 5 / 25 bps.
- Cash earns French daily RF. No leverage, no shorts (engine raises).
- Missing return for a held stock = 0% that day (counted as `stale_return_position_days`); after a stock's
  last price it is moved to cash at that price (`delisted_to_cash`, no cost).
- Sizing: SFIC total ≈ $1,540,747 (positions file). Primary allocation 1% ≈ $15.4K; sensitivity 5% ≈ $77K.
  `rounding="fractional"` (default) or `"whole_share"` (floor shares at raw close, remainder cash).
- Rebalance schedule: Strategy 1 and 2 monthly. Baseline tested monthly AND every 2 months
  (`rebalance_dates(..., every_n_months=2)`).
- Reports must include turnover (per rebalance and annual one-way), trades per rebalance, cost drag.

## 4. Loader interface (common/data_access.py)

Strategies get data ONLY through the loader object passed to `run(cfg, loader)`. Never open files.

```
loader.prices(tickers=None, start=None, end=None, field="adj_close")  # wide date x ticker
        # field in {"adj_close","close"(raw),"volume","dollar_volume","ret"}
loader.returns(tickers, start, end)      # daily simple returns from Adj Close
loader.volumes(...), loader.dollar_volumes(...)
loader.universe(asof) -> list[str]
loader.factors(freq="daily"|"monthly")   # date, MKT_RF, SMB, HML, RF, MOM (decimals; monthly dated month-end)
loader.benchmarks()                      # date, SPY, EFA, AGG, SFIC_BENCH (daily returns)
loader.cash_rate()                       # daily RF Series
loader.trading_days(); loader.split_name; loader.max_date; loader.perf_start
```
`TrainingLoader` raises `LookaheadError` for any date > its max_date (≤ 2019-12-31).
`HoldoutLoader` is created only by `run_holdout.py`; it exposes training history for lookbacks and the
holdout data; performance is scored from `perf_start = 2020-01-01`. Your entrypoint must work unchanged
with either loader (use `loader.max_date` / `loader.trading_days()`, never hard-coded end dates).

## 5. Strategy entrypoint contract

`strategy_X/src/entrypoint.py` exposes `run(cfg: dict, loader) -> dict` returning:
- `daily_returns`: DataFrame [date, gross, net, exposure] (+ engine extras turnover, cost, nav allowed)
- `positions`: DataFrame [date, signal_date, ticker, weight, shares, price, value_usd]
- `trades`: DataFrame [date, ticker, side, weight_before, weight_after, delta_weight, notional_usd, shares, reason]
- optional `stats` dict. Use `common.backtest_engine.run_backtest` to produce these.
Imports: own package (relative imports), `common.*`, third-party. Never the other strategy.

## 6. Frozen output schema (`strategy_X/outputs/frozen/`)

`daily_returns.csv`, `positions.csv`, `trades.csv`, `metrics.json` (validation/training results of the frozen
spec), `config.yaml` (the exact cfg passed to `run`), `freeze_record.md` written by
`common.run_logger.write_freeze_record(strategy_dir)`: config hash (sha256 of config.yaml), code hash
(`common.codehash.code_hash`), number of variants tried, total runs. After freezing, do not edit
src/, configs/, common/ or config/ — `run_holdout.py` refuses if any hash changed.

## 7. Run-logging contract

Every run uses `common.run_logger.RunLogger` (see its docstring). It creates `strategy_X/runs/<run_id>/` with
config snapshot, data manifest hash, split, params, seed, code hash, start/end time, stdout/stderr log,
metrics.json, equity curve, daily returns, positions, trades, and notes.md (purpose / hypothesis / outcome /
next decision); and appends to `strategy_X/logs/run_registry.csv`
(run_id, timestamp, variant, split, key_params, headline metrics, status). Failed runs are logged too.
`count_variants()` gives the number of variants tried — report it with results. Never delete runs.
Shared logs: `logs/data_log.md` (data), `logs/decision_log.md` (decisions + reasons), `logs/holdout_access.log`.

## 8. Isolation, holdout rules, leakage checklist, pre-registration

Isolation: each strategy works only in its own folder plus read access to `common/`, `config/`,
`docs/PROJECT_SPEC.md`. It never reads/writes the other strategy's folder, `evaluation/outputs`, or
`data/test_holdout` (chmod 000 + folder access restrictions). Changes to `common/` or `config/` go in `logs/decision_log.md`
and affect both strategies' code hashes — avoid them; if a bug is found, record it and fix it once.

Holdout: run once per strategy, after freezing, via
`python -m common.run_holdout --strategy <name> --confirm-freeze`. Repeats need `--override --reason` and
are logged as re-looks. Holdout results must not feed back into design; if they do, say so.

Leakage checklist (tick each before validation and before freezing):
- [ ] Universe at t uses only volume/prices ≤ t (use `loader.universe(t)`; no future-volume universe).
- [ ] Betas, residual vol, z-score moments, vol-scaling constant c: estimated only with data ≤ t
      (rolling/expanding) or on fit only — never on the full sample or validation/holdout.
- [ ] Validation results are never presented as test/out-of-sample results.
- [ ] No same-close execution: engine trades at t+1 close; do not shift targets earlier.
- [ ] Dates/frequencies aligned: monthly factors are month-end stamped; daily returns are close-to-close;
      the 12-1 skip month is really skipped; no off-by-one between signal month and return month.
- [ ] No access to `data/test_holdout` or `HoldoutLoader` in strategy code (tested).

Pre-registration: before the first validation run, write `strategy_X/logs/preregistration.md` with the
primary specification (exact parameters), the hypothesis and success metrics, and a capped list of
**≤ 12 variants**. Validation runs outside that list must be logged and flagged as exploratory.
