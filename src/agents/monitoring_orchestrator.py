"""
Monitoring Domain Orchestrator — LangGraph v1
Doctrine §88 Tier 1: Monitoring domain — operational safety net.

Tasks:
  - get_system_health_summary  → Supabase SELECT from system_health_summary view
  - get_recent_dispatches      → SELECT from agent_dispatches ORDER BY created_at DESC
  - get_recent_alerts          → SELECT from activities WHERE severity in ('warning','error')
  - get_agent_call_chain       → SELECT chain by parent_dispatch_id (audit trail)
  - run_qc_check               → fire QC Agent v1 via n8n_writer execute_workflow
  - audit_contact_journey      → SELECT contacts WHERE pipeline OR tags drifted
  - check_drift                → compare expected campaign state vs actual
"""
from __future__ import annotations
import os, time
from typing import TypedDict, Optional
import httpx
from urllib.parse import urlencode
from langgraph.graph import StateGraph, START, END

MMA_OS_FUNCTIONS_BASE = os.environ.get("MMA_OS_FUNCTIONS_BASE", "https://slcqeiqcrhepicqxqjng.supabase.co/functions/v1")
MMA_OS_SUPABASE_URL = os.environ.get("MMA_OS_SUPABASE_URL", "https://slcqeiqcrhepicqxqjng.supabase.co")
MMA_OS_BRIDGE_URL = f"{MMA_OS_FUNCTIONS_BASE}/mma-os-bridge"
N8N_WRITER_URL = f"{MMA_OS_FUNCTIONS_BASE}/n8n-writer"
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
MMA_OS_BRIDGE_API_KEY = os.environ.get("MMA_OS_BRIDGE_API_KEY", "")
N8N_WRITER_API_KEY = os.environ.get("N8N_WRITER_API_KEY", "")

QC_AGENT_WORKFLOW_ID = "gM2HiJy9kCcUtCoe"

TASK_REGISTRY = {
    "get_system_health_summary": {"specialist": "supabase_view",  "via": "supabase_select", "table": "system_health_summary"},
    "get_system_health":         {"specialist": "supabase_table", "via": "supabase_select", "table": "system_health"},
    "get_recent_dispatches":     {"specialist": "supabase_table", "via": "supabase_select", "table": "agent_dispatches", "order": "created_at.desc", "limit": 50},
    "get_recent_alerts":         {"specialist": "supabase_table", "via": "supabase_select", "table": "activities"},
    "get_agent_call_chain":      {"specialist": "supabase_table", "via": "supabase_select", "table": "agent_calls"},
    "run_qc_check":              {"specialist": "qc_agent_v1",    "via": "n8n_execute", "workflow_id": QC_AGENT_WORKFLOW_ID},
    "audit_contact_journey":     {"specialist": "supabase_view",  "via": "supabase_select", "table": "contact_journey_audit"},
}

class MonState(TypedDict, total=False):
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

def _supabase_select(table, filters=None, order=None, limit=None):
    if not SUPABASE_SERVICE_ROLE_KEY:
        return {"ok": False, "error": "SUPABASE_SERVICE_ROLE_KEY not set"}
    try:
        with httpx.Client(timeout=10.0) as client:
            params = {}
            if filters:
                for k, v in filters.items():
                    params[k] = f"eq.{v}" if not str(v).startswith(("eq.", "gt.", "lt.", "in.", "like.")) else v
            if order:
                params["order"] = order
            if limit:
                params["limit"] = limit
            qs = urlencode(params)
            r = client.get(f"{MMA_OS_SUPABASE_URL}/rest/v1/{table}?{qs}", headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"})
            return {"ok": r.status_code < 300, "status": r.status_code, "data": r.json() if r.text else [], "row_count": len(r.json()) if r.text and isinstance(r.json(), list) else None}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

def _n8n_writer_post(body, timeout=30.0):
    if not N8N_WRITER_API_KEY:
        return {"ok": False, "error": "N8N_WRITER_API_KEY not set"}
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.post(N8N_WRITER_URL, headers={"Authorization": f"Bearer {N8N_WRITER_API_KEY}", "Content-Type": "application/json"}, json=body)
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
            return {"ok": r.status_code < 300, "row": data[0] if isinstance(data, list) and data else data}
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
    task = (state.get("task") or "").strip()
    if not task:
        return {**state, "error": "no task provided"}
    if task not in TASK_REGISTRY:
        return {**state, "error": f"unknown_task:{task}", "specialist_info": {}}
    spec = TASK_REGISTRY[task]
    log_res = _supabase_insert("agent_calls", {"parent_dispatch_id": state.get("parent_dispatch_id"), "parent_agent": "monitoring_orchestrator", "child_agent": spec["specialist"], "child_tier": 2, "task": task, "input": state.get("payload", {}), "status": "pending"})
    call_id = log_res["row"]["id"] if log_res.get("ok") else None
    return {**state, "specialist_info": spec, "call_id": call_id}

def dispatch_to_specialist(state):
    if state.get("error"):
        return state
    spec = state.get("specialist_info", {})
    task = state.get("task", "")
    payload = state.get("payload", {}) or {}
    via = spec.get("via")
    if via == "supabase_select":
        table = spec["table"]
        # Task-specific filter logic
        filters = {}
        order = spec.get("order")
        limit = spec.get("limit", 100)
        if task == "get_agent_call_chain":
            if payload.get("parent_dispatch_id"):
                filters["parent_dispatch_id"] = payload["parent_dispatch_id"]
            order = "created_at.asc"
        elif task == "get_recent_alerts":
            filters["severity"] = "in.(warning,error)" if not payload.get("severity") else f"eq.{payload['severity']}"
            order = "created_at.desc"
            limit = payload.get("limit", 25)
        elif task == "get_system_health":
            if payload.get("domain"):
                filters["domain"] = payload["domain"]
            if payload.get("status"):
                filters["status"] = payload["status"]
        elif task == "get_recent_dispatches":
            if payload.get("source"):
                filters["source"] = payload["source"]
            if payload.get("status"):
                filters["status"] = payload["status"]
            limit = payload.get("limit", 50)
        # Apply user-provided overrides
        if payload.get("limit"):
            limit = payload["limit"]
        result = _supabase_select(table, filters=filters or None, order=order, limit=limit)
        return {**state, "specialist_result": result}
    if via == "n8n_execute":
        workflow_id = payload.get("workflow_id", spec["workflow_id"])
        result = _n8n_writer_post({"verb": "execute_workflow", "id": workflow_id, "data": payload.get("data", {})})
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
        summary = f"Monitoring ERROR: {state['error']}"
    else:
        result = state.get("specialist_result", {}) or {}
        task = state.get("task", "?")
        if result.get("ok"):
            row_count = result.get("row_count") if "row_count" in result else "n/a"
            summary = f"Monitoring.{task} OK (rows: {row_count})"
        else:
            summary = f"Monitoring.{task} FAILED: {result.get('error', 'unknown')}"
    return {**state, "summary": summary}

def build_graph():
    g = StateGraph(MonState)
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
