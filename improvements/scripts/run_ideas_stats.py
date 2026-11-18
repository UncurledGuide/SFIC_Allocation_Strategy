"""Pass/fail table for the pre-registered new-ideas round (LSEG data, 0 bps), plus the Deflated Sharpe of the best idea.
Pass rule (fixed in advance): Sharpe beats B by >= 0.10 in BOTH 2002-2014 and 2015-2026 AND full-sample max DD no worse than B's
(idea 3 is also compared with C).   Run with SFIC_DATA_SOURCE=lseg."""
import json, re
import numpy as np, pandas as pd
from scipy.stats import norm, skew, kurtosis
from src import data

root = data.DATA.parent; OUT = root / "results" / "ideas_stats"; OUT.mkdir(parents=True, exist_ok=True)
LP, ID = root / "results" / "lseg_live_rule", root / "results" / "lseg_ideas"
TD = 252
def load(d, n):
    m = pd.read_csv(d / f"{n}_metrics.csv"); m = m[m.cost_bps == 0].set_index("period")
    return {"Sharpe IS": m.loc["IS", "Sharpe"], "Sharpe OOS": m.loc["OOS", "Sharpe"], "Sharpe Full": m.loc["Full", "Sharpe"], "CAGR": m.loc["Full", "CAGR"],
            "MaxDD": m.loc["Full", "MaxDD"], "Alpha": m.loc["Full", "Alpha"], "avg_swaps": m.loc["Full", "avg_swaps"], "max_swaps_qtr": m.loc["Full", "max_swaps_qtr"]}
ref = {"B (baseline + L3)": load(LP, "live_2b"), "C (B + L4)": load(LP, "live_2b_L4")}
ideas = {"1 Residual momentum": "idea1_resid_mom", "2 Frog-in-the-pan": "idea2_fip", "3 Crash-state rule (vs L4)": "idea3_crash_state", "4 12-1 momentum": "idea4_mom12_1"}
rows = []
for k, n in ideas.items():
    v = load(ID, n); B = ref["B (baseline + L3)"]
    chk = {"dSharpe IS vs B": v["Sharpe IS"] - B["Sharpe IS"], "dSharpe OOS vs B": v["Sharpe OOS"] - B["Sharpe OOS"],
           "MaxDD no worse than B": v["MaxDD"] >= B["MaxDD"] - 1e-12}
    ok = chk["dSharpe IS vs B"] >= 0.10 and chk["dSharpe OOS vs B"] >= 0.10 and chk["MaxDD no worse than B"]
    row = {"idea": k, **v, **chk, "PASS vs B": bool(ok)}
    if k.startswith("3"):
        C = ref["C (B + L4)"]
        row.update({"dSharpe IS vs C": v["Sharpe IS"] - C["Sharpe IS"], "dSharpe OOS vs C": v["Sharpe OOS"] - C["Sharpe OOS"], "MaxDD no worse than C": v["MaxDD"] >= C["MaxDD"] - 1e-12})
        row["PASS vs C"] = bool(row["dSharpe IS vs C"] >= 0.10 and row["dSharpe OOS vs C"] >= 0.10 and row["MaxDD no worse than C"])
    rows.append(row)
T = pd.DataFrame(rows); T.to_csv(OUT / "ideas_table.csv", index=False)
R = pd.DataFrame([{"idea": k, **v} for k, v in ref.items()]); R.to_csv(OUT / "reference_rows.csv", index=False)

# Deflated Sharpe of the best idea (highest full-sample Sharpe), with the NEW trial count
log = pd.read_csv(root / "results" / "trials_log.csv")
tags = log.sort_values("cost_bps").drop_duplicates("tag")
N = tags.tag.nunique() + data.CFG["stats"]["original_search_trials"]
Vd = ((tags.Sharpe / np.sqrt(TD)) ** 2).mean() - (tags.Sharpe / np.sqrt(TD)).mean() ** 2
g = 0.5772156649; sr0 = np.sqrt(Vd) * ((1 - g) * norm.ppf(1 - 1 / N) + g * norm.ppf(1 - 1 / (N * np.e)))
tb = data.get_tbill()
def dsr(name, d):
    r = pd.read_csv(d / f"{name}_returns.csv", index_col=0, parse_dates=True).iloc[:, 0].astype(float)
    x = (r - tb.reindex(r.index).fillna(0.0)).to_numpy(dtype=float); s = x.mean() / x.std(ddof=1)
    return float(norm.cdf((s - sr0) * np.sqrt(len(x) - 1) / np.sqrt(1 - skew(x) * s + (kurtosis(x, fisher=False) - 1) / 4 * s ** 2)))
best = T.loc[T["Sharpe Full"].idxmax(), "idea"]; bn = ideas[best]
out = {"best_idea_by_full_sharpe": best, "DSR_best": dsr(bn, ID), "DSR_B_same_N": dsr("live_2b", LP), "N_trials": int(N), "distinct_tags": int(tags.tag.nunique()),
       "expected_max_sharpe_null_annual": float(sr0 * np.sqrt(TD))}
# sensitivity for idea 1: its signal needs 36 completed months, so it sits in T-bills for 2002 -> compare on 2003+ only (descriptive)
def sh_from(d, n, a):
    r = pd.read_csv(d / f"{n}_returns.csv", index_col=0, parse_dates=True).iloc[:, 0].astype(float).loc[a:]
    x = r - tb.reindex(r.index).fillna(0.0); return float(x.mean() / x.std() * np.sqrt(TD))
out["idea1_vs_B_sharpe_2003_2014"] = {"idea1": sh_from(ID, "idea1_resid_mom", "2003-01-01") if False else None}
r1 = pd.read_csv(ID / "idea1_resid_mom_returns.csv", index_col=0, parse_dates=True).iloc[:, 0].astype(float)
rB = pd.read_csv(LP / "live_2b_returns.csv", index_col=0, parse_dates=True).iloc[:, 0].astype(float)
def shp(r, a, b):
    r = r.loc[a:b]; x = r - tb.reindex(r.index).fillna(0.0); return float(x.mean() / x.std() * np.sqrt(TD))
out["idea1_vs_B_sharpe_2003_2014"] = {"idea1": shp(r1, "2003-01-01", "2014-12-31"), "B": shp(rB, "2003-01-01", "2014-12-31")}
exp3 = pd.read_csv(ID / "idea3_crash_state_exposure.csv", index_col=0, parse_dates=True).iloc[:, 0]
out["idea3_exposure"] = {"share_of_rebalances_at_50pct": float((exp3 < 1).mean()), "mean": float(exp3.mean())}
json.dump(out, open(OUT / "ideas_stats.json", "w"), indent=1)
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
print(R.round(3).to_string(index=False)); print(T.round(3).T.to_string()); print(json.dumps(out, indent=1))
