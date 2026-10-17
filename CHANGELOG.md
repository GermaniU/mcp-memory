# Changelog

Todos los cambios relevantes del proyecto se documentan en este archivo.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el versionado [SemVer](https://semver.org/lang/es/).

---

## [Unreleased]

---

## [0.6.0] — 2026-10-17

### Added
- **Transporte stdio**: `mcp-memory --stdio` (o `MCP_TRANSPORT=stdio`) sirve MCP por stdin/stdout, para que el cliente lance el proceso él solo — sin server de fondo ni puerto abierto. Es lo que piden Claude Desktop y la mayoría de clientes. Con `uv` no hace falta clonar: `uvx --from "git+https://github.com/GermaniU/mcp-memory#subdirectory=server" mcp-memory --stdio`. Los logs van a stderr para no corromper el canal JSON-RPC; un test E2E lanza el subproceso real y lo verifica. HTTP sigue siendo el default (`--http` lo fuerza).
- Docs: configuración stdio para Claude Desktop, Claude Code y Cursor en `docs/CLIENTS.md`, y `examples/claude-desktop.json`.
- **MCP Registry**: `server.json` (namespace `io.github.GermaniU/mcp-memory`, imagen OCI de GHCR por stdio) y job `mcp-registry` en `release.yml`, que lo publica con login OIDC de GitHub Actions al empujar un tag `v*`. La imagen lleva el label `io.modelcontextprotocol.server.name` que el registry usa para verificar la propiedad; CI comprueba que coincida con `server.json`.
- Imagen Docker: `ENTRYPOINT` en vez de `CMD`, para que `docker run -i --rm ghcr.io/germaniu/mcp-memory --stdio` funcione; el `HEALTHCHECK` no marca `unhealthy` un contenedor stdio. CI hace un smoke test stdio del contenedor.
- **Anotaciones MCP en las 9 tools** (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`): `memory_search`/`list`/`recent`/`stats`/`export` se marcan como solo lectura, `memory_update`/`delete` como destructivas y `memory_save`/`import` como escrituras no destructivas. Los clientes que las soportan pueden auto-aprobar lecturas y pedir confirmación antes de modificar o borrar.
- **`instructions` del servidor**: al conectarse, el agente recibe una guía breve de uso (buscar antes de responder sobre el usuario, queries con palabras clave literales porque la búsqueda es léxica, preferir `memory_update` a duplicar).
- CLI: `mcp-memory --version` / `-V` y `mcp-memory --help`.
- `HEALTHCHECK` en el `Dockerfile` (consulta `/health` con la stdlib, sin instalar curl); el smoke test de CI verifica que el contenedor llegue a `healthy`.
- CI: los tests de integración (`tests/integration`) corren en toda la matriz de Python — antes solo corrían los unitarios.
- `pyproject.toml`: `keywords`, `classifiers` y `[project.urls]` para que el paquete muestre metadatos útiles.

### Fixed
- `mcp-memory --help` (o cualquier argumento desconocido, como un typo) **arrancaba el servidor** en vez de mostrar ayuda o fallar. Ahora el CLI usa `argparse`: `--help` muestra la ayuda y un argumento inválido sale con código 2. `check`, `--check` y `-c` siguen funcionando.
- `memory_update` aceptaba `content` vacío o solo espacios (dejando una memoria imposible de encontrar por FTS5), mientras que `memory_save` lo rechazaba. Ahora aplica el mismo criterio: recorta espacios y rechaza contenido vacío sin modificar la memoria.
- La descripción de `memory_export` mencionaba "no vectors", resto del backend de embeddings retirado en 0.4.0.

### Removed
- Restos del backend anterior (vectorial + embeddings) en docs, tests, `.gitignore` y el smoke script. El CHANGELOG de 0.1.0–0.4.0 se resume en «Historia previa», porque ese código nunca formó parte de este repositorio.

### Changed
- `CLAUDE.md`: regla para no publicar enlaces de sesión, atribución ni datos del entorno en commits y PRs.
- Enlaces del final del CHANGELOG: apuntaban a tags (`v0.1.0`…`v0.4.0`) que no existen en el repo.
- Dependencias: pisos mínimos subidos a `pydantic>=2.13.5`, `pydantic-settings>=2.15.0`, `aiosqlite>=0.22.1` y, en dev, `pytest-asyncio>=1.4.0` y `ruff>=0.16.9`. `uv.lock` regenerado (seguía declarando `mcp-memory` 0.4.0). Release: `docker/setup-buildx-action@v4` y `docker/metadata-action@v6` (runtime Node 24, sin cambios en los inputs usados).
- Dependencias: `fastmcp>=4.1.0` (el piso anterior, `>=2.5.0`, no se probaba: el lock ya usaba 3.4.7), `pydantic>=2.14.1` y, en dev, `pytest>=9.1.1` y `ruff>=0.17.0`. `uv.lock` regenerado (fastmcp 4.1.0, mcp 2.3.0).
- Plantilla de bug report actualizada al backend actual (pide `mcp-memory check`, health y `MCP_CORS_ORIGINS`) y enlace al reporte privado de vulnerabilidades.
- Imagen de portada (`docs/assets/og-image.png`/`.svg`) rediseñada: icono de base de datos con búsqueda BM25, texto acorde al backend actual (SQLite + FTS5) y mismo estilo que tor-mcp-proxy.

---

## [0.5.0] — 2026-10-03

Primera versión del repositorio con historial limpio.

### 🔒 Security
- **CORS cerrado por defecto.** Antes el transporte HTTP respondía `Access-Control-Allow-Origin: *`, lo que permitía a **cualquier página web abierta en tu navegador** leer, exportar o borrar tus memorias con un `fetch` a `127.0.0.1:8765`. Ahora no se añade CORS salvo que lo pidas con `MCP_CORS_ORIGINS`, y solo para los orígenes exactos que listes. Hay tests de regresión en `tests/unit/test_http_security.py`.
- La imagen Docker corre como usuario sin privilegios (`uid 10001`), escucha en `0.0.0.0` dentro del contenedor (antes `127.0.0.1`, que dejaba el contenedor inaccesible) y guarda la base en el volumen `/data`.
- Nuevo `SECURITY.md` con el modelo de amenazas y el canal privado de reporte.

### ⚠️ Breaking
- Si un cliente **web** (navegador o gateway HTTP que corra en el navegador) llamaba al server desde otro origen, ahora necesita `MCP_CORS_ORIGINS=<origen>`. Los clientes MCP nativos (Claude Code, Cursor, OpenCode, Continue) no se ven afectados: no usan CORS.

### Added
- CI: auditoría de dependencias con `pip-audit`, build y smoke test de la imagen Docker, y `permissions: contents: read`.
- `tests/unit/test_architecture.py`: hace cumplir la arquitectura vertical slice (una tool solo depende de su carpeta y del `Protocol` `MemoryStore`; `shared/` nunca depende de tools, server ni CLI).
- Sección de Docker en `docs/INSTALL.md`.

### Changed
- `actions/checkout` v7 en todos los workflows.
- `CLAUDE.md`: la regla anti-drift apunta a `README.en.md` (antes mencionaba un `README.es.md` inexistente).

---

## Historia previa (antes del repositorio público)

El historial de git de este repo empieza en 0.5.0. Las versiones anteriores (0.1.0–0.4.0, 2026-05 a 2026-08, y una primera implementación en Node.js) no están publicadas; en resumen:

- **0.1.0–0.3.0**: reescritura de Node.js (stdio) a Python + FastMCP (Streamable HTTP), arquitectura vertical slice, namespaces, `/health`, `memory_export`/`memory_import` y CI. El almacenamiento usaba un backend vectorial externo con embeddings.
- **0.4.0**: el backend se reemplazó por SQLite + FTS5 (BM25) para eliminar toda infra externa. `memory_search` pasó de búsqueda semántica a léxica, desapareció `min_score` y se introdujo `DB_PATH`.

---

[Unreleased]: https://github.com/GermaniU/mcp-memory/compare/v0.6.0...HEAD
[0.6.0]: https://github.com/GermaniU/mcp-memory/compare/83f2f88...v0.6.0
[0.5.0]: https://github.com/GermaniU/mcp-memory/commit/83f2f88
