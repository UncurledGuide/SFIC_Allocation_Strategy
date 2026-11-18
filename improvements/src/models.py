"""Build a trading rule from a model YAML. Every v2 layer is a switch in the config, so one runner covers all models.

model YAML keys (layered over config.yaml):
  name, tag, stage
  selection: {type: baseline_two_list|rank_score, n_stocks, mom_share, mom_signal}
  sector_cap: int|null          (Layer 2)
  quality_filter: bool          (data-quality exclusion, diagnostics fix)
  weighting: equal|inverse_vol  (Layer 2)
  weight_cap: float|null        (diagnostics fix, spec change)
  buffer: {enabled, exit_rank, max_swaps}   (Layer 3)
"""
from types import SimpleNamespace
import copy
import pandas as pd
import yaml
from . import data, signals, portfolio as P


def deep_update(a, b):
    a = copy.deepcopy(a)
    for k, v in b.items():
        a[k] = deep_update(a[k], v) if isinstance(v, dict) and isinstance(a.get(k), dict) else v
    return a


def load_model_cfg(path):
    return deep_update(data.CFG, yaml.safe_load(open(path)))


def build_context(cfg):
    px = data.get_prices()
    uni = pd.read_pickle(data.DATA / ("universe_dollar_lseg.pkl" if data._use_lseg(None) else "universe_dollar.pkl"))
    rets = px["adj_close"].pct_change(fill_method=None)
    vol = rets.rolling(cfg["portfolio"]["vol_window"], min_periods=cfg["portfolio"]["vol_window"]).std()
    return SimpleNamespace(
        px=px, uni=uni, dates=list(uni), rets=rets, vol=vol, volc=vol.where(P.quality_ok(rets)),
        sig=signals.compute_all(px, cfg), bench=data.get_benchmark(), tbill=data.get_tbill(),
        sectors=data.get_sectors(sorted({t for v in uni.values() for t in v})))


def build_target_fn(cfg, ctx):
    sel, buf = cfg["selection"], cfg.get("buffer", {"enabled": False})
    cap, qf, wt, wcap = cfg.get("sector_cap"), cfg.get("quality_filter", False), cfg.get("weighting", "equal"), cfg.get("weight_cap")
    n, share, mkey = sel["n_stocks"], sel.get("mom_share", 0.7), sel.get("mom_signal", "mom180")
    hkey = sel.get("high_signal", "near52")
    ok = ctx.volc if qf else (ctx.vol if wt == "inverse_vol" else None)   # names need a valid 63d vol for L2
    sectors = ctx.sectors if cap else None
    exit_n = buf.get("exit_rank", cfg["trading"]["buffer_exit"]); max_sw = buf.get("max_swaps", cfg["trading"]["max_swaps"])

    def weights(tickers, d):
        if wt == "equal":
            return P.equal_weight(list(tickers))
        if wt == "sleeve":      # SFIC live tool: 70% split over the momentum slots, 30% over the high slots (7% / 6% each)
            k = int(round(n * share)); tk = list(tickers)
            return pd.Series([share / k] * min(k, len(tk)) + [(1 - share) / max(len(tk) - k, 1)] * max(len(tk) - k, 0), index=tk)\
                .pipe(lambda x: x / x.sum())
        w = P.inverse_vol_weights(tickers, ctx.vol.loc[d])
        return P.cap_weights(w, wcap) if wcap else w

    if sel["type"] == "baseline_two_list":
        def fn(d, w):
            if buf.get("enabled"):
                t = P.baseline_buffered(d, ctx.sig, ctx.uni, list(w.index), n, share, mkey, ok, sectors, cap, exit_n, max_sw, hkey)
            else:
                t = P.baseline_select2(d, ctx.sig, ctx.uni, n, share, mkey, ok, sectors, cap, hkey)
            return weights(t, d)
    elif sel["type"] == "rank_score":
        def fn(d, w):
            o = P.pct_rank_score(d, ctx.sig, ctx.uni, extra_ok=ok)
            if buf.get("enabled"):
                t = P.buffered_select(o, ctx.sectors, list(w.index), n, exit_n, max_sw, cap if cap else 10**6)
            elif cap:
                t = P.greedy_capped(o, ctx.sectors, n, cap)
            else:
                t = list(o.index[:n])
            return weights(t, d)
    else:
        raise ValueError(sel["type"])
    return fn
