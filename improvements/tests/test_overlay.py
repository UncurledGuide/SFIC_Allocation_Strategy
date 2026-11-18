import sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.overlay import exposure_schedule


def _series(vol, n=300, seed=0):
    idx = pd.bdate_range("2020-01-01", periods=n)
    return pd.Series(np.random.default_rng(seed).normal(0, vol / np.sqrt(252), n), index=idx)


def test_w_is_one_until_enough_history_and_never_above_one():
    u = _series(0.10)                                     # low vol -> raw w would be >1 -> capped at 1
    s = exposure_schedule(u, list(u.index[::21]), sigma_target=0.15)
    assert (s == 1.0).all()


def test_scales_down_when_vol_is_high_and_only_updates_on_big_moves():
    u = _series(0.30)
    s = exposure_schedule(u, list(u.index[::21]), sigma_target=0.15)
    late = s.iloc[-1]
    assert 0.35 < late < 0.7                              # ~0.15/0.30 = 0.5
    steps = s.diff().abs().dropna()
    assert ((steps == 0) | (steps > 0.10)).all()          # every change is larger than the 0.10 threshold


def test_no_future_data_in_exposure():
    u = _series(0.30)
    dates = list(u.index[::21]); d = dates[10]
    a = exposure_schedule(u, dates[:11], 0.15).iloc[-1]
    poisoned = u.copy(); poisoned.loc[poisoned.index > d] = 5.0
    b = exposure_schedule(poisoned, dates[:11], 0.15).iloc[-1]
    assert a == b
