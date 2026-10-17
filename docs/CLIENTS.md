# Conectar tu cliente MCP

El servidor habla dos transportes:

- **stdio** — el cliente lanza `mcp-memory --stdio` como subproceso y habla por stdin/stdout. No hay server de fondo ni puerto abierto. Es lo que esperan Claude Desktop y la mayoría de clientes.
- **Streamable HTTP** — arrancas `mcp-memory` tú y los clientes se conectan a `http://localhost:8765/mcp` (puerto configurable). Útil para compartir un único proceso entre varios clientes o correrlo en Docker.

En los dos modos la memoria vive en el mismo archivo (`DB_PATH`, default `~/.agent-memory/memory.db`): puedes mezclar clientes stdio y HTTP y todos ven las mismas memorias.

---

## Modo stdio (recomendado)

Necesitas [`uv`](https://docs.astral.sh/uv/getting-started/installation/). `uvx` descarga el server desde GitHub la primera vez, lo cachea y lo lanza en cada sesión — no hace falta clonar el repo:

```
uvx --from "git+https://github.com/GermaniU/mcp-memory#subdirectory=server" mcp-memory --stdio
```

Esa URL sigue la rama `main`. Para fijar una versión y que un cambio en `main` no te sorprenda, añade el tag: `git+https://github.com/GermaniU/mcp-memory@v0.6.0#subdirectory=server`.

Si ya lo instalaste localmente (`pip install -e .` dentro de `server/`), usa `mcp-memory --stdio` como comando.

> Para pasar variables (`DB_PATH`, `DEFAULT_NAMESPACE`) usa el bloque `env` de la config del cliente: el proceso no hereda el `.env` de tu proyecto salvo que el cliente lo lance desde ese directorio.

### Claude Desktop

`Settings → Developer → Edit Config` abre `claude_desktop_config.json` (macOS: `~/Library/Application Support/Claude/`, Windows: `%APPDATA%\Claude\`):

```json
{
  "mcpServers": {
    "mcp-memory": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/GermaniU/mcp-memory#subdirectory=server",
        "mcp-memory",
        "--stdio"
      ]
    }
  }
}
```

Reinicia Claude Desktop. Si no aparece, suele ser el `PATH`: las apps de escritorio no leen el de tu shell, así que pon la ruta absoluta de `uvx` en `command` (la que devuelve `which uvx`, típicamente `~/.local/bin/uvx`).

Ver también: [`examples/claude-desktop.json`](../examples/claude-desktop.json).

### Claude Code (stdio)

```bash
claude mcp add -s user mcp-memory -- uvx --from "git+https://github.com/GermaniU/mcp-memory#subdirectory=server" mcp-memory --stdio
```

### Cursor (stdio)

`~/.cursor/mcp.json` (global) o `.cursor/mcp.json` (por proyecto): el mismo bloque `mcpServers` que en Claude Desktop.

### Cualquier otro cliente

Si tu cliente acepta un `command` + `args`, configura `uvx` con los argumentos de arriba. Es el formato estándar de servers MCP stdio.

---

## Modo HTTP

Arranca el server (`mcp-memory`, o `docker run` — ver [`INSTALL.md`](INSTALL.md)) y apunta tu cliente a `http://localhost:8765/mcp`.

## Claude Code

Regístralo con el CLI (scope `user` = disponible en todos tus proyectos):

```bash
claude mcp add -s user -t http mcp-memory http://localhost:8765/mcp
```

> ⚠️ **No edites `~/.claude/settings.json`** — Claude Code lee los servers MCP de `~/.claude.json` (en la raíz de tu home), que es el archivo que `claude mcp add` gestiona. Añadir `mcpServers` a settings.json no tiene ningún efecto.

> ⚠️ **Las tools aparecen en sesiones NUEVAS**, no en la sesión donde registraste el server. `claude mcp list` puede decir `✓ Connected` y aun así tu sesión abierta no las tiene — reiníciala.

Verifica:

```bash
claude mcp list
# mcp-memory: http://localhost:8765/mcp (HTTP) - ✓ Connected
```

Las tools aparecen como `mcp__mcp-memory__memory_save`, etc.

Ver también: [`examples/claude-code.json`](../examples/claude-code.json) — es la entrada que `claude mcp add` deja escrita en `~/.claude.json`, por si prefieres auditarla a mano.

---

## Cursor

`Settings → Cursor Settings → MCP Servers → Add new MCP Server`:

```json
{
  "mcpServers": {
    "mcp-memory": {
      "url": "http://localhost:8765/mcp"
    }
  }
}
```

Ver también: [`examples/cursor.json`](../examples/cursor.json).

---

## Continue (VS Code / JetBrains)

En tu `~/.continue/config.json`:

```json
{
  "experimental": {
    "modelContextProtocolServers": [
      {
        "transport": {
          "type": "streamable-http",
          "url": "http://localhost:8765/mcp"
        }
      }
    ]
  }
}
```

Ver también: [`examples/continue.json`](../examples/continue.json).

---

## OpenCode

Configura el servidor en tu `~/.config/opencode/config.json`:

```json
{
  "mcp": {
    "mcp-memory": {
      "type": "remote",
      "url": "http://localhost:8765/mcp",
      "enabled": true
    }
  }
}
```

Ver también: [`examples/opencode.json`](../examples/opencode.json).

---

## Otros clientes MCP

Cualquier cliente que soporte **Streamable HTTP transport** funciona apuntando a `http://localhost:8765/mcp`. Si solo soporta stdio, usa el [modo stdio](#modo-stdio-recomendado).

---

## Ejemplos de uso desde el agente

Una vez conectado, el agente puede llamar las tools como:

```jsonc
// Guardar
{
  "tool": "memory_save",
  "args": {
    "content": "El TenantMiddleware exige Bearer token además de X-Api-Key.",
    "namespace": "flowordr",
    "tags": ["auth", "gotcha"]
  }
}

// Buscar (léxico — la query comparte términos con el contenido, no solo el significado)
{
  "tool": "memory_search",
  "args": {
    "query": "TenantMiddleware Bearer token X-Api-Key",
    "namespace": "flowordr",
    "limit": 3
  }
}

// Las últimas memorias del proyecto
{
  "tool": "memory_recent",
  "args": { "namespace": "flowordr", "limit": 10 }
}

// Stats globales
{
  "tool": "memory_stats",
  "args": {}
}
```

---

## Buenas prácticas para tu agente

- **Usa namespaces**. Uno por proyecto, agente o "tema". Sin namespace todo cae al pool global y se ensucia.
- **Guarda el WHY, no el WHAT**. La memoria es para razonamiento, no para snapshots de código.
- **Borra cuando algo deje de ser cierto**. La memoria no caduca sola; un `memory_delete` periódico mantiene la calidad de la búsqueda.
- **La búsqueda es léxica (BM25/FTS5), no semántica**: incluye en la query los términos/nombres propios que esperas encontrar en el contenido guardado (identificadores, nombres de error, palabras clave), no solo una paráfrasis del significado.
