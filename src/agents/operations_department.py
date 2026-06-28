"""
Operations Department â LangGraph v1 (Tier -1)
The first Department Head agent. Composes multiple DX agents + monitoring orchestrator
into business-level outputs: morning briefs, system audits, incident reports.

Tasks:
  - morning_brief         â Fires all 7 DX agents in parallel + composes consolidated digest + delivers via comms to Telegram. Default scheduled 7am ET.
  - run_full_audit        â Comprehensive: every DX + agent_dispatches stats + Engine v4.5 last fire + Telegram digest
  - get_uptime_stats      â Query system_health for healthy/total ratio + by-domain breakdown
  - list_active_incidents â system_health WHERE status != healthy (escalation candidates)
  - escalate_to_human     â urgent push via comms_orchestrator with HIGH severity
"""
from __future__ import annotations
import os, time, json
from typing import TypedDict, Optional, List
import httpx
from urllib.parse import quote
from langgraph.graph import StateGraph, START, END
from datetime import datetime, timezone, timedelta

MMA_OS_FUNCTIONS_BASE = os.environ.get("MMA_OS_FUNCTIONS_BASE", "https://slcqeiqcrhepicqxqjng.supabase.co/functions/v1")
MMA_OS_SUPABASE_URL = os.environ.get("MMA_OS_SUPABASE_URL", "https://slcqeiqcrhepicqxqjng.supabase.co")
LANGGRAPH_BRIDGE_URL = f"{MMA_OS_FUNCTIONS_BASE}/langgraph-bridge"
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
LANGGRAPH_WRITER_API_KEY = os.environ.get("LANGGRAPH_WRITER_API_KEY", "")

DX_AGENTS = ["comms_dx", "crm_dx", "revenue_dx", "lifecycle_dx", "content_dx", "support_dx", "monitoring_dx"]

class OpsState(TypedDict, total=False):
    task: str
    payload: dict
    parent_dispatch_id: Optional[str]
    source: Optional[str]
    actor: Optional[str]
    call_id: str
    call_started_at: float
    dx_results: List[dict]
    health_summary: dict
    recent_alerts: List[dict]
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

def _langgraph_fire(graph_id, input_data, wait=True, timeout_ms=40000):
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

def _log_start(state, task):
    return _supabase_insert("agent_calls", {"parent_dispatch_id": state.get("parent_dispatch_id"), "parent_agent": "operations_department", "child_agent": "composite", "child_tier": 1, "task": task, "input": state.get("payload", {}), "status": "pending"})

# === Graph nodes ===

def start(state):
    state = {**state, "error": None, "call_started_at": time.time()}
    task = (state.get("task") or "morning_brief").strip().lower()
    # Aliases
    aliases = {"morning_brief": ["brief", "morning", "morning_briefing", "daily_brief", "ops_brief"], "run_full_audit": ["audit", "full_audit"], "get_uptime_stats": ["uptime"], "list_active_incidents": ["incidents", "active_incidents", "down_agents"], "escalate_to_human": ["escalate"]}
    canonical = task
    for canon, alist in aliases.items():
        if task == canon or task in alist:
            canonical = canon; break
    log_res = _log_start(state, canonical)
    call_id = log_res["row"]["id"] if log_res.get("ok") and log_res.get("row") else None
    return {**state, "task": canonical, "call_id": call_id}

def fan_out_dx(state):
    """For morning_brief and run_full_audit â fire all 7 DX agents in parallel via langgraph-bridge."""
    if state.get("task") not in ("morning_brief", "run_full_audit"):
        return state
    results = []
    for dx in DX_AGENTS:
        res = _langgraph_fire(dx, {"trigger": f"ops_{state.get('task')}"}, wait=True, timeout_ms=30000)
        vals = res.get("state", {}).get("values", {}) if isinstance(res.get("state"), dict) else {}
        checks = vals.get("check_results", [])
        healthy = sum(1 for c in checks if c.get("status") == "healthy")
        total = len(checks)
        failures = [c.get("agent") for c in checks if c.get("status") != "healthy"]
        results.append({"dx_agent": dx, "summary": vals.get("summary", "?"), "healthy": healthy, "total": total, "failures": failures, "ok": res.get("ok", False)})
    return {**state, "dx_results": results}

