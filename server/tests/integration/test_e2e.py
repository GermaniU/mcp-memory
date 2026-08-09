"""Integration tests contra un SqliteFtsStore REAL — sin ningún servicio externo.

Antes requerían Qdrant + Ollama vivos (marker `integration`, auto-skip si no
respondían). Con el backend SQLite + FTS5 (TKT-1470, ADR
mcp-memory-sqlite-fts5-backend) el path E2E real corre siempre: real
SqliteFtsStore + FastMCP `Client(app)` transporte in-memory, sin mocks, sin
marker. Cubre AC1-AC4, AC8-AC11, AC15-AC18.

Run:  pytest tests/integration
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime

import anyio
import pytest
from fastmcp import Client

from mcp_memory.server import build_app
from mcp_memory.shared.config import Settings
from mcp_memory.shared.store import SqliteFtsStore
from mcp_memory.shared.types import Memory

NS = "itest"


def _data(result):
    """Extract structured payload from a CallToolResult."""
    if result.structured_content is not None:
        sc = result.structured_content
        return sc.get("result", sc) if isinstance(sc, dict) else sc
    return json.loads(result.content[0].text)


@pytest.fixture
async def app():
    """Build the FastMCP app on una SqliteFtsStore ':memory:' fresca por test."""
    settings = Settings(db_path=":memory:", default_namespace=NS)
    store = SqliteFtsStore(db_path=settings.db_path)
    await store.ensure_schema()
    application = build_app(settings=settings, store=store)
    try:
        yield application
    finally:
        await store.aclose()


async def test_ensure_schema_is_idempotent():
    """AC1: correr ensure_schema() dos veces seguidas no falla ni duplica nada."""
    store = SqliteFtsStore(db_path=":memory:")
    await store.ensure_schema()
    await store.ensure_schema()  # segunda pasada — CREATE ... IF NOT EXISTS en todo
    try:
        stats = await store.stats(namespace=None)
        assert stats["count"] == 0
    finally:
        await store.aclose()


async def test_save_then_search_literal_match(app):
    """AC2/AC8: round-trip save→search por palabra literal; único match -> score 1.0."""
    async with Client(app) as c:
        saved = _data(await c.call_tool("memory_save", {
            "content": "Germani prefiere copy en espanol MX neutro, ver TKT-1470",
            "namespace": NS, "tags": ["estilo", "copy"],
        }))
        assert saved["id"]
        assert saved["namespace"] == NS

        hits = _data(await c.call_tool("memory_search", {
            "query": "TKT-1470", "namespace": NS, "limit": 5,
        }))
        assert len(hits) == 1
        assert hits[0]["id"] == saved["id"]
        assert hits[0]["score"] == 1.0


async def test_search_empty_query_returns_empty(app):
    """AC9: query vacía o solo whitespace no toca la DB, devuelve []."""
    async with Client(app) as c:
        await c.call_tool("memory_save", {"content": "algo", "namespace": NS})

        hits_empty = _data(await c.call_tool("memory_search", {"query": "", "namespace": NS}))
        hits_blank = _data(await c.call_tool("memory_search", {"query": "   ", "namespace": NS}))
        assert hits_empty == []
        assert hits_blank == []


async def test_search_syntax_noise_does_not_raise(app):
    """AC10: tokens AND/OR/NOT quedan neutralizados por el quoting defensivo."""
    async with Client(app) as c:
        saved = _data(await c.call_tool("memory_save", {
            "content": "una nota de prueba real", "namespace": NS,
        }))
        hits = _data(await c.call_tool("memory_search", {
            "query": 'AND OR "prueba"', "namespace": NS, "limit": 5,
        }))
        assert any(h["id"] == saved["id"] for h in hits)


async def test_search_ranks_more_matched_terms_first(app):
    """AC11: la fila con más términos de la query matcheados rankea primero."""
    async with Client(app) as c:
        one_term = _data(await c.call_tool("memory_save", {
            "content": "el gato duerme en el sofa", "namespace": NS,
        }))
        two_terms = _data(await c.call_tool("memory_save", {
            "content": "el gato come pescado fresco", "namespace": NS,
        }))

        hits = _data(await c.call_tool("memory_search", {
            "query": "gato pescado", "namespace": NS, "limit": 5,
        }))
        assert hits[0]["id"] == two_terms["id"]
        assert hits[0]["score"] >= hits[-1]["score"]
        if len(hits) > 1:
            assert one_term["id"] in {h["id"] for h in hits}


async def test_update_resyncs_fts_index(app):
    """AC4: search por contenido viejo deja de matchear; por contenido nuevo sí."""
    async with Client(app) as c:
        saved = _data(await c.call_tool("memory_save", {
            "content": "el deploy corre en un VPS Contabo", "namespace": NS,
        }))
        upd = _data(await c.call_tool("memory_update", {
            "id": saved["id"],
            "content": "las ordenes dine-in entran al tablero de cocina",
        }))
        assert "cocina" in upd["content"]

        old_hits = _data(await c.call_tool("memory_search", {
            "query": "Contabo", "namespace": NS,
        }))
        assert old_hits == []

        new_hits = _data(await c.call_tool("memory_search", {
            "query": "cocina", "namespace": NS,
        }))
        assert new_hits and new_hits[0]["id"] == saved["id"]


async def test_delete_removes_from_fts_index(app):
    """AC3: tras delete, buscar una palabra que solo estaba en esa fila da 0 hits."""
    async with Client(app) as c:
        saved = _data(await c.call_tool("memory_save", {
            "content": "palabraunicaparaeltest borrame", "namespace": NS,
        }))
        d = _data(await c.call_tool("memory_delete", {"id": saved["id"]}))
        assert d["deleted"] is True

        hits = _data(await c.call_tool("memory_search", {
            "query": "palabraunicaparaeltest", "namespace": NS,
        }))
        assert hits == []

        d2 = _data(await c.call_tool("memory_delete", {"id": saved["id"]}))
        assert d2["deleted"] is False


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
            await c.call_tool("memory_save", {"content": f"dato de stats {i}", "namespace": NS})
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


async def test_export_import_round_trip(app):
    """Simula el flujo de migración: export → delete src → import a otro namespace."""
    src_ns = "itest-export-src"
    dst_ns = "itest-export-dst"
    async with Client(app) as c:
        saved_ids = []
        for content in [
            "El deploy de prod corre en un VPS Contabo",
            "SQLite FTS5 indexa contenido lexico via BM25",
            "Hermes orquesta agentes especializados en tareas concretas",
        ]:
            r = _data(await c.call_tool("memory_save", {"content": content, "namespace": src_ns}))
            saved_ids.append(r["id"])

        export_result = _data(await c.call_tool("memory_export", {"namespace": src_ns}))
        assert export_result["count"] == 3
        assert export_result["jsonl"]

        for mid in saved_ids:
            await c.call_tool("memory_delete", {"id": mid})

        import_result = _data(await c.call_tool("memory_import", {
            "jsonl": export_result["jsonl"],
            "namespace_override": dst_ns,
        }))
        assert import_result["imported"] == 3
        assert import_result["skipped"] == 0
        assert import_result["errors"] == []

        # Segunda importación con los mismos IDs: ya existen en dst -> todo skipped.
        import_again = _data(await c.call_tool("memory_import", {
            "jsonl": export_result["jsonl"],
            "namespace_override": dst_ns,
        }))
        assert import_again["imported"] == 0
        assert import_again["skipped"] == 3

        hits = _data(await c.call_tool("memory_search", {
            "query": "VPS Contabo", "namespace": dst_ns, "limit": 5,
        }))
        assert len(hits) >= 1


async def test_ac15_memory_sentinel_persists_within_session():
    """AC15: la conexión se abre una vez y se reutiliza — save→search en la
    misma sesión de ':memory:' funciona (si se reabriera, ':memory:' pierde
    todo su contenido)."""
    store = SqliteFtsStore(db_path=":memory:")
    await store.ensure_schema()
    try:
        mem = Memory(
            id=str(uuid.uuid4()),
            content="contenido que debe persistir entre llamadas",
            namespace=NS,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        await store.save(mem)
        hits = await store.search("persistir", namespace=NS, limit=5)
        assert len(hits) == 1
        assert hits[0].id == mem.id
    finally:
        await store.aclose()


async def test_ac16_concurrent_saves_do_not_lock(app):
    """AC16: N operaciones concurrentes (anyio.gather) completan sin
    'database is locked' — sin manejo de error especial en el código de la app."""
    async with Client(app) as c:
        async def _save(i: int) -> None:
            await c.call_tool("memory_save", {
                "content": f"memoria concurrente {i}", "namespace": NS,
            })

        async with anyio.create_task_group() as tg:
            for i in range(15):
                tg.start_soon(_save, i)

        st = _data(await c.call_tool("memory_stats", {"namespace": NS}))
        assert st["count"] == 15


async def test_ac17_wal_mode_on_real_file(tmp_path):
    """AC17: PRAGMA journal_mode devuelve 'wal' tras _connect() sobre un
    archivo real (":memory:" ignora WAL — no aplica ahí)."""
    db_path = tmp_path / "wal-test.db"
    store = SqliteFtsStore(db_path=str(db_path))
    await store.ensure_schema()
    try:
        conn = await store._connect()
        cursor = await conn.execute("PRAGMA journal_mode")
        row = await cursor.fetchone()
        await cursor.close()
        assert row[0].lower() == "wal"
    finally:
        await store.aclose()


async def test_ac18_external_reader_does_not_fail_under_wal(tmp_path):
    """AC18: una segunda conexión externa (sqlite3 crudo) puede leer mientras
    el store mantiene la conexión abierta — WAL permite el lector concurrente."""
    db_path = tmp_path / "wal-external.db"
    store = SqliteFtsStore(db_path=str(db_path))
    await store.ensure_schema()
    try:
        mem = Memory(
            id=str(uuid.uuid4()),
            content="visible para un lector externo",
            namespace=NS,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        await store.save(mem)

        external = sqlite3.connect(str(db_path))
        try:
            cursor = external.execute("SELECT COUNT(*) FROM memories")
            assert cursor.fetchone()[0] == 1
        finally:
            external.close()
    finally:
        await store.aclose()
