"""Data loaders. Strategies get data ONLY through these objects, never via file paths.

TrainingLoader: physically reads only data/training; raises on any request after 2019-12-31
                (or after a lower `max_date` the caller chooses, e.g. fit-only runs).
HoldoutLoader : gated; constructed only by common/run_holdout.py. Exposes training history
                for lookbacks plus the holdout period; performance is measured from holdout start.

Shared interface:
  prices(tickers=None, start=None, end=None, field="adj_close") -> wide DataFrame (date x ticker)
      field in {"adj_close", "close", "volume", "dollar_volume", "ret"}
  returns(tickers=None, start=None, end=None) -> wide daily simple returns (from Adj Close)
  volumes(tickers=None, start=None, end=None) -> wide share volume
  dollar_volumes(...) -> wide raw Close*Volume
  universe(asof) -> list[str]  point-in-time top-500 S&P 500 members (on asof) by trailing 63d dollar volume
  factors(freq="daily"|"monthly") -> DataFrame [date, MKT_RF, SMB, HML, RF, MOM]
  benchmarks() -> DataFrame [date, SPY, EFA, AGG, SFIC_BENCH] daily returns
  cash_rate() -> Series daily RF (decimal), index=date
  trading_days() -> DatetimeIndex
  split_name, max_date, perf_start
"""
from __future__ import annotations

from functools import cached_property
from pathlib import Path

import pandas as pd
import yaml

from common import universe as _universe

ROOT = Path(__file__).resolve().parents[1]
SPLITS = yaml.safe_load((ROOT / "config" / "splits.yaml").read_text())
TRAINING_CEILING = pd.Timestamp(SPLITS["training_max_date"])
HOLDOUT_START = pd.Timestamp(SPLITS["holdout"]["start"])
_FIELDS = {"adj_close", "close", "volume", "dollar_volume", "ret"}


class LookaheadError(ValueError):
    """Raised when a request reaches beyond the loader's max_date."""


class _BaseLoader:
    split_name: str = "base"

    def __init__(self, data_dirs: list[Path], max_date: pd.Timestamp, perf_start: pd.Timestamp | None):
        for d in data_dirs:
            if not Path(d).is_dir():
                raise FileNotFoundError(d)
        self._dirs = [Path(d) for d in data_dirs]
        self.max_date = pd.Timestamp(max_date)
        self.perf_start = perf_start
        self._wide: dict[str, pd.DataFrame] = {}

    # ---------------------------------------------------------------- internals
    def _read(self, fn: str) -> pd.DataFrame:
        parts = [pd.read_parquet(d / fn) for d in self._dirs]
        df = pd.concat(parts, ignore_index=True)
        df["date"] = pd.to_datetime(df["date"])
        df = df[df.date <= self.max_date]
        return df.sort_values("date").reset_index(drop=True)

    def _check(self, *dates):
        for d in dates:
            if d is not None and pd.Timestamp(d) > self.max_date:
                raise LookaheadError(f"{self.split_name}: requested date {pd.Timestamp(d).date()} > "
                                     f"max_date {self.max_date.date()}")

    @cached_property
    def _long_prices(self) -> pd.DataFrame:
        return self._read("prices.parquet")

    def _wide_field(self, field: str) -> pd.DataFrame:
        if field not in _FIELDS:
            raise ValueError(f"field must be one of {_FIELDS}")
        if field not in self._wide:
            w = self._long_prices.pivot(index="date", columns="ticker", values=field)
            self._wide[field] = w.reindex(self.trading_days())
        return self._wide[field]

    # ---------------------------------------------------------------- interface
    def trading_days(self) -> pd.DatetimeIndex:
        return pd.DatetimeIndex(self._bench["date"])

    def prices(self, tickers=None, start=None, end=None, field="adj_close") -> pd.DataFrame:
        self._check(start, end)
        w = self._wide_field(field)
        if tickers is not None:
            w = w.reindex(columns=list(tickers))
        return w.loc[start:end].copy()

    def returns(self, tickers=None, start=None, end=None) -> pd.DataFrame:
        return self.prices(tickers, start, end, field="ret")

    def volumes(self, tickers=None, start=None, end=None) -> pd.DataFrame:
        return self.prices(tickers, start, end, field="volume")

    def dollar_volumes(self, tickers=None, start=None, end=None) -> pd.DataFrame:
        return self.prices(tickers, start, end, field="dollar_volume")

    def universe(self, asof) -> list[str]:
        self._check(asof)
        mem = self._membership
        members = _universe.members_on(mem, asof) if mem is not None else None
        return _universe.top_by_dollar_volume(self._wide_field("dollar_volume"),
                                              self._wide_field("adj_close"), asof, members=members)

    @cached_property
    def _membership(self):
        return _universe.load_membership()

    def factors(self, freq: str = "daily") -> pd.DataFrame:
        if freq not in ("daily", "monthly"):
            raise ValueError("freq must be 'daily' or 'monthly'")
        return self._read(f"factors_{freq}.parquet")

    @cached_property
    def _bench(self) -> pd.DataFrame:
        return self._read("benchmarks_daily.parquet")

    def benchmarks(self) -> pd.DataFrame:
        return self._bench[["date", "SPY", "EFA", "AGG", "SFIC_BENCH"]].copy()

    def cash_rate(self) -> pd.Series:
        f = self.factors("daily").set_index("date")["RF"]
        return f.reindex(self.trading_days()).ffill(limit=5).fillna(0.0)

    def __repr__(self):
        return f"<{type(self).__name__} split={self.split_name} max_date={self.max_date.date()}>"


class TrainingLoader(_BaseLoader):
    """Reads only data/training. `max_date` may be lowered (e.g. '2014-12-31' for fit-only work)."""

    split_name = "training"

    def __init__(self, max_date=None, _data_dir: Path | None = None):
        d = Path(_data_dir) if _data_dir else ROOT / "data" / "training"
        if "test_holdout" in str(d.resolve()):
            raise PermissionError("TrainingLoader may not read data/test_holdout")
        md = pd.Timestamp(max_date) if max_date is not None else TRAINING_CEILING
        if md > TRAINING_CEILING:
            raise LookaheadError(f"TrainingLoader max_date cannot exceed {TRAINING_CEILING.date()}")
        super().__init__([d], md, perf_start=None)


_GATE_TOKEN = object()  # only run_holdout.py passes this


class HoldoutLoader(_BaseLoader):
    """Gated loader. Use only via common/run_holdout.py."""

    split_name = "test_holdout"

    def __init__(self, _gate=None, _training_dir: Path | None = None, _holdout_dir: Path | None = None):
        if _gate is not _GATE_TOKEN:
            raise PermissionError("HoldoutLoader can only be created by common/run_holdout.py")
        t = Path(_training_dir) if _training_dir else ROOT / "data" / "training"
        h = Path(_holdout_dir) if _holdout_dir else ROOT / "data" / "test_holdout"
        super().__init__([t, h], pd.Timestamp.max.normalize(), perf_start=HOLDOUT_START)
        self.max_date = self.trading_days().max()
