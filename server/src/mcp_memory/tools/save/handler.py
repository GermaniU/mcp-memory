from __future__ import annotations

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from mcp_memory.faithfulness.gate import (
    FaithfulnessGateError,
    append_to_review_queue,
    gate_fact,
    is_gated_namespace,
)
from mcp_memory.shared.types import EmbeddingsClient, Memory, MemoryStore


class SaveInput(BaseModel):
    content: str = Field(..., description="Memory content (free text).")
    namespace: str | None = Field(
        None, description="Logical bucket. Defaults to server's default_namespace."
    )
    tags: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


async def save(
    inp: SaveInput,
    *,
    embeddings: EmbeddingsClient,
    store: MemoryStore,
    default_namespace: str,
) -> Memory:
    content = inp.content.strip()
    if not content:
        raise ValueError("content must not be empty")

    namespace = inp.namespace or default_namespace

    # Gate solo namespaces "gateables" (default: decisions) — un save interactivo
    # normal no puede esperar hasta 180s de Gemini en cada llamada. Ver
    # is_gated_namespace() para el scope configurable (FAITHFULNESS_GATE_NAMESPACES).
    if is_gated_namespace(namespace):
        gate_result = gate_fact(content)
        if gate_result["verdict"] != "accept":
            queue_verdict = "rejected" if gate_result["verdict"] == "reject" else "held_judge_error"
            append_to_review_queue(
                namespace=namespace,
                content=content,
                verdict=queue_verdict,
                severity=gate_result["severity"],
                reason=gate_result["reason"],
                source="save",
            )
            raise FaithfulnessGateError(
                f"faithfulness gate {queue_verdict} (namespace={namespace!r}): "
                f"{gate_result['reason'] or 'sin razón provista'}"
            )

    now = datetime.now(UTC)
    memory = Memory(
        id=str(uuid.uuid4()),
        content=content,
        namespace=namespace,
        tags=inp.tags,
        metadata=inp.metadata,
        created_at=now,
        updated_at=now,
    )
    vector = await embeddings.embed(content)
    return await store.save(memory, vector)
