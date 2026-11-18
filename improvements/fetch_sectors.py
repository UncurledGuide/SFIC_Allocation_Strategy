import pandas as pd
from src import data
u = pd.read_pickle(data.DATA / "universe_dollar.pkl")
ever = sorted({t for v in u.values() for t in v})
s = data.get_sectors(ever)
print(len(ever), "tickers;", (s == "Unknown").sum(), "Unknown"); print(s.value_counts().to_string())
