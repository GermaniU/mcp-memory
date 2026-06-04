from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qm
from qdrant_client.http.exceptions import UnexpectedResponse

from mcp_memory.shared.types import Memory

# Payload indexes the store relies on: namespace filtering, recent/oldest ordering.
_PAYLOAD_INDEXES: tuple[tuple[str, qm.PayloadSchemaType], ...] = (
    ("namespace", qm.PayloadSchemaType.KEYWORD),
    ("updated_at", qm.PayloadSchemaType.FLOAT),
    ("created_at", qm.PayloadSchemaType.FLOAT),
)


class QdrantStore:
    """MemoryStore backed by a single Qdrant collection. Namespaces live in payload."""

    def __init__(self, *, url: str, collection: str, dim: int) -> None:
        self._client = AsyncQdrantClient(url=url)
        self._collection = collection
        self._dim = dim

    async def ensure_collection(self) -> None:
        """Create the collection if missing; otherwise validate its vector dim.

        Idempotent: safe to call on every boot. If the collection exists with a
        different vector size, raise — silently writing wrong-dim vectors would
        corrupt search. Payload indexes are (re)asserted in both branches.
        """
        existing = await self._client.get_collections()
        if any(c.name == self._collection for c in existing.collections):
            await self._validate_dim()
        else:
            await self._client.create_collection(
                collection_name=self._collection,
                vectors_config=qm.VectorParams(size=self._dim, distance=qm.Distance.COSINE),
            )
        await self._ensure_indexes()

    async def _validate_dim(self) -> None:
        info = await self._client.get_collection(self._collection)
        vectors = info.config.params.vectors
        # Unnamed default vector → VectorParams; named vectors → dict[str, VectorParams].
        if isinstance(vectors, qm.VectorParams):
            actual = vectors.size
        elif isinstance(vectors, dict) and "" in vectors:
            actual = vectors[""].size
        else:
            # Named-vector collection not created by this store; cannot reconcile.
            raise RuntimeError(
                f"Collection '{self._collection}' uses named vectors and was not "
                f"created by mcp-memory. Use a dedicated collection (QDRANT_COLLECTION)."
            )
        if actual != self._dim:
            raise RuntimeError(
                f"Collection '{self._collection}' has vector size {actual} but "
                f"EMBEDDING_DIM is {self._dim}. They must match. "
                f"Point QDRANT_COLLECTION at a fresh name, or recreate the collection "
                f"with the correct dimension (this will drop existing data)."
            )

    async def _ensure_indexes(self) -> None:
        for field_name, field_schema in _PAYLOAD_INDEXES:
            # Creating an already-existing index is a no-op error — non-fatal on boot.
            with contextlib.suppress(UnexpectedResponse):
                await self._client.create_payload_index(
                    collection_name=self._collection,
                    field_name=field_name,
                    field_schema=field_schema,
                )

    async def save(self, memory: Memory, vector: list[float]) -> Memory:
        await self._client.upsert(
            collection_name=self._collection,
            points=[
                qm.PointStruct(
                    id=memory.id,
                    vector=vector,
                    payload=_to_payload(memory),
                )
            ],
        )
        return memory

    async def update(
        self,
        memory_id: str,
        *,
        content: str | None,
        tags: list[str] | None,
        metadata: dict | None,
        vector: list[float] | None,
    ) -> Memory | None:
        existing = await self._fetch(memory_id)
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
        if vector is not None:
            await self._client.upsert(
                collection_name=self._collection,
                points=[qm.PointStruct(id=updated.id, vector=vector, payload=_to_payload(updated))],
            )
        else:
            await self._client.set_payload(
                collection_name=self._collection,
                payload=_to_payload(updated),
                points=[updated.id],
            )
        return updated

    async def delete(self, memory_id: str) -> bool:
        if await self._fetch(memory_id) is None:
            return False
        await self._client.delete(
            collection_name=self._collection,
            points_selector=qm.PointIdsList(points=[memory_id]),
        )
        return True

    async def search(
        self,
        vector: list[float],
        *,
        namespace: str | None,
        limit: int,
        min_score: float,
    ) -> list[Memory]:
        result = await self._client.query_points(
            collection_name=self._collection,
            query=vector,
            limit=limit,
            score_threshold=min_score or None,
            query_filter=_namespace_filter(namespace),
            with_payload=True,
        )
        return [_from_payload(p.payload, point_id=str(p.id), score=p.score) for p in result.points]

    async def list_(
        self,
        *,
        namespace: str | None,
        limit: int,
        offset: int,
    ) -> list[Memory]:
        points, _ = await self._client.scroll(
            collection_name=self._collection,
            scroll_filter=_namespace_filter(namespace),
            limit=limit + offset,
            with_payload=True,
        )
        sliced = points[offset : offset + limit]
        return [_from_payload(p.payload, point_id=str(p.id)) for p in sliced]

    async def recent(self, *, namespace: str | None, limit: int) -> list[Memory]:
        points, _ = await self._client.scroll(
            collection_name=self._collection,
            scroll_filter=_namespace_filter(namespace),
            order_by=qm.OrderBy(key="updated_at", direction=qm.Direction.DESC),
            limit=limit,
            with_payload=True,
        )
        return [_from_payload(p.payload, point_id=str(p.id)) for p in points]

    async def stats(self, *, namespace: str | None) -> dict[str, Any]:
        ns_filter = _namespace_filter(namespace)
        count = (
            await self._client.count(
                collection_name=self._collection,
                count_filter=ns_filter,
                exact=True,
            )
        ).count
        if count == 0:
            return {"count": 0, "namespaces": [], "oldest": None, "newest": None}

        facet = await self._client.facet(
            collection_name=self._collection,
            key="namespace",
            facet_filter=ns_filter,
            exact=True,
        )
        # Qdrant devuelve hits con count=0 para namespaces cuyos points fueron borrados.
        namespaces = sorted(str(h.value) for h in facet.hits if h.count > 0)

        oldest_points, _ = await self._client.scroll(
            collection_name=self._collection,
            scroll_filter=ns_filter,
            order_by=qm.OrderBy(key="created_at", direction=qm.Direction.ASC),
            limit=1,
            with_payload=True,
        )
        newest_points, _ = await self._client.scroll(
            collection_name=self._collection,
            scroll_filter=ns_filter,
            order_by=qm.OrderBy(key="updated_at", direction=qm.Direction.DESC),
            limit=1,
            with_payload=True,
        )
        oldest = _from_payload(oldest_points[0].payload, point_id=str(oldest_points[0].id))
        newest = _from_payload(newest_points[0].payload, point_id=str(newest_points[0].id))
        return {
            "count": count,
            "namespaces": namespaces,
            "oldest": oldest.created_at.isoformat(),
            "newest": newest.updated_at.isoformat(),
        }

    async def ping(self) -> bool:
        """Lightweight liveness check for /health — does the collection answer?"""
        try:
            await self._client.get_collection(self._collection)
            return True
        except Exception:
            return False

    async def _fetch(self, memory_id: str) -> Memory | None:
        points = await self._client.retrieve(
            collection_name=self._collection,
            ids=[memory_id],
            with_payload=True,
        )
        if not points:
            return None
        return _from_payload(points[0].payload, point_id=str(points[0].id))

    async def aclose(self) -> None:
        await self._client.close()


def _namespace_filter(namespace: str | None) -> qm.Filter | None:
    if namespace is None:
        return None
    return qm.Filter(
        must=[qm.FieldCondition(key="namespace", match=qm.MatchValue(value=namespace))]
    )


def _to_payload(memory: Memory) -> dict[str, Any]:
    return {
        "content": memory.content,
        "namespace": memory.namespace,
        "tags": memory.tags,
        "metadata": memory.metadata,
        "created_at": memory.created_at.timestamp(),
        "updated_at": memory.updated_at.timestamp(),
    }


def _from_payload(
    payload: dict[str, Any] | None, *, point_id: str, score: float | None = None
) -> Memory:
    p = payload or {}
    return Memory(
        id=point_id,
        content=p.get("content", ""),
        namespace=p.get("namespace", ""),
        tags=list(p.get("tags") or []),
        metadata=dict(p.get("metadata") or {}),
        created_at=datetime.fromtimestamp(p.get("created_at", 0), tz=UTC),
        updated_at=datetime.fromtimestamp(p.get("updated_at", 0), tz=UTC),
        score=score,
    )
