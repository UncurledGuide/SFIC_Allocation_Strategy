# STATUS — strategy_1_residual_momentum

_Read this file first and update it after each change._

## Current state (2026-11-17): FROZEN — re-frozen on the corrected universe; numbers in the table below are OLD-universe, see "Universe-correction re-measure" at the bottom for current numbers
- Frozen spec: **V1 `configs/v1_unscaled.yaml`** — residual momentum, rolling 36-month FF3 OLS on monthly
  returns, score = sum of residuals over months t−11..t−1 (skip month t), **no residual-vol scaling**, top 15 EW,
  long-only, monthly, 10 bps/side, fractional, 1% allocation.
- Selected by the pre-registered rule (`logs/preregistration.md`): V1 validation net Sharpe 1.025 ≥ primary 0.555 + 0.10.
- Frozen outputs: `outputs/frozen/` (config.yaml, daily_returns/positions/trades = full 2000–2019 backtest,
  metrics.json scored on validation, freeze_record.md). Hashes verified: config_hash ee492c06…, code_hash c30a22e3….
- **Do not edit `src/`, `configs/`, `../common/`, `../config/`** — the holdout runner refuses if the code hash changes.
- Variants tried: 5 (P, V1, V2, B1, B2). Runs logged: 9 (3 fit, 6 validation incl. V1 sensitivity re-run).

## Results (net of 10 bps; validation 2015–2019 is NOT an out-of-sample test)
| variant | fit Sharpe | val Sharpe [95% CI] | val CAGR | val vol | val MDD | turnover/yr (1-way) | trades/reb | β MKT | β MOM |
|---|---|---|---|---|---|---|---|---|---|
| P primary (vol-scaled) | 0.63 | 0.55 [−0.19, 1.35] | 9.1% | 16.2% | −23.2% | 6.2 | 22.5 | 1.02 | 0.29 |
| **V1 unscaled (frozen)** | 0.99 | **1.03 [0.22, 1.81]** | 21.5% | 20.0% | −25.4% | 5.1 | 20.9 | 1.15 | 0.18 |
| V2 vol-scaled + buffer 30 | 0.62 | 0.48 [−0.21, 1.25] | 7.8% | 16.2% | −22.9% | 4.2 | 19.8 | 1.01 | 0.30 |
| B1 baseline 70/30 monthly | 0.85 | 0.85 [0.13, 1.58] | 18.1% | 21.0% | −25.8% | 6.9 | 23.4 | 1.18 | 0.46 |
| B2 baseline 70/30 2-monthly | 0.84 | 0.86 [0.14, 1.62] | 18.6% | 21.5% | −29.8% | 4.1 | 25.1 | 1.22 | 0.44 |
| SFIC benchmark | 0.24 | 0.79 | | | | | | | |

- V1 − B1 Sharpe diff (validation, paired block bootstrap): +0.18 [−0.38, +0.73], p(≤0)=0.27 → not significant.
- V1 − SFIC bench: +0.23 [−0.33, +0.74]. V1 − P: +0.47 [+0.03, +0.89].
- V1 cost sensitivity (validation Sharpe): 0 bps 1.08 / 5 bps 1.05 / 10 bps 1.03 / 25 bps 0.95; whole-share at 1%
  and 5% allocation ≈ fractional (1.03). Cost drag ≈ 1%/yr at 10 bps.
- V1 has a lower MOM loading than the baseline (0.18 vs 0.46) but higher market beta than the vol-scaled primary.
- Survivorship caveat applies to all rows (pool over-represents survivors; levels biased up, mostly early years).

## Notes / honest caveats
- The canonical BHM spec (vol-scaled) lost to both V1 and the baseline on fit and validation in this universe.
  Plausible reason: dividing by residual vol favors low-idiosyncratic-vol names (lower return in this
  large-cap, survivor-heavy pool). V1 is the rule-selected spec, not the textbook one — say so when presenting.
- 5 years of validation cannot separate Sharpe differences of ~0.2; the V1 vs baseline edge is not statistically supported.
- Monthly French factors: if the latest month isn't published at signal time, the regression window ends at the last
  published month (count reported as `signals_with_factor_lag` in stats). Relevant for the holdout.

## Next steps
1. Holdout (maintainer decision): `../.venv/bin/python -m common.run_holdout --strategy strategy_1_residual_momentum --confirm-freeze` — once only.
2. Cross-strategy comparison belongs in `../evaluation/` (outside this folder).

## Open issues
- Survivorship: only 413 stocks have prices on 2000-01-03 (599 by 2019-12-31); 226 of 382 removed names have no Yahoo data.
- Data files are chmod 000; use only the loader passed to run(cfg, loader).

## Universe correction (2026-11-17) — read before doing anything
- Problem found after the first holdout run: the candidate pool used today's S&P 500 list, so stocks that joined the
  index later (TSLA before 2020-12, SMCI, CVNA, APP, HOOD, BE, ...) were tradable before they joined.
