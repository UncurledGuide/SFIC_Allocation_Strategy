"""Run-logging contract (docs/PROJECT_SPEC.md §7). EVERY run must use RunLogger.

    from common.run_logger import RunLogger
    with RunLogger(strategy_dir, variant="primary", split="validation", cfg=cfg,
                   purpose="...", hypothesis="...", seed=0, key_params={...}) as run:
        result = entrypoint.run(cfg, loader)          # dict: daily_returns, positions, trades
        run.record(result, metrics_dict)
        run.note(outcome="...", next_decision="...")

Creates <strategy_dir>/runs/<run_id>/ with: config.yaml, meta.json (data manifest hash, split, params,
seed, code hash, start/end time, status), stdout.log (stdout+stderr tee), metrics.json, equity_curve.csv,
daily_returns.csv, positions.csv, trades.csv, notes.md; and appends one row to
<strategy_dir>/logs/run_registry.csv so the number of variants tried is countable.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import random
import sys
import traceback
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from common.codehash import code_hash, file_hash

ROOT = Path(__file__).resolve().parents[1]
VALID_SPLITS = {"fit", "validation", "fit+validation", "training", "holdout", "smoke"}
REGISTRY_COLS = ["run_id", "timestamp", "variant", "split", "key_params", "sharpe", "cagr", "ann_vol",
                 "max_drawdown", "turnover", "status", "code_hash", "run_dir"]


class _Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, s):
        for st in self.streams:
            st.write(s)

    def flush(self):
        for st in self.streams:
            st.flush()


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (pd.Timestamp, dt.date)):
        return str(o)
    return repr(o)


class RunLogger:
    def __init__(self, strategy_dir, variant: str, split: str, cfg: dict, purpose: str,
                 hypothesis: str, seed: int = 0, key_params: dict | None = None,
                 runs_root: Path | None = None, registry_path: Path | None = None):
        if split not in VALID_SPLITS:
            raise ValueError(f"split must be one of {VALID_SPLITS}")
        if not purpose or not hypothesis:
            raise ValueError("purpose and hypothesis are required")
        self.strategy_dir = Path(strategy_dir) if Path(strategy_dir).is_absolute() else ROOT / strategy_dir
        self.variant, self.split, self.cfg, self.seed = variant, split, cfg, seed
        self.purpose, self.hypothesis = purpose, hypothesis
        self.key_params = key_params or {}
        self.runs_root = Path(runs_root) if runs_root else self.strategy_dir / "runs"
        self.registry = Path(registry_path) if registry_path else self.strategy_dir / "logs" / "run_registry.csv"
        self.metrics: dict = {}
        self.outcome, self.next_decision = "", ""
        self.status = "running"

    # ------------------------------------------------------------------ lifecycle
    def __enter__(self):
        self.start = dt.datetime.now()
        self.code_hash = code_hash(self.strategy_dir) if (self.strategy_dir / "src").exists() else code_hash(self.strategy_dir)
        safe_variant = "".join(c if c.isalnum() or c in "-_" else "-" for c in self.variant)[:40]
        self.run_id = f"{self.start:%Y%m%d-%H%M%S}-{safe_variant}-{self.code_hash[:8]}"
        self.dir = self.runs_root / self.run_id
        self.dir.mkdir(parents=True, exist_ok=False)
        (self.dir / "config.yaml").write_text(yaml.safe_dump(self.cfg, sort_keys=True))
        tm = ROOT / "data" / "training" / "_split_manifest.json"
        self.data_manifest_hash = file_hash(tm) if tm.exists() else None
        random.seed(self.seed)
        np.random.seed(self.seed)
        self._log = open(self.dir / "stdout.log", "w")
        self._old = (sys.stdout, sys.stderr)
        sys.stdout = _Tee(self._old[0], self._log)
        sys.stderr = _Tee(self._old[1], self._log)
        self._write_meta()
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is not None:
            self.status = "failed"
            traceback.print_exception(exc_type, exc, tb, file=self._log)
        elif self.status == "running":
            self.status = "ok"
        self.end = dt.datetime.now()
        sys.stdout, sys.stderr = self._old
        self._log.close()
        (self.dir / "metrics.json").write_text(json.dumps(self.metrics, indent=2, default=_json_default))
        self._write_meta()
        self._write_notes()
        self._append_registry()
        return False  # never swallow exceptions

    # ------------------------------------------------------------------ api
    def record(self, result: dict, metrics: dict):
        """Save entrypoint outputs (daily_returns, positions, trades) and metrics."""
        dr = result["daily_returns"]
        dr.to_csv(self.dir / "daily_returns.csv", index=False)
        eq = dr[["date"]].copy()
        for c in ("gross", "net"):
            if c in dr:
                eq[f"equity_{c}"] = (1 + dr[c]).cumprod().values
        eq.to_csv(self.dir / "equity_curve.csv", index=False)
        for k in ("positions", "trades"):
            if k in result and isinstance(result[k], pd.DataFrame):
                result[k].to_csv(self.dir / f"{k}.csv", index=False)
        self.metrics = metrics

    def note(self, outcome: str, next_decision: str):
        self.outcome, self.next_decision = outcome, next_decision

    # ------------------------------------------------------------------ writers
    def _write_meta(self):
        meta = {"run_id": self.run_id, "variant": self.variant, "split": self.split, "seed": self.seed,
                "key_params": self.key_params, "code_hash": self.code_hash,
                "data_manifest_sha256": self.data_manifest_hash,
                "start_time": self.start.isoformat(timespec="seconds"),
                "end_time": getattr(self, "end", None) and self.end.isoformat(timespec="seconds"),
                "status": self.status, "python": sys.version.split()[0]}
        (self.dir / "meta.json").write_text(json.dumps(meta, indent=2, default=_json_default))

    def _write_notes(self):
        (self.dir / "notes.md").write_text(
            f"# Run {self.run_id}\n\n- **Variant:** {self.variant}\n- **Split:** {self.split}\n"
            f"- **Status:** {self.status}\n\n## Purpose\n{self.purpose}\n\n## Hypothesis\n{self.hypothesis}\n\n"
            f"## Outcome\n{self.outcome or '(not recorded)'}\n\n## Next decision\n{self.next_decision or '(not recorded)'}\n")

    def _append_registry(self):
        self.registry.parent.mkdir(parents=True, exist_ok=True)
        new = not self.registry.exists()
        m = self.metrics or {}
        row = {"run_id": self.run_id, "timestamp": self.start.isoformat(timespec="seconds"),
               "variant": self.variant, "split": self.split,
               "key_params": json.dumps(self.key_params, sort_keys=True, default=_json_default),
               "sharpe": m.get("sharpe"), "cagr": m.get("cagr"), "ann_vol": m.get("ann_vol"),
               "max_drawdown": m.get("max_drawdown"),
               "turnover": m.get("annual_one_way_turnover"), "status": self.status,
               "code_hash": self.code_hash,
               "run_dir": str(self.dir.relative_to(ROOT)) if self.dir.is_relative_to(ROOT) else str(self.dir)}
        with open(self.registry, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=REGISTRY_COLS)
            if new:
                w.writeheader()
            w.writerow(row)


def count_variants(strategy_dir) -> int:
    """Number of distinct variants with at least one completed run in the registry."""
    p = Path(strategy_dir)
    p = (p if p.is_absolute() else ROOT / p) / "logs" / "run_registry.csv"
    if not p.exists():
        return 0
    df = pd.read_csv(p)
    return int(df.loc[df.status == "ok", "variant"].nunique())


def write_freeze_record(strategy_dir, entrypoint_note: str = "src/entrypoint.py:run") -> Path:
    """Write outputs/frozen/freeze_record.md with config hash, code hash, variants tried.
    Call after placing the frozen config.yaml (and validation outputs) in outputs/frozen/."""
    sdir = Path(strategy_dir) if Path(strategy_dir).is_absolute() else ROOT / strategy_dir
    fz = sdir / "outputs" / "frozen"
    cfgp = fz / "config.yaml"
    if not cfgp.exists():
        raise FileNotFoundError(cfgp)
    reg = sdir / "logs" / "run_registry.csv"
    n_runs = len(pd.read_csv(reg)) if reg.exists() else 0
    rec = fz / "freeze_record.md"
    rec.write_text(
        f"# Freeze record: {sdir.name}\n\n"
        f"frozen_at: {dt.datetime.now().isoformat(timespec='seconds')}\n"
        f"config_hash: {file_hash(cfgp)}\n"
        f"code_hash: {code_hash(sdir)}\n"
        f"variants_tried: {count_variants(sdir)}\n"
        f"total_runs_logged: {n_runs}\n"
        f"entrypoint: {entrypoint_note}\n")
    return rec
