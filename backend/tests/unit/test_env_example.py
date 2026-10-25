"""Every environment variable read in app/ must be listed in backend/.env.example."""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

BACKEND = Path(__file__).resolve().parents[2]


def _env_names_in_code() -> set[str]:
    """Collect string names passed to os.getenv, os.environ.get and os.environ[...]."""
    names = set()
    for path in (BACKEND / "app").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
            key = None
            if isinstance(node, ast.Call) and node.args:
                func = ast.unparse(node.func)
                if func in ("os.getenv", "os.environ.get", "getenv"):
                    key = node.args[0]
            elif isinstance(node, ast.Subscript) and ast.unparse(node.value) == "os.environ":
                key = node.slice
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                names.add(key.value)
    return names


def _env_names_in_example() -> set[str]:
    names = set()
    for line in (BACKEND / ".env.example").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            names.add(line.split("=", 1)[0].strip())
    return names


def test_code_reads_some_env_vars():
    # Guards against the scanner silently finding nothing
    assert "DATABASE_URL" in _env_names_in_code()


def test_every_env_var_is_in_example():
    missing = _env_names_in_code() - _env_names_in_example()
    assert not missing, f"Add to backend/.env.example: {sorted(missing)}"
