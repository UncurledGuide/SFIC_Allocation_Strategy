"""Rebuilt SFIC baseline: 15 stocks EW, long-only.

At signal date t (month-end close), using only data <= t:
  * universe = loader.universe(t)
  * momentum  = adj_close[t] / adj_close[t - mom_days] - 1           (126 trading days, no skip month)
  * proximity = adj_close[t] / max(adj_close over last high_days)     (252 trading days incl. t)
  * eligible: price at t and at t - mom_days, >= min_high_obs valid prices in the 252-day window
  * pick n_mom names by momentum (desc), then fill to n_stocks by proximity (desc, tie-break momentum)
    from names not already picked. Equal weight.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def baseline_targets(loader, signal_dates, cfg: dict) -> pd.DataFrame:
    b = cfg["baseline"]
    n, n_mom = int(b["n_stocks"]), int(b["n_mom"])
    mom_days, high_days, min_obs = int(b["mom_days"]), int(b["high_days"]), int(b["min_high_obs"])
    last = pd.Timestamp(signal_dates[-1])
    px = loader.prices(end=last, field="adj_close")
    td = px.index
    rows = {}
    for sd in signal_dates:
        sd = pd.Timestamp(sd)
        i = int(td.searchsorted(sd, side="right")) - 1
        if i < high_days:
            continue
        uni = loader.universe(sd)
        win = px.iloc[i - high_days + 1: i + 1].reindex(columns=uni)
        p_t = win.iloc[-1]
        p_lag = px.iloc[i - mom_days].reindex(uni)
        mom = p_t / p_lag - 1
        prox = p_t / win.max()
        ok = p_t.notna() & p_lag.notna() & (win.notna().sum() >= min_obs) & np.isfinite(mom)
        df = pd.DataFrame({"mom": mom, "prox": prox})[ok]
        if len(df) < n:
            continue
        pick_m = list(df.sort_values("mom", ascending=False, kind="mergesort").index[:n_mom])
        rest = df.drop(index=pick_m).sort_values(["prox", "mom"], ascending=False, kind="mergesort")
        picks = pick_m + list(rest.index[: n - n_mom])
        rows[sd] = pd.Series(1.0 / n, index=picks)
    return pd.DataFrame(rows).T.fillna(0.0).sort_index()
