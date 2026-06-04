"""Smoke E2E contra un servidor mcp-memory corriendo (HTTP MCP real).

Ejercita las 7 tools en orden: save -> search -> list -> recent -> update -> stats -> delete.
Requiere: servidor en http://localhost:8765/mcp + Qdrant + Ollama vivos.

Uso:
    .venv/bin/python scripts/smoke_e2e.py
"""

from __future__ import annotations

import json
import sys

import anyio
from fastmcp import Client

URL = "http://localhost:8765/mcp"
NS = "smoke-test"


def _data(result):
    """Extrae el payload estructurado de un CallToolResult."""
    if result.structured_content is not None:
        sc = result.structured_content
        return sc.get("result", sc) if isinstance(sc, dict) else sc
    return json.loads(result.content[0].text)


async def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        mark = "OK" if cond else "FAIL"
        print(f"  [{mark}] {name}" + (f" - {detail}" if detail else ""))
        if not cond:
            failures.append(name)

    async with Client(URL) as c:
        tools = await c.list_tools()
        names = sorted(t.name for t in tools)
        print(f"tools expuestas ({len(names)}): {', '.join(names)}")
        expected = {
            "memory_save", "memory_search", "memory_delete", "memory_list",
            "memory_update", "memory_recent", "memory_stats",
        }
        check("las 7 tools registradas", expected.issubset(set(names)))

        # 1. save x2 — API plana (campos directos, sin wrapper "inp")
        r1 = _data(await c.call_tool("memory_save", {
            "content": "Germani prefiere copy en espanol MX neutro con tu, sin argentinismos",
            "namespace": NS, "tags": ["estilo", "copy"],
        }))
        r2 = _data(await c.call_tool("memory_save", {
            "content": "El deploy de prod corre en un VPS Contabo compartido con Docker",
            "namespace": NS, "tags": ["infra"],
        }))
        check("save devuelve id + namespace", bool(r1.get("id")) and r1.get("namespace") == NS)

        # 2. search semantico — la query NO comparte keywords exactas con el contenido
        hits = _data(await c.call_tool("memory_search", {
            "query": "que estilo de redaccion usar para textos de clientes mexicanos?",
            "namespace": NS, "limit": 5,
        }))
        check("search >=1 hit", len(hits) >= 1, f"{len(hits)} hits")
        if hits:
            top = hits[0]
            check(
                "hit mas relevante = memoria de copy (semantica real)",
                top["id"] == r1["id"],
                f"top score={top.get('score'):.3f}",
            )

        # 3. list
        listed = _data(await c.call_tool("memory_list", {"namespace": NS, "limit": 10}))
        check("list devuelve las 2", len(listed) == 2, f"{len(listed)}")

        # 4. recent — r2 fue la ultima escrita
        recent = _data(await c.call_tool("memory_recent", {"namespace": NS, "limit": 1}))
        check("recent[0] = ultima escrita", bool(recent) and recent[0]["id"] == r2["id"])

        # 5. update re-embebe: ahora r2 deberia matchear una query de cocina
        upd = _data(await c.call_tool("memory_update", {
            "id": r2["id"],
            "content": "Las ordenes dine-in entran al tablero de cocina al confirmarse",
        }))
        check("update devuelve contenido nuevo", "cocina" in (upd or {}).get("content", ""))
        hits2 = _data(await c.call_tool("memory_search", {
            "query": "flujo de pedidos del restaurante hacia la cocina",
            "namespace": NS, "limit": 1,
        }))
        check("search post-update encuentra el contenido re-embebido",
              bool(hits2) and hits2[0]["id"] == r2["id"])

        # 6. stats
        st = _data(await c.call_tool("memory_stats", {"namespace": NS}))
        check("stats cuenta 2 en el namespace", st.get("count") == 2, json.dumps(st))

        # 7. delete + verificacion
        for rid in (r1["id"], r2["id"]):
            d = _data(await c.call_tool("memory_delete", {"id": rid}))
            check(f"delete {rid[:8]}", d.get("deleted") is True)
        st2 = _data(await c.call_tool("memory_stats", {"namespace": NS}))
        check("namespace queda vacio", st2.get("count") == 0)

    print()
    if failures:
        print(f"SMOKE FAIL - {len(failures)} checks rotos: {failures}")
        return 1
    print("SMOKE OK - las 7 tools funcionan E2E contra Qdrant + Ollama reales")
    return 0


if __name__ == "__main__":
    sys.exit(anyio.run(main))
