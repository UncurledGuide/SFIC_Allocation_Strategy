"""VALIDATION 2015-2019 on the corrected point-in-time universe: frozen primary (new c) + monthly baseline.
Same metrics/bootstrap as validate.py; cost sensitivity 0/5/25 bps. Variants suffixed _pit."""
import copy, json
from common import metrics
from common.data_access import TrainingLoader
from strategy_2_vol_managed.scripts.common_run import load_cfg, logged_run, SDIR

L = TrainingLoader()
S, E = "2015-01-01", "2019-12-31"
rf = L.cash_rate()
bench = L.benchmarks().set_index("date")["SFIC_BENCH"]
specs = {"primary_pit": load_cfg("primary_pit"), "baseline_monthly_pit": load_cfg("baseline_monthly")}
out, rets, results = {}, {}, {}
for name, cfg in specs.items():
    res, m = logged_run(name, "validation", cfg, L,
                        purpose=f"Universe correction re-validation (point-in-time S&P 500): {name}",
                        hypothesis="Frozen overlay keeps shallower MDD than baseline; Sharpe diff ~0",
                        key_params=cfg.get("overlay", {}) | {"every_n_months": 1, "universe": "pit"},
                        start=S, end=E, next_decision="re-freeze primary with new c; holdout re-run follows")
    m.pop("exposure_target", None)
    out[name] = m; results[name] = res
    rets[name] = res["daily_returns"].set_index("date")["net"].loc[S:E]
    print(name, {k: round(m[k], 4) for k in ("sharpe", "cagr", "max_drawdown", "ann_vol", "avg_exposure", "annual_one_way_turnover")})
bk = bench.loc[S:E]
boot = {"primary_pit_minus_baseline_monthly_pit": metrics.bootstrap_sharpe_diff_ci(rets["primary_pit"], rets["baseline_monthly_pit"], rf)}
for n in specs:
    boot[f"{n}_minus_SFIC_BENCH"] = metrics.bootstrap_sharpe_diff_ci(rets[n], bk, rf)
    boot[f"{n}_sharpe_ci"] = metrics.bootstrap_sharpe_ci(rets[n], rf)
bench_m = {"sharpe": metrics.sharpe(bk, rf), "sortino": metrics.sortino(bk, rf), "cagr": metrics.cagr(bk),
           "ann_vol": metrics.ann_vol(bk), "max_drawdown": metrics.max_drawdown(bk),
           "factor_loadings": metrics.factor_loadings(bk, L.factors("daily"))}
sens = {}
for name in specs:
    for bps in (0, 5, 25):
        c = copy.deepcopy(specs[name]); c["cost_bps"] = bps
        _, m = logged_run(f"{name}_cost{bps}", "validation", c, L, purpose=f"Universe correction: cost sensitivity {bps} bps",
                          hypothesis="Ranking vs baseline robust to costs", key_params={"cost_bps": bps, "universe": "pit"},
                          start=S, end=E)
        sens[f"{name}_cost{bps}"] = {k: m[k] for k in ("sharpe", "cagr", "max_drawdown", "total_cost_drag")}
res = {"validation": out, "sfic_benchmark": bench_m, "bootstrap": boot, "sensitivity": sens}
(SDIR / "logs" / "validation_results_pit.json").write_text(json.dumps(res, indent=2, default=str))
# frozen outputs
import shutil, pandas as pd
fz = SDIR / "outputs" / "frozen"
reg = pd.read_csv(SDIR / "logs" / "run_registry.csv")
src_run = reg[(reg.variant == "primary_pit") & (reg.split == "validation")].iloc[-1]["run_dir"]
src_dir = SDIR.parent / src_run
for k in ("daily_returns", "positions", "trades"):
    shutil.copyfile(src_dir / f"{k}.csv", fz / f"{k}.csv")
fit = json.loads((SDIR / "logs" / "c_estimates_fit_pit.json").read_text())
mj = {"spec": "primary (frozen design, c re-estimated on point-in-time universe)",
      "source_run": str(src_run).replace("strategy_2_vol_managed/", ""),
      "split": "validation 2015-01-01..2019-12-31 (NOT out-of-sample test)",
      "universe": "point-in-time S&P 500 membership (data correction 2026-11-17)",
      "c": specs["primary_pit"]["overlay"]["c"], "c_old_universe": fit["old_c_old_universe"],
      "primary_validation": out["primary_pit"], "baseline_monthly_validation": out["baseline_monthly_pit"],
      "sfic_benchmark_validation": bench_m, "bootstrap": boot, "sensitivity": sens, "c_fit_estimates": fit,
      "survivorship_caveat": "Membership is point-in-time but sparse before ~2008 (2000-2007 partly survivor-based) "
                             "and delisted names often lack price data; absolute returns may still be biased upward."}
(fz / "metrics.json").write_text(json.dumps(mj, indent=2, default=str))
print(json.dumps({"boot": boot, "bench": {k: v for k, v in bench_m.items() if k != 'factor_loadings'}, "sens": sens}, indent=1, default=str))
