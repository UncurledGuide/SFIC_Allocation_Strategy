"""Point-in-time universe: top-N S&P 500 members on asof by trailing average dollar volume.

Uses only rows with date <= asof. No strategy logic.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]


def universe_config() -> dict:
    return yaml.safe_load((ROOT / "config" / "universe.yaml").read_text())


def load_membership() -> pd.DataFrame | None:
    """Point-in-time S&P 500 membership spells (ticker, start, end); None if not configured."""
    f = universe_config().get("membership_file")
    if not f:
        return None
    return pd.read_csv(ROOT / f, parse_dates=["start", "end"])


def members_on(membership: pd.DataFrame, asof) -> set[str]:
    """Tickers that were S&P 500 members on asof (start <= asof < end)."""
    d = pd.Timestamp(asof)
    m = (membership.start <= d) & (membership.end.isna() | (membership.end > d))
    return set(membership.loc[m, "ticker"])


def top_by_dollar_volume(dollar_volume: pd.DataFrame, adj_close: pd.DataFrame, asof,
                         n: int | None = None, lookback: int | None = None,
                         min_obs: int | None = None, members: set[str] | None = None) -> list[str]:
    """dollar_volume / adj_close: wide frames (index=trading dates, columns=tickers).

    Rank by mean raw Close*Volume over the last `lookback` trading days ending at asof (inclusive).
    A ticker needs >= min_obs valid observations in the window and a price on the last
    trading day <= asof. If `members` is given, only those tickers (S&P 500 members on asof) are
    eligible. Returns tickers sorted by rank (highest dollar volume first).
    """
    cfg = universe_config()
    n = n or cfg["size"]
    lookback = lookback or cfg["lookback_days"]
    min_obs = min_obs or cfg["min_obs_in_lookback"]
    asof = pd.Timestamp(asof)
    dv = dollar_volume.loc[:asof]
    if dv.empty:
        return []
    win = dv.tail(lookback)
    valid = win.where(win > 0)
    cnt = valid.count()
    avg = valid.mean()
    last_px = adj_close.loc[:asof].iloc[-1] if cfg.get("require_price_on_asof", True) else None
    ok = cnt >= min_obs
    if last_px is not None:
        ok &= last_px.reindex(avg.index).notna()
    excl = set(cfg.get("exclude", []))
    if members is not None:
        ok &= avg.index.isin(list(members))
    avg = avg[ok & ~avg.index.isin(excl)].sort_values(ascending=False, kind="mergesort")
    return list(avg.index[:n])
