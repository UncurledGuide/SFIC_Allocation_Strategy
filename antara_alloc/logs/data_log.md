
## build_processed run 2026-11-17T03:12:41
- trading calendar = SPY dates: 7516 days 1997-01-02..2026-11-16
- EFA: proxy VGTSX used through 2001-08-27 (1174 days)
- AGG: proxy VBMFX used through 2003-09-29 (1696 days)
- factors monthly: 357 rows 1997-01-31..2026-09-30; MOM missing: 0
- factors daily: 7483 rows 1997-01-02..2026-09-30; MOM missing: 0
- rows in: 3,944,638; dropped non-positive/missing price rows: 0
- bad ticks removed (one-day >100%/-50% spike that reverses): 10
- returns set NaN because gap > 5 trading days: 0
- |daily return| > 300% set NaN: 11
- tickers: 659; median missing-day fraction within life: 0.0000; tickers with >5% missing days: 0
- processed prices: 3,944,628 rows, 659 tickers

## Survivorship / coverage (stock download)
- Candidate pool: 885 tickers = 503 current S&P 500 + 382 from the historical additions/removals table.
- Yahoo returned data for 659; **226 had no data (all 226 are historical names, 59% of the 382)**; Stooq fallback recovered 0.
- Current members: 503/503 have data. Historical (removed) names: 156/382 have data.
- Stocks with prices on 2000-01-03: 413; on 2019-12-31: 599. The early-year universe is therefore smaller than 500 and tilted toward survivors.
- Note: some tickers with data may be a later company that reused the symbol; not corrected.

## split run 2026-11-17T03:12:59
training <= 2019-12-31 ; holdout >= 2020-01-01

| split | file | rows | first | last | sha256 |
|---|---|---|---|---|---|
| training | prices.parquet | 2,865,149 | 1997-01-02 | 2019-12-31 | `29477a16068aa81f…` |
| test_holdout | prices.parquet | 1,079,479 | 2020-01-02 | 2026-11-16 | `6cd21113047eaca9…` |
| training | factors_daily.parquet | 5,788 | 1997-01-02 | 2019-12-31 | `0e8b82a86a5b32d8…` |
| test_holdout | factors_daily.parquet | 1,695 | 2020-01-02 | 2026-09-30 | `6ded2f0991adc9ef…` |
| training | factors_monthly.parquet | 276 | 1997-01-31 | 2019-12-31 | `4306ba0afe2bad77…` |
| test_holdout | factors_monthly.parquet | 81 | 2020-01-31 | 2026-09-30 | `c97572e960066690…` |
| training | benchmarks_daily.parquet | 5,787 | 1997-01-03 | 2019-12-31 | `501e9ae55c57b18e…` |
| test_holdout | benchmarks_daily.parquet | 1,728 | 2020-01-02 | 2026-11-16 | `933f03361c93902a…` |

training manifest sha256: `daa1cef966b3a1d30f125188e0578c1bdfe639b4b8a77abee212b253ac1bf33e`
holdout manifest sha256 (recorded before lock): `3cde03829e327009955701dea24f0f245e3bcdb2bea94e00690a0bda22a3d342`
data/test_holdout locked with chmod -R 000: YES

## Point-in-time S&P 500 membership (2026-11-17T10:28:55)
- 903 membership spells, 863 tickers -> data/membership/sp500_membership.csv
- Universe(asof) = top 500 by dollar volume among stocks that were S&P 500 members on asof.
| date | members (reconstructed) | members without Yahoo data |
|---|---|---|
| 2000 | 516 | 148 |
| 2005 | 517 | 148 |
| 2008 | 512 | 138 |
| 2010 | 511 | 131 |
| 2015 | 510 | 89 |
| 2019 | 508 | 49 |
- Changes table is sparse before ~2008 (1-11 events/yr vs ~20-40 actual): fit-period (2000-2007) membership still contains future members/survivors; validation (2015-19) and holdout use a near-complete event list.
