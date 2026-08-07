from __future__ import annotations

import logging
from typing import Any

import anyio
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp_memory.shared.config import Settings, get_settings
from mcp_memory.shared.store import SqliteFtsStore
from mcp_memory.shared.types import Memory, MemoryStore
from mcp_memory.tools.delete.handler import DeleteInput, DeleteResult, delete
from mcp_memory.tools.export.handler import ExportInput, ExportResult, export_memories
from mcp_memory.tools.import_.handler import ImportInput, ImportResult, import_memories
from mcp_memory.tools.list_.handler import ListInput, list_memories
from mcp_memory.tools.recent.handler import RecentInput, recent
from mcp_memory.tools.save.handler import SaveInput, save
from mcp_memory.tools.search.handler import SearchInput, search
from mcp_memory.tools.stats.handler import StatsInput, stats
from mcp_memory.tools.update.handler import UpdateInput, update

logger = logging.getLogger("mcp_memory")


def build_app(
    *,
    settings: Settings,
    store: MemoryStore,
) -> FastMCP:
    """Compose the FastMCP app. Pure wiring — no business logic here.

    Tool inputs are flat (one parameter per field) so the MCP schema clients see
    is not nested under an ``inp`` object. The handler-level Input models are
    rebuilt internally and remain the unit-tested contract.
    """
    mcp = FastMCP("mcp-memory")

    @mcp.tool(name="memory_save", description="Persist a new memory. Returns the saved entry.")
    async def _save(
        content: str,
        namespace: str | None = None,
        tags: list[str] | None = None,
        metadata: dict | None = None,
    ) -> Memory:
        inp = SaveInput(
            content=content, namespace=namespace, tags=tags or [], metadata=metadata or {}
        )
        return await save(inp, store=store, default_namespace=settings.default_namespace)

    @mcp.tool(
        name="memory_search", description="Lexical (BM25/FTS5) search across stored memories."
    )
    async def _search(
        query: str,
        namespace: str | None = None,
        limit: int = 20,
    ) -> list[Memory]:
        inp = SearchInput(query=query, namespace=namespace, limit=limit)
        return await search(inp, store=store)

    @mcp.tool(name="memory_delete", description="Delete a memory by id.")
    async def _delete(id: str) -> DeleteResult:
        return await delete(DeleteInput(id=id), store=store)

    @mcp.tool(name="memory_list", description="List memories with pagination.")
    async def _list(
        namespace: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Memory]:
        inp = ListInput(namespace=namespace, limit=limit, offset=offset)
        return await list_memories(inp, store=store)

    @mcp.tool(
        name="memory_update", description="Update content/tags/metadata of an existing memory."
    )
    async def _update(
        id: str,
        content: str | None = None,
        tags: list[str] | None = None,
        metadata: dict | None = None,
    ) -> Memory | None:
        inp = UpdateInput(id=id, content=content, tags=tags, metadata=metadata)
        return await update(inp, store=store)

    @mcp.tool(name="memory_recent", description="Most recently updated memories.")
    async def _recent(namespace: str | None = None, limit: int = 10) -> list[Memory]:
        inp = RecentInput(namespace=namespace, limit=limit)
        return await recent(inp, store=store)

    @mcp.tool(name="memory_stats", description="Counts and namespace summary.")
    async def _stats(namespace: str | None = None) -> dict[str, Any]:
        return await stats(StatsInput(namespace=namespace), store=store)

    @mcp.tool(name="memory_export", description="Export memories as JSONL (no vectors).")
    async def _export(namespace: str | None = None) -> ExportResult:
        inp = ExportInput(namespace=namespace)
        return await export_memories(inp, store=store)

    @mcp.tool(
        name="memory_import",
        description="Import memories from JSONL (skips ids that already exist).",
    )
    async def _import(jsonl: str, namespace_override: str | None = None) -> ImportResult:
        inp = ImportInput(jsonl=jsonl, namespace_override=namespace_override)
        return await import_memories(inp, store=store)

    @mcp.custom_route("/health", methods=["GET"])
    async def _health(request: Request) -> JSONResponse:
        db_ok = await store.ping()
        return JSONResponse(
            {"status": "ok", "db": db_ok},
            status_code=200 if db_ok else 503,
        )

    return mcp


async def _serve(settings: Settings) -> None:
    store = SqliteFtsStore(db_path=settings.db_path)
    await store.ensure_schema()
    try:
        app = build_app(settings=settings, store=store)
        from starlette.middleware.cors import CORSMiddleware
        http_app = app.http_app()
        http_app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
        app.http_app = lambda *args, **kwargs: http_app
        await app.run_async(transport="http", host=settings.mcp_host, port=settings.mcp_port)
    finally:
        await store.aclose()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    anyio.run(_serve, get_settings())


if __name__ == "__main__":
    main()
