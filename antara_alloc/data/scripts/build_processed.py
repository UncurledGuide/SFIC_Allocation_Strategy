"""Clean data/raw -> data/processed (parquet). Logs cleaning stats to logs/data_log.md.

Outputs (data/processed/):
  prices.parquet         long: date, ticker, close (raw), adj_close, volume, dollar_volume, ret, source
  factors_daily.parquet  date, MKT-RF, SMB, HML, RF, MOM   (decimals)
  factors_monthly.parquet same, month-end dates
  benchmarks_daily.parquet date, SPY, EFA, AGG, SFIC_BENCH (daily simple returns), EFA_src, AGG_src
Run: .venv/bin/python data/scripts/build_processed.py
"""
from __future__ import annotations

import datetime as dt
import io
import json
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
from download import parse_french_csv  # noqa: E402

RAW, PROC = ROOT / "data" / "raw", ROOT / "data" / "processed"
CFG = yaml.safe_load((ROOT / "config" / "data_sources.yaml").read_text())
MAX_GAP_DAYS = 5  # trading days; a return spanning a longer gap is set NaN (not attributed)
STATS: list[str] = []


def stat(s):
    print(s)
    STATS.append(s)


def clean_prices(df: pd.DataFrame, calendar: pd.DatetimeIndex) -> pd.DataFrame:
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    n0 = len(df)
    bad = (df.close <= 0) | (df.adj_close <= 0) | df.adj_close.isna() | df.close.isna()
    df = df[~bad]
    df["volume"] = df["volume"].fillna(0).clip(lower=0)
    stat(f"- rows in: {n0:,}; dropped non-positive/missing price rows: {int(bad.sum()):,}")
    df = df[df.date.isin(calendar)]  # keep NYSE trading days only (calendar = SPY dates)
    df = df.sort_values(["ticker", "date"]).reset_index(drop=True)

    # spike detection: one-day jump that fully reverses next day -> bad tick, drop the row
    g = df.groupby("ticker")["adj_close"]
    r = g.pct_change()
    r_next = g.pct_change().groupby(df.ticker).shift(-1)
    spike = ((r > 1.0) & (r_next < -0.5)) | ((r < -0.5) & (r_next > 1.0))
    stat(f"- bad ticks removed (one-day >100%/-50% spike that reverses): {int(spike.sum())}")
    df = df[~spike.fillna(False)].reset_index(drop=True)

    # returns between consecutive observations; NaN if gap too long (no silent fills)
    pos = pd.Series(calendar.get_indexer(df.date), index=df.index)
    gap = pos.groupby(df.ticker).diff()
    df["ret"] = df.groupby("ticker")["adj_close"].pct_change()
    long_gap = gap > MAX_GAP_DAYS
    df.loc[long_gap, "ret"] = np.nan
    stat(f"- returns set NaN because gap > {MAX_GAP_DAYS} trading days: {int(long_gap.sum())}")
    extreme = df.ret.abs() > 3.0
    df.loc[extreme, "ret"] = np.nan
    stat(f"- |daily return| > 300% set NaN: {int(extreme.sum())}")
    df["dollar_volume"] = df["close"] * df["volume"]  # raw close * volume
    # missing-data stats: share of trading days between first and last obs that are missing
    span = df.groupby("ticker").agg(first=("date", "min"), last=("date", "max"), n=("date", "size"))
    span["expected"] = calendar.get_indexer(span["last"]) - calendar.get_indexer(span["first"]) + 1
    span["missing_frac"] = 1 - span.n / span.expected
    stat(f"- tickers: {len(span)}; median missing-day fraction within life: {span.missing_frac.median():.4f}; "
         f"tickers with >5% missing days: {int((span.missing_frac > 0.05).sum())}")
    return df[["date", "ticker", "close", "adj_close", "volume", "dollar_volume", "ret", "source"]]


