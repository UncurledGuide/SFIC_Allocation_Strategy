# strategy_2_vol_managed
Volatility-managed overlay (Moreira & Muir) on the existing SFIC baseline (70% 6-month momentum / 30% 52-week-high, 15 stocks EW): exposure = min(1, c / RV_{t-1}) from the base portfolio's prior-month daily realized variance, rest in cash; c estimated without look-ahead; monthly.

Start here: `logs/STATUS.md` → `../docs/PROJECT_SPEC.md`.
Layout: `src/` code (entrypoint.py), `configs/` YAML configs, `runs/` one folder per logged run,
`logs/` STATUS, run_registry.csv, preregistration.md, `outputs/frozen/` final frozen outputs.
