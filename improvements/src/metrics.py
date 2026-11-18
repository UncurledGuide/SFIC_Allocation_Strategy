import numpy as np
import pandas as pd

TD = 252


def max_drawdown(r):
    eq = (1 + r).cumprod()
    return float((eq / eq.cummax() - 1).min())


def swaps_stats(swaps):
    """swaps: Series indexed by trade date (initial portfolio build already excluded by the backtest)."""
    s = swaps
    q = s.groupby([s.index.year, s.index.quarter]).sum()
    return {"avg_swaps": float(s.mean()), "max_swaps": float(s.max()), "max_swaps_qtr": float(q.max()),
            "avg_swaps_qtr": float(q.mean())}


def perf(r, rf, bench, swaps=None):
    """r, rf, bench: daily return Series. Sharpe/Sortino on excess-over-T-bill returns."""
    idx = r.index.intersection(bench.index)
    r, b, rf = r.loc[idx], bench.loc[idx], rf.reindex(idx).fillna(0.0)
    ex = r - rf
    yrs = len(r) / TD
    cagr = float((1 + r).prod() ** (1 / yrs) - 1)
    vol = float(r.std() * np.sqrt(TD))
    sharpe = float(ex.mean() / ex.std() * np.sqrt(TD))
    dd = np.sqrt((np.minimum(ex, 0) ** 2).mean()) * np.sqrt(TD)
    sortino = float(ex.mean() * TD / dd)
    mdd = max_drawdown(r)
    out = {"CAGR": cagr, "Vol": vol, "Sharpe": sharpe, "Sortino": sortino, "MaxDD": mdd,
           "Calmar": cagr / abs(mdd) if mdd < 0 else np.nan,
           "Beta": float(np.cov(r, b)[0, 1] / b.var()), "Corr": float(np.corrcoef(r, b)[0, 1])}
    if swaps is not None:
        sw = swaps.loc[(swaps.index >= idx[0]) & (swaps.index <= idx[-1])]
        out.update(swaps_stats(sw))
    return out
