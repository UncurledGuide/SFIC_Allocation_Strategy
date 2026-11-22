"""Shared helpers for driver scripts (not part of the frozen entrypoint)."""
from __future__ import annotations
import copy
from pathlib import Path
import yaml
from common import metrics
from common.run_logger import RunLogger
from strategy_2_vol_managed.src import entrypoint

SDIR = Path(__file__).resolve().parents[1]


def load_cfg(name):
    return yaml.safe_load((SDIR / "configs" / f"{name}.yaml").read_text())


def score(res, loader, start=None, end=None):
    dr = res["daily_returns"]
    r = dr.set_index("date")["net"]
    rf = loader.cash_rate()
    bench = loader.benchmarks().set_index("date")["SFIC_BENCH"]
    m = metrics.summary(r, rf, bench, loader.factors("daily"), dr, start=start, end=end)
    m["avg_exposure"] = float(dr.set_index("date").loc[start:end, "exposure"].mean())
    m["total_cost_drag"] = float(dr.set_index("date").loc[start:end, "cost"].sum())
    s = res["stats"]
    for k in ("avg_trades_per_rebalance", "n_rebalances", "stale_return_position_days", "n_delist_events",
              "cost_bps_per_side", "rounding", "starting_capital_usd"):
        m[k] = s.get(k)
    return m


def logged_run(variant, split, cfg, loader, purpose, hypothesis, key_params, start=None, end=None,
               outcome="", next_decision=""):
    with RunLogger(SDIR, variant=variant, split=split, cfg=cfg, purpose=purpose, hypothesis=hypothesis,
                   key_params=key_params) as run:
        res = entrypoint.run(copy.deepcopy(cfg), loader)
        m = score(res, loader, start, end)
        if "exposure_target" in res["stats"]:
            m["exposure_target"] = res["stats"]["exposure_target"]
        run.record(res, m)
        run.note(outcome=outcome or f"sharpe={m['sharpe']:.3f} mdd={m['max_drawdown']:.3f} vol={m['ann_vol']:.3f}",
                 next_decision=next_decision or "see logs/STATUS.md")
    return res, m
