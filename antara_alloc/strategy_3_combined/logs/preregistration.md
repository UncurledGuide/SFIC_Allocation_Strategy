# Pre-registration — strategy_3_combined

Written 2026-11-17, after the fit-period c estimate and BEFORE any validation (2015–2019) run.

## Primary specification (the only specification; no other variants)
- Stock selection: frozen Strategy 1 V1, unchanged (`src/s1_frozen/`, `configs/s1_frozen_config.yaml`):
  36-month FF3 regressions, 11-month residual momentum skipping 1 month, unscaled, top 15 EW, monthly,
  signals from 1999-12-31.
- Overlay: frozen Strategy 2 overlay, unchanged (`src/s2_frozen/overlay.py`, `configs/s2_frozen_overlay.yaml`):
  RV_t = 252 × population variance of unmanaged V1's daily (fractional, 0 bps) returns in calendar month t
  (returns ≤ t only); w_t = clip(c / RV_t, 0, 1); rest in cash at French RF; trades at t+1 close.
- c = 0.060743 (mm_vol_match on unmanaged V1, fit 2000-01..2014-12, 180 months; run
  `runs/*-primary-*` split=fit; `logs/c_estimate_fit.json`). Held fixed for validation and holdout.
  The first signal (1999-12-31) has no RV and keeps w = 1 (fit period only).
- Execution: 10 bps/side base, fractional, 1% allocation. Exact cfg: `configs/primary.yaml`.

## Hypothesis and success metrics (validation 2015-01-01..2019-12-31)
- H1: the overlay lowers volatility and max drawdown vs unmanaged V1 (same V1 targets, 10 bps).
- H2: net Sharpe of managed ≥ unmanaged V1; reported with a paired block-bootstrap CI (21-day blocks, 2000 draws).
- Comparison vs the SFIC benchmark (65/15/20): Sharpe difference and its bootstrap CI.
- Reported regardless of outcome: Sharpe, CAGR, vol, MDD, avg exposure, turnover (per rebalance and annual
  one-way), trades per rebalance, cost drag, 0/5/10/25 bps cost sensitivity, variants tried.
- Freezing does not depend on the validation outcome: this is the single pre-specified combination.

## Variant list (cap ≤ 12)
1. primary — the only variant. Cost sensitivity (0/5/25 bps) and the unmanaged-V1 reference are computed
   inside the same validation run and are not design variants.

## Leakage checklist (PROJECT_SPEC §8)
- [x] Universe at t via `loader.universe(t)` (frozen V1 code).
- [x] Betas: rolling 36 months ≤ t (frozen V1). RV_t uses only daily returns dated ≤ t. c estimated with
      `TrainingLoader(max_date="2014-12-31")` only (estimate_fit_c refuses a later max_date).
- [x] Validation results are labelled validation, never out-of-sample/test.
- [x] No same-close execution: common engine trades at the close of t+1; targets not shifted.
- [x] Dates: monthly factors month-end stamped (frozen V1); estimate_c lags RV by one month; skip month in V1.
- [x] No holdout-data access or holdout loader in strategy code (tests/test_imports.py).

## Caveat
Survivorship bias: the candidate pool over-represents survivors (413 stocks priced on 2000-01-03, 599 by
2019-12-31); absolute returns are biased upward, mostly in early years. Relative comparisons are less affected.
