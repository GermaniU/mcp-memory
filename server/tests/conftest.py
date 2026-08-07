from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from mcp_memory.shared.types import Memory, MemoryStore


class FakeStore(MemoryStore):
    """In-memory store para tests unitarios de handlers.

    Búsqueda léxica simple (token/substring overlap) — no coseno, no BM25 real.
    Suficiente para probar el contrato de los handlers sin arrastrar ningún
    concepto de embeddings; el motor FTS5/BM25 real se prueba contra
    `SqliteFtsStore` en tests/unit/test_store.py y tests/integration/test_e2e.py.
    Orden: insertion.
    """

    def __init__(self) -> None:
        self._items: dict[str, Memory] = {}

    async def get(self, memory_id: str) -> Memory | None:
        return self._items.get(memory_id)

    async def save(self, memory: Memory) -> Memory:
        self._items[memory.id] = memory
        return memory

    async def update(
        self,
        memory_id: str,
        *,
        content: str | None,
        tags: list[str] | None,
        metadata: dict | None,
    ) -> Memory | None:
        existing = self._items.get(memory_id)
        if existing is None:
            return None
        updated = existing.model_copy(
            update={
                "content": content if content is not None else existing.content,
                "tags": tags if tags is not None else existing.tags,
                "metadata": metadata if metadata is not None else existing.metadata,
                "updated_at": datetime.now(UTC),
            }
        )
        self._items[memory_id] = updated
        return updated

    async def delete(self, memory_id: str) -> bool:
        return self._items.pop(memory_id, None) is not None

    async def search(
        self,
        query: str,
        *,
        namespace: str | None,
        limit: int,
    ) -> list[Memory]:
        tokens = [t.lower() for t in query.split()]
        if not tokens:
            return []
        scored: list[tuple[int, Memory]] = []
        for mem in self._items.values():
            if namespace and mem.namespace != namespace:
                continue
            haystack = f"{mem.content} {' '.join(mem.tags)}".lower()
            matches = sum(1 for t in tokens if t in haystack)
            if matches == 0:
                continue
            scored.append((matches, mem))
        scored.sort(key=lambda s: s[0], reverse=True)
        top = scored[:limit]
        best = top[0][0] if top else 1
        return [m.model_copy(update={"score": matches / best}) for matches, m in top]

    async def list_(
        self,
        *,
        namespace: str | None,
        limit: int,
        offset: int,
    ) -> list[Memory]:
        items = [m for m in self._items.values() if not namespace or m.namespace == namespace]
        return items[offset : offset + limit]

    async def recent(self, *, namespace: str | None, limit: int) -> list[Memory]:
        items = [m for m in self._items.values() if not namespace or m.namespace == namespace]
        items.sort(key=lambda m: m.updated_at, reverse=True)
        return items[:limit]

    async def stats(self, *, namespace: str | None) -> dict[str, Any]:
        items = [m for m in self._items.values() if not namespace or m.namespace == namespace]
        if not items:
            return {"count": 0, "namespaces": [], "oldest": None, "newest": None}
        return {
            "count": len(items),
            "namespaces": sorted({m.namespace for m in items}),
            "oldest": min(m.created_at for m in items).isoformat(),
            "newest": max(m.updated_at for m in items).isoformat(),
        }

    async def ping(self) -> bool:
        return True


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()
