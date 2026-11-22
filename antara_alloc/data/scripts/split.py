"""THE ONLY code allowed to read data/processed.

Writes data/training (<= training_max_date, includes warm-up) and data/test_holdout (>= holdout start),
records hashes/row counts in logs/data_log.md and each split's _split_manifest.json, then locks
data/test_holdout with chmod -R 000. After this runs, nothing but common/run_holdout.py may open it.
Run: .venv/bin/python data/scripts/split.py
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import stat
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]
PROC = ROOT / "data" / "processed"
TRAIN, HOLD = ROOT / "data" / "training", ROOT / "data" / "test_holdout"
SPL = yaml.safe_load((ROOT / "config" / "splits.yaml").read_text())
FILES = ["prices.parquet", "factors_daily.parquet", "factors_monthly.parquet", "benchmarks_daily.parquet"]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def lock(path: Path):
    for root, dirs, files in os.walk(path, topdown=False):
        for f in files:
            os.chmod(os.path.join(root, f), 0)
        for d in dirs:
            os.chmod(os.path.join(root, d), 0)
    os.chmod(path, 0)


def main():
    if HOLD.exists() and not os.access(HOLD, os.R_OK | os.X_OK):
        raise SystemExit("data/test_holdout is already locked; refusing to re-split.")
    tmax = pd.Timestamp(SPL["training_max_date"])
    hmin = pd.Timestamp(SPL["holdout"]["start"])
    assert hmin > tmax
    TRAIN.mkdir(parents=True, exist_ok=True)
    HOLD.mkdir(parents=True, exist_ok=True)
    lines = [f"\n## split run {dt.datetime.now().isoformat(timespec='seconds')}",
             f"training <= {tmax.date()} ; holdout >= {hmin.date()}", "",
             "| split | file | rows | first | last | sha256 |", "|---|---|---|---|---|---|"]
    man = {"training": {}, "test_holdout": {}}
    for fn in FILES:
        df = pd.read_parquet(PROC / fn)
        df["date"] = pd.to_datetime(df["date"])
        for name, part, d in (("training", df[df.date <= tmax], TRAIN), ("test_holdout", df[df.date >= hmin], HOLD)):
            out = d / fn
            part.reset_index(drop=True).to_parquet(out, index=False)
            h = sha(out)
            man[name][fn] = {"rows": len(part), "sha256": h,
                             "first": str(part.date.min().date()) if len(part) else None,
                             "last": str(part.date.max().date()) if len(part) else None}
            lines.append(f"| {name} | {fn} | {len(part):,} | {man[name][fn]['first']} | {man[name][fn]['last']} | `{h[:16]}…` |")
    raw_manifest = ROOT / "data" / "raw" / "manifest.json"
    for name, d in (("training", TRAIN), ("test_holdout", HOLD)):
        m = {"split": name, "created_at": dt.datetime.now().isoformat(timespec="seconds"),
             "raw_manifest_sha256": sha(raw_manifest), "files": man[name]}
        (d / "_split_manifest.json").write_text(json.dumps(m, indent=2))
    lines.append(f"\ntraining manifest sha256: `{sha(TRAIN / '_split_manifest.json')}`")
    lines.append(f"holdout manifest sha256 (recorded before lock): `{sha(HOLD / '_split_manifest.json')}`")
    lock(HOLD)
    ok = not os.access(HOLD, os.R_OK)
    lines.append(f"data/test_holdout locked with chmod -R 000: {'YES' if ok else 'FAILED'}")
    with open(ROOT / "logs" / "data_log.md", "a") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
