import json, pandas as pd, yaml
from src import data, universe
CFG = data.CFG
px = data.get_prices()
pool = data.get_universe_pool()
req = json.load(open(data.DATA / "requested_tickers.json"))
dates = universe.rebalance_dates(px["close"].index, CFG["data"]["backtest_start"], CFG["trading"]["rebalance_days"])
u = universe.build_universe(px["close"], px["volume"], dates, **{k: CFG["universe"][k] for k in ["window" if False else "adv_window"]} if False else dict(size=CFG["universe"]["size"], window=CFG["universe"]["adv_window"], min_history=CFG["universe"]["min_history"], volume_type=CFG["universe"]["volume_type"]))
rep = universe.coverage_report(req, px["close"], u)
print(json.dumps(rep, indent=1))
sizes = pd.Series({d: len(v) for d, v in u.items()})
print("universe size min/median/max:", sizes.min(), sizes.median(), sizes.max())
print("first date", dates[0].date(), "last", dates[-1].date(), "n rebalances", len(dates))
# coverage over time: how many of the hist-500 names at each year-start have data
hist = pd.read_csv(data.DATA / "sp500_hist_updated.csv"); hist["date"] = pd.to_datetime(hist["date"])
got = set(px["close"].columns); rows = []
for y in range(2002, 2027, 4):
    r = hist[hist.date <= f"{y}-01-02"].iloc[-1]
    m = {t.replace(".", "-") for t in r.tickers.split(",")}
    rows.append((y, len(m), len(m & got), round(100 * len(m & got) / len(m), 1)))
cov = pd.DataFrame(rows, columns=["year", "sp500_members", "with_data", "pct"])
print(cov.to_string(index=False))
cov.to_csv(data.DATA.parent / "results" / "coverage_by_year.csv", index=False)
json.dump({**rep}, open(data.DATA.parent / "results" / "coverage.json", "w"), indent=1)
pd.to_pickle(u, data.DATA / "universe_dollar.pkl")
