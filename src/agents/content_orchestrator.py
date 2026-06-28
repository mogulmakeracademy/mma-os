"""
Content Domain Orchestrator — LangGraph v1
Doctrine §88 Tier 1: Content domain — editorial pipeline.
Tasks: list_editorial_drafts, get_brief_status, mark_brief_ready, fire_brief_now,
       resolve_content_pointer (§64 bridge), list_campaign_content.
Specialists: Notion (via notion-writer), n8n editorial workflows (via n8n-writer), mma-os-bridge.
"""
from __future__ import annotations
import os, time
from typing import TypedDict, Optional
import httpx
from langgraph.graph import StateGraph, START, END

MMA_OS_FUNCTIONS_BASE = os.environ.get("MMA_OS_FUNCTIONS_BASE", "https://slcqeiqcrhepicqxqjng.supabase.co/functions/v1")
MMA_OS_SUPABASE_URL = os.environ.get("MMA_OS_SUPABASE_URL", "https://slcqeiqcrhepicqxqjng.supabase.co")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
MMA_OS_BRIDGE_API_KEY = os.environ.get("MMA_OS_BRIDGE_API_KEY", "")
N8N_WRITER_API_KEY = os.environ.get("N8N_WRITER_API_KEY", "")
NOTION_WRITER_API_KEY = os.environ.get("NOTION_WRITER_API_KEY", "")
EDITORIAL_DB_ID = os.environ.get("EDITORIAL_DB_ID", "")  # Notion DB

TASK_REGISTRY = {
    "list_editorial_drafts":   {"specialist": "notion_writer", "via": "notion_query", "aliases": ["editorial_drafts", "drafts", "list_drafts"]},
    "get_brief_status":        {"specialist": "supabase",      "via": "supabase_read", "table": "editorial_status", "aliases": ["brief_status"]},
    "mark_brief_ready":        {"specialist": "notion_writer", "via": "notion_update", "aliases": ["ready_flip", "mark_ready"]},
    "fire_brief_now":          {"specialist": "n8n_writer",    "via": "n8n_execute", "aliases": ["send_brief", "fire_mogul_brief"]},
    "resolve_content_pointer": {"specialist": "mma_os_bridge", "via": "bridge_verb", "verb": "resolve_content_pointer", "aliases": ["resolve_pointer", "get_content"]},
    "list_campaign_content":   {"specialist": "supabase",      "via": "supabase_read", "table": "campaign_content_registry", "aliases": ["campaign_content"]},
}

def _resolve_task(action_str):
    if not action_str: return "list_editorial_drafts"
    a = action_str.strip().lower()
    if a in TASK_REGISTRY: return a
    for task, spec in TASK_REGISTRY.items():
        if a in [x.lower() for x in spec.get("aliases", [])]: return task
    for task in TASK_REGISTRY:
        if task in a or a in task: return task
    return "list_editorial_drafts"

class ContentState(TypedDict, total=False):
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

def _supabase_read(table, filters=None, limit=50):
    if not SUPABASE_SERVICE_ROLE_KEY: return {"ok": False}
    try:
        with httpx.Client(timeout=10.0) as client:
            qs_parts = []
            if filters:
                for k, v in filters.items(): qs_parts.append(f"{k}=eq.{v}")
            qs_parts.append(f"limit={limit}")
            r = client.get(f"{MMA_OS_SUPABASE_URL}/rest/v1/{table}?" + "&".join(qs_parts), headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"})
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
    log_res = _supabase_insert("agent_calls", {"parent_dispatch_id": state.get("parent_dispatch_id"), "parent_agent": "content_orchestrator", "child_agent": spec["specialist"], "child_tier": 2, "task": resolved, "input": {"raw_task": raw_task, "payload": state.get("payload", {})}, "status": "pending"})
    call_id = log_res["row"]["id"] if log_res.get("ok") and log_res.get("row") else None
    return {**state, "specialist_info": spec, "call_id": call_id, "resolved_task": resolved}

def dispatch_to_specialist(state):
    if state.get("error"): return state
    spec = state.get("specialist_info", {})
    payload = state.get("payload", {}) or {}
    via = spec.get("via")
    if via == "supabase_read":
        table = spec["table"]
        filters = {k: v for k, v in payload.items() if k in ("campaign_key", "status", "active")}
        limit = payload.get("limit", 50)
        return {**state, "specialist_result": _supabase_read(table, filters=filters or None, limit=limit)}
    if via == "bridge_verb":
        return {**state, "specialist_result": _post(f"{MMA_OS_FUNCTIONS_BASE}/mma-os-bridge", {"verb": spec["verb"], **payload}, MMA_OS_BRIDGE_API_KEY)}
    if via == "n8n_execute":
        workflow_id = payload.get("workflow_id")
        if not workflow_id:
            return {**state, "specialist_result": {"ok": False, "error": "workflow_id required in payload for fire_brief_now"}}
        return {**state, "specialist_result": _post(f"{MMA_OS_FUNCTIONS_BASE}/n8n-writer", {"verb": "execute_workflow", "id": workflow_id, "data": payload.get("data", {})}, N8N_WRITER_API_KEY)}
    if via == "notion_query":
        if not EDITORIAL_DB_ID:
            return {**state, "specialist_result": {"ok": False, "error": "EDITORIAL_DB_ID env not set"}}
        db_id = payload.get("database_id", EDITORIAL_DB_ID)
        filt = payload.get("filter") or {"property": "Status", "select": {"equals": payload.get("status", "Draft")}}
        return {**state, "specialist_result": _post(f"{MMA_OS_FUNCTIONS_BASE}/notion-writer", {"verb": "query_database", "database_id": db_id, "filter": filt, "page_size": payload.get("limit", 25)}, NOTION_WRITER_API_KEY)}
    if via == "notion_update":
        page_id = payload.get("page_id")
        if not page_id:
            return {**state, "specialist_result": {"ok": False, "error": "page_id required for mark_brief_ready"}}
        props = payload.get("properties") or {"Status": {"select": {"name": "Ready"}}}
        return {**state, "specialist_result": _post(f"{MMA_OS_FUNCTIONS_BASE}/notion-writer", {"verb": "update_page", "page_id": page_id, "properties": props}, NOTION_WRITER_API_KEY)}
    return {**state, "specialist_result": {"ok": False, "error": f"unsupported_via:{via}"}}

def log_call_complete(state):
    call_id = state.get("call_id")
    if not call_id: return state
    duration_ms = int((time.time() - (state.get("call_started_at") or time.time())) * 1000)
    result = state.get("specialist_result", {}) or {}
    _supabase_patch("agent_calls", "id", call_id, {"output": result, "status": "success" if result.get("ok") else "error", "duration_ms": duration_ms})
    return state

def summarize(state):
    if state.get("error"):
        return {**state, "summary": f"Content ERROR: {state['error']}"}
    result = state.get("specialist_result", {}) or {}
    task = state.get("resolved_task", "?")
    if result.get("ok"):
        rc = result.get("row_count")
        rc_note = f" (rows: {rc})" if rc is not None else ""
        return {**state, "summary": f"Content.{task} OK{rc_note}"}
    return {**state, "summary": f"Content.{task} FAILED: {result.get('error', 'unknown')[:120]}"}

def build_graph():
    g = StateGraph(ContentState)
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
