"""Charts for the presentation. Run from improvements/ with SFIC_DATA_SOURCE=lseg.
Reads results/lseg_live_rule/*_returns.csv and results/stage4_stats/stage4_stats.json; writes PNGs to results/deck/."""
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from src import data

ROOT = data.DATA.parent
R, OUT = ROOT / "results" / "lseg_live_rule", ROOT / "results" / "deck"
OUT.mkdir(parents=True, exist_ok=True)

INK, MUTED, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
BLUE, ORANGE, AQUA, GRAY = "#2a78d6", "#eb6834", "#1baf7a", "#8a8984"
plt.rcParams.update({"font.family": "sans-serif", "font.size": 12, "axes.edgecolor": GRID, "axes.labelcolor": MUTED,
                     "xtick.color": MUTED, "ytick.color": MUTED, "figure.facecolor": SURF, "axes.facecolor": SURF,
                     "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8})

CAND = {"A: live baseline": ("live_base", BLUE), "B: A + L3": ("live_2b", ORANGE), "C: B + L4": ("live_2b_L4", AQUA)}
ret = {k: pd.read_csv(R / f"{v}_returns.csv", index_col=0, parse_dates=True).iloc[:, 0] for k, (v, _) in CAND.items()}
idx = ret["A: live baseline"].index
for r in ret.values():
    idx = idx.intersection(r.index)
ret = {k: r.loc[idx] for k, r in ret.items()}
bench = data.get_benchmark().reindex(idx).fillna(0.0)
stats = json.load(open(ROOT / "results" / "stage4_stats" / "stage4_stats.json"))["estimates"]


def save(fig, name):
    fig.tight_layout()
    fig.savefig(OUT / name, dpi=200)
    plt.close(fig)


# 1. Claimed vs reproduced Sharpe (pitch -> each correction)
labels = ["Original pitch\n(window 2024-26)", "Rebuild, today's\nuniverse (look-ahead)", "Rebuild, point-in-time\n(Yahoo, 2002-26)", "LSEG point-in-time\n(delisted incl., 2002-26)"]
vals = [1.7, 1.11, 0.91, stats["A: live baseline"]["Sharpe"]]
cols = [GRAY, GRAY, BLUE, BLUE]
fig, ax = plt.subplots(figsize=(10, 5.2))
bars = ax.bar(labels, vals, color=cols, width=0.55)
bars[0].set_hatch("//"); bars[0].set_edgecolor(SURF)
bars[1].set_hatch("//"); bars[1].set_edgecolor(SURF)
for b, v in zip(bars, vals):
    ax.text(b.get_x() + b.get_width() / 2, v + 0.04, f"{v:.2f}", ha="center", color=INK, fontsize=14, fontweight="bold")
ax.set_ylabel("Sharpe ratio"); ax.set_ylim(0, 2.0); ax.grid(axis="x", visible=False)
ax.set_title("The pitched Sharpe shrinks as data and window are corrected", loc="left", color=INK, fontsize=15)
fig.text(0.01, 0.005, "Hatched = not a valid full-sample backtest (short window or look-ahead universe). Rebuild uses the 180d/52w-high baseline; LSEG bar uses the live rule.",
         fontsize=8.5, color=MUTED)
save(fig, "1_pitch_vs_reproduced.png")

# 2. Growth of $1 (log)
fig, ax = plt.subplots(figsize=(10, 5.2))
for k, (_, c) in CAND.items():
    g = (1 + ret[k]).cumprod()
    ax.plot(g.index, g, color=c, lw=2, label=k)
    ax.text(g.index[-1], g.iloc[-1], f"  {k.split(':')[0]}", color=INK, va="center", fontsize=11)
gb = (1 + bench).cumprod()
ax.plot(gb.index, gb, color=GRAY, lw=2, ls="--", label="Benchmark 65/15/20")
ax.text(gb.index[-1], gb.iloc[-1], "  Bench", color=INK, va="center", fontsize=11)
ax.set_yscale("log"); ax.set_ylabel("Growth of $1 (log scale)"); ax.set_xlim(right=idx[-1] + pd.Timedelta(days=500))
ax.set_title("Growth of $1, LSEG point-in-time data, 0 bps", loc="left", color=INK, fontsize=15)
ax.legend(frameon=False, loc="upper left")
save(fig, "2_growth_of_dollar.png")

# 3. Drawdowns
fig, ax = plt.subplots(figsize=(10, 5.2))
for k, (_, c) in CAND.items():
    g = (1 + ret[k]).cumprod()
    ax.plot(g.index, g / g.cummax() - 1, color=c, lw=1.6, label=k)
gb = (1 + bench).cumprod()
ax.plot(gb.index, gb / gb.cummax() - 1, color=GRAY, lw=1.6, ls="--", label="Benchmark 65/15/20")
ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
ax.set_ylabel("Drawdown from peak")
ax.set_title("L4 roughly halves the 2008 drawdown; its worst point is 2002, before it has history", loc="left", color=INK, fontsize=14)
ax.legend(frameon=False, loc="lower right")
save(fig, "3_drawdowns.png")

# 4. Sharpe with 95% bootstrap CI
fig, ax = plt.subplots(figsize=(8, 4.6))
for i, (k, (_, c)) in enumerate(CAND.items()):
    s, (lo, hi) = stats[k]["Sharpe"], stats[k]["Sharpe_ci95"]
    ax.errorbar(i, s, yerr=[[s - lo], [hi - s]], fmt="o", color=c, ms=9, lw=2.5, capsize=6)
    ax.text(i + 0.12, s, f"{s:.2f}  [{lo:.2f}, {hi:.2f}]", va="center", color=INK, fontsize=11)
ax.set_xticks(range(3)); ax.set_xticklabels(CAND.keys()); ax.set_xlim(-0.5, 2.9); ax.set_ylim(0, 1.3)
ax.set_ylabel("Sharpe (95% block-bootstrap CI)"); ax.grid(axis="x", visible=False)
ax.set_title("The three candidates are statistically indistinguishable", loc="left", color=INK, fontsize=14)
save(fig, "4_sharpe_ci.png")
print("wrote", sorted(p.name for p in OUT.glob("*.png")))
