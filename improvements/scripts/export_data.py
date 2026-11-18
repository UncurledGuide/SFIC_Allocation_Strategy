"""Bundle the exact inputs used by every backtest into shared_data/ (+ zip) for another researcher."""
import shutil, json, pandas as pd, numpy as np
from pathlib import Path
from src import data
CFG = data.CFG
out = Path("shared_data"); shutil.rmtree(out, ignore_errors=True); out.mkdir()
for k in ["adj_close", "close", "high", "volume"]:
    shutil.copy(data.DATA / f"prices_{k}.parquet", out / f"prices_{k}.parquet")
uni = pd.read_pickle(data.DATA / "universe_dollar.pkl")
idx = pd.read_parquet(data.DATA / "prices_close.parquet").index
rows = [(d, t) for d, v in uni.items() for t in v]
pd.DataFrame(rows, columns=["signal_date", "ticker"]).to_csv(out / "universe_by_signal_date.csv", index=False)
pos = {d: idx.get_loc(d) for d in uni}
pd.DataFrame([(d, idx[p + 1] if p + 1 < len(idx) else pd.NaT) for d, p in pos.items()],
             columns=["signal_date", "trade_date"]).to_csv(out / "rebalance_dates.csv", index=False)
sec = data.get_sectors(sorted({t for v in uni.values() for t in v}))
sec.rename("sector").rename_axis("ticker").to_csv(out / "sectors_today.csv")
data.get_benchmark().to_frame().rename_axis("date").to_csv(out / "benchmark_daily_returns.csv")
data.get_tbill().to_frame().rename_axis("date").to_csv(out / "tbill_daily_return.csv")
shutil.copy("config.yaml", out / "config.yaml")
shutil.copy(data.DATA / "sp500_hist_updated.csv", out / "sp500_historical_membership_fja05680.csv")
shutil.copy("results/stage2/stage2_baseline_returns.csv", out / "reference_baseline_daily_returns.csv")
shutil.copy("results/stage3/stage3_returns.csv", out / "reference_stage3_daily_returns.csv")
shutil.make_archive("shared_data", "zip", ".", "shared_data")
print(sum(f.stat().st_size for f in out.iterdir()) / 1e6, "MB;", len(uni), "signal dates;", len(rows), "universe rows")
