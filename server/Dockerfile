FROM python:3.11-slim

# El MCP Registry verifica que la imagen pertenece al server con este label
# (debe coincidir con "name" en server.json).
LABEL io.modelcontextprotocol.server.name="io.github.GermaniU/mcp-memory"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Dentro del contenedor hay que escuchar en todas las interfaces para que
    # el port mapping funcione; publica el puerto solo en 127.0.0.1 del host.
    MCP_HOST=0.0.0.0 \
    DB_PATH=/data/memory.db

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src

RUN pip install --no-cache-dir . \
    && useradd --system --uid 10001 --home-dir /data mcp \
    && mkdir -p /data \
    && chown mcp:mcp /data

USER mcp
VOLUME ["/data"]
EXPOSE 8765

# La imagen slim no trae curl: se usa urllib de la stdlib. /health devuelve 503
# si SQLite no responde, lo que hace fallar urlopen. En modo stdio no hay HTTP
# que consultar (`docker run -i ... --stdio`): el check pasa si PID 1 lo pidió.
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import os, sys, urllib.request; stdio = b'--stdio' in open('/proc/1/cmdline', 'rb').read() or os.environ.get('MCP_TRANSPORT') == 'stdio'; stdio and sys.exit(0); urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"MCP_PORT\", \"8765\")}/health', timeout=2)"]

# ENTRYPOINT (no CMD) para que los argumentos de `docker run` lleguen al CLI:
# `docker run ... ghcr.io/germaniu/mcp-memory --stdio`.
ENTRYPOINT ["python", "-m", "mcp_memory"]
