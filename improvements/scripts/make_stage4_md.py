"""Append/refresh the 'Stage 4 (LSEG)' section of docs/RESULTS.md from results/stage4_stats/*."""
import json, re
import pandas as pd
from pathlib import Path
root = Path(__file__).resolve().parents[1]; S = root / "results" / "stage4_stats"
j = json.load(open(S / "stage4_stats.json")); e, b, t, r, d, l4 = j["estimates"], j["bootstrap"], j["trials"], j["L4_rule"], j["drawdown_dates"], j["L4_exposure"]
pct = lambda v: f"{v:.1%}"
rows = ["| Candidate | Sharpe (95% bootstrap CI) | CAGR | Max DD (95% CI) | Deflated Sharpe |", "|:--|:--|--:|:--|--:|"]
for k, v in e.items():
    rows.append(f"| {k} | {v['Sharpe']:.2f} ({v['Sharpe_ci95'][0]:.2f} to {v['Sharpe_ci95'][1]:.2f}) | {pct(v['CAGR'])} | {pct(v['MaxDD'])} ({pct(v['MaxDD_ci95'][0])} to {pct(v['MaxDD_ci95'][1])}) | {v['DSR']:.2f} |")
bt = ["| Difference | Point estimate | 95% CI | CI includes 0? |", "|:--|--:|:--|:--|"]
for k, v in b.items():
    f = (lambda x: f"{x:+.3f}") if k.startswith("Sharpe") else (lambda x: f"{x:+.1%}")
    bt.append(f"| {k} | {f(v['point'])} | {f(v['ci95'][0])} to {f(v['ci95'][1])} | {'yes' if v['ci_includes_0'] else 'no'} |")
dt = ["| Candidate | Peak | Trough | Recovery | Max DD |", "|:--|:--|:--|:--|--:|"] + [f"| {k} | {v['peak']} | {v['trough']} | {v['recovery']} | {pct(v['maxDD'])} |" for k, v in d.items()]
cw = pd.read_csv(S / "crash_windows.csv", index_col=0).map(lambda x: f"{x:.1%}"); cw = cw.reset_index().rename(columns={"index": "Model"})
rb = pd.read_csv(S / "robustness.csv")
for c in ["Sharpe IS", "Sharpe OOS", "Sharpe Full"]: rb[c] = rb[c].map("{:.2f}".format)
rb["CAGR"] = rb["CAGR"].map(pct); rb["MaxDD"] = rb["MaxDD"].map(pct); rb["avg_swaps"] = rb["avg_swaps"].map("{:.1f}".format)
md = lambda df: "\n".join(["| " + " | ".join(map(str, df.columns)) + " |", "|" + "|".join(["---"] * len(df.columns)) + "|"] + ["| " + " | ".join(map(str, x)) + " |" for x in df.values])
sec = f"""<!-- STAGE4-LSEG:start -->
## Stage 4 (LSEG point-in-time data, 2002-2026, 0 bps): three pre-registered candidates
A = live-rule baseline (15 names: 10 by return t-200..t-20, 5 by price / prior 252-day max close, equal weight), B = A + L3, C = B + L4. Data: LSEG, delisted names included (99.8% of index members priced). All rows below come from `scripts/run_stage4_stats.py`.

{chr(10).join(rows)}

Deflated Sharpe uses N = **{t['N_trials']}** trials = {t['distinct_tags_in_log']} distinct tags in `trials_log.csv` + {t['pitch_search_trials']:,} (the original 288 x 6 search). Under the null the expected best Sharpe of N trials is {t['expected_max_sharpe_null_annual']:.2f} (the dispersion of trial Sharpes, {t['trial_sharpe_std_annual']:.2f}, is estimated from our logged trials; see CAVEATS 13).

### Paired block bootstrap ({j['bootstrap_settings']['reps']:,} resamples, {j['bootstrap_settings']['block_days']}-day (3-month) circular blocks, seed {j['bootstrap_settings']['seed']})
{chr(10).join(bt)}

### Pre-set Layer 4 rule: stay if Max DD is -49% or better AND Sharpe falls by <= 0.05 vs B
- Max DD of C = {pct(r['maxDD_C'])} (threshold -49.0%): **{'pass' if r['dd_ok'] else 'fail'}**.
- Sharpe fall C vs B = {r['sharpe_fall_C_vs_B']:.4f} (limit 0.05): **{'pass' if r['sharpe_ok'] else 'fail'}**, with a margin of only {0.05 - r['sharpe_fall_C_vs_B']:.4f}.
- **Point-estimate verdict: {'PASS' if r['point_estimate_pass'] else 'FAIL'}.** The 95% bootstrap CI for the Sharpe difference C - B is {r['CI_C_minus_B_sharpe'][0]:+.3f} to {r['CI_C_minus_B_sharpe'][1]:+.3f}, which **{'includes' if r['CI_includes_0'] else 'excludes'} 0**: the data cannot tell whether L4 costs Sharpe, so the pass is not statistically distinguishable from a fail.

### Max drawdown dates
{chr(10).join(dt)}

C's worst drawdown falls in 2002-2003, inside the first 126 days when L4 has no history and is fully invested (w = 1). From 2008 on, C is far shallower than A and B (see the crash windows).

### Crash windows (cumulative return)
{md(cw)}

### How often L4 is invested less than 100%
L4 held less than 100% in stocks at **{pct(l4['share_of_rebalances_below_100pct'])}** of the {l4['rebalance_dates']} monthly rebalances ({pct(l4['share_of_days_below_100pct'])} of days); mean exposure {l4['mean_exposure']:.2f}, minimum {l4['min_exposure']:.2f}, below 50% at {pct(l4['share_of_rebalances_below_50pct'])} of rebalances. Because the strategy's volatility sits well above the 16% target, L4 is close to a permanent partial cash holding, not a crash switch.

### Robustness (B and C only; 0 bps)
{md(rb)}

Parameters not varied in each row are held at the base values (buffer exit rank 25, max 6 swaps per rebalance, 15 names unless stated); L3 parameters were not rescaled for the size variants.
<!-- STAGE4-LSEG:end -->
"""
p = root / "docs" / "RESULTS.md"; s = p.read_text()
if "<!-- STAGE4-LSEG:start -->" in s:
    s = re.sub(r"<!-- STAGE4-LSEG:start -->.*<!-- STAGE4-LSEG:end -->\n", sec, s, flags=re.S)
else:
    s = s.rstrip() + "\n\n" + sec
p.write_text(s); print("ok", len(sec))
