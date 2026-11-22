"""Setup smoke test (not a strategy): equal-weight top-15 by trailing dollar volume, monthly.

Proves loader -> universe -> backtest_engine -> metrics -> run_logger end to end on TrainingLoader data.
Logs under logs/setup_smoke/ (not in any strategy registry).
Run: .venv/bin/python tests/smoke_dummy.py
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd

from common import metrics
from common.backtest_engine import rebalance_dates, run_backtest
from common.data_access import TrainingLoader
from common.run_logger import RunLogger

ROOT = Path(__file__).resolve().parents[1]
SMOKE = ROOT / "logs" / "setup_smoke"


def run(cfg, loader):
    td = loader.trading_days()
    dates = rebalance_dates(td, cfg["start"], loader.max_date, every_n_months=cfg["every_n_months"])
    rows = {}
    for d in dates:
        u = loader.universe(d)[: cfg["n"]]
        rows[d] = pd.Series(1.0 / len(u), index=u)
    targets = pd.DataFrame(rows).T.fillna(0.0)
    return run_backtest(targets, loader.returns(), loader.cash_rate(), close=loader.prices(field="close"),
                        rounding=cfg["rounding"], allocation=cfg["allocation"], start=cfg["start"])


def main():
    t0 = time.time()
    loader = TrainingLoader()
    cfg = {"n": 15, "start": "1999-12-31", "every_n_months": 1, "rounding": "whole_share", "allocation": 0.01}
    with RunLogger(SMOKE, variant="smoke_ew_top15_dollar_volume", split="smoke", cfg=cfg,
                   purpose="Setup smoke test of the shared pipeline", hypothesis="Plumbing works end to end",
                   runs_root=SMOKE / "runs", registry_path=SMOKE / "registry.csv") as run_log:
        res = run(cfg, loader)
        r = res["daily_returns"].set_index("date")["net"]
        bench = loader.benchmarks().set_index("date")["SFIC_BENCH"]
        m = metrics.summary(r, loader.cash_rate(), bench, loader.factors("daily"), res["daily_returns"],
                            start="2000-01-01")
        m["engine_stats"] = res["stats"]
        m["sharpe_ci"] = metrics.bootstrap_sharpe_ci(r.loc["2000":], loader.cash_rate(), n_boot=300)
        m["sharpe_diff_vs_bench_ci"] = metrics.bootstrap_sharpe_diff_ci(r.loc["2000":], bench, loader.cash_rate(),
                                                                         n_boot=300)
        run_log.record(res, m)
        run_log.note("smoke ran", "remove outputs")
        print(json.dumps({k: v for k, v in m.items() if not isinstance(v, dict)}, indent=1, default=str))
        print(json.dumps(m["engine_stats"], indent=1))
        print("factor loadings:", json.dumps(m["factor_loadings"], default=str))
    print(f"run dir: {run_log.dir}  ({time.time() - t0:.1f}s)")
    expected = {"config.yaml", "meta.json", "stdout.log", "metrics.json", "equity_curve.csv", "daily_returns.csv",
                "positions.csv", "trades.csv", "notes.md"}
    missing = expected - {p.name for p in run_log.dir.iterdir()}
    assert not missing, missing
    assert run_log.status == "ok"
    return run_log, m


if __name__ == "__main__":
    main()
