# common/
Neutral, tested tools shared by both strategies. No strategy logic (enforced by tests/test_imports.py).
- `data_access.py` TrainingLoader / gated HoldoutLoader (one interface; see PROJECT_SPEC §4)
- `universe.py` point-in-time top-500 by trailing 63-day dollar volume
- `backtest_engine.py` targets → daily returns/positions/trades; t+1 close execution, costs, rounding
- `metrics.py` CAGR, vol, Sharpe, Sortino, MDD, Calmar, hit rate, turnover, FF3+MOM loadings, bootstrap CIs
- `costs.py` cost/sizing from config/costs.yaml
- `codehash.py` SHA-256 over strategy src/ + configs/ + common/ + config/
- `run_logger.py` RunLogger context manager (mandatory), count_variants, write_freeze_record
- `run_holdout.py` gated one-shot holdout runner (do not run during development)
Editing anything here changes both strategies' code hashes — record why in logs/decision_log.md.
