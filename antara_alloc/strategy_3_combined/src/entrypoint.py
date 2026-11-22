"""Strategy 3 entrypoint: frozen V1 residual momentum + frozen Moreira–Muir overlay. run(cfg, loader) -> dict.

Pipeline (PROJECT_SPEC §5; works unchanged with the training or the gated holdout loader):
  1. V1 target weights from the frozen Strategy 1 code (src/s1_frozen, configs/s1_frozen_config.yaml).
  2. Unmanaged V1 daily returns: fractional, 0 bps (the overlay's RV input, per the frozen overlay spec).
  3. RV_t at each V1 signal date t from those returns, 1-month window, only returns dated <= t
     (src/s2_frozen/overlay.realized_variance, unchanged).
  4. w_t = clip(c / RV_t, floor, cap) (overlay.exposure, unchanged); c is a FIXED number in cfg, estimated
     once on unmanaged V1's fit-period (2000-2014) returns with overlay.estimate_c (see estimate_fit_c).
  5. Managed targets = w_t x V1 targets (remainder cash at RF), traded by the common engine at t+1 close
     with cfg's cost/rounding/allocation.
The only signal date without an RV (fewer than 10 daily returns, i.e. the first one, 1999-12-31) keeps
w = 1; it lies in the warm-up/fit period and never affects validation or holdout scoring.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from .s1_frozen import entrypoint as v1
from .s2_frozen import overlay

HERE = Path(__file__).resolve().parent
CONFIGS = HERE.parent / "configs"
FIT_END = "2014-12-31"
FIT_START = "2000-01-01"


def frozen_v1_cfg() -> dict:
    return yaml.safe_load((CONFIGS / "s1_frozen_config.yaml").read_text())


def frozen_overlay_cfg() -> dict:
    return yaml.safe_load((CONFIGS / "s2_frozen_overlay.yaml").read_text())["overlay"]


def _check_frozen(cfg: dict) -> None:
    """Refuse to run anything but frozen V1 + the frozen overlay settings (only c may differ)."""
    if cfg["v1"] != frozen_v1_cfg():
        raise ValueError("cfg['v1'] differs from configs/s1_frozen_config.yaml")
    fo = frozen_overlay_cfg()
    for k in ("rv_window_months", "cap", "floor", "c_method", "enabled"):
        if cfg["overlay"].get(k) != fo[k]:
            raise ValueError(f"overlay.{k}={cfg['overlay'].get(k)!r} differs from frozen {fo[k]!r}")
    unknown = set(cfg) - {"v1", "overlay", "cost_bps", "rounding", "allocation"}
    if unknown:
        raise ValueError(f"unknown cfg keys: {sorted(unknown)}")


def unmanaged_v1(v1_cfg: dict, loader) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """(V1 targets, diagnostics, unmanaged fractional 0-bps backtest result)."""
    targets, diag = v1.build_targets(v1_cfg, loader)
    res = v1.backtest(targets, v1_cfg, loader, cost_bps=0.0, rounding="fractional", allocation=None)
    return targets, diag, res


def _daily(res: dict) -> pd.Series:
    return res["daily_returns"].set_index("date")["net"]


def overlay_rv(unmanaged_res: dict, signal_dates, window_months: int) -> pd.Series:
    return overlay.realized_variance(_daily(unmanaged_res), signal_dates, window_months)


def estimate_fit_c(loader, v1_cfg: dict | None = None, ov: dict | None = None) -> dict:
    """c from unmanaged V1 fit-period returns only. Call with TrainingLoader(max_date='2014-12-31')."""
    if pd.Timestamp(loader.max_date) > pd.Timestamp(FIT_END):
        raise ValueError("estimate_fit_c must use a fit-only loader (max_date <= 2014-12-31)")
    v1_cfg = v1_cfg or frozen_v1_cfg()
    ov = ov or frozen_overlay_cfg()
    targets, _, res = unmanaged_v1(v1_cfg, loader)
    daily = _daily(res).loc[FIT_START:FIT_END]
    rv = overlay_rv(res, targets.index, ov["rv_window_months"]).loc[:FIT_END]
    rf = loader.cash_rate()
    c = overlay.estimate_c(daily, rf, rv, ov["c_method"])
    return {"c": c, "rv": rv, "unmanaged": res, "targets": targets,
            "rv_median_fit": float(rv.median()), "n_rv_months_fit": int(len(rv))}


def managed_targets(targets: pd.DataFrame, rv: pd.Series, ov: dict) -> tuple[pd.DataFrame, pd.Series]:
    w = overlay.exposure(rv, ov["c"], ov["cap"], ov["floor"]).reindex(targets.index).fillna(1.0)
    return targets.mul(w, axis=0), w


def run(cfg: dict, loader) -> dict:
    _check_frozen(cfg)
    ov = cfg["overlay"]
    if not isinstance(ov.get("c"), (int, float)) or not ov["c"] > 0:
        raise ValueError("overlay.c must be the fixed fit-period estimate (positive number)")
    targets, diag, unm = unmanaged_v1(cfg["v1"], loader)
    rv = overlay_rv(unm, targets.index, ov["rv_window_months"])
    mt, w = managed_targets(targets, rv, ov)
    res = v1.backtest(mt, cfg["v1"], loader, cost_bps=cfg.get("cost_bps"),
                      rounding=cfg.get("rounding", "fractional"), allocation=cfg.get("allocation"))
    res["stats"]["c"] = float(ov["c"])
    res["stats"]["signals_without_rv"] = int(rv.reindex(targets.index).isna().sum())
    res["targets"] = mt
    res["v1_targets"] = targets
    res["diagnostics"] = diag
    res["overlay"] = pd.DataFrame({"rv": rv.reindex(targets.index), "w": w})
    res["unmanaged_v1_0bps"] = unm["daily_returns"]
    return res
