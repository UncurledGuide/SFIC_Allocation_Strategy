"""(a) AST import isolation: strategies never import each other and import project code only
from common/ (or their own package); common/ contains no strategy imports or strategy logic."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STRATS = ["strategy_1_residual_momentum", "strategy_2_vol_managed", "strategy_3_combined"]
PROJECT_TOP = set(STRATS) | {"common", "evaluation", "data", "tests", "config"}
STRATEGY_WORDS = ("momentum", "residual", "vol_managed", "realized_variance", "52w", "week_high")


def _imports(path: Path):
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield a.name, 0
        elif isinstance(node, ast.ImportFrom):
            yield (node.module or ""), node.level


def _py(d: Path):
    return [p for p in d.rglob("*.py") if "__pycache__" not in p.parts]


def test_strategies_import_only_common_or_self():
    for s in STRATS:
        for p in _py(ROOT / s):
            for mod, level in _imports(p):
                if level:  # relative import stays inside the package
                    continue
                top = mod.split(".")[0]
                if top in PROJECT_TOP:
                    assert top in ("common", s), f"{p.relative_to(ROOT)} imports {mod}"
                assert "test_holdout" not in mod


def test_strategies_never_reference_each_other_or_holdout_paths():
    for s in STRATS:
        others = [o for o in STRATS if o != s]
        for p in (ROOT / s).rglob("*"):
            if p.is_file() and p.suffix in {".py", ".yaml", ".yml", ".json", ".toml"}:
                txt = p.read_text(errors="ignore")
                for other in others:
                    assert other not in txt, f"{p.relative_to(ROOT)} references {other}"
                assert "test_holdout" not in txt, f"{p.relative_to(ROOT)} references test_holdout"
                assert "HoldoutLoader" not in txt, f"{p.relative_to(ROOT)} references HoldoutLoader"


def test_common_has_no_strategy_imports_or_logic():
    for p in _py(ROOT / "common"):
        for mod, level in _imports(p):
            assert mod.split(".")[0] not in STRATS, f"{p.name} imports a strategy"
        defs = [n.name.lower() for n in ast.walk(ast.parse(p.read_text()))
                if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
        for d in defs:
            assert not any(w in d for w in STRATEGY_WORDS), f"common/{p.name} defines strategy-like {d}"
