"""Strategy 1 entrypoint: run(cfg, loader) -> dict (PROJECT_SPEC §5).

cfg["model"]:
  "residual_momentum"  rolling FF3 regressions on monthly returns, 12-1 residual momentum (optionally
                       scaled by residual vol), top-n equal weight, long-only, monthly.
  "baseline_70_30"     SFIC baseline: n_mom names by 6-month momentum + rest by 52-week-high proximity,
                       equal weight; rebalanced every `every_n_months`.
Works unchanged with the training or the gated holdout loader (uses loader.max_date / trading_days only).
"""
from __future__ import annotations

import pandas as pd

from common.backtest_engine import rebalance_dates, run_backtest

from . import signals

DEFAULTS = {
    "model": "residual_momentum",
    "start": "1999-12-31",        # first signal date (fit scoring starts 2000-01)
    "n_holdings": 15,
    "every_n_months": 1,
    "reg_months": 36,
    "mom_months": 11,
    "skip_months": 1,
    "standardize": True,
    "buffer": None,               # e.g. 30: keep held names while rank <= buffer
    "n_mom": 11,                  # baseline: 11 of 15 (~70%) from momentum, 4 from 52w-high
    "mom_days": 126,
    "high_days": 252,
    "cost_bps": None,             # None -> config/costs.yaml base case (10 bps)
    "rounding": "fractional",
    "allocation": None,           # None -> config/costs.yaml primary (1%)
}


def _cfg(cfg: dict) -> dict:
    out = {**DEFAULTS, **(cfg or {})}
    unknown = set(cfg or {}) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"unknown cfg keys: {sorted(unknown)}")
    return out


def build_targets(cfg: dict, loader) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Target weights (index = signal dates) and a per-date diagnostics frame."""
    c = _cfg(cfg)
    td = loader.trading_days()
    dates = rebalance_dates(td, c["start"], loader.max_date, every_n_months=c["every_n_months"])
    rows, diag, held = {}, [], []
    if c["model"] == "residual_momentum":
        mret = signals.monthly_returns(loader.returns())
        mfac = signals.monthly_factors(loader.factors("monthly"))
        for d in dates:
            u = loader.universe(d)
            sc, info = signals.residual_momentum_scores(
                mret, mfac, d, u, c["reg_months"], c["mom_months"], c["skip_months"], c["standardize"])
            picks = signals.pick_top(sc, c["n_holdings"], held, c["buffer"]) if len(sc) else []
            diag.append({"signal_date": d, "universe": len(u), **info, "n_picks": len(picks)})
            rows[d] = pd.Series(1.0 / len(picks), index=picks) if picks else pd.Series(dtype=float)
            held = picks
    elif c["model"] == "baseline_70_30":
        px = loader.prices(field="adj_close")
        for d in dates:
            u = loader.universe(d)
            sc = signals.baseline_scores(px, d, u, c["mom_days"], c["high_days"])
            picks = signals.pick_baseline(sc, c["n_holdings"], c["n_mom"])
            diag.append({"signal_date": d, "universe": len(u), "n_scored": int(sc["mom"].notna().sum()),
                         "n_picks": len(picks)})
            rows[d] = pd.Series(1.0 / len(picks), index=picks) if picks else pd.Series(dtype=float)
    else:
        raise ValueError(f"unknown model {c['model']!r}")
    targets = pd.DataFrame(rows).T.fillna(0.0)
    targets = targets.reindex(pd.DatetimeIndex(dates)).fillna(0.0)
    return targets, pd.DataFrame(diag)


def backtest(targets: pd.DataFrame, cfg: dict, loader, **overrides) -> dict:
    c = {**_cfg(cfg), **overrides}
    return run_backtest(targets, loader.returns(), loader.cash_rate(), close=loader.prices(field="close"),
                        cost_bps=c["cost_bps"], rounding=c["rounding"], allocation=c["allocation"],
                        start=c["start"])


def run(cfg: dict, loader) -> dict:
    targets, diag = build_targets(cfg, loader)
    res = backtest(targets, cfg, loader)
    res["stats"]["min_names_scored"] = int(diag["n_scored"].min()) if len(diag) else 0
    if "factor_lag_months" in diag:
        res["stats"]["signals_with_factor_lag"] = int((diag["factor_lag_months"] > 0).sum())
    res["targets"] = targets
    res["diagnostics"] = diag
    return res