def query_health(state):
    """Pull current system_health snapshot."""
    res = _supabase_get("system_health?select=agent_name,status,domain,tier,last_check_at,last_error&order=domain,agent_name&limit=200")
    rows = res["body"] if isinstance(res["body"], list) else []
    summary = {
        "total_agents": len(rows),
        "healthy": sum(1 for r in rows if r.get("status") == "healthy"),
        "degraded": sum(1 for r in rows if r.get("status") == "degraded"),
        "down": sum(1 for r in rows if r.get("status") == "down"),
        "by_domain": {},
        "down_list": [{"agent": r.get("agent_name"), "domain": r.get("domain"), "error": (r.get("last_error") or "")[:120]} for r in rows if r.get("status") != "healthy"]
    }
    for r in rows:
        d = r.get("domain", "unknown")
        summary["by_domain"].setdefault(d, {"total": 0, "healthy": 0})
        summary["by_domain"][d]["total"] += 1
        if r.get("status") == "healthy":
            summary["by_domain"][d]["healthy"] += 1
    return {**state, "health_summary": summary}

def query_recent_activity(state):
    """Recent agent_dispatches (last 24h) for activity stats."""
    threshold = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    res = _supabase_get(f"agent_dispatches?created_at=gte.{quote(threshold)}&select=source,status,dispatch_target,created_at&order=created_at.desc&limit=100")
    rows = res["body"] if isinstance(res["body"], list) else []
    by_status = {}
    by_domain = {}
    for r in rows:
        by_status[r.get("status", "?")] = by_status.get(r.get("status", "?"), 0) + 1
        by_domain[r.get("dispatch_target", "?")] = by_domain.get(r.get("dispatch_target", "?"), 0) + 1
    return {**state, "recent_alerts": {"dispatches_24h": len(rows), "by_status": by_status, "by_domain": by_domain}}

def compose_brief(state):
    """Build the consolidated morning brief text."""
    if state.get("task") not in ("morning_brief", "run_full_audit"):
        return state
    hs = state.get("health_summary", {})
    dx = state.get("dx_results", []) or []
    act = state.get("recent_alerts", {}) or {}
    
    total_dx = len(dx)
    dx_all_healthy = all(r.get("failures", []) == [] for r in dx)
    
    lines = []
    lines.append(f"*\U0001F305 MMA OS Operations \u2014 Morning Brief*")
    lines.append(f"_{datetime.now(timezone.utc).strftime('%A %b %d %Y %H:%M UTC')}_")
    lines.append("")
    
    # Top-level health
    overall_icon = "\U0001F7E2" if hs.get("down", 0) == 0 else ("\U0001F7E1" if hs.get("down", 0) < 3 else "\U0001F534")
    lines.append(f"{overall_icon} *Overall:* {hs.get('healthy', 0)}/{hs.get('total_agents', 0)} agents healthy")
    if hs.get("down", 0) > 0:
        lines.append(f"  \u26A0 {hs.get('down', 0)} down, {hs.get('degraded', 0)} degraded")
    lines.append("")
    
    # By-domain summary
    lines.append("*Domain status:*")
    for domain, stats in sorted((hs.get("by_domain") or {}).items()):
        icon = "\u2705" if stats["healthy"] == stats["total"] else "\u26A0"
        lines.append(f"  {icon} {domain}: {stats['healthy']}/{stats['total']}")
    lines.append("")
    
    # DX summaries
    lines.append("*DX agents (just ran):*")
    for r in dx:
        icon = "\u2705" if r.get("healthy") == r.get("total") else "\u26A0"
        lines.append(f"  {icon} {r['dx_agent']}: {r.get('summary', '?')}")
    lines.append("")
    
    # Active incidents
    down_list = hs.get("down_list", []) or []
    if down_list:
        lines.append(f"*\U0001F6A8 Active incidents ({len(down_list)}):*")
        for d in down_list[:10]:
            lines.append(f"  \u2022 [{d.get('domain')}] {d.get('agent')} \u2014 {d.get('error', '?')[:80]}")
        lines.append("")
    
    # Activity stats
    lines.append(f"*Master Orchestrator activity (24h):*")
    lines.append(f"  Dispatches: {act.get('dispatches_24h', 0)}")
    if act.get("by_status"):
        lines.append(f"  By status: " + ", ".join([f"{k}:{v}" for k,v in act.get('by_status', {}).items()]))
    if act.get("by_domain"):
        top_domains = sorted(act.get("by_domain", {}).items(), key=lambda x: -x[1])[:5]
        lines.append(f"  Top domains: " + ", ".join([f"{k}({v})" for k,v in top_domains]))
    lines.append("")
    
    if dx_all_healthy and hs.get("down", 0) == 0:
        lines.append("\u2705 *All systems green. Have a great day, Antonio.*")
    else:
        lines.append("\u26A0 *Some agents need attention. See incident list above.*")
    
    brief = "\n".join(lines)
    return {**state, "brief_text": brief}

