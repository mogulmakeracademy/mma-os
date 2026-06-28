"""
Comms Domain Orchestrator — LangGraph v1
Doctrine §88 Tier 1: Comms domain. Receives tasks from Master Orchestrator
(or any caller via langgraph-bridge) and routes to specialists.
"""
from __future__ import annotations
import os, time
from typing import TypedDict, Optional
import httpx
from langgraph.graph import StateGraph, START, END

MMA_OS_BRIDGE_URL = os.environ.get("MMA_OS_BRIDGE_URL", "https://slcqeiqcrhepicqxqjng.supabase.co/functions/v1/mma-os-bridge")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://slcqeiqcrhepicqxqjng.supabase.co")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
MMA_OS_BRIDGE_API_KEY = os.environ.get("MMA_OS_BRIDGE_API_KEY", "")

TASK_REGISTRY = {
    "send_telegram":    {"specialist": "mma_telegram_bridge", "via": "bridge_verb", "verb": "push_admin_notification"},
    "send_admin_alert": {"specialist": "mma_telegram_bridge", "via": "bridge_verb", "verb": "push_admin_notification"},
    "notify_admin":     {"specialist": "mma_telegram_bridge", "via": "bridge_verb", "verb": "push_admin_notification"},
    "send_email_ghl":   {"specialist": "ghl_email",            "via": "bridge_verb", "verb": "send_ghl_email"},
    "send_sms_ghl":     {"specialist": "ghl_sms",              "via": "bridge_verb", "verb": "send_ghl_sms"},
}

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
    summary: str
    error: Optional[str]

def _post(url, body, bearer, timeout=20.0):
    if not bearer:
        return {"ok": False, "error": "missing bearer token"}
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, headers={"Authorization": f"Bearer {bearer}", "Content-Type": "application/json"}, json=body)
            try:
                return resp.json()
            except Exception:
                return {"ok": False, "error": "non-json response"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

def _bridge_post(body, timeout=20.0):
    return _post(MMA_OS_BRIDGE_URL, body, MMA_OS_BRIDGE_API_KEY, timeout)

def _supabase_insert(table, payload):
    if not SUPABASE_SERVICE_ROLE_KEY:
        return {"ok": False, "error": "SUPABASE_SERVICE_ROLE_KEY not set"}
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(f"{SUPABASE_URL}/rest/v1/{table}", headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}", "Content-Type": "application/json", "Prefer": "return=representation"}, json=payload)
            data = resp.json()
            if resp.status_code >= 300:
                return {"ok": False, "status": resp.status_code, "error": data}
            return {"ok": True, "row": data[0] if isinstance(data, list) and data else data}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

def _supabase_patch(table, pk_field, pk_value, payload):
    if not SUPABASE_SERVICE_ROLE_KEY:
        return {"ok": False, "error": "SUPABASE_SERVICE_ROLE_KEY not set"}
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.patch(f"{SUPABASE_URL}/rest/v1/{table}?{pk_field}=eq.{pk_value}", headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}", "Content-Type": "application/json", "Prefer": "return=representation"}, json=payload)
            return {"ok": resp.status_code < 300, "status": resp.status_code}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

def validate_and_log_start(state):
    state = {**state, "error": None, "call_started_at": time.time()}
    task = (state.get("task") or "").strip()
    if not task:
        return {**state, "error": "no task provided"}
    if task not in TASK_REGISTRY:
        return {**state, "error": f"unknown_task:{task}", "specialist_info": {}}
    spec = TASK_REGISTRY[task]
    log_res = _supabase_insert("agent_calls", {"parent_dispatch_id": state.get("parent_dispatch_id"), "parent_agent": "comms_orchestrator", "child_agent": spec["specialist"], "child_tier": 2, "task": task, "input": state.get("payload", {}), "status": "pending"})
    call_id = log_res["row"]["id"] if log_res.get("ok") else None
    return {**state, "specialist_info": spec, "call_id": call_id}

def dispatch_to_specialist(state):
    if state.get("error"):
        return state
    spec = state.get("specialist_info", {})
    payload = state.get("payload", {}) or {}
    if spec.get("via") == "bridge_verb":
        verb = spec["verb"]
        if verb == "push_admin_notification":
            body = {"verb": verb, "category": payload.get("category", "master_orchestrator"), "severity": payload.get("severity", "info"), "message": payload.get("message") or payload.get("text") or "(no message)", "metadata": payload.get("metadata", {"source": state.get("source"), "actor": state.get("actor")})}
        elif verb == "send_ghl_email":
            body = {"verb": verb, "to_email": payload.get("to_email") or payload.get("email"), "subject": payload.get("subject", "MMA OS notification"), "body": payload.get("body") or payload.get("message", ""), "from_name": payload.get("from_name", "Mogul Maker Academy")}
        elif verb == "send_ghl_sms":
            body = {"verb": verb, "to_phone": payload.get("to_phone") or payload.get("phone"), "message": payload.get("message", "")}
        else:
            body = {"verb": verb, **payload}
        result = _bridge_post(body)
        return {**state, "specialist_result": result}
    return {**state, "specialist_result": {"ok": False, "error": f"unsupported_via:{spec.get('via')}"}}

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
        task = state.get("task", "?")
        if result.get("ok"):
            summary = f"Comms.{task} OK"
        else:
            summary = f"Comms.{task} FAILED: {result.get('error', 'unknown')}"
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
