"""Single validation run of the pre-registered primary spec (2015-01-01..2019-12-31).

Run from the repo root:  .venv/bin/python -m strategy_3_combined.scripts.validate_pit
Also computes (inside the same run, not design variants): 0/5/25 bps cost sensitivity, the unmanaged V1
reference (same targets, 10 bps), the SFIC benchmark, and paired block-bootstrap Sharpe-difference CIs.
Writes outputs/frozen/{daily_returns,positions,trades}.csv, metrics.json, config.yaml.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

from common import metrics
from common.data_access import TrainingLoader
from common.run_logger import RunLogger, count_variants
from strategy_3_combined.src import entrypoint as ep

SDIR = Path(__file__).resolve().parents[1]
VS, VE = "2015-01-01", "2019-12-31"


def _win(res):
    return res["daily_returns"].set_index("date").loc[VS:VE]


def _core(res, rf):
    d = _win(res)
    r = d["net"]
    reb = res["trades"][(res["trades"].reason == "rebalance")]
    reb = reb[(reb.date >= VS) & (reb.date <= VE)]
    years = len(d) / 252
    return {"sharpe": metrics.sharpe(r, rf), "cagr": metrics.cagr(r), "ann_vol": metrics.ann_vol(r),
            "max_drawdown": metrics.max_drawdown(r), "sortino": metrics.sortino(r, rf),
            "avg_exposure": float(d["exposure"].mean()),
            "avg_one_way_turnover_per_rebalance": float(d.turnover[d.turnover > 0].mean() / 2),
            "annual_one_way_turnover": float(d.turnover.sum() / 2 / years),
            "avg_trades_per_rebalance": float(reb.groupby("date").size().mean()) if len(reb) else 0.0,
            "cost_drag_total": float(d.cost.sum()),
            "cost_drag_annual": float(d.cost.sum() / years),
            "gross_minus_net_cagr": metrics.cagr(d["gross"]) - metrics.cagr(r)}


def main():
    cfg = yaml.safe_load((SDIR / "configs" / "primary_pit.yaml").read_text())
    loader = TrainingLoader()  # max_date 2019-12-31
    with RunLogger(SDIR, variant="primary_pit", split="validation", cfg=cfg,
                   purpose="[PIT universe re-validation] Pre-registered validation of frozen V1 + frozen MM overlay (c fixed from fit).",
                   hypothesis="Overlay lowers vol and MDD vs unmanaged V1 with Sharpe not lower (see preregistration).",
                   key_params={"c": cfg["overlay"]["c"], "cost_bps": 10}) as run:
        res = ep.run(cfg, loader)
        rf = loader.cash_rate()
        bench = loader.benchmarks().set_index("date")["SFIC_BENCH"]
        r = _win(res)["net"]
        unm = ep.v1.backtest(res["v1_targets"], cfg["v1"], loader)
        ru = _win(unm)["net"]
        rb = bench.loc[VS:VE].reindex(r.index)
        m = {"split": "validation", "window": [VS, VE], "c": cfg["overlay"]["c"],
             "primary_10bps": {**_core(res, rf),
                               **metrics.summary(r, rf, bench, loader.factors("daily"), res["daily_returns"],
                                                 start=VS, end=VE)},
             "unmanaged_v1_10bps": _core(unm, rf),
             "sfic_benchmark": {"sharpe": metrics.sharpe(rb, rf), "cagr": metrics.cagr(rb),
                                "ann_vol": metrics.ann_vol(rb), "max_drawdown": metrics.max_drawdown(rb)},
             "overlay_w_validation": {
                 "mean": float(res["overlay"]["w"].loc[VS:VE].mean()),
                 "min": float(res["overlay"]["w"].loc[VS:VE].min()),
                 "share_months_at_cap": float((res["overlay"]["w"].loc[VS:VE] >= 1).mean())},
             "sharpe_ci_primary": metrics.bootstrap_sharpe_ci(r, rf),
             "sharpe_diff_vs_unmanaged_v1": metrics.bootstrap_sharpe_diff_ci(r, ru, rf),
             "sharpe_diff_vs_sfic_benchmark": metrics.bootstrap_sharpe_diff_ci(r, rb, rf),
             "stats_full_sample_engine": res["stats"]}
        sens = {}
        for bps in (0, 5, 10, 25):
            rs = res if bps == 10 else ep.run({**cfg, "cost_bps": float(bps)}, loader)
            us = unm if bps == 10 else ep.v1.backtest(res["v1_targets"], cfg["v1"], loader, cost_bps=float(bps))
            sens[f"{bps}bps"] = {"primary": {k: v for k, v in _core(rs, rf).items()
                                             if k in ("sharpe", "cagr", "ann_vol", "max_drawdown", "cost_drag_annual")},
                                 "unmanaged_v1": {k: v for k, v in _core(us, rf).items()
                                                  if k in ("sharpe", "cagr", "ann_vol", "max_drawdown", "cost_drag_annual")},
                                 "sharpe_diff_vs_unmanaged_v1": metrics.bootstrap_sharpe_diff_ci(
                                     _win(rs)["net"], _win(us)["net"], rf)}
        m["cost_sensitivity"] = sens
        m["variants_tried"] = 1
        m["design_variants"] = 1
        m["universe"] = "point-in-time S&P 500 membership (loader.universe corrected 2026-11-17)"
        m["c_old_universe"] = 0.06074283701403243
        m["survivorship_caveat"] = ("Universe is point-in-time S&P 500 membership; the changes table is sparse "
                                    "before ~2008, so 2000-2007 membership is still partly survivor-based.")
        run.record(res, m)
        res["overlay"].to_csv(run.dir / "overlay_rv_w.csv")
        unm["daily_returns"].to_csv(run.dir / "unmanaged_v1_10bps_daily_returns.csv", index=False)
        fz = SDIR / "outputs" / "frozen"
        fz.mkdir(parents=True, exist_ok=True)
        for k in ("daily_returns", "positions", "trades"):
            res[k].to_csv(fz / f"{k}.csv", index=False)
        res["overlay"].to_csv(fz / "overlay_rv_w.csv")
        (fz / "config.yaml").write_text(yaml.safe_dump(cfg, sort_keys=True))
        (fz / "metrics.json").write_text(json.dumps({**m, "validation_run_id": run.run_id}, indent=2, default=str))
        print(json.dumps(m, indent=2, default=str))
        run.note(outcome=(f"Sharpe {m['primary_10bps']['sharpe']:.3f} vs unmanaged {m['unmanaged_v1_10bps']['sharpe']:.3f}"
                          f" vs SFIC {m['sfic_benchmark']['sharpe']:.3f}"),
                 next_decision="Freeze primary (pre-registered single spec) with write_freeze_record.")


def unmanaged_run(cfg, loader):
    """Separate logged run of unmanaged V1 (same frozen V1 code, 10 bps) on the PIT universe."""
    with RunLogger(SDIR, variant="unmanaged_v1_pit", split="validation", cfg={**cfg, "overlay": {**cfg["overlay"], "enabled": False}},
                   purpose="[PIT universe] Unmanaged frozen V1 reference for the combination (no overlay).",
                   hypothesis="Reference only; not a design variant.", key_params={"cost_bps": 10}) as run:
        res = ep.run(cfg, loader)
        unm = ep.v1.backtest(res["v1_targets"], cfg["v1"], loader)
        rf = loader.cash_rate()
        m = {"split": "validation", "window": [VS, VE], "unmanaged_v1_10bps": _core(unm, rf)}
        for bps in (0, 5, 25):
            m[f"unmanaged_v1_{bps}bps"] = _core(ep.v1.backtest(res["v1_targets"], cfg["v1"], loader,
                                                              cost_bps=float(bps)), rf)
        m["sharpe_ci"] = metrics.bootstrap_sharpe_ci(_win(unm)["net"], rf)
        run.record(unm, m)
        print(json.dumps(m, indent=2, default=str))
        run.note(outcome=f"Unmanaged V1 Sharpe {m['unmanaged_v1_10bps']['sharpe']:.3f}", next_decision="Re-freeze.")


if __name__ == "__main__":
    import sys
    if "--unmanaged" in sys.argv:
        unmanaged_run(yaml.safe_load((SDIR / "configs" / "primary_pit.yaml").read_text()), TrainingLoader())
    else:
        main()
