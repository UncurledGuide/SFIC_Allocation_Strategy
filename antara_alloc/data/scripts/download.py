"""Download all raw data into data/raw/ and write data/raw/manifest.json.

Raw files are immutable: re-running skips files that already exist unless --force.
Run: .venv/bin/python data/scripts/download.py
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import sys
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests
import yaml

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
CFG = yaml.safe_load((ROOT / "config" / "data_sources.yaml").read_text())
UA = {"User-Agent": "Mozilla/5.0 (research data download)"}
LOG = []


def log(msg):
    print(msg, flush=True)
    LOG.append(f"{dt.datetime.now().isoformat(timespec='seconds')} {msg}")


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load_manifest():
    p = RAW / "manifest.json"
    return json.loads(p.read_text()) if p.exists() else {"files": {}}


def save_manifest(m):
    (RAW / "manifest.json").write_text(json.dumps(m, indent=2, sort_keys=True))


def record(m, path: Path, source, rows=None, tickers=None, extra=None):
    entry = {
        "source": source,
        "downloaded_at": dt.datetime.now().isoformat(timespec="seconds"),
        "sha256": sha256(path),
        "bytes": path.stat().st_size,
    }
    if rows is not None:
        entry["rows"] = int(rows)
    if tickers is not None:
        entry["n_tickers"] = len(tickers)
        entry["tickers"] = sorted(tickers)
    if extra:
        entry.update(extra)
    m["files"][path.name] = entry
    save_manifest(m)


# ---------------------------------------------------------------- Wikipedia
def norm_ticker(t: str) -> str:
    return str(t).strip().upper().replace(".", "-")


def get_wikipedia(m, force=False):
    html_p = RAW / "wikipedia_sp500.html"
    if force or not html_p.exists():
        r = requests.get(CFG["wikipedia_url"], headers=UA, timeout=60)
        r.raise_for_status()
        html_p.write_bytes(r.content)
        record(m, html_p, CFG["wikipedia_url"])
    current = pd.read_html(io.StringIO(html_p.read_text()))[0]
    # The additions/removals table was moved off the main list page to its own article.
    hist_p = RAW / "wikipedia_sp500_historical_components.html"
    if force or not hist_p.exists():
        r = requests.get(CFG["wikipedia_changes_url"], headers=UA, timeout=60)
        r.raise_for_status()
        hist_p.write_bytes(r.content)
        record(m, hist_p, CFG["wikipedia_changes_url"])
    changes = pd.read_html(io.StringIO(hist_p.read_text()))[0]
    ch_p = RAW / "sp500_changes.csv"
    if force or not ch_p.exists():
        flat = changes.copy()
        flat.columns = ["_".join(dict.fromkeys(c)) if isinstance(c, tuple) else c for c in flat.columns]
        flat.to_csv(ch_p, index=False)
        record(m, ch_p, "derived from wikipedia_sp500_historical_components.html table 0", rows=len(flat))
    cur = sorted({norm_ticker(t) for t in current["Symbol"]})
    # changes table has MultiIndex columns: (Added, Ticker), (Removed, Ticker)
    hist = set()
    for col in changes.columns:
        if isinstance(col, tuple) and col[-1].lower().startswith("ticker"):
            hist |= {norm_ticker(t) for t in changes[col].dropna() if str(t).strip() and str(t) != "nan"}
    hist -= set(cur)
    pool = pd.DataFrame(
        [(t, "current") for t in cur] + [(t, "historical_change") for t in sorted(hist)],
        columns=["ticker", "origin"],
    )
    p = RAW / "candidate_pool.csv"
    if force or not p.exists() or "n_historical" not in m["files"].get(p.name, {}) or m["files"][p.name]["n_historical"] == 0:
        pool.to_csv(p, index=False)
        record(m, p, "derived from wikipedia_sp500.html (tables 0 and 1)", rows=len(pool),
               extra={"n_current": len(cur), "n_historical": len(hist)})
    log(f"Candidate pool: {len(cur)} current + {len(hist)} historical-only = {len(pool)}")
    return pool


# ---------------------------------------------------------------- French
def parse_french_csv(text: str, daily: bool) -> pd.DataFrame:
    """Parse the first data block of a French CSV (skip annual block). Returns decimals."""
    lines = text.splitlines()
    out, header, started = [], None, False
    for ln in lines:
        parts = [x.strip() for x in ln.split(",")]
        if not started:
            if len(parts) > 1 and parts[0] == "" and any(p for p in parts[1:]):
                header = ["date"] + parts[1:]
                started = True
            continue
        if not parts[0] or not parts[0].isdigit():
            if out:
                break
            continue
        if (daily and len(parts[0]) != 8) or (not daily and len(parts[0]) != 6):
            break
        out.append(parts[: len(header)])
    df = pd.DataFrame(out, columns=header)
    fmt = "%Y%m%d" if daily else "%Y%m"
    df["date"] = pd.to_datetime(df["date"], format=fmt)
    if not daily:
        df["date"] = df["date"] + pd.offsets.MonthEnd(0)
    for c in df.columns[1:]:
        df[c] = pd.to_numeric(df[c], errors="coerce") / 100.0  # percent -> decimal
    df.columns = [c.replace(" ", "").replace("Mom", "MOM").upper() if c != "date" else c for c in df.columns]
    return df


def get_french(m, force=False):
    base = CFG["french_base_url"]
    for group in CFG["french_files"].values():
        for fn in group:
            zp = RAW / fn
            if force or not zp.exists():
                for attempt in range(4):
                    try:
                        r = requests.get(base + fn, headers=UA, timeout=60)
                        r.raise_for_status()
                        zp.write_bytes(r.content)
                        break
                    except Exception as e:  # noqa
                        log(f"French {fn} attempt {attempt+1} failed: {e}")
                        time.sleep(2 ** attempt)
                else:
                    log(f"FAILED French {fn}")
                    continue
                daily = "daily" in fn
                with zipfile.ZipFile(zp) as z:
                    txt = z.read(z.namelist()[0]).decode("latin-1")
                df = parse_french_csv(txt, daily)
                record(m, zp, base + fn, rows=len(df),
                       extra={"first": str(df.date.min().date()), "last": str(df.date.max().date())})
                log(f"French {fn}: {len(df)} rows {df.date.min().date()}..{df.date.max().date()}")


# ---------------------------------------------------------------- Prices
def yf_batch(tickers, start, end):
    import yfinance as yf
    df = yf.download(tickers, start=start, end=end, auto_adjust=False, actions=False,
                     group_by="column", threads=True, progress=False, timeout=60)
    if df is None or df.empty:
        return pd.DataFrame()
    if not isinstance(df.columns, pd.MultiIndex):
        df.columns = pd.MultiIndex.from_product([df.columns, tickers])
    long = df.stack(level=1, future_stack=True).reset_index()
    long.columns = [str(c) for c in long.columns]
    long = long.rename(columns={"Date": "date", "Ticker": "ticker", "level_1": "ticker",
                                "Adj Close": "adj_close", "Close": "close", "Open": "open",
                                "High": "high", "Low": "low", "Volume": "volume"})
    long = long.dropna(subset=["close", "adj_close"], how="all")
    return long[["date", "ticker", "open", "high", "low", "close", "adj_close", "volume"]]


def stooq_one(t, start):
    url = f"https://stooq.com/q/d/l/?s={t.lower().replace('-', '.')}.us&i=d"
    r = requests.get(url, headers=UA, timeout=30)
    if r.status_code != 200 or not r.text.startswith("Date"):
        return pd.DataFrame()
    d = pd.read_csv(io.StringIO(r.text))
    d = d.rename(columns={"Date": "date", "Open": "open", "High": "high", "Low": "low",
                          "Close": "close", "Volume": "volume"})
    d["date"] = pd.to_datetime(d["date"])
    d = d[d.date >= start]
    # Stooq close is split-adjusted but not dividend-adjusted: use as adj_close approximation.
    d["adj_close"] = d["close"]
    d["ticker"] = t
    return d[["date", "ticker", "open", "high", "low", "close", "adj_close", "volume"]]


def get_prices(m, tickers, out_name, batch=50, force=False):
    out = RAW / out_name
    if out.exists() and not force:
        log(f"{out_name} exists, skipping")
        return pd.read_parquet(out)
    start = CFG["price_start"]
    end = (dt.date.today() + dt.timedelta(days=1)).isoformat()
    frames, failed = [], []
    for i in range(0, len(tickers), batch):
        b = tickers[i:i + batch]
        for attempt in range(5):
            try:
                d = yf_batch(b, start, end)
                break
            except Exception as e:  # noqa
                wait = 5 * 2 ** attempt
                log(f"yf batch {i} attempt {attempt+1} error {e!r}; sleeping {wait}s")
                time.sleep(wait)
        else:
            d = pd.DataFrame()
        got = set(d.ticker.unique()) if len(d) else set()
        failed += [t for t in b if t not in got]
        frames.append(d)
        log(f"yf batch {i//batch+1}/{(len(tickers)-1)//batch+1}: {len(got)}/{len(b)} tickers, {len(d)} rows")
        time.sleep(1.5)
    # retry failures individually once (yahoo sometimes drops tickers in batches)
    still = []
    for t in failed:
        try:
            d = yf_batch([t], start, end)
        except Exception:  # noqa
            d = pd.DataFrame()
        if len(d):
            frames.append(d)
        else:
            still.append(t)
        time.sleep(0.5)
    # Stooq fallback
    stooq_got = []
    for t in still:
        try:
            d = stooq_one(t, start)
        except Exception:  # noqa
            d = pd.DataFrame()
        if len(d):
            d["source"] = "stooq"
            frames.append(d)
            stooq_got.append(t)
    no_data = [t for t in still if t not in stooq_got]
    allp = pd.concat([f for f in frames if len(f)], ignore_index=True)
    if "source" not in allp:
        allp["source"] = "yfinance"
    allp["source"] = allp["source"].fillna("yfinance")
    allp["date"] = pd.to_datetime(allp["date"]).dt.tz_localize(None)
    allp = allp.drop_duplicates(["date", "ticker"]).sort_values(["ticker", "date"])
    allp.to_parquet(out, index=False)
    record(m, out, "yfinance (auto_adjust=False); fallback stooq", rows=len(allp),
           tickers=list(allp.ticker.unique()),
           extra={"requested": len(tickers), "no_data": sorted(no_data), "stooq_fallback": sorted(stooq_got),
                  "first_date": str(allp.date.min().date()), "last_date": str(allp.date.max().date())})
    log(f"{out_name}: {allp.ticker.nunique()} tickers with data, {len(no_data)} no data, "
        f"{len(stooq_got)} via stooq; rows={len(allp)}")
    return allp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--only", choices=["wiki", "french", "bench", "stocks"], default=None)
    a = ap.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    m = load_manifest()
    m["last_run"] = dt.datetime.now().isoformat(timespec="seconds")
    if a.only in (None, "wiki", "stocks"):
        pool = get_wikipedia(m, a.force)
    if a.only in (None, "french"):
        get_french(m, a.force)
    if a.only in (None, "bench"):
        bm = CFG["benchmarks"]
        ticks = sorted(set(bm) | {v for v in bm.values() if v})
        get_prices(m, ticks, "benchmarks_prices.parquet", batch=10, force=a.force)
    if a.only in (None, "stocks"):
        get_prices(m, list(pool.ticker), "stock_prices.parquet", batch=50, force=a.force)
    save_manifest(m)
    with open(ROOT / "logs" / "download_run.log", "a") as f:
        f.write("\n".join(LOG) + "\n")


if __name__ == "__main__":
    sys.exit(main())
