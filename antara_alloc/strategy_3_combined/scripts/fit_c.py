"""Fit-period only: estimate c on unmanaged V1 2000-2014 returns, write configs/primary.yaml.

Run from the repo root:  .venv/bin/python -m strategy_3_combined.scripts.fit_c
Uses TrainingLoader(max_date='2014-12-31'), which physically refuses later dates.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from common import metrics
from common.data_access import TrainingLoader
from common.run_logger import RunLogger
from strategy_3_combined.src import entrypoint as ep

SDIR = Path(__file__).resolve().parents[1]


def main():
    loader = TrainingLoader(max_date=ep.FIT_END)
    v1cfg, ov = ep.frozen_v1_cfg(), ep.frozen_overlay_cfg()
    est_cfg = {"v1": v1cfg, "overlay": {**ov, "c": None}, "cost_bps": 0.0, "rounding": "fractional",
               "allocation": None}
    with RunLogger(SDIR, variant="primary", split="fit", cfg=est_cfg,
                   purpose="Estimate overlay c on unmanaged V1 fit-period (2000-2014) returns; fit-period check.",
                   hypothesis="c via mm_vol_match on V1; managed fit-period vol below unmanaged, Sharpe not lower.",
                   key_params={"c_method": ov["c_method"], "rv_window_months": ov["rv_window_months"]}) as run:
        est = ep.estimate_fit_c(loader, v1cfg, ov)
        c = est["c"]
        cfg = {"v1": v1cfg, "overlay": {**ov, "c": float(c)}, "cost_bps": None,
               "rounding": "fractional", "allocation": None}
        res = ep.run(cfg, loader)
        rf = loader.cash_rate()
        r = res["daily_returns"].set_index("date")["net"]
        unm10 = ep.v1.backtest(est["targets"], v1cfg, loader)["daily_returns"].set_index("date")["net"]
        m = metrics.summary(r, rf, daily_returns=res["daily_returns"], start=ep.FIT_START, end=ep.FIT_END)
        m.update({"c": c, "rv_median_fit": est["rv_median_fit"], "n_rv_months_fit": est["n_rv_months_fit"],
                  "avg_overlay_w_fit": float(res["overlay"]["w"].loc[ep.FIT_START:ep.FIT_END].mean()),
                  "share_months_capped_fit": float((res["overlay"]["w"].loc[ep.FIT_START:ep.FIT_END] >= 1).mean()),
                  "unmanaged_v1_10bps_fit": metrics.summary(unm10, rf, start=ep.FIT_START, end=ep.FIT_END)})
        run.record(res, m)
        res["overlay"].to_csv(run.dir / "overlay_rv_w.csv")
        (SDIR / "configs" / "primary.yaml").write_text(yaml.safe_dump(cfg, sort_keys=True))
        (SDIR / "logs" / "c_estimate_fit.json").write_text(json.dumps(
            {"c": c, "method": ov["c_method"], "fit": [ep.FIT_START, ep.FIT_END],
             "rv_median_fit": est["rv_median_fit"], "run_id": run.run_id}, indent=2))
        print(json.dumps({k: v for k, v in m.items() if not isinstance(v, dict)}, indent=2, default=str))
        print("unmanaged fit:", json.dumps(m["unmanaged_v1_10bps_fit"], default=str))
        run.note(outcome=f"c={c:.6f}; written to configs/primary.yaml",
                 next_decision="Write preregistration, then single validation run of the primary spec.")


if __name__ == "__main__":
    main()
