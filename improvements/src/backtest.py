"""Event-driven monthly backtest. Signal on close of day t -> trade at close of t+1 -> new weights earn from t+2.
Holdings drift between rebalances. Costs = bps * one-way traded notional, charged on the trade day."""
import datetime as dt
import hashlib, json
import numpy as np
import pandas as pd
from . import data as D

LOG = D.ROOT / "results" / "trials_log.csv"


def run_backtest(returns, sig_dates, target_fn, tbill, cost_bps=0.0, cash_ok=True):
    """returns: DataFrame of daily stock returns (NaN -> 0, i.e. position frozen after data ends).
    target_fn(d, prev_w) -> Series of target weights (sum<=1, remainder in T-bills).
    Returns (daily return Series, swaps Series indexed by trade date, weights DataFrame at trade dates)."""
    idx = returns.index
    pos = {d: idx.get_loc(d) for d in sig_dates}
    trade_at = {idx[p + 1]: d for d, p in pos.items() if p + 1 < len(idx)}
    w = pd.Series(dtype=float)  # stock weights (fraction of NAV); cash = 1 - sum
    out, swaps, wlog, tlog = {}, {}, {}, {}
    first_trade = min(trade_at)
    for day in idx[idx >= first_trade]:
        r = returns.loc[day].reindex(w.index).fillna(0.0)
        rf = tbill.get(day, 0.0)
        cash = 1 - w.sum()
        pr = float((w * r).sum() + cash * rf)
        nav_new = 1 + pr
        w = w * (1 + r) / nav_new
        cost = 0.0
        if day in trade_at:
            tgt = target_fn(trade_at[day], w)
            allt = w.index.union(tgt.index)
            old, new = w.reindex(allt).fillna(0), tgt.reindex(allt).fillna(0)
            turnover = float((new - old).abs().sum())
            sold = int(((old > 0) & (new == 0)).sum())
            cost = cost_bps / 1e4 * turnover
            swaps[day] = sold if len(w) else int((new > 0).sum())
            tlog[day] = turnover
            w = tgt[tgt > 0]
            wlog[day] = w.copy()
        out[day] = pr - cost
    ser = pd.Series(out)
    # the first trade day is the initial build: its return is ~0 (all cash) - drop it
    ser = ser.iloc[1:]
    sw, tl = pd.Series(swaps), pd.Series(tlog)
    # drop the initial portfolio build (15 'buys' from cash) from swap / turnover statistics
    return ser, sw.iloc[1:], tl.iloc[1:], wlog


def log_trial(tag, params, metrics, cost_bps):
    LOG.parent.mkdir(exist_ok=True)
    row = {"timestamp": dt.datetime.now().isoformat(timespec="seconds"), "tag": tag, "cost_bps": cost_bps,
           "params": json.dumps(params, sort_keys=True, default=str),
           "cfg_hash": hashlib.md5(json.dumps(D.CFG, sort_keys=True, default=str).encode()).hexdigest()[:8],
           **{k: round(v, 5) for k, v in metrics.items() if k in ("CAGR", "Vol", "Sharpe", "Sortino", "MaxDD", "avg_swaps", "max_swaps", "max_swaps_qtr")}}
    pd.DataFrame([row]).to_csv(LOG, mode="a", header=not LOG.exists(), index=False)
