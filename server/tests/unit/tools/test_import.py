from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from mcp_memory.tools.import_.handler import _MAX_IMPORT_BYTES, ImportInput, import_memories
from mcp_memory.tools.save.handler import SaveInput, save


def _line(
    *,
    id: str = "11111111-1111-1111-1111-111111111111",
    content: str = "contenido de prueba",
    namespace: str = "src-ns",
    tags: list[str] | None = None,
    metadata: dict | None = None,
    created_at: str = "2025-01-01T10:00:00+00:00",
    updated_at: str = "2025-01-01T10:00:00+00:00",
) -> str:
    return json.dumps(
        {
            "id": id,
            "content": content,
            "namespace": namespace,
            "tags": tags or [],
            "metadata": metadata or {},
            "created_at": created_at,
            "updated_at": updated_at,
        }
    )


async def test_import_happy_path(embeddings, store):
    jsonl = "\n".join([
        _line(id="aaaa0001-0000-0000-0000-000000000001", content="primera"),
        _line(id="aaaa0002-0000-0000-0000-000000000002", content="segunda"),
    ])
    result = await import_memories(ImportInput(jsonl=jsonl), embeddings=embeddings, store=store)
    assert result.imported == 2
    assert result.skipped == 0
    assert result.errors == []


async def test_import_namespace_override(embeddings, store):
    jsonl = _line(id="bbbb0001-0000-0000-0000-000000000001", namespace="origen")
    result = await import_memories(
        ImportInput(jsonl=jsonl, namespace_override="destino"),
        embeddings=embeddings,
        store=store,
    )
    assert result.imported == 1
    mem = await store.get("bbbb0001-0000-0000-0000-000000000001")
    assert mem is not None
    assert mem.namespace == "destino"


async def test_import_collision_skips_existing_id(embeddings, store):
    # Guardamos primero una memoria con un id conocido.
    existing_id = "cccc0001-0000-0000-0000-000000000001"
    await save(
        SaveInput(content="memoria existente", namespace="ns"),
        embeddings=embeddings,
        store=store,
        default_namespace="default",
    )
    # Sobreescribimos el id en store directamente vía un save raw para fijar el id.
    from mcp_memory.shared.types import Memory
    fixed_mem = Memory(
        id=existing_id,
        content="existente original",
        namespace="ns",
        tags=[],
        metadata={},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    vec = await embeddings.embed("existente original")
    await store.save(fixed_mem, vec)

    jsonl = _line(id=existing_id, content="intento de sobreescritura")
    result = await import_memories(ImportInput(jsonl=jsonl), embeddings=embeddings, store=store)
    assert result.imported == 0
    assert result.skipped == 1
    assert result.errors == []
    # El contenido original no fue modificado.
    mem = await store.get(existing_id)
    assert mem is not None
    assert mem.content == "existente original"


async def test_import_malformed_line_accumulates_error(embeddings, store):
    jsonl = "\n".join([
        _line(id="dddd0001-0000-0000-0000-000000000001", content="buena"),
        "{ esto no es json valido",
        _line(id="dddd0002-0000-0000-0000-000000000002", content="tambien buena"),
    ])
    result = await import_memories(ImportInput(jsonl=jsonl), embeddings=embeddings, store=store)
    assert result.imported == 2
    assert result.skipped == 0
    assert len(result.errors) == 1
    assert result.errors[0].line == 2


async def test_import_missing_required_field_accumulates_error(embeddings, store):
    # Línea JSON válida pero falta el campo "content" requerido.
    bad = json.dumps({"id": "eeee0001-0000-0000-0000-000000000001", "namespace": "ns"})
    result = await import_memories(ImportInput(jsonl=bad), embeddings=embeddings, store=store)
    assert result.imported == 0
    assert len(result.errors) == 1
    assert result.errors[0].line == 1


async def test_import_rejects_payload_over_size_limit(embeddings, store):
    # Crea un payload que excede _MAX_IMPORT_BYTES bytes.
    oversized = "x" * (_MAX_IMPORT_BYTES + 1)
    with pytest.raises(ValueError, match="límite permitido"):
        await import_memories(ImportInput(jsonl=oversized), embeddings=embeddings, store=store)


async def test_import_accepts_payload_at_size_limit(embeddings, store):
    # Un payload justo en el límite no debe lanzar excepción (aunque sea JSON inválido,
    # el error de tamaño no se lanza).
    at_limit = "x" * _MAX_IMPORT_BYTES
    # No debe lanzar ValueError por tamaño; puede haber errores de parseo JSON.
    result = await import_memories(ImportInput(jsonl=at_limit), embeddings=embeddings, store=store)
    assert result.imported == 0  # no hay líneas JSONL válidas, todo es un solo "x" continuo


async def test_import_blank_lines_ignored(embeddings, store):
    jsonl = "\n".join([
        "",
        _line(id="ffff0001-0000-0000-0000-000000000001", content="valida"),
        "   ",
        "",
    ])
    result = await import_memories(ImportInput(jsonl=jsonl), embeddings=embeddings, store=store)
    assert result.imported == 1
    assert result.skipped == 0
    assert result.errors == []


async def test_import_preserves_original_timestamps_and_tags(embeddings, store):
    created = "2024-06-01T08:00:00+00:00"
    updated = "2024-06-02T09:30:00+00:00"
    mem_id = "gggg0001-0000-0000-0000-000000000001"
    jsonl = _line(
        id=mem_id,
        tags=["tag-a", "tag-b"],
        metadata={"key": "val"},
        created_at=created,
        updated_at=updated,
    )
    await import_memories(ImportInput(jsonl=jsonl), embeddings=embeddings, store=store)
    mem = await store.get(mem_id)
    assert mem is not None
    assert mem.tags == ["tag-a", "tag-b"]
    assert mem.metadata == {"key": "val"}
    assert mem.created_at.isoformat() == created
    assert mem.updated_at.isoformat() == updated
