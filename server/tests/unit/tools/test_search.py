from mcp_memory.tools.save.handler import SaveInput, save
from mcp_memory.tools.search.handler import SearchInput, search


async def test_search_returns_most_similar_first(store):
    for txt in ["el gato come pescado", "la receta de la abuela", "el perro ladra fuerte"]:
        await save(SaveInput(content=txt), store=store, default_namespace="default")

    out = await search(SearchInput(query="el gato come pescado", limit=2), store=store)
    assert len(out) == 2
    assert out[0].content == "el gato come pescado"
    assert out[0].score is not None and out[0].score >= (out[1].score or 0)


async def test_search_filters_by_namespace(store):
    await save(SaveInput(content="a", namespace="ns1"), store=store, default_namespace="default")
    await save(SaveInput(content="a", namespace="ns2"), store=store, default_namespace="default")

    out = await search(SearchInput(query="a", namespace="ns1"), store=store)
    assert len(out) == 1
    assert out[0].namespace == "ns1"


async def test_search_returns_empty_when_no_terms_match(store):
    # BM25/FTS5 es léxico, no semántico: sin `min_score` (eliminado del contrato,
    # Decisión 4 del ADR), una query sin ningún término en común con el contenido
    # simplemente no matchea nada — no hay threshold que ajustar.
    await save(SaveInput(content="hola"), store=store, default_namespace="default")
    out = await search(SearchInput(query="completamente otra cosa xyz"), store=store)
    assert out == []


async def test_search_empty_query_returns_empty(store):
    await save(SaveInput(content="hola"), store=store, default_namespace="default")
    out = await search(SearchInput(query="   "), store=store)
    assert out == []


async def test_search_default_limit_is_twenty():
    assert SearchInput(query="x").limit == 20
