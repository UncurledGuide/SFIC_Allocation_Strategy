import sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.portfolio import buffered_select, greedy_capped

ORDER = pd.Series(np.linspace(1, 0, 60), index=[f"S{i}" for i in range(1, 61)])
SEC = {f"S{i}": f"sec{i % 8}" for i in range(1, 61)}


def test_no_trade_when_all_inside_buffer():
    held = [f"S{i}" for i in range(11, 26)]          # ranks 11..25: inside the exit buffer
    assert set(buffered_select(ORDER, SEC, held, cap=99)) == set(held)


def test_swap_cap_and_lowest_ranked_sold_first():
    held = [f"S{i}" for i in list(range(30, 40)) + list(range(1, 6))]   # 10 holdings ranked >25
    new = buffered_select(ORDER, SEC, held, cap=99)
    sold = set(held) - set(new)
    assert len(sold) == 6 and len(new) == 15
    assert sold == {"S39", "S38", "S37", "S36", "S35", "S34"}
    assert set(new) - set(held) == {f"S{i}" for i in range(6, 12)}      # best-ranked non-held names bought


def test_sector_cap():
    out = greedy_capped(ORDER, SEC, 15, 4)
    from collections import Counter
    assert max(Counter(SEC[t] for t in out).values()) <= 4 and len(out) == 15


def test_cap_weights_sums_to_one_and_respects_cap():
    from src.portfolio import cap_weights
    w = pd.Series([0.5] + [0.5 / 14] * 14)
    c = cap_weights(w, 0.10)
    assert abs(c.sum() - 1) < 1e-9 and c.max() <= 0.10 + 1e-9


def test_quality_filter_flags_pinned_and_stale_stocks():
    from src.portfolio import quality_ok
    rng = np.random.default_rng(1)
    idx = pd.bdate_range("2020-01-01", periods=120)
    r = pd.DataFrame({"norm": rng.normal(0, .02, 120), "pinned": rng.normal(0, .001, 120), "stale": 0.0}, index=idx)
    ok = quality_ok(r).iloc[-1]
    assert ok["norm"] and not ok["pinned"] and not ok["stale"]


def test_ineligible_ties_are_broken_deterministically():
    """Many held names are ineligible (rank=inf, all tied) and only 6 may be sold: the 6 chosen must not depend on
    set iteration order (PYTHONHASHSEED)."""
    held = [f"X{i:02d}" for i in range(10)] + [f"S{i}" for i in range(1, 6)]   # 10 ineligible + 5 good
    outs = {tuple(sorted(buffered_select(ORDER, SEC, held, cap=99))) for _ in range(5)}
    assert len(outs) == 1
    sold = set(held) - set(next(iter(outs)))
    assert sold == {f"X{i:02d}" for i in range(4, 10)}      # ticker-descending tie-break
