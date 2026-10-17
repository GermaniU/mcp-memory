"""E2E del transporte stdio: el cliente lanza `python -m mcp_memory --stdio`
como subproceso, igual que Claude Desktop/Claude Code/Cursor con `command`.

Si algo escribe en stdout (un print, el banner, logs) el canal JSON-RPC se
corrompe y el handshake falla — este test lo detecta.
"""

from __future__ import annotations

import os
import sys

from fastmcp import Client
from fastmcp.client.transports import StdioTransport


async def test_stdio_roundtrip_persists_to_db_path(tmp_path):
    db_path = tmp_path / "memory.db"
    transport = StdioTransport(
        command=sys.executable,
        args=["-m", "mcp_memory", "--stdio"],
        env={**os.environ, "DB_PATH": str(db_path)},
        cwd=str(tmp_path),
    )

    async with Client(transport) as client:
        tools = {tool.name for tool in await client.list_tools()}
        assert "memory_save" in tools
        assert len(tools) == 9

        await client.call_tool(
            "memory_save", {"content": "stdio funciona end-to-end", "namespace": "stdio"}
        )
        result = await client.call_tool(
            "memory_search", {"query": "stdio end-to-end", "namespace": "stdio"}
        )
        hits = result.structured_content["result"]
        assert [hit["content"] for hit in hits] == ["stdio funciona end-to-end"]

    # El proceso terminó: la memoria quedó en el archivo, no en RAM.
    assert db_path.exists()
