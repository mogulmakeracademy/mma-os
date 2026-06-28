"""
Sales Department — LangGraph v1 (Tier -1)
Department Head composing crm + revenue + comms for new-deal generation.

Tasks:
  - daily_sales_brief    Fans out to: pipeline status, hot leads, recent closes -> Telegram digest
  - list_active_deals    Query deals/opportunities table
  - get_pipeline_health  Velocity, stuck deals, avg deal size
  - handle_new_lead      Composite: crm.upsert_contact + crm.add_tag + comms.notify_admin
  - escalate_hot_lead    Urgent Telegram alert when a high-intent signal fires

Doctrine §97 compliance + Doctrine §98 cost-aware (1 run/day brief design).
"""
from __future__ import annotations
import os, time
from typing import TypedDict, Optional, List
from urllib.parse import quote
import httpx
from langgraph.graph import StateGraph, START, END
from datetime import datetime, timezone, timedelta

ICON_OK = "OK"
ICON_WARN = "WARN"
ICON_HOT = "HOT"
ICON_MONEY = "$$$"

MMA_OS_FUNCTIONS_BASE = os.environ.get("MMA_OS_FUNCTIONS_BASE", "https://slcqeiqcrhepicqxqjng.supabase.co/functions/v1")
MMA_OS_SUPABASE_URL = os.environ.get("MMA_OS_SUPABASE_URL", "https://slcqeiqcrhepicqxqjng.supabase.co")
LANGGRAPH_BRIDGE_URL = f"{MMA_OS_FUNCTIONS_BASE}/langgraph-bridge"
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
LANGGRAPH_WRITER_API_KEY = os.environ.get("LANGGRAPH_WRITER_API_KEY", "")

class SalesState(TypedDict, total=False):
    task: str
    payload: dict
    parent_dispatch_id: Optional[str]
    source: Optional[str]
    actor: Optional[str]
    call_id: str
    call_started_at: float
    active_deals: List[dict]
    hot_leads: List[dict]
    recent_closes: List[dict]
    pipeline_health: dict
    composite_steps: List[dict]
    brief_text: str
    comms_result: dict
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

def _langgraph_fire(graph_id, input_data, wait=True, timeout_ms=30000):
    return _post(LANGGRAPH_BRIDGE_URL, {"verb": "fire_agent", "graph_id": graph_id, "input": input_data, "wait": wait, "timeout_ms": timeout_ms}, LANGGRAPH_WRITER_API_KEY, timeout=timeout_ms/1000 + 10)

