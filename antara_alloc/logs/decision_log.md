# Decision log

## Source summary (setup)
1. Project Doc: Allocation team goal = develop a quant strategy to maximize returns on a **1% cash allocation** of SFIC's portfolio; "New Iteration" = explore a change to the existing allocation model.
2. Existing model (Allocation Pitch): top-500-by-volume universe; 70% of picks from 6-month (180-day) momentum, 30% from 52-week-high proximity; 15 stocks EW, long-only; ~2-month (60-day) rebalance; weekly Yahoo data from 2000.
3. Pitch claims Sharpe ≈ 1.7 vs SFIC benchmark (65% S&P 500 / 15% MSCI EAFE / 20% Barclays bonds) — measured on a ~2-year window with parameters optimized in-sample (288 combinations); likely overfit.
4. Known weaknesses: higher volatility than benchmark, overfitting, weekly data granularity, ~10–11 trades per rebalance (~0.74 one-way turnover).
5. Strategy 1 (Propositions doc): residual momentum — rolling 36-month FF3 regressions, 12-1 residual returns (skip latest month), standardized by residual vol, top 15 EW, monthly.
6. Strategy 2: Moreira–Muir volatility management on the baseline portfolio — exposure w_t = c / RV_{t-1} from prior-month daily realized variance, capped [0, 1], rest in cash; c from training data only.
7. Evaluation: compare vs existing model, momentum-only baseline and SFIC benchmark; Sharpe, Sortino, MDD, vol, turnover, factor exposure; include transaction costs and out-of-sample tests.
8. SFIC holdings snapshot (positions_10_19.csv): 56 positions plus a cash line (57 line items), total ≈ $1,540,747.

## Conflicts and defaults chosen
| Conflict | Default | Why |
|---|---|---|
| Allocation 1% (Project Doc) vs 5% (Pitch) | Primary **1% ≈ $15.4K**; 5% ≈ $77K as sensitivity | Project Doc is the current mandate; 5% was a past proposal |
| Baseline rebalance "2 months" (pitch text, "15 stocks selected monthly" in pitch Step 2) | Baseline tested **monthly and every 2 months** | Source is internally inconsistent |
| Strategy rebalance | Strategy 1 and 2 **monthly** | Both papers/propositions specify monthly |
| "Top 500 by trading volume" (shares) | Rank by **dollar volume** (raw Close×Volume), 63-day trailing mean | Share volume favors low-priced stocks; dollar volume is the standard liquidity measure |
| Weekly vs daily data | **Daily** data | Strategy 2 needs daily realized variance; pitch flagged weekly as a weakness |
| Pitch "top decile long/short" vs SFIC long-only | Long-only, no leverage, exposure ≤ 1 | SFIC constraint; Strategy 2 cap is explicitly in the proposition |
| EAFE benchmark proxy | EFA, before inception VGTSX (total international, includes EM) | Free data; approximation noted |
| Bond benchmark | AGG, before inception VBMFX | Free proxy for Barclays/Bloomberg Aggregate |

