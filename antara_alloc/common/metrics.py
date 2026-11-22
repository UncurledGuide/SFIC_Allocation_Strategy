"""Performance metrics on daily simple returns. Neutral; no strategy logic.

All functions take a pd.Series of daily returns indexed by date (and an aligned daily RF series
where relevant). Annualization uses 252 trading days.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

ANN = 252


def _align(r: pd.Series, rf: pd.Series | None):
    r = r.dropna()
    if rf is None:
        return r, pd.Series(0.0, index=r.index)
    return r, rf.reindex(r.index).fillna(0.0)


def cagr(r: pd.Series) -> float:
    r = r.dropna()
    if len(r) == 0:
        return np.nan
    return float((1 + r).prod() ** (ANN / len(r)) - 1)


def ann_vol(r: pd.Series) -> float:
    return float(r.dropna().std(ddof=1) * np.sqrt(ANN))


def sharpe(r: pd.Series, rf: pd.Series | None = None) -> float:
    r, rf = _align(r, rf)
    ex = r - rf
    sd = ex.std(ddof=1)
    return float(ex.mean() / sd * np.sqrt(ANN)) if sd > 0 else np.nan


def sortino(r: pd.Series, rf: pd.Series | None = None) -> float:
    r, rf = _align(r, rf)
    ex = r - rf
    dd = np.sqrt((np.minimum(ex, 0) ** 2).mean())
    return float(ex.mean() / dd * np.sqrt(ANN)) if dd > 0 else np.nan


def drawdown(r: pd.Series) -> pd.Series:
    eq = (1 + r.dropna()).cumprod()
    return eq / eq.cummax() - 1


def max_drawdown(r: pd.Series) -> float:
    dd = drawdown(r)
    return float(dd.min()) if len(dd) else np.nan


def calmar(r: pd.Series) -> float:
    mdd = max_drawdown(r)
    return float(cagr(r) / abs(mdd)) if mdd < 0 else np.nan


def monthly_returns(r: pd.Series) -> pd.Series:
    r = r.dropna()
    return (1 + r).groupby(r.index.to_period("M")).prod() - 1


def hit_rate(r: pd.Series, benchmark: pd.Series | None = None) -> float:
    """Share of months with positive return (or beating the benchmark if given)."""
    m = monthly_returns(r)
    if benchmark is not None:
        b = monthly_returns(benchmark.reindex(r.index))
        m = (m - b.reindex(m.index)).dropna()
    return float((m > 0).mean()) if len(m) else np.nan


def turnover_stats(daily_returns: pd.DataFrame) -> dict:
    """From engine output: per-rebalance and annualized one-way turnover."""
    t = daily_returns["turnover"]
    years = len(t) / ANN
    reb = t[t > 0]
    return {"avg_one_way_turnover_per_rebalance": float(reb.mean() / 2) if len(reb) else 0.0,
            "annual_one_way_turnover": float(t.sum() / 2 / years) if years else np.nan}


def factor_loadings(r: pd.Series, factors: pd.DataFrame, cols=("MKT_RF", "SMB", "HML", "MOM"),
                    hac_lags: int = 5) -> dict:
    """OLS of excess returns on FF3 + momentum (daily), Newey-West SEs.
    factors: DataFrame with 'date', RF and factor columns (decimals)."""
    import statsmodels.api as sm
    f = factors.set_index("date") if "date" in factors else factors
    df = pd.concat([r.rename("r"), f], axis=1, join="inner").dropna(subset=["r", "RF", *cols])
    y = df["r"] - df["RF"]
    X = sm.add_constant(df[list(cols)])
    res = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": hac_lags})
    out = {"alpha_ann": float(res.params["const"] * ANN), "alpha_t": float(res.tvalues["const"]),
           "r2": float(res.rsquared), "n_obs": int(res.nobs)}
    for c in cols:
        out[f"beta_{c}"] = float(res.params[c])
        out[f"t_{c}"] = float(res.tvalues[c])
    return out


def _block_indices(n: int, block: int, rng: np.random.Generator) -> np.ndarray:
    """Circular block bootstrap indices of length n."""
    nb = int(np.ceil(n / block))
    starts = rng.integers(0, n, nb)
    idx = (starts[:, None] + np.arange(block)[None, :]).ravel()[:n] % n
    return idx


def bootstrap_sharpe_ci(r: pd.Series, rf: pd.Series | None = None, n_boot: int = 2000,
                        block: int = 21, alpha: float = 0.05, seed: int = 0) -> dict:
    r, rf = _align(r, rf)
    ex = (r - rf).to_numpy()
    rng = np.random.default_rng(seed)
    s = np.empty(n_boot)
    for b in range(n_boot):
        x = ex[_block_indices(len(ex), block, rng)]
        sd = x.std(ddof=1)
        s[b] = x.mean() / sd * np.sqrt(ANN) if sd > 0 else np.nan
    lo, hi = np.nanquantile(s, [alpha / 2, 1 - alpha / 2])
    return {"sharpe": sharpe(r, rf), "ci_low": float(lo), "ci_high": float(hi), "n_boot": n_boot, "block": block}


def bootstrap_sharpe_diff_ci(r1: pd.Series, r2: pd.Series, rf: pd.Series | None = None,
                             n_boot: int = 2000, block: int = 21, alpha: float = 0.05, seed: int = 0) -> dict:
    """Paired circular block bootstrap of Sharpe(r1) - Sharpe(r2) on common dates."""
    df = pd.concat([r1.rename("a"), r2.rename("b")], axis=1, join="inner").dropna()
    rfa = rf.reindex(df.index).fillna(0.0).to_numpy() if rf is not None else 0.0
    a, b = df["a"].to_numpy() - rfa, df["b"].to_numpy() - rfa
    rng = np.random.default_rng(seed)
    d = np.empty(n_boot)
    for k in range(n_boot):
        ix = _block_indices(len(a), block, rng)
        xa, xb = a[ix], b[ix]
        d[k] = (xa.mean() / xa.std(ddof=1) - xb.mean() / xb.std(ddof=1)) * np.sqrt(ANN)
    lo, hi = np.nanquantile(d, [alpha / 2, 1 - alpha / 2])
    point = (a.mean() / a.std(ddof=1) - b.mean() / b.std(ddof=1)) * np.sqrt(ANN)
    return {"sharpe_diff": float(point), "ci_low": float(lo), "ci_high": float(hi),
            "p_le_0": float(np.mean(d <= 0)), "n_boot": n_boot, "block": block}


def summary(r: pd.Series, rf: pd.Series | None = None, benchmark: pd.Series | None = None,
            factors: pd.DataFrame | None = None, daily_returns: pd.DataFrame | None = None,
            start=None, end=None) -> dict:
    """Headline metrics dict. start/end restrict the scoring window (e.g. holdout perf_start)."""
    r = r.loc[start:end].dropna()
    out = {"start": str(r.index.min().date()) if len(r) else None,
           "end": str(r.index.max().date()) if len(r) else None, "n_days": int(len(r)),
           "cagr": cagr(r), "ann_vol": ann_vol(r), "sharpe": sharpe(r, rf), "sortino": sortino(r, rf),
           "max_drawdown": max_drawdown(r), "calmar": calmar(r), "hit_rate_monthly": hit_rate(r)}
    if benchmark is not None:
        b = benchmark.reindex(r.index)
        out["benchmark_cagr"] = cagr(b)
        out["benchmark_sharpe"] = sharpe(b, rf)
        out["hit_rate_vs_benchmark_monthly"] = hit_rate(r, b)
        ex = (r - b).dropna()
        out["tracking_error"] = ann_vol(ex)
        out["information_ratio"] = float(ex.mean() / ex.std() * np.sqrt(ANN)) if ex.std() > 0 else np.nan
    if daily_returns is not None:
        dr = daily_returns.set_index("date").loc[start:end].reset_index()
        out.update(turnover_stats(dr))
    if factors is not None:
        try:
            out["factor_loadings"] = factor_loadings(r, factors)
        except Exception as e:  # noqa
            out["factor_loadings"] = {"error": repr(e)}
    return out
