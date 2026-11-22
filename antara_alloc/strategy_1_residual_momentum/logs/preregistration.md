# Pre-registration — strategy_1_residual_momentum

Written 2026-11-17, **before any validation (2015–2019) run**. Fit-period runs done before this file:
`primary`, `baseline_monthly`, `baseline_2monthly` (split=fit; see logs/run_registry.csv). No parameter was
changed after seeing fit results.

## Hypothesis
Ranking the point-in-time top-500 dollar-volume universe on standardized 12-1 residual returns (residuals of
rolling 36-month FF3 regressions; Blitz, Huij & Martens 2011) gives a 15-stock long-only portfolio with
(a) a higher net Sharpe than the SFIC benchmark and (b) a net Sharpe at least comparable to the existing SFIC
70/30 baseline, with lower time-varying factor (market/MOM) exposure than plain momentum.

## Primary specification (configs/primary.yaml)
- Signal date t = last trading day of each month; trade at the close of the next trading day (engine).
- Universe: `loader.universe(t)` (top 500 by 63-day mean dollar volume, data ≤ t).
- Monthly returns: compounded daily close-to-close returns per calendar month (≥ 15 valid days, else NaN).
- Regression: for each stock with complete returns over the 36 months ending at month(t):
  r − RF = a + b_MKT·MKT_RF + b_SMB·SMB + b_HML·HML + e (OLS, French monthly factors).
  If the French file has not yet published month(t), the window ends at the last published month (flagged).
- Score: sum of residuals over months t−11..t−1 (11 months; month t skipped) divided by the std (ddof=1)
  of the same 11 residuals.
- Portfolio: top 15 by score, equal weight, long-only, fully invested, monthly.
- Costs 10 bps/side; fractional rounding; 1% allocation (≈ $15.4K). First signal 1999-12-31.

## Variants (capped list; 5 runs on validation, ≤ 12 allowed)
| id | config | role | change vs primary |
|---|---|---|---|
| P  | primary | candidate | — |
| V1 | v1_unscaled | candidate | raw residual sum, no residual-vol scaling |
| V2 | v2_buffer30 | candidate | held names kept while rank ≤ 30 (turnover reduction) |
| B1 | baseline_monthly | comparison only | SFIC baseline: 11 names by 6-month (126d) momentum + 4 by 52-week-high proximity, EW, monthly |
| B2 | baseline_2monthly | comparison only | same, rebalanced every 2 months |

Baseline split 70/30 of 15 names → 11/4 (10.5/4.5 rounded toward momentum). Not a selection candidate.

Sensitivity of the frozen spec (not selection variants): cost 0/5/10/25 bps; whole-share rounding at 1% and 5%
allocation — run once on validation with `--sensitivity`, same targets.

## Success metrics (validation 2015-01..2019-12, net of costs)
Primary: net Sharpe (excess of French RF). Also: CAGR, vol, Sortino, MDD, Calmar, monthly hit rate,
tracking error / IR vs SFIC_BENCH, annual one-way turnover, trades per rebalance, cost drag, FF3+MOM loadings,
block-bootstrap 95% CIs for Sharpe and Sharpe differences (vs SFIC_BENCH and vs B1).

## Selection rule (decided now)
Freeze **P** unless:
- a candidate (V1/V2) has validation net Sharpe ≥ P + 0.10 → freeze that candidate; or
- V2 has net Sharpe ≥ P − 0.05 **and** annual one-way turnover ≥ 30% lower than P → freeze V2
  (cost robustness for a small allocation).
If both trigger, the higher net Sharpe wins. Baselines are never frozen as strategy 1.
5 years of validation cannot distinguish Sharpe differences of ~0.1 statistically; the rule is a tie-breaker,
not evidence. Validation is not an out-of-sample test; the holdout (2020+) is run once after freezing.

## Leakage checklist (ticked before validation)
- [x] Universe at t from `loader.universe(t)` (volume/prices ≤ t).
- [x] Betas/residual vol estimated per date from the 36 months ending at month(t); nothing full-sample
      (checked: scores at t identical with `TrainingLoader(max_date=t)` vs max_date=2014-12-31, 2003-06 and 2008-10).
- [x] Validation results are labeled validation, never test/out-of-sample.
- [x] No same-close execution: engine trades at t+1 close; targets dated t.
- [x] Monthly factors month-end stamped, aligned by calendar month; 12-1 skip verified on synthetic data
      (a large residual in month t does not raise the score).
- [x] Strategy code uses only `TrainingLoader` / the loader passed to `run`; no holdout access.

## Survivorship caveat
Candidate pool over-represents survivors (only 413 names priced on 2000-01-03; 226 removed names lack data).
Absolute returns are biased upward, mostly in early years; compare strategies on the same universe.
