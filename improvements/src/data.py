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


SOURCE = os.environ.get("SFIC_DATA_SOURCE", CFG["data"].get("source", "yfinance"))


def _use_lseg(source):
    return (source or SOURCE) == "lseg"


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


def get_prices(refresh=False, source=None):
    if _use_lseg(source):
        return lseg_get_prices(refresh)
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


def get_universe(refresh=False, source=None):
    """Candidate pool (dict of lists). LSEG: every RIC that was ever an S&P 500 / S&P 400 member at a month-end since 2000
    (incl. delisted '^' codes) plus today's members; the month-end membership itself is lseg_membership()."""
    if _use_lseg(source):
        m, _ = lseg_membership(refresh)
        return {"sp500_ever": sorted(m[m["index"] == "sp500"].ric.unique()), "sp400_ever": sorted(m[m["index"] == "sp400"].ric.unique())}
    return get_universe_pool(refresh)


def get_sectors(tickers, refresh=False, source=None):
    if _use_lseg(source):
        return lseg_get_sectors(tickers, refresh)
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


def get_benchmark(source=None):
    if _use_lseg(source):
        return lseg_get_benchmark()
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


def get_tbill(source=None):
    if _use_lseg(source):
        return lseg_get_tbill()
    """Daily T-bill return from ^IRX (13-wk yield, %), lagged one day (yield known at prior close)."""
    y = _adj_series("^IRX", CFG["data"]["start"])
    y.index = pd.to_datetime(y.index)
    d = (y.shift(1).ffill() / 100.0) / 252.0
    return d.rename("tbill").loc[CFG["data"]["backtest_start"]:]


# =====================================================================================================
# LSEG (Workspace desktop session) source.  Select with source="lseg" or env SFIC_DATA_SOURCE=lseg.
# Identifiers are RICs (e.g. KO.N, and delisted codes like SNV.N^A26), which are unique per security and so
# avoid the ticker-reuse problem of the yfinance source.  Everything is cached under data/lseg/.
# Facts below were verified against the live API (see docs/DECISIONS.md, "LSEG source"):
#  * 0#.SPX(date) returns TODAY's members regardless of date -> history is rebuilt backwards from the TR.IndexJL* joiner/leaver table
#  * the joiner/leaver call errors on multi-year windows -> pulled one calendar year at a time
#  * get_history default prices are split-adjusted, NOT dividend-adjusted; close + TR.DivAdjustedGross on the ex-date reproduces
#    LSEG's TR.TotalReturn to ~1e-12, so the adjusted close is built from those (batched total return is ~100x slower)
#  * ACVOL_UNS on an exchange RIC (.N) is primary-exchange volume only (~30% of consolidated); the bare composite RIC is consolidated
#  * a get_history batch fails entirely if any RIC is unresolvable -> failed batches are bisected
#  * concurrent requests hit 500 timeouts -> strictly sequential
# =====================================================================================================
import hashlib, re
LSEG_DIR = DATA / "lseg"
LSEG_INDEXES = {"sp500": ".SPX", "sp400": ".MID"}
LSEG_START = CFG["data"]["start"]
_NASDAQ = ("O", "OQ")


class lseg_session:
    """with lseg_session() as ld: ...  Opens the Workspace desktop session defined in lseg-data.config.json (git-ignored)."""
    def __enter__(self):
        import warnings; warnings.filterwarnings("ignore")
        import lseg.data as ld
        self.ld = ld; ld.open_session(); return ld
    def __exit__(self, *a):
        self.ld.close_session()


def _retry(fn, tries=4, wait=5):
    err = None
    for i in range(tries):
        try:
            return fn()
        except Exception as e:                        # LDError 500 timeouts etc.
            err = e; time.sleep(wait * (i + 1))
    raise err


def _composite(ric):
    """'KO.N' -> 'KO', 'YNR.N^J00' -> 'YNR^J00'. Nasdaq (.O/.OQ) codes are already consolidated: returned unchanged."""
    m = re.match(r"^(.*?)\.([A-Z]+)(\^.*)?$", ric)
    if not m or m.group(2) in _NASDAQ:
        return ric
    return m.group(1) + (m.group(3) or "")


def lseg_current_members(ld, index_ric):
    today = pd.Timestamp.today().normalize()
    for back in range(0, 6):                          # step back over weekends/holidays
        d = (today - pd.Timedelta(days=back)).strftime("%Y-%m-%d")
        try:
            r = _retry(lambda: ld.get_data(universe=[f"0#{index_ric}({d.replace('-', '')})"], fields=["TR.PriceClose"],
                                           parameters={"SDATE": d, "EDATE": d}), tries=2)
            ric = [x for x in r["Instrument"].tolist() if isinstance(x, str)]
            if len(ric) > 100:
                return ric
        except Exception:
            pass
    raise RuntimeError(f"could not get current constituents of {index_ric}")


