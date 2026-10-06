from __future__ import annotations

from pydantic import BaseModel, Field

from mcp_memory.shared.types import Memory, MemoryStore


class UpdateInput(BaseModel):
    id: str = Field(...)
    content: str | None = Field(None)
    tags: list[str] | None = Field(None)
    metadata: dict | None = Field(None)


async def update(
    inp: UpdateInput,
    *,
    store: MemoryStore,
) -> Memory | None:
    # Mismo criterio que memory_save: una memoria vacía no es buscable por FTS5
    # y solo ensucia list/recent.
    content = inp.content
    if content is not None:
        content = content.strip()
        if not content:
            raise ValueError("content must not be empty")

    return await store.update(
        inp.id,
        content=content,
        tags=inp.tags,
        metadata=inp.metadata,
    )
