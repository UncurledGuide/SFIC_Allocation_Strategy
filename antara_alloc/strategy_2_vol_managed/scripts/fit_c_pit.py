"""FIT-ONLY (2000-2014), corrected point-in-time universe: re-estimate c with the FROZEN rule
(1-month RV, mm_vol_match). Same code path as fit_c.py; only the frozen method is computed."""
import json
import pandas as pd
from common.data_access import TrainingLoader
from common.backtest_engine import rebalance_dates
from strategy_2_vol_managed.scripts.common_run import load_cfg, logged_run, SDIR
from strategy_2_vol_managed.src.overlay import realized_variance, estimate_c, exposure
from strategy_2_vol_managed.src.entrypoint import signal_baseline_returns
from strategy_2_vol_managed.src.baseline import baseline_targets

OLD_C = 0.047445238397869696
L = TrainingLoader(max_date="2014-12-31")
cfg = load_cfg("baseline_monthly"); cfg["start"] = "2000-01-01"
res, m = logged_run("baseline_monthly_pit", "fit", cfg, L,
                    purpose="Universe correction: rebuild baseline on fit 2000-2014 with point-in-time S&P 500 universe",
                    hypothesis="Fit-period baseline returns change with the universe, so c must be re-estimated",
                    key_params={"every_n_months": 1, "universe": "pit"}, start="2000-01-01", end="2014-12-31")
fitm = {k: m[k] for k in ("sharpe", "cagr", "ann_vol", "max_drawdown", "annual_one_way_turnover")}
print("baseline fit", fitm)
sd = rebalance_dates(L.trading_days(), "1999-12-01", "2014-12-31")
tg = baseline_targets(L, sd, cfg)
daily = signal_baseline_returns(L, tg, pd.Timestamp("2014-12-31")).loc["2000-01-01":]
rf = L.cash_rate()
rv = realized_variance(daily, tg.index, 1).loc["2000-01-01":"2014-12-31"]
c = estimate_c(daily, rf, rv, "mm_vol_match")
w = exposure(rv, c)
out = {"win1_mm_vol_match_pit": {"c": c, "avg_exposure_fit": float(w.mean()),
                                  "share_months_capped": float((w >= 1).mean()),
                                  "share_below_0.25": float((w < 0.25).mean()),
                                  "rv_median": float(rv.median()), "rv_mean": float(rv.mean())},
       "old_c_old_universe": OLD_C, "c_ratio_new_over_old": c / OLD_C, "baseline_fit_metrics_pit": fitm}
print(json.dumps(out, indent=2))
(SDIR / "logs" / "c_estimates_fit_pit.json").write_text(json.dumps(out, indent=2))
