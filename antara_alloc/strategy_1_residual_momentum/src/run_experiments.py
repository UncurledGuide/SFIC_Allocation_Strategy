"""Logged experiment runner (every run goes through common.run_logger.RunLogger).

  ../.venv/bin/python -m strategy_1_residual_momentum.src.run_experiments --config primary --split fit \
      --purpose "..." --hypothesis "..."

split=fit        -> TrainingLoader(max_date="2014-12-31"), scored 2000-01-01..2014-12-31
split=validation -> TrainingLoader() (<= 2019-12-31),   scored 2015-01-01..2019-12-31 (fit window also reported)
Validation results are NOT out-of-sample test results.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from common import metrics
from common.data_access import TrainingLoader
from common.run_logger import RunLogger

from . import entrypoint

SDIR = Path(__file__).resolve().parents[1]
WINDOWS = {"fit": ("2000-01-01", "2014-12-31"), "validation": ("2015-01-01", "2019-12-31")}
SURVIVORSHIP = ("Survivorship caveat: candidate pool over-represents firms that survived to today "
                "(only ~413 names priced in 2000); absolute returns are biased upward, mostly early years.")


def load_cfg(name: str) -> dict:
    return yaml.safe_load((SDIR / "configs" / f"{name}.yaml").read_text())


def score(res: dict, loader, start, end, boot: int = 1000) -> dict:
    dr = res["daily_returns"]
    r = dr.set_index("date")["net"]
    rf = loader.cash_rate()
    bench = loader.benchmarks().set_index("date")["SFIC_BENCH"]
    m = metrics.summary(r, rf, bench, loader.factors("daily"), dr, start=start, end=end)
    rw = r.loc[start:end]
    m["gross_sharpe"] = metrics.sharpe(dr.set_index("date")["gross"].loc[start:end], rf)
    m["cost_drag_window"] = float(dr.set_index("date")["cost"].loc[start:end].sum())
    m["sharpe_ci"] = metrics.bootstrap_sharpe_ci(rw, rf, n_boot=boot)
    m["sharpe_diff_vs_sfic_bench"] = metrics.bootstrap_sharpe_diff_ci(rw, bench, rf, n_boot=boot)
    return m


def _short(res: dict, loader, start, end) -> dict:
    dr = res["daily_returns"].set_index("date").loc[start:end]
    rf = loader.cash_rate()
    return {"sharpe": round(metrics.sharpe(dr["net"], rf), 4), "cagr": round(metrics.cagr(dr["net"]), 4),
            "max_drawdown": round(metrics.max_drawdown(dr["net"]), 4), "cost_drag": round(float(dr["cost"].sum()), 4),
            "avg_exposure": round(float(dr["exposure"].mean()), 4),
            "avg_trades_per_rebalance": round(res["stats"]["avg_trades_per_rebalance"], 2)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--split", required=True, choices=["fit", "validation"])
    ap.add_argument("--purpose", required=True)
    ap.add_argument("--hypothesis", required=True)
    ap.add_argument("--variant", default=None)
    ap.add_argument("--sensitivity", action="store_true", help="also report 0/5/10/25 bps and whole-share 1%%/5%%")
    a = ap.parse_args(argv)
    cfg = load_cfg(a.config)
    loader = TrainingLoader(max_date="2014-12-31") if a.split == "fit" else TrainingLoader()
    variant = a.variant or a.config
    with RunLogger(SDIR, variant=variant, split=a.split, cfg=cfg, purpose=a.purpose,
                   hypothesis=a.hypothesis, key_params=cfg) as run:
        res = entrypoint.run(cfg, loader)
        m = score(res, loader, *WINDOWS[a.split])
        if a.split == "validation":
            m["fit_window"] = {k: v for k, v in score(res, loader, *WINDOWS["fit"], boot=200).items()
                               if not isinstance(v, dict)}
        m["engine_stats"] = res["stats"]
        m["caveat"] = SURVIVORSHIP
        run.record(res, m)
        res["diagnostics"].to_csv(run.dir / "diagnostics.csv", index=False)
        res["targets"].to_csv(run.dir / "targets.csv")
        if a.sensitivity:  # same targets, different cost / rounding / allocation (not selection variants)
            sens = {}
            for bps in (0, 5, 10, 25):
                sens[f"cost_{bps}bps"] = _short(entrypoint.backtest(res["targets"], cfg, loader, cost_bps=bps),
                                                loader, *WINDOWS[a.split])
            for alloc in (0.01, 0.05):
                sens[f"whole_share_alloc_{alloc}"] = _short(entrypoint.backtest(
                    res["targets"], cfg, loader, rounding="whole_share", allocation=alloc), loader, *WINDOWS[a.split])
            m["sensitivity"] = sens
            print("sensitivity:", json.dumps(sens, indent=1))
        head = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in m.items() if not isinstance(v, dict)}
        print(json.dumps(head, indent=1, default=str))
        print("engine:", json.dumps(res["stats"], default=str))
        print("FF4:", json.dumps({k: round(v, 3) for k, v in m["factor_loadings"].items()}, default=str))
        print("sharpe CI:", m["sharpe_ci"], "\nvs SFIC bench:", m["sharpe_diff_vs_sfic_bench"])
        run.note(outcome=f"net Sharpe {m['sharpe']:.2f}, CAGR {m['cagr']:.1%}, MDD {m['max_drawdown']:.1%}, "
                         f"turnover {m.get('annual_one_way_turnover', float('nan')):.2f}/yr",
                 next_decision="see logs/STATUS.md")
    print("run dir:", run.dir)


if __name__ == "__main__":
    main()
