"""Build the point-in-time top-500 dollar-volume universe from LSEG data (same rule as Stage 1) -> data/universe_dollar_lseg.pkl"""
import pandas as pd
from src import data, universe
px = data.lseg_get_prices(); C = data.CFG
dates = universe.rebalance_dates(px["close"].index, C["data"]["backtest_start"], C["trading"]["rebalance_days"])
u = universe.build_universe(px["close"], px["volume"], dates, size=C["universe"]["size"], window=C["universe"]["adv_window"],
                            min_history=C["universe"]["min_history"], volume_type=C["universe"]["volume_type"])
pd.to_pickle(u, data.DATA / "universe_dollar_lseg.pkl")
ever = {t for v in u.values() for t in v}
print(len(u), "rebalance dates", min(u), max(u), "| distinct tickers ever in universe:", len(ever), "| with '^':", sum("^" in t for t in ever))
