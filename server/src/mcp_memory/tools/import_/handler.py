from __future__ import annotations

import json
from datetime import datetime

from pydantic import BaseModel, Field, ValidationError

from mcp_memory.shared.types import EmbeddingsClient, Memory, MemoryStore


class ImportInput(BaseModel):
    jsonl: str = Field(..., description="JSONL string produced by memory_export.")
    namespace_override: str | None = Field(
        None, description="If set, all imported memories land in this namespace."
    )


class ImportLineSchema(BaseModel):
    """Esquema mínimo esperado en cada línea JSONL exportada."""

    id: str
    content: str
    namespace: str
    tags: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class ImportLineError(BaseModel):
    line: int
    error: str


class ImportResult(BaseModel):
    imported: int
    skipped: int
    errors: list[ImportLineError]


async def import_memories(
    inp: ImportInput,
    *,
    embeddings: EmbeddingsClient,
    store: MemoryStore,
) -> ImportResult:
    imported = 0
    skipped = 0
    errors: list[ImportLineError] = []

    for line_number, raw in enumerate(inp.jsonl.splitlines(), start=1):
        if not raw.strip():
            # Línea vacía o solo whitespace: se ignora silenciosamente.
            continue

        try:
            data = json.loads(raw)
            line_data = ImportLineSchema.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            errors.append(ImportLineError(line=line_number, error=str(exc)))
            continue

        # Colisión de id: skip, no sobreescribir.
        if await store.get(line_data.id) is not None:
            skipped += 1
            continue

        namespace = (
            inp.namespace_override if inp.namespace_override is not None else line_data.namespace
        )
        memory = Memory(
            id=line_data.id,
            content=line_data.content,
            namespace=namespace,
            tags=line_data.tags,
            metadata=line_data.metadata,
            created_at=line_data.created_at,
            updated_at=line_data.updated_at,
        )
        vector = await embeddings.embed(line_data.content)
        await store.save(memory, vector)
        imported += 1

    return ImportResult(imported=imported, skipped=skipped, errors=errors)
