"""Point-in-time universe: top-N by trailing average dollar (or share) volume, using data up to date t only."""
import numpy as np
import pandas as pd


def rebalance_dates(index, start, every=21):
    """Signal dates: every `every` trading days starting at first trading day >= start."""
    idx = index[index >= pd.Timestamp(start)]
    return idx[::every]


def build_universe(close, volume, dates, size=500, window=63, min_history=252, volume_type="dollar"):
    """Returns dict {date: list of tickers}. `close` should be split-adjusted raw close for dollar volume.
    Eligibility on date t: >= min_history non-NaN closes up to t, full ADV window, and top `size` by ADV."""
    turn = close * volume if volume_type == "dollar" else volume
    adv = turn.rolling(window, min_periods=window).mean()
    hist = close.notna().cumsum()
    uni = {}
    for d in dates:
        a = adv.loc[d]
        ok = a.notna() & (hist.loc[d] >= min_history) & close.loc[d].notna()
        uni[d] = list(a[ok].nlargest(size).index)
    return uni


def coverage_report(requested, prices_close, universe, hist_members=None):
    got = set(prices_close.columns)
    req = set(requested)
    ever = {t for u in universe.values() for t in u}
    lines = {
        "tickers_requested": len(req),
        "tickers_with_data": len(req & got),
        "tickers_missing (delisted/unavailable)": len(req - got),
        "coverage_pct": round(100 * len(req & got) / len(req), 1),
        "tickers_ever_in_universe": len(ever),
    }
    return lines
