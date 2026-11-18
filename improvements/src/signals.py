"""Signals. Every value at row t uses data with date <= t only (verified in tests/test_no_lookahead.py)."""
import pandas as pd


def mom_lookback(adj_close, n):
    """Total return over the last n trading days: P_t / P_{t-n} - 1."""
    return adj_close / adj_close.shift(n) - 1


def mom_skip(adj_close, start, end):
    """Return from t-start to t-end trading days (e.g. 126 -> 21 = '6-1' momentum)."""
    return adj_close.shift(end) / adj_close.shift(start) - 1


def nearness_52w(adj_close, high_adj, window=252):
    """price / max(high over last `window` days, including today)."""
    return adj_close / high_adj.rolling(window, min_periods=window).max()


def compute_all(px, cfg):
    s = cfg["signals"]
    return {
        "mom180": mom_lookback(px["adj_close"], s["mom_lookback_baseline"]),
        "mom6_1": mom_skip(px["adj_close"], s["mom_6_1"]["start"], s["mom_6_1"]["end"]),
        "near52": nearness_52w(px["adj_close"], px["high"], s["high_window"]),
    }
