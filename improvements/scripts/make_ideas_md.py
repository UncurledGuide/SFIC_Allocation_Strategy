"""Append/refresh the 'New-ideas round' section of docs/RESULTS.md and the trial-count line, from results/ideas_stats/*."""
import json, re
import pandas as pd
from pathlib import Path
root = Path(__file__).resolve().parents[1]; S = root / "results" / "ideas_stats"
T = pd.read_csv(S / "ideas_table.csv"); R = pd.read_csv(S / "reference_rows.csv"); j = json.load(open(S / "ideas_stats.json"))
pc = lambda v: f"{v:.1%}"; f2 = lambda v: f"{v:.2f}"
def line(name, r, verdict):
    return f"| {name} | {f2(r['Sharpe IS'])} | {f2(r['Sharpe OOS'])} | {f2(r['Sharpe Full'])} | {pc(r['CAGR'])} | {pc(r['MaxDD'])} | {pc(r['Alpha'])} | {r['avg_swaps']:.1f} / {int(r['max_swaps_qtr'])} | {verdict} |"
rows = ["| Model | Sharpe 2002-14 | Sharpe 2015-26 | Sharpe full | CAGR | Max DD | Alpha | Swaps (avg per rebalance / max per quarter) | Pass? |", "|:--|--:|--:|--:|--:|--:|--:|:--|:--|"]
for _, r in R.iterrows(): rows.append(line(r["idea"], r, "reference"))
for _, r in T.iterrows():
    v = ("PASS" if r["PASS vs B"] else "FAIL") + f" vs B (dIS {r['dSharpe IS vs B']:+.2f}, dOOS {r['dSharpe OOS vs B']:+.2f}" + ("" if r["MaxDD no worse than B"] else ", DD worse") + ")"
    if str(r["idea"]).startswith("3"):
        v += f"; {'PASS' if r['PASS vs C'] else 'FAIL'} vs C (dIS {r['dSharpe IS vs C']:+.2f}, dOOS {r['dSharpe OOS vs C']:+.2f}, DD {'no worse' if r['MaxDD no worse than C'] else 'worse'})"
    rows.append(line(r["idea"], r, v))
sec = f"""<!-- IDEAS:start -->
## New-ideas round (pre-registered, each run once, swapped into candidate B; LSEG data, 0 bps)
Pass rule fixed in advance: Sharpe beats B by >= 0.10 in BOTH 2002-2014 and 2015-2026, AND full-sample max DD no worse than B's (idea 3 is also compared with C). No ideas were combined and no variants were tried.

{chr(10).join(rows)}

**Result: no idea passes.** The best by full-sample Sharpe is {j['best_idea_by_full_sharpe']} (that is B plus a rarely-triggered de-risking rule: it holds 50% stocks at only {pc(j['idea3_exposure']['share_of_rebalances_at_50pct'])} of rebalances, mean exposure {j['idea3_exposure']['mean']:.2f}); it matches B's Sharpe, trims the max drawdown modestly, and does not match C's drawdown protection.
- Residual momentum has a data-availability artifact: its signal needs 36 completed months, so the portfolio sits in T-bills until January 2003. Its apparent +0.11 in 2002-2014 comes from missing 2002; from 2003 to 2014 its Sharpe is {j['idea1_vs_B_sharpe_2003_2014']['idea1']:.2f} against B's {j['idea1_vs_B_sharpe_2003_2014']['B']:.2f}. Out of sample it is far worse.
- Frog-in-the-pan and 12-1 momentum are worse than B out of sample (-0.20 and -0.14 Sharpe) and no better in sample.

**Deflated Sharpe, updated for the new trial count:** N = {j['N_trials']} ({j['distinct_tags']} distinct tags + 1,728). Best idea ({j['best_idea_by_full_sharpe']}): **{j['DSR_best']:.2f}**; B at the same N: {j['DSR_B_same_N']:.2f}. Expected best Sharpe among N null trials is {j['expected_max_sharpe_null_annual']:.2f}. Neither is above the 0.95 convention, and the best idea is not distinguishable from B.
<!-- IDEAS:end -->
"""
p = root / "docs" / "RESULTS.md"; s = p.read_text()
s = re.sub(r"<!-- IDEAS:start -->.*<!-- IDEAS:end -->\n", sec, s, flags=re.S) if "<!-- IDEAS:start -->" in s else s.rstrip() + "\n\n" + sec
s = re.sub(r"holds \*\*\d+\*\* distinct trial tags", f"holds **{j['distinct_tags']}** distinct trial tags", s)
p.write_text(s); print("ok")
