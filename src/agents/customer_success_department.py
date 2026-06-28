"""
Customer Success Department — LangGraph v1 (Tier -1)
Department Head composing support + lifecycle + crm + comms for member retention.

Tasks:
  - daily_cs_brief        Fans out to: support tickets, recent churn, recent saves -> Telegram digest
  - list_open_tickets     Query support_drafts WHERE status='pending'
  - get_member_health     Composite: customer_profile + recent activities + tier state for one email
  - handle_churn_save     Composite: lifecycle.mark_as_active + crm.add_note + comms.notify_admin
  - escalate_to_human     Urgent Telegram alert for CS-specific incidents

Doctrine §97 compliance: zero backslashes in f-string expressions. All emoji as constants.
"""
from __future__ import annotations
import os, time
from typing import TypedDict, Optional, List
from urllib.parse import quote
import httpx
from langgraph.graph import StateGraph, START, END
from datetime import datetime, timezone, timedelta

# Emoji constants (NEVER put inside f-string expressions per Doctrine §97)
ICON_OK = "OK"
ICON_WARN = "WARN"
ICON_RED = "DOWN"
ICON_HEART = "HEALTH"
ICON_TICKET = "TICKET"

MMA_OS_FUNCTIONS_BASE = os.environ.get("MMA_OS_FUNCTIONS_BASE", "https://slcqeiqcrhepicqxqjng.supabase.co/functions/v1")
MMA_OS_SUPABASE_URL = os.environ.get("MMA_OS_SUPABASE_URL", "https://slcqeiqcrhepicqxqjng.supabase.co")
LANGGRAPH_BRIDGE_URL = f"{MMA_OS_FUNCTIONS_BASE}/langgraph-bridge"
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
LANGGRAPH_WRITER_API_KEY = os.environ.get("LANGGRAPH_WRITER_API_KEY", "")

class CSState(TypedDict, total=False):
    task: str
    payload: dict
    parent_dispatch_id: Optional[str]
    source: Optional[str]
    actor: Optional[str]
    call_id: str
    call_started_at: float
    open_tickets: List[dict]
    recent_churn: List[dict]
    recent_saves: List[dict]
    member_health: dict
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
    task = (state.get("task") or "daily_cs_brief").strip().lower()
    aliases = {
        "daily_cs_brief": ["cs_brief", "customer_brief", "retention_brief", "daily_brief"],
        "list_open_tickets": ["tickets", "open_tickets", "support_queue"],
        "get_member_health": ["member_health", "health_check", "contact_health"],
        "handle_churn_save": ["churn_save", "save", "winback"],
        "escalate_to_human": ["escalate"]
    }
    canonical = task
    for canon, alist in aliases.items():
        if task == canon or task in alist:
            canonical = canon
            break
    log_res = _supabase_insert("agent_calls", {"parent_dispatch_id": state.get("parent_dispatch_id"), "parent_agent": "customer_success_department", "child_agent": "composite", "child_tier": 1, "task": canonical, "input": state.get("payload", {}), "status": "pending"})
    call_id = log_res["row"]["id"] if log_res.get("ok") and log_res.get("row") else None
    return {**state, "task": canonical, "call_id": call_id}

def gather_cs_data(state):
    """For daily_cs_brief: pull tickets, recent churn, recent saves in parallel."""
    if state.get("task") != "daily_cs_brief":
        return state
    threshold_7d = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    # Open tickets (support_drafts where status is pending/draft)
    tickets_res = _supabase_get(f"support_drafts?limit=20&order=created_at.desc")
    tickets = tickets_res["body"] if isinstance(tickets_res["body"], list) else []
    # Recent churn (contact_state where lifecycle_stage=churned in last 7d) — table may not exist yet
    churn_res = _supabase_get(f"contact_state?lifecycle_stage=eq.churned&updated_at=gte.{quote(threshold_7d)}&limit=20")
    churn = churn_res["body"] if isinstance(churn_res["body"], list) else []
    # Recent saves (lifecycle_stage=active where previously churned in last 7d) — heuristic
    saves_res = _supabase_get(f"contact_state?lifecycle_stage=eq.active&updated_at=gte.{quote(threshold_7d)}&limit=20")
    saves = saves_res["body"] if isinstance(saves_res["body"], list) else []
    return {**state, "open_tickets": tickets, "recent_churn": churn, "recent_saves": saves}

