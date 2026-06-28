"""
Support Domain Orchestrator — LangGraph v1
Doctrine §88 Tier 1: Support domain — wraps existing Customer Support v1 workflows.
Tasks: triage_ticket (fire CS Triage), draft_response, get_recent_tickets, escalate.
"""
from __future__ import annotations
import os, time
from typing import TypedDict, Optional
import httpx
from langgraph.graph import StateGraph, START, END

MMA_OS_FUNCTIONS_BASE = os.environ.get("MMA_OS_FUNCTIONS_BASE", "https://slcqeiqcrhepicqxqjng.supabase.co/functions/v1")
MMA_OS_SUPABASE_URL = os.environ.get("MMA_OS_SUPABASE_URL", "https://slcqeiqcrhepicqxqjng.supabase.co")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
N8N_WRITER_API_KEY = os.environ.get("N8N_WRITER_API_KEY", "")
MMA_OS_BRIDGE_API_KEY = os.environ.get("MMA_OS_BRIDGE_API_KEY", "")

CS_TRIAGE_WORKFLOW_ID = "XFTPX0uBmC8D8Mb2"
CS_COMMAND_WORKFLOW_ID = "IAM6fmqqU3BhnVOF"

TASK_REGISTRY = {
    "triage_ticket":      {"specialist": "cs_triage_workflow", "via": "n8n_execute", "workflow_id": CS_TRIAGE_WORKFLOW_ID, "aliases": ["triage", "process_ticket", "ticket"]},
    "draft_response":     {"specialist": "cs_command_handler", "via": "n8n_execute", "workflow_id": CS_COMMAND_WORKFLOW_ID, "aliases": ["draft_reply", "respond"]},
    "get_recent_tickets": {"specialist": "supabase",           "via": "supabase_read", "table": "support_drafts", "aliases": ["recent_tickets", "list_tickets"]},
    "escalate_to_human":  {"specialist": "mma_os_bridge",      "via": "bridge_verb", "verb": "push_admin_notification", "aliases": ["escalate", "human"]},
}

def _resolve_task(action):
    if not action: return "triage_ticket"
    a = action.strip().lower()
    if a in TASK_REGISTRY: return a
    for t, s in TASK_REGISTRY.items():
        if a in [x.lower() for x in s.get("aliases", [])]: return t
    for t in TASK_REGISTRY:
        if t in a or a in t: return t
    return "triage_ticket"

class SupportState(TypedDict, total=False):
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

def _post(url, body, bearer, timeout=20.0):
    if not bearer: return {"ok": False, "error": "missing bearer"}
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.post(url, headers={"Authorization": f"Bearer {bearer}", "Content-Type": "application/json"}, json=body)
            try: return r.json()
            except Exception: return {"ok": False, "error": "non-json"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

def _supabase_read(table, limit=20):
    if not SUPABASE_SERVICE_ROLE_KEY: return {"ok": False}
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(f"{MMA_OS_SUPABASE_URL}/rest/v1/{table}?limit={limit}&order=created_at.desc", headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"})
            return {"ok": r.status_code < 300, "data": r.json() if r.text else [], "row_count": len(r.json()) if r.text and isinstance(r.json(), list) else 0}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

def _supabase_insert(table, payload):
    if not SUPABASE_SERVICE_ROLE_KEY: return {"ok": False}
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.post(f"{MMA_OS_SUPABASE_URL}/rest/v1/{table}", headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}", "Content-Type": "application/json", "Prefer": "return=representation"}, json=payload)
            data = r.json()
            return {"ok": r.status_code < 300, "row": data[0] if isinstance(data, list) and data else None}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

def _supabase_patch(table, pk_field, pk_value, payload):
    if not SUPABASE_SERVICE_ROLE_KEY: return {"ok": False}
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
    log_res = _supabase_insert("agent_calls", {"parent_dispatch_id": state.get("parent_dispatch_id"), "parent_agent": "support_orchestrator", "child_agent": spec["specialist"], "child_tier": 2, "task": resolved, "input": {"raw_task": raw_task, "payload": state.get("payload", {})}, "status": "pending"})
    call_id = log_res["row"]["id"] if log_res.get("ok") and log_res.get("row") else None
    return {**state, "specialist_info": spec, "call_id": call_id, "resolved_task": resolved}

def dispatch_to_specialist(state):
    if state.get("error"): return state
    spec = state.get("specialist_info", {})
    payload = state.get("payload", {}) or {}
    via = spec.get("via")
    if via == "n8n_execute":
        wf = spec["workflow_id"]
        return {**state, "specialist_result": _post(f"{MMA_OS_FUNCTIONS_BASE}/n8n-writer", {"verb": "execute_workflow", "id": wf, "data": payload}, N8N_WRITER_API_KEY)}
    if via == "supabase_read":
        return {**state, "specialist_result": _supabase_read(spec["table"], limit=payload.get("limit", 20))}
    if via == "bridge_verb":
        return {**state, "specialist_result": _post(f"{MMA_OS_FUNCTIONS_BASE}/mma-os-bridge", {"verb": spec["verb"], **payload}, MMA_OS_BRIDGE_API_KEY)}
    return {**state, "specialist_result": {"ok": False, "error": f"unsupported_via:{via}"}}

def log_call_complete(state):
    call_id = state.get("call_id")
    if not call_id: return state
    duration_ms = int((time.time() - (state.get("call_started_at") or time.time())) * 1000)
    result = state.get("specialist_result", {}) or {}
    _supabase_patch("agent_calls", "id", call_id, {"output": result, "status": "success" if result.get("ok") else "error", "duration_ms": duration_ms})
    return state

def summarize(state):
    if state.get("error"): return {**state, "summary": f"Support ERROR: {state['error']}"}
    result = state.get("specialist_result", {}) or {}
    task = state.get("resolved_task", "?")
    return {**state, "summary": f"Support.{task} {'OK' if result.get('ok') else 'FAILED: ' + str(result.get('error', 'unknown'))[:100]}"}

def build_graph():
    g = StateGraph(SupportState)
    for n, f in [("validate_and_log_start", validate_and_log_start), ("dispatch_to_specialist", dispatch_to_specialist), ("log_call_complete", log_call_complete), ("summarize", summarize)]:
        g.add_node(n, f)
    g.add_edge(START, "validate_and_log_start")
    g.add_edge("validate_and_log_start", "dispatch_to_specialist")
    g.add_edge("dispatch_to_specialist", "log_call_complete")
    g.add_edge("log_call_complete", "summarize")
    g.add_edge("summarize", END)
    return g.compile()

graph = build_graph()
