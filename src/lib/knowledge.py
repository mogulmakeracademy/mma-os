"""Knowledge base helpers — embed query text then search pgvector."""
from __future__ import annotations

import os
from typing import Any

from openai import OpenAI

from .supabase_client import search_knowledge

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMS = 1536


def _openai() -> OpenAI:
    return OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def embed(text: str) -> list[float]:
    """Embed a single text → 1536-dim vector. Truncates inputs over 8192 tokens."""
    res = _openai().embeddings.create(
        model=EMBEDDING_MODEL,
        input=text[:30000],  # rough char limit, well below token limit
    )
    return res.data[0].embedding


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed many texts in one API call (up to 2048 per request)."""
    if not texts:
        return []
    res = _openai().embeddings.create(
        model=EMBEDDING_MODEL,
        input=[t[:30000] for t in texts],
    )
    return [d.embedding for d in res.data]


def ask_knowledge(
    question: str,
    *,
    k: int = 5,
    source_type: str | None = None,
) -> list[dict[str, Any]]:
    """End-to-end: embed question, return top-k chunks with similarity scores."""
    vec = embed(question)
    return search_knowledge(
        vec,
        match_count=k,
        filter_source_type=source_type,
    )
