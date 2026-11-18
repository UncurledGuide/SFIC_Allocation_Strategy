"""Run any model config:  python run_model.py configs/baseline.yaml [configs/2b.yaml ...] [--costs 0 5 10]
Writes results/<stage>/<name>_{returns,swaps,metrics}.csv and logs the trial to results/trials_log.csv."""
import argparse
from pathlib import Path
import numpy as np, pandas as pd
from src import data, models, backtest, metrics, overlay

ap = argparse.ArgumentParser()
ap.add_argument("configs", nargs="+")
ap.add_argument("--costs", nargs="+", type=float, default=[0.0], help="one-way trading cost in bps (default 0)")
args = ap.parse_args()

ctx = None
for path in args.configs:
    cfg = models.load_model_cfg(path)
    ctx = ctx or models.build_context(cfg)
    fn = models.build_target_fn(cfg, ctx)
    LS = data._use_lseg(None)
    if LS: cfg["tag"] = "lseg:" + cfg["tag"]
    out = Path("results") / (("lseg_" if LS else "") + cfg["stage"]); out.mkdir(parents=True, exist_ok=True)
    PER = {"IS": cfg["periods"]["in_sample"], "OOS": cfg["periods"]["out_of_sample"], "Full": ["2002-01-01", None]}
    rows, expo = [], None
    ov = cfg.get("overlay", {})
    if ov.get("enabled"):      # Layer 4: pass 1 = unlevered strategy (0 bps) -> exposure schedule -> pass 2 = scaled run
        base_fn = fn
        u, *_ = backtest.run_backtest(ctx.rets, ctx.dates, base_fn, ctx.tbill, cost_bps=0)
        tgt = overlay.target_vol(ctx.bench, ov["target_calib_end"])
        expo = overlay.exposure_schedule(u, ctx.dates, tgt, ov["vol_window"], ov["min_change"])
        fn = lambda d, w: base_fn(d, w) * expo[d]
        print(f"[L4] sigma_target (benchmark vol through {ov['target_calib_end']}) = {tgt:.4f}")
    for c in args.costs:
        r, sw, to, _ = backtest.run_backtest(ctx.rets, ctx.dates, fn, ctx.tbill, cost_bps=c)
        backtest.log_trial(cfg["tag"], {"config": path, "name": cfg["name"]}, metrics.perf(r, ctx.tbill, ctx.bench, sw), c)
        for pn, (a, b) in PER.items():
            rows.append({"model": cfg["name"], "cost_bps": c, "period": pn, **metrics.perf(r.loc[a:b], ctx.tbill, ctx.bench, sw),
                         "turnover": float(to.loc[a:b].mean())})
        if c == args.costs[0]:
            r.to_csv(out / f"{cfg['name']}_returns.csv"); sw.to_csv(out / f"{cfg['name']}_swaps.csv")
            if expo is not None:
                expo.rename("w").to_csv(out / f"{cfg['name']}_exposure.csv")
                print(f"[L4] exposure w: mean {expo.mean():.3f}, min {expo.min():.3f}, share of rebalances with w<1: {(expo<1).mean():.1%}, changes: {int((expo.diff().abs()>0).sum())}")
    m = pd.DataFrame(rows); m.to_csv(out / f"{cfg['name']}_metrics.csv", index=False)
    pd.set_option("display.width", 250); pd.set_option("display.float_format", "{:.3f}".format)
    print(f"== {cfg['name']} ({path}) ==")
    print(m[m.cost_bps == args.costs[0]][["period", "CAGR", "Vol", "Sharpe", "Sortino", "MaxDD", "Calmar", "Beta", "Alpha", "InfoRatio", "avg_swaps", "max_swaps", "max_swaps_qtr"]].to_string(index=False))
