"""Integration tests against REAL Qdrant + Ollama (localhost).

These exercise the full stack in-memory via FastMCP's ``Client(app)`` transport:
real QdrantStore + real OllamaEmbeddings, no HTTP server, no mocks. They run on an
ephemeral collection (``mcp_memory_itest``) that is created and dropped per session.

Run:  pytest tests/integration -m integration
Auto-skips cleanly if Qdrant or Ollama are unreachable.
"""

from __future__ import annotations

import contextlib
import json
import uuid

import httpx
import pytest
from fastmcp import Client
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qm

from mcp_memory.server import build_app
from mcp_memory.shared.config import Settings
from mcp_memory.shared.embeddings import OllamaEmbeddings
from mcp_memory.shared.store import QdrantStore

pytestmark = pytest.mark.integration

QDRANT_URL = "http://localhost:6333"
OLLAMA_URL = "http://localhost:11434"
MODEL = "bge-m3"
DIM = 1024
ITEST_COLLECTION = "mcp_memory_itest"
NS = "itest"


def _data(result):
    """Extract structured payload from a CallToolResult."""
    if result.structured_content is not None:
        sc = result.structured_content
        return sc.get("result", sc) if isinstance(sc, dict) else sc
    return json.loads(result.content[0].text)


async def _services_up() -> str | None:
    """Return None if both services answer, else a skip reason."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as c:
            r = await c.get(f"{QDRANT_URL}/readyz")
            if r.status_code >= 500:
                return f"Qdrant not ready ({r.status_code})"
    except Exception as exc:  # any connectivity error -> skip
        return f"Qdrant unreachable: {exc}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.post(
                f"{OLLAMA_URL}/api/embed", json={"model": MODEL, "input": "ping"}
            )
            r.raise_for_status()
            embs = r.json().get("embeddings") or []
            if not embs or len(embs[0]) != DIM:
                return f"Ollama model {MODEL} not serving {DIM}-dim embeddings"
    except Exception as exc:  # any connectivity error -> skip
        return f"Ollama unreachable: {exc}"
    return None


@pytest.fixture
async def app():
    """Build the FastMCP app on a fresh ephemeral collection; drop it on teardown."""
    reason = await _services_up()
    if reason:
        pytest.skip(reason)

    settings = Settings(
        embedding_model=MODEL,
        embedding_dim=DIM,
        ollama_url=OLLAMA_URL,
        qdrant_url=QDRANT_URL,
        qdrant_collection=ITEST_COLLECTION,
        default_namespace=NS,
    )
    # Start from a clean slate even if a prior run left the collection behind.
    admin = AsyncQdrantClient(url=QDRANT_URL)
    with contextlib.suppress(Exception):
        await admin.delete_collection(ITEST_COLLECTION)

    store = QdrantStore(
        url=settings.qdrant_url,
        collection=settings.qdrant_collection,
        dim=settings.embedding_dim,
    )
    embeddings = OllamaEmbeddings(
        base_url=settings.ollama_url,
        model=settings.embedding_model,
        api_key=settings.ollama_api_key,
        expected_dim=settings.embedding_dim,
    )
    await store.ensure_collection()
    application = build_app(settings=settings, embeddings=embeddings, store=store)
    try:
        yield application
    finally:
        await embeddings.aclose()
        await store.aclose()
        try:
            await admin.delete_collection(ITEST_COLLECTION)
        finally:
            await admin.close()


async def test_save_then_semantic_search_cross_keyword(app):
    async with Client(app) as c:
        saved = _data(await c.call_tool("memory_save", {
            "content": "Germani prefiere copy en espanol MX neutro con tu, sin argentinismos",
            "namespace": NS, "tags": ["estilo", "copy"],
        }))
        assert saved["id"]
        assert saved["namespace"] == NS

        # Query shares no exact keywords with the stored content -> tests real embeddings.
        hits = _data(await c.call_tool("memory_search", {
            "query": "que tono de redaccion usar para textos de clientes mexicanos?",
            "namespace": NS, "limit": 5,
        }))
        assert len(hits) >= 1
        assert hits[0]["id"] == saved["id"]
        assert hits[0]["score"] is not None and hits[0]["score"] > 0


async def test_update_reembeds(app):
    async with Client(app) as c:
        saved = _data(await c.call_tool("memory_save", {
            "content": "El deploy de prod corre en un VPS Contabo con Docker",
            "namespace": NS,
        }))
        upd = _data(await c.call_tool("memory_update", {
            "id": saved["id"],
            "content": "Las ordenes dine-in entran al tablero de cocina al confirmarse",
        }))
        assert "cocina" in upd["content"]

        hits = _data(await c.call_tool("memory_search", {
            "query": "flujo de pedidos del restaurante hacia la cocina",
            "namespace": NS, "limit": 3,
        }))
        assert hits and hits[0]["id"] == saved["id"]


async def test_recent_is_ordered(app):
    async with Client(app) as c:
        ids = []
        for i in range(3):
            r = _data(await c.call_tool("memory_save", {
                "content": f"memoria numero {i} para ordenamiento temporal",
                "namespace": NS,
            }))
            ids.append(r["id"])

        recent = _data(await c.call_tool("memory_recent", {"namespace": NS, "limit": 3}))
        assert [m["id"] for m in recent] == list(reversed(ids))


async def test_stats(app):
    async with Client(app) as c:
        for i in range(2):
            await c.call_tool("memory_save", {
                "content": f"dato de stats {i}", "namespace": NS,
            })
        await c.call_tool("memory_save", {
            "content": "dato en otro namespace", "namespace": "itest-other",
        })

        st = _data(await c.call_tool("memory_stats", {"namespace": NS}))
        assert st["count"] == 2
        assert st["namespaces"] == [NS]
        assert st["oldest"] is not None
        assert st["newest"] is not None

        st_all = _data(await c.call_tool("memory_stats", {}))
        assert st_all["count"] == 3
        assert set(st_all["namespaces"]) == {NS, "itest-other"}


async def test_delete(app):
    async with Client(app) as c:
        saved = _data(await c.call_tool("memory_save", {
            "content": "memoria a borrar", "namespace": NS,
        }))
        d = _data(await c.call_tool("memory_delete", {"id": saved["id"]}))
        assert d["deleted"] is True

        d2 = _data(await c.call_tool("memory_delete", {"id": saved["id"]}))
        assert d2["deleted"] is False


async def test_stats_no_phantom_namespace_after_delete(app):
    """Namespace fantasma: tras borrar todos sus points no debe aparecer en memory_stats."""
    async with Client(app) as c:
        # (a) Guardamos una memoria en el namespace a fantasmear.
        ghost = _data(await c.call_tool("memory_save", {
            "content": "memoria fantasma que sera borrada",
            "namespace": "ghost-ns",
        }))
        # (b) Guardamos otra en un segundo namespace para que count global > 0
        #     y stats no haga early-return antes de llegar al facet.
        _data(await c.call_tool("memory_save", {
            "content": "memoria permanente en namespace real",
            "namespace": "real-ns",
        }))
        # (c) Borramos el único point de ghost-ns.
        deleted = _data(await c.call_tool("memory_delete", {"id": ghost["id"]}))
        assert deleted["deleted"] is True

        # (d) stats global no debe listar ghost-ns; real-ns sí debe aparecer.
        st = _data(await c.call_tool("memory_stats", {}))
        assert "ghost-ns" not in st["namespaces"]
        assert "real-ns" in st["namespaces"]


async def test_export_import_round_trip(app):
    """Exportar desde un namespace, borrar origen, importar con override a otro namespace.

    Este test simula el flujo real de migración: export → delete src → import to dst.
    La colisión de IDs solo aplica si el punto sigue existiendo; tras el delete puede importarse.
    El round-trip finaliza verificando que memory_search semántico encuentra el contenido en dst.
    """
    src_ns = "itest-export-src"
    dst_ns = "itest-export-dst"
    async with Client(app) as c:
        # 1. Guardamos 3 memorias en el namespace origen.
        saved_ids = []
        for content in [
            "El deploy de prod corre en un VPS Contabo",
            "Qdrant almacena vectores de embeddings bge-m3",
            "Hermes orquesta agentes especializados en tareas concretas",
        ]:
            r = _data(await c.call_tool("memory_save", {"content": content, "namespace": src_ns}))
            saved_ids.append(r["id"])

        # 2. Exportamos el namespace origen.
        export_result = _data(await c.call_tool("memory_export", {"namespace": src_ns}))
        assert export_result["count"] == 3
        assert export_result["jsonl"]

        # 3. Borramos las memorias de origen para liberar los IDs.
        for mid in saved_ids:
            await c.call_tool("memory_delete", {"id": mid})

        # 4. Importamos con override al namespace destino — IDs ya no existen, sin colisión.
        import_result = _data(await c.call_tool("memory_import", {
            "jsonl": export_result["jsonl"],
            "namespace_override": dst_ns,
        }))
        assert import_result["imported"] == 3
        assert import_result["skipped"] == 0
        assert import_result["errors"] == []

        # 5. Segunda importación con los mismos IDs: ahora existen en dst → todo skipped.
        import_again = _data(await c.call_tool("memory_import", {
            "jsonl": export_result["jsonl"],
            "namespace_override": dst_ns,
        }))
        assert import_again["imported"] == 0
        assert import_again["skipped"] == 3

        # 6. Búsqueda semántica en el namespace destino encuentra el contenido re-embedado.
        hits = _data(await c.call_tool("memory_search", {
            "query": "infraestructura de servidor y contenedores en produccion",
            "namespace": dst_ns,
            "limit": 5,
        }))
        assert len(hits) >= 1
        hit_contents = [h["content"] for h in hits]
        assert any("VPS" in ct or "Qdrant" in ct or "Hermes" in ct for ct in hit_contents)


async def test_dim_mismatch_raises():
    """A collection created with a different vector size must fail ensure_collection."""
    reason = await _services_up()
    if reason:
        pytest.skip(reason)

    collection = f"mcp_memory_itest_dim_{uuid.uuid4().hex[:8]}"
    admin = AsyncQdrantClient(url=QDRANT_URL)
    try:
        await admin.create_collection(
            collection_name=collection,
            vectors_config=qm.VectorParams(size=512, distance=qm.Distance.COSINE),
        )
        store = QdrantStore(url=QDRANT_URL, collection=collection, dim=DIM)
        with pytest.raises(RuntimeError, match="vector size 512"):
            await store.ensure_collection()
        await store.aclose()
    finally:
        try:
            await admin.delete_collection(collection)
        finally:
            await admin.close()