def lseg_changes(ld, index_ric, refresh=False):
    """Joiners/leavers since LSEG_START, one calendar year per request (multi-year windows 500). Cached."""
    f = LSEG_DIR / f"changes_{index_ric.strip('.')}.parquet"
    LSEG_DIR.mkdir(parents=True, exist_ok=True)
    if f.exists() and not refresh:
        return pd.read_parquet(f)
    F = ["TR.IndexJLConstituentChangeDate", "TR.IndexJLConstituentRIC", "TR.IndexJLConstituentName", "TR.IndexJLConstituentituentChange"]
    out = []
    for y in range(int(LSEG_START[:4]), pd.Timestamp.today().year + 1):
        a, b = f"{y}-01-01", min(pd.Timestamp(f"{y}-12-31"), pd.Timestamp.today()).strftime("%Y-%m-%d")
        try:
            d = _retry(lambda: ld.get_data(universe=[index_ric], fields=F, parameters={"SDATE": a, "EDATE": b, "IC": "B"}), tries=2)
        except Exception as e:
            if "Unable to resolve" in str(e):         # LSEG has no joiner/leaver history for this index in this year
                continue
            raise
        out.append(d)
    ch = pd.concat(out, ignore_index=True).rename(columns={"Constituent RIC": "ric", "Constituent Name": "name", "Change": "change", "Date": "date"})
    ch = ch[["date", "ric", "name", "change"]].dropna(subset=["date", "ric"]).drop_duplicates()
    ch["date"] = pd.to_datetime(ch["date"]).dt.tz_localize(None)
    ch.to_parquet(f)
    return ch


def lseg_membership(refresh=False):
    """Month-end constituents of the S&P 500 and S&P 400 since 2000, INCLUDING later-delisted names (RICs with '^').
    Rebuilt BACKWARDS from today's members by undoing each joiner/leaver (the dated chain 0#.SPX(date) is not point-in-time).
    Returns (DataFrame[index, date, ric], diagnostics dict). Cached."""
    f, fd = LSEG_DIR / "membership.parquet", LSEG_DIR / "membership_diag.json"
    if f.exists() and fd.exists() and not refresh:
        return pd.read_parquet(f), json.load(open(fd))
    rows, diag = [], {}
    with lseg_session() as ld:
        for name, ric in LSEG_INDEXES.items():
            cur = set(lseg_current_members(ld, ric))
            ch = lseg_changes(ld, ric, refresh=refresh).sort_values("date", ascending=False)
            ends = pd.date_range(LSEG_START, pd.Timestamp.today(), freq="ME")
            # some indexes' joiner table begins with a one-day bulk load of the starting constituents (S&P 400: 397 joiners on
            # 2001-07-20). Before that date membership cannot be reconstructed, so earlier month-ends are dropped.
            jc = ch[ch["change"] == "Joiner"].groupby("date").size()
            snap = jc.idxmax() if len(jc) and jc.max() > 0.5 * len(cur) else None
            state, anomalies, ptr = set(cur), {"joiner_not_in_set": 0, "leaver_already_in_set": 0}, 0
            dates, recs = ch["date"].to_numpy(), ch.reset_index(drop=True)
            sizes = {}
            for X in sorted(ends, reverse=True):
                if snap is not None and X < snap:
                    break
                while ptr < len(recs) and recs.at[ptr, "date"] > X:            # undo every change dated after X
                    d0 = recs.at[ptr, "date"]; grp = []
                    while ptr < len(recs) and recs.at[ptr, "date"] == d0:
                        grp.append(recs.iloc[ptr]); ptr += 1
                    J = {g["ric"] for g in grp if g["change"] == "Joiner"}; L = {g["ric"] for g in grp if g["change"] == "Leaver"}
                    for r in J - L:
                        anomalies["joiner_not_in_set"] += r not in state; state.discard(r)
                    for r in L - J:
                        anomalies["leaver_already_in_set"] += r in state; state.add(r)
                rows += [(name, X, r) for r in state]; sizes[X] = len(state)
            sz = pd.Series(sizes)
            diag[name] = {"index_ric": ric, "current_members": len(cur), "change_rows": int(len(ch)), "anomalies": anomalies,
                          "size_min": int(sz.min()), "size_median": float(sz.median()), "size_max": int(sz.max()),
                          "size_first_month": int(sz.sort_index().iloc[0]), "n_month_ends": int(len(sz)),
                          "initial_snapshot_date": str(snap.date()) if snap is not None else None,
                          "first_month_end": str(sz.index.min().date())}
    m = pd.DataFrame(rows, columns=["index", "date", "ric"])
    m.to_parquet(f); json.dump(diag, open(fd, "w"), indent=1, default=str)
    return m, diag


