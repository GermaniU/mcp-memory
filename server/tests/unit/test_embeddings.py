from __future__ import annotations

import httpx
import pytest

from mcp_memory.shared.embeddings import OllamaEmbeddings

BASE_URL = "http://localhost:11434"


@pytest.mark.asyncio
async def test_embed_success(respx_mock):
    respx_mock.post(f"{BASE_URL}/api/embed").respond(
        json={"embeddings": [[0.1] * 1024]}
    )
    client = OllamaEmbeddings(base_url=BASE_URL, model="bge-m3", expected_dim=1024)

    vector = await client.embed("hello")

    assert vector == [0.1] * 1024


@pytest.mark.asyncio
async def test_embed_dim_mismatch_raises(respx_mock):
    respx_mock.post(f"{BASE_URL}/api/embed").respond(
        json={"embeddings": [[0.1] * 768]}
    )
    client = OllamaEmbeddings(base_url=BASE_URL, model="bge-m3", expected_dim=1024)

    with pytest.raises(RuntimeError, match="dim mismatch"):
        await client.embed("hello")


@pytest.mark.asyncio
async def test_embed_connect_error_raises_actionable_message(respx_mock):
    respx_mock.post(f"{BASE_URL}/api/embed").mock(
        side_effect=httpx.ConnectError("mock connect error")
    )
    client = OllamaEmbeddings(base_url=BASE_URL, model="bge-m3")

    with pytest.raises(RuntimeError, match="Could not connect to Ollama"):
        await client.embed("hello")


@pytest.mark.asyncio
async def test_embed_read_timeout_raises_actionable_message(respx_mock):
    """Regression test: a read timeout (the likely real-world case when Ollama is
    cold-loading a model) must be wrapped like the other httpx failure modes, not
    propagate as a raw httpx.ReadTimeout."""
    respx_mock.post(f"{BASE_URL}/api/embed").mock(
        side_effect=httpx.ReadTimeout("mock read timeout")
    )
    client = OllamaEmbeddings(base_url=BASE_URL, model="bge-m3")

    with pytest.raises(RuntimeError, match="timed out while generating"):
        await client.embed("hello")


@pytest.mark.asyncio
async def test_embed_404_suggests_pull(respx_mock):
    respx_mock.post(f"{BASE_URL}/api/embed").respond(status_code=404)
    client = OllamaEmbeddings(base_url=BASE_URL, model="bge-m3")

    with pytest.raises(RuntimeError, match="ollama pull bge-m3"):
        await client.embed("hello")


@pytest.mark.asyncio
async def test_embed_401_mentions_ollama_cloud(respx_mock):
    respx_mock.post(f"{BASE_URL}/api/embed").respond(status_code=401)
    client = OllamaEmbeddings(base_url=BASE_URL, model="bge-m3")

    with pytest.raises(RuntimeError, match="Ollama Cloud"):
        await client.embed("hello")
