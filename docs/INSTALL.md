# Instalación detallada

Hay dos modos: **con Docker** (recomendado para no pelearse con Python) y **sin Docker** (proceso Python directo).

---

## ⚠️ Pre-requisito: Ollama con un modelo de embeddings

Antes de levantar nada, asegúrate de que tu Ollama responde con embeddings. **Ollama Cloud (`https://ollama.com`) no ofrece este endpoint** — solo modelos de chat. Necesitas Ollama local o remoto:

```bash
# Instala Ollama (si aún no): https://ollama.com/download
ollama pull bge-m3              # multilingüe, recomendado
# o:
ollama pull mxbai-embed-large   # alta calidad, inglés
ollama pull nomic-embed-text    # ligero, inglés

# Verifica que responde:
curl -X POST http://localhost:11434/api/embed \
  -H 'Content-Type: application/json' \
  -d '{"model":"bge-m3","input":"hola"}' | head -c 200
# Debe imprimir un JSON con {"embeddings":[[...]]} (un vector por cada input)
```

Si esto no funciona, no sigas — el resto fallará con `401`/`404`.

---

## Modo A — Docker

> La imagen está publicada en GHCR (`ghcr.io/germaniu/mcp-memory:latest`). `docker compose up -d` la descarga automáticamente — **no necesitas buildear nada**. Si quieres modificar el server, corre `docker compose build` para construir tu imagen local desde `./server`.

### Requisitos

- **Docker** ≥ 24 con Compose v2.
- Un endpoint de Ollama **con modelo de embeddings** (ver pre-requisito arriba):
  - Ollama local en tu Mac → `host.docker.internal` (Docker Desktop lo resuelve).
  - Ollama remoto → URL pública (+ `OLLAMA_API_KEY` si tu proxy la exige).
  - Ollama Cloud ❌ — no ofrece embeddings.
- Puertos libres: `8765` (MCP), `6333` (Qdrant).

### Pasos

```bash
git clone https://github.com/GermaniU/mcp-memory.git
cd mcp-memory
cp .env.example .env
# Edita .env (ver tabla abajo)
docker compose up -d
docker compose logs -f mcp-memory
```

### Variables (`.env`)

| Variable             | Default               | Descripción |
|----------------------|-----------------------|-------------|
| `OLLAMA_URL`         | `http://host.docker.internal:11434` | Endpoint Ollama. **Cloud NO sirve para embeddings** — usa local o remoto. |
| `OLLAMA_API_KEY`     | _vacío_               | Solo si tu endpoint requiere `Authorization: Bearer …`. |
| `EMBEDDING_MODEL`    | `bge-m3`              | Modelo Ollama. Debe estar `ollama pull`-ed en tu Ollama. |
| `EMBEDDING_DIM`      | `1024`                | **Debe coincidir EXACTO** con el modelo: bge-m3=1024, mxbai-embed-large=1024, nomic-embed-text=768. |
| `MCP_PORT`           | `8765`                | Puerto del MCP en el host. |
| `QDRANT_COLLECTION`  | `mcp_memory`     | Nombre interno de la colección Qdrant. |
| `DEFAULT_NAMESPACE`  | `default`             | Namespace cuando el cliente no especifica uno. |

Tras editar `.env`: `docker compose up -d` (recrea solo lo necesario).

---

## Modo B — Sin Docker (proceso Python)

### Requisitos

- Python 3.11+.
- Qdrant disponible — local (`docker run -p 6333:6333 qdrant/qdrant`), Qdrant Cloud, o uno tuyo.
- Endpoint Ollama local o remoto con modelo de embeddings (**Cloud no sirve** — ver pre-requisito arriba).

### Pasos

```bash
git clone https://github.com/GermaniU/mcp-memory.git
cd mcp-memory/server
python -m venv .venv && source .venv/bin/activate
pip install -e .

export OLLAMA_URL=http://localhost:11434   # o tu Ollama remoto (Cloud NO da embeddings)
# export OLLAMA_API_KEY=...                # solo si tu endpoint remoto la exige
export QDRANT_URL=http://localhost:6333
export EMBEDDING_MODEL=bge-m3
export EMBEDDING_DIM=1024

python -m mcp_memory
```

