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
        try:
            resp = await self._client.post(
                f"{self._base_url}/api/embed",
                json={"model": self._model, "input": text},
            )
            resp.raise_for_status()
        except httpx.ConnectError as exc:
            raise RuntimeError(
                f"Could not connect to Ollama at '{self._base_url}'. "
                f"Ensure Ollama is running ('ollama serve'). If running mcp-memory outside Docker, "
                f"set OLLAMA_URL=http://localhost:11434."
            ) from exc
        except httpx.ConnectTimeout as exc:
            raise RuntimeError(
                f"Connection to Ollama at '{self._base_url}' timed out. "
                f"Verify network connectivity and Ollama responsiveness."
            ) from exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise RuntimeError(
                    f"Model '{self._model}' not found or /api/embed endpoint missing at "
                    f"{self._base_url}. Run 'ollama pull {self._model}' to install the model."
                ) from exc
            if exc.response.status_code == 401:
                raise RuntimeError(
                    f"Ollama returned 401 Unauthorized for {self._base_url}. Note: Ollama Cloud "
                    f"(ollama.com) does not support embeddings. Use a local or self-hosted Ollama."
                ) from exc
            raise RuntimeError(
                f"Ollama returned HTTP {exc.response.status_code}: {exc.response.text}"
            ) from exc
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
