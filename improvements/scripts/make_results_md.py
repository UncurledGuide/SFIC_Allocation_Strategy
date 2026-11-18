"""Generate docs/RESULTS.md from results/*.csv (no hand-copied numbers)."""
import pandas as pd, numpy as np
from pathlib import Path
from src import data, metrics

R = Path("results"); D = R / "diagnostics"
allm = pd.read_csv(D / "diagnostics_all.csv")
allm = allm[allm.model != "3 Baseline, FIXED today-top500"].copy()
fixed = pd.read_csv(D / "diagnostics_all.csv"); fixed = fixed[fixed.model == "3 Baseline, FIXED today-top500"]
rows = []
S4 = {"2b+L4": "2b_L4", "4b+L4": "4b_L4"}
for k, f in S4.items():
    p = R / "stage4" / f"{f}_metrics.csv"
    if p.exists():
        m = pd.read_csv(p); m = m[m.cost_bps == 0].assign(model=k); rows.append(m)
allm = pd.concat([allm] + rows, ignore_index=True)

def cell(model, per, col): 
    v = allm[(allm.model == model) & (allm.period == per)][col]
    return float(v.iloc[0]) if len(v) else np.nan

ret = pd.read_csv(D / "baseline_returns.csv", index_col=0, parse_dates=True).iloc[:, 0]
bench, tb = data.get_benchmark(), data.get_tbill()
PER = {"IS": ("2002-01-01", "2014-12-31"), "OOS": ("2015-01-01", None), "Full": ("2002-01-01", None)}
bm = bench.loc[ret.index[0]:]
bmet = {p: metrics.perf(bm.loc[a:b], tb, bench) for p, (a, b) in PER.items()}

def row(model, label):
    g = lambda per, c: cell(model, per, c)
    return {"Model": label, "Sharpe IS": g("IS", "Sharpe"), "Sharpe OOS": g("OOS", "Sharpe"), "Sharpe Full": g("Full", "Sharpe"),
            "CAGR": g("Full", "CAGR"), "Vol": g("Full", "Vol"), "Sortino": g("Full", "Sortino"), "MaxDD": g("Full", "MaxDD"),
            "Calmar": g("Full", "Calmar"), "Beta (OOS)": g("OOS", "Beta"), "Alpha (t)": f"{g('Full','Alpha'):.1%} ({g('Full','Alpha_t'):.1f})",
            "IR": g("Full", "InfoRatio"), "Swaps avg/max/qtr": f"{g('Full','avg_swaps'):.1f} / {g('Full','max_swaps'):.0f} / {g('Full','max_swaps_qtr'):.0f}"}

LAB = [("Baseline", "Baseline (70/30, 180d mom + 52w-high)"),
       ("1a Base, 6-1 mom (70/30)", "1a Baseline, 6-1 momentum"), ("1b Base, 50/50 split", "1b Baseline, 50/50 split"),
       ("1c Rank score alone (L1)", "1c L1 alone (rank-average score)"),
       ("2a Base+L2 (spec)", "2a Baseline + L2"), ("2b Base+L3", "**2b Baseline + L3**"), ("2c Base+L2+L3 (spec)", "2c Baseline + L2 + L3"),
       ("4a Base+L2 (fixed)", "4a Baseline + L2 (fixed)"), ("4b Base+L2+L3 (fixed)", "**4b Baseline + L2 + L3 (fixed)**"),
       ("v2 +L1+L2 (spec)", "v2 L1+L2"), ("v2 +L1+L2+L3 (spec)", "v2 L1+L2+L3"),
       ("v2 +L1+L2 (fixed)", "v2 L1+L2 (fixed)"), ("v2 +L1+L2+L3 (fixed)", "v2 L1+L2+L3 (fixed)"),
       ("2b+L4", "2b + L4 (vol target)"), ("4b+L4", "4b + L4 (vol target)")]
T = pd.DataFrame([row(m, l) for m, l in LAB if ((allm.model == m).any())])
bt = {"Model": "Benchmark 65/15/20", "Sharpe IS": bmet["IS"]["Sharpe"], "Sharpe OOS": bmet["OOS"]["Sharpe"], "Sharpe Full": bmet["Full"]["Sharpe"],
      "CAGR": bmet["Full"]["CAGR"], "Vol": bmet["Full"]["Vol"], "Sortino": bmet["Full"]["Sortino"], "MaxDD": bmet["Full"]["MaxDD"],
      "Calmar": bmet["Full"]["Calmar"], "Beta (OOS)": 1.0, "Alpha (t)": "-", "IR": np.nan, "Swaps avg/max/qtr": "-"}
T = pd.concat([T, pd.DataFrame([bt])], ignore_index=True)
fmt = {c: "{:.2f}" for c in ["Sharpe IS", "Sharpe OOS", "Sharpe Full", "Sortino", "Calmar", "Beta (OOS)", "IR"]}
fmt.update({c: "{:.1%}" for c in ["CAGR", "Vol", "MaxDD"]})
Tf = T.copy()
for c, f in fmt.items():
    Tf[c] = Tf[c].map(lambda v: "-" if pd.isna(v) else f.format(v))

