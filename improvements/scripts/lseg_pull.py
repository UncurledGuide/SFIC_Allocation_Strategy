"""Resumable LSEG pull.  python -m scripts.lseg_pull membership|prices|sectors|benchmark|report"""
import sys, json, pandas as pd
from src import data
stage = sys.argv[1] if len(sys.argv) > 1 else "membership"
if stage == "membership":
    m, diag = data.lseg_membership(refresh="--refresh" in sys.argv)
    print(json.dumps(diag, indent=1, default=str))
    ric = sorted(m.ric.unique())
    print("distinct RICs ever in S&P 500 or S&P 400 (month-ends since 2000):", len(ric), "| with '^' (delisted/renamed codes):", sum('^' in r for r in ric))
    print("by index:", m.groupby("index").ric.nunique().to_dict())
elif stage == "prices":
    data.lseg_pull_prices()
    w = data.lseg_build_wide(); print("built wide frames:", {k: v.shape for k, v in w.items()})
elif stage == "extras":
    u = data.get_universe(source="lseg"); rics = sorted(set(u["sp500_ever"]) | set(u["sp400_ever"]))
    s = data.lseg_get_sectors(rics); print("sectors:", len(s), "| Unknown:", int((s == "Unknown").sum()))
    b = data.lseg_get_benchmark(); print("benchmark:", b.index[0].date(), "->", b.index[-1].date(), len(b))
    t = data.lseg_get_tbill(); print("tbill:", t.index[0].date(), "->", t.index[-1].date(), len(t))
