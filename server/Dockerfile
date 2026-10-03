FROM python:3.11-slim

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

CMD ["python", "-m", "mcp_memory"]
