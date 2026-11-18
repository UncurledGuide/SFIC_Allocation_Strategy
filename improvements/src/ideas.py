"""Pre-registered 'new ideas' round (signals swapped into candidate B). Everything at row d uses data with date <= d only.
 - mom_resid : residual momentum (36 completed months of stock excess returns on SPY excess returns; sum of the residuals over
               months t-12..t-1 divided by the residuals' std over the 36 months). t = the month containing d; only completed months.
 - mom_fip   : 'frog in the pan'. Top 30 by live-rule momentum, re-ordered by ID = sign(12-1 return) * (%neg days - %pos days)
               over the 12-1 window (t-252 .. t-21); lowest ID first. The 10 momentum slots then take the 10 lowest-ID names.
Both are returned as ranking scores (higher = better) on the rebalance dates only."""
import numpy as np
import pandas as pd
from . import data


def _monthly(adj):
    m = adj.resample("ME").last()
    # a month with no observation for a name stays NaN (no ffill: delisted names drop out)
    return m.pct_change(fill_method=None)


def residual_momentum(ctx, window=36, skip_months=12):
    adj = ctx.px["adj_close"]
    rm = _monthly(adj)
    spy = pd.read_parquet(data.LSEG_DIR / "benchmark_components.parquet")["SPY"].astype(float)
    spy_m = (1 + spy.dropna()).resample("ME").prod() - 1
    y = pd.read_parquet(data.LSEG_DIR / "tbill_US3MT.parquet")["v"]            # raw cache starts 2000 (ctx.tbill is cut at 2002)
    rf_d = (y.shift(1).ffill() / 100.0 / 252.0).astype(float)
    rf_m = (1 + rf_d).resample("ME").prod() - 1
    ex = rm.sub(rf_m.reindex(rm.index), axis=0)
    x = (spy_m - rf_m.reindex(spy_m.index)).reindex(rm.index)
    out = pd.DataFrame(np.nan, index=rm.index, columns=rm.columns)
    for k in range(window, len(rm)):
        Y = ex.iloc[k - window + 1:k + 1]                     # 36 completed months ending at month k
        X = x.iloc[k - window + 1:k + 1]
        if X.isna().any():
            continue
        ok = Y.notna().all()
        if not ok.any():
            continue
        Yo = Y.loc[:, ok]; xc = X - X.mean()
        beta = (Yo.sub(Yo.mean()).mul(xc, axis=0)).sum() / (xc ** 2).sum()
        alpha = Yo.mean() - beta * X.mean()
        e = Yo.sub(alpha, axis=1).sub(np.outer(X.values, beta.values))
        out.loc[rm.index[k], ok[ok].index] = (e.iloc[-skip_months:].sum() / e.std(ddof=1)).values
    res = {}
    for d in ctx.dates:
        prior = out.index[out.index < pd.Timestamp(d).to_period("M").to_timestamp()]   # completed months strictly before d's month
        res[d] = out.loc[prior[-1]] if len(prior) else pd.Series(np.nan, index=out.columns)
    return pd.DataFrame(res).T.reindex(columns=adj.columns)


def frog_in_the_pan(ctx, top_k=30, lo=252, hi=21):
    adj, rets = ctx.px["adj_close"], ctx.rets
    r121 = adj.shift(hi) / adj.shift(lo) - 1
    n = lo - hi                                                # days from t-lo+1 .. t-hi  (231)
    valid = rets.notna()
    neg = (rets < 0).astype(float).where(valid).rolling(n, min_periods=int(0.9 * n)).mean().shift(hi)
    pos = (rets > 0).astype(float).where(valid).rolling(n, min_periods=int(0.9 * n)).mean().shift(hi)
    ID = np.sign(r121) * (neg - pos)
    mom = ctx.sig["mom_live"]; hi_sig = ctx.sig["near52_live"]
    rows = {}
    for d in ctx.dates:
        elig = [t for t in ctx.uni[d] if t in mom.columns]
        m = mom.loc[d, elig].dropna(); h = hi_sig.loc[d, elig].dropna(); i_ = ID.loc[d, elig].dropna()
        idx = m.index.intersection(h.index).intersection(i_.index)
        m = m[idx].sort_values(ascending=False, kind="stable")
        top = m.index[:top_k]
        order = i_[top].sort_values(kind="stable").index                    # lowest ID first
        score = m.copy()                                                    # everyone else keeps their momentum value
        score.loc[order] = 1000.0 - np.arange(len(order))                   # tier 1 sits above every raw return
        rows[d] = score
    return pd.DataFrame(rows).T.reindex(columns=adj.columns)


def build(key, ctx):
    return {"mom_resid": residual_momentum, "mom_fip": frog_in_the_pan}[key](ctx)
