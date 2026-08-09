# Arquitectura

## Decisiones de diseño

### Vertical slice

```
server/src/mcp_memory/
├── server.py                 # composition root: wiring FastMCP + dependencias
├── shared/                   # solo lo verdaderamente compartido
│   ├── config.py             # pydantic-settings, .env (DB_PATH, MCP_HOST/PORT, DEFAULT_NAMESPACE)
│   ├── store.py               # SqliteFtsStore (aiosqlite + SQLite FTS5)
│   └── types.py               # Memory + Protocol (MemoryStore)
└── tools/                    # 1 carpeta = 1 slice MCP
    ├── save/handler.py       # SaveInput + async save(...)
    ├── search/handler.py
    ├── delete/handler.py
    ├── list_/handler.py
    ├── update/handler.py
    ├── recent/handler.py
    ├── stats/handler.py
    ├── export/handler.py
    └── import_/handler.py
```

Cada slice es **una función pura** que recibe sus dependencias por keyword arguments. Esto significa:

- **Test unitario sin infra externa**: `pytest tests/unit` corre con un `FakeStore` in-memory. 60 tests, <1s.
- **Añadir una tool nueva**: una carpeta nueva en `tools/`, un decorador `@mcp.tool` en `server.py`. Cero acoplamiento con las existentes (OCP).

### SOLID, sin sobreingeniería

- **SRP**: cada handler hace una cosa. `MemoryStore` solo persiste y busca.
- **DIP**: handlers dependen del `Protocol` `MemoryStore`, no de `SqliteFtsStore` directamente. Por eso el `FakeStore` de los tests es trivial — no requiere herencia.
- **OCP**: `tools/` es abierto a extensión, cerrado a modificación. Añadir una tool ≠ tocar otras.
- **Sin** factories, builders, registries dinámicos. Wiring explícito en `server.build_app`.

### KISS + YAGNI

- Un único archivo SQLite; namespaces se filtran por columna indexada (`idx_memories_namespace`). Sin bases de datos por namespace ni por usuario.
- `recent` y `stats` resuelven server-side con SQL directo (`ORDER BY updated_at DESC LIMIT`, `COUNT`/`DISTINCT`) — sin traer todo a Python para ordenar.
- El servidor expone solo `streamable-http`. stdio se añade cuando un usuario real lo pida.
- `DB_PATH` inyectable vía `.env`. No hay "registry de backends" — cuando exista una segunda implementación real de `MemoryStore` se evaluará la abstracción, no antes (YAGNI aplicado en ambas direcciones: se removió `EmbeddingsClient` por completo en TKT-1470 en vez de dejarlo como abstracción muerta).

### Tests

- **Unit (60)**: `tests/unit/` — `test_store.py` cubre `SqliteFtsStore` contra `:memory:` (schema, CRUD, ranking BM25, normalización de score, escape de sintaxis FTS5); `test_config.py` y `test_cli.py` cubren `Settings`/`mcp-memory check`; `tests/unit/tools/` tiene 1 archivo por slice con `FakeStore` (búsqueda léxica simple por overlap de tokens, no BM25 real — el contrato del handler no depende del motor de ranking).
- **Integration (14)**: `tests/integration/test_e2e.py` — corre contra un `SqliteFtsStore` **real** (archivo temporal) vía el transporte in-memory de FastMCP (`Client(app)`), sin mocks y sin ningún servicio externo. Cubre save→search con ranking BM25, update que re-sincroniza el índice FTS5, recent ordenado, stats, delete, export/import y el escape de sintaxis especial de FTS5 en la query. Corre siempre — no tiene marker de skip: `pytest tests/integration`.

### Datos

```
Memory {
  id: UUID
  content: str
  namespace: str
  tags: list[str]
  metadata: dict
  created_at, updated_at: datetime UTC
  score: float | None  # solo en respuestas de search; normalizado [0,1] dentro
                        # del result set de esa llamada — NO comparable entre
                        # llamadas ni namespaces distintos
}
```

**Schema SQLite** (`shared/store.py::_SCHEMA_SQL`, idempotente vía `IF NOT EXISTS`):

- **`memories`** — tabla normal, fuente de verdad. `id TEXT PRIMARY KEY`, `content`, `namespace`, `tags`/`metadata` serializados como JSON (`TEXT`), `created_at`/`updated_at` como epoch float. Índices B-tree en `namespace`, `updated_at`, `created_at`.
- **`memories_fts`** — tabla virtual FTS5 **external content** (`content='memories'`, `content_rowid='rowid'`), tokenizer `unicode61 remove_diacritics 2` (búsqueda insensible a mayúsculas/acentos) con `tokenchars '-_'` para no partir identificadores tipo `X-Api-Key`. No duplica datos: solo indexa `content` + `tags`.
- **Triggers `memories_ai`/`memories_ad`/`memories_au`** — mantienen `memories_fts` sincronizada en cada INSERT/DELETE/UPDATE de `memories`, automáticamente y en la misma transacción. No hay reindexado manual ni background job.

### Flujo `memory_save`

1. Cliente MCP llama `memory_save(content, namespace?, tags?, metadata?)`.
2. Handler valida (Pydantic) y rechaza contenido vacío.
3. Genera UUID v4 y timestamps.
4. `store.save(memory)` hace `INSERT` en `memories`; el trigger `memories_ai` inserta la fila espejo en `memories_fts`.
5. Devuelve la `Memory` resultante al cliente.

### Flujo `memory_search`

1. Cliente llama `memory_search(query, namespace?, limit)`.
2. El handler pasa `query` tal cual al store — no hay paso de embedding.
3. `store.search(...)` tokeniza la query y construye un `match_expr` de FTS5 donde **cada token se escapa y envuelve en comillas dobles**, unidos con `OR` — neutraliza cualquier sintaxis especial de FTS5 (`AND`/`OR`/`NOT`/`NEAR`, `*`, `:`, `-`) tratándola como texto literal, maximizando recall en vez de fallar la query completa.
4. Ejecuta `SELECT ... FROM memories_fts JOIN memories ... WHERE memories_fts MATCH :match_expr AND namespace = :namespace ORDER BY bm25(memories_fts) ASC LIMIT :limit` (BM25 de SQLite: más negativo = más relevante).
5. Normaliza los `raw_score` de la página de resultados a `[0,1]` con min-max **dentro de esa misma llamada** (no hay un score absoluto comparable entre búsquedas).
6. Devuelve `[Memory]` ordenadas por relevancia descendente, cada una con `score`.

## No-goals (por ahora)

- **Búsqueda semántica.** BM25/FTS5 es léxico — matchea términos, no significado. Si el caso de uso real lo exige (paráfrasis sin overlap de vocabulario), se evaluará un backend de embeddings de vuelta, pero como opción configurable, no como default (ver ADR `mcp-memory-sqlite-fts5-backend`).
- **Multi-usuario / multi-tenant**: el repo asume "una persona, una máquina". Aislamiento entre proyectos = namespaces.
- **Auth/ACL**: escucha en `127.0.0.1` por defecto. Puedes sobreescribir con la variable `MCP_HOST` si necesitas exponerlo en red, pero en ese caso eres responsable de poner un proxy con auth delante.
- **Soporte multimodal** (imágenes, PDF como blobs).
- **Sync entre máquinas**. El archivo SQLite es autocontenido — copiarlo (o `sqlite3 .backup`) es suficiente para 99% de casos.

Si alguno de estos se vuelve necesario, abre un issue con caso de uso real (no especulativo).
