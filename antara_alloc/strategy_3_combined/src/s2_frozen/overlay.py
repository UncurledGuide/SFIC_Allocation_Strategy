"""Moreira–Muir volatility-managed overlay on the baseline portfolio.

RV_t (annualised variance) at month-end t = population variance x 252 of the baseline's own daily
returns over the trading days in the `window_months` calendar months ending at t (inclusive of t).
Only returns dated <= t are used; the engine trades the resulting exposure at the close of t+1.
Exposure w_t = clip(c / RV_t, floor, cap); the remainder (1 - w_t) is cash at French RF.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def realized_variance(daily: pd.Series, signal_dates, window_months: int = 1) -> pd.Series:
    daily = daily.dropna()
    out = {}
    for t in signal_dates:
        t = pd.Timestamp(t)
        lo = (t.to_period("M") - (window_months - 1)).start_time
        x = daily.loc[lo:t]
        if len(x) >= 10 * window_months:
            out[t] = float(x.var(ddof=0) * 252)
    return pd.Series(out, dtype=float)


def exposure(rv: pd.Series, c: float, cap: float = 1.0, floor: float = 0.0) -> pd.Series:
    return (c / rv).clip(lower=floor, upper=cap)


def estimate_c(daily: pd.Series, rf: pd.Series, rv: pd.Series, method: str) -> float:
    """Fit-period only. daily: baseline daily returns; rv: RV at month-ends (signal dates).

    mm_vol_match: Moreira-Muir — c makes the UNCAPPED managed monthly excess return
                  (c / RV_{t-1}) * f_t have the same std as the unmanaged f_t.
    median_rv:    c = median fit-period RV (full exposure whenever RV <= its typical level).
    """
    if method == "median_rv":
        return float(rv.median())
    if method != "mm_vol_match":
        raise ValueError(method)
    ex = (daily - rf.reindex(daily.index).fillna(0.0)).dropna()
    f = (1 + ex).groupby(ex.index.to_period("M")).prod() - 1
    lag = pd.Series(rv.values, index=rv.index.to_period("M") + 1)   # RV known at end of previous month
    df = pd.concat([f.rename("f"), lag.rename("rv")], axis=1, join="inner").dropna()
    scaled = df.f / df.rv
    return float(df.f.std(ddof=1) / scaled.std(ddof=1))
