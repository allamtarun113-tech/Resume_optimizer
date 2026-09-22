"""Text embeddings (OpenAI text-embedding-3-small) with a cache keyed by model + text."""

import hashlib
import math
from collections.abc import Sequence
from typing import Protocol

import openai

EMBEDDING_DIMENSIONS = 1536
BATCH_SIZE = 256


class Embedder(Protocol):
    model: str

    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class EmbeddingStore(Protocol):
    async def get_cached_embeddings(self, keys: list[str]) -> dict[str, list[float]]: ...

    async def put_cached_embeddings(self, model: str, vectors: dict[str, list[float]]) -> None: ...


def embedding_key(model: str, text: str) -> str:
    return hashlib.sha256(f"{model}\n{' '.join(text.split())}".encode()).hexdigest()


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


class OpenAIEmbedder:
    def __init__(self, api_key: str, model: str, client: openai.AsyncOpenAI | None = None) -> None:
        self.model = model
        self._client = client or openai.AsyncOpenAI(api_key=api_key or None, max_retries=3)

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), BATCH_SIZE):
            batch = list(texts[start : start + BATCH_SIZE])
            response = await self._client.embeddings.create(model=self.model, input=batch)
            vectors.extend(item.embedding for item in sorted(response.data, key=lambda d: d.index))
        return vectors


class CachedEmbedder:
    """Embedder that reuses stored vectors for texts it has seen before."""

    def __init__(self, inner: Embedder, store: EmbeddingStore) -> None:
        self.model = inner.model
        self._inner = inner
        self._store = store

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        keys = [embedding_key(self.model, t) for t in texts]
        cached = await self._store.get_cached_embeddings(sorted(set(keys)))
        missing = [i for i, k in enumerate(keys) if k not in cached]
        if missing:
            fresh = await self._inner.embed([texts[i] for i in missing])
            new = {keys[i]: v for i, v in zip(missing, fresh, strict=True)}
            await self._store.put_cached_embeddings(self.model, new)
            cached.update(new)
        return [cached[k] for k in keys]
