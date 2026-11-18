"""Pre-Stage-4 diagnostics. Every variant is run through the same engine at 0 bps and logged to trials_log.csv."""
import pandas as pd, numpy as np
from src import data, signals, portfolio as P, backtest, metrics, universe as U
CFG = data.CFG
px = data.get_prices(); sig = signals.compute_all(px, CFG)
uni = pd.read_pickle(data.DATA / "universe_dollar.pkl"); dates = list(uni)
rets = px["adj_close"].pct_change(fill_method=None)
vol = rets.rolling(63, min_periods=63).std()
volc = vol.where(P.quality_ok(rets))            # NaN where flagged -> excluded
bench, tb = data.get_benchmark(), data.get_tbill()
sectors = data.get_sectors(sorted({t for v in uni.values() for t in v}))
n, cap, tr = 15, CFG["portfolio"]["max_per_sector"], CFG["trading"]
EW = P.equal_weight

# sanity: the generalised picker reproduces the original baseline picker
for d in dates[20:300:40]:
    assert P.baseline_select2(d, sig, uni) == P.baseline_select(d, sig, uni), d

def order(d, clean):  return P.pct_rank_score(d, sig, uni, extra_ok=volc if clean else vol)
def iv(t, d, clean):
    w = P.inverse_vol_weights(t, vol.loc[d]); return P.cap_weights(w, 0.10) if clean else w

M = {}
M["Baseline"] = lambda d, w: EW(P.baseline_select2(d, sig, uni))
# 1. decompose L1 (each alone on the baseline)
M["1a Base, 6-1 mom (70/30)"] = lambda d, w: EW(P.baseline_select2(d, sig, uni, mom_key="mom6_1"))
M["1b Base, 50/50 split"]     = lambda d, w: EW(P.baseline_select2(d, sig, uni, mom_share=0.5))
M["1c Rank score alone (L1)"] = lambda d, w: EW(list(order(d, False).index[:n]))
# 2. one-at-a-time (spec L2 = inverse-vol + sector cap)
def b_l2(clean):  return lambda d, w: iv(P.baseline_select2(d, sig, uni, ok=volc if clean else vol, sectors=sectors, cap=cap), d, clean)
b_l3 = lambda d, w: EW(P.baseline_buffered(d, sig, uni, list(w.index), exit_n=tr["buffer_exit"], max_swaps=tr["max_swaps"]))
def b_l23(clean): return lambda d, w: iv(P.baseline_buffered(d, sig, uni, list(w.index), ok=volc if clean else vol, sectors=sectors, cap=cap, exit_n=tr["buffer_exit"], max_swaps=tr["max_swaps"]), d, clean)
M["2a Base+L2 (spec)"]    = b_l2(False)
M["2b Base+L3"]           = b_l3
M["2c Base+L2+L3 (spec)"] = b_l23(False)
# 4. fixed L2: quality filter + 10% weight cap
M["4a Base+L2 (fixed)"]    = b_l2(True)
M["4b Base+L2+L3 (fixed)"] = b_l23(True)
# cumulative v2 (stage 3 definitions), spec vs fixed
def c_l12(clean):  return lambda d, w: iv(P.greedy_capped(order(d, clean), sectors, n, cap), d, clean)
def c_l123(clean): return lambda d, w: iv(P.buffered_select(order(d, clean), sectors, list(w.index), n, tr["buffer_exit"], tr["max_swaps"], cap), d, clean)
M["v2 +L1+L2 (spec)"]      = c_l12(False)
M["v2 +L1+L2+L3 (spec)"]   = c_l123(False)
M["v2 +L1+L2 (fixed)"]     = c_l12(True)
M["v2 +L1+L2+L3 (fixed)"]  = c_l123(True)
# 3. fixed universe = today's top-500 by dollar volume, used at every date (look-ahead / survivorship by design)
today = U.build_universe(px["close"], px["volume"], [px["close"].index[-1]], size=500)[px["close"].index[-1]]
uni_fixed = {d: today for d in dates}
M["3 Baseline, FIXED today-top500"] = lambda d, w: EW(P.baseline_select2(d, sig, uni_fixed))

PER = {"IS": CFG["periods"]["in_sample"], "OOS": CFG["periods"]["out_of_sample"], "Full": ["2002-01-01", None]}
rows, rr, wl_all = [], {}, {}
for name, fn in M.items():
    r, sw, to, wl = backtest.run_backtest(rets, dates, fn, tb, cost_bps=0)
    backtest.log_trial("diag:" + name, {"diag": name}, metrics.perf(r, tb, bench, sw), 0)
    rr[name] = r; wl_all[name] = wl
    for pn, (a, b) in PER.items():
        rows.append({"model": name, "period": pn, **metrics.perf(r.loc[a:b], tb, bench, sw),
                     "turnover": float(to.loc[a:b].mean())})
    print("done", name, flush=True)
df = pd.DataFrame(rows); df.to_csv("results/diagnostics/diagnostics_all.csv", index=False)
pd.DataFrame(rr).to_csv("results/diagnostics/diagnostics_returns.csv")
pd.set_option("display.width", 300); pd.set_option("display.max_columns", 50); pd.set_option("display.float_format", "{:.3f}".format)
g = lambda per, col: df[df.period == per].set_index("model")[col]
T = pd.DataFrame({"Sh_IS": g("IS", "Sharpe"), "Sh_OOS": g("OOS", "Sharpe"), "Sh_Full": g("Full", "Sharpe"),
                  "CAGR": g("Full", "CAGR"), "Vol": g("Full", "Vol"), "MaxDD": g("Full", "MaxDD"),
                  "Beta_F": g("Full", "Beta"), "Beta_OOS": g("OOS", "Beta"),
                  "Alpha_F": g("Full", "Alpha"), "t_F": g("Full", "Alpha_t"), "Alpha_OOS": g("OOS", "Alpha"), "t_OOS": g("OOS", "Alpha_t"),
                  "IR_F": g("Full", "InfoRatio"), "avgSw": g("Full", "avg_swaps"), "maxSw": g("Full", "max_swaps"), "maxQ": g("Full", "max_swaps_qtr")}).loc[list(M)]
print(T.to_string()); T.to_csv("results/diagnostics/diagnostics_table.csv")
open("results/diagnostics/diagnostics_table.md", "w").write(T.round(3).to_markdown())
# benchmark reference row
bm = bench.loc[rr["Baseline"].index[0]:]
print("\nBenchmark Sharpe IS/OOS/Full:", [round(metrics.perf(bm.loc[a:b], tb, bench)["Sharpe"], 3) for a, b in PER.values()])
# weight-cap check (exclude final un-traded signal date)
for k in ["2a Base+L2 (spec)", "4a Base+L2 (fixed)", "4b Base+L2+L3 (fixed)", "v2 +L1+L2+L3 (fixed)"]:
    wl = wl_all[k]; ws = [w.max() for d, w in sorted(wl.items())]
    print(k, "max weight (traded rebalances): %.3f" % max(ws))
nflag = sum((~P.quality_ok(rets).loc[d, [t for t in uni[d] if t in rets.columns]]).sum() for d in dates)
print("stock-dates in universe removed by the quality filter:", int(nflag), "of", sum(len(v) for v in uni.values()))
