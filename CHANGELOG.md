# Changelog

Todos los cambios relevantes del proyecto se documentan en este archivo.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el versionado [SemVer](https://semver.org/lang/es/).

---

## [Unreleased]

### Posibles próximos pasos
- Soporte para `EmbeddingsClient` adicionales (OpenAI, Voyage, Cohere) en paralelo a Ollama.
- Modo Qdrant embedded (sin docker, archivo en disco) para "instalación cero infra".
- Tool `memory_export` (JSONL/Markdown) para portabilidad.
- Imagen oficial publicada en Docker Hub / GHCR.

> Estos son posibles, no garantizados. PRs bienvenidos — lee [CONTRIBUTING.md](CONTRIBUTING.md).

---

## [0.2.0] — 2026-06-03

### Hardening de Qdrant externo + robustez de arranque

Endurecimiento para producción y para el caso "ya tengo un Qdrant". Incluye **un cambio breaking** en la firma de las tools (ver abajo).

### ⚠️ Breaking
- **Inputs de las tools aplanados.** Las 7 tools ahora reciben los campos directos en `arguments` (`{"content": "...", "namespace": "..."}`) en vez del wrapper anidado `{"inp": {...}}`. El schema MCP que ven los clientes ya no está anidado. **Acción requerida:** si llamabas las tools por JSON-RPC crudo con `arguments.inp`, quita ese nivel. Los clientes MCP que generan argumentos a partir del schema no requieren cambios.

### Added
- **Validación de dimensión al arrancar.** `ensure_collection()` es idempotente: si la colección ya existe, valida que el `size` de sus vectores coincida con `EMBEDDING_DIM`; si difiere, aborta con un error claro en vez de corromper la búsqueda.
- **Validación de dimensión del embedding.** El cliente Ollama compara el vector devuelto contra `EMBEDDING_DIM` y falla con mensaje explícito (modelo + dim devuelto + dim configurado) si no coinciden.
- **Endpoint `GET /health`** → `{"status":"ok","qdrant":true|false}` (200 / 503). Pensado para healthchecks de Docker / orquestadores.
- **Healthcheck del service `mcp-memory`** en `docker-compose.yml` usando `/health`.
- **Arranque resiliente:** reintento con backoff exponencial (8 intentos, ~30s) alrededor de `ensure_collection()` mientras Qdrant levanta. Los errores de config (dim mismatch) fallan rápido, sin reintentar.
- **Índice de payload `created_at`** (float) además de `namespace` y `updated_at`, para ordenar `oldest` server-side.
- **Modo "Qdrant externo"**: `QDRANT_URL` overridable en el compose (`${QDRANT_URL:-http://qdrant:6333}`) y `depends_on` del Qdrant bundled marcado `required: false`, de modo que `docker compose up mcp-memory` levanta solo el server contra tu Qdrant. Documentado como **Modo C** en [INSTALL](docs/INSTALL.md).
- **Tests de integración reales** (`server/tests/integration/`, marker `integration`): corren contra Qdrant + Ollama de verdad vía el transporte in-memory de FastMCP, sobre una colección efímera (`mcp_memory_itest`) que se crea y borra por sesión. Cubren save→search cross-keyword, update re-embed, recent ordenado, stats, delete y el error de dim mismatch. Auto-skip limpio si los servicios no responden.

### Changed
- **Embeddings migrados a `POST /api/embed`** (`{"model":...,"input":...}` → `{"embeddings":[[...]]}`), el endpoint moderno de Ollama, en lugar del legacy `/api/embeddings`.
- **`recent()` y `stats()` ahora son server-side.** `recent()` usa `scroll` con `OrderBy(updated_at, DESC)` y `limit` real (antes traía hasta 10k puntos y ordenaba en Python). `stats()` usa `count(exact=True)`, `facet(key="namespace")` y dos `scroll` ordenados de `limit=1` para oldest/newest. El shape de salida no cambia.
- **Índices de payload (re)asegurados en cada arranque**, también cuando la colección ya existe (idempotente: ignora el error de índice ya creado).
- `docker-compose.yml`: imagen bump a `mcp-memory:0.2.0`.

### Migración desde 0.1.0
- Reemplaza `{"inp": {...}}` por los campos directos en cualquier llamada JSON-RPC cruda (ver Breaking).
- Si reutilizabas una colección con dimensión distinta a `EMBEDDING_DIM`, el server ahora abortará al arrancar: corrige `EMBEDDING_DIM` o usa una `QDRANT_COLLECTION` nueva.

---

## [0.1.0] — 2026-05-07

### Reescritura completa: de Node.js stdio a Python MCP HTTP

Primera versión publicable. La implementación previa en Node.js se eliminó del árbol vivo — su trazabilidad permanece en el git history (`git log --before=2026-05-07`).

### Added
- Servidor MCP en **Python 3.11** con [FastMCP](https://gofastmcp.com) (Streamable HTTP, `:8765/mcp`).
- **Vertical-slice architecture**: una carpeta por tool en `server/src/mcp_memory/tools/` con handler aislado.
- **7 tools MCP**:
  - `memory_save` — guardar texto + tags + metadata, embebe automático.
  - `memory_search` — búsqueda semántica con filtro por namespace y `min_score`.
  - `memory_update` — modificar contenido/tags/metadata por id, re-embebe si cambia el contenido.
  - `memory_delete` — borrar por id.
  - `memory_list` — paginación por namespace.
  - `memory_recent` — últimas N por `updated_at`.
  - `memory_stats` — conteo, namespaces, oldest/newest.
- **Namespaces** para separar memoria por proyecto/agente (filtro por payload con índice keyword en Qdrant).
- **Ollama configurable** vía `OLLAMA_URL` + `OLLAMA_API_KEY`: soporta Ollama local, remoto y, en el futuro, cualquier endpoint Ollama-compatible.
- **Modelo de embeddings parametrizable** (`EMBEDDING_MODEL` + `EMBEDDING_DIM`). Default: `bge-m3` (multilingüe, 1024 dims).
- **`docker-compose.yml`** mínimo: solo Qdrant + mcp-memory. Ollama lo aporta el usuario.
- **16 tests unitarios** con `FakeStore` y `FakeEmbeddings` — corren en <0.3s sin Docker ni Ollama.
- **Documentación completa**: [README](README.md), [INSTALL](docs/INSTALL.md), [CLIENTS](docs/CLIENTS.md), [ARCHITECTURE](docs/ARCHITECTURE.md), [CONTRIBUTING](CONTRIBUTING.md).
- **Ejemplos de configuración** listos para Claude Code, OpenCode, Cursor, Continue en [`examples/`](examples/).
- **Imagen OG / social preview** (`docs/assets/og-image.png`).

### Changed
- Transport pasó de **stdio** (Node legacy) a **Streamable HTTP** — funciona con cualquier cliente MCP moderno sin wrappers.
- Aislamiento conceptual cambió de `collection` (Node legacy) a `namespace` — una sola colección Qdrant + filtro por payload.
- Modelo de embeddings default: `nomic-embed-text` (Node, 768 dim, inglés) → `bge-m3` (Python, 1024 dim, multilingüe).
- Setup pasó de paths hardcoded `/root/workspace/...` (Node legacy) a `docker compose up -d` self-contained.

### Discovered (gotchas documentadas)
- **Ollama Cloud (`https://ollama.com`) no expone modelos de embedding** — su catálogo cloud es solo chat (kimi-k2, deepseek, gpt-oss, etc.). `POST /api/embed` devuelve 401 incluso con API key válida para `/api/chat`. Documentado prominentemente en README + INSTALL.
- El protocolo MCP **exige** `Accept: application/json, text/event-stream`. Sin él, FastMCP devuelve 406 / connection reset.
- `EMBEDDING_DIM` debe coincidir EXACTO con la dimensión real del modelo, o Qdrant falla al insertar/buscar.

### Disciplinas aplicadas
Clean Code · SOLID (DIP con `Protocol`) · KISS · YAGNI · Vertical slice · Tests primero.

---

## [Legacy] — 2026-02-26 (Node.js, eliminado del árbol)

Primera implementación. **Eliminada del repo en 2026-05-07** (commit posterior). El código vive en el git history: `git log --all -- 'legacy/**'` lo recupera para inspección histórica.

### Highlights de la versión legacy
- Node.js, MCP **stdio** (`hook/memory-hook.js`, ~580 líneas).
- Asumía Qdrant + proxy de embeddings ya levantados externamente.
- 5 tools: `memory_add`, `memory_sync`, `memory_search`, `memory_delete`, `memory_stats`.
- `nomic-embed-text` (768 dim) como embedding.
- Aislamiento por `collection` (no namespace).
- Setup con paths hardcoded `/root/workspace/scratch/...`.

### Por qué se reescribió
- Cero infra externa: el nuevo stack arranca con un `docker compose up -d`.
- Mantenibilidad: vertical slice + tests unitarios + Pydantic vs ~580 líneas planas en JS sin tests automatizados.
- Multilingüe: `bge-m3` da resultados drásticamente mejores en español que `nomic-embed-text`.

---

[Unreleased]: https://github.com/GermaniU/mcp-memory/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/GermaniU/mcp-memory/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/GermaniU/mcp-memory/releases/tag/v0.1.0