# cost sensitivity: any model with a multi-cost run on file
cs = []
s3 = pd.read_csv(R / "stage3" / "stage3_ablation_all.csv")
for m, lab in [("Baseline", "Baseline"), ("+L1+L2+L3", "v2 L1+L2+L3")]:
    x = s3[(s3.model == m) & (s3.period == "Full")].set_index("cost_bps").Sharpe
    cs.append({"Model": lab, **{f"{int(c)} bps": f"{x[c]:.2f}" for c in x.index}})
for k, f in S4.items():
    p = R / "stage4" / f"{f}_metrics.csv"
    if p.exists():
        x = pd.read_csv(p); x = x[x.period == "Full"].set_index("cost_bps").Sharpe
        cs.append({"Model": k, **{f"{int(c)} bps": f"{x[c]:.2f}" for c in x.index}})
C = pd.DataFrame(cs)

# crash windows
W = {"2008-09 to 2009-03": ("2008-09-01", "2009-03-31"), "2009-03 to 2009-05 (momentum crash)": ("2009-03-01", "2009-05-31"),
     "2020-02 to 2020-04": ("2020-02-01", "2020-04-30"), "2022": ("2022-01-01", "2022-12-31")}
series = {"Baseline": D / "baseline_returns.csv", "2b": D / "2b_baseline_L3_returns.csv", "4b": D / "4b_baseline_L2_L3_fixed_returns.csv"}
for k, f in S4.items():
    if (R / "stage4" / f"{f}_returns.csv").exists():
        series[k + " (L4)" if False else f"{k}"] = R / "stage4" / f"{f}_returns.csv"
cr = {}
for k, p in series.items():
    r = pd.read_csv(p, index_col=0, parse_dates=True).iloc[:, 0]
    cr[k] = {w: (1 + r.loc[a:b]).prod() - 1 for w, (a, b) in W.items()}
cr["Benchmark"] = {w: (1 + bench.loc[a:b]).prod() - 1 for w, (a, b) in W.items()}
CR = pd.DataFrame(cr).T.map(lambda v: f"{v:.1%}")

fx = fixed.set_index("period")
fixed_md = pd.DataFrame([{"Model": "Baseline, fixed universe = TODAY's top-500", "Sharpe IS": fx.loc["IS", "Sharpe"], "Sharpe OOS": fx.loc["OOS", "Sharpe"],
                          "Sharpe Full": fx.loc["Full", "Sharpe"], "CAGR": fx.loc["Full", "CAGR"], "MaxDD": fx.loc["Full", "MaxDD"],
                          "Alpha (t)": f"{fx.loc['Full','Alpha']:.1%} ({fx.loc['Full','Alpha_t']:.1f})"},
                         {"Model": "Baseline, point-in-time universe (for comparison)", "Sharpe IS": cell("Baseline", "IS", "Sharpe"),
                          "Sharpe OOS": cell("Baseline", "OOS", "Sharpe"), "Sharpe Full": cell("Baseline", "Full", "Sharpe"),
                          "CAGR": cell("Baseline", "Full", "CAGR"), "MaxDD": cell("Baseline", "Full", "MaxDD"),
                          "Alpha (t)": f"{cell('Baseline','Full','Alpha'):.1%} ({cell('Baseline','Full','Alpha_t'):.1f})"}])
for c in ["Sharpe IS", "Sharpe OOS", "Sharpe Full"]:
    fixed_md[c] = fixed_md[c].map("{:.2f}".format)
for c in ["CAGR", "MaxDD"]:
    fixed_md[c] = fixed_md[c].map("{:.1%}".format)

n_trials = pd.read_csv(R / "trials_log.csv").tag.nunique()
md = f"""# Results (all models run so far)

*Generated by `scripts/make_results_md.py` from `results/**/*.csv`; do not edit by hand.*
Point-in-time universe, signals on day t's close, trades at t+1's close, monthly (21-day) rebalance, **0 bps** costs unless noted.
Sharpe/Sortino are on excess returns over T-bills. IS = 2002-2014, OOS = 2015-present, Full = 2002-present. Alpha is annualised CAPM
alpha vs the SFIC benchmark (t-stat in parentheses). Benchmark = 65% SPY / 15% EFA / 20% AGG (VBMFX before AGG).
**All numbers carry survivorship bias** (see CAVEATS.md); the original pitch's ~1.7 Sharpe is not reproduced.

## Main table
{Tf.to_markdown(index=False)}

Bold rows (2b, 4b) are the two models Layer 4 was run on. The spec's own L2 (rows 2a, 2c, v2 spec) and the data-fixed L2 (4a, 4b, v2 fixed:
quality filter + 10% max weight) are both shown; the fixed version is a spec change (see DECISIONS.md).

## Trading-cost sensitivity (Full-sample Sharpe)
{C.to_markdown(index=False)}

## Crash windows (cumulative return, 0 bps)
{CR.to_markdown()}

## Look-ahead diagnostic (NOT a valid backtest)
The universe here is **today's** top-500 by dollar volume applied to every historical date, i.e. it conditions on survival and on
future success. It exists only to show how much of the baseline's result depends on the point-in-time universe; it is **excluded from the table above**.

{fixed_md.to_markdown(index=False)}

## Trial count
`results/trials_log.csv` holds **{n_trials}** distinct trial tags (each distinct model/variant run counts once; costs are not separate trials).
The Deflated Sharpe Ratio must add the original search (288 weightings x 6 portfolio sizes = 1,728 trials) to this number.
"""
Path("docs").mkdir(exist_ok=True); open("docs/RESULTS.md", "w").write(md)
print(md[:3200])
