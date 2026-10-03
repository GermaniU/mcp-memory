import asyncio

from mcp_memory.tools.save.handler import SaveInput, save
from mcp_memory.tools.update.handler import UpdateInput, update


async def test_update_changes_content_and_bumps_updated_at(store):
    saved = await save(SaveInput(content="v1"), store=store, default_namespace="default")
    await asyncio.sleep(0.01)
    out = await update(
        UpdateInput(id=saved.id, content="v2"),
        store=store,
    )
    assert out is not None
    assert out.content == "v2"
    assert out.id == saved.id
    assert out.updated_at > saved.updated_at


async def test_update_only_tags_keeps_content(store):
    saved = await save(
        SaveInput(content="v1", tags=["a"]),
        store=store,
        default_namespace="default",
    )
    out = await update(UpdateInput(id=saved.id, tags=["b", "c"]), store=store)
    assert out is not None
    assert out.content == "v1"
    assert out.tags == ["b", "c"]


async def test_update_missing_returns_none(store):
    out = await update(
        UpdateInput(id="00000000-0000-0000-0000-000000000000", content="x"),
        store=store,
    )
    assert out is None
