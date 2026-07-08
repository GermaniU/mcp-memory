# CLAUDE.md — mcp-memory

Convenciones del proyecto para sesiones de Claude Code.

---

## Stack

- **Python 3.11+** · FastMCP (Streamable HTTP) · Qdrant · Ollama embeddings.
- **Arquitectura vertical slice**: cada tool vive en `server/src/mcp_memory/tools/<tool>/handler.py`. Añadir una tool = añadir una carpeta + un decorator en `server.py`.
- **Tests**: `pytest tests/unit -q` (unit, sin Docker, <0.3s). `pytest tests/integration -m integration` (requiere Qdrant + Ollama corriendo).
- **Linting**: `ruff check src tests scripts`.

## Convenciones de código

- Identifiers en **inglés**. Comentarios y commits en **español**.
- Conventional Commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`.
- **DIP**: dependencias externas (store, embeddings) detrás de `Protocol` — los tests no deben requerir Docker.
- Sin abstracciones especulativas (YAGNI).

## Regla anti-drift de docs

**Todo PR que agregue, cambie o elimine tools MCP debe actualizar `README.md` + `README.es.md` (+ `CHANGELOG.md`) en el mismo diff. Un PR de tools sin docs se rechaza.**

Esto incluye: tabla de tools, conteo de tools ("N tools" en quickstart y scope), y tests unitarios si el número cambia.
