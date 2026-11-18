"""Check that results from configs/*.yaml are bit-identical to the original diagnostics run."""
import pandas as pd, numpy as np
ref = pd.read_csv("results/diagnostics/diagnostics_returns.csv", index_col=0, parse_dates=True, float_precision="round_trip")
refm = pd.read_csv("results/diagnostics/diagnostics_all.csv")
MAP = {"baseline": "Baseline", "2b_baseline_L3": "2b Base+L3", "4b_baseline_L2_L3_fixed": "4b Base+L2+L3 (fixed)"}
ok = True
for name, old in MAP.items():
    new = pd.read_csv(f"results/diagnostics/{name}_returns.csv", index_col=0, parse_dates=True, float_precision="round_trip").iloc[:, 0]
    same_idx = new.index.equals(ref[old].index)
    maxdiff = float((new - ref[old]).abs().max())
    exact = same_idx and bool((new.values == ref[old].values).all())
    m = pd.read_csv(f"results/diagnostics/{name}_metrics.csv"); m = m[m.cost_bps == 0].set_index("period")
    r = refm[refm.model == old].set_index("period")
    cols = [c for c in r.columns if c in m.columns and c != "model"]
    mdiff = float((m.loc[r.index, cols].astype(float) - r[cols].astype(float)).abs().max().max())
    print(f"{name:26s} days={len(new)}  index_equal={same_idx}  returns_max_abs_diff={maxdiff:.3e}  bit_identical={exact}  metrics_max_abs_diff={mdiff:.3e}")
    ok &= exact and mdiff < 1e-12
print("ALL IDENTICAL" if ok else "MISMATCH")
