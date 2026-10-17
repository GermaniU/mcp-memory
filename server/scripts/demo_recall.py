"""Demo grabable: el agente guarda algo en una sesión y lo recupera en otra.

Dos clientes MCP independientes (dos "sesiones") contra el mismo server y la
misma DB en disco. La segunda sesión no comparte memoria en RAM con la primera:
lo único que las une es el archivo SQLite.

Pensado para grabarse con asciinema -> GIF (ver docs/assets/demo.gif).
Requiere el server corriendo en http://localhost:8765/mcp con una DB limpia.

Uso:
    .venv/bin/python scripts/demo_recall.py
"""

from __future__ import annotations

import json
import os
import sys
import time

import anyio
from fastmcp import Client

URL = os.environ.get("MCP_DEMO_URL", "http://localhost:8765/mcp")
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


async def session_1_save() -> str:
    out("\033[1;36m▸ sesión 1\033[0m  ·  el agente aprende algo")
    beat()
    async with Client(URL) as c:
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


async def session_2_recall() -> None:
    out()
    out("\033[1;36m▸ sesión 2\033[0m  ·  proceso nuevo, otra conversación")
    beat()
    async with Client(URL) as c:
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
    await session_1_save()
    beat(1.0)
    await session_2_recall()
    out()
    out("  \033[1;32m✓ recordado en una sesión distinta — mismo archivo SQLite\033[0m")
    out()
    return 0


if __name__ == "__main__":
    sys.exit(anyio.run(main))
