# STATUS — strategy_3_combined

_Read this file first and update it after each change._

## Current state: RE-FROZEN on point-in-time universe (2026-11-17T10:34:18) — holdout re-look NOT run here
- Design unchanged: frozen V1 (src/s1_frozen, hashes match SOURCE_SHA256.txt and Strategy 1) + frozen MM overlay
  (src/s2_frozen/overlay.py, matches Strategy 2; 1-month RV, cap 1, floor 0, mm_vol_match). src/ untouched;
  entrypoint.py unchanged (no run failed).
- **c re-estimated by the same rule** on unmanaged V1 fit-period (2000–2014) returns, TrainingLoader(max_date
  2014-12-31), PIT universe: **c 0.060743 → 0.048673** (RV median fit 0.0563 → 0.0448). New config
  `configs/primary_pit.yaml` = `outputs/frozen/config.yaml` (only config change; `configs/primary.yaml` kept as the
  old-universe record). `logs/c_estimate_fit_pit.json`.
- Runs (PIT): fit `runs/20261117-103339-primary_pit-b28d6ac6`; validation `runs/20261117-103349-primary_pit-922c5ab5`;
  unmanaged V1 reference `runs/20261117-103356-unmanaged_v1_pit-922c5ab5`. Scripts: `scripts/fit_c_pit.py`,
  `scripts/validate_pit.py` (`--unmanaged` for the reference run); scripts/ is outside the code hash.
- Freeze record rewritten: config_hash a7a1743c…, code_hash 922c5ab5… (= validation run hash); `verify` passes.
  variants_tried shows 3 because count_variants counts variant names (primary, primary_pit, unmanaged_v1_pit);
  **design variants = 1** (primary spec only; unmanaged_v1_pit is a reference run). Total runs logged 5.
- Old frozen outputs (old universe) kept in `logs/frozen_pre_universe_correction/` (incl. old freeze_record, config,
  c_estimate). First (old-universe) holdout stays in outputs/holdout/20261117-102403 and did not feed into this.
- pytest: 24 passed, 1 skipped.

## Before/after: validation 2015-01-01..2019-12-31, 10 bps, fractional (validation, not out-of-sample)
| | Combo old | Combo PIT | Unmanaged V1 old | Unmanaged V1 PIT | SFIC old | SFIC PIT |
|---|---|---|---|---|---|---|
| c | 0.06074 | 0.04867 | – | – | – | – |
| Sharpe | 0.924 | **0.435** | 1.025 | **0.573** | 0.793 | 0.793 |
| CAGR | 18.1% | 7.1% | 21.5% | 10.1% | 9.1% | 9.1% |
| Vol | 18.8% | 16.7% | 20.0% | 17.8% | 10.4% | 10.4% |
| Max DD | −24.1% | −24.1% | −25.4% | −23.7% | −14.8% | −14.8% |
| Avg exposure | 0.95 | 0.94 (w min 0.42; 83% of months at cap) | 1.00 | 1.00 | | |
| Annual one-way turnover | 5.03× | 4.85× | 5.08× | 4.87× | | |
| Cost drag (annual) | 1.01% | 0.98% | 1.02% | 0.98% | | |
- Sharpe diff combo − unmanaged V1: old −0.101 [−0.229, +0.021] → PIT **−0.138 [−0.287, +0.004]** (P(≤0) 0.97).
- Sharpe diff combo − SFIC: old +0.131 [−0.440, +0.681] → PIT **−0.358 [−0.956, +0.185]** (P(≤0) 0.91).
- Combo Sharpe CI: old [0.11, 1.72] → PIT [−0.35, 1.22].
- Cost sensitivity PIT, Sharpe combo / unmanaged (diff CI): 0 bps 0.493/0.628 [−0.283, 0.008]; 5 bps 0.464/0.600
  [−0.285, 0.006]; 10 bps 0.435/0.573 [−0.287, 0.004]; 25 bps 0.348/0.490 [−0.293, −0.002]. Combo MDD −23.9/−24.0/−24.1/−24.4%.
- Fit 2000–2014 PIT (10 bps): combo Sharpe 0.673, vol 19.5%, MDD −35.1% vs unmanaged 0.673, 29.8%, −65.3%
  (old universe: 1.13 vs 0.98).
- Reading: H1 (lower vol AND shallower MDD than unmanaged) now only half holds in validation (vol lower, MDD
  slightly deeper); H2 (Sharpe ≥ unmanaged) not met; combo below the SFIC benchmark on point estimate.

## Superseded: first freeze on the old universe (kept for the record)
### FROZEN (2026-11-17T10:22:20), old universe
- Spec: frozen V1 (src/s1_frozen, unchanged; hashes match SOURCE_SHA256.txt) + frozen MM overlay
  (src/s2_frozen/overlay.py, unchanged; 1-month RV on unmanaged V1 fractional 0-bps returns, cap 1, floor 0).
  Only c re-estimated: **c = 0.060743** (mm_vol_match, unmanaged V1, fit 2000-01..2014-12, TrainingLoader
  max_date 2014-12-31). First signal (1999-12-31) has no RV → w = 1 (fit only).
