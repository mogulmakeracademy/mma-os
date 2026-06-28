"""
Comms Domain Orchestrator — LangGraph v2
v2 changes:
  - DIRECT Telegram Bot API call (bypass mma-os-bridge which was proxying to Paige with bad creds)
  - TASK_REGISTRY now has aliases — LLM action 'send_telegram_message' aliases to 'send_telegram'
  - Fuzzy task resolution per Doctrine §96 — if no exact/alias match, default to notify_admin
  - Support reply_to_chat_id in payload for two-way Telegram (future-ready)
"""
from __future__ import annotations
import os, time
from typing import TypedDict, Optional
import httpx
from langgraph.graph import StateGraph, START, END

MMA_OS_FUNCTIONS_BASE = os.environ.get("MMA_OS_FUNCTIONS_BASE", "https://slcqeiqcrhepicqxqjng.supabase.co/functions/v1")
MMA_OS_SUPABASE_URL = os.environ.get("MMA_OS_SUPABASE_URL", "https://slcqeiqcrhepicqxqjng.supabase.co")
MMA_OS_BRIDGE_URL = f"{MMA_OS_FUNCTIONS_BASE}/mma-os-bridge"
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "5188669161")  # Antonio's chat ID (from MMA Telegram Bridge)
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
MMA_OS_BRIDGE_API_KEY = os.environ.get("MMA_OS_BRIDGE_API_KEY", "")

# Doctrine §96: task aliases for LLM-flexibility
TASK_REGISTRY = {
    "send_telegram":       {"specialist": "telegram_bot_api",  "via": "direct_telegram", "aliases": ["send_telegram_message", "telegram", "send_tg", "tg_send"]},
    "send_admin_alert":    {"specialist": "telegram_bot_api",  "via": "direct_telegram", "aliases": ["admin_alert", "alert_admin", "notify_admin_telegram"]},
    "notify_admin":        {"specialist": "telegram_bot_api",  "via": "direct_telegram", "aliases": ["notify", "alert", "admin_notify", "send_notification"]},
    "send_email_ghl":      {"specialist": "ghl_email",          "via": "bridge_verb", "verb": "send_ghl_email", "aliases": ["send_email", "email"]},
    "send_sms_ghl":        {"specialist": "ghl_sms",            "via": "bridge_verb", "verb": "send_ghl_sms", "aliases": ["send_sms", "sms"]},
}

def _resolve_task(action_str):
    """Doctrine §96: exact match → alias match → fuzzy substring → default to notify_admin."""
    if not action_str:
        return "notify_admin"
    action = action_str.strip().lower()
    # Exact match
    if action in TASK_REGISTRY:
        return action
    # Alias match
    for task, spec in TASK_REGISTRY.items():
        if action in [a.lower() for a in spec.get("aliases", [])]:
            return task
    # Fuzzy: contains any TASK key as substring
    for task in TASK_REGISTRY:
        if task in action or action in task:
            return task
    # Comms keyword fallback
    if any(k in action for k in ("telegram", "tg", "notify", "alert", "message", "send")):
        return "notify_admin"
    return "notify_admin"  # safest default for comms domain

class CommsState(TypedDict, total=False):
    task: str
    payload: dict
    parent_dispatch_id: Optional[str]
    source: Optional[str]
    actor: Optional[str]
    call_id: str
    call_started_at: float
    specialist_info: dict
    specialist_result: dict
    resolved_task: str
    summary: str
    error: Optional[str]

def _telegram_send(text, chat_id=None, reply_to_message_id=None):
    """Direct Telegram Bot API call. Bypasses bridge for reliability."""
    if not TELEGRAM_BOT_TOKEN:
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN not set in env"}
    target = chat_id or TELEGRAM_CHAT_ID
    if not target:
        return {"ok": False, "error": "no chat_id (TELEGRAM_CHAT_ID env or payload.chat_id)"}
    try:
        body = {"chat_id": target, "text": text, "parse_mode": "Markdown"}
        if reply_to_message_id:
            body["reply_to_message_id"] = reply_to_message_id
        with httpx.Client(timeout=15.0) as client:
            r = client.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json=body)
            try:
                data = r.json()
            except Exception:
                data = {"raw": r.text[:200]}
            return {"ok": data.get("ok", False), "telegram_response": data, "http_status": r.status_code}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

