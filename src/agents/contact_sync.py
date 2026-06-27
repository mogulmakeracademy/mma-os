"""Contact Sync Agent — v1 (Premium + VIP from GHL).

Pulls contacts tagged 'Tier: Premium' and 'Tier: VIP' from GHL via the MMA OS
bridge (which uses GHL_PIT internally — secrets never leave Supabase), upserts
them into MMA OS contacts table, mirrors them into Paige's clients table via
the Paige Bridge, and pushes an admin notification with the summary.

Idempotent: bulk_mirror_to_paige upserts by email. Safe to run continuously.

Doctrine §66: Claude builds; LangGraph fires.
Doctrine §95: Agent Graph Architecture — first agent in the data-sync tier.
Doctrine §91: Uses both bridges (MMA OS + Paige via the mirror verb).

Trigger: LangGraph Platform cron (recommended every 30 min)
Reads:   GHL contacts (via mma_os_bridge.ghl_search_contacts_by_tag)
Writes:  contacts + tier_state (via mma_os_bridge.bulk_mirror_to_paige)
         paige_clients (via Paige Bridge mirror inside bulk_mirror)
         paige_admin_notifications (via mma_os_bridge.push_admin_notification)
         activities (run record via mma_os_bridge.log_activity)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from src.lib import mma_os_bridge


# ─── Configuration ──────────────────────────────────────────────────

TAGS_TO_SYNC = ["Tier: Premium", "Tier: VIP"]
GHL_PER_TAG_LIMIT = 500

# Tier mapping: which GHL tag maps to which MMA tier value.
TAG_TO_TIER: dict[str, str] = {
    "Tier: Premium": "premium",
    "Tier: VIP": "vip",
    "Tier: Standard": "standard",
    "Tier: Free": "lead",
}


# ─── Agent state ────────────────────────────────────────────────────


class ContactSyncState(TypedDict, total=False):
    dry_run: bool
    tags_to_sync: list[str]
    ghl_pull_result: dict[str, Any]
    contacts_to_mirror: list[dict[str, Any]]
    mirror_result: dict[str, Any]
    summary: dict[str, Any]
    notification_sent: bool
    errors: list[str]


# ─── Nodes ──────────────────────────────────────────────────────────


def pull_from_ghl(state: ContactSyncState) -> ContactSyncState:
    """Search GHL for contacts matching configured tier tags."""
    tags = state.get("tags_to_sync") or TAGS_TO_SYNC
    errors: list[str] = list(state.get("errors", []))
    try:
        result = mma_os_bridge.ghl_search_contacts_by_tag(tags, limit=GHL_PER_TAG_LIMIT)
    except mma_os_bridge.MmaOsBridgeError as exc:
        errors.append(f"ghl_search_contacts_by_tag failed: {exc}")
        return {"ghl_pull_result": {"ok": False, "error": str(exc)}, "errors": errors}
    return {"ghl_pull_result": result, "errors": errors}


def prepare_mirror_payload(state: ContactSyncState) -> ContactSyncState:
    """Shape GHL contacts into bulk_mirror_to_paige input.

    Adds tier (derived from matched tag), source attribution, dedupe by email.
    """
    pull = state.get("ghl_pull_result") or {}
    raw_contacts: list[dict[str, Any]] = pull.get("contacts", []) if isinstance(pull, dict) else []
    seen_emails: set[str] = set()
    prepared: list[dict[str, Any]] = []
    for c in raw_contacts:
        if not isinstance(c, dict):
            continue
        email = (c.get("email") or "").strip().lower()
        if not email or email in seen_emails:
            continue
        if "error" in c:
            continue
        seen_emails.add(email)
        matched_tag = c.get("matched_tag") or ""
        prepared.append({
            "email": email,
            "first_name": c.get("first_name"),
            "last_name": c.get("last_name"),
            "phone": c.get("phone"),
            "ghl_id": c.get("ghl_id"),
            "tier": TAG_TO_TIER.get(matched_tag),
            "matched_tag": matched_tag,
            "source": f"contact_sync_agent:{matched_tag}",
        })
    return {"contacts_to_mirror": prepared}


def mirror_to_paige(state: ContactSyncState) -> ContactSyncState:
    """Bulk upsert into MMA OS + mirror into Paige via the bridge verb."""
    contacts = state.get("contacts_to_mirror", [])
    dry_run = bool(state.get("dry_run", False))
    errors: list[str] = list(state.get("errors", []))
    if not contacts:
        return {"mirror_result": {"processed": 0, "results": [], "note": "no contacts to mirror"}, "errors": errors}
    try:
        result = mma_os_bridge.bulk_mirror_to_paige(contacts, dry_run=dry_run)
    except mma_os_bridge.MmaOsBridgeError as exc:
        errors.append(f"bulk_mirror_to_paige failed: {exc}")
        return {"mirror_result": {"processed": 0, "error": str(exc)}, "errors": errors}
    return {"mirror_result": result, "errors": errors}


def compute_summary(state: ContactSyncState) -> ContactSyncState:
    """Roll up the run into a single summary dict."""
    pull = state.get("ghl_pull_result") or {}
    mirror = state.get("mirror_result") or {}
    contacts = state.get("contacts_to_mirror", [])
    results = mirror.get("results", []) if isinstance(mirror, dict) else []
    mirrored_ok = sum(1 for r in results if isinstance(r, dict) and r.get("paige_mirror") == "ok")
    mirrored_failed = sum(1 for r in results if isinstance(r, dict) and r.get("paige_mirror") == "failed")
    contact_errors = sum(1 for r in results if isinstance(r, dict) and r.get("error"))
    by_tier: dict[str, int] = {}
    for c in contacts:
        t = c.get("tier") or "unknown"
        by_tier[t] = by_tier.get(t, 0) + 1
    summary = {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": bool(state.get("dry_run", False)),
        "tags_searched": state.get("tags_to_sync") or TAGS_TO_SYNC,
        "ghl_contacts_found": len(pull.get("contacts", [])) if isinstance(pull, dict) else 0,
        "unique_contacts_to_mirror": len(contacts),
        "by_tier": by_tier,
        "mirrored_ok": mirrored_ok,
        "mirrored_failed": mirrored_failed,
        "contact_errors": contact_errors,
        "agent_errors": state.get("errors", []),
    }
    return {"summary": summary}


def notify_admin(state: ContactSyncState) -> ContactSyncState:
    """Push a Paige admin notification + log activity. Severity scales with errors."""
    s = state.get("summary") or {}
    errors = state.get("errors", [])
    sent = False
    severity = "info"
    if errors or s.get("mirrored_failed", 0) > 0 or s.get("contact_errors", 0) > 0:
        severity = "warning"
    if errors and s.get("unique_contacts_to_mirror", 0) == 0:
        severity = "urgent"

    title = f"Contact Sync Agent — {s.get('mirrored_ok', 0)} mirrored, {s.get('mirrored_failed', 0)} failed"
    by_tier_str = ", ".join(f"{k}={v}" for k, v in (s.get("by_tier") or {}).items()) or "none"
    body_lines = [
        f"Tags searched: {', '.join(s.get('tags_searched') or [])}",
        f"GHL contacts found: {s.get('ghl_contacts_found', 0)}",
        f"Unique to mirror: {s.get('unique_contacts_to_mirror', 0)}",
        f"By tier: {by_tier_str}",
        f"Mirrored OK: {s.get('mirrored_ok', 0)}",
        f"Mirrored failed: {s.get('mirrored_failed', 0)}",
        f"Contact errors: {s.get('contact_errors', 0)}",
    ]
    if errors:
        body_lines.append("")
        body_lines.append("Agent errors:")
        for e in errors[:5]:
            body_lines.append(f"• {e}")
    body_text = "\n".join(body_lines)

    try:
        mma_os_bridge.push_admin_notification(
            severity=severity,
            title=title,
            body=body_text,
            link_to="/admin/all-leads",
            source_workflow_key="contact_sync_agent",
        )
        sent = True
    except mma_os_bridge.MmaOsBridgeError as exc:
        errors = list(errors) + [f"push_admin_notification failed: {exc}"]

    # Always log the run as an activity for auditability.
    try:
        mma_os_bridge.log_activity(
            type="agent.contact_sync.run",
            source="langgraph",
            data=s,
        )
    except mma_os_bridge.MmaOsBridgeError as exc:
        errors = list(errors) + [f"log_activity failed: {exc}"]

    return {"notification_sent": sent, "errors": errors}


# ─── Graph ──────────────────────────────────────────────────────────


def build_graph() -> Any:
    g = StateGraph(ContactSyncState)
    g.add_node("pull_from_ghl", pull_from_ghl)
    g.add_node("prepare_mirror_payload", prepare_mirror_payload)
    g.add_node("mirror_to_paige", mirror_to_paige)
    g.add_node("compute_summary", compute_summary)
    g.add_node("notify_admin", notify_admin)

    g.set_entry_point("pull_from_ghl")
    g.add_edge("pull_from_ghl", "prepare_mirror_payload")
    g.add_edge("prepare_mirror_payload", "mirror_to_paige")
    g.add_edge("mirror_to_paige", "compute_summary")
    g.add_edge("compute_summary", "notify_admin")
    g.add_edge("notify_admin", END)

    return g.compile()


# LangGraph Platform looks for `graph` in the module.
graph = build_graph()
