"""Deterministic SHA-256 over a strategy's code + shared code/config."""
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SKIP_DIRS = {"__pycache__", ".pytest_cache", ".ipynb_checkpoints"}
_SKIP_SUFFIX = {".pyc", ".pyo"}


def covered_files(strategy_dir, root: Path | None = None) -> list[Path]:
    root = Path(root) if root else ROOT
    sdir = Path(strategy_dir)
    if not sdir.is_absolute():
        sdir = root / sdir
    dirs = [sdir / "src", sdir / "configs", root / "common", root / "config"]
    files = []
    for d in dirs:
        if not d.exists():
            continue
        for p in d.rglob("*"):
            if p.is_file() and not (set(p.relative_to(root).parts) & _SKIP_DIRS) \
                    and p.suffix not in _SKIP_SUFFIX and p.name != ".DS_Store":
                files.append(p)
    return sorted(files, key=lambda p: p.relative_to(root).as_posix())


def code_hash(strategy_dir, root: Path | None = None) -> str:
    """SHA-256 over sorted (relative path, contents) of strategy src/ + configs/ + common/ + config/."""
    root = Path(root) if root else ROOT
    h = hashlib.sha256()
    for p in covered_files(strategy_dir, root):
        h.update(p.relative_to(root).as_posix().encode())
        h.update(b"\0")
        h.update(p.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def file_hash(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
