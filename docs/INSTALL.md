# Instalación detallada

MCP Memory corre como un proceso Python nativo. No hay Docker, no hay servicios externos que levantar — el único estado es un archivo SQLite local.

---

## Requisitos

- **Python 3.11+** con FTS5 compilado en el módulo estándar `sqlite3`. Los builds de Homebrew (macOS), python.org (macOS/Windows) y la mayoría de distros Linux ya lo traen. Verifícalo con:
  ```bash
  python3 -c "import sqlite3; sqlite3.connect(':memory:').execute('CREATE VIRTUAL TABLE t USING fts5(x)')"
  ```
  Si esto falla con `no such module: fts5`, ver [Troubleshooting](#troubleshooting) abajo.

---

## Instalación

```bash
git clone https://github.com/GermaniU/mcp-memory.git
cd mcp-memory/server
python -m venv .venv && source .venv/bin/activate
pip install -e .

python -m mcp_memory
# o, si el venv está activo: mcp-memory
```

Alternativa sin crear un venv manual, usando [`uv`](https://docs.astral.sh/uv/):

```bash
cd mcp-memory/server
uvx --from . mcp-memory
```

El server queda escuchando en `http://localhost:8765/mcp`. Al arrancar crea (si no existen) el archivo `DB_PATH` y su schema: tabla `memories` + tabla virtual `memories_fts` (FTS5) con los triggers que las mantienen sincronizadas.

---

## Variables de entorno

Todas opcionales — hay defaults sensatos para uso local. Configúralas con `export` o en un `.env` en el `cwd` desde el que arrancas el server (copia `.env.example` como punto de partida).

| Variable            | Default                       | Descripción |
|---------------------|--------------------------------|-------------|
| `DB_PATH`           | `~/.agent-memory/memory.db`   | Ruta del archivo SQLite. `~` se expande. Usa `:memory:` para una instancia efímera (se pierde todo al cerrar el proceso — solo para pruebas). |
| `MCP_HOST`          | `127.0.0.1`                    | Host donde escucha el server MCP. |
| `MCP_PORT`          | `8765`                         | Puerto del server MCP. |
| `DEFAULT_NAMESPACE` | `default`                      | Namespace usado cuando el cliente no especifica uno. |

```bash
export DB_PATH=~/proyectos/mi-agente/memory.db
python -m mcp_memory
```

> Tip: si apuntas `DB_PATH` a una ruta dentro de un repo sincronizado (Dropbox, iCloud, un volumen compartido), tienes memoria portátil entre máquinas sin montar nada — es un archivo plano.

---

## Diagnóstico

`mcp-memory check` valida en un solo paso: soporte de FTS5 en tu Python y accesibilidad de `DB_PATH` (directorio padre escribible, conteo de memorias si el archivo ya existe).

```bash
mcp-memory check
```

Salida esperada (instalación nueva):

```
==================================================
 MCP Memory Diagnostics (mcp-memory check)
==================================================
Config:
  · DB_PATH:            /Users/tu-usuario/.agent-memory/memory.db
  · MCP_HOST/PORT:      127.0.0.1:8765
  · DEFAULT_NAMESPACE:  default
--------------------------------------------------

[1/2] Checking SQLite FTS5 support...
  ✓ FTS5 is compiled in this Python's sqlite3 module.

[2/2] Checking DB_PATH...
  ✓ Parent directory is writable: /Users/tu-usuario/.agent-memory
  [i] Database file does not exist yet at '.../memory.db'.
     A fresh DB with 0 memories will be created on server start.
```

---

## Healthcheck

El server expone `GET /health` (sin prefijo `/mcp`):

```bash
curl http://localhost:8765/health
# {"status":"ok","db":true}   -> 200 si la conexión SQLite responde
# {"status":"ok","db":false}  -> 503 si no responde
```

Útil para healthchecks de systemd/launchd/orquestadores si corres el server como servicio de fondo.

---

## Backups

Toda la memoria vive en un único archivo. Copiarlo alcanza:

```bash
cp ~/.agent-memory/memory.db ~/.agent-memory/memory-$(date +%Y%m%d).db.bak
```

Si el server está corriendo en modo WAL (default), puede haber un `memory.db-wal` y `memory.db-shm` junto al `.db` con escrituras aún no consolidadas. Para un backup consistente sin detener el server:

```bash
sqlite3 ~/.agent-memory/memory.db ".backup '/ruta/backup-$(date +%Y%m%d).db'"
```

`.backup` usa la API online de SQLite — captura un snapshot consistente incluso con el server escribiendo.

---

## Restaurar / mover memoria a otra máquina

```bash
# En la máquina origen
cp ~/.agent-memory/memory.db /ruta/compartida/memory.db

# En la máquina destino
mkdir -p ~/.agent-memory
cp /ruta/compartida/memory.db ~/.agent-memory/memory.db
mcp-memory check   # confirma que el archivo es legible y cuenta las memorias
```

También puedes usar `memory_export`/`memory_import` (JSONL) si quieres fusionar memoria de dos instancias en vez de reemplazar.

---

## Apagar / desinstalar

El server es un proceso Python normal — `Ctrl-C` o matar el proceso lo detiene, sin nada que "apagar" aparte. Para desinstalar completamente:

```bash
pip uninstall mcp-memory
rm -rf ~/.agent-memory   # borra la memoria guardada — irreversible
```

---

## Troubleshooting

**`no such module: fts5`**
- Tu Python no tiene FTS5 compilado en `sqlite3`. Pasa habitualmente con builds custom (algunos pyenv/asdf en Linux sin `libsqlite3-dev` instalado antes de compilar).
  - **macOS**: usa Homebrew (`brew install python@3.12`) o el instalador de python.org — ambos traen FTS5.
  - **Linux (pyenv/asdf)**: `apt install libsqlite3-dev` (o el equivalente de tu distro) **antes** de `pyenv install`, luego reinstala la versión de Python.
  - **Windows**: el instalador oficial de python.org trae FTS5.

**`mcp-memory` no arranca: `PermissionError` en `DB_PATH`**
- El directorio padre de `DB_PATH` no es escribible por el usuario que corre el proceso. Corré `mcp-memory check` para confirmar antes de arrancar el server.

**Puerto 8765 ocupado**
- Cambia `MCP_PORT` y reinicia.

**`memory_search` devuelve vacío**
- Verifica el namespace: si guardaste sin namespace y buscas con `namespace: "x"`, no coincide.
- La búsqueda es léxica (BM25 vía FTS5), no semántica: la query necesita compartir *términos* con el contenido guardado. Una paráfrasis sin overlap de vocabulario no va a matchear.

**`Connection reset by peer` al hacer `curl`**
- Falta el header `Accept: application/json, text/event-stream` en la request al endpoint `/mcp`. Sin él, FastMCP cierra la conexión.