def load_factors():
    out = {}
    for freq in ("monthly", "daily"):
        daily = freq == "daily"
        ff = [f for f in CFG["french_files"]["ff3_monthly_daily"] if ("daily" in f) == daily][0]
        mo = [f for f in CFG["french_files"]["mom_monthly_daily"] if ("daily" in f) == daily][0]
        a = parse_french_csv(zipfile.ZipFile(RAW / ff).read(zipfile.ZipFile(RAW / ff).namelist()[0]).decode("latin-1"), daily)
        b = parse_french_csv(zipfile.ZipFile(RAW / mo).read(zipfile.ZipFile(RAW / mo).namelist()[0]).decode("latin-1"), daily)
        b = b.rename(columns={c: "MOM" for c in b.columns if c != "date"})
        f = a.merge(b, on="date", how="left").rename(columns={"MKT-RF": "MKT_RF"})
        f = f[f.date >= CFG["price_start"]].reset_index(drop=True)
        assert f[["MKT_RF", "SMB", "HML", "RF"]].abs().max().max() < 1.0, "factor not in decimals?"
        stat(f"- factors {freq}: {len(f)} rows {f.date.min().date()}..{f.date.max().date()}; "
             f"MOM missing: {int(f.MOM.isna().sum())}")
        out[freq] = f
    return out


def build_benchmarks(bp: pd.DataFrame) -> pd.DataFrame:
    bp = bp.copy()
    bp["date"] = pd.to_datetime(bp["date"])
    px = bp.pivot(index="date", columns="ticker", values="adj_close").sort_index()
    ret = px.pct_change()
    out = pd.DataFrame(index=px.index)
    out["SPY"] = ret["SPY"]
    for etf, proxy in CFG["benchmarks"].items():
        if proxy is None:
            continue
        first = px[etf].first_valid_index()
        # use proxy returns strictly before the ETF's first full return day
        s = ret[etf].copy()
        use_proxy = s.index <= first  # ETF's first day has no return
        s[use_proxy] = ret.loc[use_proxy, proxy]
        out[etf] = s
        out[f"{etf}_src"] = np.where(use_proxy, proxy, etf)
        stat(f"- {etf}: proxy {proxy} used through {first.date()} ({int(use_proxy.sum())} days)")
    out = out.iloc[1:]
    # SFIC benchmark: 65/15/20, rebalanced to target at each month-end close, drifting within month
    w_t = pd.Series(CFG["sfic_benchmark_weights"])
    r = out[w_t.index].fillna(0.0)
    month = out.index.to_period("M")
    rets, w = [], w_t.copy()
    prev_m = None
    for d, m in zip(out.index, month):
        if prev_m is not None and m != prev_m:
            w = w_t.copy()  # reset at start of each new month (= previous month-end close)
        rd = r.loc[d]
        pr = float((w * rd).sum())
        rets.append(pr)
        w = w * (1 + rd) / (1 + pr)
        prev_m = m
    out["SFIC_BENCH"] = rets
    return out.reset_index().rename(columns={"index": "date", "Date": "date"})


def main():
    PROC.mkdir(parents=True, exist_ok=True)
    STATS.append(f"\n## build_processed run {dt.datetime.now().isoformat(timespec='seconds')}")
    bp = pd.read_parquet(RAW / "benchmarks_prices.parquet")
    cal = pd.DatetimeIndex(sorted(pd.to_datetime(bp.loc[bp.ticker == "SPY", "date"]).unique()))
    stat(f"- trading calendar = SPY dates: {len(cal)} days {cal[0].date()}..{cal[-1].date()}")
    bench = build_benchmarks(bp)
    bench.to_parquet(PROC / "benchmarks_daily.parquet", index=False)
    fac = load_factors()
    fac["daily"].to_parquet(PROC / "factors_daily.parquet", index=False)
    fac["monthly"].to_parquet(PROC / "factors_monthly.parquet", index=False)
    sp = pd.read_parquet(RAW / "stock_prices.parquet")
    excl = set(yaml.safe_load((ROOT / "config" / "universe.yaml").read_text())["exclude"])
    sp = sp[~sp.ticker.isin(excl)]
    prices = clean_prices(sp, cal)
    prices.to_parquet(PROC / "prices.parquet", index=False)
    stat(f"- processed prices: {len(prices):,} rows, {prices.ticker.nunique()} tickers")
    with open(ROOT / "logs" / "data_log.md", "a") as f:
        f.write("\n".join(STATS) + "\n")


if __name__ == "__main__":
    main()
