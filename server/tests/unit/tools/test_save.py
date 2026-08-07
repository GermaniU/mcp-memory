import pytest

from mcp_memory.tools.save.handler import SaveInput, save


async def test_save_returns_memory_with_generated_id_and_timestamps(store):
    out = await save(
        SaveInput(content="recordar a juan"),
        store=store,
        default_namespace="default",
    )
    assert out.id
    assert out.content == "recordar a juan"
    assert out.namespace == "default"
    assert out.created_at == out.updated_at


async def test_save_uses_explicit_namespace_and_tags(store):
    out = await save(
        SaveInput(content="x", namespace="flowordr", tags=["bug", "auth"]),
        store=store,
        default_namespace="default",
    )
    assert out.namespace == "flowordr"
    assert out.tags == ["bug", "auth"]


async def test_save_rejects_empty_content(store):
    with pytest.raises(ValueError):
        await save(
            SaveInput(content="   "),
            store=store,
            default_namespace="default",
        )
