"""Gated one-shot holdout runner. NOT to be executed during development.

Usage:
  .venv/bin/python -m common.run_holdout --strategy strategy_1_residual_momentum --confirm-freeze
  [--override --reason "why a re-look is justified"]

Checks, in order:
  1. --confirm-freeze is given.
  2. <strategy>/outputs/frozen/{config.yaml,freeze_record.md} exist.
  3. sha256(frozen config.yaml) == config_hash in the freeze record.
  4. code_hash(strategy) == code_hash in the freeze record (no code edits since freezing).
  5. No previous holdout run for this strategy in logs/holdout_access.log, unless --override
     (then logged as a RE-LOOK with the reason).
Then: appends an access line, temporarily makes data/test_holdout readable, runs the frozen
entrypoint ONCE with a HoldoutLoader, re-locks the folder, and writes outputs to
<strategy>/outputs/holdout/<timestamp>/ with metrics measured only from the holdout start.
"""
from __future__ import annotations

import argparse
import datetime as dt
import getpass
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common import data_access, metrics  # noqa: E402
from common.codehash import code_hash, file_hash  # noqa: E402

HOLD = ROOT / "data" / "test_holdout"
ACCESS_LOG = ROOT / "logs" / "holdout_access.log"
STRATEGIES = {"strategy_1_residual_momentum", "strategy_2_vol_managed", "strategy_3_combined"}


def _log(line: str):
    with open(ACCESS_LOG, "a") as f:
        f.write(f"{dt.datetime.now().isoformat(timespec='seconds')}\t{getpass.getuser()}\t{line}\n")


def _set_mode(path: Path, file_mode: int, dir_mode: int):
    if dir_mode:  # unlocking: open dirs top-down
        os.chmod(path, dir_mode)
        for root, dirs, files in os.walk(path):
            for d in dirs:
                os.chmod(os.path.join(root, d), dir_mode)
            for f in files:
                os.chmod(os.path.join(root, f), file_mode)
    else:  # locking: files first, then dirs bottom-up
        for root, dirs, files in os.walk(path, topdown=False):
            for f in files:
                os.chmod(os.path.join(root, f), 0)
            for d in dirs:
                os.chmod(os.path.join(root, d), 0)
        os.chmod(path, 0)


def _parse_record(p: Path) -> dict:
    out = {}
    for ln in p.read_text().splitlines():
        m = re.match(r"^(\w+):\s*(\S+)", ln.strip())
        if m:
            out[m.group(1)] = m.group(2)
    return out


def verify(strategy: str) -> tuple[Path, dict]:
    sdir = ROOT / strategy
    fz = sdir / "outputs" / "frozen"
    cfgp, recp = fz / "config.yaml", fz / "freeze_record.md"
    for p in (cfgp, recp):
        if not p.exists():
            raise SystemExit(f"missing {p.relative_to(ROOT)}; freeze the strategy first")
    rec = _parse_record(recp)
    if file_hash(cfgp) != rec.get("config_hash"):
        raise SystemExit("frozen config hash does not match freeze record")
    if code_hash(sdir) != rec.get("code_hash"):
        raise SystemExit("code hash does not match freeze record (code or config changed since freeze)")
    return sdir, rec


def previous_runs(strategy: str) -> int:
    if not ACCESS_LOG.exists():
        return 0
    return sum(1 for ln in ACCESS_LOG.read_text().splitlines() if f"RUN\t{strategy}" in ln)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", required=True, choices=sorted(STRATEGIES))
    ap.add_argument("--confirm-freeze", action="store_true")
    ap.add_argument("--override", action="store_true")
    ap.add_argument("--reason", default="")
    a = ap.parse_args(argv)
    if not a.confirm_freeze:
        raise SystemExit("refusing: pass --confirm-freeze to acknowledge the strategy is frozen")
    sdir, rec = verify(a.strategy)
    n_prev = previous_runs(a.strategy)
    if n_prev and not a.override:
        _log(f"REFUSED\t{a.strategy}\tprevious_runs={n_prev}")
        raise SystemExit(f"holdout already run {n_prev}x for {a.strategy}; use --override --reason to re-look")
    if a.override and not a.reason:
        raise SystemExit("--override requires --reason")
    kind = "RE-LOOK" if n_prev else "FIRST"
    _log(f"RUN\t{a.strategy}\t{kind}\tcode_hash={rec['code_hash'][:16]}\tconfig_hash={rec['config_hash'][:16]}"
         f"\tvariants_tried={rec.get('variants_tried')}\treason={a.reason!r}")

    cfg = yaml.safe_load((sdir / "outputs" / "frozen" / "config.yaml").read_text())
    spec = importlib.util.spec_from_file_location(f"{a.strategy}.src.entrypoint", sdir / "src" / "entrypoint.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    _set_mode(HOLD, 0o400, 0o500)
    try:
        loader = data_access.HoldoutLoader(_gate=data_access._GATE_TOKEN)
        result = mod.run(cfg, loader)
        rf = loader.cash_rate()
        bench = loader.benchmarks().set_index("date")["SFIC_BENCH"]
        fac = loader.factors("daily")
    finally:
        _set_mode(HOLD, 0, 0)
    out = sdir / "outputs" / "holdout" / dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True)
    for k in ("daily_returns", "positions", "trades"):
        result[k].to_csv(out / f"{k}.csv", index=False)
    r = result["daily_returns"].set_index("date")["net"]
    m = metrics.summary(r, rf, bench, fac, result["daily_returns"], start=data_access.HOLDOUT_START)
    m["kind"] = kind
    (out / "metrics.json").write_text(json.dumps(m, indent=2, default=str))
    _log(f"DONE\t{a.strategy}\t{kind}\toutputs={out.relative_to(ROOT)}")
    print(json.dumps(m, indent=2, default=str))


if __name__ == "__main__":
    main()
