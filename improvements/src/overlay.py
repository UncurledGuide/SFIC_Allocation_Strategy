"""Layer 4: volatility-targeting overlay.
exposure w = min(1, sigma_target / sigma_hat)
  sigma_target : benchmark realised vol on 2002-2014 ONLY (a single constant, never updated)
  sigma_hat    : trailing 126-day realised vol (annualised) of the UNLEVERED strategy's own daily returns, through the signal date
Updated only on rebalance (signal) dates, and only if the new w differs from the current w by more than `min_change`.
The 1 - w remainder sits in T-bills. Until 126 days of strategy history exist, w = 1."""
import numpy as np
import pandas as pd

TD = 252


def target_vol(bench, calib_end):
    return float(bench.loc[:calib_end].std() * np.sqrt(TD))


def exposure_schedule(unlevered, signal_dates, sigma_target, window=126, min_change=0.10):
    """Returns Series(date -> w) for each signal date, using only unlevered returns up to and including that date."""
    w, out = 1.0, {}
    for d in signal_dates:
        hist = unlevered.loc[:d]
        if len(hist) >= window:
            sigma_hat = float(hist.iloc[-window:].std() * np.sqrt(TD))
            raw = min(1.0, sigma_target / sigma_hat) if sigma_hat > 0 else 1.0
            if abs(raw - w) > min_change:
                w = raw
        out[d] = w
    return pd.Series(out)


def crash_schedule(unlevered, bench, signal_dates, calib_end, vol_window=126, bench_days=504, low=0.5):
    """Idea 3 (alternative to L4): exposure = `low` when the benchmark's trailing 24-month (504-day) return is negative AND the
    unlevered strategy's trailing 126-day vol exceeds its own 2002-2014 median (one constant); otherwise 1. Rest in T-bills.
    Evaluated on signal dates only, with data through that date; w = 1 until both histories exist."""
    vol = unlevered.rolling(vol_window).std() * np.sqrt(TD)
    med = float(vol.loc[:calib_end].median())
    out = {}
    for d in signal_dates:
        w = 1.0
        b = bench.loc[:d]
        if len(b) >= bench_days and pd.notna(vol.loc[:d].iloc[-1]):
            if float((1 + b.iloc[-bench_days:]).prod() - 1) < 0 and float(vol.loc[:d].iloc[-1]) > med:
                w = low
        out[d] = w
    return pd.Series(out), med
