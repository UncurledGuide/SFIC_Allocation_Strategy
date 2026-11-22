# Pre-registration — strategy_2_vol_managed

Written 2026-11-17, **before any validation (2015–2019) run**. Fit-period (2000–2014) runs done before
this: `baseline_monthly` (fit) and `primary` (fit diagnostics). c values were estimated on fit only
(`logs/c_estimates_fit.json`, `scripts/fit_c.py`) and are held fixed.

## Hypothesis
Scaling the SFIC baseline by inverse prior-month realised variance (Moreira & Muir), capped at 100%
exposure with the rest in cash, gives **(H1) a shallower maximum drawdown** and **(H2) a higher Sharpe
ratio** than the unmanaged monthly baseline over validation 2015–2019, net of 10 bps/side costs.

Success metrics (validation, net, fractional, 1% allocation):
- H1: max drawdown of primary less severe than baseline_monthly. (Primary metric, reported first.)
- H2: Sharpe(primary) − Sharpe(baseline_monthly) > 0; reported with a paired circular block bootstrap
  95% CI (block 21 days, 2000 draws). We call H2 "supported" only if the CI excludes 0; a positive
  point estimate with CI spanning 0 is reported as "directionally consistent, not significant".
- Also reported: Sortino, vol, CAGR, average exposure, turnover, cost drag, FF3+MOM loadings, Sharpe
  vs SFIC benchmark (0.79 over validation per the project notes).

## Common baseline (all specs)
Universe `loader.universe(t)`; 15 stocks EW, long-only; 11 by 126-day momentum, then 4 by proximity to
the 252-day high among the rest; monthly signal at month-end close, trade at t+1 close
(`common.backtest_engine.run_backtest`). Details in `logs/STATUS.md`.

## Primary specification (`configs/primary.yaml`)
- RV_t = population variance × 252 of the unscaled baseline's daily returns (fractional, 0 bps) over the
  trading days of calendar month t (window = 1 month, ends at signal date t inclusive).
- w_t = min(1, c / RV_t), floor 0. c = 0.047445 (Moreira–Muir: makes the *uncapped* managed monthly
  excess return have the same fit-period std as the unmanaged baseline; fit 2000–2014).
- Costs 10 bps/side, fractional, 1% allocation.

## Variants (capped at 3)
| id | change vs primary | c (fit) |
|---|---|---|
| V1 `rv3m` | RV window = 3 calendar months | 0.061173 (mm_vol_match, 3m RV) |
| V2 `c_median` | c = fit-period median 1m RV (full exposure whenever RV ≤ its fit median) | 0.050703 |
| V3 `floor25` | w_t = clip(c / RV_t, 0.25, 1.0) | 0.047445 |

Note: V2's c is within 7% of the primary's, so V2 is expected to be nearly identical (checked on fit
only; recorded here so it is not a surprise).

Comparators (not candidates for freezing): `baseline_monthly`, `baseline_2monthly` (same engine,
universe, costs), SFIC benchmark (65/15/20).

## Selection rule (fixed in advance)
Freeze the **primary** unless a variant has, on validation, **both** a higher Sharpe **and** a less severe
max drawdown than the primary **and** a paired bootstrap Sharpe-difference vs primary with
P(diff ≤ 0) < 0.10. If several qualify, take the one with the higher Sharpe. Validation is used for this
one comparison; no further tuning. Holdout is run once, after freezing.

## Sensitivities (primary + baseline_monthly, reporting only, not selection)
Costs 0 / 5 / 25 bps per side; whole-share rounding at 1% (~$15.4K) and 5% (~$77K) allocation.

## Survivorship caveat
The candidate pool over-represents firms that survived (most delisted names have no data), so absolute
returns are biased upward, mostly early in the sample. Relative comparisons (overlay vs baseline on the
same universe) are less affected but not immune: the overlay scales the same biased portfolio.
