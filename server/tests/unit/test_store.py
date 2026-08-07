"""Tests unitarios de SqliteFtsStore contra ":memory:" (sin Docker, sin red).

Cubre los criterios de aceptación del ADR mcp-memory-sqlite-fts5-backend
(TKT-1470): AC1-AC11 (esquema, tokenizer, search) y AC15-AC20 (aiosqlite,
concurrencia, pragmas WAL, fallback FTS5 faltante).
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import anyio
import pytest

from mcp_memory.shared.store import SqliteFtsStore
from mcp_memory.shared.types import Memory

NS = "ns"


def _memory(content: str, *, namespace: str = NS, tags: list[str] | None = None) -> Memory:
    now = datetime.now(UTC)
    return Memory(
        id=str(uuid.uuid4()),
        content=content,
        namespace=namespace,
        tags=tags or [],
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
async def store():
    s = SqliteFtsStore(db_path=":memory:")
    await s.ensure_schema()
    try:
        yield s
    finally:
        await s.aclose()


# ─── Decisión 1 — Esquema ───────────────────────────────────────────────────


async def test_ac1_ensure_schema_is_idempotent():
    """Correr ensure_schema() dos veces seguidas no falla ni duplica nada."""
    s = SqliteFtsStore(db_path=":memory:")
    await s.ensure_schema()
    await s.ensure_schema()
    try:
        assert await s.stats(namespace=None) == {
            "count": 0,
            "namespaces": [],
            "oldest": None,
            "newest": None,
        }
    finally:
        await s.aclose()


async def test_ac2_save_then_search_round_trip(store):
    mem = _memory("recordar comprar cafe para la oficina")
    await store.save(mem)

    hits = await store.search("cafe", namespace=None, limit=10)

    assert len(hits) == 1
    assert hits[0].id == mem.id
    assert hits[0].content == mem.content


async def test_ac3_delete_cleans_fts_index(store):
    mem = _memory("palabraunicaquesoloestaaqui")
    await store.save(mem)
    assert await store.search("palabraunicaquesoloestaaqui", namespace=None, limit=10)

    deleted = await store.delete(mem.id)

    assert deleted is True
    assert await store.search("palabraunicaquesoloestaaqui", namespace=None, limit=10) == []
    # rowcount == 0 en un segundo delete confirma que ya no existe.
    assert await store.delete(mem.id) is False


async def test_ac4_update_resyncs_fts_triggers(store):
    mem = _memory("contenido viejo sobre deploys")
    await store.save(mem)

    updated = await store.update(
        mem.id, content="contenido nuevo sobre cocina", tags=None, metadata=None
    )

    assert updated is not None
    assert await store.search("deploys", namespace=None, limit=10) == []
    hits = await store.search("cocina", namespace=None, limit=10)
    assert len(hits) == 1
    assert hits[0].id == mem.id


# ─── Decisión 2 — Tokenizer ─────────────────────────────────────────────────


async def test_ac5_tokenchars_keeps_hyphenated_ids_as_single_token(store):
    mem = _memory("ver TKT-1470 para el contexto completo")
    await store.save(mem)

    full_code = await store.search("TKT-1470", namespace=None, limit=10)
    number_only = await store.search("1470", namespace=None, limit=10)

    assert len(full_code) == 1 and full_code[0].id == mem.id
    assert number_only == []


async def test_ac6_remove_diacritics_matches_accented_content(store):
    mem = _memory("una sesión de trabajo productiva")
    await store.save(mem)

    hits = await store.search("sesion", namespace=None, limit=10)

    assert len(hits) == 1
    assert hits[0].id == mem.id


async def test_ac7_mixed_language_rows_coexist_without_tokenizer_error(store):
    en = _memory("this row is entirely in english prose")
    es = _memory("esta fila está completamente en español")
    await store.save(en)
    await store.save(es)

    en_hits = await store.search("english", namespace=None, limit=10)
    es_hits = await store.search("espanol", namespace=None, limit=10)

    assert [h.id for h in en_hits] == [en.id]
    assert [h.id for h in es_hits] == [es.id]


# ─── Decisión 3 — search() ──────────────────────────────────────────────────


async def test_ac8_single_match_scores_one(store):
    await store.save(_memory("primera fila sin el termino buscado"))
    await store.save(_memory("segunda fila tampoco lo tiene"))
    target = _memory("tercera fila con TKT-1470 adentro")
    await store.save(target)

    hits = await store.search("TKT-1470", namespace=None, limit=10)

    assert len(hits) == 1
    assert hits[0].id == target.id
    assert hits[0].score == 1.0


async def test_ac9_empty_query_returns_empty_without_touching_db(store):
    await store.save(_memory("algo"))

    assert await store.search("", namespace=None, limit=10) == []
    assert await store.search("   ", namespace=None, limit=10) == []


async def test_ac10_syntax_noise_does_not_raise_operational_error(store):
    mem = _memory("una fila de prueba real")
    await store.save(mem)

    hits = await store.search('AND OR "test"', namespace=None, limit=10)

    # AND/OR quedan neutralizados por el quoting — se tratan como literales de
    # búsqueda (que no matchean nada acá), no como operadores; no debe lanzar.
    assert isinstance(hits, list)


async def test_ac11_more_matched_terms_ranks_first(store):
    one_term = _memory("el gato duerme en el sofa todo el dia")
    two_terms = _memory("el gato come pescado fresco cada dia")
    await store.save(one_term)
    await store.save(two_terms)

    hits = await store.search("gato pescado", namespace=None, limit=10)

    assert hits[0].id == two_terms.id
    assert hits[0].score >= hits[-1].score


async def test_search_filters_by_namespace(store):
    await store.save(_memory("contenido compartido", namespace="ns1"))
    await store.save(_memory("contenido compartido", namespace="ns2"))

    hits = await store.search("compartido", namespace="ns1", limit=10)

    assert len(hits) == 1
    assert hits[0].namespace == "ns1"


# ─── Decisión 5/6 — aiosqlite, concurrencia, pragmas ────────────────────────


async def test_ac15_memory_sentinel_connection_persists_across_calls():
    """La conexión se abre una vez y se reutiliza — crítico para ':memory:',
    que pierde su contenido si la conexión se cierra entre llamadas."""
    s = SqliteFtsStore(db_path=":memory:")
    await s.ensure_schema()
    try:
        mem = _memory("contenido que debe sobrevivir entre llamadas")
        await s.save(mem)
        hits = await s.search("sobrevivir", namespace=None, limit=10)
        assert len(hits) == 1
    finally:
        await s.aclose()


async def test_ac16_concurrent_operations_do_not_lock(store):
    async def _save(i: int) -> None:
        await store.save(_memory(f"memoria concurrente numero {i}"))

    async with anyio.create_task_group() as tg:
        for i in range(20):
            tg.start_soon(_save, i)

    stats = await store.stats(namespace=None)
    assert stats["count"] == 20


async def test_ac17_wal_mode_on_real_file(tmp_path):
    db_path = tmp_path / "wal.db"
    s = SqliteFtsStore(db_path=str(db_path))
    await s.ensure_schema()
    try:
        conn = await s._connect()
        cursor = await conn.execute("PRAGMA journal_mode")
        row = await cursor.fetchone()
        await cursor.close()
        assert row[0].lower() == "wal"
    finally:
        await s.aclose()


async def test_ac18_external_connection_can_read_under_wal(tmp_path):
    db_path = tmp_path / "wal-external.db"
    s = SqliteFtsStore(db_path=str(db_path))
    await s.ensure_schema()
    try:
        await s.save(_memory("visible para un lector externo"))

        external = sqlite3.connect(str(db_path))
        try:
            count = external.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            assert count == 1
        finally:
            external.close()
    finally:
        await s.aclose()


# ─── Decisión 7 — Portabilidad de FTS5 ──────────────────────────────────────


async def test_ac19_ensure_schema_does_not_raise_in_this_environment():
    """FTS5 confirmado compilado en este entorno (Homebrew/python.org Python 3.11+)."""
    s = SqliteFtsStore(db_path=":memory:")
    try:
        await s.ensure_schema()  # no debe lanzar
    finally:
        await s.aclose()


async def test_ac20_missing_fts5_reraises_as_actionable_runtime_error():
    """Mockea executescript() para simular un sqlite3 sin FTS5 compilado —
    debe re-lanzarse como RuntimeError con instrucciones accionables por
    plataforma, no propagar el OperationalError crudo."""
    s = SqliteFtsStore(db_path=":memory:")
    conn = await s._connect()
    conn.executescript = AsyncMock(
        side_effect=sqlite3.OperationalError("no such module: fts5")
    )

    with pytest.raises(RuntimeError, match="FTS5"):
        await s.ensure_schema()

    await s.aclose()


async def test_other_operational_errors_are_not_swallowed():
    """Un OperationalError que NO sea el de FTS5 faltante debe propagarse tal
    cual — solo el caso específico de FTS5 se traduce a un mensaje accionable."""
    s = SqliteFtsStore(db_path=":memory:")
    conn = await s._connect()
    conn.executescript = AsyncMock(
        side_effect=sqlite3.OperationalError("disk I/O error")
    )

    with pytest.raises(sqlite3.OperationalError, match="disk I/O error"):
        await s.ensure_schema()

    await s.aclose()
