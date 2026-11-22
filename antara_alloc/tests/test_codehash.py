"""(e) code_hash is deterministic and changes when any covered file changes."""
import shutil
from pathlib import Path

import pytest

from common.codehash import code_hash, covered_files

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def fake_root(tmp_path):
    for d in ("common", "config"):
        shutil.copytree(ROOT / d, tmp_path / d, ignore=shutil.ignore_patterns("__pycache__"))
    s = tmp_path / "strategy_x"
    (s / "src").mkdir(parents=True)
    (s / "configs").mkdir()
    (s / "src" / "entrypoint.py").write_text("def run(cfg, loader):\n    return {}\n")
    (s / "configs" / "base.yaml").write_text("a: 1\n")
    (s / "runs").mkdir()
    return tmp_path


def test_deterministic(fake_root):
    assert code_hash(fake_root / "strategy_x", root=fake_root) == code_hash(fake_root / "strategy_x", root=fake_root)


def test_changes_on_any_covered_file(fake_root):
    s = fake_root / "strategy_x"
    files = covered_files(s, root=fake_root)
    assert any("common" in f.parts for f in files) and any("config" in f.parts for f in files)
    for f in [s / "src" / "entrypoint.py", s / "configs" / "base.yaml",
              fake_root / "common" / "metrics.py", fake_root / "config" / "costs.yaml"]:
        before = code_hash(s, root=fake_root)
        orig = f.read_bytes()
        f.write_bytes(orig + b"\n# edit\n")
        assert code_hash(s, root=fake_root) != before, f"hash unchanged after editing {f.name}"
        f.write_bytes(orig)
        assert code_hash(s, root=fake_root) == before


def test_new_file_and_ignored_paths(fake_root):
    s = fake_root / "strategy_x"
    h = code_hash(s, root=fake_root)
    (s / "runs" / "out.csv").write_text("x")  # runs/ is not covered
    (s / "src" / "__pycache__").mkdir()
    (s / "src" / "__pycache__" / "a.pyc").write_bytes(b"x")
    assert code_hash(s, root=fake_root) == h
    (s / "src" / "helper.py").write_text("x = 1\n")
    assert code_hash(s, root=fake_root) != h
