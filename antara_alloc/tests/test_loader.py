"""(b) TrainingLoader ceiling, (c) look-ahead invariance, holdout lock checks."""
import os
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from common.data_access import HoldoutLoader, LookaheadError, TrainingLoader
from conftest import require_training_data

ROOT = Path(__file__).resolve().parents[1]
ASOF = pd.Timestamp("2012-06-29")


@pytest.fixture(scope="module")
def loader():
    require_training_data()
    return TrainingLoader()


# ---------------------------------------------------------------- (b)
def test_refuses_dates_after_ceiling(loader):
    assert loader.max_date == pd.Timestamp("2019-12-31")
    for call in (lambda: loader.prices(end="2020-01-02"), lambda: loader.prices(start="2020-01-02"),
                 lambda: loader.returns(end="2021-01-01"), lambda: loader.universe("2020-01-31"),
                 lambda: TrainingLoader(max_date="2020-01-01")):
        with pytest.raises(LookaheadError):
            call()


def test_no_data_after_ceiling(loader):
    assert loader.prices().index.max() <= pd.Timestamp("2019-12-31")
    assert loader.trading_days().max() <= pd.Timestamp("2019-12-31")
    for f in ("daily", "monthly"):
        assert loader.factors(f).date.max() <= pd.Timestamp("2019-12-31")
    assert loader.benchmarks().date.max() <= pd.Timestamp("2019-12-31")


def test_lower_max_date_for_fit_only():
    require_training_data()
    l = TrainingLoader(max_date="2014-12-31")
    assert l.prices().index.max() <= pd.Timestamp("2014-12-31")
    with pytest.raises(LookaheadError):
        l.prices(end="2015-01-02")


def test_training_loader_refuses_holdout_dir():
    with pytest.raises(PermissionError):
        TrainingLoader(_data_dir=ROOT / "data" / "test_holdout")


def test_holdout_loader_is_gated():
    with pytest.raises(PermissionError):
        HoldoutLoader()


def test_holdout_folder_is_locked():
    h = ROOT / "data" / "test_holdout"
    if not h.exists():
        pytest.skip("data/test_holdout not present; it is created and locked by data/scripts/split.py")
    assert not os.access(h, os.R_OK), "data/test_holdout must be chmod 000"
    assert (os.stat(h).st_mode & 0o777) == 0


# ---------------------------------------------------------------- (c)
@pytest.fixture(scope="module")
def perturbed_dirs(tmp_path_factory):
    """Copies of data/training with (1) all rows after ASOF removed, (2) rows after ASOF scrambled."""
    require_training_data()
    src = ROOT / "data" / "training"
    trunc, pert = tmp_path_factory.mktemp("trunc"), tmp_path_factory.mktemp("pert")
    rng = np.random.default_rng(0)
    for fn in src.glob("*.parquet"):
        df = pd.read_parquet(fn)
        df["date"] = pd.to_datetime(df["date"])
        df[df.date <= ASOF].to_parquet(trunc / fn.name, index=False)
        p = df.copy()
        fut = p.date > ASOF
        for c in p.columns:
            if c not in ("date", "ticker", "source") and pd.api.types.is_numeric_dtype(p[c]):
                p.loc[fut, c] = p.loc[fut, c].to_numpy() * rng.uniform(0.1, 10, fut.sum())
        p.to_parquet(pert / fn.name, index=False)
    return trunc, pert


def test_lookahead_invariance(loader, perturbed_dirs):
    trunc, pert = perturbed_dirs
    lt, lp = TrainingLoader(_data_dir=trunc), TrainingLoader(_data_dir=pert)
    for asof in (pd.Timestamp("2005-03-31"), pd.Timestamp("2010-12-31"), ASOF):
        u = loader.universe(asof)
        assert len(u) > 100
        assert u == lt.universe(asof) == lp.universe(asof), f"universe({asof.date()}) depends on future data"
    for field in ("adj_close", "close", "volume", "dollar_volume", "ret"):
        a = loader.prices(end=ASOF, field=field)
        pd.testing.assert_frame_equal(a, lp.prices(end=ASOF, field=field))
        pd.testing.assert_frame_equal(a, lt.prices(end=ASOF, field=field).reindex(columns=a.columns))
    for f in ("daily", "monthly"):
        a = loader.factors(f)
        pd.testing.assert_frame_equal(a[a.date <= ASOF].reset_index(drop=True),
                                      lp.factors(f).query("date <= @ASOF").reset_index(drop=True))
    b = loader.benchmarks()
    pd.testing.assert_frame_equal(b[b.date <= ASOF].reset_index(drop=True),
                                  lp.benchmarks().query("date <= @ASOF").reset_index(drop=True))
    pd.testing.assert_series_equal(loader.cash_rate().loc[:ASOF], lp.cash_rate().loc[:ASOF])


def test_universe_uses_only_past_dollar_volume(loader):
    # spike a ticker's volume the day AFTER asof: rank must not move
    from common.universe import top_by_dollar_volume
    dv = loader.dollar_volumes(end="2012-12-31").copy()
    px = loader.prices(end="2012-12-31")
    base = top_by_dollar_volume(dv, px, ASOF)
    loser = base[-1]
    nxt = dv.index[dv.index.get_loc(ASOF) + 1]
    dv.loc[nxt:, loser] = 1e15
    assert top_by_dollar_volume(dv, px, ASOF) == base
