from mcp_memory.tools.list_.handler import ListInput, list_memories
from mcp_memory.tools.save.handler import SaveInput, save


async def test_list_returns_all_in_namespace(store):
    for i in range(3):
        await save(
            SaveInput(content=f"m{i}", namespace="ns"),
            store=store,
            default_namespace="default",
        )
    out = await list_memories(ListInput(namespace="ns"), store=store)
    assert len(out) == 3


async def test_list_pagination(store):
    for i in range(5):
        await save(SaveInput(content=f"m{i}"), store=store, default_namespace="default")
    page1 = await list_memories(ListInput(limit=2, offset=0), store=store)
    page2 = await list_memories(ListInput(limit=2, offset=2), store=store)
    assert len(page1) == 2
    assert len(page2) == 2
    assert {m.id for m in page1}.isdisjoint({m.id for m in page2})
