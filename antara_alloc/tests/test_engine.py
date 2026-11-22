"""Backtest engine timing, costs, rounding and metrics on synthetic data."""
import numpy as np
import pandas as pd
import pytest

from common import metrics
from common.backtest_engine import rebalance_dates, run_backtest

days = pd.bdate_range("2010-01-01", "2010-04-30")


def _data():
    rng = np.random.default_rng(1)
    r = pd.DataFrame(rng.normal(0, 0.01, (len(days), 3)), index=days, columns=["A", "B", "C"])
    close = 100 * (1 + r).cumprod()
    rf = pd.Series(0.0001, index=days)
    return r, close, rf


def test_next_day_execution_and_costs():
    r, close, rf = _data()
    sig = days[days.month == 1][-1]
    t = pd.DataFrame({"A": [1.0]}, index=[sig])
    out = run_backtest(t, r, rf, close=close, cost_bps=10)
    dr = out["daily_returns"].set_index("date")
    trade_day = days[days > sig][0]
    # before and on trade date: all cash (old weights) -> gross == rf
    assert np.allclose(dr.loc[:trade_day, "gross"], 0.0001)
    assert dr.loc[trade_day, "turnover"] == pytest.approx(1.0)
    assert dr.loc[trade_day, "cost"] == pytest.approx(0.001)
    nxt = days[days > trade_day][0]
    assert dr.loc[nxt, "gross"] == pytest.approx(r.loc[nxt, "A"])
    assert out["trades"].date.iloc[0] == trade_day


def test_whole_share_rounding_leaves_cash():
    r, close, rf = _data()
    t = pd.DataFrame({"A": [0.5], "B": [0.5]}, index=[days[5]])
    out = run_backtest(t, r, rf, close=close, rounding="whole_share", allocation=0.0001)  # ~$154
    pos = out["positions"]
    assert (pos.shares == np.floor(pos.shares)).all()
    assert pos.weight.sum() < 1.0


def test_delisting_moves_to_cash():
    r, close, rf = _data()
    r.loc[days[30]:, "B"] = np.nan
    t = pd.DataFrame({"B": [1.0]}, index=[days[5]])
    out = run_backtest(t, r, rf, close=close)
    assert (out["trades"].reason == "delisted_to_cash").sum() == 1
    assert out["daily_returns"].exposure.iloc[-1] == 0


def test_rejects_leverage_and_shorts():
    r, close, rf = _data()
    with pytest.raises(ValueError):
        run_backtest(pd.DataFrame({"A": [0.7], "B": [0.7]}, index=[days[3]]), r, rf)
    with pytest.raises(ValueError):
        run_backtest(pd.DataFrame({"A": [-0.5]}, index=[days[3]]), r, rf)


def test_rebalance_dates():
    me = rebalance_dates(days)
    assert [d.month for d in me] == [1, 2, 3, 4]
    assert [d.month for d in rebalance_dates(days, every_n_months=2)] == [1, 3]


def test_metrics_basic():
    r = pd.Series([0.01, -0.02, 0.015, 0.0] * 100, index=pd.bdate_range("2010-01-01", periods=400))
    assert metrics.max_drawdown(r) < 0
    assert metrics.cagr(r) > 0
    ci = metrics.bootstrap_sharpe_ci(r, n_boot=200)
    assert ci["ci_low"] <= ci["sharpe"] <= ci["ci_high"]
    d = metrics.bootstrap_sharpe_diff_ci(r, r * 0.5 + 0.0001, n_boot=200)
    assert d["ci_low"] <= d["ci_high"]
