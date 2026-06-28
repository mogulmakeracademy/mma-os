"""
Revenue Domain Orchestrator — LangGraph v1
Doctrine §88 Tier 1: Revenue domain. Wraps Engine v4.5 + Campaign Control + bridge verbs.

Tasks:
  - fire_campaign         → n8n execute Engine v4.5 (workflow x6AGdX76nQWgpYdx)
  - kill_campaign         → Campaign Control Commands webhook (action=kill)
  - unkill_campaign       → action=unkill
  - pause_campaign        → action=pause
  - unpause_campaign      → action=unpause
  - test_fire_campaign    → set test_recipient + fire (recipient defaults to Antonio per §73)
  - check_campaign_status → read campaign_control row
  - list_due_enrollments  → bridge due_enrollments verb
  - go_live_campaign      → action=go-live

All tasks logged to agent_calls. Per §73, test fires NEVER route to real customers.
"""
from __future__ import annotations
import os, time
from typing import TypedDict, Optional
import httpx
from langgraph.graph import StateGraph, START, END

MMA_OS_FUNCTIONS_BASE = os.environ.get("MMA_OS_FUNCTIONS_BASE", "https://slcqeiqcrhepicqxqjng.supabase.co/functions/v1")
MMA_OS_SUPABASE_URL = os.environ.get("MMA_OS_SUPABASE_URL", "https://slcqeiqcrhepicqxqjng.supabase.co")
MMA_OS_BRIDGE_URL = f"{MMA_OS_FUNCTIONS_BASE}/mma-os-bridge"
N8N_WRITER_URL = f"{MMA_OS_FUNCTIONS_BASE}/n8n-writer"
CAMPAIGN_CONTROL_WEBHOOK = os.environ.get("CAMPAIGN_CONTROL_WEBHOOK_URL", "https://mrmogulmaker.app.n8n.cloud/webhook/campaign-control")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
MMA_OS_BRIDGE_API_KEY = os.environ.get("MMA_OS_BRIDGE_API_KEY", "")
N8N_WRITER_API_KEY = os.environ.get("N8N_WRITER_API_KEY", "")
ANTONIO_TEST_EMAIL = "mrmogulmaker@gmail.com"

ENGINE_WORKFLOW_ID = "x6AGdX76nQWgpYdx"

TASK_REGISTRY = {
    "fire_campaign":        {"specialist": "engine_v4.5", "via": "n8n_execute"},
    "test_fire_campaign":   {"specialist": "engine_v4.5", "via": "test_fire_then_n8n_execute"},
    "kill_campaign":        {"specialist": "campaign_control", "via": "webhook_action", "action": "kill"},
    "unkill_campaign":      {"specialist": "campaign_control", "via": "webhook_action", "action": "unkill"},
    "pause_campaign":       {"specialist": "campaign_control", "via": "webhook_action", "action": "pause"},
    "unpause_campaign":     {"specialist": "campaign_control", "via": "webhook_action", "action": "unpause"},
    "go_live_campaign":     {"specialist": "campaign_control", "via": "webhook_action", "action": "go-live"},
    "check_campaign_status":{"specialist": "campaign_control", "via": "supabase_read"},
    "list_due_enrollments": {"specialist": "mma_os_bridge", "via": "bridge_verb", "verb": "due_enrollments"},
}

class RevenueState(TypedDict, total=False):
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

def _n8n_writer_post(body, timeout=30.0):
    return _post(N8N_WRITER_URL, body, N8N_WRITER_API_KEY, timeout)

def _webhook_post(url, body, timeout=15.0):
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, headers={"Content-Type": "application/json"}, json=body)
            try:
                return {"ok": resp.status_code < 300, "status": resp.status_code, "body": resp.json()}
            except Exception:
                return {"ok": resp.status_code < 300, "status": resp.status_code, "body": resp.text[:300]}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

