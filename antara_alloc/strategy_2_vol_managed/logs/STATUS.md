# STATUS — strategy_2_vol_managed

_Read this file first and update it after each change._

## Current state (2026-11-17, after universe correction): RE-FROZEN on point-in-time universe, holdout re-look not yet run
- Frozen spec: **primary, unchanged design** (1-month RV, cap 1, floor 0, c_method mm_vol_match, same baseline rules);
  only c re-estimated on the corrected fit data: **c 0.04745 → 0.03710** (×0.78).
  Config: `configs/primary_pit.yaml` = `outputs/frozen/config.yaml`. `configs/primary.yaml` kept as the old-universe record.
- Freeze record rewritten 2026-11-17T10:31:56: config_hash `59536725…`, code_hash `8482b53a…`, variants_tried 24, runs 27.
  `verify('strategy_2_vol_managed')` passes. Old record: `logs/freeze_record_before_universe_correction.md`
  (+ `logs/frozen_config_before_universe_correction.yaml`). `src/` not changed.
- variants_tried rose 16 → 24 only because the re-measurement runs are logged under `_pit` labels
  (primary_pit, baseline_monthly_pit, 6 cost runs). No new design variants were tried.
- Results on corrected universe: `logs/validation_results_pit.json`, `outputs/frozen/metrics.json`, c: `logs/c_estimates_fit_pit.json`.
  Drivers: `scripts/fit_c_pit.py`, `scripts/validate_pit.py`.
- **The old-universe numbers in the sections below are superseded** (kept for the record; they were inflated by
  look-ahead in the candidate pool).

### Before / after universe correction (validation 2015–2019, net 10 bps/side, fractional, 1%)
| | Sharpe | Sortino | CAGR | Vol | Max DD | Calmar | Avg exposure | Annual 1-way turnover |
|---|---|---|---|---|---|---|---|---|
| overlay (primary), old universe, c=0.0474 | 0.837 | 1.14 | 16.2% | 18.9% | −22.2% | 0.73 | 0.89 | 6.24 |
| **overlay (primary), corrected, c=0.0371** | **0.312** | 0.42 | **4.8%** | 16.0% | **−21.3%** | 0.23 | 0.92 | 6.47 |
| baseline monthly, old universe | 0.832 | 1.14 | 18.2% | 21.7% | −28.0% | 0.65 | 1.00 | 6.73 |
| **baseline monthly, corrected** | **0.413** | 0.56 | **6.9%** | 17.3% | **−19.8%** | 0.35 | 1.00 | 6.75 |
| SFIC benchmark (unchanged) | 0.793 | 1.10 | 9.1% | 10.4% | −14.8% | – | – | – |

Sharpe-difference 95% block-bootstrap CIs (2000 draws, block 21 days):
| | old universe | corrected |
|---|---|---|
| overlay − baseline | +0.006 [−0.21, +0.23], P(≤0) 0.49 | **−0.101 [−0.23, +0.03], P(≤0) 0.93** |
| overlay − SFIC benchmark | +0.045 [−0.63, +0.67], P(≤0) 0.46 | **−0.481 [−1.05, +0.02], P(≤0) 0.97** |
| baseline − SFIC benchmark | +0.039 [−0.61, +0.62] | −0.380 [−0.94, +0.13], P(≤0) 0.93 |
| overlay Sharpe CI | 0.837 [0.07, 1.58] | 0.312 [−0.43, 1.05] |

Cost sensitivity, corrected (Sharpe / MDD): overlay 0 bps 0.393 / −21.1%, 5 bps 0.353 / −21.2%, 10 bps 0.312 / −21.3%,
25 bps 0.191 / −21.6%; baseline 0 bps 0.491 / −19.5%, 5 bps 0.452 / −19.7%, 10 bps 0.413 / −19.8%, 25 bps 0.295 / −20.1%.

Fit 2000–2014 baseline, corrected universe: Sharpe 0.67 (old 0.79), CAGR 17.6%, vol 26.8% (old 29.0%), MDD −61.4% (old −64.2%).
c fit stats (corrected): avg fit exposure 0.73 (old 0.77), months capped 38% (old 46%).
Factor loadings, corrected (daily FF3+MOM): overlay β_MKT 0.92, SMB 0.22, MOM 0.37, alpha −5.6%/yr (t −1.47);
baseline β_MKT 1.04, SMB 0.19, MOM 0.41, alpha −5.0%/yr (t −1.35).

Reading (validation only, not out-of-sample):
- Most of the old edge came from the look-ahead pool: baseline Sharpe 0.83 → 0.41, CAGR 18% → 7%; both now trail the
  SFIC benchmark (Sharpe 0.79) in point estimate, though CIs still include zero difference.
