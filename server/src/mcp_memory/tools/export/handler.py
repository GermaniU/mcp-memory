from __future__ import annotations

import json

from pydantic import BaseModel, Field

from mcp_memory.shared.types import MemoryStore

# Tamaño de página elegido para iterar el store sin traer todo en memoria de una vez.
_PAGE_SIZE = 500


class ExportInput(BaseModel):
    namespace: str | None = Field(None)


class ExportResult(BaseModel):
    count: int
    jsonl: str


async def export_memories(inp: ExportInput, *, store: MemoryStore) -> ExportResult:
    lines: list[str] = []
    offset = 0
    while True:
        page = await store.list_(namespace=inp.namespace, limit=_PAGE_SIZE, offset=offset)
        for mem in page:
            lines.append(
                json.dumps(
                    {
                        "id": mem.id,
                        "content": mem.content,
                        "namespace": mem.namespace,
                        "tags": mem.tags,
                        "metadata": mem.metadata,
                        "created_at": mem.created_at.isoformat(),
                        "updated_at": mem.updated_at.isoformat(),
                    },
                    ensure_ascii=False,
                )
            )
        if len(page) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE
    return ExportResult(count=len(lines), jsonl="\n".join(lines))
