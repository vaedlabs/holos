"""LangChain and LangGraph are gone (Plan P4.12): no module in app/ imports them, or the
old Gemini SDK, and requirements.txt doesn't install them."""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

BACKEND = Path(__file__).resolve().parents[2]
GONE = ("langchain", "langgraph", "langsmith", "google.generativeai")


def _imports(path: Path) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names.add(node.module)
    return names


def _gone(name: str) -> bool:
    return any(name == g or name.startswith(f"{g}.") or name.startswith(f"{g}_")
               for g in GONE)


def test_no_module_in_app_imports_them():
    found = {f"{path.relative_to(BACKEND)}: {name}"
             for path in (BACKEND / "app").rglob("*.py")
             for name in _imports(path) if _gone(name)}
    assert found == set()


def test_requirements_dont_install_them():
    packages = [line.split("==")[0].split("[")[0].strip().lower()
                for line in (BACKEND / "requirements.txt").read_text().splitlines()
                if line.strip() and not line.lstrip().startswith("#")]
    assert [p for p in packages if p.startswith(("langchain", "langgraph", "langsmith"))
            or p == "google-generativeai"] == []


def test_the_check_sees_an_import(tmp_path):
    module = tmp_path / "m.py"
    module.write_text("import os\nfrom langchain_core.messages import HumanMessage\n"
                      "import google.generativeai as genai\n")
    assert {n for n in _imports(module) if _gone(n)} == {"langchain_core.messages",
                                                        "google.generativeai"}