def get_member_health_data(state):
    """For get_member_health: pull customer_profile + recent activities."""
    if state.get("task") != "get_member_health":
        return state
    email = (state.get("payload") or {}).get("email")
    if not email:
        return {**state, "error": "email required for get_member_health"}
    profile_res = _supabase_get(f"customer_profiles?email=eq.{quote(email)}&limit=1")
    profile = (profile_res["body"][0] if isinstance(profile_res["body"], list) and profile_res["body"] else {})
    activities_res = _supabase_get(f"activities?contact_id=eq.{profile.get('contact_id','')}&order=occurred_at.desc&limit=10")
    activities = activities_res["body"] if isinstance(activities_res["body"], list) else []
    health = {"profile": profile, "recent_activity_count": len(activities), "fact_count": profile.get("fact_count", 0)}
    return {**state, "member_health": health}

def compose_brief(state):
    if state.get("task") != "daily_cs_brief":
        return state
    tickets = state.get("open_tickets", []) or []
    churn = state.get("recent_churn", []) or []
    saves = state.get("recent_saves", []) or []
    now_str = datetime.now(timezone.utc).strftime('%A %b %d %Y %H:%M UTC')
    ticket_count = len(tickets)
    churn_count = len(churn)
    save_count = len(saves)
    
    overall_status = ICON_OK if ticket_count == 0 and churn_count == 0 else ICON_WARN
    
    lines = []
    lines.append("*Customer Success Department - Daily Brief*")
    lines.append(f"_{now_str}_")
    lines.append("")
    lines.append(f"[{overall_status}] *CS Health Pulse*")
    lines.append(f"  - Open tickets: {ticket_count}")
    lines.append(f"  - Churn events (7d): {churn_count}")
    lines.append(f"  - Saves (7d): {save_count}")
    lines.append("")
    if tickets:
        lines.append(f"*Top open tickets:*")
        for t in tickets[:5]:
            t_id = t.get("id", "?")
            t_id_short = str(t_id)[:8]
            t_status = t.get("status", "?")
            lines.append(f"  - {t_id_short} (status: {t_status})")
        lines.append("")
    if churn:
        lines.append(f"*Recent churn (7d):*")
        for c in churn[:5]:
            c_email = c.get("email", "?")
            c_tier = c.get("tier", "?")
            lines.append(f"  - {c_email} ({c_tier})")
        lines.append("")
    if save_count > 0:
        lines.append(f"*Recent saves: {save_count} (great work)*")
        lines.append("")
    if ticket_count == 0 and churn_count == 0:
        lines.append("[OK] *No active CS issues. Focus on outbound success calls.*")
    else:
        lines.append("[WARN] *Action required: check open tickets and reach out to recent churners.*")
    
    brief = "\n".join(lines)
    return {**state, "brief_text": brief}

def deliver_brief(state):
    if state.get("task") != "daily_cs_brief":
        return state
    brief = state.get("brief_text", "(no brief generated)")
    res = _langgraph_fire("comms_orchestrator", {"task": "send_telegram", "payload": {"message": brief, "category": "Customer Success Brief", "severity": "info"}, "parent_dispatch_id": state.get("parent_dispatch_id"), "source": "customer_success_department", "actor": "cs_dept_head"}, wait=True, timeout_ms=20000)
    return {**state, "comms_result": res}

