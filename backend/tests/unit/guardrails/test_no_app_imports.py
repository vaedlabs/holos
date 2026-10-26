"""Plan C.1: guardrails/ imports nothing from app.* and no LangChain."""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

PACKAGE = Path(__file__).parents[3] / "app" / "guardrails"
BACKEND = PACKAGE.parents[1]


def test_no_module_imports_app_or_langchain():
    paths = list(PACKAGE.glob("*.py"))
    assert {"gate.py", "matcher.py", "loader.py"} <= {p.name for p in paths}
    for path in paths:
        for node in ast.walk(ast.parse(path.read_text())):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module or ""]
            for name in names:
                assert not name.startswith(("app", "langchain", "langgraph")), (path.name, name)


def test_importing_the_gate_loads_nothing_else_from_app():
    """Catches imports the AST check can't see, such as importlib calls."""
    code = (
        "import sys, app.guardrails.gate, app.guardrails.matcher\n"
        "app.guardrails.gate.gate('physical', {'summary': 'x'}, "
        "app.guardrails.types.Profile())\n"
        "print('\\n'.join(m for m in sys.modules if m.split('.')[0] in "
        "('app', 'langchain', 'langgraph')))"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, capture_output=True,
                         text=True, check=True).stdout.split()
    assert out and all(m == "app" or m.startswith("app.guardrails") for m in out), out