def _bridge_post(body, timeout=15.0):
    if not MMA_OS_BRIDGE_API_KEY:
        return {"ok": False, "error": "MMA_OS_BRIDGE_API_KEY not set"}
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.post(MMA_OS_BRIDGE_URL, headers={"Authorization": f"Bearer {MMA_OS_BRIDGE_API_KEY}", "Content-Type": "application/json"}, json=body)
            try:
                return r.json()
            except Exception:
                return {"ok": False, "error": "non-json response"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

def _supabase_insert(table, payload):
    if not SUPABASE_SERVICE_ROLE_KEY:
        return {"ok": False}
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.post(f"{MMA_OS_SUPABASE_URL}/rest/v1/{table}", headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}", "Content-Type": "application/json", "Prefer": "return=representation"}, json=payload)
            data = r.json()
            return {"ok": r.status_code < 300, "row": data[0] if isinstance(data, list) and data else None}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

def _supabase_patch(table, pk_field, pk_value, payload):
    if not SUPABASE_SERVICE_ROLE_KEY:
        return {"ok": False}
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.patch(f"{MMA_OS_SUPABASE_URL}/rest/v1/{table}?{pk_field}=eq.{pk_value}", headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}", "Content-Type": "application/json"}, json=payload)
            return {"ok": r.status_code < 300}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

def validate_and_log_start(state):
    state = {**state, "error": None, "call_started_at": time.time()}
    raw_task = (state.get("task") or "").strip()
    resolved = _resolve_task(raw_task)
    spec = TASK_REGISTRY[resolved]
    log_res = _supabase_insert("agent_calls", {"parent_dispatch_id": state.get("parent_dispatch_id"), "parent_agent": "comms_orchestrator", "child_agent": spec["specialist"], "child_tier": 2, "task": resolved, "input": {"raw_task": raw_task, "resolved_to": resolved, "payload": state.get("payload", {})}, "status": "pending"})
    call_id = log_res["row"]["id"] if log_res.get("ok") and log_res.get("row") else None
    return {**state, "specialist_info": spec, "call_id": call_id, "resolved_task": resolved}

def dispatch_to_specialist(state):
    if state.get("error"):
        return state
    spec = state.get("specialist_info", {})
    payload = state.get("payload", {}) or {}
    via = spec.get("via")
    
    if via == "direct_telegram":
        # Get message text from payload (LLM puts it here)
        message = payload.get("message") or payload.get("text") or payload.get("body") or "(no message text)"
        chat_id = payload.get("chat_id")  # If LLM specified a different chat, use it
        reply_to = payload.get("reply_to_message_id")
        # Add a category prefix if provided
        category = payload.get("category")
        severity = payload.get("severity", "info")
        prefix_map = {"info": "ℹ️", "warning": "⚠️", "error": "🚨", "success": "✅"}
        prefix = prefix_map.get(severity, "ℹ️")
        if category:
            full_text = f"{prefix} *{category}*\n\n{message}"
        else:
            full_text = f"{prefix} {message}"
        result = _telegram_send(full_text, chat_id=chat_id, reply_to_message_id=reply_to)
        return {**state, "specialist_result": result}
    
    if via == "bridge_verb":
        verb = spec["verb"]
        if verb == "send_ghl_email":
            body = {"verb": verb, "to_email": payload.get("to_email") or payload.get("email"), "subject": payload.get("subject", "MMA OS notification"), "body": payload.get("body") or payload.get("message", ""), "from_name": payload.get("from_name", "Mogul Maker Academy")}
        elif verb == "send_ghl_sms":
            body = {"verb": verb, "to_phone": payload.get("to_phone") or payload.get("phone"), "message": payload.get("message", "")}
        else:
            body = {"verb": verb, **payload}
        result = _bridge_post(body)
        return {**state, "specialist_result": result}
    
    return {**state, "specialist_result": {"ok": False, "error": f"unsupported_via:{via}"}}

def log_call_complete(state):
    call_id = state.get("call_id")
    if not call_id:
        return state
    started = state.get("call_started_at") or time.time()
    duration_ms = int((time.time() - started) * 1000)
    result = state.get("specialist_result", {}) or {}
    status = "success" if result.get("ok") else "error"
    _supabase_patch("agent_calls", "id", call_id, {"output": result, "status": status, "duration_ms": duration_ms})
    return state

def summarize(state):
    if state.get("error"):
        summary = f"Comms ERROR: {state['error']}"
    else:
        result = state.get("specialist_result", {}) or {}
        task = state.get("resolved_task", state.get("task", "?"))
        raw_task = state.get("task", task)
        alias_note = f" (alias from {raw_task})" if raw_task != task else ""
        if result.get("ok"):
            summary = f"Comms v2.{task} OK{alias_note}"
        else:
            err = result.get("error") or str(result.get("telegram_response", {}).get("description", "unknown"))
            summary = f"Comms v2.{task} FAILED: {err[:120]}"
    return {**state, "summary": summary}

def build_graph():
    g = StateGraph(CommsState)
    g.add_node("validate_and_log_start", validate_and_log_start)
    g.add_node("dispatch_to_specialist", dispatch_to_specialist)
    g.add_node("log_call_complete", log_call_complete)
    g.add_node("summarize", summarize)
    g.add_edge(START, "validate_and_log_start")
    g.add_edge("validate_and_log_start", "dispatch_to_specialist")
    g.add_edge("dispatch_to_specialist", "log_call_complete")
    g.add_edge("log_call_complete", "summarize")
    g.add_edge("summarize", END)
    return g.compile()

graph = build_graph()
