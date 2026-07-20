from __future__ import annotations

import json
from datetime import datetime

from pydantic import BaseModel, Field, ValidationError

from mcp_memory.faithfulness.gate import append_to_review_queue, gate_fact
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


class ImportRejection(BaseModel):
    """Ítem retenido por el gate de faithfulness (nunca persistido)."""

    line: int
    verdict: str  # "rejected" | "held_judge_error"
    reason: str
    severity: str | None = None


class ImportResult(BaseModel):
    imported: int
    skipped: int
    errors: list[ImportLineError]
    rejected: list[ImportRejection] = Field(default_factory=list)


async def import_memories(
    inp: ImportInput,
    *,
    embeddings: EmbeddingsClient,
    store: MemoryStore,
) -> ImportResult:
    imported = 0
    skipped = 0
    errors: list[ImportLineError] = []
    rejected: list[ImportRejection] = []

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

        # Colisión de id: skip, no sobreescribir. Chequeo antes del gate — no
        # tiene sentido invocar al juez (hasta 180s) sobre algo que se va a saltar.
        if await store.get(line_data.id) is not None:
            skipped += 1
            continue

        namespace = (
            inp.namespace_override if inp.namespace_override is not None else line_data.namespace
        )

        # Bulk import: SIEMPRE gateado (a diferencia de save/, que solo gatea
        # namespaces configurados) — es inherentemente no interactivo.
        gate_result = gate_fact(line_data.content)
        if gate_result["verdict"] != "accept":
            queue_verdict = "rejected" if gate_result["verdict"] == "reject" else "held_judge_error"
            append_to_review_queue(
                namespace=namespace,
                content=line_data.content,
                verdict=queue_verdict,
                severity=gate_result["severity"],
                reason=gate_result["reason"],
                source="import",
            )
            rejected.append(
                ImportRejection(
                    line=line_number,
                    verdict=queue_verdict,
                    reason=gate_result["reason"],
                    severity=gate_result["severity"],
                )
            )
            continue

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

    return ImportResult(imported=imported, skipped=skipped, errors=errors, rejected=rejected)
