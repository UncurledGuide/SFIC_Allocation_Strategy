# Decisions log

Choices the spec left open, deviations from it, and bugs found along the way. All parameters in `config.yaml` were fixed
before seeing results and have not been tuned. Anything marked **SPEC CHANGE** was made after seeing results.

## Data and universe
1. **Pool**: all historical S&P 500 members (fja05680 "Updated" file, plain tickers), plus current S&P 500 and S&P 400 (Wikipedia). 1,545 tickers; 1,096 have Yahoo data.
2. **Universe at each signal date**: top 500 by trailing 63-day average of *unadjusted close x volume* among pool names with >= 252 days of history. Raw close (not dividend-adjusted) is used so dollar volume is not distorted by dividend adjustment. Returns use adjusted close; the 52-week high is scaled onto the same adjusted basis.
3. **Rate-limit retries**: the first Yahoo pass silently dropped ~380 tickers (XOM, WM, ZTS...). `retry_missing()` re-requests them slowly; what still fails is treated as delisted/unavailable.
4. **Frozen delisted holdings**: a held stock whose data ends gets 0% return afterwards (no forced sale). Mildly generous.
5. **Sectors** are yfinance `.info` sectors fetched today. Tickers Yahoo has no sector for (8) are treated as their own one-name sector, so the cap never binds on them. A first sector pass had 46 Unknown because of rate limits; the layer 2/3 rows were re-run on the complete map.

## Execution
6. Signal on day t close -> trade at t+1 close -> new weights first earn the return of t+2. Holdings drift between rebalances. Tested in `tests/test_no_lookahead.py`.
7. Rebalance every 21 trading days from 2002-01-02 (299 signal dates). The benchmark uses the same 21-day calendar.
8. **Costs** = bps x sum of |weight change| on the trade day (buys and sells both count). T-bill leg is free. Main results use 0 bps.
9. **Swaps** = names sold (= names bought). The initial build is excluded from swap/turnover stats (a bug counting one real rebalance twice in each period was found and fixed at Stage 3).
10. **T-bill return** = ^IRX yield / 100 / 252, lagged one day.
11. **Beta / alpha** are from a regression of daily excess returns over T-bills on the benchmark's excess return; alpha is annualised x252. Information ratio = annualised mean active return / tracking error.

## Baseline and layers
12. **Baseline picker**: 10 names by 180-day return, then the 5 best 52-week-high names not already picked. **Ties** at the 52-week-high cutoff (many names close at exactly 1.0) are broken by universe (alphabetical) order. This decides the last slot at 9 of 279 rebalances.
13. **L1** = mean of cross-sectional percentile ranks of 6-1 momentum and 52-week-high nearness over the point-in-time universe.
14. **L2** = inverse 63-day-vol weights, max 4 names per sector (greedy down the ranked list, skipping names that would breach).
15. **L3** = buy when a stock enters the top 15, sell only when it ranks below 25, at most 6 sold per rebalance (lowest ranked first), buys = sells.
16. **EXTENSION - L3 on the two-list baseline** (models 2a-2c, 4a-4b): the spec defines the buffer for one ranking, but the baseline has two lists. A holding is kept while it is in the top 18 of the momentum list or the top 7 of the 52-week-high list (the n=25 version of the 70/30 split); replacements come from the n=15 selection, ordered by rank within their own list.
17. **SPEC CHANGE (after diagnostics) - L2 data-quality fix**: names with annualised 63-day vol < 8% or > 5 zero-return days are excluded from L2 models, and weights are capped at 10% (excess redistributed pro rata). Reason: inverse-vol gave a pinned takeover target (TECH, ~2% vol) a 51% weight on the final signal date, and Baseline+L2 reached a 55.6% weight at one traded rebalance. The filter removes 251 of 149,500 universe stock-dates. Both the spec-L2 and fixed-L2 versions are reported.
18. **Layer 4** (see `src/overlay.py`): w = min(1, sigma_target / sigma_hat). sigma_target = benchmark daily vol on 2002-2014 x sqrt(252), computed once (16.0%). sigma_hat = trailing 126-day vol of the *unlevered* strategy's own returns through the signal date (using the levered returns would be circular). w is updated only on signal dates and only if it moves by more than 0.10; w = 1 until 126 days of strategy history exist. Remainder in T-bills. The two-pass implementation (unlevered run -> exposure schedule -> scaled run) leaves stock selection unchanged.

## Bugs found and fixed
19. **Non-deterministic tie-break in the buffer (found during the reorg).** When more than 6 holdings were sell-eligible and several were tied (e.g. ineligible names, rank = infinity), the 6 sold were chosen by `set` iteration order, which changes with `PYTHONHASHSEED`. The same config gave different returns in different processes (up to 1.4% on a single day). Fixed by breaking ties on ticker; verified bit-identical across 3 hash seeds and covered by a unit test. Effect on previously reported numbers: only models using the two-list buffer changed (2b, 2c, 4b), by <= 0.004 Sharpe; no conclusion changed. Stage 3 (single-ranking buffer) was unaffected.
20. **Stage 3 sector map** (see 5): rows in the first Stage 3 table used 46 Unknown sectors; re-run with the complete map, differences <= 0.003 Sharpe.

