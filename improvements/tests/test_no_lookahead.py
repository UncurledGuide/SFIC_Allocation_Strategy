"""Signals at date t must be unchanged if all data after t is deleted (and garbage is injected)."""
import sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import signals

CFG = {"signals": {"mom_lookback_baseline": 180, "high_window": 252, "mom_6_1": {"start": 126, "end": 21}}}


def _px(n=700, k=8, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2015-01-01", periods=n)
    adj = pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(0, .02, (n, k)), 0)), index=idx, columns=list("ABCDEFGH"))
    return {"adj_close": adj, "high": adj * 1.01}


def test_signals_use_no_future_data():
    px = _px()
    full = signals.compute_all(px, CFG)
    for cut in (300, 450, 600):
        d = px["adj_close"].index[cut]
        trunc = {k: v.loc[:d] for k, v in px.items()}
        part = signals.compute_all(trunc, CFG)
        # also poison the future: results at d must still be identical
        poisoned = {k: v.copy() for k, v in px.items()}
        for v in poisoned.values():
            v.iloc[cut + 1:] = 1e9
        pois = signals.compute_all(poisoned, CFG)
        for name in full:
            pd.testing.assert_series_equal(full[name].loc[d], part[name].loc[d])
            pd.testing.assert_series_equal(full[name].loc[d], pois[name].loc[d])


def test_trade_executes_after_signal():
    from src.backtest import run_backtest
    idx = pd.bdate_range("2020-01-01", periods=60)
    rets = pd.DataFrame({"A": 0.0, "B": 0.0}, index=idx)
    rets.loc[idx[11], "A"] = 0.5   # day t+1 return: must NOT be earned by a position set on signal day t=10
    rets.loc[idx[12], "A"] = 0.1   # day t+2 return: earned
    tb = pd.Series(0.0, index=idx)
    out, sw, _, _ = run_backtest(rets, [idx[10]], lambda d, w: pd.Series({"A": 1.0}), tb)
    assert abs(out.get(idx[11], 0.0)) < 1e-12 or idx[11] not in out.index
    assert abs(out.loc[idx[12]] - 0.1) < 1e-9
