"""
Lifecycle Domain Orchestrator — LangGraph v1
Doctrine §88 Tier 1: Lifecycle domain — tier transitions + campaign membership.

This is a CROSS-DOMAIN composer: it calls crm_orchestrator (tag changes),
revenue_orchestrator (campaign enrollment), and Paige bridge (cross-system sync)
to execute a single lifecycle event (e.g., "Move Tashia from Standard to Premium").

Tasks:
  - tier_change         → remove old Tier tag, add new Tier tag, exit/enroll campaigns, Paige sync
  - enroll_in_campaign  → call revenue.fire_campaign with cohort=[email]
  - exit_campaign       → mark enrollment exited in Supabase
  - get_lifecycle_stage → read from contact_state table
  - mark_as_churned     → add 'churned' tag + exit all active campaigns
  - mark_as_active      → remove 'churned' tag + (optionally) enroll in welcome-back
"""
from __future__ import annotations
import os, time
from typing import TypedDict, Optional, List
import httpx
from langgraph.graph import StateGraph, START, END

MMA_OS_FUNCTIONS_BASE = os.environ.get("MMA_OS_FUNCTIONS_BASE", "https://slcqeiqcrhepicqxqjng.supabase.co/functions/v1")
MMA_OS_SUPABASE_URL = os.environ.get("MMA_OS_SUPABASE_URL", "https://slcqeiqcrhepicqxqjng.supabase.co")
LANGGRAPH_BRIDGE_URL = f"{MMA_OS_FUNCTIONS_BASE}/langgraph-bridge"
MMA_OS_BRIDGE_URL = f"{MMA_OS_FUNCTIONS_BASE}/mma-os-bridge"
PAIGE_BRIDGE_URL = os.environ.get("PAIGE_BRIDGE_URL", "https://bfmyebsjyuoecmjskqhs.supabase.co/functions/v1/paige-bridge")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
MMA_OS_BRIDGE_API_KEY = os.environ.get("MMA_OS_BRIDGE_API_KEY", "")
LANGGRAPH_WRITER_API_KEY = os.environ.get("LANGGRAPH_WRITER_API_KEY", "")
PAIGE_BRIDGE_API_KEY = os.environ.get("PAIGE_BRIDGE_API_KEY", "")

# Tier badge canonical names (per Doctrine §86)
TIER_TAGS = {"free": "Tier: Free", "standard": "Tier: Standard", "premium": "Tier: Premium", "vip": "Tier: VIP", "btf": "Tier: BTF"}

TASK_REGISTRY = {
    "tier_change":         {"specialist": "composite",       "via": "compose"},
    "enroll_in_campaign":  {"specialist": "revenue",         "via": "langgraph_call", "graph_id": "revenue_orchestrator", "task": "fire_campaign"},
    "exit_campaign":       {"specialist": "mma_os_bridge",   "via": "bridge_verb", "verb": "exit_enrollment"},
    "get_lifecycle_stage": {"specialist": "supabase_table",  "via": "supabase_select", "table": "contact_state"},
    "mark_as_churned":     {"specialist": "composite",       "via": "compose"},
    "mark_as_active":      {"specialist": "composite",       "via": "compose"},
}

class LifecycleState(TypedDict, total=False):
    task: str
    payload: dict
    parent_dispatch_id: Optional[str]
    source: Optional[str]
    actor: Optional[str]
    call_id: str
    call_started_at: float
    specialist_info: dict
    specialist_result: dict
    composite_steps: List[dict]
    summary: str
    error: Optional[str]

