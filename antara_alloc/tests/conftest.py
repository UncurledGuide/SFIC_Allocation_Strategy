import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


import pytest

TRAINING_DATA = ROOT / "data" / "training" / "prices.parquet"


def require_training_data():
    """Skip a test when data/training has not been built (it is not stored in git)."""
    if not TRAINING_DATA.exists():
        pytest.skip("data/training not present; build it with data/scripts (see README)")
