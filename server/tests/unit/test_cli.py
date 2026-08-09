from __future__ import annotations

import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_memory.cli import main, run_diagnostics


@pytest.mark.asyncio
async def test_run_diagnostics_success_memory_sentinel(monkeypatch):
    """DB_PATH=":memory:" — FTS5 real (confirmado en este entorno, ADR AC19) y
    nada que chequear en disco."""
    monkeypatch.setenv("DB_PATH", ":memory:")

    success = await run_diagnostics()

    assert success is True


@pytest.mark.asyncio
async def test_run_diagnostics_success_fresh_db_path(tmp_path, monkeypatch):
    """`check` crea el directorio padre pero NO el archivo .db — eso lo hace
    ensure_schema() en el arranque real del server, no el diagnóstico."""
    db_path = tmp_path / "nested" / "memory.db"
    monkeypatch.setenv("DB_PATH", str(db_path))

    success = await run_diagnostics()

    assert success is True
    assert db_path.parent.exists()
    assert not db_path.exists()


@pytest.mark.asyncio
async def test_run_diagnostics_reports_existing_row_count(tmp_path, monkeypatch):
    db_path = tmp_path / "memory.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE memories (id TEXT PRIMARY KEY, content TEXT, namespace TEXT, "
        "tags TEXT, metadata TEXT, created_at REAL, updated_at REAL)"
    )
    conn.execute(
        "INSERT INTO memories VALUES ('a', 'x', 'ns', '[]', '{}', 0, 0)"
    )
    conn.commit()
    conn.close()

    monkeypatch.setenv("DB_PATH", str(db_path))

    success = await run_diagnostics()

    assert success is True


@pytest.mark.asyncio
async def test_run_diagnostics_fts5_missing_fails(monkeypatch):
    """Regression test: si el sqlite3 del Python del usuario no trae FTS5
    compilado, `check` debe reportarlo como falla accionable (Decisión 7 del ADR),
    no crashear ni reportar éxito falso."""
    monkeypatch.setenv("DB_PATH", ":memory:")

    mock_conn = MagicMock()
    mock_conn.execute.side_effect = sqlite3.OperationalError("no such module: fts5")

    with patch("mcp_memory.cli.sqlite3.connect", return_value=mock_conn):
        success = await run_diagnostics()

    assert success is False
    mock_conn.close.assert_called_once()


def test_cli_main_check_flag():
    with patch("sys.argv", ["mcp-memory", "check"]), \
         patch("mcp_memory.cli.run_diagnostics", new_callable=AsyncMock) as mock_diag, \
         patch("sys.exit") as mock_exit:
        mock_diag.return_value = True
        main()
        mock_exit.assert_called_once_with(0)