> Tip: pon esas variables en un `.env` y carga con `direnv` o `dotenv` en lugar de `export` manual.

---

## Modo C — Ya tengo un Qdrant (Qdrant externo)

Si ya corres Qdrant (otra app, un Qdrant Cloud, un cluster compartido) **no necesitas el Qdrant bundled** del compose. Levanta solo el server apuntándolo a tu URL.

> ⚠️ Usa una **colección dedicada** (`QDRANT_COLLECTION`). El server valida al arrancar que la dimensión de los vectores de la colección coincida con `EMBEDDING_DIM`; si difiere, aborta con un error claro en vez de corromper la búsqueda. No reutilices una colección que ya use otra app/dimensión.

### Variante Docker (solo el service `mcp-memory`)

```bash
cp .env.example .env
# En .env, apunta QDRANT_URL a tu Qdrant. Si corre en el host:
#   QDRANT_URL=http://host.docker.internal:6333
# Si es remoto:
#   QDRANT_URL=https://qdrant.tu-dominio.com
#   QDRANT_COLLECTION=mcp_memory

# Levanta SOLO el server (no arranca el Qdrant bundled):
docker compose up -d mcp-memory
docker compose logs -f mcp-memory
```

### Variante proceso local

Igual que el Modo B, con `QDRANT_URL` apuntando a tu Qdrant existente:

```bash
export QDRANT_URL=http://localhost:6333   # o tu URL remota
export QDRANT_COLLECTION=mcp_memory
python -m mcp_memory
```

El default para usuarios nuevos sigue siendo el Qdrant bundled (`docker compose up -d` arranca ambos services).

---

## Healthcheck

El server expone `GET /health` (sin prefijo `/mcp`):

```bash
curl http://localhost:8765/health
# {"status":"ok","qdrant":true}   -> 200 si Qdrant responde
# {"status":"ok","qdrant":false}  -> 503 si Qdrant no responde
```

El service `mcp-memory` del compose usa este endpoint en su `healthcheck`, así que `docker compose ps` muestra `healthy`/`unhealthy` de un vistazo. El arranque es resiliente: si Qdrant todavía no está listo, el server reintenta con backoff exponencial (8 intentos, ~30s) antes de rendirse.

---

## Cambiar de modelo de embedding

```bash
# 1. Ajusta EMBEDDING_MODEL y EMBEDDING_DIM
# 2. Borra la colección (los vectores viejos no son compatibles con otra dim)
curl -X DELETE http://localhost:6333/collections/mcp_memory
# 3. Recrea
docker compose up -d --force-recreate mcp-memory
```

---

## Backups

Toda la memoria vive en el volumen `qdrant-data`:

```bash
docker run --rm \
  -v mcp-memory_qdrant-data:/data \
  -v "$PWD":/backup \
  alpine tar czf /backup/qdrant-$(date +%Y%m%d).tar.gz -C /data .
```

---

## Apagar / desinstalar

```bash
docker compose down              # apaga, conserva datos
docker compose down -v           # ↑ y borra los volúmenes (¡pierdes la memoria!)
```

---

## Troubleshooting

**`mcp-memory` reinicia en bucle**
- `docker compose logs mcp-memory`. Causas frecuentes:
  - `OLLAMA_API_KEY` mal o ausente cuando tu endpoint la pide.
  - Modelo `EMBEDDING_MODEL` no disponible en tu Ollama (`ollama list` debería mostrarlo).
  - Qdrant aún no levantó — espera unos segundos.

**Mi Ollama corre en mi Mac, no me conecta desde el contenedor**
- En `.env`: `OLLAMA_URL=http://host.docker.internal:11434` y deja `OLLAMA_API_KEY` vacío.
- En Linux nativo (no Docker Desktop): añade `--add-host=host.docker.internal:host-gateway` (ya está en el compose).

**Quiero ver Qdrant**
- UI web: <http://localhost:6333/dashboard>. Solo lectura recomendada.

**Puerto 8765 ocupado**
- Cambia `MCP_PORT` en `.env` y reinicia.

**`memory_search` devuelve vacío**
- Verifica el namespace: si guardaste sin namespace y buscas con `namespace: "x"`, no coincide.
- Baja `min_score` a 0.0 para diagnosticar (luego súbelo a 0.5–0.7 en producción).
