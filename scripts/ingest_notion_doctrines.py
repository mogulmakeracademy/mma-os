"""Knowledge ingestion — Notion doctrines § → Supabase knowledge_chunks.

Run once to backfill, then n8n will keep it fresh on a daily cron.

Usage:
    python -m scripts.ingest_notion_doctrines --page-id <notion_page_id>
    python -m scripts.ingest_notion_doctrines --search "MMA OS Doctrine"
"""
from __future__ import annotations

import argparse
import hashlib
import os

import httpx
import tiktoken

from src.lib.knowledge import embed_batch
from src.lib.supabase_client import get_supabase


NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
CHUNK_TOKEN_TARGET = 500


def _notion_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {os.environ['NOTION_API_KEY']}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def fetch_page_blocks(page_id: str) -> list[dict]:
    """Recursively fetch all blocks under a Notion page."""
    blocks: list[dict] = []
    cursor: str | None = None
    while True:
        params = {"page_size": 100}
        if cursor:
            params["start_cursor"] = cursor
        with httpx.Client(headers=_notion_headers(), timeout=30.0) as c:
            res = c.get(f"{NOTION_API}/blocks/{page_id}/children", params=params)
            res.raise_for_status()
            data = res.json()
        blocks.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return blocks


def block_to_text(block: dict) -> str:
    """Render a Notion block as plain text. Handles common types."""
    t = block.get("type", "")
    payload = block.get(t, {})
    rich = payload.get("rich_text", []) or []
    text = "".join(r.get("plain_text", "") for r in rich)
    if t in {"heading_1", "heading_2", "heading_3"}:
        prefix = "#" * int(t[-1])
        return f"\n{prefix} {text}\n"
    if t == "bulleted_list_item":
        return f"- {text}"
    if t == "numbered_list_item":
        return f"1. {text}"
    if t == "to_do":
        check = "[x]" if payload.get("checked") else "[ ]"
        return f"- {check} {text}"
    if t == "code":
        lang = payload.get("language", "")
        return f"\n```{lang}\n{text}\n```\n"
    if t == "quote":
        return f"> {text}"
    return text


def chunk_text(text: str, max_tokens: int = CHUNK_TOKEN_TARGET) -> list[str]:
    enc = tiktoken.get_encoding("cl100k_base")
    tokens = enc.encode(text)
    chunks: list[str] = []
    for i in range(0, len(tokens), max_tokens):
        chunks.append(enc.decode(tokens[i : i + max_tokens]))
    return chunks


def ingest_page(page_id: str, *, title_hint: str | None = None) -> int:
    """Fetch + chunk + embed + upsert one Notion page. Returns chunk count."""
    blocks = fetch_page_blocks(page_id)
    text = "\n".join(block_to_text(b) for b in blocks).strip()
    if not text:
        print(f"  (empty page {page_id})")
        return 0

    # Get page title for source_url + title
    with httpx.Client(headers=_notion_headers(), timeout=30.0) as c:
        res = c.get(f"{NOTION_API}/pages/{page_id}")
        res.raise_for_status()
        page = res.json()
    title = title_hint
    if not title:
        for prop in page.get("properties", {}).values():
            if prop.get("type") == "title":
                title = "".join(t.get("plain_text", "") for t in prop.get("title", []))
                break
    title = title or f"Notion page {page_id[:8]}"
    source_url = page.get("url", f"https://notion.so/{page_id.replace('-', '')}")

    chunks = chunk_text(text)
    embeddings = embed_batch(chunks)

    sb = get_supabase()
    rows = []
    for idx, (chunk, emb) in enumerate(zip(chunks, embeddings, strict=True)):
        content_hash = hashlib.sha256(chunk.encode()).hexdigest()
        rows.append(
            {
                "source_type": "notion",
                "source_id": page_id,
                "source_url": source_url,
                "title": title,
                "content": chunk,
                "chunk_index": idx,
                "token_count": len(chunk),
                "embedding": emb,
                "content_hash": content_hash,
                "metadata": {"notion_page_id": page_id},
            }
        )

    sb.table("knowledge_chunks").upsert(
        rows, on_conflict="source_type,source_id,chunk_index"
    ).execute()
    print(f"  ingested '{title}' → {len(chunks)} chunks")
    return len(chunks)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--page-id", help="Notion page ID to ingest")
    parser.add_argument("--search", help="Search Notion for pages matching this title")
    args = parser.parse_args()

    if args.page_id:
        ingest_page(args.page_id)
    elif args.search:
        with httpx.Client(headers=_notion_headers(), timeout=30.0) as c:
            res = c.post(
                f"{NOTION_API}/search",
                json={"query": args.search, "filter": {"property": "object", "value": "page"}},
            )
            res.raise_for_status()
            for page in res.json().get("results", []):
                ingest_page(page["id"])
    else:
        parser.error("provide --page-id or --search")


if __name__ == "__main__":
    main()
