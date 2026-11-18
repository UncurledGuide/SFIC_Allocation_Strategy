"""Coverage report for the LSEG source (reads local caches only; no API calls).  python -m scripts.lseg_report"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
from src import data


def main(out_dir="results/lseg"):
    L = data.LSEG_DIR
    mem, diag = data.lseg_membership()
    pool = sorted(mem.ric.unique())
    w = data.lseg_build_wide()
    close, vol = w["close"], w["volume"]
    missing = json.load(open(L / "missing.json")) if (L / "missing.json").exists() else {}
    have = set(close.columns)
    asof_end = close.index[-1]
    last_valid = close.apply(lambda s: s.last_valid_index())
    first_valid = close.apply(lambda s: s.first_valid_index())
    caret = {r for r in pool if "^" in r}
    stopped = {r for r in have if last_valid[r] < asof_end - pd.Timedelta(days=30)}          # price history ends >30d before the data end
    R = {}
    R["data_end"] = str(asof_end.date()); R["data_start"] = str(close.index[0].date())
    R["pool_rics"] = len(pool); R["pool_sp500"] = int(mem[mem["index"] == "sp500"].ric.nunique()); R["pool_sp400"] = int(mem[mem["index"] == "sp400"].ric.nunique())
    R["rics_with_prices"] = len(have & set(pool)); R["rics_no_prices"] = len(set(pool) - have)
    R["coverage_pct"] = round(100 * len(have & set(pool)) / len(pool), 1)
    R["caret_rics_in_pool"] = len(caret); R["caret_with_prices"] = len(caret & have); R["caret_no_prices"] = len(caret - have)
    R["priced_rics_whose_history_ended_early(stopped trading)"] = len(stopped & set(pool))
    R["delisted_or_stopped_with_prices"] = len((caret & have) | (stopped & set(pool)))
    R["no_price_reasons"] = pd.Series({r: missing.get(r, "not attempted") for r in set(pool) - have}).value_counts().to_dict()
    # member-month coverage: share of (month-end, member) pairs that have a price on/just before that month-end
    mem = mem.copy(); mem["has_px"] = mem.ric.isin(have)
    # a member counts as covered if its price history spans that month-end (starts by then, ends no more than 10 days before it)
    fv, lv = first_valid.to_dict(), last_valid.to_dict()
    mem["priced_that_month"] = [(r in fv and pd.notna(fv[r]) and fv[r] <= d and lv[r] >= d - pd.Timedelta(days=10)) for r, d in zip(mem.ric, mem.date)]
    cov = {}
    for idx, g in mem.groupby("index"):
        cov[idx] = {"member_months": int(len(g)), "priced_pct": round(100 * g.priced_that_month.mean(), 1)}
    R["member_month_coverage"] = cov
    rows = []
    for y in [2002, 2006, 2010, 2014, 2018, 2022, 2026]:
        d = pd.Timestamp(f"{y}-01-31")
        row = {"year": y}
        for idx in ["sp500", "sp400"]:
            g = mem[(mem["index"] == idx) & (mem.date == d)]
            row[f"{idx}_members"] = len(g); row[f"{idx}_priced"] = int(g.priced_that_month.sum()); row[f"{idx}_pct"] = round(100 * g.priced_that_month.mean(), 1) if len(g) else np.nan
        rows.append(row)
    by_year = pd.DataFrame(rows)
    # compare with the yfinance source on the same S&P 500 dates (stage-1 report)
    yf_cov = pd.read_csv("results/stage1/coverage_by_year.csv")
    by_year = by_year.merge(yf_cov[["year", "pct"]].rename(columns={"pct": "yfinance_sp500_pct"}), on="year", how="left")
    # data quality
    n_obs = close.notna().sum()
    ret = w["adj_close"].pct_change(fill_method=None)
    Q = {"rics_with_<252_rows": int((n_obs < 252).sum()), "median_history_years": round(float(n_obs.median() / 252), 1),
         "non_positive_close_cells": int((close <= 0).sum().sum()),
         "daily_moves_>100pct": int((ret.abs() > 1).sum().sum()), "rics_with_zero_volume_share>20pct": int(((vol.fillna(0) == 0) & close.notna()).sum().div(n_obs.clip(lower=1)).gt(0.2).sum())}
    # cross-check with yfinance for names present in both (match on bare ticker, exchange-listed live names only)
    yf = data.get_prices(source="yfinance")
    cmp = []
    for r in sorted(have):
        if "^" in r:
            continue
        tk = r.split(".")[0].replace("/", "-")
        if tk in yf["adj_close"].columns:
            a, b = ret[r], yf["adj_close"][tk].pct_change(fill_method=None)
            c = pd.concat([a, b], axis=1).dropna()
            if len(c) > 500:
                cmp.append((r, len(c), c.corr().iloc[0, 1], (c.iloc[:, 0] - c.iloc[:, 1]).abs().max()))
    cmp = pd.DataFrame(cmp, columns=["ric", "n", "corr", "maxdiff"])
    Q["yahoo_overlap_names"] = int(len(cmp)); Q["yahoo_adj_return_corr_median"] = round(float(cmp["corr"].median()), 5)
    Q["yahoo_overlap_corr_below_0.99"] = int((cmp["corr"] < 0.99).sum()); Q["yahoo_overlap_corr_below_0.95"] = int((cmp["corr"] < 0.95).sum())
    R["data_quality"] = Q
    R["membership_reconstruction"] = {k: {kk: v[kk] for kk in ("size_min", "size_median", "size_max", "first_month_end", "anomalies")} for k, v in diag.items()}
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    json.dump(R, open(Path(out_dir) / "coverage.json", "w"), indent=1, default=str)
    by_year.to_csv(Path(out_dir) / "coverage_by_year.csv", index=False)
    cmp.sort_values("corr").head(25).to_csv(Path(out_dir) / "worst_yahoo_matches.csv", index=False)
    return R, by_year, cmp


if __name__ == "__main__":
    R, by_year, cmp = main()
    print(json.dumps(R, indent=1, default=str)); print(by_year.to_string(index=False))