def _supabase_get(path):
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(f"{MMA_OS_SUPABASE_URL}/rest/v1/{path}", headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"})
            return {"status": r.status_code, "body": r.json() if r.text else []}
    except Exception as exc:
        return {"status": 0, "body": {"error": str(exc)}}

def _supabase_insert(table, payload):
    if not SUPABASE_SERVICE_ROLE_KEY: return {"ok": False}
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.post(f"{MMA_OS_SUPABASE_URL}/rest/v1/{table}", headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}", "Content-Type": "application/json", "Prefer": "return=representation"}, json=payload)
            d = r.json()
            return {"ok": r.status_code < 300, "row": d[0] if isinstance(d, list) and d else None}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

def _supabase_patch(table, pk_field, pk_value, payload):
    if not SUPABASE_SERVICE_ROLE_KEY: return {"ok": False}
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.patch(f"{MMA_OS_SUPABASE_URL}/rest/v1/{table}?{pk_field}=eq.{pk_value}", headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}", "Content-Type": "application/json"}, json=payload)
            return {"ok": r.status_code < 300}
    except Exception: return {"ok": False}

def start(state):
    state = {**state, "error": None, "call_started_at": time.time()}
    task = (state.get("task") or "daily_sales_brief").strip().lower()
    aliases = {
        "daily_sales_brief": ["sales_brief", "pipeline_brief", "deal_brief"],
        "list_active_deals": ["deals", "active_deals", "opportunities"],
        "get_pipeline_health": ["pipeline_health", "pipeline", "deal_velocity"],
        "handle_new_lead": ["new_lead", "lead", "inbound"],
        "escalate_hot_lead": ["hot_lead", "escalate"]
    }
    canonical = task
    for canon, alist in aliases.items():
        if task == canon or task in alist:
            canonical = canon
            break
    log_res = _supabase_insert("agent_calls", {"parent_dispatch_id": state.get("parent_dispatch_id"), "parent_agent": "sales_department", "child_agent": "composite", "child_tier": 1, "task": canonical, "input": state.get("payload", {}), "status": "pending"})
    call_id = log_res["row"]["id"] if log_res.get("ok") and log_res.get("row") else None
    return {**state, "task": canonical, "call_id": call_id}

def gather_sales_data(state):
    """For daily_sales_brief: pull deals, hot leads, recent closes."""
    if state.get("task") != "daily_sales_brief":
        return state
    threshold_7d = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    # Active deals (contact_state lifecycle_stage in opportunity/active)
    deals_res = _supabase_get(f"contact_state?lifecycle_stage=in.(opportunity,active_deal,negotiating)&limit=20")
    deals = deals_res["body"] if isinstance(deals_res["body"], list) else []
    # Hot leads (engagement_score high, created in 7d)
    hot_res = _supabase_get(f"contact_state?lifecycle_stage=eq.lead&created_at=gte.{quote(threshold_7d)}&limit=20")
    hot = hot_res["body"] if isinstance(hot_res["body"], list) else []
    # Recent closes (enrollments in last 7d)
    closes_res = _supabase_get(f"enrollments?enrolled_at=gte.{quote(threshold_7d)}&limit=20")
    closes = closes_res["body"] if isinstance(closes_res["body"], list) else []
    return {**state, "active_deals": deals, "hot_leads": hot, "recent_closes": closes}

def get_pipeline_data(state):
    """For get_pipeline_health: compute velocity metrics."""
    if state.get("task") != "get_pipeline_health":
        return state
    deals_res = _supabase_get(f"contact_state?lifecycle_stage=in.(opportunity,active_deal,negotiating)&limit=100")
    deals = deals_res["body"] if isinstance(deals_res["body"], list) else []
    threshold_30d = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    stuck_count = sum(1 for d in deals if d.get("updated_at", "") < threshold_30d)
    health = {"total_deals": len(deals), "stuck_30d": stuck_count, "fresh_deals": len(deals) - stuck_count}
    return {**state, "pipeline_health": health, "active_deals": deals}

def compose_brief(state):
    if state.get("task") != "daily_sales_brief":
        return state
    deals = state.get("active_deals", []) or []
    hot = state.get("hot_leads", []) or []
    closes = state.get("recent_closes", []) or []
    now_str = datetime.now(timezone.utc).strftime('%A %b %d %Y %H:%M UTC')
    deal_count = len(deals)
    hot_count = len(hot)
    close_count = len(closes)
    
    overall_status = ICON_OK if close_count > 0 or deal_count > 0 else ICON_WARN
    
    lines = []
    lines.append("*Sales Department - Daily Brief*")
    lines.append(f"_{now_str}_")
    lines.append("")
    lines.append(f"[{overall_status}] *Pipeline Pulse*")
    lines.append(f"  - Active deals: {deal_count}")
    lines.append(f"  - Hot leads (7d): {hot_count}")
    lines.append(f"  - Closes (7d): {close_count}")
    lines.append("")
    if hot:
        lines.append(f"*Top hot leads (call today):*")
        for h in hot[:5]:
            email = h.get("email", "?")
            stage = h.get("lifecycle_stage", "?")
            lines.append(f"  - {email} (stage: {stage})")
        lines.append("")
    if deals:
        lines.append(f"*Active deals:*")
        for d in deals[:5]:
            email = d.get("email", "?")
            tier = d.get("tier", "?")
            lines.append(f"  - {email} ({tier})")
        lines.append("")
    if close_count > 0:
        lines.append(f"[{ICON_MONEY}] *Recent wins: {close_count} new members this week*")
        for c in closes[:3]:
            tier = c.get("tier", "?")
            lines.append(f"  - {tier}")
        lines.append("")
    if deal_count == 0 and hot_count == 0:
        lines.append("[WARN] *Empty pipeline. Time to prospect or run an ad campaign.*")
    else:
        lines.append("[OK] *Action: prioritize hot leads first, then move active deals forward.*")
    
    brief = "\n".join(lines)
    return {**state, "brief_text": brief}

def deliver_brief(state):
    if state.get("task") != "daily_sales_brief":
        return state
    brief = state.get("brief_text", "(no brief generated)")
    res = _langgraph_fire("comms_orchestrator", {"task": "send_telegram", "payload": {"message": brief, "category": "Sales Brief", "severity": "info"}, "parent_dispatch_id": state.get("parent_dispatch_id"), "source": "sales_department", "actor": "sales_dept_head"}, wait=True, timeout_ms=20000)
    return {**state, "comms_result": res}

def handle_specific(state):
    task = state.get("task")
    if task in ("list_active_deals", "get_pipeline_health"):
        return state
    if task == "handle_new_lead":
        payload = state.get("payload") or {}
        email = payload.get("email")
        if not email:
            return {**state, "error": "email required for handle_new_lead"}
        steps = []
        s1 = _langgraph_fire("crm_orchestrator", {"task": "upsert_contact", "payload": {"email": email, "first_name": payload.get("first_name", ""), "last_name": payload.get("last_name", ""), "tags": ["new_lead", "sales_dept_routed"]}, "parent_dispatch_id": state.get("parent_dispatch_id"), "source": "sales_dept_new_lead"}, wait=True, timeout_ms=15000)
        steps.append({"step": "upsert_contact", "result": s1})
        s2 = _langgraph_fire("comms_orchestrator", {"task": "send_telegram", "payload": {"message": f"New lead routed by Sales Dept: {email} (source: {payload.get('source', 'unknown')})", "category": "New Lead", "severity": "info"}, "parent_dispatch_id": state.get("parent_dispatch_id"), "source": "sales_dept_new_lead"}, wait=True, timeout_ms=15000)
        steps.append({"step": "notify_antonio", "result": s2})
        return {**state, "composite_steps": steps, "comms_result": s2}
    if task == "escalate_hot_lead":
        payload = state.get("payload") or {}
        email = payload.get("email", "unknown")
        signal = payload.get("signal", "high engagement detected")
        msg = f"HOT LEAD ALERT: {email} - {signal}. Call within 1hr."
        res = _langgraph_fire("comms_orchestrator", {"task": "send_admin_alert", "payload": {"message": msg, "severity": "warning", "category": "HOT LEAD"}, "parent_dispatch_id": state.get("parent_dispatch_id"), "source": "sales_department"}, wait=True, timeout_ms=15000)
        return {**state, "comms_result": res}
    return state

def log_complete(state):
    call_id = state.get("call_id")
    if not call_id: return state
    duration_ms = int((time.time() - (state.get("call_started_at") or time.time())) * 1000)
    result = {"task": state.get("task"), "comms_ok": (state.get("comms_result", {}) or {}).get("ok")}
    _supabase_patch("agent_calls", "id", call_id, {"output": result, "status": "success", "duration_ms": duration_ms})
    return state

def summarize(state):
    task = state.get("task")
    if state.get("error"):
        err_msg = state["error"]
        return {**state, "summary": f"Sales Dept ERROR: {err_msg}"}
    cm = state.get("comms_result", {}) or {}
    cm_ok = cm.get("ok", False)
    delivered = ICON_OK if cm_ok else ICON_WARN
    if task == "daily_sales_brief":
        d_n = len(state.get("active_deals", []) or [])
        h_n = len(state.get("hot_leads", []) or [])
        c_n = len(state.get("recent_closes", []) or [])
        return {**state, "summary": f"Sales.{task}: {d_n} deals, {h_n} hot leads, {c_n} closes | brief [{delivered}]"}
    if task == "list_active_deals":
        n = len(state.get("active_deals", []) or [])
        return {**state, "summary": f"Sales.{task}: {n} deals returned"}
    if task == "get_pipeline_health":
        ph = state.get("pipeline_health", {}) or {}
        return {**state, "summary": f"Sales.{task}: {ph.get('total_deals', 0)} deals, {ph.get('stuck_30d', 0)} stuck"}
    if task == "handle_new_lead":
        steps_n = len(state.get("composite_steps", []) or [])
        return {**state, "summary": f"Sales.{task}: {steps_n} steps complete | telegram [{delivered}]"}
    if task == "escalate_hot_lead":
        return {**state, "summary": f"Sales.{task}: HOT LEAD telegram [{delivered}]"}
    return {**state, "summary": f"Sales.{task}: complete"}

def build_graph():
    g = StateGraph(SalesState)
    for n, f in [("start", start), ("gather_sales_data", gather_sales_data), ("get_pipeline_data", get_pipeline_data), ("compose_brief", compose_brief), ("deliver_brief", deliver_brief), ("handle_specific", handle_specific), ("log_complete", log_complete), ("summarize", summarize)]:
        g.add_node(n, f)
    g.add_edge(START, "start")
    g.add_edge("start", "gather_sales_data")
    g.add_edge("gather_sales_data", "get_pipeline_data")
    g.add_edge("get_pipeline_data", "compose_brief")
    g.add_edge("compose_brief", "deliver_brief")
    g.add_edge("deliver_brief", "handle_specific")
    g.add_edge("handle_specific", "log_complete")
    g.add_edge("log_complete", "summarize")
    g.add_edge("summarize", END)
    return g.compile()

graph = build_graph()