## Setup defaults
- Splits: warm-up 1997–1999, fit 2000–2014, validation 2015–2019, holdout ≥ 2020-01-01 (locked).
- Execution: signal at month-end close, trade at next trading day's close; 10 bps/side base, 0/5/25 sensitivity.
- Cash earns French daily RF. Missing held-stock return = 0% (stale) and counted; after last price → cash.
- Bad ticks: drop one-day ±spikes that fully reverse (>+100% then <−50%, or reverse); |ret| > 300% → NaN; returns spanning > 5 missing trading days → NaN (no long forward-fills).
- Trading calendar = SPY trading days.
- Pre-registration cap: ≤ 12 variants per strategy before validation.
- French data library: `https://` URLs return 404; downloaded via `http://` (same host/path).
- Wikipedia's additions/removals table has moved from "List of S&P 500 companies" to "Historical components of the S&P 500"; the pool uses that article's table.
- Access restrictions: each strategy folder was blocked from reading the holdout data, the raw and processed data and the other strategy folders. The holdout folder was also locked with chmod 000.
- Leak guard: `data/raw/*.parquet|*.zip` and `data/processed/` contain post-2019 data, so after the split they were also set to chmod 000 and added to the strategy access restrictions. Rebuilding data requires the maintainer to chmod them back (logged here). `test_benchmark_splice` skips its raw-file comparison when raw is locked; it passed before locking.
- pytest.ini restricts collection to tests/ (pytest otherwise stats the locked holdout and errors).
- A pipeline smoke test (equal-weight top 15 by dollar volume, 2000–2019) ran end to end before any strategy work.
- Access-restriction test: from inside each strategy folder, reads of the holdout, data/processed, data/raw and the other strategy folders were all refused. chmod 000 remains the hard guard.
- Test fixes at setup: pandas 3 `stack()` keeps NaN, so test_data now drops NaN explicitly before the finite/non-negative checks.
- Setup final state: pytest 23 passed, 1 skipped (raw splice check, by design); smoke test ok; holdout locked unread; requirements.lock re-frozen.
- Added strategy_3_combined (Strategy 1 frozen V1 + Moreira–Muir overlay; Strategy 1 code copied verbatim into its src/s1_frozen/, overlay specified independently of Strategy 2). Shared changes: `common/run_holdout.py` STRATEGIES now includes strategy_3_combined; tests/test_imports.py checks all three folders; each strategy folder is blocked from reading the others.
- Because common/ changed, Strategy 1's code hash changed with no change to its own code (verified frozen before the edit). Its freeze record was rewritten by write_freeze_record; old record kept at logs/s1_freeze_record_before_runner_change.md. code_hash: c30a22e3ef8e51c6044f0193ea22dafbbbc4bc4417fd7f78bbf7efb6938ceb45 -> code_hash: a9e6d563c934ee3d98c1ebc719f59661e1b11e3966eb1e63271ef8d853c7cbc1.
- strategy_3_combined now uses Strategy 2's frozen overlay verbatim (src/s2_frozen/overlay.py, configs/s2_frozen_overlay.yaml: 1-month RV, cap 1, floor 0, c via mm_vol_match), copied after Strategy 2 froze and before any combination run; only c is re-estimated on V1 fit-period returns. Strategy 2's freeze record shows variants_tried 16 because count_variants counts each cost/rounding sensitivity run as a variant; its design variants were primary, rv3m, c_median, floor25.
- Holdout runs (once each, 2026-11-17): Strategy 1 holdout Sharpe 1.04, CAGR 49%, vol 45%, MDD -40%; Strategy 2 holdout Sharpe 1.02, CAGR 27%, vol 23%, MDD -24%, avg exposure 0.59; SFIC benchmark Sharpe 0.56, CAGR 11%. strategy_3_combined was not built.
- Post-holdout finding (from holdout positions only): the candidate pool includes today's S&P 500 members, so stocks that only joined the index later (e.g. BE, CVNA, APP, HOOD, SMCI, VRT) are tradable before they joined. 25% (S1) / 29% (S2) of holdout position-months were in such names. Future index additions are winners by construction, so this is a look-ahead in the pool (not in the point-in-time ranking) that inflates absolute returns in validation AND holdout; vs-benchmark comparisons are unreliable, S1 vs S2 comparisons less affected. Fix would be point-in-time membership from the changes table; not applied (would change common/ and require logged re-looks).
- **Universe correction (post-holdout):** `loader.universe(asof)` now restricted to point-in-time S&P 500 members (data/membership/sp500_membership.csv, built by data/scripts/build_membership.py from the current list walked back through the changes table). Shared files changed: common/universe.py, common/data_access.py, config/universe.yaml, tests/test_data.py (universe size floor 300 -> 250; new membership test). Changes table sparse before ~2008, so 2000–2007 membership is still partly survivor-based; renamed tickers (e.g. FB->META) are treated as always-members.
- Honesty note: the fix was prompted by inspecting the first holdout run's positions. Strategy designs (frozen configs) are NOT changed; only the shared data rule. Both strategies re-validate their frozen spec on the corrected universe, re-freeze, and the holdout is re-run once each with --override and the reason "data correction". Strategy 2 re-estimates c with its frozen fit-period rule (mm_vol_match), since the baseline's fit returns change. The first (old-universe) holdout results stay on disk and must be reported alongside.
- strategy_3_combined was built, frozen (10:22) and its holdout run (10:24) BEFORE the universe correction; it is re-validated the same way (design fixed, c re-estimated by its frozen rule). Strategies 1 and 2 re-froze on the corrected universe (S1 config unchanged; S2 c 0.04745 -> 0.03710). Holdout re-looks run sequentially, never in parallel (run_holdout unlocks/relocks the shared holdout folder).
- **Holdout re-looks on corrected (point-in-time) universe (2026-11-17 10:33, via run_holdout --override, logged RE-LOOK, run once each, sequentially; freezes verified first):** Strategy 1 (outputs/holdout/20261117-103331): Sharpe 0.61 (first 1.04), CAGR 18.6% (49.5%), vol 31.7% (45.3%), MDD -40.2% (-40.4%), turnover 5.2x/yr. Strategy 2 (outputs/holdout/20261117-103343): Sharpe 0.41 (first 1.02), CAGR 9.0% (27.0%), vol 18.5% (23.3%), MDD -20.4% (-24.1%), avg exposure 0.66 (0.59), turnover 5.0x/yr. SFIC benchmark Sharpe 0.56, CAGR 11.0%. On the corrected universe S1 beats the benchmark on Sharpe/CAGR (IR 0.46, alpha t 0.95, market beta 1.16); S2 trails the benchmark (IR -0.08) but with shallower drawdown. Run log shows variants_tried 8 (S1) and 24 (S2) at re-freeze, vs 16 for S2's first run. data/test_holdout relocked (d---------). strategy_3_combined not re-run.
- **Strategy 3 holdout re-look on corrected (point-in-time) universe (2026-11-17 10:42, run_holdout --override, logged RE-LOOK, run once; freeze verified first):** outputs/holdout/20261117-104259: Sharpe 0.34 (first 0.94), CAGR 8.0% (33.7%), vol 21.0% (33.5%), MDD -38.1% (-32.3%), avg exposure 0.75 (0.67), turnover 4.6x/yr, IR -0.12, alpha t -0.69, market beta 0.78. COVID crash -35.6% (first -29.1%); 2020 net -18.2%. Below the SFIC benchmark (Sharpe 0.56, CAGR 11.0%) and below both corrected components (S1 0.61, S2 0.41). variants_tried=3 at re-freeze (first run 1). data/test_holdout relocked (d---------).
- Final cross-strategy table: logs/final_results.md
