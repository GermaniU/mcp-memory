from __future__ import annotations

from pydantic import BaseModel, Field

from mcp_memory.shared.types import Memory, MemoryStore


class SearchInput(BaseModel):
    query: str = Field(
        ..., description="Free-text query, matched lexically via SQLite FTS5 (BM25 ranking)."
    )
    namespace: str | None = Field(None, description="Restrict to a single namespace.")
    limit: int = Field(20, ge=1, le=100)


async def search(
    inp: SearchInput,
    *,
    store: MemoryStore,
) -> list[Memory]:
    return await store.search(
        inp.query,
        namespace=inp.namespace,
        limit=inp.limit,
    )
