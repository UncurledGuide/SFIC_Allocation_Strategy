"""FIT-ONLY (2000-2014): run baseline, compute RV, estimate c for each pre-specified method.
Uses TrainingLoader(max_date='2014-12-31'), which refuses later dates."""
import json
import pandas as pd
from common.data_access import TrainingLoader
from strategy_2_vol_managed.scripts.common_run import load_cfg, logged_run, SDIR
from strategy_2_vol_managed.src.overlay import realized_variance, estimate_c, exposure
from strategy_2_vol_managed.src.entrypoint import signal_baseline_returns

L = TrainingLoader(max_date="2014-12-31")
cfg = load_cfg("baseline_monthly"); cfg["start"] = "2000-01-01"
res, m = logged_run("baseline_monthly", "fit", cfg, L, purpose="Rebuild SFIC baseline on fit 2000-2014",
                    hypothesis="Baseline reproduces a momentum-tilted, high-beta, high-vol portfolio",
                    key_params={"every_n_months": 1}, start="2000-01-01", end="2014-12-31")
print({k: m[k] for k in ("sharpe", "cagr", "ann_vol", "max_drawdown", "annual_one_way_turnover")})
# Signal series exactly as the entrypoint builds it (unscaled, fractional, 0 bps)
from common.backtest_engine import rebalance_dates
from strategy_2_vol_managed.src.baseline import baseline_targets
sd = rebalance_dates(L.trading_days(), "1999-12-01", "2014-12-31")
tg = baseline_targets(L, sd, cfg)
daily = signal_baseline_returns(L, tg, pd.Timestamp("2014-12-31")).loc["2000-01-01":]
rf = L.cash_rate()
out = {}
for win in (1, 3):
    rv = realized_variance(daily, tg.index, win).loc["2000-01-01":"2014-12-31"]
    for meth in ("mm_vol_match", "median_rv"):
        c = estimate_c(daily, rf, rv, meth)
        w = exposure(rv, c)
        out[f"win{win}_{meth}"] = {"c": c, "avg_exposure_fit": float(w.mean()),
                                   "share_months_capped": float((w >= 1).mean()),
                                   "share_below_0.25": float((w < 0.25).mean()),
                                   "rv_median": float(rv.median()), "rv_mean": float(rv.mean())}
print(json.dumps(out, indent=2))
(SDIR / "logs" / "c_estimates_fit.json").write_text(json.dumps(out, indent=2))