- Code: `src/entrypoint.py` (refuses any v1/overlay cfg that differs from the frozen configs except c);
  `scripts/fit_c.py`, `scripts/validate.py` (scripts/ is outside the code hash; not used by the holdout).
- Frozen config: `configs/primary.yaml` = `outputs/frozen/config.yaml`. Freeze record: `outputs/frozen/freeze_record.md`
  (config_hash 77f0690a…, code_hash 7b10727c…, variants_tried 1, total runs 2). `run_holdout.verify` passes.
- Variants tried: **1** (primary). Pre-registration: `logs/preregistration.md` (written before validation).
- Runs: fit `runs/20261117-102118-primary-125c58b0` (its code hash predates writing configs/primary.yaml),
  validation `runs/20261117-102201-primary-7b10727c`.

### Old-universe validation results (2015-01-01..2019-12-31), 10 bps, fractional
| | Managed (primary) | Unmanaged V1 | SFIC bench |
|---|---|---|---|
| Sharpe | 0.924 | 1.025 | 0.793 |
| CAGR | 18.1% | 21.5% | 9.1% |
| Vol | 18.8% | 20.0% | 10.4% |
| Max DD | −24.1% | −25.4% | −14.8% |
| Avg exposure | 0.95 (w mean 0.95, min 0.44, 83% of months at cap) | 1.00 | |
| One-way turnover / rebalance; annual | 0.42; 5.03× | 0.42; 5.08× | |
| Trades / rebalance | 21.0 | 21.0 | |
| Cost drag (annual) | 1.01% | 1.02% | |
- Sharpe diff vs unmanaged V1: −0.101, 95% CI [−0.229, +0.021] (P(≤0) 0.95). H1 (lower vol/MDD) met but small;
  H2 (Sharpe ≥ unmanaged) NOT met.
- Sharpe diff vs SFIC benchmark: +0.131, 95% CI [−0.440, +0.681]. Primary Sharpe CI [0.11, 1.72].
- Cost sensitivity, Sharpe managed / unmanaged (diff CI): 0 bps 0.977/1.076 [−0.226, 0.024];
  5 bps 0.951/1.051 [−0.227, 0.022]; 10 bps 0.924/1.025; 25 bps 0.843/0.948 [−0.234, 0.016].
- Factor loadings (daily, NW): β_MKT 1.06, β_SMB 0.41, β_MOM 0.19, α 6.2%/yr (t 1.26).
- Fit (2000–2014, 10 bps): managed Sharpe 1.13, vol 22.1%, MDD −33.9% vs unmanaged 0.98, 32.5%, −66.6%.

## Open issues / caveats
- **Survivorship:** only 413 stocks priced on 2000-01-03 (599 by 2019-12-31); pool over-represents survivors,
  absolute returns biased upward (fit-period CAGRs ~27–33% are not credible as levels). Report with every result.
- 2015–2019 was a calm period (overlay at cap 83% of months), so the overlay mostly cost return via the
  occasional de-risking; its fit-period benefit came from 2000–2002/2008-type regimes.
- If Strategy 1 or 2 is re-frozen, the copies in src/s1_frozen or src/s2_frozen are stale (compare SOURCE_SHA256.txt).
- Do not edit src/, configs/, common/ or config/ now — run_holdout refuses if the code hash changes.
- Survivorship (PIT): membership changes table sparse before ~2008, so 2000–2007 (fit) is still partly survivor-based.

## Next steps
1. Holdout re-look (once, logged "data correction", sequential with S1/S2):
   `.venv/bin/python -m common.run_holdout --strategy strategy_3_combined --confirm-freeze --override`
   Report alongside the first (old-universe) holdout in outputs/holdout/20261117-102403.

## Universe correction (2026-11-17) — read before doing anything
- The first freeze and holdout (10:22 / 10:24) used the old universe, whose candidate pool used today's S&P 500 list,
  so stocks that joined the index later were tradable early (look-ahead that inflated returns).
- Fix (shared code, ~10:29): `loader.universe(asof)` now only returns stocks that were S&P 500 members on asof.
  Membership is near-complete from ~2008; sparse before.
- `src/s1_frozen/` and `src/s2_frozen/overlay.py` are still byte-identical to Strategies 1 and 2 (no code changed there).
- This folder's freeze record no longer verifies. Keep the design; re-estimate c with the frozen rule on corrected
  fit data, re-run validation, re-freeze. First holdout results stay in outputs/holdout/ and must not feed into design.
- **Done (2026-11-17 ~10:34):** c re-estimated (0.06074 → 0.04867), validation re-run, re-frozen, verify passes.
  See "Current state" and "Before/after" at the top.
