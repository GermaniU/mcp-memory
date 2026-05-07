# OpenClaw System Memory

> **Memoria persistente con búsqueda semántica para tus agentes IA, vía MCP. Levantas Qdrant, conectas tu Ollama, pegas la URL en tu cliente y listo.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![MCP](https://img.shields.io/badge/MCP-Streamable_HTTP-green)](https://modelcontextprotocol.io)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](server/pyproject.toml)

Servidor [MCP](https://modelcontextprotocol.io) que da a cualquier cliente compatible (Claude Code, OpenCode, Cursor, Continue…) **memoria con búsqueda semántica** corriendo en tu máquina:

- 🦙 Embeddings vía cualquier endpoint compatible Ollama.
- 🔍 Vector search con [Qdrant](https://qdrant.tech) (cosine + payload indexes).
- 🧩 Namespaces para separar memoria por proyecto/agente.
- 🛠 7 tools MCP: `memory_save`, `memory_search`, `memory_delete`, `memory_list`, `memory_update`, `memory_recent`, `memory_stats`.
- 🐳 Docker-friendly pero **no obligatorio**.

---

## ⚠️ Antes de empezar — sobre Ollama y embeddings

Esto te ahorra una tarde de debugging:

> **Ollama Cloud (`https://ollama.com`) hoy NO ofrece modelos de embedding.** Su catálogo cloud es solo de LLMs de chat (kimi-k2, deepseek, gpt-oss, qwen-coder, glm, etc.). Una llamada a `POST https://ollama.com/api/embed` devuelve **401** aunque tu API key sea válida para `/api/chat`.

**Necesitas embeddings → necesitas un Ollama con el modelo en el dispositivo.** Opciones:

| Setup | `OLLAMA_URL` | Cuándo |
|---|---|---|
| **Ollama local en tu Mac/Linux** ✅ recomendado | `http://host.docker.internal:11434` | Tienes Ollama instalado y descargaste un modelo de embeddings |
| **Ollama remoto** (tu servidor, VPS) | `https://ollama.tu-dominio.com` | Tienes Ollama corriendo en otro host |
| **Ollama Cloud** ❌ no funciona para embeddings | `https://ollama.com` | Solo chat, sin embeddings |

### Modelos de embedding recomendados

```bash
ollama pull bge-m3              # 1.2GB, 1024 dim, multilingüe (recomendado para español)
ollama pull mxbai-embed-large   # 670MB, 1024 dim, alta calidad en inglés
ollama pull nomic-embed-text    # 274MB, 768 dim, ligero, inglés
```

Verifica que tu Ollama responde antes de levantar el stack:

```bash
curl -X POST http://localhost:11434/api/embeddings \
  -H 'Content-Type: application/json' \
  -d '{"model":"bge-m3","prompt":"hola"}' | head -c 200
# → {"embedding":[-0.13...,0.72...]}  ← debe devolver un array de floats
```

---

## ⚡ Quickstart con Docker

```bash
git clone https://github.com/GermaniU/GermaniU-OpenClawSystemMemory.git
cd GermaniU-OpenClawSystemMemory
cp .env.example .env

# Edita .env — el default ya apunta a Ollama local. Si está en otra parte, ajústalo.
# OLLAMA_URL=http://host.docker.internal:11434
# EMBEDDING_MODEL=bge-m3
# EMBEDDING_DIM=1024

docker compose up -d
```

Solo levanta dos contenedores: **Qdrant** (vector DB) y **mcp-memory** (servidor MCP). Ollama lo aportas tú.

Endpoint MCP: `http://localhost:8765/mcp`. Pégalo en la config de tu cliente — ver [`docs/CLIENTS.md`](docs/CLIENTS.md).

---

## ⚡ Quickstart sin Docker (Python local)

Si ya tienes Qdrant en otro lado y prefieres correr el MCP server como proceso Python:

```bash
git clone https://github.com/GermaniU/GermaniU-OpenClawSystemMemory.git
cd GermaniU-OpenClawSystemMemory/server
python -m venv .venv && source .venv/bin/activate
pip install -e .

export OLLAMA_URL=http://localhost:11434
export QDRANT_URL=http://localhost:6333
export EMBEDDING_MODEL=bge-m3
export EMBEDDING_DIM=1024

python -m openclaw_memory
# Listening on http://0.0.0.0:8765/mcp
```

---

## 🧪 Smoke test — verificar que todo funciona (curl)

El protocolo MCP exige el header `Accept: application/json, text/event-stream` y un `mcp-session-id` después del `initialize`. Aquí el test mínimo (copia-pega):

```bash
# 1. Initialize y captura session id
SESSION=$(curl -sS -D - -o /dev/null -X POST http://localhost:8765/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -H 'MCP-Protocol-Version: 2025-06-18' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"smoke","version":"0.1"}}}' \
  | tr -d '\r' | awk '/^mcp-session-id:/{print $2}')
echo "session=$SESSION"

# 2. Notificación initialized (obligatoria por protocolo)
curl -sS -X POST http://localhost:8765/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -H 'MCP-Protocol-Version: 2025-06-18' \
  -H "mcp-session-id: $SESSION" \
  -d '{"jsonrpc":"2.0","method":"notifications/initialized"}'

# 3. memory_save
curl -sS -X POST http://localhost:8765/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -H 'MCP-Protocol-Version: 2025-06-18' \
  -H "mcp-session-id: $SESSION" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"memory_save","arguments":{"inp":{"content":"funciona end-to-end","namespace":"smoke","tags":["ok"]}}}}'

# 4. memory_search
curl -sS -X POST http://localhost:8765/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -H 'MCP-Protocol-Version: 2025-06-18' \
  -H "mcp-session-id: $SESSION" \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"memory_search","arguments":{"inp":{"query":"funciona?","namespace":"smoke"}}}}'
```

Debes ver SSE con un JSON que incluye un `id` UUID en `memory_save` y un array con `score > 0` en `memory_search`.

---

## 🛠 Tools expuestos

| Tool             | Para qué |
|------------------|----------|
| `memory_save`    | Guardar texto + tags + metadata; embebe automáticamente. |
| `memory_search`  | Búsqueda semántica con filtro por namespace y `min_score`. |
| `memory_update`  | Cambiar contenido/tags/metadata por id. Re-embebe si cambia el contenido. |
| `memory_delete`  | Borrar por id. |
| `memory_list`    | Paginado por namespace. |
| `memory_recent`  | Las últimas N por `updated_at`. |
| `memory_stats`   | Conteo, namespaces, oldest/newest. |

---

## 🧱 Arquitectura

```
┌─ tu agente (Claude Code / OpenCode / Cursor / …) ─┐
│           │ MCP streamable HTTP                    │
│           ▼                                        │
│    localhost:8765/mcp                              │
└────────────┬───────────────────────────────────────┘
             │
   ┌─────────▼────────┐         ┌─────────────────┐
   │   mcp-memory     │────────▶│  Ollama (local  │
   │   (Python+MCP)   │         │  o remoto)      │
   └─────────┬────────┘         └─────────────────┘
             │
             ▼
   ┌──────────────────┐
   │      Qdrant      │  ← docker compose o standalone
   └──────────────────┘
```

Vertical-slice: cada tool MCP vive en su propia carpeta con handler aislado, fácil de entender y testear sin levantar nada (`pytest tests/unit`, 16 tests, <0.3s).

Detalle: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## 🩹 Troubleshooting (los errores que ya pisé yo)

**`401 unauthorized` desde el MCP server al hacer `memory_save`**
- Tu `OLLAMA_URL` apunta a `https://ollama.com` y tu cuenta no tiene embeddings (es lo normal hoy). Cambia `OLLAMA_URL` a tu Ollama local o remoto.

**`404 Not Found` para `https://ollama.com/api/embeddings`**
- Mismo problema: Ollama Cloud no expone ese endpoint. La versión moderna usa `/api/embed` y aún así da 401 sin acceso a embeddings.

**`Connection reset by peer` al hacer `curl http://localhost:8765/mcp`**
- Falta el header `Accept: application/json, text/event-stream`. Sin él, FastMCP cierra la conexión. Mira el smoke test arriba.

**Mi Ollama corre en mi Mac, no me conecta desde el contenedor**
- Usa `OLLAMA_URL=http://host.docker.internal:11434` (Docker Desktop lo resuelve automáticamente). En Linux nativo el compose ya añade `extra_hosts: host-gateway`.

**`memory_search` devuelve vacío**
- Verifica el namespace: si guardaste sin namespace, busca con el namespace `default`.
- Baja `min_score` a `0.0` para diagnosticar; en uso real súbelo a 0.5–0.7.

**El contenedor `mcp-memory` reinicia en bucle**
- `docker compose logs mcp-memory`. Causas frecuentes: modelo `EMBEDDING_MODEL` no descargado en tu Ollama, `EMBEDDING_DIM` no coincide con el modelo (ej: pones `768` con `bge-m3` que es `1024`), o Qdrant aún arrancando.

**Cambiar de modelo de embedding después de tener datos**
- Los vectores viejos no son compatibles con otra dimensión. Borra la colección y reingiere:
  ```bash
  curl -X DELETE http://localhost:6333/collections/openclaw_memory
  docker compose up -d --force-recreate mcp-memory
  ```

---

## 📚 Docs

- [`docs/INSTALL.md`](docs/INSTALL.md) — instalación detallada, variables, troubleshooting extendido.
- [`docs/CLIENTS.md`](docs/CLIENTS.md) — config para Claude Code, OpenCode, Cursor, Continue.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — decisiones técnicas y por qué.
- [`legacy/`](legacy/) — primera implementación en Node (deprecada, se conserva como referencia).

---

## 🤝 Cómo contribuir

```bash
cd server
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q                     # 16 tests unitarios sin Docker ni Ollama
ruff check src tests
```

Disciplinas del repo: **Clean Code · SOLID · KISS · YAGNI · vertical slice · tests primero**. Una tool nueva = una carpeta nueva en `server/src/openclaw_memory/tools/`.

---

## 📄 Licencia

[MIT](LICENSE) — úsalo, fórkalo, regálale a otra gente más memoria local.
