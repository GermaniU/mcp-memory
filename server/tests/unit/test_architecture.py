"""Hace cumplir la arquitectura vertical slice descrita en docs/ARCHITECTURE.md.

- Una tool solo depende de su propia carpeta y de `shared.types` (el Protocol
  `MemoryStore`), nunca de otra tool ni del store concreto (DIP).
- `shared/` nunca depende de las tools, del server ni del CLI.
"""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[2] / "src" / "mcp_memory"


def _imports(path: Path) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
    return {module for module in modules if module.startswith("mcp_memory")}


def test_tools_depend_only_on_their_slice_and_the_store_protocol():
    for path in (PACKAGE / "tools").rglob("*.py"):
        slice_name = path.relative_to(PACKAGE / "tools").parts[0]
        if slice_name == "__init__.py":
            continue
        own_slice = f"mcp_memory.tools.{slice_name}"
        for module in _imports(path):
            allowed = module == "mcp_memory.shared.types" or module.startswith(own_slice)
            assert allowed, f"{path.relative_to(PACKAGE)} importa {module}"


def test_shared_never_depends_on_tools_server_or_cli():
    forbidden = ("mcp_memory.tools", "mcp_memory.server", "mcp_memory.cli")
    for path in (PACKAGE / "shared").rglob("*.py"):
        for module in _imports(path):
            assert not module.startswith(forbidden), f"{path.relative_to(PACKAGE)} importa {module}"
