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
    sold = sorted(forced, key=r, reverse=True)[:max_swaps]   # worst-ranked first, capped
    keep = [t for t in held if t not in sold]
    return greedy_capped(order, sectors, n, cap, keep=keep)


def inverse_vol_weights(tickers, vol_row):
    v = vol_row.reindex(tickers).replace(0, np.nan)
    w = 1.0 / v
    return w / w.sum()
