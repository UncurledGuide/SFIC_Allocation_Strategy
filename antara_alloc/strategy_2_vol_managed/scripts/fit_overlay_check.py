"""FIT-ONLY sanity check of the primary overlay on 2000-2014 (design diagnostics, not selection)."""
from common.data_access import TrainingLoader
from strategy_2_vol_managed.scripts.common_run import load_cfg, logged_run
L = TrainingLoader(max_date="2014-12-31")
cfg = load_cfg("primary"); cfg["start"] = "2000-01-01"
_, m = logged_run("primary", "fit", cfg, L, purpose="Fit-period diagnostics of primary overlay",
                  hypothesis="Overlay lowers vol and MDD vs baseline on fit (c fitted here, so in-sample)",
                  key_params={"rv_window_months": 1, "c": cfg["overlay"]["c"]}, start="2000-01-01", end="2014-12-31")
print({k: m[k] for k in ("sharpe", "sortino", "cagr", "ann_vol", "max_drawdown", "avg_exposure", "annual_one_way_turnover")})