# ---------------- LSEG prices ----------------
def _norm_hist(h):
    """get_history result -> long DataFrame [price_ric, date, close, high, volume]; handles single vs multi RIC."""
    if h is None or len(h) == 0:
        return pd.DataFrame(columns=["price_ric", "date", "close", "high", "volume"])
    h = h.copy(); h.index = pd.to_datetime(h.index)
    if not isinstance(h.columns, pd.MultiIndex):
        raise ValueError("expected multi-RIC frame")
    out = []
    for r in dict.fromkeys(h.columns.get_level_values(0)):
        x = h[r]
        x = pd.DataFrame({"close": pd.to_numeric(x.get("TRDPRC_1"), errors="coerce"), "high": pd.to_numeric(x.get("HIGH_1"), errors="coerce"),
                          "volume": pd.to_numeric(x.get("ACVOL_UNS"), errors="coerce")}).dropna(subset=["close"])
        if len(x):
            out.append(x.assign(price_ric=r).rename_axis("date").reset_index())
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=["price_ric", "date", "close", "high", "volume"])


def _hist_call(ld, rics):
    end = pd.Timestamp.today().strftime("%Y-%m-%d")
    # always request >= 2 RICs so the result is a MultiIndex frame; duplicate a safe liquid RIC if needed and drop it
    pad = len(rics) == 1
    ask = list(rics) + (["SPY"] if pad else [])
    h = _retry(lambda: ld.get_history(ask, ["TRDPRC_1", "HIGH_1", "ACVOL_UNS"], interval="daily", start=LSEG_START, end=end), tries=3, wait=8)
    d = _norm_hist(h)
    return d[d.price_ric != "SPY"] if pad else d


def _hist_bisect(ld, mapping, failures):
    """mapping: exchange RIC -> RIC used for prices. A batch with any unresolvable RIC fails entirely, so bisect to isolate."""
    if not mapping:
        return []
    try:
        d = _hist_call(ld, list(mapping.values()))
        inv = {v: k for k, v in mapping.items()}
        d["ric"] = d.price_ric.map(inv)
        out = [d]
        # LSEG silently DROPS composite RICs it cannot resolve when others in the batch resolve (no exception), so retry
        # every RIC that came back empty with its exchange RIC
        redo = {k: k for k, v in mapping.items() if v != k and k not in set(d.ric)}
        if redo:
            out += _hist_bisect(ld, redo, failures)
        return out
    except Exception as e:
        if len(mapping) > 1:
            ks = list(mapping); a, b = ks[:len(ks) // 2], ks[len(ks) // 2:]
            return _hist_bisect(ld, {k: mapping[k] for k in a}, failures) + _hist_bisect(ld, {k: mapping[k] for k in b}, failures)
        (ex, pr), = mapping.items()
        if pr != ex:                                  # composite unresolvable -> fall back to the exchange RIC itself
            return _hist_bisect(ld, {ex: ex}, failures)
        failures[ex] = str(e)[:120].replace("\n", " ")
        return []


def lseg_pull_prices(rics=None, batch=10, log=lambda *a: print(*a, flush=True)):
    """Resumable. Per batch of `batch` RICs (sequential; ~19 s): split-adjusted close, high, consolidated volume + dividend events.
    Files: data/lseg/px/px_<hash>.parquet, div_<hash>.parquet; RICs with no data -> data/lseg/missing.json."""
    px_dir = LSEG_DIR / "px"; px_dir.mkdir(parents=True, exist_ok=True)
    mf = LSEG_DIR / "missing.json"
    missing = json.load(open(mf)) if mf.exists() else {}
    if rics is None:
        u = get_universe(source="lseg"); rics = sorted(set(u["sp500_ever"]) | set(u["sp400_ever"]))
    done = set()
    for f in px_dir.glob("px_*.parquet"):
        done |= set(pd.read_parquet(f, columns=["ric"]).ric.unique())
    todo = [r for r in rics if r not in done and r not in missing]
    log(f"LSEG pull: {len(rics)} RICs | already have {len(done)} | known missing {len(missing)} | to fetch {len(todo)}")
    end = pd.Timestamp.today().strftime("%Y-%m-%d")
    t0 = time.time()
    with lseg_session() as ld:
        for i in range(0, len(todo), batch):
            part = todo[i:i + batch]
            failures = {}
            frames = _hist_bisect(ld, {r: _composite(r) for r in part}, failures)
            d = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["ric", "price_ric", "date", "close", "high", "volume"])
            try:
                dv = _retry(lambda: ld.get_data(part, ["TR.DivExDate", "TR.DivAdjustedGross"], {"SDate": LSEG_START, "EDate": end}), tries=3, wait=8)
                dv = dv.rename(columns={"Instrument": "ric", "Dividend Ex Date": "ex_date", "Adjusted Gross Dividend Amount": "div"})[["ric", "ex_date", "div"]]
                dv["ex_date"] = pd.to_datetime(dv["ex_date"], errors="coerce"); dv["div"] = pd.to_numeric(dv["div"], errors="coerce")
                dv = dv.dropna()
            except Exception as e:
                log("  dividend call failed for batch:", str(e)[:100]); dv = pd.DataFrame(columns=["ric", "ex_date", "div"])
            got = set(d.ric.unique())
            for r in part:
                if r not in got:
                    missing[r] = failures.get(r, "no price rows")
            h = hashlib.md5(",".join(part).encode()).hexdigest()[:10]
            if len(d):
                d.to_parquet(px_dir / f"px_{h}.parquet"); dv.to_parquet(px_dir / f"div_{h}.parquet")
            json.dump(missing, open(mf, "w"))
            n = i + len(part)
            log(f"  {n}/{len(todo)} fetched | {len(got)}/{len(part)} with prices | cum missing {len(missing)} | {(time.time()-t0)/60:.1f} min")


