"""
CRM Domain Orchestrator — LangGraph v1
Doctrine §88 Tier 1: CRM domain. Wraps GHL contact operations.
Tasks: get_contact, search_contacts, update_contact, upsert_contact (via bridge),
       add_tag, remove_tag, add_note, get_contact_tags, list_pipelines
Backend: GHL REST API at services.leadconnectorhq.com with GHL_PIT_TOKEN + GHL_LOCATION_ID.
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
GHL_BASE_URL = os.environ.get("GHL_BASE_URL", "https://services.leadconnectorhq.com")
GHL_PIT_TOKEN = os.environ.get("GHL_PIT_TOKEN", "") or os.environ.get("GHL_PIT", "")
GHL_LOCATION_ID = os.environ.get("GHL_LOCATION_ID", "")
GHL_API_VERSION = os.environ.get("GHL_API_VERSION", "2021-07-28")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
MMA_OS_BRIDGE_API_KEY = os.environ.get("MMA_OS_BRIDGE_API_KEY", "")

TASK_REGISTRY = {
    "get_contact":      {"specialist": "ghl_api", "via": "ghl_rest", "method": "GET",    "path_tpl": "/contacts/{contact_id}"},
    "search_contacts":  {"specialist": "ghl_api", "via": "ghl_rest", "method": "GET",    "path_tpl": "/contacts/"},
    "update_contact":   {"specialist": "ghl_api", "via": "ghl_rest", "method": "PUT",    "path_tpl": "/contacts/{contact_id}"},
    "upsert_contact":   {"specialist": "mma_os_bridge", "via": "bridge_verb", "verb": "upsert_contact_mirror"},
    "add_tag":          {"specialist": "ghl_api", "via": "ghl_rest", "method": "POST",   "path_tpl": "/contacts/{contact_id}/tags"},
    "remove_tag":       {"specialist": "ghl_api", "via": "ghl_rest", "method": "DELETE", "path_tpl": "/contacts/{contact_id}/tags"},
    "add_note":         {"specialist": "ghl_api", "via": "ghl_rest", "method": "POST",   "path_tpl": "/contacts/{contact_id}/notes"},
    "get_contact_tags": {"specialist": "ghl_api", "via": "ghl_rest", "method": "GET",    "path_tpl": "/contacts/{contact_id}/tags"},
    "list_pipelines":   {"specialist": "ghl_api", "via": "ghl_rest", "method": "GET",    "path_tpl": "/opportunities/pipelines"},
}

class CRMState(TypedDict, total=False):
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

def _ghl_request(method, path, body=None, query=None, timeout=15.0):
    if not GHL_PIT_TOKEN:
        return {"ok": False, "error": "GHL_PIT_TOKEN not set"}
    try:
        with httpx.Client(timeout=timeout) as client:
            url = f"{GHL_BASE_URL}{path}"
            if query:
                url += "?" + urlencode({k: v for k, v in query.items() if v is not None})
            r = client.request(method, url, headers={"Authorization": f"Bearer {GHL_PIT_TOKEN}", "Version": GHL_API_VERSION, "Accept": "application/json", "Content-Type": "application/json"}, json=body)
            try:
                data = r.json()
            except Exception:
                data = {"raw": r.text[:300]}
            return {"ok": r.status_code < 300, "status": r.status_code, "data": data}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

def _bridge_post(body, timeout=20.0):
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
    log_res = _supabase_insert("agent_calls", {"parent_dispatch_id": state.get("parent_dispatch_id"), "parent_agent": "crm_orchestrator", "child_agent": spec["specialist"], "child_tier": 2, "task": task, "input": state.get("payload", {}), "status": "pending"})
    call_id = log_res["row"]["id"] if log_res.get("ok") else None
    return {**state, "specialist_info": spec, "call_id": call_id}

def dispatch_to_specialist(state):
    if state.get("error"):
        return state
    spec = state.get("specialist_info", {})
    task = state.get("task", "")
    payload = state.get("payload", {}) or {}
    via = spec.get("via")
    if via == "ghl_rest":
        method = spec["method"]
        path_tpl = spec["path_tpl"]
        try:
            path = path_tpl.format(**{k: v for k, v in payload.items() if isinstance(v, (str, int))})
        except KeyError as e:
            return {**state, "specialist_result": {"ok": False, "error": f"missing path param: {e}"}}
        body = None
        query = None
        if task == "search_contacts":
            query = {"locationId": GHL_LOCATION_ID, "query": payload.get("query", ""), "limit": payload.get("limit", 20)}
        elif task == "list_pipelines":
            query = {"locationId": GHL_LOCATION_ID}
        elif task in ("add_tag", "remove_tag"):
            tags_list = payload.get("tags") or ([payload.get("tag")] if payload.get("tag") else [])
            body = {"tags": tags_list}
        elif task == "add_note":
            body = {"body": payload.get("note") or payload.get("body", ""), "userId": payload.get("user_id")}
        elif task == "update_contact":
            body = {k: v for k, v in payload.items() if k != "contact_id"}
        result = _ghl_request(method, path, body=body, query=query)
        return {**state, "specialist_result": result}
    if via == "bridge_verb":
        result = _bridge_post({"verb": spec["verb"], **payload})
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
        summary = f"CRM ERROR: {state['error']}"
    else:
        result = state.get("specialist_result", {}) or {}
        task = state.get("task", "?")
        if result.get("ok"):
            summary = f"CRM.{task} OK"
        else:
            summary = f"CRM.{task} FAILED: {result.get('error') or str(result.get('data', {}))[:100]}"
    return {**state, "summary": summary}

def build_graph():
    g = StateGraph(CRMState)
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
