"""
Customer Memory Agent — LangGraph

Autonomous customer memory enrichment. Runs in two modes:

1. On-demand fact capture: pass a name_hint + raw_text, agent extracts facts
   and upserts to customer_profiles via the customer-memory bridge.

2. Scheduled background enrichment: nightly cron sweeps every VIP/Premium contact,
   ensures their rich_notes is populated from their latest GHL data
   (enrichment_data from ghl-webhook-receiver metadata).

Architecture follows Doctrine §79 (LangGraph 5-step ritual) + §81 (subject
disambiguation via GHL) + §82 (Paige mirror on every write).
"""

from __future__ import annotations

import os
import json
from typing import Annotated, TypedDict, Optional, List

import httpx
from langgraph.graph import StateGraph, START, END

# --- Configuration --------------------------------------------------------

MMA_OS_BRIDGE_URL = os.environ.get(
    "MMA_OS_BRIDGE_URL",
    "https://slcqeiqcrhepicqxqjng.supabase.co/functions/v1/mma-os-bridge",
)
CUSTOMER_MEMORY_URL = os.environ.get(
    "CUSTOMER_MEMORY_URL",
    "https://slcqeiqcrhepicqxqjng.supabase.co/functions/v1/customer-memory",
)
MMA_OS_BRIDGE_API_KEY = os.environ.get("MMA_OS_BRIDGE_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5-20251022")


# --- State ----------------------------------------------------------------


class MemoryState(TypedDict, total=False):
    # Input
    mode: str  # "capture" | "enrichment_sweep"
    name_hint: Optional[str]
    email: Optional[str]
    raw_text: Optional[str]
    source: str
    source_meta: dict
    captured_by: str
    # Internal
    identity: dict
    extracted_facts: List[dict]
    structured: dict
    # Output
    capture_result: dict
    enrichment_summary: dict
    error: Optional[str]


# --- HTTP helpers ---------------------------------------------------------


def _bridge_post(url: str, body: dict, timeout: float = 30.0) -> dict:
    """POST to one of our Edge Functions with bridge auth."""
    if not MMA_OS_BRIDGE_API_KEY:
        return {"ok": False, "error": "MMA_OS_BRIDGE_API_KEY not set"}
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(
                url,
                headers={
                    "Authorization": f"Bearer {MMA_OS_BRIDGE_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            try:
                return resp.json()
            except Exception:
                return {"ok": False, "error": f"non-json response: {resp.text[:200]}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _claude_extract_facts(raw_text: str, name_hint: Optional[str] = None) -> List[dict]:
    """Use Claude to extract structured facts from raw text. Falls back to a
    single-fact wrapper if Anthropic isn't configured."""
    if not ANTHROPIC_API_KEY or not raw_text:
        # Fallback: store the raw_text as a single generic fact
        return [
            {
                "fact_text": raw_text[:500],
                "category": "raw",
            }
        ]

    system_prompt = (
        "You extract structured personal facts about people from free-form text. "
        "Return ONLY a JSON object: { \"facts\": [{ \"fact_text\": str, \"category\": str }] } "
        "where category is one of: family, business, employment, location, personal, "
        "health, communication, goal, milestone, preference, general. "
        "Each fact_text should be a complete sentence written in third person about the subject. "
        "Skip anything that's not a personal/contextual fact (e.g., transactional 'I want a refund' is NOT a fact). "
        "Be liberal with extraction — capture every meaningful detail."
    )
    user_msg = f"Subject: {name_hint or 'unknown'}\n\nText to extract from:\n{raw_text}"

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": ANTHROPIC_MODEL,
                    "max_tokens": 1500,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_msg}],
                },
            )
            data = resp.json()
            content_blocks = data.get("content", [])
            text = "".join(b.get("text", "") for b in content_blocks if b.get("type") == "text")
            # Strip code fences if present
            text = text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[-1]
            if text.endswith("```"):
                text = text.rsplit("```", 1)[0]
            parsed = json.loads(text)
            return parsed.get("facts", [])
    except Exception as exc:
        # On parse failure, fall back to single fact
        return [
            {
                "fact_text": raw_text[:500],
                "category": "raw",
                "extraction_error": str(exc),
            }
        ]


