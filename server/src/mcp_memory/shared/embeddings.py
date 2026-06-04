from __future__ import annotations

import httpx


class OllamaEmbeddings:
    """Thin async client for Ollama's /api/embed endpoint.

    Request:  POST /api/embed  {"model": ..., "input": <str>}
    Response: {"embeddings": [[...]]}

    Works for both local Ollama (http://host:11434) and Ollama Cloud
    (https://ollama.com) — the only difference is whether api_key is set.
    Note: Ollama Cloud does NOT serve embedding models; use a local/self-hosted
    Ollama for embeddings.

    If ``expected_dim`` is set, every returned vector is validated against it and
    a RuntimeError is raised on mismatch (catches EMBEDDING_DIM misconfig early).
    """

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout: float = 60.0,
        expected_dim: int | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._expected_dim = expected_dim
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.AsyncClient(timeout=timeout, headers=headers)

    async def embed(self, text: str) -> list[float]:
        resp = await self._client.post(
            f"{self._base_url}/api/embed",
            json={"model": self._model, "input": text},
        )
        resp.raise_for_status()
        data = resp.json()
        embeddings = data.get("embeddings")
        if not embeddings or not embeddings[0]:
            raise RuntimeError(f"Ollama returned no embedding: {data}")
        embedding = embeddings[0]
        if self._expected_dim is not None and len(embedding) != self._expected_dim:
            raise RuntimeError(
                f"Embedding dim mismatch: model '{self._model}' returned "
                f"{len(embedding)} dims but EMBEDDING_DIM is {self._expected_dim}. "
                f"Fix EMBEDDING_DIM to match the model (or pick a model of the "
                f"configured dimension)."
            )
        return embedding

    async def aclose(self) -> None:
        await self._client.aclose()