- **H1 (shallower MDD) no longer holds in validation:** overlay −21.3% vs baseline −19.8%. Vol is still lower (16.0% vs 17.3%).
- **H2 (higher Sharpe) not supported:** overlay − baseline −0.10, CI [−0.23, +0.03]. Lower c cuts exposure, but the
  validation period had few vol spikes where de-risking paid (lowest yearly avg exposure 0.85, in 2018), so the overlay mostly gives up return.
- Design was NOT changed in response to these numbers.

## Holdout command (run once, by the maintainer, after freezing)
First run (old universe) is done; results in outputs/holdout/20261117-102027 (must be reported alongside the re-look).
Re-look after the data correction:
```
cd ~/Downloads/sfic && .venv/bin/python -m common.run_holdout --strategy strategy_2_vol_managed --confirm-freeze --override --reason "data correction: point-in-time S&P 500 universe"
```

## [SUPERSEDED: old universe] Validation 2015–2019 (net, 10 bps/side, fractional, 1% allocation) — NOT an out-of-sample test
| spec | **Max DD** | Sharpe | Sortino | CAGR | Vol | Avg exposure | Annual 1-way turnover | Cost drag (5y) |
|---|---|---|---|---|---|---|---|---|
| **primary** (1m RV, MM c, cap 1) | **−22.2%** | 0.837 | 1.14 | 16.2% | 18.9% | 0.89 | 6.24 | 6.2% |
| rv3m | −23.4% | 0.795 | 1.08 | 16.4% | 20.5% | 0.95 | 6.48 | 6.5% |
| c_median | −23.4% | 0.846 | 1.15 | 16.7% | 19.2% | 0.90 | 6.31 | 6.3% |
| floor25 (= primary; exposure never < 0.28 in validation) | −22.2% | 0.837 | 1.14 | 16.2% | 18.9% | 0.89 | 6.24 | 6.2% |
| baseline monthly | **−28.0%** | 0.832 | 1.14 | 18.2% | 21.7% | 1.00 | 6.73 | 6.7% |
| baseline 2-monthly | −30.7% | 0.829 | 1.14 | 18.3% | 22.0% | 1.00 | 3.88 | 3.9% |
| SFIC benchmark | −14.8% | 0.793 | 1.10 | 9.1% | 10.4% | – | – | – |

- **H1 (shallower MDD): supported in validation** — −22.2% vs −28.0% (about 6 points), and vol 18.9% vs 21.7%.
- **H2 (higher Sharpe): not supported** — Sharpe diff vs baseline +0.006, 95% block-bootstrap CI
  [−0.21, +0.23], P(diff ≤ 0) = 0.49. Overlay vs SFIC benchmark: +0.045, CI [−0.63, +0.67]. The overlay
  gives up ~2 pts CAGR for its lower risk; Calmar 0.73 vs 0.65.
- Primary Sharpe 95% CI [0.07, 1.58] — five years cannot separate any of these specs.
- Factor loadings (daily FF3+MOM, NW): primary β_MKT 0.98, SMB 0.47, HML −0.12, MOM 0.43, alpha 4.3%/yr
  (t 0.88); baseline β_MKT 1.20, SMB 0.47, HML −0.27, MOM 0.49, alpha 3.3%/yr (t 0.69). The overlay mainly
  cuts market beta; neither alpha is significant.
- Selection rule applied: c_median has higher Sharpe (+0.009, P(≤0)=0.26) but deeper MDD → not selected.
  No variant met the rule → **primary frozen**, as pre-registered.
- Fit 2000–2014 (in-sample for c): baseline Sharpe 0.79, MDD −64.2%, vol 29.0%; primary Sharpe 0.92,
  MDD −36.8%, vol 20.3%, avg exposure 0.76.

Sensitivity (validation):
| | 0 bps | 5 bps | 10 bps | 25 bps | whole-share 1% ($15.4K) | whole-share 5% ($77K) |
|---|---|---|---|---|---|---|
| primary Sharpe / MDD | 0.904 / −22.2% | 0.871 / −22.2% | 0.837 / −22.2% | 0.738 / −22.3% | 0.828 / −21.7% | 0.838 / −22.2% |
| baseline Sharpe / MDD | 0.894 / −27.8% | 0.863 / −27.9% | 0.832 / −28.0% | 0.738 / −28.3% | 0.815 / −27.6% | 0.833 / −27.9% |