## Trial accounting
21. `results/trials_log.csv` holds one row per (trial tag, cost); re-running a trial replaces its row. Early Stage 2/3 runs logged the same models under ad-hoc tags; they were renamed to the diagnostics tags (verified bit-identical) so each distinct model counts once. For the Deflated Sharpe, add the original 288 x 6 = 1,728 search trials to the distinct tags in this file.

## LSEG data and Stage 4 (after tag `lseg-ablation`)
22. **LSEG is the primary data source for all Stage 4 work.** Universe pool = every RIC that was in the S&P 500 or S&P 400 at any month-end since 2000 (2,081 RICs, 948 delisted '^' codes; 99.8% priced). Membership is rebuilt by replaying LSEG's index-change history backward from today's members. The point-in-time top-500 dollar-volume rule is unchanged. yfinance remains available (`SFIC_DATA_SOURCE`) as a cross-check. The LSEG caches are git-ignored (licensed data, public repo).
23. **Adjusted prices on LSEG** = unadjusted close plus ex-date dividends (total-return chain anchored to the last close); high is scaled by the same factor. Composite RICs (no exchange suffix) are used for price/volume because exchange RICs give only primary-venue volume. Benchmark AGG/SPY/EFA come from LSEG; the pre-AGG VBMFX proxy and nothing else comes from Yahoo (printed warning).
24. **'Live rule' baseline** (copied from the group's live-rebalance notebook, not its backtest notebook): 10 names by return from t-200 to t-20, plus the 5 best names by price / prior-252-day max close (shifted one day, so a new high scores above 1) that are not already picked; 15 names; equal weight (the notebook's 7%/6% sleeve weights change the Sharpe by 0.006, so equal weight is used). Execution, costs and universe are ours, not the notebook's (next-day close, 0/5/10 bps).
25. **Candidates fixed before the Stage 4 stats:** A = live-rule baseline, B = A + L3 (exit rank 25, max 6 swaps), C = B + L4 (unchanged parameters). L2 was dropped from the candidates because it lowered the Sharpe on the live-rule baseline in the ablation.
26. **Deflated Sharpe:** N = distinct tags in `trials_log.csv` + 1,728. The variance of Sharpe across trials is estimated from the Sharpes logged for the distinct tags (lowest cost each); expected max Sharpe under the null uses the Bailey-Lopez de Prado formula; skewness and kurtosis of each candidate's daily excess returns enter the denominator.
27. **Bootstrap:** paired circular block bootstrap of daily returns (the same resampled days for A, B and C), 63-day blocks, 10,000 resamples, seed 42; Sharpe on excess-over-T-bill returns; max drawdown recomputed on each resampled path.
28. **Robustness choices:** the L3 parameters (exit rank 25, 6 swaps) were NOT rescaled for portfolio sizes 10 and 20; 'buffer 30' changes only the exit rank; the 2-month rebalance uses every second monthly signal date (L4 exposure also updates only then). Each variant is a logged trial (`rob:` tags).
29. **Pre-set L4 rule** was applied exactly as written: Max DD >= -49% AND Sharpe fall vs B <= 0.05, stated on the point estimate and on whether the bootstrap CI for the C - B Sharpe difference includes 0.

## New-ideas round (pre-registered; run once each)
30. **Setup:** each idea is a swap into candidate B (live-rule baseline + L3, equal weight, monthly, exit rank 25, max 6 swaps) on LSEG data, run once at 0/5/10 bps, no tuning, no combinations. Pass rule: Sharpe beats B by >= 0.10 in both 2002-2014 and 2015-2026 AND full-sample max DD no worse than B's (idea 3 is also compared with C).
31. **Idea 1, residual momentum:** monthly excess returns (month-end adjusted close, minus compounded T-bill) regressed on SPY excess returns over 36 completed months; score = sum of the residuals for the last 12 completed months / std of the 36 residuals; only months strictly before the rebalance date's month are used, so the current partial month is skipped. The 52-week-high list is unchanged (70/30 kept). A name needs all 36 months. Because the data starts in 2000-01 the first valid score is for the 2003-01 rebalance; 2002 is held in T-bills (disclosed in RESULTS). The first run used a T-bill series cut at 2002 and so waited until 2005; that was a plumbing bug found on inspection, fixed (raw T-bill cache from 2000) and re-run; the first run's trial row was replaced, not kept.
32. **Idea 2, frog-in-the-pan:** momentum list = B's live momentum (return t-200..t-20); take the top 30 of the point-in-time universe, order them by ID = sign(12-1 return) x (share of negative days - share of positive days) over t-252..t-21, and the 10 momentum slots take the 10 lowest-ID names (ties by momentum order). The buffer's top-18 exit list then follows the same ordering. The 5 high-list names are unchanged.
33. **Idea 3, crash-state rule:** exposure 50% when the benchmark's trailing 504-day return is negative AND B's unlevered 126-day vol exceeds its own median over 2002-2014 (one constant); otherwise 100%; the rest in T-bills; set on rebalance dates only; 100% until both histories exist. Same two-pass mechanics as L4. The 2002-2014 median is in-sample for those years, as L4's target is.
34. **Idea 4, 12-1 momentum:** return from t-252 to t-21 replaces B's t-200..t-20 momentum list; everything else as B.
35. **Deflated Sharpe update:** the best idea by full-sample Sharpe is tested with N = distinct tags in `trials_log.csv` (now 37) + 1,728. Stage 4's DSRs used N = 1,761 (before the ideas round).

