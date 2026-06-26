"""Supabase REST + RPC client wrapper for the MMA OS spine.

Uses the service-role key for full DB access. Never expose to client code.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from supabase import Client, create_client


@lru_cache(maxsize=1)
def get_supabase() -> Client:
    """Return a cached Supabase client. Service role — full access."""
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return create_client(url, key)


# ─── Contacts ─────────────────────────────────────────────────────────


def upsert_contact(
    email: str,
    *,
    first_name: str | None = None,
    last_name: str | None = None,
    tier: str | None = None,
    ghl_contact_id: str | None = None,
    skool_member_id: str | None = None,
    stripe_customer_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Upsert a contact by email. Returns the row."""
    sb = get_supabase()
    payload: dict[str, Any] = {"email": email.lower().strip()}
    if first_name is not None:
        payload["first_name"] = first_name
    if last_name is not None:
        payload["last_name"] = last_name
    if tier is not None:
        payload["tier"] = tier
    if ghl_contact_id is not None:
        payload["ghl_contact_id"] = ghl_contact_id
    if skool_member_id is not None:
        payload["skool_member_id"] = skool_member_id
    if stripe_customer_id is not None:
        payload["stripe_customer_id"] = stripe_customer_id
    if metadata is not None:
        payload["metadata"] = metadata
    res = sb.table("contacts").upsert(payload, on_conflict="email").execute()
    return res.data[0] if res.data else {}


# ─── Activities ───────────────────────────────────────────────────────


def log_activity(
    *,
    contact_id: str | None = None,
    type: str,
    source: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """Append to the master event timeline."""
    sb = get_supabase()
    sb.table("activities").insert(
        {
            "contact_id": contact_id,
            "type": type,
            "source": source,
            "payload": payload or {},
        }
    ).execute()


# ─── Automations registry ────────────────────────────────────────────


def upsert_automation(
    *,
    system: str,
    workflow_id: str,
    name: str,
    description: str | None = None,
    trigger_type: str | None = None,
    enabled: bool = True,
    last_run_at: str | None = None,
    last_status: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Register or update an automation. Idempotent on (system, workflow_id)."""
    sb = get_supabase()
    payload: dict[str, Any] = {
        "system": system,
        "workflow_id": workflow_id,
        "name": name,
        "enabled": enabled,
    }
    if description is not None:
        payload["description"] = description
    if trigger_type is not None:
        payload["trigger_type"] = trigger_type
    if last_run_at is not None:
        payload["last_run_at"] = last_run_at
    if last_status is not None:
        payload["last_status"] = last_status
    if metadata is not None:
        payload["metadata"] = metadata
    res = (
        sb.table("automations")
        .upsert(payload, on_conflict="system,workflow_id")
        .execute()
    )
    return res.data[0] if res.data else {}


def get_automation_health() -> list[dict[str, Any]]:
    """Read the automation_health view — health snapshot of every registered automation."""
    sb = get_supabase()
    res = sb.table("automation_health").select("*").execute()
    return res.data or []


# ─── Knowledge base (pgvector) ───────────────────────────────────────


def search_knowledge(
    query_embedding: list[float],
    *,
    match_count: int = 5,
    filter_source_type: str | None = None,
    filter_metadata: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Cosine-similarity search against knowledge_chunks. Calls match_knowledge() RPC."""
    sb = get_supabase()
    params: dict[str, Any] = {
        "query_embedding": query_embedding,
        "match_count": match_count,
    }
    if filter_source_type is not None:
        params["filter_source_type"] = filter_source_type
    if filter_metadata is not None:
        params["filter_metadata"] = filter_metadata
    res = sb.rpc("match_knowledge", params).execute()
    return res.data or []