def _supabase_insert(table, payload):
    if not SUPABASE_SERVICE_ROLE_KEY:
        return {"ok": False, "error": "SUPABASE_SERVICE_ROLE_KEY not set"}
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(f"{MMA_OS_SUPABASE_URL}/rest/v1/{table}", headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}", "Content-Type": "application/json", "Prefer": "return=representation"}, json=payload)
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
            resp = client.patch(f"{MMA_OS_SUPABASE_URL}/rest/v1/{table}?{pk_field}=eq.{pk_value}", headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}", "Content-Type": "application/json", "Prefer": "return=representation"}, json=payload)
            return {"ok": resp.status_code < 300, "status": resp.status_code}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

def _supabase_read(table, filters):
    if not SUPABASE_SERVICE_ROLE_KEY:
        return {"ok": False, "error": "SUPABASE_SERVICE_ROLE_KEY not set"}
    try:
        with httpx.Client(timeout=10.0) as client:
            qs = "&".join([f"{k}=eq.{v}" for k,v in filters.items()])
            resp = client.get(f"{MMA_OS_SUPABASE_URL}/rest/v1/{table}?{qs}", headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"})
            data = resp.json()
            return {"ok": resp.status_code < 300, "rows": data}
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
    log_res = _supabase_insert("agent_calls", {"parent_dispatch_id": state.get("parent_dispatch_id"), "parent_agent": "revenue_orchestrator", "child_agent": spec["specialist"], "child_tier": 2, "task": task, "input": state.get("payload", {}), "status": "pending"})
    call_id = log_res["row"]["id"] if log_res.get("ok") else None
    return {**state, "specialist_info": spec, "call_id": call_id}

def dispatch_to_specialist(state):
    if state.get("error"):
        return state
    spec = state.get("specialist_info", {})
    task = state.get("task", "")
    payload = state.get("payload", {}) or {}
    via = spec.get("via")
    
    if via == "n8n_execute":
        # Fire Engine v4.5 directly via n8n_writer
        workflow_id = payload.get("workflow_id", ENGINE_WORKFLOW_ID)
        result = _n8n_writer_post({"verb": "execute_workflow", "id": workflow_id, "data": payload.get("data", {})})
        return {**state, "specialist_result": result}
    
    if via == "test_fire_then_n8n_execute":
        # §73: route test fires to Antonio only. Set test_recipient_email then fire.
        campaign_key = payload.get("campaign_key", "skool_45day_tier_upgrade")
        recipient = payload.get("test_recipient", ANTONIO_TEST_EMAIL)
        # Set test_recipient via bridge
        set_result = _bridge_post({"verb": "update_campaign_control", "campaign_key": campaign_key, "test_recipient_email": recipient, "paused": True})
        if not set_result.get("ok"):
            return {**state, "specialist_result": {"ok": False, "error": "failed to set test_recipient", "details": set_result}}
        # Fire the workflow
        fire_result = _n8n_writer_post({"verb": "execute_workflow", "id": ENGINE_WORKFLOW_ID, "data": {"test_mode": True}})
        return {**state, "specialist_result": {"ok": fire_result.get("ok", False), "test_recipient_set": set_result, "fire_result": fire_result}}
    
    if via == "webhook_action":
        action = spec.get("action")
        campaign_key = payload.get("campaign_key", "skool_45day_tier_upgrade")
        body = {"action": action, "campaign_key": campaign_key, "reason": payload.get("reason", f"requested via revenue_orchestrator by {state.get('actor', 'unknown')}")}
        result = _webhook_post(CAMPAIGN_CONTROL_WEBHOOK, body)
        return {**state, "specialist_result": result}
    
    if via == "supabase_read":
        campaign_key = payload.get("campaign_key", "skool_45day_tier_upgrade")
        result = _supabase_read("campaign_control", {"campaign_key": campaign_key})
        return {**state, "specialist_result": result}
    
    if via == "bridge_verb":
        verb = spec["verb"]
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
        summary = f"Revenue ERROR: {state['error']}"
    else:
        result = state.get("specialist_result", {}) or {}
        task = state.get("task", "?")
        if result.get("ok"):
            summary = f"Revenue.{task} OK"
        else:
            summary = f"Revenue.{task} FAILED: {result.get('error', 'unknown')}"
    return {**state, "summary": summary}

def build_graph():
    g = StateGraph(RevenueState)
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
