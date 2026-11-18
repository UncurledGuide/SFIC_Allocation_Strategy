import json, pandas as pd, numpy as np
from src import data, signals, portfolio as P, backtest, metrics
CFG = data.CFG
px = data.get_prices(); sig = signals.compute_all(px, CFG)
uni = pd.read_pickle(data.DATA / "universe_dollar.pkl"); dates = list(uni)
rets = px["adj_close"].pct_change(fill_method=None)
vol = rets.rolling(CFG["portfolio"]["vol_window"], min_periods=CFG["portfolio"]["vol_window"]).std()
bench, tb = data.get_benchmark(), data.get_tbill()
ever = sorted({t for v in uni.values() for t in v})
sectors = data.get_sectors(ever)
print("sectors: %d tickers, %d Unknown" % (len(ever), (sectors == "Unknown").sum()))
n, cap = CFG["baseline"]["n_stocks"], CFG["portfolio"]["max_per_sector"]
tr = CFG["trading"]

def order(d, need_vol=False):
    return P.pct_rank_score(d, sig, uni, extra_ok=vol if need_vol else None)

def f_base(d, w):  return P.equal_weight(P.baseline_select(d, sig, uni, n, CFG["baseline"]["mom_share"]))
def f_l1(d, w):    return P.equal_weight(list(order(d).index[:n]))
def f_l12(d, w):
    o = order(d, True); return P.inverse_vol_weights(P.greedy_capped(o, sectors, n, cap), vol.loc[d])
def f_l123(d, w):
    o = order(d, True)
    t = P.buffered_select(o, sectors, list(w.index), n, tr["buffer_exit"], tr["max_swaps"], cap)
    return P.inverse_vol_weights(t, vol.loc[d])

MODELS = {"Baseline": f_base, "+L1": f_l1, "+L1+L2": f_l12, "+L1+L2+L3": f_l123}
PER = {"IS": CFG["periods"]["in_sample"], "OOS": CFG["periods"]["out_of_sample"], "Full": ["2002-01-01", None]}
rows, rets_out, sw_out, w_out = [], {}, {}, {}
for name, fn in MODELS.items():
    for c in CFG["costs_bps"]:
        r, sw, to, wl = backtest.run_backtest(rets, dates, fn, tb, cost_bps=c)
        m = metrics.perf(r, tb, bench, sw)
        backtest.log_trial(name, {"layers": name}, m, c)
        for pn, (a, b) in PER.items():
            rows.append({"model": name, "cost_bps": c, "period": pn, **metrics.perf(r.loc[a:b], tb, bench, sw),
                         "turnover": float(to.loc[a:b].mean()) if len(to.loc[a:b]) else np.nan})
        if c == 0:
            rets_out[name], sw_out[name] = r, sw
            w_out[name] = wl
    print("done", name, flush=True)
df = pd.DataFrame(rows); df.to_csv("results/stage3/stage3_ablation_all.csv", index=False)
pd.DataFrame(rets_out).to_csv("results/stage3/stage3_returns.csv"); pd.DataFrame(sw_out).to_csv("results/stage3/stage3_swaps.csv")
pd.set_option("display.width", 250); pd.set_option("display.float_format", "{:.3f}".format)
cols = ["model", "period", "CAGR", "Vol", "Sharpe", "Sortino", "MaxDD", "Calmar", "Beta", "Corr", "avg_swaps", "max_swaps", "max_swaps_qtr", "turnover"]
print(df[df.cost_bps == 0][cols].to_string(index=False))
print("\nCost sensitivity (Full sample Sharpe / CAGR):")
print(df[df.period == "Full"].pivot(index="model", columns="cost_bps", values=["Sharpe", "CAGR"]).loc[list(MODELS)].to_string())
# crash windows
W = {"2008-09..2009-03": ("2008-09-01", "2009-03-31"), "2009-03..05 (mom crash)": ("2009-03-01", "2009-05-31"),
     "2020-02..04": ("2020-02-01", "2020-04-30"), "2022": ("2022-01-01", "2022-12-31")}
cr = {k: {m: float((1 + rets_out[m].loc[a:b]).prod() - 1) for m in MODELS} | {"Benchmark": float((1 + bench.loc[a:b]).prod() - 1)} for k, (a, b) in W.items()}
print("\nCrash windows (cumulative return):"); print(pd.DataFrame(cr).T.to_string())
pd.DataFrame(cr).T.to_csv("results/stage3/stage3_crash.csv")
# sanity: sector cap & swap cap
l3 = w_out["+L1+L2+L3"]; l2 = w_out["+L1+L2"]
mx = lambda wl: max(pd.Series([sectors.get(t, "Unknown") for t in w.index]).where(lambda s: s != "Unknown").value_counts().max() for w in wl.values())
print("\nmax names in one (known) sector: L2 =", mx(l2), " L3 =", mx(l3), "| max swaps L3 =", sw_out["+L1+L2+L3"].max())
print("max single weight L2: %.3f, L3: %.3f" % (max(w.max() for w in l2.values()), max(w.max() for w in l3.values())))
# ablation table (cumulative models, 0 bps) as csv + markdown
o = {"Baseline": 0, "+L1": 1, "+L1+L2": 2, "+L1+L2+L3": 3}; pp = {"IS": 0, "OOS": 1, "Full": 2}
a = df[df.cost_bps == 0].drop(columns="cost_bps")
a = a.assign(k1=a.period.map(pp), k2=a.model.map(o)).sort_values(["k1", "k2"]).drop(columns=["k1", "k2"])
a.to_csv("results/stage3/ablation_table_stage3.csv", index=False)
open("results/stage3/ablation_table_stage3.md", "w").write(a.round(3).to_markdown(index=False))
