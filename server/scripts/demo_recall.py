"""Demo grabable: el agente guarda algo en una sesión y lo recupera en otra.

Cada sesión lanza su propio proceso `mcp-memory --stdio` (como hace un cliente
real) y el proceso termina al cerrarla. La segunda sesión no comparte RAM con la
primera: lo único que las une es el archivo SQLite.

Pensado para grabarse con asciinema -> GIF (ver docs/assets/demo.gif). No hace
falta ningún server corriendo: usa una DB temporal limpia salvo que se pase
MCP_DEMO_DB_PATH.

Uso:
    .venv/bin/python scripts/demo_recall.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

import anyio
from fastmcp import Client
from fastmcp.client.transports import StdioTransport

NS = "prod-incident"


def out(text: str = "") -> None:
    print(text, flush=True)


def beat(seconds: float = 0.7) -> None:
    time.sleep(seconds)


def payload(result):
    """Extrae el contenido estructurado de un CallToolResult."""
    if result.structured_content is not None:
        sc = result.structured_content
        return sc.get("result", sc) if isinstance(sc, dict) else sc
    return json.loads(result.content[0].text)


def new_process(db_path: str) -> Client:
    """Un proceso `mcp-memory --stdio` nuevo por sesión, contra el mismo DB_PATH.

    Los logs del server (stderr) van a un archivo junto a la DB para no ensuciar
    la grabación.
    """
    return Client(
        StdioTransport(
            command=sys.executable,
            args=["-m", "mcp_memory", "--stdio"],
            env={**os.environ, "DB_PATH": db_path},
            log_file=Path(db_path).with_suffix(".log"),
        )
    )


async def session_1_save(db_path: str) -> str:
    out("\033[1;36m▸ sesión 1\033[0m  ·  el agente aprende algo")
    beat()
    async with new_process(db_path) as c:
        out('  \033[2magent →\033[0m memory_save  { namespace: "prod-incident" }')
        beat()
        r1 = payload(
            await c.call_tool(
                "memory_save",
                {
                    "content": (
                        "El gateway de pagos reintenta 3 veces con backoff exponencial "
                        "antes de marcar la orden como fallida."
                    ),
                    "namespace": NS,
                    "tags": ["pagos", "reintentos"],
                },
            )
        )
        out(f"  \033[2mserver ←\033[0m guardado  id={r1['id'][:8]}…")
        beat()
        out('  \033[2magent →\033[0m memory_save  { namespace: "prod-incident" }')
        beat()
        r2 = payload(
            await c.call_tool(
                "memory_save",
                {
                    "content": (
                        "El webhook de Stripe se valida con la firma HMAC antes de tocar la orden."
                    ),
                    "namespace": NS,
                    "tags": ["pagos", "seguridad"],
                },
            )
        )
        out(f"  \033[2mserver ←\033[0m guardado  id={r2['id'][:8]}…")
        beat()
    out("  \033[2m(sesión cerrada — el proceso termina)\033[0m")
    return NS


async def session_2_recall(db_path: str) -> None:
    out()
    out("\033[1;36m▸ sesión 2\033[0m  ·  proceso nuevo, otra conversación")
    beat()
    async with new_process(db_path) as c:
        out('  \033[2magent →\033[0m memory_search  { query: "gateway pagos reintentos backoff" }')
        beat()
        hits = payload(
            await c.call_tool(
                "memory_search",
                {
                    "query": "gateway pagos reintentos backoff",
                    "namespace": NS,
                    "limit": 1,
                },
            )
        )
    if not hits:
        out("  \033[1;31mserver ←\033[0m sin resultados")
        sys.exit(1)
    top = hits[0]
    out(f"  \033[2mserver ←\033[0m {len(hits)} hit  ·  score BM25 {top.get('score', 0):.2f}")
    out()
    out(f"  \033[1;32m“{top['content']}”\033[0m")
    beat()


async def main() -> int:
    out()
    out("  \033[1mMCP Memory\033[0m — memoria persistente para agentes (SQLite + FTS5/BM25)")
    out("  \033[2m────────────────────────────────────────────────────────────\033[0m")
    beat()
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.environ.get("MCP_DEMO_DB_PATH") or str(Path(tmp) / "memory.db")
        await session_1_save(db_path)
        beat(1.0)
        await session_2_recall(db_path)
    out()
    out("  \033[1;32m✓ recordado en una sesión distinta — mismo archivo SQLite\033[0m")
    out()
    return 0


if __name__ == "__main__":
    sys.exit(anyio.run(main))
