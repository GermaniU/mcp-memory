from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from mcp_memory.cli import main, run_diagnostics


@pytest.mark.asyncio
async def test_run_diagnostics_success(respx_mock):
    from mcp_memory.shared.config import get_settings
    settings = get_settings()
    base_url = settings.ollama_url.rstrip('/')

    # Mock Ollama HTTP endpoints
    respx_mock.get(f"{base_url}/api/tags").respond(
        json={"models": [{"name": "bge-m3:latest"}]}
    )
    respx_mock.post(f"{base_url}/api/embed").respond(
        json={"embeddings": [[0.1] * 1024]}
    )

    # Mock Qdrant
    with patch("mcp_memory.cli.AsyncQdrantClient") as mock_qdrant_cls:
        mock_client = AsyncMock()
        mock_qdrant_cls.return_value = mock_client
        mock_client.get_collections.return_value = MagicMock(collections=[])

        success = await run_diagnostics()
        assert success is True


@pytest.mark.asyncio
async def test_run_diagnostics_ollama_failure(respx_mock):
    from mcp_memory.shared.config import get_settings
    settings = get_settings()
    base_url = settings.ollama_url.rstrip('/')

    respx_mock.get(f"{base_url}/api/tags").respond(status_code=500)
    respx_mock.post(f"{base_url}/api/embed").respond(status_code=500)

    with patch("mcp_memory.cli.AsyncQdrantClient") as mock_qdrant_cls:
        mock_client = AsyncMock()
        mock_qdrant_cls.return_value = mock_client
        mock_client.get_collections.return_value = MagicMock(collections=[])

        success = await run_diagnostics()
        assert success is False


@pytest.mark.asyncio
async def test_run_diagnostics_tags_failure_embed_ok_still_fails(respx_mock):
    """Regression test: a broken /api/tags must not be masked by a healthy /api/embed —
    'check' exists specifically to catch this kind of partial Ollama failure."""
    from mcp_memory.shared.config import get_settings
    settings = get_settings()
    base_url = settings.ollama_url.rstrip('/')

    respx_mock.get(f"{base_url}/api/tags").respond(status_code=500)
    respx_mock.post(f"{base_url}/api/embed").respond(
        json={"embeddings": [[0.1] * 1024]}
    )

    with patch("mcp_memory.cli.AsyncQdrantClient") as mock_qdrant_cls:
        mock_client = AsyncMock()
        mock_qdrant_cls.return_value = mock_client
        mock_client.get_collections.return_value = MagicMock(collections=[])

        success = await run_diagnostics()
        assert success is False


@pytest.mark.asyncio
async def test_run_diagnostics_does_not_use_qdrant_client_as_context_manager(respx_mock):
    """Regression test: AsyncQdrantClient (qdrant-client>=1.18.0, as pinned in
    pyproject.toml) does not implement __aenter__/__aexit__ — `async with` on it
    raises regardless of Qdrant's real health. Unlike MagicMock/AsyncMock, a plain
    Mock() has no auto-generated magic methods, so it reproduces that TypeError if
    cli.py ever regresses back to using it as a context manager."""
    from mcp_memory.shared.config import get_settings
    settings = get_settings()
    base_url = settings.ollama_url.rstrip('/')

    respx_mock.get(f"{base_url}/api/tags").respond(
        json={"models": [{"name": "bge-m3:latest"}]}
    )
    respx_mock.post(f"{base_url}/api/embed").respond(
        json={"embeddings": [[0.1] * 1024]}
    )

    with patch("mcp_memory.cli.AsyncQdrantClient") as mock_qdrant_cls:
        mock_client = Mock()
        mock_client.get_collections = AsyncMock(return_value=MagicMock(collections=[]))
        mock_client.close = AsyncMock()
        mock_qdrant_cls.return_value = mock_client

        success = await run_diagnostics()

        assert success is True
        mock_client.close.assert_awaited_once()


def test_cli_main_check_flag():
    with patch("sys.argv", ["mcp-memory", "check"]), \
         patch("mcp_memory.cli.run_diagnostics", new_callable=AsyncMock) as mock_diag, \
         patch("sys.exit") as mock_exit:
        mock_diag.return_value = True
        main()
        mock_exit.assert_called_once_with(0)
