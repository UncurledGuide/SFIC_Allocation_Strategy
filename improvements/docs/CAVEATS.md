# Caveats

These apply to every number in `RESULTS.md`. The first three bias results **upward**, so the strategy-vs-benchmark gaps are overstated.

1. **Survivorship bias.** Yahoo Finance lacks most delisted stocks: 1,096 of 1,545 pooled tickers have data (70.9%). Coverage of the S&P 500 membership at each year start: 61% (2002), 65% (2006), 70% (2010), 76% (2014), 83% (2018), 91% (2022), 99% (2026). Since the universe is always 500 names, the early years are filled with today's S&P 500/400 survivors. Replacing the point-in-time universe with *today's* top 500 lifts the baseline Sharpe from 0.91 to 1.11, which shows the order of magnitude of this effect (that run itself uses look-ahead and is not a valid backtest).
2. **Pool contains post-hoc winners.** The ticker pool includes names that entered the S&P indices later because they did well. The point-in-time dollar-volume screen reduces this but does not remove it.
3. **Sectors are today's**, not historical (8 tickers have none).
4. **yfinance is an unofficial API.** Data can contain errors and gaps; raw files contain >100% daily moves (e.g. DEC has an `inf` return) in tickers that never enter the universe. Genuine large moves inside the universe (GME 2021, CAR 2021, MRNA 2026-08-19, 40x volume) were kept. Reused ticker symbols resolve to today's company. Redistribution is restricted by Yahoo's terms.
5. **The original 70/30 split and 15-stock size came from a 288 x 6 parameter search** on a short window, so the pitch's results are in-sample. The pitch's ~1.7 Sharpe is not reproduced: the rebuilt baseline has 0.91 over 2002-present (0.78 in-sample, 1.04 out-of-sample); rolling 2-year windows reach 1.7+ in 10% of windows.
6. **Literature support is indirect.** The supporting papers mostly test long-short portfolios; this is long-only with 15 stocks. No paper tests averaging these two specific signal ranks, so support for layer 1 is indirect, and in this data L1 does not help.
7. **High market exposure.** The baseline is 100% equity with beta 1.17 (1.45 out-of-sample) against a 65/15/20 benchmark, so raw return gaps are partly market risk. Sharpe, CAPM alpha and information ratio are the fairer comparisons.
8. **Frozen delisted holdings** and **tie-breaking** (DECISIONS 4, 12) are small, generous-leaning approximations.
9. **Single run per configuration, one path of history.** No confidence intervals yet (bootstrap and Deflated Sharpe are Stage 4 items still to do); differences of a few hundredths of Sharpe between rows are not distinguishable from noise.
10. **Layer 4 is calibrated on the benchmark's 2002-2014 vol** and then held fixed; because 100%-equity strategies run well above that target, w < 1 at ~96% of rebalances, so the overlay acts mostly as a constant de-risking, not as timing.
11. **Diagnostics were run after seeing Stage 3 results**, and 4b's data fix is a spec change; both are counted as trials.