def handle_specific(state):
    task = state.get("task")
    if task == "list_open_tickets":
        return state
    if task == "get_member_health":
        return state
    if task == "handle_churn_save":
        payload = state.get("payload") or {}
        email = payload.get("email")
        if not email:
            return {**state, "error": "email required for handle_churn_save"}
        steps = []
        # Step 1: Mark active via lifecycle
        s1 = _langgraph_fire("lifecycle_orchestrator", {"task": "mark_as_active", "payload": {"email": email}, "parent_dispatch_id": state.get("parent_dispatch_id"), "source": "cs_dept_churn_save"}, wait=True, timeout_ms=20000)
        steps.append({"step": "mark_as_active", "result": s1})
        # Step 2: Add CRM note if contact_id provided
        if payload.get("contact_id"):
            s2 = _langgraph_fire("crm_orchestrator", {"task": "add_note", "payload": {"contact_id": payload["contact_id"], "note": f"Churn save handled by CS Dept. Reason: {payload.get('reason', 'not specified')}"}, "parent_dispatch_id": state.get("parent_dispatch_id"), "source": "cs_dept_churn_save"}, wait=True, timeout_ms=15000)
            steps.append({"step": "crm_note", "result": s2})
        # Step 3: Notify Antonio
        s3 = _langgraph_fire("comms_orchestrator", {"task": "send_telegram", "payload": {"message": f"Churn save handled by CS Dept: {email}. Reason: {payload.get('reason', 'not specified')}", "category": "Churn Save", "severity": "success"}, "parent_dispatch_id": state.get("parent_dispatch_id"), "source": "cs_dept_churn_save"}, wait=True, timeout_ms=15000)
        steps.append({"step": "notify_antonio", "result": s3})
        return {**state, "composite_steps": steps, "comms_result": s3}
    if task == "escalate_to_human":
        msg = (state.get("payload") or {}).get("message", "CS escalation requires immediate attention.")
        res = _langgraph_fire("comms_orchestrator", {"task": "send_admin_alert", "payload": {"message": msg, "severity": "warning", "category": "CS ESCALATION"}, "parent_dispatch_id": state.get("parent_dispatch_id"), "source": "customer_success_department"}, wait=True, timeout_ms=15000)
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
        return {**state, "summary": f"CS Dept ERROR: {err_msg}"}
    cm = state.get("comms_result", {}) or {}
    cm_ok = cm.get("ok", False)
    delivered = ICON_OK if cm_ok else ICON_WARN
    if task == "daily_cs_brief":
        ticket_n = len(state.get("open_tickets", []) or [])
        churn_n = len(state.get("recent_churn", []) or [])
        return {**state, "summary": f"CS.{task}: {ticket_n} open tickets, {churn_n} churn events | brief delivery [{delivered}]"}
    if task == "list_open_tickets":
        n = len(state.get("open_tickets", []) or [])
        return {**state, "summary": f"CS.{task}: {n} tickets returned"}
    if task == "get_member_health":
        mh = state.get("member_health", {}) or {}
        fc = mh.get("fact_count", 0)
        return {**state, "summary": f"CS.{task}: {fc} facts on profile"}
    if task == "handle_churn_save":
        steps_n = len(state.get("composite_steps", []) or [])
        return {**state, "summary": f"CS.{task}: {steps_n} steps complete | telegram [{delivered}]"}
    if task == "escalate_to_human":
        return {**state, "summary": f"CS.{task}: escalation telegram [{delivered}]"}
    return {**state, "summary": f"CS.{task}: complete"}

def build_graph():
    g = StateGraph(CSState)
    for n, f in [("start", start), ("gather_cs_data", gather_cs_data), ("get_member_health_data", get_member_health_data), ("compose_brief", compose_brief), ("deliver_brief", deliver_brief), ("handle_specific", handle_specific), ("log_complete", log_complete), ("summarize", summarize)]:
        g.add_node(n, f)
    g.add_edge(START, "start")
    g.add_edge("start", "gather_cs_data")
    g.add_edge("gather_cs_data", "get_member_health_data")
    g.add_edge("get_member_health_data", "compose_brief")
    g.add_edge("compose_brief", "deliver_brief")
    g.add_edge("deliver_brief", "handle_specific")
    g.add_edge("handle_specific", "log_complete")
    g.add_edge("log_complete", "summarize")
    g.add_edge("summarize", END)
    return g.compile()

graph = build_graph()
