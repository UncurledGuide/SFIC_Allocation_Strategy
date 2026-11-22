"""Neutral backtest engine: target weights at signal dates -> daily returns, positions, trades.

Timing contract (see docs/PROJECT_SPEC.md §3):
  * A target dated t (normally the last trading day of a month) may use data through the close of t.
  * Trades fill at the CLOSE of the first trading day strictly after t ("trade date").
    The trade date's own return is earned by the OLD weights; new weights earn from the next day.
  * Costs: cost_bps per side on traded notional (sum |delta w|), charged on the trade date.
  * Uninvested weight earns the daily cash rate (French RF).
  * A held stock with a missing return on a day is treated as 0% for that day (stale) and counted.
    After a stock's last available price it is moved to cash at its last price (logged, no cost).
  * Rounding: 'fractional' (exact weights) or 'whole_share' (floor(target $ / raw close) shares,
    capital = portfolio_value * allocation; remainder stays in cash).
No strategy logic lives here.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from common import costs as _costs


def rebalance_dates(trading_days: pd.DatetimeIndex, start=None, end=None, every_n_months: int = 1) -> list:
    """Last trading day of each month in [start, end], keeping every n-th month (anchored at first)."""
    td = pd.DatetimeIndex(trading_days)
    s = pd.Series(td, index=td)
    if start is not None:
        s = s.loc[pd.Timestamp(start):]
    if end is not None:
        s = s.loc[:pd.Timestamp(end)]
    me = s.groupby(s.index.to_period("M")).max()
    return list(me.iloc[::every_n_months])


def run_backtest(targets: pd.DataFrame, returns: pd.DataFrame, cash_rate: pd.Series,
                 close: pd.DataFrame | None = None, cost_bps: float | None = None,
                 rounding: str = "fractional", allocation: float | None = None,
                 start=None, end=None) -> dict:
    """targets: index = signal dates, columns = tickers, values = weights (>=0, row sum <= 1;
    remainder is cash). returns: wide daily simple returns (loader.returns()).
    close: wide RAW close (loader.prices(field='close')), required for whole_share rounding.
    Returns dict with DataFrames daily_returns, positions, trades and dict stats.
    """
    if rounding not in ("fractional", "whole_share"):
        raise ValueError("rounding must be 'fractional' or 'whole_share'")
    bps = _costs.base_bps() if cost_bps is None else float(cost_bps)
    cap0 = _costs.capital(allocation)
    targets = targets.fillna(0.0).sort_index()
    if (targets.values < -1e-12).any():
        raise ValueError("long-only engine: negative target weight")
    if (targets.sum(axis=1) > 1 + 1e-9).any():
        raise ValueError("target weights sum > 1 (no leverage)")
    cols = list(targets.columns[(targets != 0).any()])
    days = returns.index
    if start is not None:
        days = days[days >= pd.Timestamp(start)]
    if end is not None:
        days = days[days <= pd.Timestamp(end)]
    R = returns.reindex(index=days, columns=cols).to_numpy(dtype=float)
    rf = cash_rate.reindex(days).fillna(0.0).to_numpy(dtype=float)
    if rounding == "whole_share":
        if close is None:
            raise ValueError("whole_share rounding needs raw close prices")
        C = close.reindex(index=days, columns=cols).to_numpy(dtype=float)
    else:
        C = close.reindex(index=days, columns=cols).to_numpy(dtype=float) if close is not None else None
    # last date with a valid return/price per ticker (for delisting)
    has = ~np.isnan(R)
    last_valid = np.full(len(cols), -1)
    for j in range(len(cols)):
        idx = np.flatnonzero(has[:, j])
        if len(idx):
            last_valid[j] = idx[-1]

    # map signal dates -> trade day index (first trading day strictly after signal date)
    trade_map: dict[int, np.ndarray] = {}
    sig_of: dict[int, pd.Timestamp] = {}
    for sd, row in targets.iterrows():
        k = int(days.searchsorted(pd.Timestamp(sd), side="right"))
        if 0 <= k < len(days) and (start is None or pd.Timestamp(sd) >= days[0] - pd.Timedelta(days=40)):
            trade_map[k] = row.reindex(cols).to_numpy(dtype=float)
            sig_of[k] = pd.Timestamp(sd)

    w = np.zeros(len(cols))
    nav = cap0
    rows, pos_rows, trade_rows = [], [], []
    stale_count = 0
    for i, d in enumerate(days):
        # delisting: position past last valid data -> cash at last price
        gone = (w > 0) & (last_valid < i)
        if gone.any():
            for j in np.flatnonzero(gone):
                trade_rows.append((d, cols[j], "sell", w[j], 0.0, -w[j], -w[j] * nav, np.nan, "delisted_to_cash"))
            w[gone] = 0.0
        r = R[i]
        held_nan = (w > 0) & np.isnan(r)
        stale_count += int(held_nan.sum())
        r = np.nan_to_num(r, nan=0.0)
        wc = 1.0 - w.sum()
        pr = float(w @ r + wc * rf[i])
        nav_pre = nav * (1 + pr)
        w = w * (1 + r) / (1 + pr) if (1 + pr) != 0 else w
        turnover, cost = 0.0, 0.0
        if i in trade_map:
            tw = trade_map[i].copy()
            px = C[i] if C is not None else None
            if px is not None:
                untradeable = (tw > 0) & np.isnan(px)
            else:
                untradeable = (tw > 0) & (last_valid < i)
            tw[untradeable] = 0.0
            shares = np.full(len(cols), np.nan)
            if rounding == "whole_share":
                sh = np.where(tw > 0, np.floor(tw * nav_pre / np.where(np.isnan(px), np.inf, px)), 0.0)
                tw = sh * np.nan_to_num(px) / nav_pre
                shares = sh
            elif px is not None:
                shares = np.where(tw > 0, tw * nav_pre / px, 0.0)
            delta = tw - w
            turnover = float(np.abs(delta).sum())
            cost = turnover * bps / 1e4
            for j in np.flatnonzero(np.abs(delta) > 1e-10):
                dsh = delta[j] * nav_pre / px[j] if px is not None and not np.isnan(px[j]) else np.nan
                trade_rows.append((d, cols[j], "buy" if delta[j] > 0 else "sell", w[j], tw[j], delta[j],
                                   delta[j] * nav_pre, dsh, "rebalance"))
            for j in np.flatnonzero(tw > 0):
                pos_rows.append((d, sig_of[i], cols[j], tw[j], shares[j],
                                 px[j] if px is not None else np.nan, tw[j] * nav_pre))
            w = tw
        nav = nav_pre * (1 - cost)
        net = (1 + pr) * (1 - cost) - 1
        rows.append((d, pr, net, float(w.sum()), turnover, cost, nav))

    dr = pd.DataFrame(rows, columns=["date", "gross", "net", "exposure", "turnover", "cost", "nav"])
    positions = pd.DataFrame(pos_rows, columns=["date", "signal_date", "ticker", "weight", "shares", "price", "value_usd"])
    trades = pd.DataFrame(trade_rows, columns=["date", "ticker", "side", "weight_before", "weight_after",
                                               "delta_weight", "notional_usd", "shares", "reason"])
    reb = trades[trades.reason == "rebalance"]
    n_reb = int(dr.turnover.gt(0).sum())
    years = max(len(dr) / 252.0, 1e-9)
    stats = {
        "n_rebalances": len(trade_map),
        "n_rebalances_with_trades": n_reb,
        "avg_trades_per_rebalance": float(reb.groupby("date").size().mean()) if len(reb) else 0.0,
        "avg_one_way_turnover_per_rebalance": float(dr.loc[dr.turnover > 0, "turnover"].mean() / 2) if n_reb else 0.0,
        "annual_one_way_turnover": float(dr.turnover.sum() / 2 / years),
        "total_cost_drag": float(dr.cost.sum()),
        "stale_return_position_days": stale_count,
        "n_delist_events": int((trades.reason == "delisted_to_cash").sum()),
        "cost_bps_per_side": bps,
        "rounding": rounding,
        "starting_capital_usd": cap0,
        "avg_exposure": float(dr.exposure.mean()),
    }
    return {"daily_returns": dr, "positions": positions, "trades": trades, "stats": stats}


def equity_curve(daily_returns: pd.DataFrame, col: str = "net") -> pd.Series:
    s = daily_returns.set_index("date")[col]
    return (1 + s).cumprod()