def lseg_build_wide():
    """Assemble wide frames. adj_close = dividend-adjusted (total-return) close anchored to the last close, built from the
    split-adjusted close and ex-date dividends: TR_t = (P_t + D_t) / P_{t-1} - 1 (reproduces LSEG TR.TotalReturn to ~1e-12)."""
    px_dir = LSEG_DIR / "px"
    d = pd.concat([pd.read_parquet(f) for f in sorted(px_dir.glob("px_*.parquet"))], ignore_index=True)
    dv = pd.concat([pd.read_parquet(f) for f in sorted(px_dir.glob("div_*.parquet"))], ignore_index=True)
    d = d.drop_duplicates(["ric", "date"], keep="last")
    close = d.pivot(index="date", columns="ric", values="close").sort_index()
    high = d.pivot(index="date", columns="ric", values="high").reindex_like(close)
    vol = d.pivot(index="date", columns="ric", values="volume").reindex_like(close)
    div = pd.DataFrame(0.0, index=close.index, columns=close.columns)
    if len(dv):
        dv = dv[dv.ric.isin(close.columns)].copy()
        pos = close.index.searchsorted(dv["ex_date"].values)          # ex-date not a trading day -> next trading day
        dv = dv[pos < len(close.index)]; pos = pos[pos < len(close.index)]
        agg = pd.DataFrame({"i": pos, "ric": dv["ric"].values, "div": dv["div"].values}).groupby(["i", "ric"])["div"].sum()
        for (i, r), v in agg.items():
            div.iat[i, close.columns.get_loc(r)] += v
    prev = close.ffill().shift(1)
    tr = ((close + div) / prev - 1).where(close.notna()).replace([np.inf, -np.inf], np.nan)
    idxv = (1 + tr.fillna(0)).cumprod()
    scale = close.ffill().iloc[-1] / idxv.ffill().iloc[-1]
    adj = (idxv * scale).where(close.notna())
    high_adj = high * (adj / close)
    for k, v in {"adj_close": adj, "close": close, "high": high_adj, "volume": vol}.items():
        v.to_parquet(LSEG_DIR / f"prices_{k}.parquet")
    return {"adj_close": adj, "close": close, "high": high_adj, "volume": vol}


def lseg_get_prices(refresh=False):
    if refresh or not (LSEG_DIR / "prices_adj_close.parquet").exists():
        lseg_build_wide()
    return {k: pd.read_parquet(LSEG_DIR / f"prices_{k}.parquet").astype("float64") for k in FIELDS}   # float64 so NaN, not pd.NA


