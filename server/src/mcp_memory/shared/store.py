from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite

from mcp_memory.shared.types import Memory

# DDL — Decisión 1 del ADR (mcp-memory-sqlite-fts5-backend). Tabla normal `memories`
# (fuente de verdad, con índices B-tree reales) + tabla virtual FTS5 externa
# `memories_fts` (content='memories'), sincronizada por triggers AI/AD/AU. Todo
# `IF NOT EXISTS` — idempotente, seguro de correr en cada boot.
_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS memories (
    id          TEXT PRIMARY KEY,
    content     TEXT NOT NULL,
    namespace   TEXT NOT NULL,
    tags        TEXT NOT NULL DEFAULT '[]',
    metadata    TEXT NOT NULL DEFAULT '{}',
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_memories_namespace  ON memories(namespace);
CREATE INDEX IF NOT EXISTS idx_memories_updated_at ON memories(updated_at);
CREATE INDEX IF NOT EXISTS idx_memories_created_at ON memories(created_at);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    content,
    tags,
    content='memories',
    content_rowid='rowid',
    tokenize="unicode61 remove_diacritics 2 tokenchars '-_'"
);

CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
  INSERT INTO memories_fts(rowid, content, tags) VALUES (new.rowid, new.content, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
  INSERT INTO memories_fts(memories_fts, rowid, content, tags)
  VALUES('delete', old.rowid, old.content, old.tags);
END;

CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
  INSERT INTO memories_fts(memories_fts, rowid, content, tags)
  VALUES('delete', old.rowid, old.content, old.tags);
  INSERT INTO memories_fts(rowid, content, tags) VALUES (new.rowid, new.content, new.tags);
END;
"""

_SELECT_COLUMNS = "id, content, namespace, tags, metadata, created_at, updated_at"

_FTS5_MISSING_MSG = (
    "Tu Python no tiene FTS5 compilado en su módulo sqlite3 "
    "('no such module: fts5'). mcp-memory requiere FTS5 para buscar.\n"
    "  - macOS: usa Homebrew (`brew install python@3.12`) o el instalador de "
    "python.org — ambos traen FTS5.\n"
    "  - Linux: instala `libsqlite3-dev` ANTES de compilar Python (pyenv/asdf), "
    "o usa el Python del sistema de tu distro.\n"
    "  - Windows: el instalador oficial de python.org trae FTS5.\n"
    "Verificá con: python3 -c \"import sqlite3; "
    "sqlite3.connect(':memory:').execute('CREATE VIRTUAL TABLE t USING fts5(x)')\""
)


class SqliteFtsStore:
    """MemoryStore backed por un archivo SQLite local + FTS5 (BM25 léxico).

    Sin infra externa: `db_path` puede ser un archivo real o ``":memory:"``
    (efímero, usado en tests). La conexión se abre una única vez (lazy) y se
    reutiliza para todo el ciclo de vida del store — crítico para `:memory:`,
    que pierde su contenido si la conexión se cierra.
    """

    def __init__(self, *, db_path: str) -> None:
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def _connect(self) -> aiosqlite.Connection:
        if self._conn is None:
            if self._db_path != ":memory:":
                # "~" ya viene expandido por config.get_settings() (Decisión 8) —
                # acá solo se asegura que el directorio padre exista.
                Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            conn = await aiosqlite.connect(self._db_path)
            conn.row_factory = aiosqlite.Row
            # Decisión 6 — concurrencia. WAL no aplica a ":memory:" (SQLite lo
            # ignora silenciosamente y queda en modo "memory"); se reafirma en
            # cada apertura de conexión de todas formas, sin costo real.
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA synchronous=NORMAL")
            await conn.execute("PRAGMA busy_timeout=5000")
            self._conn = conn
        return self._conn

    async def ensure_schema(self) -> None:
        conn = await self._connect()
        try:
            await conn.executescript(_SCHEMA_SQL)
            await conn.commit()
        except sqlite3.OperationalError as exc:
            if "no such module: fts5" in str(exc):
                raise RuntimeError(_FTS5_MISSING_MSG) from exc
            raise

    async def get(self, memory_id: str) -> Memory | None:
        conn = await self._connect()
        cursor = await conn.execute(
            f"SELECT {_SELECT_COLUMNS} FROM memories WHERE id = :id",
            {"id": memory_id},
        )
        row = await cursor.fetchone()
        await cursor.close()
        return _from_row(row) if row is not None else None

    async def save(self, memory: Memory) -> Memory:
        conn = await self._connect()
        await conn.execute(
            "INSERT INTO memories (id, content, namespace, tags, metadata, created_at, updated_at) "
            "VALUES (:id, :content, :namespace, :tags, :metadata, :created_at, :updated_at)",
            _to_params(memory),
        )
        await conn.commit()
        return memory

    async def update(
        self,
        memory_id: str,
        *,
        content: str | None,
        tags: list[str] | None,
        metadata: dict | None,
    ) -> Memory | None:
        existing = await self.get(memory_id)
        if existing is None:
            return None
        updated = existing.model_copy(
            update={
                "content": content if content is not None else existing.content,
                "tags": tags if tags is not None else existing.tags,
                "metadata": metadata if metadata is not None else existing.metadata,
                "updated_at": datetime.now(UTC),
            }
        )
        conn = await self._connect()
        await conn.execute(
            "UPDATE memories SET content=:content, tags=:tags, metadata=:metadata, "
            "updated_at=:updated_at WHERE id=:id",
            {
                "id": updated.id,
                "content": updated.content,
                "tags": json.dumps(updated.tags, ensure_ascii=False),
                "metadata": json.dumps(updated.metadata, ensure_ascii=False),
                "updated_at": updated.updated_at.timestamp(),
            },
        )
        await conn.commit()
        # Trigger memories_au re-sincroniza memories_fts (delete + insert) automáticamente.
        return updated

    async def delete(self, memory_id: str) -> bool:
        conn = await self._connect()
        cursor = await conn.execute("DELETE FROM memories WHERE id = :id", {"id": memory_id})
        await conn.commit()
        deleted = cursor.rowcount > 0
        await cursor.close()
        # Trigger memories_ad limpia memories_fts automáticamente.
        return deleted

    async def search(
        self,
        query: str,
        *,
        namespace: str | None,
        limit: int,
    ) -> list[Memory]:
        match_expr = _build_match_expr(query)
        if match_expr is None:
            return []
        conn = await self._connect()
        cursor = await conn.execute(
            """
            SELECT m.id, m.content, m.namespace, m.tags, m.metadata, m.created_at, m.updated_at,
                   bm25(memories_fts) AS raw_score
            FROM memories_fts
            JOIN memories m ON m.rowid = memories_fts.rowid
            WHERE memories_fts MATCH :match_expr
              AND (:namespace IS NULL OR m.namespace = :namespace)
            ORDER BY raw_score ASC
            LIMIT :limit
            """,
            {"match_expr": match_expr, "namespace": namespace, "limit": limit},
        )
        rows = await cursor.fetchall()
        await cursor.close()
        if not rows:
            return []

        # Normalización min-max de bm25() (más negativo = mejor) al rango [0,1]
        # dentro de esta página de resultados — NO comparable entre llamadas.
        raw_scores = [row["raw_score"] for row in rows]
        best = min(raw_scores)
        worst = max(raw_scores)
        results: list[Memory] = []
        for row in rows:
            raw = row["raw_score"]
            norm_score = 1.0 if best == worst else (worst - raw) / (worst - best)
            results.append(_from_row(row, score=norm_score))
        return results

    async def list_(
        self,
        *,
        namespace: str | None,
        limit: int,
        offset: int,
    ) -> list[Memory]:
        conn = await self._connect()
        cursor = await conn.execute(
            f"SELECT {_SELECT_COLUMNS} FROM memories "
            "WHERE (:namespace IS NULL OR namespace = :namespace) "
            "ORDER BY rowid ASC LIMIT :limit OFFSET :offset",
            {"namespace": namespace, "limit": limit, "offset": offset},
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [_from_row(row) for row in rows]

    async def recent(self, *, namespace: str | None, limit: int) -> list[Memory]:
        conn = await self._connect()
        cursor = await conn.execute(
            f"SELECT {_SELECT_COLUMNS} FROM memories "
            "WHERE (:namespace IS NULL OR namespace = :namespace) "
            "ORDER BY updated_at DESC LIMIT :limit",
            {"namespace": namespace, "limit": limit},
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [_from_row(row) for row in rows]

    async def stats(self, *, namespace: str | None) -> dict[str, Any]:
        conn = await self._connect()
        params = {"namespace": namespace}

        cursor = await conn.execute(
            "SELECT COUNT(*) AS c FROM memories "
            "WHERE (:namespace IS NULL OR namespace = :namespace)",
            params,
        )
        count_row = await cursor.fetchone()
        await cursor.close()
        count = count_row["c"]
        if count == 0:
            return {"count": 0, "namespaces": [], "oldest": None, "newest": None}

        cursor = await conn.execute(
            "SELECT DISTINCT namespace FROM memories "
            "WHERE (:namespace IS NULL OR namespace = :namespace) ORDER BY namespace",
            params,
        )
        ns_rows = await cursor.fetchall()
        await cursor.close()
        namespaces = [r["namespace"] for r in ns_rows]

        cursor = await conn.execute(
            "SELECT created_at FROM memories "
            "WHERE (:namespace IS NULL OR namespace = :namespace) "
            "ORDER BY created_at ASC LIMIT 1",
            params,
        )
        oldest_row = await cursor.fetchone()
        await cursor.close()

        cursor = await conn.execute(
            "SELECT updated_at FROM memories "
            "WHERE (:namespace IS NULL OR namespace = :namespace) "
            "ORDER BY updated_at DESC LIMIT 1",
            params,
        )
        newest_row = await cursor.fetchone()
        await cursor.close()

        return {
            "count": count,
            "namespaces": namespaces,
            "oldest": datetime.fromtimestamp(oldest_row["created_at"], tz=UTC).isoformat(),
            "newest": datetime.fromtimestamp(newest_row["updated_at"], tz=UTC).isoformat(),
        }

    async def ping(self) -> bool:
        """Lightweight liveness check for /health — does the connection answer?"""
        try:
            conn = await self._connect()
            await conn.execute("SELECT 1")
            return True
        except Exception:
            return False

    async def aclose(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None


def _build_match_expr(query: str) -> str | None:
    """Construye el `match_expr` de FTS5 de forma defensiva (Decisión 3 del ADR).

    Cada token de la query se escapa (comillas dobles internas duplicadas) y se
    envuelve en comillas dobles — neutraliza cualquier sintaxis especial de FTS5
    (AND/OR/NOT/NEAR, *, :, -) tratándolo como frase literal de un solo token.
    Los tokens se unen con " OR " para maximizar recall.

    Devuelve None si la query no tiene tokens (vacía o solo whitespace) — el
    caller debe devolver [] sin tocar la DB en ese caso.
    """
    tokens = query.split()
    if not tokens:
        return None
    escaped = ['"' + token.replace('"', '""') + '"' for token in tokens]
    return " OR ".join(escaped)


def _to_params(memory: Memory) -> dict[str, Any]:
    return {
        "id": memory.id,
        "content": memory.content,
        "namespace": memory.namespace,
        "tags": json.dumps(memory.tags, ensure_ascii=False),
        "metadata": json.dumps(memory.metadata, ensure_ascii=False),
        "created_at": memory.created_at.timestamp(),
        "updated_at": memory.updated_at.timestamp(),
    }


def _from_row(row: Any, *, score: float | None = None) -> Memory:
    return Memory(
        id=row["id"],
        content=row["content"],
        namespace=row["namespace"],
        tags=json.loads(row["tags"]) if row["tags"] else [],
        metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        created_at=datetime.fromtimestamp(row["created_at"], tz=UTC),
        updated_at=datetime.fromtimestamp(row["updated_at"], tz=UTC),
        score=score,
    )
