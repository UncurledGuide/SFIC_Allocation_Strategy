import pandas as pd, numpy as np
from src import data, signals, portfolio, backtest, metrics
CFG = data.CFG
px = data.get_prices()
sig = signals.compute_all(px, CFG)
uni = pd.read_pickle(data.DATA / "universe_dollar.pkl")
dates = list(uni.keys())
rets = px["adj_close"].pct_change(fill_method=None)
bench, tb = data.get_benchmark(), data.get_tbill()
print("bench", bench.index[0].date(), bench.index[-1].date(), "| tbill", tb.index[0].date(), tb.index[-1].date())
bad = rets.abs().stack(); bad = bad[bad > 1.0]
print("daily |returns|>100%:", len(bad)); print(bad.sort_values(ascending=False).head(8))

bl = CFG["baseline"]
fn = lambda d, w: portfolio.equal_weight(portfolio.baseline_select(d, sig, uni, bl["n_stocks"], bl["mom_share"]))
P = {"IS": CFG["periods"]["in_sample"], "OOS": CFG["periods"]["out_of_sample"], "Full": ["2002-01-01", None]}
rows = []
res = {}
for c in CFG["costs_bps"]:
    r, sw, to, wl = backtest.run_backtest(rets, dates, fn, tb, cost_bps=c)
    res[c] = (r, sw, to)
    m = metrics.perf(r, tb, bench, sw)
    backtest.log_trial("baseline_70_30", {"n": 15, "mom_share": .7}, m, c)
    for pn, (a, b) in P.items():
        rr = r.loc[a:b]
        rows.append({"model": "Baseline", "cost_bps": c, "period": pn, **metrics.perf(rr, tb, bench, sw)})
r, sw, to = res[0]
bm = bench.loc[r.index[0]:]
for pn, (a, b) in P.items():
    rows.append({"model": "Benchmark", "cost_bps": 0, "period": pn, **metrics.perf(bm.loc[a:b], tb, bench)})
rows.append({"model": "Baseline", "cost_bps": 0, "period": "Last2y", **metrics.perf(r.iloc[-504:], tb, bench, sw)})
rows.append({"model": "Benchmark", "cost_bps": 0, "period": "Last2y", **metrics.perf(bm.iloc[-504:], tb, bench)})
df = pd.DataFrame(rows)
df.to_csv("results/stage2/stage2_baseline.csv", index=False)
pd.set_option("display.width", 250); pd.set_option("display.float_format", "{:.3f}".format)
cols = ["model", "cost_bps", "period", "CAGR", "Vol", "Sharpe", "Sortino", "MaxDD", "Calmar", "Beta", "Corr", "avg_swaps", "max_swaps", "max_swaps_qtr"]
print(df[cols].to_string(index=False))
print("\nTrading window:", r.index[0].date(), "->", r.index[-1].date(), "n days", len(r))
print("swaps per rebalance (ex initial build): n=%d mean=%.2f median=%.1f min=%d max=%d" % (len(sw), sw.mean(), sw.median(), sw.min(), sw.max()))
print("avg one-way turnover per rebalance: %.2f" % to.mean())
q = sw.groupby([sw.index.year, sw.index.quarter]).sum()
print("swaps/quarter: mean %.1f max %d; share of quarters >20: %.1f%%" % (q.mean(), q.max(), 100*(q>20).mean()))
sw.to_csv("results/stage2/stage2_baseline_swaps.csv"); r.to_csv("results/stage2/stage2_baseline_returns.csv")