# ---------------- LSEG sectors / benchmark / T-bill ----------------
def lseg_get_sectors(rics, refresh=False):
    """GICS sector from LSEG. LIMITATION (verified): TR.GICSSector / GICS industry group / TRBC return TODAY's classification
    whatever SDate/Date is passed (GOOGL.O = 'Communication Services' for 2005, 2017 and 2019), so historical sectors are NOT
    available through this API; this is today's sector, same caveat as the yfinance source. Blank for many delisted codes."""
    f = LSEG_DIR / "sectors.json"
    cache = json.load(open(f)) if f.exists() and not refresh else {}
    todo = [r for r in rics if r not in cache]
    if todo:
        with lseg_session() as ld:
            for i in range(0, len(todo), 100):
                part = todo[i:i + 100]
                d = _retry(lambda: ld.get_data(part, ["TR.GICSSector"]), tries=3, wait=8)
                for r, sct in zip(d["Instrument"], d["GICS Sector Name"]):
                    cache[r] = sct if isinstance(sct, str) and sct else "Unknown"
                json.dump(cache, open(f, "w"))
    return pd.Series({r: cache.get(r, "Unknown") for r in rics})


def lseg_get_benchmark():
    """65% SPY / 15% EFA / 20% AGG (VBMFX before AGG), 21-day rebalance. Daily total returns from TR.TotalReturn (single-RIC calls)."""
    f = LSEG_DIR / "benchmark_components.parquet"
    if not f.exists():
        cands = {"SPY": ["SPY", "SPY.P"], "EFA": ["EFA", "EFA.P"], "AGG": ["AGG", "AGG.P"], "VBMFX": ["VBMFX.O"]}
        got = {}
        with lseg_session() as ld:
            for k, rl in cands.items():
                for r in rl:
                    try:
                        h = _retry(lambda: ld.get_history(r, ["TR.TotalReturn"], interval="daily", start=LSEG_START,
                                                          end=pd.Timestamp.today().strftime("%Y-%m-%d")), tries=2)
                        if len(h) > 100:
                            s = pd.to_numeric(h.iloc[:, 0], errors="coerce") / 100.0; s.index = pd.to_datetime(s.index); got[k] = s; break
                    except Exception:
                        continue
        pd.DataFrame(got).to_parquet(f)
    r = pd.read_parquet(f)
    if "VBMFX" not in r:
        # LIMITATION (verified): LSEG serves only NAV for the mutual fund VBMFX.O (no total return, no distribution events), so NAV
        # alone misses the bond income (0.3% vs 17.9% cumulative 2001-06..2004-06). LSEG has no US Aggregate index series we could
        # find either. For the pre-AGG window (before 2003-09) fall back to the yfinance VBMFX adjusted close, and say so.
        print("WARNING: benchmark AGG proxy for the pre-AGG window (2002-01..2003-09) comes from yfinance VBMFX, not LSEG")
        v = _adj_series("VBMFX", CFG["data"]["start"]); v.index = pd.to_datetime(v.index)
        r["VBMFX"] = v.pct_change(fill_method=None).reindex(r.index)
        r.to_parquet(f)
    agg = r["AGG"].where(r["AGG"].notna(), r["VBMFX"])
    comp = pd.DataFrame({"SPY": r["SPY"], "EFA": r["EFA"], "AGG": agg}).loc[CFG["data"]["backtest_start"]:].dropna()
    w = CFG["benchmark"]["weights"]; tw = pd.Series(w)[comp.columns]
    cur, out = tw.copy(), []
    for i, (_, row) in enumerate(comp.iterrows()):
        if i % CFG["trading"]["rebalance_days"] == 0:
            cur = tw * 1.0
        out.append(float((cur * row).sum())); cur = cur * (1 + row); cur = cur / cur.sum()
    return pd.Series(out, index=comp.index, name="benchmark")


def lseg_get_tbill():
    """3-month US T-bill yield (US3MT=RR, MID_YLD_1, %) -> daily return = yield/100/252, lagged one day (same convention as ^IRX)."""
    f = LSEG_DIR / "tbill_US3MT.parquet"
    if not f.exists():
        with lseg_session() as ld:
            h = _retry(lambda: ld.get_history("US3MT=RR", ["MID_YLD_1"], interval="daily", start=LSEG_START,
                                              end=pd.Timestamp.today().strftime("%Y-%m-%d")))
        s = pd.to_numeric(h.iloc[:, 0], errors="coerce").rename("v"); s.index = pd.to_datetime(s.index); s.to_frame().to_parquet(f)
    y = pd.read_parquet(f)["v"]
    return ((y.shift(1).ffill() / 100.0) / 252.0).rename("tbill").loc[CFG["data"]["backtest_start"]:]
