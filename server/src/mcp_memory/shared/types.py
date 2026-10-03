from __future__ import annotations

from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, Field


class Memory(BaseModel):
    """A single memory entry as returned to MCP clients."""

    id: str
    content: str
    namespace: str
    tags: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    score: float | None = Field(
        None,
        description=(
            "Relevancia normalizada [0,1] dentro del result set de una llamada a "
            "memory_search (BM25 vía SQLite FTS5). No es un score absoluto: no es "
            "comparable entre llamadas distintas ni entre namespaces."
        ),
    )


class MemoryStore(Protocol):
    async def get(self, memory_id: str) -> Memory | None: ...
    async def save(self, memory: Memory) -> Memory: ...
    async def update(
        self,
        memory_id: str,
        *,
        content: str | None,
        tags: list[str] | None,
        metadata: dict | None,
    ) -> Memory | None: ...
    async def delete(self, memory_id: str) -> bool: ...
    async def search(
        self,
        query: str,
        *,
        namespace: str | None,
        limit: int,
    ) -> list[Memory]: ...
    async def list_(
        self,
        *,
        namespace: str | None,
        limit: int,
        offset: int,
    ) -> list[Memory]: ...
    async def recent(self, *, namespace: str | None, limit: int) -> list[Memory]: ...
    async def stats(self, *, namespace: str | None) -> dict: ...
    async def ping(self) -> bool: ...
