"""Stock selection / weighting. Each function sees only data through signal date d."""
import numpy as np
import pandas as pd


def baseline_select(d, sig, universe, n=15, mom_share=0.70):
    """70% momentum (180d return), 30% nearness to 52w high. If a stock is on both lists the
    52w-high slot goes to the next-best name on the 52w-high list."""
    elig = [t for t in universe[d] if t in sig["mom180"].columns]
    m = sig["mom180"].loc[d, elig].dropna()
    h = sig["near52"].loc[d, elig].dropna()
    ok = m.index.intersection(h.index)
    m, h = m[ok], h[ok]
    n_m = int(round(n * mom_share))
    mom_picks = list(m.nlargest(n_m).index)
    high_picks = list(h.drop(mom_picks).nlargest(n - n_m).index)
    return mom_picks + high_picks


def equal_weight(tickers):
    return pd.Series(1.0 / len(tickers), index=tickers) if tickers else pd.Series(dtype=float)


# ---------------- v2 layers ----------------
def pct_rank_score(d, sig, universe, extra_ok=None):
    """Layer 1: average of cross-sectional percentile ranks of 6-1 momentum and 52w-high nearness,
    over names in the point-in-time universe with both signals available on d. Returns Series sorted best-first."""
    elig = [t for t in universe[d] if t in sig["mom6_1"].columns]
    df = pd.DataFrame({"m": sig["mom6_1"].loc[d, elig], "h": sig["near52"].loc[d, elig]}).dropna()
    if extra_ok is not None:
        df = df[df.index.isin(extra_ok.loc[d].dropna().index)]
    score = (df["m"].rank(pct=True) + df["h"].rank(pct=True)) / 2
    return score.sort_values(ascending=False, kind="stable")


def _sec(t, sectors):
    s = sectors.get(t, "Unknown")
    return f"UNK_{t}" if s == "Unknown" else s  # unknown-sector names are not grouped together


def greedy_capped(order, sectors, n, cap, keep=()):
    """Walk the ranked list; accept a name unless its sector already holds `cap` names."""
    out = list(keep)
    cnt = {}
    for t in out:
        cnt[_sec(t, sectors)] = cnt.get(_sec(t, sectors), 0) + 1
    for t in order.index:
        if len(out) >= n:
            break
        if t in out:
            continue
        s = _sec(t, sectors)
        if cnt.get(s, 0) >= cap:
            continue
        out.append(t); cnt[s] = cnt.get(s, 0) + 1
    return out


def buffered_select(order, sectors, held, n=15, exit_rank=25, max_swaps=6, cap=4):
    """Layer 3. Sell a holding only if its rank > exit_rank (or it is no longer eligible, or it breaks the sector cap);
    buy replacements in rank order. At most `max_swaps` sells per rebalance (lowest-ranked sold first);
    buys = number of sells, so 1 swap = 1 sold + 1 bought."""
    held = list(held)
    if not held:
        return greedy_capped(order, sectors, n, cap)
    rank = pd.Series(np.arange(1, len(order) + 1), index=order.index)
    r = lambda t: rank.get(t, np.inf)
    forced = {t for t in held if r(t) > exit_rank}
    keepers = [t for t in held if t not in forced]
    by_sec = {}
    for t in sorted(keepers, key=r):
        by_sec.setdefault(_sec(t, sectors), []).append(t)
    for s, ts in by_sec.items():           # sector-cap breaches: drop the worst-ranked extras
        forced |= set(ts[cap:])
    # worst-ranked first, capped. Ties (e.g. several ineligible names at rank=inf) are broken by ticker so the
    # result never depends on set iteration order / PYTHONHASHSEED.
    sold = sorted(forced, key=lambda t: (r(t), t), reverse=True)[:max_swaps]
    keep = [t for t in held if t not in sold]
    return greedy_capped(order, sectors, n, cap, keep=keep)


def inverse_vol_weights(tickers, vol_row):
    v = vol_row.reindex(tickers).replace(0, np.nan)
    w = 1.0 / v
    return w / w.sum()


# ---------------- diagnostics / fixes ----------------
def quality_ok(rets, window=63, min_vol=0.08, max_zero=5):
    """Data-quality filter: ann. 63d vol >= 8% and <= 5 zero-return days in the window. True = ok."""
    vol = rets.rolling(window, min_periods=window).std() * np.sqrt(252)
    zeros = rets.eq(0).astype(int).rolling(window, min_periods=window).sum()
    return (vol >= min_vol) & (zeros <= max_zero)


