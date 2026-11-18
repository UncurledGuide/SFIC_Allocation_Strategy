"""Single data-access interface. Swap the internals (yfinance -> CRSP/WRDS/LSEG)
without touching the rest of the code. Everything is cached to parquet in data/."""
import io, json, os, time
from pathlib import Path
import numpy as np
import pandas as pd
import requests
import yaml
import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load(open(ROOT / "config.yaml"))
DATA = ROOT / CFG["data"]["cache_dir"]
DATA.mkdir(exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (research; SFIC backtest)"}
FIELDS = ["close", "adj_close", "high", "volume"]


# ---------- ticker pool ----------
def _wiki_table(url, col):
    html = requests.get(url, headers=UA, timeout=30).text
    for t in pd.read_html(io.StringIO(html)):
        if col in t.columns:
            return t
    raise ValueError("table not found")


def get_universe_pool(refresh=False):
    """Ticker pool: all historical S&P 500 members (fja05680 dataset) + current S&P 500 + S&P 400.
    NOTE: this is a candidate POOL; the point-in-time universe is built in universe.py."""
    f = DATA / "pool.json"
    if f.exists() and not refresh:
        return json.load(open(f))
    hist = pd.read_csv(DATA / "sp500_hist_updated.csv")
    hist_t = set(t for s in hist.tickers for t in s.split(","))
    sp500 = set(_wiki_table("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", "Symbol")["Symbol"])
    sp400 = set(_wiki_table("https://en.wikipedia.org/wiki/List_of_S%26P_400_companies", "Symbol")["Symbol"])
    norm = lambda s: s.replace(".", "-")  # yfinance uses BRK-B
    pool = {"hist500": sorted(map(norm, hist_t)), "cur500": sorted(map(norm, sp500)), "cur400": sorted(map(norm, sp400))}
    json.dump(pool, open(f, "w"))
    return pool


def _download(tickers, start, chunk=80):
    out = {k: [] for k in FIELDS}
    for i in range(0, len(tickers), chunk):
        part = tickers[i:i + chunk]
        for attempt in range(3):
            try:
                df = yf.download(part, start=start, auto_adjust=False, progress=False, threads=True, group_by="column")
                break
            except Exception as e:
                print("retry", e); time.sleep(3)
        if df is None or df.empty:
            continue
        if not isinstance(df.columns, pd.MultiIndex):  # single ticker
            df.columns = pd.MultiIndex.from_product([df.columns, part[:1]])
        m = {"close": "Close", "adj_close": "Adj Close", "high": "High", "volume": "Volume"}
        for k, v in m.items():
            out[k].append(df[v])
        print(f"downloaded {min(i+chunk, len(tickers))}/{len(tickers)}", flush=True)
    return {k: pd.concat(v, axis=1) for k, v in out.items() if v}


def retry_missing(max_rounds=4, chunk=25, pause=8):
    """Re-request tickers that came back empty (many are rate-limit failures, not true delistings).
    Tickers that still fail after several slow rounds are treated as unavailable/delisted."""
    have = {k: pd.read_parquet(DATA / f"prices_{k}.parquet") for k in FIELDS}
    req = json.load(open(DATA / "requested_tickers.json"))
    for rnd in range(max_rounds):
        missing = sorted(set(req) - set(have["close"].columns))
        if not missing:
            break
        print(f"retry round {rnd}: {len(missing)} missing", flush=True)
        new = {}
        for i in range(0, len(missing), chunk):
            time.sleep(pause)
            part = _download(missing[i:i + chunk], CFG["data"]["start"], chunk=chunk)
            for k, v in part.items():
                new.setdefault(k, []).append(v)
        if not new:
            continue
        add = {k: pd.concat(v, axis=1) for k, v in new.items()}
        add["high"] = add["high"] * (add["adj_close"] / add["close"])
        for k in FIELDS:
            a = add[k].loc[:, ~add[k].columns.duplicated()].dropna(axis=1, how="all")
            have[k] = pd.concat([have[k], a], axis=1)
            have[k].to_parquet(DATA / f"prices_{k}.parquet")
    return sorted(set(req) - set(have["close"].columns))


def get_prices(refresh=False):
    """Returns dict of wide DataFrames (date x ticker): close (split-adj, NOT dividend-adj),
    adj_close (total-return adj), high (dividend-adj, consistent with adj_close), volume (split-adj shares)."""
    f = DATA / "prices_adj_close.parquet"
    if not f.exists() or refresh:
        pool = get_universe_pool()
        tickers = sorted(set(pool["hist500"]) | set(pool["cur500"]) | set(pool["cur400"]))
        raw = _download(tickers, CFG["data"]["start"])
        ratio = raw["adj_close"] / raw["close"]
        raw["high"] = raw["high"] * ratio  # put 52w-high on the same adjusted basis as adj_close
        for k, v in raw.items():
            v = v.loc[:, ~v.columns.duplicated()]
            v = v.dropna(axis=1, how="all")
            v.to_parquet(DATA / f"prices_{k}.parquet")
        json.dump(tickers, open(DATA / "requested_tickers.json", "w"))
        retry_missing()   # the first pass is rate-limited by Yahoo; re-request empty tickers slowly
    return {k: pd.read_parquet(DATA / f"prices_{k}.parquet") for k in FIELDS}


def get_universe(refresh=False):
    """Alias kept for the interface: returns the candidate pool (dict of lists)."""
    return get_universe_pool(refresh)


def get_sectors(tickers, refresh=False):
    """Today's yfinance .info sector (NOT point-in-time). Cached. Failed lookups (rate limits) are retried and
    never cached as 'Unknown'; 'Unknown' means Yahoo answered but has no sector (e.g. funds)."""
    from concurrent.futures import ThreadPoolExecutor
    f = DATA / "sectors.json"
    cache = json.load(open(f)) if f.exists() and not refresh else {}
    def one(t):
        try:
            return t, ((yf.Ticker(t).info or {}).get("sector") or "Unknown")
        except Exception:
            return t, None
    for rnd in range(4):
        todo = [t for t in tickers if t not in cache]
        if not todo:
            break
        with ThreadPoolExecutor(4) as ex:
            for t, sct in ex.map(one, todo):
                if sct is not None:
                    cache[t] = sct
        json.dump(cache, open(f, "w"))
        time.sleep(5)
    return pd.Series({t: cache.get(t, "Unknown") for t in tickers})


def _adj_series(t, start):
    f = DATA / f"idx_{t.replace('^','')}.parquet"
    if f.exists():
        return pd.read_parquet(f)["v"]
    df = yf.download(t, start=start, auto_adjust=False, progress=False)
    s = df["Adj Close"].squeeze() if t != "^IRX" else df["Close"].squeeze()
    s.name = "v"
    s.to_frame().to_parquet(f)
    return s


def get_benchmark():
    """Daily returns of SFIC benchmark: 65% SPY / 15% EFA / 20% AGG (VBMFX before AGG),
    rebalanced every `rebalance_days` trading days (same calendar as the strategy)."""
    w = CFG["benchmark"]["weights"]
    start = CFG["data"]["start"]
    px = pd.DataFrame({t: _adj_series(t, start) for t in list(w) + [CFG["benchmark"]["agg_proxy"]]})
    px.index = pd.to_datetime(px.index)
    r = px.pct_change(fill_method=None)
    agg = r["AGG"].where(r["AGG"].notna(), r[CFG["benchmark"]["agg_proxy"]])
    comp = pd.DataFrame({"SPY": r["SPY"], "EFA": r["EFA"], "AGG": agg}).loc[CFG["data"]["backtest_start"]:].dropna()
    tw = pd.Series(w)[comp.columns]
    cur = tw.copy(); out = []
    for i, (_, row) in enumerate(comp.iterrows()):
        if i % CFG["trading"]["rebalance_days"] == 0:
            cur = tw * 1.0
        pr = float((cur * row).sum()); out.append(pr)
        cur = cur * (1 + row); cur = cur / cur.sum()
    return pd.Series(out, index=comp.index, name="benchmark")


def get_tbill():
    """Daily T-bill return from ^IRX (13-wk yield, %), lagged one day (yield known at prior close)."""
    y = _adj_series("^IRX", CFG["data"]["start"])
    y.index = pd.to_datetime(y.index)
    d = (y.shift(1).ffill() / 100.0) / 252.0
    return d.rename("tbill").loc[CFG["data"]["backtest_start"]:]
