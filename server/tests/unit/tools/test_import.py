from __future__ import annotations

import json
from datetime import UTC, datetime

from mcp_memory.faithfulness import gate as gate_module
from mcp_memory.tools.import_.handler import ImportInput, import_memories
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
    jsonl = "\n".join(
        [
            _line(id="aaaa0001-0000-0000-0000-000000000001", content="primera"),
            _line(id="aaaa0002-0000-0000-0000-000000000002", content="segunda"),
        ]
    )
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
    jsonl = "\n".join(
        [
            _line(id="dddd0001-0000-0000-0000-000000000001", content="buena"),
            "{ esto no es json valido",
            _line(id="dddd0002-0000-0000-0000-000000000002", content="tambien buena"),
        ]
    )
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


async def test_import_blank_lines_ignored(embeddings, store):
    jsonl = "\n".join(
        [
            "",
            _line(id="ffff0001-0000-0000-0000-000000000001", content="valida"),
            "   ",
            "",
        ]
    )
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


# ── Faithfulness gate (TKT-1291) ────────────────────────────────────────────
# Bulk import está SIEMPRE gateado (a diferencia de save/, que solo gatea
# namespaces configurados) — es inherentemente no interactivo. Mockeamos
# gate_module.call_provider — nunca gastamos Gemini real en tests.


def _mock_judge(monkeypatch, verdict_json: dict | None, raw: str | None = None):
    raw_out = (
        raw if raw is not None else (json.dumps(verdict_json) if verdict_json is not None else "")
    )
    monkeypatch.setattr(gate_module, "call_provider", lambda prompt, provider, **kw: raw_out)


async def test_import_poisoned_line_is_rejected_not_persisted(
    embeddings, store, monkeypatch, tmp_path
):
    monkeypatch.setenv("FAITHFULNESS_REVIEW_QUEUE", str(tmp_path / "queue.jsonl"))
    _mock_judge(
        monkeypatch,
        {
            "pass": False,
            "severity": "critical",
            "reasoning": "El comando 'hermes reload-mcp' no existe.",
            "claims": [
                {"claim": "x", "verdict": "CONTRADICTED", "check": "hermes --help", "evidence": "y"}
            ],
        },
    )

    mem_id = "hhhh0001-0000-0000-0000-000000000001"
    jsonl = _line(
        id=mem_id,
        content="Para recargar los MCPs corré `hermes reload-mcp`.",
        namespace="decisions",
    )

    result = await import_memories(ImportInput(jsonl=jsonl), embeddings=embeddings, store=store)

    assert result.imported == 0
    assert result.skipped == 0
    assert result.errors == []
    assert len(result.rejected) == 1
    assert result.rejected[0].line == 1
    assert result.rejected[0].verdict == "rejected"
    assert result.rejected[0].severity == "critical"
    assert await store.get(mem_id) is None

    lines = (tmp_path / "queue.jsonl").read_text().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["verdict"] == "rejected"
    assert entry["source"] == "import"


async def test_import_clean_line_is_persisted_normally(embeddings, store, monkeypatch, tmp_path):
    monkeypatch.setenv("FAITHFULNESS_REVIEW_QUEUE", str(tmp_path / "queue.jsonl"))
    _mock_judge(monkeypatch, {"pass": True, "severity": "low", "reasoning": "ok", "claims": []})

    mem_id = "iiii0001-0000-0000-0000-000000000001"
    jsonl = _line(id=mem_id, content="fact legítimo")

    result = await import_memories(ImportInput(jsonl=jsonl), embeddings=embeddings, store=store)

    assert result.imported == 1
    assert result.rejected == []
    assert await store.get(mem_id) is not None
    assert not (tmp_path / "queue.jsonl").exists()


async def test_import_judge_error_holds_line_not_persisted(
    embeddings, store, monkeypatch, tmp_path
):
    monkeypatch.setenv("FAITHFULNESS_REVIEW_QUEUE", str(tmp_path / "queue.jsonl"))
    # call_provider vacío/no parseable → verdict "error" (timeout, wrapper ausente, etc.)
    _mock_judge(monkeypatch, verdict_json=None, raw="")

    mem_id = "jjjj0001-0000-0000-0000-000000000001"
    jsonl = _line(id=mem_id, content="fact legítimo pero el juez no pudo decidir")

    result = await import_memories(ImportInput(jsonl=jsonl), embeddings=embeddings, store=store)

    assert result.imported == 0
    assert len(result.rejected) == 1
    assert result.rejected[0].verdict == "held_judge_error"
    assert await store.get(mem_id) is None

    lines = (tmp_path / "queue.jsonl").read_text().splitlines()
    entry = json.loads(lines[0])
    assert entry["verdict"] == "held_judge_error"


async def test_import_id_collision_skips_before_invoking_judge(embeddings, store, monkeypatch):
    called = {"count": 0}

    def fail_if_called(prompt, provider, **kw):
        called["count"] += 1
        raise AssertionError("call_provider no debería invocarse para un id ya existente (skip)")

    monkeypatch.setattr(gate_module, "call_provider", fail_if_called)

    existing_id = "kkkk0001-0000-0000-0000-000000000001"
    await save(
        SaveInput(content="ya existe", namespace="default"),
        embeddings=embeddings,
        store=store,
        default_namespace="default",
    )
    from mcp_memory.shared.types import Memory

    fixed_mem = Memory(
        id=existing_id,
        content="ya existe con id fijo",
        namespace="ns",
        tags=[],
        metadata={},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    vec = await embeddings.embed("ya existe con id fijo")
    await store.save(fixed_mem, vec)

    jsonl = _line(id=existing_id, content="intento de sobreescritura")
    result = await import_memories(ImportInput(jsonl=jsonl), embeddings=embeddings, store=store)

    assert result.skipped == 1
    assert result.rejected == []
    assert called["count"] == 0