def cap_weights(w, cap=0.10):
    """Iteratively cap weights at `cap` and redistribute the excess pro rata to uncapped names (sum stays 1)."""
    w = w.copy()
    for _ in range(50):
        over = w > cap + 1e-12
        if not over.any():
            break
        excess = (w[over] - cap).sum()
        w[over] = cap
        free = ~over & (w < cap - 1e-12)
        if not free.any():
            break
        w[free] += excess * w[free] / w[free].sum()
    return w


def baseline_select2(d, sig, universe, n=15, mom_share=0.70, mom_key="mom180", ok=None, sectors=None, cap=None):
    """Baseline two-list picker with optional signal swap (mom_key), data filter `ok` (DataFrame, NaN = excluded)
    and sector cap. Momentum slots first; 52w-high slots take the best names not already picked."""
    elig = [t for t in universe[d] if t in sig[mom_key].columns]
    m = sig[mom_key].loc[d, elig].dropna()
    h = sig["near52"].loc[d, elig].dropna()
    idx = m.index.intersection(h.index)
    if ok is not None:
        idx = idx.intersection(ok.loc[d].dropna().index)
    # stable sort => ties keep universe (alphabetical) order, identical to Series.nlargest(keep='first')
    m, h = m[idx].sort_values(ascending=False, kind='stable'), h[idx].sort_values(ascending=False, kind='stable')
    n_m = int(round(n * mom_share))
    out, cnt = [], {}
    def take(lst, k):
        got = 0
        for t in lst.index:
            if got >= k:
                break
            if t in out:
                continue
            if cap is not None and sectors is not None:
                s = _sec(t, sectors)
                if cnt.get(s, 0) >= cap:
                    continue
                cnt[s] = cnt.get(s, 0) + 1
            out.append(t); got += 1
    take(m, n_m); take(h, n - n_m)
    return out


def baseline_buffered(d, sig, universe, held, n=15, mom_share=0.70, mom_key="mom180", ok=None,
                      sectors=None, cap=None, exit_n=25, max_swaps=6):
    """Layer 3 applied to the two-list baseline. A holding is kept while it is still within the n=25 version of
    either list (top 18 momentum / top 7 52w-high); sells are capped at max_swaps (worst first); buys come from the
    n=15 selection in order of rank-within-its-list. (Spec defines the buffer for a single ranking; this is the
    natural extension to two lists.)"""
    if not held:
        return baseline_select2(d, sig, universe, n, mom_share, mom_key, ok, sectors, cap)
    elig = [t for t in universe[d] if t in sig[mom_key].columns]
    m = sig[mom_key].loc[d, elig].dropna(); h = sig["near52"].loc[d, elig].dropna()
    idx = m.index.intersection(h.index)
    if ok is not None:
        idx = idx.intersection(ok.loc[d].dropna().index)
    rm = m[idx].rank(ascending=False, method="first"); rh = h[idx].rank(ascending=False, method="first")
    n_m, n_h = int(round(n * mom_share)), n - int(round(n * mom_share))
    nx_m = int(round(exit_n * mom_share)); nx_h = exit_n - nx_m
    inf = np.inf
    bad = lambda t: min(rm.get(t, inf) / n_m, rh.get(t, inf) / n_h)
    inside = lambda t: rm.get(t, inf) <= nx_m or rh.get(t, inf) <= nx_h
    forced = {t for t in held if not inside(t)}
    keepers = [t for t in held if t not in forced]
    if cap is not None and sectors is not None:
        by = {}
        for t in sorted(keepers, key=bad):
            by.setdefault(_sec(t, sectors), []).append(t)
        for ts in by.values():
            forced |= set(ts[cap:])
    sold = sorted(forced, key=lambda t: (bad(t), t), reverse=True)[:max_swaps]   # ticker tie-break => deterministic
    keep = [t for t in held if t not in sold]
    cnt = {}
    for t in keep:
        cnt[_sec(t, sectors) if sectors is not None else t] = cnt.get(_sec(t, sectors) if sectors is not None else t, 0) + 1
    out = list(keep)
    pools = [baseline_select2(d, sig, universe, n, mom_share, mom_key, ok, sectors, cap),
             baseline_select2(d, sig, universe, exit_n, mom_share, mom_key, ok, sectors, cap)]
    for pool in pools:
        for t in sorted([x for x in pool if x not in out], key=bad):
            if len(out) >= n:
                break
            if cap is not None and sectors is not None:
                s = _sec(t, sectors)
                if cnt.get(s, 0) >= cap:
                    continue
                cnt[s] = cnt.get(s, 0) + 1
            out.append(t)
    return out
