# Final results — all three strategies (corrected point-in-time S&P 500 universe)

Holdout = 2020-01-02 .. 2026-11-16, net of 10 bps/side, 1% allocation (~$15.4K), fractional shares.
Corrected = re-look after the universe fix (logged as RE-LOOK in holdout_access.log). Old = first run, inflated by look-ahead in the stock pool.

| | S1 Residual momentum (V1) | S2 Vol-managed baseline | S3 Combination (S1 + overlay) | SFIC benchmark |
|---|---|---|---|---|
| **Holdout Sharpe** | **0.61** | **0.41** | **0.34** | **0.56** |
| Holdout Sharpe, old (inflated) | 1.04 | 1.02 | 0.94 | 0.56 |
| Return per year | 18.6% | 9.0% | 8.0% | 11.0% |
| Volatility | 31.7% | 18.5% | 21.0% | — |
| Max drawdown | −40.2% | −20.4% | −38.1% | — |
| COVID crash (2020-02-19..03-23) | −37.8% | −19.3% | −35.6% | — |
| Jan–Oct 2022 | −10.4% | −2.2% | −6.8% | — |
| Average exposure | 1.00 | 0.66 | 0.75 | 1.00 |
| Sortino | 0.86 | 0.56 | 0.46 | — |
| Information ratio vs benchmark | 0.46 | −0.08 | −0.12 | — |
| FF4 alpha / yr (t-stat) | +6.2% (0.95) | +1.5% (0.31) | −3.2% (−0.69) | — |
| Market beta / momentum beta | 1.16 / 0.37 | 0.57 / 0.29 | 0.78 / 0.27 | — |
| Annual one-way turnover | 5.2× | 5.0× | 4.6× | — |
| **Validation 2015–19 Sharpe (corrected)** | 0.57 | 0.31 | 0.44 | 0.79 |
| Validation return / max drawdown | 10.1% / −23.7% | 4.8% / −21.3% | 7.1% / −24.1% | 9.1% / −14.8% |

Caveats: universe membership is near-complete from ~2008 but sparse before (fit period still partly survivor-biased);
~226 removed names have no Yahoo data; holdout results were inspected before the universe fix, which was prompted by
them (designs unchanged; re-looks logged). No alpha is statistically significant.
