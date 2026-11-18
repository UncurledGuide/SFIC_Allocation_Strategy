"""Stage 4 statistics on three pre-registered candidates (LSEG point-in-time data, 2002-2026, 0 bps):
 A = live-rule baseline, B = A + L3, C = B + L4.   Run with SFIC_DATA_SOURCE=lseg.
Outputs results/stage4_stats/*.csv|json and prints the tables."""
import json
import numpy as np, pandas as pd
from scipy.stats import norm, skew, kurtosis
from src import data, metrics

OUT = data.DATA.parent / "results" / "stage4_stats"; OUT.mkdir(parents=True, exist_ok=True)
R = data.DATA.parent / "results" / "lseg_live_rule"
CAND = {"A: live baseline": "live_base", "B: A + L3": "live_2b", "C: B + L4": "live_2b_L4"}
TD, BLOCK, REPS, SEED = 252, 63, 10_000, data.CFG["stats"]["seed"]
tb, bench = data.get_tbill(), data.get_benchmark()
ret = {k: pd.read_csv(R / f"{v}_returns.csv", index_col=0, parse_dates=True).iloc[:, 0] for k, v in CAND.items()}
idx = ret["A: live baseline"].index
for r in ret.values():
    idx = idx.intersection(r.index)
ret = {k: r.loc[idx] for k, r in ret.items()}
rf = tb.reindex(idx).fillna(0.0)
sharpe = lambda x: x.mean() / x.std() * np.sqrt(TD)

# ---------- point estimates ----------
est = {k: {"Sharpe": float(sharpe(r - rf)), "CAGR": float((1 + r).prod() ** (TD / len(r)) - 1), "MaxDD": metrics.max_drawdown(r)} for k, r in ret.items()}

# ---------- Deflated Sharpe ----------
log = pd.read_csv(data.DATA.parent / "results" / "trials_log.csv")
tags = log.sort_values("cost_bps").drop_duplicates("tag")          # one Sharpe per distinct tag (lowest cost logged)
n_tags, N = tags.tag.nunique(), tags.tag.nunique() + data.CFG["stats"]["original_search_trials"]
V = float(((tags.Sharpe / np.sqrt(TD)) ** 2).mean() - (tags.Sharpe / np.sqrt(TD)).mean() ** 2)   # variance of trial Sharpes (daily units)
g = 0.5772156649
sr0 = np.sqrt(V) * ((1 - g) * norm.ppf(1 - 1 / N) + g * norm.ppf(1 - 1 / (N * np.e)))     # expected max Sharpe under the null (daily)
def dsr(x):
    s = x.mean() / x.std(); T = len(x)
    return float(norm.cdf((s - sr0) * np.sqrt(T - 1) / np.sqrt(1 - skew(x) * s + (kurtosis(x, fisher=False) - 1) / 4 * s ** 2)))
for k, r in ret.items():
    est[k]["DSR"] = dsr((r - rf).to_numpy(dtype=float))
meta = {"distinct_tags_in_log": int(n_tags), "pitch_search_trials": data.CFG["stats"]["original_search_trials"], "N_trials": int(N),
        "trial_sharpe_std_annual": float(np.sqrt(V) * np.sqrt(TD)), "expected_max_sharpe_null_annual": float(sr0 * np.sqrt(TD)), "T_days": len(idx)}

# ---------- paired circular block bootstrap ----------
rng = np.random.default_rng(SEED)
T = len(idx); nb = int(np.ceil(T / BLOCK))
X = {k: (r - rf).to_numpy(dtype=float) for k, r in ret.items()}; Rr = {k: r.to_numpy(dtype=float) for k, r in ret.items()}
ks = list(ret)
sh = {k: [] for k in ks}; dd = {k: [] for k in ks}
for c0 in range(0, REPS, 500):
    m = min(500, REPS - c0)
    st = rng.integers(0, T, size=(m, nb))
    ix = ((st[:, :, None] + np.arange(BLOCK)[None, None, :]) % T).reshape(m, -1)[:, :T]
    for k in ks:
        x = X[k][ix]; sh[k].append(x.mean(1) / x.std(1, ddof=1) * np.sqrt(TD))
        eq = np.cumprod(1 + Rr[k][ix], axis=1); dd[k].append((eq / np.maximum.accumulate(eq, axis=1) - 1).min(1))
sh = {k: np.concatenate(v) for k, v in sh.items()}; dd = {k: np.concatenate(v) for k, v in dd.items()}
A, B, C = ks
ci = lambda a: [float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))]
boot = {}
for lab, (u, v) in {"B - A": (B, A), "C - A": (C, A), "C - B": (C, B)}.items():
    d = sh[u] - sh[v]; boot[f"Sharpe diff {lab}"] = {"point": est[u]["Sharpe"] - est[v]["Sharpe"], "ci95": ci(d), "ci_includes_0": bool(ci(d)[0] <= 0 <= ci(d)[1]), "p_diff>0": float((d > 0).mean())}