- Fix (shared code): `loader.universe(asof)` now only returns stocks that were S&P 500 members on asof
  (config/universe.yaml `membership_file`). Membership is near-complete from ~2008; sparse before.
- Consequence: this folder's freeze record no longer verifies (common/ and config/ changed). The frozen SPEC
  (config.yaml choices) stays the same; re-run its validation numbers on the corrected universe and re-freeze.
  Do not switch to another variant. First holdout results (old universe) are in outputs/holdout/ — do not use them for design.

## Universe-correction re-measure + re-freeze (2026-11-17) — CURRENT NUMBERS
Design unchanged: `outputs/frozen/config.yaml` byte-identical (sha256 ee492c06…); `src/` and `configs/` untouched
(no run failed). Re-run with `TrainingLoader()` (point-in-time S&P 500 membership), split=validation, via RunLogger:
- V1 `runs/20261117-103025-v1_unscaled_pit-30d9a5ab` (with 0/5/10/25 bps + whole-share sensitivity)
- primary `runs/20261117-103029-primary_pit-30d9a5ab`, baseline monthly `runs/20261117-103032-baseline_monthly_pit-30d9a5ab`
- `outputs/frozen/` daily_returns/positions/trades/metrics.json replaced by the V1_pit run (old files kept in
  `logs/frozen_pre_universe_correction/`). New freeze record: code_hash 30d9a5ab…, config_hash ee492c06…;
  `verify('strategy_1_residual_momentum')` passes. pytest: 24 passed, 1 skipped.
- Freeze record shows variants_tried 8: `count_variants` counts the `_pit` re-runs as new names; design variants are still 5.

### Validation 2015–2019, net of 10 bps (old universe → corrected PIT universe)
| | Sharpe [95% CI] | CAGR | vol | MDD | turnover/yr | Sharpe − SFIC bench [CI] |
|---|---|---|---|---|---|---|
| **V1 (frozen)** | 1.03 [0.22, 1.81] → **0.57 [−0.18, 1.37]** | 21.5% → 10.1% | 20.0% → 17.8% | −25.4% → −23.7% | 5.08 → 4.87 | +0.23 [−0.33, 0.74] → −0.22 [−0.78, 0.26] |
| Primary (vol-scaled) | 0.55 [−0.19, 1.35] → 0.47 [−0.23, 1.22] | 9.1% → 7.5% | 16.2% → 15.8% | −23.2% → −21.5% | 6.18 → 5.98 | −0.24 [−0.72, 0.23] → −0.32 [−0.78, 0.12] |
| Baseline 70/30 monthly | 0.85 [0.13, 1.58] → 0.44 [−0.26, 1.18] | 18.1% → 7.4% | 21.0% → 17.0% | −25.8% → −20.2% | 6.92 → 7.02 | +0.06 [−0.61, 0.65] → −0.35 [−0.88, 0.14] |
| SFIC benchmark (unaffected) | 0.79 → 0.79 | 9.1% | 10.4% | −14.8% | — | — |

Paired block-bootstrap Sharpe differences (1000 draws, block 21): V1 − baseline +0.18 [−0.38, 0.72] → +0.13 [−0.44, 0.70]
(p≤0 0.34); V1 − primary +0.47 [+0.03, 0.88] → +0.10 [−0.28, 0.45] (p≤0 0.28).
Factor loadings (V1, new): β MKT 1.08, β SMB 0.17, β MOM 0.11, FF4 alpha −1.6%/yr (t −0.37). Trades/rebalance 20.9.
V1 cost sensitivity (validation Sharpe, new): 0 bps 0.63 / 5 bps 0.60 / 10 bps 0.57 / 25 bps 0.49.

### V1 fit period 2000–2014 (from the same run; old → new)
Sharpe 0.99 → 0.67, CAGR 33.0% → 19.0%, vol 32.5% → 29.8%, MDD −66.6% → −65.3%, turnover 5.11 → 5.17/yr.
(Primary fit Sharpe 0.63 → 0.55; baseline 0.85 → 0.68; SFIC bench fit 0.24.) Pre-2008 membership is still partly survivor-based.

### Would the pre-registered rule still pick V1? (report only — not switching)
Rule: V1 chosen if V1 Sharpe ≥ P + 0.10. New: 0.573 vs 0.471 + 0.10 = 0.571 → **yes, by 0.002** (knife-edge;
noise-level). V2 was not re-run on the corrected universe (out of scope), so the V2 turnover branch was not re-checked.
With the correction, no strategy here beats the SFIC benchmark's validation Sharpe (0.79); all CIs vs benchmark include 0.

### Next steps
1. Re-run the holdout once with `--override` and reason "data correction" (not run here). Report the first
   (old-universe) holdout in `outputs/holdout/20261117-102018/` alongside it.