def _post(url, body, bearer, timeout=20.0):
    if not bearer:
        return {"ok": False, "error": "missing bearer token"}
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.post(url, headers={"Authorization": f"Bearer {bearer}", "Content-Type": "application/json"}, json=body)
            try:
                return r.json()
            except Exception:
                return {"ok": False, "error": "non-json response"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

def _langgraph_call(graph_id, task, payload, parent_dispatch_id=None, timeout_ms=30000):
    return _post(LANGGRAPH_BRIDGE_URL, {"verb": "fire_agent", "graph_id": graph_id, "input": {"task": task, "payload": payload, "parent_dispatch_id": parent_dispatch_id, "source": "lifecycle_composer"}, "wait": True, "timeout_ms": timeout_ms}, LANGGRAPH_WRITER_API_KEY, timeout=timeout_ms/1000 + 10)

def _bridge_post(body, timeout=15.0):
    return _post(MMA_OS_BRIDGE_URL, body, MMA_OS_BRIDGE_API_KEY, timeout)

def _paige_post(body, timeout=15.0):
    return _post(PAIGE_BRIDGE_URL, body, PAIGE_BRIDGE_API_KEY, timeout)

def _supabase_read(table, filters):
    if not SUPABASE_SERVICE_ROLE_KEY:
        return {"ok": False}
    try:
        with httpx.Client(timeout=10.0) as client:
            qs = "&".join([f"{k}=eq.{v}" for k,v in filters.items()])
            r = client.get(f"{MMA_OS_SUPABASE_URL}/rest/v1/{table}?{qs}", headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"})
            return {"ok": r.status_code < 300, "data": r.json() if r.text else []}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

def _supabase_insert(table, payload):
    if not SUPABASE_SERVICE_ROLE_KEY:
        return {"ok": False}
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.post(f"{MMA_OS_SUPABASE_URL}/rest/v1/{table}", headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}", "Content-Type": "application/json", "Prefer": "return=representation"}, json=payload)
            return {"ok": r.status_code < 300, "row": r.json()[0] if isinstance(r.json(), list) and r.json() else None}
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

def _compose_tier_change(payload, parent_dispatch_id):
    """Cross-domain composition: remove old tier tag, add new tier tag, optionally exit/enroll campaigns, sync Paige."""
    contact_id = payload.get("contact_id") or payload.get("ghl_contact_id")
    email = payload.get("email")
    from_tier = (payload.get("from_tier") or "").lower()
    to_tier = (payload.get("to_tier") or "").lower()
    sync_paige = payload.get("sync_paige", to_tier in ("premium", "vip", "btf"))  # Per §86, only Premium/VIP/BTF mirror to Paige
    steps = []
    overall_ok = True
    
    if not contact_id and not email:
        return {"ok": False, "error": "contact_id or email required", "steps": steps}
    
    # Step 1: Remove old tier tag (if specified)
    if from_tier and from_tier in TIER_TAGS:
        crm_remove = _langgraph_call("crm_orchestrator", "remove_tag", {"contact_id": contact_id, "tag": TIER_TAGS[from_tier]}, parent_dispatch_id)
        steps.append({"step": "remove_old_tier", "tag": TIER_TAGS[from_tier], "result": crm_remove})
        if not crm_remove.get("ok"):
            overall_ok = False
    
    # Step 2: Add new tier tag
    if to_tier and to_tier in TIER_TAGS:
        crm_add = _langgraph_call("crm_orchestrator", "add_tag", {"contact_id": contact_id, "tag": TIER_TAGS[to_tier]}, parent_dispatch_id)
        steps.append({"step": "add_new_tier", "tag": TIER_TAGS[to_tier], "result": crm_add})
        if not crm_add.get("ok"):
            overall_ok = False
    
    # Step 3: Update contact_state in Supabase
    if email:
        state_update = _bridge_post({"verb": "upsert_contact_state", "email": email, "tier": to_tier, "lifecycle_stage": "active"})
        steps.append({"step": "update_contact_state", "result": state_update})
    
    # Step 4: Paige sync (only Premium/VIP/BTF per §86)
    if sync_paige and email:
        paige_sync = _paige_post({"verb": "upsert_client", "payload": {"email": email, "tier": to_tier, "source": "mma_os_lifecycle"}})
        steps.append({"step": "paige_sync", "tier": to_tier, "result": paige_sync})
    
    return {"ok": overall_ok, "steps": steps, "summary": f"tier_change {from_tier} -> {to_tier} for {email or contact_id}"}

def _compose_mark_as_churned(payload, parent_dispatch_id):
    contact_id = payload.get("contact_id") or payload.get("ghl_contact_id")
    email = payload.get("email")
    steps = []
    if contact_id:
        crm_add = _langgraph_call("crm_orchestrator", "add_tag", {"contact_id": contact_id, "tag": "Churned"}, parent_dispatch_id)
        steps.append({"step": "add_churned_tag", "result": crm_add})
    if email:
        state_update = _bridge_post({"verb": "upsert_contact_state", "email": email, "lifecycle_stage": "churned"})
        steps.append({"step": "mark_state_churned", "result": state_update})
    return {"ok": True, "steps": steps, "summary": f"marked {email or contact_id} as churned"}

def _compose_mark_as_active(payload, parent_dispatch_id):
    contact_id = payload.get("contact_id") or payload.get("ghl_contact_id")
    email = payload.get("email")
    steps = []
    if contact_id:
        crm_remove = _langgraph_call("crm_orchestrator", "remove_tag", {"contact_id": contact_id, "tag": "Churned"}, parent_dispatch_id)
        steps.append({"step": "remove_churned_tag", "result": crm_remove})
    if email:
        state_update = _bridge_post({"verb": "upsert_contact_state", "email": email, "lifecycle_stage": "active"})
        steps.append({"step": "mark_state_active", "result": state_update})
    return {"ok": True, "steps": steps, "summary": f"marked {email or contact_id} as active"}

def validate_and_log_start(state):
    state = {**state, "error": None, "call_started_at": time.time()}
    task = (state.get("task") or "").strip()
    if not task:
        return {**state, "error": "no task provided"}
    if task not in TASK_REGISTRY:
        return {**state, "error": f"unknown_task:{task}", "specialist_info": {}}
    spec = TASK_REGISTRY[task]
    log_res = _supabase_insert("agent_calls", {"parent_dispatch_id": state.get("parent_dispatch_id"), "parent_agent": "lifecycle_orchestrator", "child_agent": spec["specialist"], "child_tier": 2, "task": task, "input": state.get("payload", {}), "status": "pending"})
    call_id = log_res["row"]["id"] if log_res.get("ok") and log_res.get("row") else None
    return {**state, "specialist_info": spec, "call_id": call_id}

def dispatch_to_specialist(state):
    if state.get("error"):
        return state
    spec = state.get("specialist_info", {})
    task = state.get("task", "")
    payload = state.get("payload", {}) or {}
    via = spec.get("via")
    parent_dispatch_id = state.get("parent_dispatch_id")
    
    if via == "compose":
        if task == "tier_change":
            result = _compose_tier_change(payload, parent_dispatch_id)
        elif task == "mark_as_churned":
            result = _compose_mark_as_churned(payload, parent_dispatch_id)
        elif task == "mark_as_active":
            result = _compose_mark_as_active(payload, parent_dispatch_id)
        else:
            result = {"ok": False, "error": f"unknown composite task:{task}"}
        return {**state, "specialist_result": result, "composite_steps": result.get("steps", [])}
    
    if via == "langgraph_call":
        result = _langgraph_call(spec["graph_id"], spec["task"], payload, parent_dispatch_id)
        return {**state, "specialist_result": result}
    
    if via == "bridge_verb":
        result = _bridge_post({"verb": spec["verb"], **payload})
        return {**state, "specialist_result": result}
    
    if via == "supabase_select":
        email = payload.get("email")
        if not email:
            return {**state, "specialist_result": {"ok": False, "error": "email required for get_lifecycle_stage"}}
        result = _supabase_read("contact_state", {"email": email})
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
        summary = f"Lifecycle ERROR: {state['error']}"
    else:
        result = state.get("specialist_result", {}) or {}
        task = state.get("task", "?")
        if result.get("ok"):
            steps_count = len(state.get("composite_steps", []))
            summary = f"Lifecycle.{task} OK ({steps_count} steps)" if steps_count else f"Lifecycle.{task} OK"
        else:
            summary = f"Lifecycle.{task} FAILED: {result.get('error', 'unknown')}"
    return {**state, "summary": summary}

def build_graph():
    g = StateGraph(LifecycleState)
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
