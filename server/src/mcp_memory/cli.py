"""cli.py — CLI entry point for mcp-memory.

Supports:
  mcp-memory         -> Launches the FastMCP HTTP server.
  mcp-memory check   -> Runs environment diagnostics (Qdrant, Ollama, model dim, gate).
"""

from __future__ import annotations

import asyncio
import os
import sys

import httpx
from qdrant_client import AsyncQdrantClient

from mcp_memory.server import main as server_main
from mcp_memory.shared.config import get_settings


async def run_diagnostics() -> bool:
    settings = get_settings()
    print("==================================================")
    print(" MCP Memory Diagnostics (mcp-memory check)")
    print("==================================================")
    print("Config:")
    print(f"  · QDRANT_URL:         {settings.qdrant_url}")
    print(f"  · QDRANT_COLLECTION:  {settings.qdrant_collection}")
    print(f"  · OLLAMA_URL:         {settings.ollama_url}")
    print(f"  · EMBEDDING_MODEL:    {settings.embedding_model}")
    print(f"  · EMBEDDING_DIM:      {settings.embedding_dim}")
    print(f"  · MCP_HOST/PORT:      {settings.mcp_host}:{settings.mcp_port}")
    print(f"  · DEFAULT_NAMESPACE:  {settings.default_namespace}")
    print("--------------------------------------------------")

    all_ok = True

    # 1. Qdrant check
    print("\n[1/3] Checking Qdrant connection...")
    try:
        async with AsyncQdrantClient(url=settings.qdrant_url) as qclient:
            collections = await qclient.get_collections()
            names = [c.name for c in collections.collections]
            print(f"  ✓ Qdrant is reachable. Collections found: {names or '(none)'}")

            if settings.qdrant_collection in names:
                info = await qclient.get_collection(settings.qdrant_collection)
                vectors = info.config.params.vectors
                size = (
                    vectors.size
                    if hasattr(vectors, "size")
                    else (
                        vectors.get("").size
                        if isinstance(vectors, dict) and "" in vectors
                        else None
                    )
                )
                if size == settings.embedding_dim:
                    print(
                        f"  ✓ Collection '{settings.qdrant_collection}' exists with "
                        f"dim={size} (matches EMBEDDING_DIM)."
                    )
                else:
                    print(
                        f"  ❌ Collection '{settings.qdrant_collection}' has dim={size}, "
                        f"but EMBEDDING_DIM is {settings.embedding_dim}!"
                    )
                    all_ok = False
            else:
                print(
                    f"  [i] Collection '{settings.qdrant_collection}' does not exist yet; "
                    f"will be auto-created on startup."
                )
    except Exception as exc:
        print(f"  ❌ Failed to connect to Qdrant at '{settings.qdrant_url}': {exc}")
        print("     Tip: If running outside Docker, set QDRANT_URL=http://localhost:6333")
        all_ok = False

    # 2. Ollama check
    print("\n[2/3] Checking Ollama connection & model...")
    try:
        headers = (
            {"Authorization": f"Bearer {settings.ollama_api_key}"}
            if settings.ollama_api_key
            else {}
        )
        async with httpx.AsyncClient(timeout=10.0, headers=headers) as http_client:
            tags_resp = await http_client.get(
                f"{settings.ollama_url.rstrip('/')}/api/tags"
            )
            if tags_resp.status_code == 200:
                models = [
                    m.get("name", "").split(":")[0]
                    for m in tags_resp.json().get("models", [])
                ]
                full_models = [
                    m.get("name", "") for m in tags_resp.json().get("models", [])
                ]
                print(f"  ✓ Ollama is reachable at '{settings.ollama_url}'.")

                target_base = settings.embedding_model.split(":")[0]
                if target_base in models or settings.embedding_model in full_models:
                    print(f"  ✓ Model '{settings.embedding_model}' is pulled.")
                else:
                    print(
                        f"  ⚠️ Model '{settings.embedding_model}' is not listed in Ollama tags."
                    )
                    print(
                        f"     Available models: {', '.join(full_models) or 'none'}"
                    )
                    print(f"     Run: 'ollama pull {settings.embedding_model}'")

            # Embed test
            print(
                f"  Testing embedding generation with model '{settings.embedding_model}'..."
            )
            embed_resp = await http_client.post(
                f"{settings.ollama_url.rstrip('/')}/api/embed",
                json={
                    "model": settings.embedding_model,
                    "input": "mcp-memory check test",
                },
            )
            if embed_resp.status_code == 200:
                embeddings = embed_resp.json().get("embeddings", [])
                if embeddings and len(embeddings[0]) == settings.embedding_dim:
                    dim_len = len(embeddings[0])
                    print(f"  ✓ Embedding test successful! Vector dim: {dim_len}")
                else:
                    dim = len(embeddings[0]) if embeddings else 0
                    print(
                        f"  ❌ Vector dim mismatch! Model returned {dim} dims, "
                        f"but EMBEDDING_DIM is {settings.embedding_dim}."
                    )
                    all_ok = False
            else:
                code = embed_resp.status_code
                txt = embed_resp.text
                print(f"  ❌ Embedding request failed (HTTP {code}): {txt}")
                all_ok = False
    except Exception as exc:
        print(f"  ❌ Ollama check failed: {exc}")
        print(
            "     Tip: Ensure Ollama is running ('ollama serve'). "
            "If running outside Docker, set OLLAMA_URL=http://localhost:11434"
        )
        all_ok = False

    # 3. Faithfulness Gate check
    print("\n[3/3] Checking Faithfulness Gate configuration...")
    judge_provider = os.environ.get("HERMES_JUDGE_PROVIDER", "gemini")
    gate_namespaces = os.environ.get("FAITHFULNESS_GATE_NAMESPACES", "decisions")
    print(f"  · Judge Provider:     {judge_provider}")
    print(f"  · Gated Namespaces:   {gate_namespaces}")

    print("\n--------------------------------------------------")
    if all_ok:
        print(" RESULT: All checks passed! Ready to start mcp-memory. 🚀")
    else:
        print(" RESULT: Diagnostics found issues. Please check the recommendations above.")
    print("==================================================\n")
    return all_ok


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] in ("check", "--check", "-c"):
        success = asyncio.run(run_diagnostics())
        sys.exit(0 if success else 1)
    else:
        server_main()


if __name__ == "__main__":
    main()
