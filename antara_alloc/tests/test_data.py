"""(d) data checks: no NaN explosions, factor alignment, benchmark proxies spliced correctly."""
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from common.data_access import TrainingLoader
from conftest import require_training_data

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def L():
    require_training_data()
    return TrainingLoader()


def test_returns_sane(L):
    r = L.returns()
    v = r.to_numpy().ravel(); v = v[~np.isnan(v)]
    assert np.isfinite(v).all()
    assert r.abs().max().max() <= 3.0
    # no NaN explosion: share of NaN among tickers that are alive (have a price) stays small
    px = L.prices()
    alive = px.notna()
    nan_alive = (r.isna() & alive).sum().sum() / alive.sum().sum()
    assert nan_alive < 0.01, nan_alive
    dv = L.prices(field="dollar_volume").to_numpy().ravel()
    assert (dv[~np.isnan(dv)] >= 0).all()


def test_universe_size(L):
    for d in ("2000-01-31", "2008-09-30", "2019-12-31"):
        u = L.universe(d)
        # universe = S&P 500 members on d that have Yahoo data (fewer early on: removed names lack data)
        assert 250 <= len(u) <= 500, (d, len(u))
        assert not {"SPY", "EFA", "AGG"} & set(u)


def test_factor_alignment(L):
    fd, fm = L.factors("daily"), L.factors("monthly")
    for f in (fd, fm):
        assert {"MKT_RF", "SMB", "HML", "RF", "MOM"} <= set(f.columns)
        assert f[["MKT_RF", "SMB", "HML", "RF"]].abs().max().max() < 0.5  # decimals, not percent
        assert f.date.is_monotonic_increasing and f.date.is_unique
    assert (fm.date == fm.date + pd.offsets.MonthEnd(0)).all()  # month-end stamps
    td = L.trading_days()
    cov = td.isin(pd.DatetimeIndex(fd.date)).mean()
    assert cov > 0.995, cov
    # monthly factors ~ compounded daily factors
    d = fd.set_index("date")
    comp = (1 + d["MKT_RF"] + d["RF"]).groupby(d.index.to_period("M")).prod() - 1
    m = fm.set_index(fm.date.dt.to_period("M"))
    diff = (comp - (m["MKT_RF"] + m["RF"])).dropna()
    assert diff.abs().median() < 0.002
    # market factor correlates with SPY
    spy = L.benchmarks().set_index("date")["SPY"]
    x = pd.concat([spy, d["MKT_RF"] + d["RF"]], axis=1, join="inner").dropna()
    assert x.corr().iloc[0, 1] > 0.95


def test_benchmark_splice(L):
    b = L.benchmarks().set_index("date")
    assert b[["SPY", "EFA", "AGG", "SFIC_BENCH"]].notna().all().all()
    rawp = ROOT / "data" / "raw" / "benchmarks_prices.parquet"
    if not os.access(rawp, os.R_OK):
        pytest.skip("data/raw locked after split; splice vs raw proxies verified at setup (logs/data_log.md)")
    raw = pd.read_parquet(rawp)
    raw["date"] = pd.to_datetime(raw["date"])
    px = raw.pivot(index="date", columns="ticker", values="adj_close")
    rr = px.pct_change()
    for etf, proxy in (("EFA", "VGTSX"), ("AGG", "VBMFX")):
        first = px[etf].first_valid_index()
        pre = b.loc[:first].index[1:]
        post = b.loc[first:].index[1:]
        np.testing.assert_allclose(b.loc[pre, etf], rr.loc[pre, proxy], atol=1e-12)
        np.testing.assert_allclose(b.loc[post, etf], rr.loc[post, etf], atol=1e-12)
    # SFIC benchmark: on the first day of each month weights are exactly 65/15/20
    firsts = b.groupby(b.index.to_period("M")).head(1).index[1:]
    exp = 0.65 * b.loc[firsts, "SPY"] + 0.15 * b.loc[firsts, "EFA"] + 0.20 * b.loc[firsts, "AGG"]
    np.testing.assert_allclose(b.loc[firsts, "SFIC_BENCH"], exp, atol=1e-12)
    assert 0.03 < b["SFIC_BENCH"].std() * np.sqrt(252) < 0.25


def test_universe_only_point_in_time_members(L):
    from common.universe import load_membership, members_on
    mem = load_membership()
    assert mem is not None, "config/universe.yaml must set membership_file"
    for d in ("2005-06-30", "2012-03-30", "2016-12-30", "2019-12-31"):
        assert set(L.universe(d)) <= members_on(mem, d), d
    # stocks that joined the index later are not eligible before they joined
    assert "TSLA" not in L.universe("2019-12-31")      # added 2020-12-21
    assert "TSLA" not in members_on(mem, "2020-12-18") and "TSLA" in members_on(mem, "2020-12-21")