Monthly turnover is heavy (~52% one-way per rebalance, ~23 trades incl. trims), so at 25 bps costs take
~3 pts/yr. The overlay saves a little turnover (0.887 avg exposure) and the MDD gap holds at every cost level.

**Survivorship caveat (applies to every number above):** the candidate pool over-represents firms that
survived to today (most delisted names have no Yahoo data; 413 names with prices in 2000 vs 599 in 2019).
Absolute returns of both baseline and overlay are biased upward, most in early years. The overlay-vs-baseline
comparison is on the same universe and is less affected, but the overlay scales the same biased portfolio.

## Interpretation choices (baseline rebuild, Step 1)
- Momentum = adj_close[t]/adj_close[t−126] − 1 (126 trading days ≈ 6 months; no skip month; the pitch
  said 180 days, the project notes said 126).
- 52-week-high proximity = adj_close[t] / max adj_close over the last 252 trading days incl. t (adjusted
  closes, no intraday highs in the data).
- 70/30 split of 15: **11 by momentum** (10.5 rounded up), then **4 by proximity** from names not already
  picked; ties in proximity (several names at 1.0) broken by momentum. No duplicates by construction.
- Eligibility: in `loader.universe(t)`, price at t and t−126, ≥ 240 valid prices in the 252-day window.
- Equal weight 1/15, monthly signal at last trading day, trade at t+1 close via `run_backtest`.
- Baseline also run 2-monthly (per the project rules), anchored so a signal falls on the month-end before scoring starts.

## Overlay choices (Step 2)
- RV_t = population variance × 252 of the unscaled baseline's daily returns (fractional, 0 bps, so the
  signal does not depend on rounding/costs) over trading days in calendar month t (≥10 obs).
- w_t = min(1, c/RV_t); rest cash at French RF. Engine trades at t+1 close.
- c: matching fit-period vol of the **capped** series to the baseline is impossible (exposure ≤ 1 means
  c → ∞). So c is the Moreira–Muir constant: the *uncapped* scaled monthly excess return has the same
  2000–2014 std as the baseline; then the cap is applied. c = 0.04745 (annualised-variance units, ≈ 21.8%
  vol threshold), fixed in config.
- Validation scoring starts with fresh capital on 2015-01-02 (first trade from the 2014-12-31 signal).
  Holdout scoring starts at `loader.perf_start`; signals warm up 13 months earlier from training data.

## Leakage checklist (ticked before validation and before freezing)
- [x] Universe via `loader.universe(t)` only.
- [x] c estimated on fit only with `TrainingLoader(max_date="2014-12-31")`; RV uses returns ≤ t.
  Truncation test: running primary with `max_date=2017-06-30` gives identical exposures, positions and
  returns (max diff 2e-16) to the full run up to that date.
- [x] Validation results labelled as validation, never as out-of-sample tests.
- [x] No same-close execution (engine t+1 close; targets not shifted).
- [x] Dates aligned: month-end signals, daily close-to-close returns, RV month = signal month.
- [x] No holdout access in strategy code; pytest 23 passed, 1 skipped.

## Open issues / next steps
0. (2026-11-17) Re-frozen on corrected universe; the holdout re-look command above is run once (reason "data correction").
1. (old) The holdout command above is run once. Holdout results must not feed back into design.
2. The project plan capped variants at 3–4 (spec allows 12); we used 3. floor25 turned out inactive in
   validation (min exposure 0.28), and c_median ≈ primary (c within 7%), so effectively only the RV
   window was tested.
3. `scripts/` (drivers: fit_c.py, fit_overlay_check.py, validate.py) is outside the code hash by design.

## Universe correction (2026-11-17) — read before doing anything
- Problem found after the first holdout run: the candidate pool used today's S&P 500 list, so stocks that joined the
  index later (TSLA before 2020-12, SMCI, CVNA, APP, HOOD, BE, ...) were tradable before they joined.
- Fix (shared code): `loader.universe(asof)` now only returns stocks that were S&P 500 members on asof
  (config/universe.yaml `membership_file`). Membership is near-complete from ~2008; sparse before.
- Consequence: this folder's freeze record no longer verifies (common/ and config/ changed). The frozen SPEC
  (config.yaml choices) stays the same; re-run its validation numbers on the corrected universe and re-freeze.
  Do not switch to another variant. First holdout results (old universe) are in outputs/holdout/ — do not use them for design.
- **Done (re-validation run, 2026-11-17):** c re-estimated (0.04745 → 0.03710), frozen spec and baseline re-run on validation
  (`_pit` variants), frozen outputs replaced, freeze record rewritten, verify passes, pytest 24 passed / 1 skipped.
  See "Current state" at the top for the before/after table.
