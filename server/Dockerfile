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

# pip < 26.2.2 vendors a certifi that still trusts the emSign ECC Root CA - G3
# (eMudhra incident, GHSA-6q48-6c7w-9gw2), and pip always loads that bundle on
# top of the system store. The base image ships an older pip, so it is replaced
# by a hash-pinned wheel first: the sha256 check protects this one download
# even over the old trust store, and every later install uses pip >= 26.2.2.
ARG PIP_BOOTSTRAP="pip @ https://files.pythonhosted.org/packages/3f/06/3e4420302363fbb71be3c7f35ce042f54bfca330e3e66b3a2e3c4cca579f/pip-26.2.2-py3-none-any.whl#sha256=fd7f4dfa8190e014013b9f08f3e973f4e4c26ffd179a204895533a7254813a70"

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src

RUN python -m pip install --no-cache-dir --no-deps "$PIP_BOOTSTRAP" \
    && python -m pip --version \
    && pip install --no-cache-dir . \
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
