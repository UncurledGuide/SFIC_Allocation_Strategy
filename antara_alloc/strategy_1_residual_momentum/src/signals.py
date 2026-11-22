"""Signals for strategy 1 (residual momentum) and the in-folder baseline (70/30 momentum + 52w-high).

Every function takes data already restricted by the loader and an `asof` signal date (a month-end
trading day t). Only data dated <= t is used; nothing is estimated on the full sample.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

FF3 = ["MKT_RF", "SMB", "HML"]


# --------------------------------------------------------------------------- monthly data
def monthly_returns(daily_ret: pd.DataFrame, min_days: int = 15) -> pd.DataFrame:
    """Compound daily close-to-close returns into calendar-month returns (index = Period[M]).
    A month needs >= min_days valid daily returns, else NaN (missing days inside a valid month = 0%)."""
    per = daily_ret.index.to_period("M")
    g = (1 + daily_ret.fillna(0.0)).groupby(per).prod() - 1
    cnt = daily_ret.notna().groupby(per).sum()
    return g.where(cnt >= min_days)


def monthly_factors(fac: pd.DataFrame) -> pd.DataFrame:
    """French monthly factors (month-end stamped) re-indexed by Period[M]."""
    f = fac.copy()
    f.index = pd.to_datetime(f["date"]).dt.to_period("M")
    return f[FF3 + ["RF"]].astype(float)


# --------------------------------------------------------------------------- residual momentum
def residual_momentum_scores(mret: pd.DataFrame, mfac: pd.DataFrame, asof, tickers,
                             reg_months: int = 36, mom_months: int = 11, skip_months: int = 1,
                             standardize: bool = True) -> tuple[pd.Series, dict]:
    """Blitz-Huij-Martens residual momentum at signal date `asof` (month-end close of month p).

    For each ticker with complete returns over the `reg_months` months ending at month p:
      excess_r = a + b'FF3 + e   (OLS, one regression per stock, window p-reg_months+1 .. p)
    score = sum(e over months p-skip-mom+1 .. p-skip) [/ std(e over the same months)].
    Default 12-1: months p-11 .. p-1 (11 months), the just-finished month p is skipped.
    If factors are not yet published for month p, the window ends at the last factor month
    (flagged in info['factor_lag_months']).
    """
    p = pd.Timestamp(asof).to_period("M")
    last_f = min(p, mfac.index.max())
    lag = (p - last_f).n
    months = pd.period_range(end=last_f, periods=reg_months, freq="M")
    info = {"factor_lag_months": lag, "n_candidates": len(tickers)}
    if not set(months) <= set(mfac.index):
        return pd.Series(dtype=float), {**info, "n_scored": 0, "error": "factor history too short"}
    F = mfac.loc[months]
    Y = mret.reindex(index=months, columns=list(tickers))
    Y = Y.loc[:, Y.notna().all()]
    info["n_scored"] = Y.shape[1]
    if Y.shape[1] == 0:
        return pd.Series(dtype=float), info
    y = Y.to_numpy() - F["RF"].to_numpy()[:, None]
    X = np.column_stack([np.ones(len(F)), F[FF3].to_numpy()])
    B, *_ = np.linalg.lstsq(X, y, rcond=None)
    E = y - X @ B
    # rows of the estimation window that form the momentum window (relative to the last factor month)
    end = reg_months - skip_months  # exclusive
    start = end - mom_months
    win = E[start:end]
    s = win.sum(axis=0)
    if standardize:
        sd = win.std(axis=0, ddof=1)
        s = np.where(sd > 0, s / sd, np.nan)
    return pd.Series(s, index=Y.columns).dropna(), info


# --------------------------------------------------------------------------- baseline 70/30
def baseline_scores(adj_close: pd.DataFrame, asof, tickers, mom_days: int = 126,
                    high_days: int = 252, min_high_obs: int = 200) -> pd.DataFrame:
    """6-month (126 trading day) price momentum and proximity to the 52-week (252-day) high,
    both from adjusted closes up to and including asof."""
    px = adj_close.loc[:pd.Timestamp(asof)].reindex(columns=list(tickers))
    win = px.tail(high_days + 1)
    last = win.iloc[-1]
    past = win.iloc[-1 - mom_days] if len(win) > mom_days else pd.Series(np.nan, index=px.columns)
    mom = last / past - 1
    hi = win.tail(high_days)
    prox = last / hi.max()
    prox = prox.where(hi.count() >= min_high_obs)
    return pd.DataFrame({"mom": mom, "high52": prox})


def pick_baseline(scores: pd.DataFrame, n: int, n_mom: int) -> list[str]:
    """n_mom names by 6-month momentum, the rest by 52w-high proximity among the remaining names."""
    mom = scores["mom"].dropna().sort_values(ascending=False, kind="mergesort")
    picks = list(mom.index[:n_mom])
    hi = scores["high52"].dropna().drop(picks, errors="ignore").sort_values(ascending=False, kind="mergesort")
    return picks + list(hi.index[: n - len(picks)])


def pick_top(scores: pd.Series, n: int, held: list[str] | None = None, buffer: int | None = None) -> list[str]:
    """Top-n by score. With a buffer, currently held names stay while ranked <= buffer."""
    ranked = list(scores.sort_values(ascending=False, kind="mergesort").index)
    if not buffer or not held:
        return ranked[:n]
    keep = [t for t in ranked[:buffer] if t in set(held)][:n]
    return keep + [t for t in ranked if t not in set(keep)][: n - len(keep)]
