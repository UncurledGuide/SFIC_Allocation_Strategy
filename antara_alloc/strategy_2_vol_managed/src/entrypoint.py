"""Strategy 2 entrypoint: run(cfg, loader) -> dict (PROJECT_SPEC §5).

cfg["overlay"]["enabled"] = False  -> the rebuilt SFIC baseline alone (comparison runs).
cfg["overlay"]["enabled"] = True   -> baseline scaled by w_t = clip(c / RV_t, floor, cap), rest cash.
c is a fixed number in cfg (estimated on fit 2000-2014 only, see scripts/fit_c.py).
Works unchanged with any loader: scoring starts at loader.perf_start if set, else cfg["start"];
it ends at loader.max_date.
"""
from __future__ import annotations

import pandas as pd

from common.backtest_engine import rebalance_dates, run_backtest

from .baseline import baseline_targets
from .overlay import exposure, realized_variance


def _start(cfg, loader) -> pd.Timestamp:
    ps = getattr(loader, "perf_start", None)
    return pd.Timestamp(ps) if ps is not None else pd.Timestamp(cfg["start"])


def signal_baseline_returns(loader, targets: pd.DataFrame, end) -> pd.Series:
    """Daily returns of the UNSCALED baseline (fractional, 0 bps): the input to RV.
    Deterministic and independent of the run's rounding/cost settings."""
    rets = loader.returns(end=end)
    res = run_backtest(targets, rets, loader.cash_rate(), cost_bps=0.0, rounding="fractional",
                       start=targets.index[0], end=end)
    return res["daily_returns"].set_index("date")["gross"]


def run(cfg: dict, loader) -> dict:
    start = _start(cfg, loader)
    end = pd.Timestamp(cfg.get("end") or loader.max_date)
    td = loader.trading_days()
    ov = cfg.get("overlay", {}) or {}
    every = int(cfg["baseline"].get("every_n_months", 1))
    # signals from 13 months before scoring start (RV warm-up); engine ignores signals well before start
    sig_start = (start - pd.DateOffset(months=13))
    sdates = [d for d in rebalance_dates(td, sig_start, end, every_n_months=every)]
    if every > 1:  # anchor 2-monthly schedule so a signal falls on the month-end just before start
        pre = [d for d in rebalance_dates(td, sig_start, end) if d < start][-1]
        sdates = [d for d in rebalance_dates(td, sig_start, end) if ((d.to_period("M") - pre.to_period("M")).n % every) == 0]
    targets = baseline_targets(loader, sdates, cfg)
    stats_extra = {}
    if ov.get("enabled"):
        base_daily = signal_baseline_returns(loader, targets, end)
        rv = realized_variance(base_daily, targets.index, int(ov["rv_window_months"]))
        w = exposure(rv, float(ov["c"]), float(ov.get("cap", 1.0)), float(ov.get("floor", 0.0)))
        w = w.reindex(targets.index)
        targets = targets.loc[w.notna()].mul(w.dropna(), axis=0)
        stats_extra["exposure_target"] = {str(k.date()): float(v) for k, v in w.dropna().items()}
        stats_extra["rv"] = {str(k.date()): float(v) for k, v in rv.items()}
    rets = loader.returns(end=end)
    close = loader.prices(end=end, field="close")
    res = run_backtest(targets, rets, loader.cash_rate(), close=close, cost_bps=cfg.get("cost_bps"),
                       rounding=cfg.get("rounding", "fractional"), allocation=cfg.get("allocation"),
                       start=start, end=end)
    res["stats"].update(stats_extra)
    return res
