"""Deduplicate results/trials_log.csv by trial tag (one row per tag x cost_bps, latest wins).
Early runs (stage 2/3) used ad-hoc tags for models that were later re-run under the diagnostics tags and verified
bit-identical; they are renamed to the canonical tag first so each distinct model counts as ONE trial."""
import pandas as pd
CANON = {"baseline_70_30": "diag:Baseline", "Baseline": "diag:Baseline",
         "+L1": "diag:1c Rank score alone (L1)", "+L1+L2": "diag:v2 +L1+L2 (spec)",
         "+L1+L2+L3": "diag:v2 +L1+L2+L3 (spec)"}
f = "results/trials_log.csv"
d = pd.read_csv(f)
n0, t0 = len(d), d.tag.nunique()
d["tag"] = d.tag.replace(CANON)
d = d.sort_values("timestamp").drop_duplicates(["tag", "cost_bps"], keep="last").sort_values("timestamp")
d.to_csv(f, index=False)
print(f"rows {n0} -> {len(d)}; distinct tags {t0} -> {d.tag.nunique()} (= distinct models; trial count for the Deflated Sharpe)")
