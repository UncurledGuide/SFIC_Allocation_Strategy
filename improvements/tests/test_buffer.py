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