for lab, (u, v) in {"C - A": (C, A), "C - B": (C, B)}.items():
    d = dd[u] - dd[v]; boot[f"MaxDD diff {lab}"] = {"point": est[u]["MaxDD"] - est[v]["MaxDD"], "ci95": ci(d), "ci_includes_0": bool(ci(d)[0] <= 0 <= ci(d)[1])}
for k in ks:
    est[k]["Sharpe_ci95"] = ci(sh[k]); est[k]["MaxDD_ci95"] = ci(dd[k])

# ---------- pre-set L4 rule ----------
dS = est[B]["Sharpe"] - est[C]["Sharpe"]
rule = {"maxDD_C": est[C]["MaxDD"], "maxDD_threshold": -0.49, "dd_ok": est[C]["MaxDD"] >= -0.49,
        "sharpe_fall_C_vs_B": dS, "sharpe_ok": dS <= 0.05 + 1e-12,
        "point_estimate_pass": bool(est[C]["MaxDD"] >= -0.49 and dS <= 0.05 + 1e-12),
        "CI_C_minus_B_sharpe": boot["Sharpe diff C - B"]["ci95"], "CI_includes_0": boot["Sharpe diff C - B"]["ci_includes_0"]}

# ---------- drawdown dates ----------
def dd_dates(r):
    eq = (1 + r).cumprod(); peak = eq.cummax(); d = eq / peak - 1
    tro = d.idxmin(); pk = eq.loc[:tro].idxmax()
    after = eq.loc[tro:]; rec = after[after >= eq.loc[pk]]
    return {"peak": str(pk.date()), "trough": str(tro.date()), "recovery": str(rec.index[0].date()) if len(rec) else "not recovered", "maxDD": float(d.min())}
dates = {k: dd_dates(r) for k, r in ret.items()}

# ---------- crash windows ----------
W = {"2002 (dot-com tail)": ("2002-01-01", "2002-10-09"), "2008-09 to 2009-03": ("2008-09-01", "2009-03-31"),
     "2009-03 to 2009-05 (momentum crash)": ("2009-03-01", "2009-05-31"), "2020-02 to 2020-04": ("2020-02-01", "2020-04-30"), "2022": ("2022-01-01", "2022-12-31")}
cw = {k: {w: float((1 + r.loc[a:b]).prod() - 1) for w, (a, b) in W.items()} for k, r in ret.items()}
cw["Benchmark"] = {w: float((1 + bench.loc[a:b]).prod() - 1) for w, (a, b) in W.items()}
CW = pd.DataFrame(cw).T

# ---------- L4 exposure ----------
ex = pd.read_csv(R / "live_2b_L4_exposure.csv", index_col=0, parse_dates=True).iloc[:, 0]
daily_w = ex.reindex(idx, method="ffill").fillna(1.0)
l4 = {"rebalance_dates": int(len(ex)), "share_of_rebalances_below_100pct": float((ex < 1).mean()), "share_of_days_below_100pct": float((daily_w < 1).mean()),
      "mean_exposure": float(ex.mean()), "min_exposure": float(ex.min()), "share_of_rebalances_below_50pct": float((ex < 0.5).mean())}

# ---------- robustness (B and C only) ----------
rob = []
for m, base in (("B", "live_2b"), ("C", "live_2b_L4")):
    rows = [("base (n=15, buffer 25, monthly)", pd.read_csv(R / f"{base}_metrics.csv"))]
    for v, lab in (("buf30", "buffer 30"), ("n10", "size 10"), ("n20", "size 20"), ("rb2m", "2-month rebalance")):
        rows.append((lab, pd.read_csv(data.DATA.parent / "results" / "lseg_robustness" / f"rob_{m}_{v}_metrics.csv")))
    for lab, d in rows:
        d = d[d.cost_bps == 0].set_index("period")
        rob.append({"model": m, "variant": lab, "Sharpe IS": d.loc["IS", "Sharpe"], "Sharpe OOS": d.loc["OOS", "Sharpe"], "Sharpe Full": d.loc["Full", "Sharpe"],
                    "CAGR": d.loc["Full", "CAGR"], "MaxDD": d.loc["Full", "MaxDD"], "avg_swaps": d.loc["Full", "avg_swaps"], "max_swaps_qtr": d.loc["Full", "max_swaps_qtr"]})
ROB = pd.DataFrame(rob)

json.dump({"estimates": est, "trials": meta, "bootstrap": boot, "L4_rule": rule, "drawdown_dates": dates, "L4_exposure": l4,
           "bootstrap_settings": {"block_days": BLOCK, "reps": REPS, "seed": SEED, "type": "paired circular block bootstrap of daily returns"}},
          open(OUT / "stage4_stats.json", "w"), indent=1, default=float)
CW.to_csv(OUT / "crash_windows.csv"); ROB.to_csv(OUT / "robustness.csv", index=False)
pd.set_option("display.width", 220)
print(json.dumps({"estimates": est, "trials": meta}, indent=1, default=float)); print(json.dumps(boot, indent=1, default=float))
print(json.dumps(rule, indent=1, default=float)); print(json.dumps(dates, indent=1)); print(json.dumps(l4, indent=1))
print((CW * 100).round(1).to_string()); print(ROB.round(3).to_string(index=False))
