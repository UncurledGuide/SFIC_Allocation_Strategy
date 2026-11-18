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

## Bugs found and fixed
18. **Non-deterministic tie-break in the buffer (found during the reorg).** When more than 6 holdings were sell-eligible and several were tied (e.g. ineligible names, rank = infinity), the 6 sold were chosen by `set` iteration order, which changes with `PYTHONHASHSEED`. The same config gave different returns in different processes (up to 1.4% on a single day). Fixed by breaking ties on ticker; verified bit-identical across 3 hash seeds and covered by a unit test. Effect on previously reported numbers: only models using the two-list buffer changed (2b, 2c, 4b), by <= 0.004 Sharpe; no conclusion changed. Stage 3 (single-ranking buffer) was unaffected.
19. **Stage 3 sector map** (see 5): rows in the first Stage 3 table used 46 Unknown sectors; re-run with the complete map, differences <= 0.003 Sharpe.

## Trial accounting
20. `results/trials_log.csv` holds one row per (trial tag, cost); re-running a trial replaces its row. Early Stage 2/3 runs logged the same models under ad-hoc tags; they were renamed to the diagnostics tags (verified bit-identical) so each distinct model counts once. For the Deflated Sharpe, add the original 288 x 6 = 1,728 search trials to the distinct tags in this file.