def deliver_brief(state):
    """Send the brief to Telegram via comms_orchestrator."""
    if state.get("task") not in ("morning_brief", "run_full_audit"):
        return state
    brief = state.get("brief_text", "(no brief generated)")
    res = _langgraph_fire("comms_orchestrator", {"task": "send_telegram", "payload": {"message": brief, "category": "Operations Dept Morning Brief", "severity": "info"}, "parent_dispatch_id": state.get("parent_dispatch_id"), "source": "operations_department", "actor": "ops_dept_head"}, wait=True, timeout_ms=20000)
    return {**state, "comms_result": res}

def handle_specific_task(state):
    """For non-brief tasks (get_uptime_stats, list_active_incidents, escalate_to_human)."""
    task = state.get("task")
    if task == "get_uptime_stats":
        return state  # health_summary already populated in query_health
    if task == "list_active_incidents":
        return state  # down_list already in health_summary
    if task == "escalate_to_human":
        msg = state.get("payload", {}).get("message", "Operations Department escalation \u2014 immediate attention required.")
        sev = state.get("payload", {}).get("severity", "error")
        res = _langgraph_fire("comms_orchestrator", {"task": "send_admin_alert", "payload": {"message": msg, "severity": sev, "category": "Ops ESCALATION"}, "parent_dispatch_id": state.get("parent_dispatch_id"), "source": "operations_department", "actor": "ops_dept_head"}, wait=True, timeout_ms=20000)
        return {**state, "comms_result": res}
    return state

def log_complete(state):
    call_id = state.get("call_id")
    if not call_id: return state
    duration_ms = int((time.time() - (state.get("call_started_at") or time.time())) * 1000)
    result = {"task": state.get("task"), "comms_ok": (state.get("comms_result", {}) or {}).get("ok"), "dx_count": len(state.get("dx_results", []) or [])}
    _supabase_patch("agent_calls", "id", call_id, {"output": result, "status": "success", "duration_ms": duration_ms})
    return state

def summarize(state):
    task = state.get("task")
    if state.get("error"):
        return {**state, "summary": f"Operations ERROR: {state['error']}"}
    hs = state.get("health_summary", {})
    cm = state.get("comms_result", {}) or {}
    if task in ("morning_brief", "run_full_audit"):
        delivered = "\u2705" if cm.get("ok") else "\u26A0"
        return {**state, "summary": f"Ops.{task}: {hs.get('healthy', 0)}/{hs.get('total_agents', 0)} healthy | brief delivered to Telegram {delivered}"}
    if task == "get_uptime_stats":
        return {**state, "summary": f"Ops.uptime: {hs.get('healthy', 0)}/{hs.get('total_agents', 0)} healthy across {len(hs.get('by_domain') or {})} domains"}
    if task == "list_active_incidents":
        return {**state, "summary": f"Ops.incidents: {hs.get('down', 0)} down, {hs.get('degraded', 0)} degraded"}
    if task == "escalate_to_human":
        return {**state, "summary": f"Ops.escalate: telegram delivery {"OK" if cm.get('ok') else "WARN"}"}
    return {**state, "summary": f"Ops.{task}: complete"}

def build_graph():
    g = StateGraph(OpsState)
    for n, f in [("start", start), ("fan_out_dx", fan_out_dx), ("query_health", query_health), ("query_recent_activity", query_recent_activity), ("compose_brief", compose_brief), ("deliver_brief", deliver_brief), ("handle_specific_task", handle_specific_task), ("log_complete", log_complete), ("summarize", summarize)]:
        g.add_node(n, f)
    g.add_edge(START, "start")
    g.add_edge("start", "fan_out_dx")
    g.add_edge("fan_out_dx", "query_health")
    g.add_edge("query_health", "query_recent_activity")
    g.add_edge("query_recent_activity", "compose_brief")
    g.add_edge("compose_brief", "deliver_brief")
    g.add_edge("deliver_brief", "handle_specific_task")
    g.add_edge("handle_specific_task", "log_complete")
    g.add_edge("log_complete", "summarize")
    g.add_edge("summarize", END)
    return g.compile()

graph = build_graph()
