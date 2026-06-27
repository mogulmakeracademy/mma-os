"""MMA OS Bridge client — calls the Supabase Edge Function directly.

The MMA OS bridge is a versioned Edge Function on the Mogul Maker Academy
Supabase project (`slcqeiqcrhepicqxqjng`). It exposes ~66 verbs via a single
bearer-authenticated POST endpoint. Bridge code lives in the mma-os-bridge
function; this client is the Python wrapper LangGraph agents use to call it.

Replaces the older `n8n_client.call_bridge` (which routed through an n8n
webhook) for all v13+ verbs. The old path still works for legacy verbs.

Doctrine §66: Claude BUILDS the system; Supabase + n8n + LangGraph FIRE it.
Doctrine §91: Two-way bridge architecture — MMA OS Bridge + Paige Bridge.
"""
from __future__ import annotations

import os
from typing import Any

import httpx


DEFAULT_BRIDGE_URL = "https://slcqeiqcrhepicqxqjng.supabase.co/functions/v1/mma-os-bridge"


class MmaOsBridgeError(RuntimeError):
    """Raised when the bridge returns a non-2xx response or transport fails."""

    def __init__(self, message: str, *, status: int | None = None, body: Any = None) -> None:
        super().__init__(message)
        self.status = status
        self.body = body


def _url() -> str:
    return os.environ.get("MMA_OS_BRIDGE_URL", DEFAULT_BRIDGE_URL).rstrip("/")


def _api_key() -> str:
    key = os.environ.get("MMA_OS_BRIDGE_API_KEY")
    if not key:
        raise MmaOsBridgeError(
            "MMA_OS_BRIDGE_API_KEY env var not set. Configure it in LangGraph Platform secrets."
        )
    return key


def call(verb: str, payload: dict[str, Any] | None = None, *, timeout: float = 60.0) -> Any:
    """POST {verb, payload} to the MMA OS bridge. Returns parsed JSON.

    Raises MmaOsBridgeError on non-2xx, network failure, or invalid JSON.
    """
    body: dict[str, Any] = {"verb": verb}
    if payload is not None:
        body["payload"] = payload
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {_api_key()}",
    }
    try:
        with httpx.Client(timeout=httpx.Timeout(timeout)) as c:
            res = c.post(_url(), json=body, headers=headers)
    except httpx.HTTPError as exc:
        raise MmaOsBridgeError(f"transport failed: {exc}") from exc
    if res.status_code >= 300:
        raise MmaOsBridgeError(
            f"bridge returned {res.status_code} for verb '{verb}'",
            status=res.status_code,
            body=res.text,
        )
    try:
        return res.json()
    except ValueError as exc:
        raise MmaOsBridgeError(f"non-JSON response: {res.text[:200]}") from exc


# ─── Convenience helpers for common verbs ─────────────────────────────


def log_activity(
    *,
    type: str,
    source: str,
    contact_id: str | None = None,
    data: dict[str, Any] | None = None,
) -> Any:
    return call(
        "log_activity",
        {"type": type, "source": source, "contact_id": contact_id, "data": data or {}},
    )


def ghl_search_contacts_by_tag(tags: list[str], *, limit: int = 100) -> Any:
    return call("ghl_search_contacts_by_tag", {"tags": tags, "limit": limit})


def bulk_mirror_to_paige(contacts: list[dict[str, Any]], *, dry_run: bool = False) -> Any:
    return call("bulk_mirror_to_paige", {"contacts": contacts, "dry_run": dry_run})


def push_admin_notification(
    *,
    severity: str,
    title: str,
    body: str,
    link_to: str | None = None,
    source_workflow_key: str | None = None,
) -> Any:
    return call(
        "push_admin_notification",
        {
            "severity": severity,
            "title": title,
            "body": body,
            "link_to": link_to,
            "source_workflow_key": source_workflow_key,
        },
    )


def list_contact_state(*, tier_filter: str | None = None, limit: int = 5000) -> Any:
    payload: dict[str, Any] = {"limit": limit}
    if tier_filter is not None:
        payload["tier_filter"] = tier_filter
    return call("list_contact_state", payload)
