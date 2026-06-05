<p align="center">
  <img src="docs/assets/og-image.png" alt="MCP Memory — local memory for AI agents via MCP" width="720">
</p>

**English** · [Español](README.es.md)

# MCP Memory — Local memory for AI agents via MCP

> **Bring your AI agent's memory to any machine.**
> Open source MCP server that gives persistent memory with semantic search to Claude Code, OpenCode, Cursor, Continue, and any client compatible with the [Model Context Protocol](https://modelcontextprotocol.io). Embeddings via Ollama, vector search via Qdrant, **100% on your hardware**.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![MCP](https://img.shields.io/badge/MCP-Streamable_HTTP-green)](https://modelcontextprotocol.io)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](server/pyproject.toml)
[![CI](https://github.com/GermaniU/mcp-memory/actions/workflows/ci.yml/badge.svg)](https://github.com/GermaniU/mcp-memory/actions/workflows/ci.yml)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](docker-compose.yml)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

**Tags:** `mcp-server` · `ai-agents` · `ollama` · `qdrant` · `claude-code` · `cursor` · `opencode` · `semantic-search` · `embeddings` · `agent-memory` · `vector-database` · `rag` · `local-first` · `self-hosted`

---

## 💡 Why it exists

AI agents forget everything between conversations. Existing solutions are cloud-only, heavy multi-tenant systems, or locked to a single client. **MCP Memory** solves this with three simple ideas:

1. **Your memory, your machine.** Embeddings and vectors run locally. Zero data in the cloud.
2. **Connect once, works everywhere.** It's a standard MCP server — any client that speaks MCP uses it without custom code.
3. **Zero overhead.** `docker compose up` and you have 9 tools ready for your agent.

---

## ⚡ Quickstart (3 commands)

> **Prerequisite:** an Ollama instance with an embedding model downloaded. Read the warning below before continuing.

```bash
git clone https://github.com/GermaniU/mcp-memory.git
cd mcp-memory
cp .env.example .env && docker compose up -d
```

MCP endpoint: `http://localhost:8765/mcp`. Paste it into your client's config (see [`docs/CLIENTS.md`](docs/CLIENTS.md) (in Spanish) — Claude Code, OpenCode, Cursor, Continue).

---

## ⚠️ Before you start — Ollama and embeddings

This will save you an afternoon of debugging:

> **Ollama Cloud (`https://ollama.com`) does NOT offer embedding models today.** Its cloud catalog is chat LLMs only (kimi-k2, deepseek, gpt-oss, qwen-coder, glm…). `POST https://ollama.com/api/embed` returns **401** even if your API key is valid for `/api/chat`.

**You need embeddings → you need Ollama on a device (local or your own server).**

```bash
# Install Ollama: https://ollama.com/download
ollama pull bge-m3              # 1.2GB · 1024 dim · multilingual — best pick for non-English content (e.g. Spanish)
# alternatives:
ollama pull mxbai-embed-large   # 670MB · 1024 dim · high quality for English
ollama pull nomic-embed-text    # 274MB ·  768 dim · lightweight, English
```

Verify before continuing:

```bash
curl -X POST http://localhost:11434/api/embed \
  -H 'Content-Type: application/json' \
  -d '{"model":"bge-m3","input":"hello"}' | head -c 200
# → {"embeddings":[[-0.13...,0.72...]]}  ← should print a vector array
```

| Setup                                    | `OLLAMA_URL`                              | Works |
|------------------------------------------|-------------------------------------------|-------|
| **Local Ollama** ✅ recommended          | `http://host.docker.internal:11434`       | yes   |
| **Remote Ollama** (your server / VPS)    | `https://ollama.your-domain.com`          | yes   |
| **Ollama Cloud** ❌ no embeddings        | `https://ollama.com`                      | no    |

---

## 🛠 Exposed MCP tools

| Tool             | What it does |
|------------------|--------------|
| `memory_save`    | Save text + tags + metadata. Embeds automatically. |
| `memory_search`  | Semantic search with namespace and `min_score` filters. |
| `memory_update`  | Update content/tags/metadata by id. Re-embeds if content changes. |
| `memory_delete`  | Delete by id. |
| `memory_list`    | Paginated listing by namespace. |
| `memory_recent`  | The last N entries by `updated_at`. |
| `memory_stats`   | Count, namespaces, oldest/newest. |
| `memory_export`  | Export all memories (or a namespace) as JSONL. Returns `count` and a `jsonl` string. |
| `memory_import`  | Import a JSONL string produced by `memory_export`. Re-embeds each entry. Skips id collisions silently. Accepts optional `namespace_override`. |

Schemas and invocation examples in [`docs/CLIENTS.md`](docs/CLIENTS.md) (in Spanish).

---

## 🎯 Current scope

MCP Memory is deliberately small. It does **one thing well: semantic memory for plain text**. It is not a full RAG system, not a knowledge base, not a graph.

### What it DOES
- ✅ Stores and retrieves **plain text** with embeddings.
- ✅ Semantic search with `namespace` and `min_score` filters.
- ✅ Free-form tags + metadata on every entry.
- ✅ 9 standard MCP tools for any compatible agent.
- ✅ Disk persistence (Qdrant volume), backup = `tar`.

### What it does NOT do (yet)
- ❌ **No image or binary support.** Text only.
- ❌ **No PDFs or binary files** — extract the text before saving.
- ❌ **Not multi-tenant.** One person, one machine, one memory (namespaces separate contexts).
- ❌ **No built-in UI.** Manage it from your agent or via curl/MCP.
- ❌ **No cross-machine sync.** Manual backup (`tar` the volume) if you want to move data.
- ❌ **No auth.** Listens on `localhost` only. If you expose it to the internet, put an auth proxy in front.

If you need something from the NO list, open an [issue](https://github.com/GermaniU/mcp-memory/issues) with a real (not speculative) use case — we add things on demand, not on speculation.

---

## 🔌 Connect your client

Ready-to-paste config snippets in [`docs/CLIENTS.md`](docs/CLIENTS.md) (in Spanish):

- 🟦 **Claude Code** — `claude mcp add -s user -t http mcp-memory http://localhost:8765/mcp` (tools show up in new sessions).
- 🟧 **Cursor** — Settings → MCP Servers → Add new MCP Server.
- 🟩 **Continue** (VS Code / JetBrains) — `~/.continue/config.json`.
- 🟪 **OpenCode** — `~/.config/opencode/config.json`.

Ready-to-use JSON snippets in [`examples/`](examples/).

---

## 🧪 Smoke test with curl

To validate the stack without needing an MCP client:

```bash
SESSION=$(curl -sS -D - -o /dev/null -X POST http://localhost:8765/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -H 'MCP-Protocol-Version: 2025-06-18' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"smoke","version":"0.1"}}}' \
  | tr -d '\r' | awk '/^mcp-session-id:/{print $2}')

curl -sS -X POST http://localhost:8765/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -H 'MCP-Protocol-Version: 2025-06-18' \
  -H "mcp-session-id: $SESSION" \
  -d '{"jsonrpc":"2.0","method":"notifications/initialized"}'

curl -sS -X POST http://localhost:8765/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -H 'MCP-Protocol-Version: 2025-06-18' \
  -H "mcp-session-id: $SESSION" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"memory_save","arguments":{"content":"works end-to-end","namespace":"smoke","tags":["ok"]}}}'
```

---

## 🧱 Architecture (vertical slice)

```
┌─ your agent (Claude Code / OpenCode / Cursor / …) ─┐
│           │ MCP streamable HTTP                     │
│           ▼                                         │
│    localhost:8765/mcp                               │
└────────────┬────────────────────────────────────────┘
             │
   ┌─────────▼────────┐         ┌─────────────────┐
   │   mcp-memory     │────────▶│  Ollama (local  │
   │   (Python+MCP)   │         │  or remote)     │
   └─────────┬────────┘         └─────────────────┘
             │
             ▼
   ┌──────────────────┐
   │      Qdrant      │  ← docker compose or standalone
   └──────────────────┘
```

Each MCP tool lives in its own folder (`server/src/mcp_memory/tools/<tool>/handler.py`). Adding a new tool = adding a folder + a decorator in `server.py`. Zero coupling.

Technical details in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) (in Spanish).

---

## 🤝 Contributing

MCP Memory is **a gift to the community** — MIT, no strings attached. PRs, issues, and forks are welcome.

**Rules (summary):**
1. **Clean Code · SOLID · KISS · YAGNI · Vertical slice · Tests first.** PRs without tests for new logic will not be accepted.
2. **Identifiers in English**, comments and commits in Spanish. Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`).
3. **One new tool = one new folder.** Do not touch existing slices unless fixing a bug.
4. **DIP**: external dependencies behind a `Protocol` so tests don't require Docker.
5. **No speculative abstractions.** If there's only 1 implementation, there's no interface.
6. **Document the WHY, not the WHAT.** The function name already tells you what.

Full details and step-by-step workflow in [`CONTRIBUTING.md`](CONTRIBUTING.md).

```bash
# Local development setup (no Docker)
cd server
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/unit -q                  # 27 unit tests, <0.3s, no Docker or Ollama needed
pytest tests/integration -m integration   # real E2E (auto-skip if Qdrant/Ollama are not running)
ruff check src tests scripts
```

---

## 🩹 Troubleshooting (real errors I already hit)

**`401 unauthorized` from the MCP server when calling `memory_save`**
- You're pointing at Ollama Cloud and your account has no embeddings (that's normal today). Change `OLLAMA_URL` to local/remote Ollama.

**`404 Not Found` for `https://ollama.com/api/embed`**
- Same issue: Ollama Cloud does not expose that endpoint.

**`Embedding dim mismatch` / `Collection ... has vector size N`**
- `EMBEDDING_DIM` doesn't match the model's actual dimension, or you reused a collection from a different dim. Adjust `EMBEDDING_DIM` or use a new `QDRANT_COLLECTION`. The server detects this at startup instead of silently corrupting search results.

**`Connection reset by peer` when running `curl http://localhost:8765/mcp`**
- The `Accept: application/json, text/event-stream` header is missing. Without it, FastMCP closes the connection.

**`memory_search` returns empty results**
- Same namespace? If you saved without a namespace, search with `default`. Lower `min_score` to `0.0` to diagnose.

**`mcp-memory` keeps restarting**
- `docker compose logs mcp-memory`. Common causes: model not pulled in your Ollama, `EMBEDDING_DIM` doesn't match the model (bge-m3=1024, not 768), or Qdrant is still starting up.

**Switching embedding models after you already have data**
- Old vectors are not compatible with a different dimension:
  ```bash
  curl -X DELETE http://localhost:6333/collections/mcp_memory
  docker compose up -d --force-recreate mcp-memory
  ```

---

## 📚 Documentation

- [`docs/INSTALL.md`](docs/INSTALL.md) (in Spanish) — detailed installation, environment variables, extended troubleshooting.
- [`docs/CLIENTS.md`](docs/CLIENTS.md) (in Spanish) — config for Claude Code, OpenCode, Cursor, Continue.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) (in Spanish) — technical decisions and rationale.
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — disciplines, workflow, how to add a tool.

---

## 📄 License

[MIT](LICENSE) — use it, fork it, give more people local memory.

---

**Made by [@GermaniU](https://github.com/GermaniU)** with professional software disciplines. If it has been useful to you, a ⭐ helps more people find it. If it broke something, open an issue and we'll fix it.
