"""VALIDATION 2015-2019: pre-registered specs + comparators + sensitivities (logs/preregistration.md)."""
import copy, json
import pandas as pd
from common import metrics
from common.data_access import TrainingLoader
from strategy_2_vol_managed.scripts.common_run import load_cfg, logged_run, SDIR

L = TrainingLoader()
S, E = "2015-01-01", "2019-12-31"
rf = L.cash_rate()
bench = L.benchmarks().set_index("date")["SFIC_BENCH"]
P = load_cfg("primary"); B = load_cfg("baseline_monthly")

specs = {"primary": P}
v = copy.deepcopy(P); v["overlay"].update(rv_window_months=3, c=0.06117299836813377); specs["rv3m"] = v
v = copy.deepcopy(P); v["overlay"].update(c_method="median_rv", c=0.05070285679775571); specs["c_median"] = v
v = copy.deepcopy(P); v["overlay"].update(floor=0.25); specs["floor25"] = v
specs["baseline_monthly"] = B
v = copy.deepcopy(B); v["baseline"]["every_n_months"] = 2; specs["baseline_2monthly"] = v

out, rets = {}, {}
for name, cfg in specs.items():
    res, m = logged_run(name, "validation", cfg, L, purpose=f"Pre-registered validation run: {name}",
                        hypothesis="Overlay: shallower MDD and higher Sharpe than baseline_monthly",
                        key_params=cfg.get("overlay", {}) | {"every_n_months": cfg["baseline"]["every_n_months"]},
                        start=S, end=E)
    m.pop("exposure_target", None)
    out[name] = m
    rets[name] = res["daily_returns"].set_index("date")["net"].loc[S:E]
    print(name, {k: round(m[k], 4) for k in ("sharpe", "max_drawdown", "ann_vol", "avg_exposure")})

boot = {}
for a, b in [("primary", "baseline_monthly"), ("rv3m", "baseline_monthly"), ("c_median", "baseline_monthly"),
             ("floor25", "baseline_monthly"), ("rv3m", "primary"), ("c_median", "primary"), ("floor25", "primary"),
             ("baseline_2monthly", "baseline_monthly")]:
    boot[f"{a}_minus_{b}"] = metrics.bootstrap_sharpe_diff_ci(rets[a], rets[b], rf)
bk = bench.loc[S:E]
for n in ("primary", "baseline_monthly"):
    boot[f"{n}_minus_SFIC_BENCH"] = metrics.bootstrap_sharpe_diff_ci(rets[n], bk, rf)
    boot[f"{n}_sharpe_ci"] = metrics.bootstrap_sharpe_ci(rets[n], rf)
bench_m = {"sharpe": metrics.sharpe(bk, rf), "sortino": metrics.sortino(bk, rf), "cagr": metrics.cagr(bk),
           "ann_vol": metrics.ann_vol(bk), "max_drawdown": metrics.max_drawdown(bk),
           "factor_loadings": metrics.factor_loadings(bk, L.factors("daily"))}

# Sensitivities (reporting only)
sens = {}
for name in ("primary", "baseline_monthly"):
    for bps in (0, 5, 25):
        c = copy.deepcopy(specs[name]); c["cost_bps"] = bps
        _, m = logged_run(f"{name}_cost{bps}", "validation", c, L, purpose=f"Cost sensitivity {bps} bps",
                          hypothesis="Ranking vs baseline robust to costs", key_params={"cost_bps": bps}, start=S, end=E)
        sens[f"{name}_cost{bps}"] = {k: m[k] for k in ("sharpe", "cagr", "max_drawdown", "total_cost_drag")}
    for alloc in (0.01, 0.05):
        c = copy.deepcopy(specs[name]); c["rounding"] = "whole_share"; c["allocation"] = alloc
        _, m = logged_run(f"{name}_whole{int(alloc*100)}pct", "validation", c, L,
                          purpose=f"Whole-share rounding at {alloc:.0%}", hypothesis="Rounding drag small",
                          key_params={"rounding": "whole_share", "allocation": alloc}, start=S, end=E)
        sens[f"{name}_whole{int(alloc*100)}pct"] = {k: m[k] for k in ("sharpe", "cagr", "max_drawdown", "avg_exposure",
                                                                     "total_cost_drag", "avg_trades_per_rebalance")}
res = {"validation": out, "sfic_benchmark": bench_m, "bootstrap": boot, "sensitivity": sens}
(SDIR / "logs" / "validation_results.json").write_text(json.dumps(res, indent=2, default=str))
print(json.dumps({"boot": boot, "bench": {k: v for k, v in bench_m.items() if k != 'factor_loadings'}, "sens": sens}, indent=1, default=str))
