"""Cost and sizing assumptions, read from config/costs.yaml (single source of truth)."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_costs() -> dict:
    return yaml.safe_load((ROOT / "config" / "costs.yaml").read_text())


def base_bps() -> float:
    return float(load_costs()["cost_bps_per_side"])


def sensitivity_bps() -> list[float]:
    return [float(x) for x in load_costs()["cost_bps_sensitivity"]]


def capital(allocation: float | None = None) -> float:
    """Dollar capital for an allocation fraction (default: primary 1%)."""
    c = load_costs()
    a = c["allocation_primary"] if allocation is None else allocation
    return float(c["portfolio_value_usd"]) * float(a)


def cost_fraction(turnover: float, bps: float | None = None) -> float:
    """Cost as a fraction of NAV for a given traded notional / NAV (sum of |buys| + |sells|)."""
    b = base_bps() if bps is None else bps
    return turnover * b / 1e4
