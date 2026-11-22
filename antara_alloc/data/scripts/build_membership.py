"""Point-in-time S&P 500 membership, reconstructed backwards from the current constituent list
through Wikipedia's additions/removals table (data/raw/sp500_changes.csv).

Output: data/membership/sp500_membership.csv with one row per membership spell:
    ticker, start, end   (member on dates d with start <= d < end; end empty = still a member)
Tickers normalised like download.py ('.' -> '-').
Caveat: the changes table is sparse before ~2008 (few events/year vs ~20-40 actual), so early
membership is close to "current list" and still contains survivors. See logs/data_log.md.
Run: .venv/bin/python data/scripts/build_membership.py
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "membership"
EPOCH = pd.Timestamp("1900-01-01")


def norm(t):
    if pd.isna(t) or not str(t).strip():
        return None
    return str(t).strip().upper().replace(".", "-")


def build() -> pd.DataFrame:
    ch = pd.read_csv(RAW / "sp500_changes.csv")
    ch["d"] = pd.to_datetime(ch["Effective Date"])
    ch["A"], ch["R"] = ch.Added_Ticker.map(norm), ch.Removed_Ticker.map(norm)
    pool = pd.read_csv(RAW / "candidate_pool.csv")
    current = set(pool.loc[pool.origin == "current", "ticker"])
    open_since: dict[str, pd.Timestamp | None] = {t: None for t in current}  # start unknown yet
    end_of: dict[str, pd.Timestamp | None] = {t: None for t in current}      # still a member
    spells = []
    for d, g in ch.sort_values("d", ascending=False).groupby("d", sort=False):
        for _, r in g.iterrows():
            if r.A and r.A in end_of:            # before d, A was not a member: close spell [d, end)
                spells.append((r.A, d, end_of.pop(r.A)))
            if r.R and r.R not in end_of:        # before d, R was a member until d
                end_of[r.R] = d
    for t, e in end_of.items():                  # members before the first recorded event
        spells.append((t, EPOCH, e))
    df = pd.DataFrame(spells, columns=["ticker", "start", "end"]).sort_values(["ticker", "start"])
    return df.reset_index(drop=True)


def members_on(df: pd.DataFrame, date) -> set[str]:
    d = pd.Timestamp(date)
    m = (df.start <= d) & (df.end.isna() | (df.end > d))
    return set(df.loc[m, "ticker"])


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    df = build()
    df.to_csv(OUT / "sp500_membership.csv", index=False, date_format="%Y-%m-%d")
    m = json.loads((RAW / "manifest.json").read_text())["files"]["stock_prices.parquet"]
    nodata = set(m["no_data"])
    lines = [f"\n## Point-in-time S&P 500 membership ({dt.datetime.now().isoformat(timespec='seconds')})",
             f"- {len(df)} membership spells, {df.ticker.nunique()} tickers -> data/membership/sp500_membership.csv",
             "- Universe(asof) = top 500 by dollar volume among stocks that were S&P 500 members on asof.",
             "| date | members (reconstructed) | members without Yahoo data |", "|---|---|---|"]
    for y in (2000, 2005, 2008, 2010, 2015, 2019):
        s = members_on(df, f"{y}-12-31" if y != 2000 else "2000-01-03")
        lines.append(f"| {y} | {len(s)} | {len(s & nodata)} |")
    lines.append("- Changes table is sparse before ~2008 (1-11 events/yr vs ~20-40 actual): fit-period (2000-2007) "
                 "membership still contains future members/survivors; validation (2015-19) and holdout use a "
                 "near-complete event list.")
    with open(ROOT / "logs" / "data_log.md", "a") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
