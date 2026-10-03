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
    return await store.update(
        inp.id,
        content=inp.content,
        tags=inp.tags,
        metadata=inp.metadata,
    )
