# Conectar tu cliente MCP

El servidor expone **streamable HTTP** en `http://localhost:8765/mcp` (puerto configurable).

---

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

Cualquier cliente que soporte **Streamable HTTP transport** funciona apuntando a `http://localhost:8765/mcp`. Si tu cliente solo soporta stdio, abre un issue — añadiremos un wrapper `docker exec`.

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

// Buscar
{
  "tool": "memory_search",
  "args": {
    "query": "por qué falla la autenticación con X-Api-Key",
    "namespace": "flowordr",
    "limit": 3,
    "min_score": 0.5
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
- **Guarda el WHY, no el WHAT**. La memoria semántica es para razonamiento, no para snapshots de código.
- **Borra cuando algo deje de ser cierto**. La memoria no caduca sola; un `memory_delete` periódico mantiene la calidad de la búsqueda.
- **`min_score`** es tu amigo: 0.5–0.7 evita matches espurios al buscar.
