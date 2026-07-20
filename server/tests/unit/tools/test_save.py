import json

import pytest

from mcp_memory.faithfulness import gate as gate_module
from mcp_memory.faithfulness.gate import FaithfulnessGateError
from mcp_memory.tools.save.handler import SaveInput, save


async def test_save_returns_memory_with_generated_id_and_timestamps(embeddings, store):
    out = await save(
        SaveInput(content="recordar a juan"),
        embeddings=embeddings,
        store=store,
        default_namespace="default",
    )
    assert out.id
    assert out.content == "recordar a juan"
    assert out.namespace == "default"
    assert out.created_at == out.updated_at


async def test_save_uses_explicit_namespace_and_tags(embeddings, store):
    out = await save(
        SaveInput(content="x", namespace="flowordr", tags=["bug", "auth"]),
        embeddings=embeddings,
        store=store,
        default_namespace="default",
    )
    assert out.namespace == "flowordr"
    assert out.tags == ["bug", "auth"]


async def test_save_rejects_empty_content(embeddings, store):
    with pytest.raises(ValueError):
        await save(
            SaveInput(content="   "),
            embeddings=embeddings,
            store=store,
            default_namespace="default",
        )


# ── Faithfulness gate (TKT-1291) ────────────────────────────────────────────
# Namespace "decisions" es gateado por default (FAITHFULNESS_GATE_NAMESPACES).
# Mockeamos gate_module.call_provider — nunca gastamos Gemini real en tests.


def _mock_judge(monkeypatch, verdict_json: dict | None, raw: str | None = None):
    raw_out = (
        raw if raw is not None else (json.dumps(verdict_json) if verdict_json is not None else "")
    )
    monkeypatch.setattr(gate_module, "call_provider", lambda prompt, provider, **kw: raw_out)


async def test_save_gated_namespace_poisoned_fact_is_rejected_not_persisted(
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

    with pytest.raises(FaithfulnessGateError):
        await save(
            SaveInput(
                content="Para recargar los MCPs corré `hermes reload-mcp`.", namespace="decisions"
            ),
            embeddings=embeddings,
            store=store,
            default_namespace="default",
        )

    # Nada persistido.
    stats = await store.stats(namespace="decisions")
    assert stats["count"] == 0

    # Quedó en la cola de revisión como "rejected".
    lines = (tmp_path / "queue.jsonl").read_text().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["verdict"] == "rejected"
    assert entry["namespace"] == "decisions"
    assert entry["source"] == "save"


async def test_save_gated_namespace_clean_fact_is_persisted(
    embeddings, store, monkeypatch, tmp_path
):
    monkeypatch.setenv("FAITHFULNESS_REVIEW_QUEUE", str(tmp_path / "queue.jsonl"))
    _mock_judge(monkeypatch, {"pass": True, "severity": "low", "reasoning": "ok", "claims": []})

    out = await save(
        SaveInput(content="mcp-memory expone memory_save vía MCP.", namespace="decisions"),
        embeddings=embeddings,
        store=store,
        default_namespace="default",
    )

    assert out.namespace == "decisions"
    stats = await store.stats(namespace="decisions")
    assert stats["count"] == 1
    assert not (tmp_path / "queue.jsonl").exists()


async def test_save_gated_namespace_judge_error_is_held_not_persisted(
    embeddings, store, monkeypatch, tmp_path
):
    monkeypatch.setenv("FAITHFULNESS_REVIEW_QUEUE", str(tmp_path / "queue.jsonl"))
    # call_provider vacío/no parseable → verdict "error" (timeout, wrapper ausente, etc.)
    _mock_judge(monkeypatch, verdict_json=None, raw="")

    with pytest.raises(FaithfulnessGateError):
        await save(
            SaveInput(content="fact legítimo pero el juez no pudo decidir", namespace="decisions"),
            embeddings=embeddings,
            store=store,
            default_namespace="default",
        )

    stats = await store.stats(namespace="decisions")
    assert stats["count"] == 0

    lines = (tmp_path / "queue.jsonl").read_text().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["verdict"] == "held_judge_error"


async def test_save_non_gated_namespace_bypasses_judge_entirely(embeddings, store, monkeypatch):
    called = {"count": 0}

    def fail_if_called(prompt, provider, **kw):
        called["count"] += 1
        raise AssertionError("call_provider no debería invocarse para un namespace no gateado")

    monkeypatch.setattr(gate_module, "call_provider", fail_if_called)

    out = await save(
        SaveInput(content="nota rápida cualquiera", namespace="default"),
        embeddings=embeddings,
        store=store,
        default_namespace="default",
    )

    assert out.namespace == "default"
    assert called["count"] == 0