# --- Graph nodes ----------------------------------------------------------


def resolve_identity(state: MemoryState) -> MemoryState:
    """Doctrine §81 — confirm subject identity via GHL search before any write."""
    if state.get("email"):
        # Already have an email — skip lookup, trust it
        return {**state, "identity": {"match_status": "confirmed", "suggested_email": state["email"]}}

    name_hint = state.get("name_hint", "").strip()
    if not name_hint:
        return {**state, "error": "no email or name_hint provided", "identity": {"match_status": "no_input"}}

    result = _bridge_post(
        CUSTOMER_MEMORY_URL,
        {"verb": "resolve_identity", "name_hint": name_hint},
    )

    if not result.get("ok"):
        return {**state, "error": f"resolve_identity failed: {result.get('error')}", "identity": result}

    return {**state, "identity": result}


def extract_facts(state: MemoryState) -> MemoryState:
    """Use Claude to pull structured facts out of raw_text."""
    if state.get("error"):
        return state

    raw_text = state.get("raw_text", "")
    if not raw_text:
        return {**state, "extracted_facts": []}

    facts = _claude_extract_facts(raw_text, state.get("name_hint"))
    return {**state, "extracted_facts": facts}


def capture_to_bridge(state: MemoryState) -> MemoryState:
    """Push the extracted facts into customer_profiles via the bridge."""
    if state.get("error"):
        return state

    identity = state.get("identity", {})
    if identity.get("match_status") not in ("confirmed", "multiple_matches"):
        return {
            **state,
            "capture_result": {"ok": False, "error": "identity not confirmed; skipping write"},
        }

    body = {
        "verb": "capture",
        "facts": state.get("extracted_facts", []),
        "source": state.get("source", "langgraph_customer_memory"),
        "source_meta": state.get("source_meta", {}),
        "raw_excerpt": (state.get("raw_text") or "")[:500],
        "captured_by": state.get("captured_by", "customer_memory_agent"),
        "structured": state.get("structured", {}),
    }
    if state.get("email"):
        body["email"] = state["email"]
    elif identity.get("suggested_email"):
        body["email"] = identity["suggested_email"]
    else:
        body["name_hint"] = state.get("name_hint")

    result = _bridge_post(CUSTOMER_MEMORY_URL, body)
    return {**state, "capture_result": result}


def notify_admin(state: MemoryState) -> MemoryState:
    """Telegram digest via mma-os-bridge push_admin_notification."""
    capture = state.get("capture_result", {})
    if not capture.get("ok"):
        msg = f"🧠 Customer Memory: capture FAILED — {capture.get('error', 'unknown')}"
    else:
        profile = capture.get("profile", {})
        facts_added = capture.get("facts_added", 0)
        facts_total = capture.get("facts_total", 0)
        msg = (
            f"🧠 Customer Memory updated\n"
            f"• {profile.get('full_name', profile.get('email', 'unknown'))}\n"
            f"• +{facts_added} facts (total: {facts_total})\n"
            f"• action: {capture.get('action', 'updated')}\n"
            f"• Paige mirror: {'✅' if capture.get('paige_mirror', {}).get('ok') else '⚠️'}"
        )

    _bridge_post(
        MMA_OS_BRIDGE_URL,
        {
            "verb": "push_admin_notification",
            "category": "customer_memory",
            "severity": "info",
            "message": msg,
            "metadata": {"capture_result": capture},
        },
    )
    return {**state, "enrichment_summary": {"message_sent": msg, "ok": capture.get("ok", False)}}


# --- Graph wiring ---------------------------------------------------------


def build_graph() -> StateGraph:
    g = StateGraph(MemoryState)
    g.add_node("resolve_identity", resolve_identity)
    g.add_node("extract_facts", extract_facts)
    g.add_node("capture_to_bridge", capture_to_bridge)
    g.add_node("notify_admin", notify_admin)

    g.add_edge(START, "resolve_identity")
    g.add_edge("resolve_identity", "extract_facts")
    g.add_edge("extract_facts", "capture_to_bridge")
    g.add_edge("capture_to_bridge", "notify_admin")
    g.add_edge("notify_admin", END)
    return g.compile()


# Required export for langgraph.json
graph = build_graph()
