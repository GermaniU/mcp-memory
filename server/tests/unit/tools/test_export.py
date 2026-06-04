from __future__ import annotations

import json

from mcp_memory.tools.export.handler import ExportInput, export_memories
from mcp_memory.tools.save.handler import SaveInput, save


async def test_export_happy_path_returns_all_memories(embeddings, store):
    for i in range(3):
        await save(
            SaveInput(content=f"memoria {i}", namespace="ns"),
            embeddings=embeddings,
            store=store,
            default_namespace="default",
        )
    result = await export_memories(ExportInput(), store=store)
    assert result.count == 3
    lines = result.jsonl.splitlines()
    assert len(lines) == 3
    # Cada línea es JSON válido con los campos esperados.
    for line in lines:
        obj = json.loads(line)
        assert "id" in obj
        assert "content" in obj
        assert "namespace" in obj
        assert "tags" in obj
        assert "metadata" in obj
        assert "created_at" in obj
        assert "updated_at" in obj
        # Sin vectores: portabilidad entre modelos de embedding.
        assert "vector" not in obj


async def test_export_namespace_filter(embeddings, store):
    await save(
        SaveInput(content="en ns-a", namespace="ns-a"),
        embeddings=embeddings,
        store=store,
        default_namespace="default",
    )
    await save(
        SaveInput(content="en ns-b", namespace="ns-b"),
        embeddings=embeddings,
        store=store,
        default_namespace="default",
    )
    result = await export_memories(ExportInput(namespace="ns-a"), store=store)
    assert result.count == 1
    obj = json.loads(result.jsonl)
    assert obj["namespace"] == "ns-a"
    assert obj["content"] == "en ns-a"


async def test_export_empty_namespace_returns_count_zero(store):
    result = await export_memories(ExportInput(namespace="inexistente"), store=store)
    assert result.count == 0
    assert result.jsonl == ""


async def test_export_timestamps_are_iso8601(embeddings, store):
    await save(
        SaveInput(content="timestamp test"),
        embeddings=embeddings,
        store=store,
        default_namespace="default",
    )
    result = await export_memories(ExportInput(), store=store)
    obj = json.loads(result.jsonl)
    # datetime.isoformat() produce strings parseables — validamos que no sean epoch floats.
    assert "T" in obj["created_at"]
    assert "T" in obj["updated_at"]
