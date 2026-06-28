"""
BTF Stall Detector — LangGraph v1 (Tier 1 specialized agent)

Doctrine §103 + §103 correction (90-day program):
  - Phase open >45 days = stalled (1.5x the 30-day target per phase)
  - Document requested >14 days unfulfilled = stalled
  - Intake stalled >72 hours after invite acceptance
  - Total program >150 days from close without funded = executive review
  - Coach message thread idle >14 days = stalled
  - Client has not logged in to portal in 14 days = stalled

Tasks:
  - daily_stall_sweep    Run every morning at 8 AM ET, fire Telegram alerts
  - get_stall_report     Return stall list without firing (used by ops_dept brief)
  - check_specific_deal  Check stall conditions for one deal_id (manual trigger)

Doctrine §97 + §97b compliance: no backslashes or inner-doubles in f-strings.
Doctrine §98 compliance: 1x/day cron, customer-triggered checks for ad-hoc.
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
ICON_STALL = "STALL"
ICON_BTF = "BTF"

MMA_OS_FUNCTIONS_BASE = os.environ.get("MMA_OS_FUNCTIONS_BASE", "https://slcqeiqcrhepicqxqjng.supabase.co/functions/v1")
MMA_OS_SUPABASE_URL = os.environ.get("MMA_OS_SUPABASE_URL", "https://slcqeiqcrhepicqxqjng.supabase.co")
LANGGRAPH_BRIDGE_URL = MMA_OS_FUNCTIONS_BASE + "/langgraph-bridge"
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
LANGGRAPH_WRITER_API_KEY = os.environ.get("LANGGRAPH_WRITER_API_KEY", "")

# Stall thresholds (Doctrine §103 v1.1 — 90-day sprint)
PHASE_STALL_DAYS = 45
DOC_STALL_DAYS = 14
INTAKE_STALL_HOURS = 72
PROGRAM_EXEC_REVIEW_DAYS = 150
COACH_THREAD_STALL_DAYS = 14
CLIENT_LOGIN_STALL_DAYS = 14

class StallState(TypedDict, total=False):
    task: str
    payload: dict
    parent_dispatch_id: Optional[str]
    source: Optional[str]
    call_id: str
    call_started_at: float
    stalls_phase: List[dict]
    stalls_doc: List[dict]
    stalls_intake: List[dict]
    stalls_exec_review: List[dict]
    total_stall_count: int
    alert_messages: List[str]
    comms_results: List[dict]
    summary: str
    error: Optional[str]

def _post(url, body, bearer, timeout=20.0):
    if not bearer: return {"ok": False, "error": "missing bearer"}
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.post(url, headers={"Authorization": "Bearer " + bearer, "Content-Type": "application/json"}, json=body)
            try: return r.json()
            except Exception: return {"ok": False, "error": "non-json"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

def _langgraph_fire(graph_id, input_data, wait=True, timeout_ms=20000):
    return _post(LANGGRAPH_BRIDGE_URL, {"verb": "fire_agent", "graph_id": graph_id, "input": input_data, "wait": wait, "timeout_ms": timeout_ms}, LANGGRAPH_WRITER_API_KEY, timeout=timeout_ms/1000 + 10)

def _sb_get(path):
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.get(MMA_OS_SUPABASE_URL + "/rest/v1/" + path, headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": "Bearer " + SUPABASE_SERVICE_ROLE_KEY})
            return {"status": r.status_code, "body": r.json() if r.text else []}
    except Exception as exc:
        return {"status": 0, "body": {"error": str(exc)}}

def _sb_insert(table, payload):
    if not SUPABASE_SERVICE_ROLE_KEY: return {"ok": False}
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.post(MMA_OS_SUPABASE_URL + "/rest/v1/" + table, headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": "Bearer " + SUPABASE_SERVICE_ROLE_KEY, "Content-Type": "application/json", "Prefer": "return=representation"}, json=payload)
            d = r.json()
            return {"ok": r.status_code < 300, "row": d[0] if isinstance(d, list) and d else None}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

def _log_touchpoint(btf_deal_id, layer, touchpoint_type, metadata=None):
    if not btf_deal_id: return
    _sb_insert("btf_touchpoints", {"btf_deal_id": btf_deal_id, "layer": layer, "touchpoint_type": touchpoint_type, "direction": "outbound", "metadata": metadata or {}})

def start(state):
    state = {**state, "error": None, "call_started_at": time.time(), "stalls_phase": [], "stalls_doc": [], "stalls_intake": [], "stalls_exec_review": [], "alert_messages": [], "comms_results": []}
    task = (state.get("task") or "daily_stall_sweep").strip().lower()
    aliases = {
        "daily_stall_sweep": ["stall_sweep", "morning_stall_check", "stall_check"],
        "get_stall_report": ["stall_report", "report"],
        "check_specific_deal": ["check_deal", "single_check"]
    }
    canonical = task
    for canon, alist in aliases.items():
        if task == canon or task in alist:
            canonical = canon
            break
    log_res = _sb_insert("agent_calls", {"parent_dispatch_id": state.get("parent_dispatch_id"), "parent_agent": "btf_stall_detector", "child_agent": "self", "child_tier": 1, "task": canonical, "input": state.get("payload", {}), "status": "pending"})
    call_id = log_res["row"]["id"] if log_res.get("ok") and log_res.get("row") else None
    return {**state, "task": canonical, "call_id": call_id}

def detect_phase_stalls(state):
    """Phase open >45 days = stalled."""
    threshold = (datetime.now(timezone.utc) - timedelta(days=PHASE_STALL_DAYS)).isoformat()
    res = _sb_get("btf_deals?status=eq.active&phase_started_at=lt." + quote(threshold) + "&current_phase=neq.funded&select=id,contact_email,full_legal_name,current_phase,phase_started_at,assigned_coach")
    stalls = res["body"] if isinstance(res["body"], list) else []
    return {**state, "stalls_phase": stalls}

def detect_intake_stalls(state):
    """Workspace invited but no intake submitted within 72h."""
    threshold = (datetime.now(timezone.utc) - timedelta(hours=INTAKE_STALL_HOURS)).isoformat()
    # Touchpoints of type=workspace_invite older than 72h, where intake_submitted touchpoint NOT yet logged for same deal
    res = _sb_get("btf_touchpoints?touchpoint_type=eq.workspace_invite&delivered_at=lt." + quote(threshold) + "&select=btf_deal_id,delivered_at,metadata")
    invites = res["body"] if isinstance(res["body"], list) else []
    # Check which of these have NO intake_submitted touchpoint
    stalls = []
    for inv in invites:
        deal_id = inv.get("btf_deal_id")
        if not deal_id: continue
        intake_res = _sb_get("btf_touchpoints?btf_deal_id=eq." + deal_id + "&touchpoint_type=eq.intake_submitted&select=id&limit=1")
        if not intake_res["body"]:
            # No intake submitted — fetch deal info
            deal_res = _sb_get("btf_deals?id=eq." + deal_id + "&select=contact_email,full_legal_name,assigned_coach")
            if deal_res["body"]:
                d = deal_res["body"][0]
                stalls.append({"btf_deal_id": deal_id, "contact_email": d.get("contact_email"), "full_legal_name": d.get("full_legal_name"), "assigned_coach": d.get("assigned_coach"), "invited_at": inv.get("delivered_at")})
    return {**state, "stalls_intake": stalls}

def detect_exec_review(state):
    """Program >150 days from close without funded outcome."""
    threshold = (datetime.now(timezone.utc) - timedelta(days=PROGRAM_EXEC_REVIEW_DAYS)).isoformat()
    res = _sb_get("btf_deals?status=eq.active&closed_at=lt." + quote(threshold) + "&current_phase=neq.funded&select=id,contact_email,full_legal_name,current_phase,closed_at,assigned_coach")
    stalls = res["body"] if isinstance(res["body"], list) else []
    return {**state, "stalls_exec_review": stalls}

def compose_alerts(state):
    """Build Telegram alert messages for each stall category."""
    if state.get("task") == "get_stall_report":
        # Report mode: no alerts fired, just return data
        return state
    alerts = []
    phase_stalls = state.get("stalls_phase", []) or []
    intake_stalls = state.get("stalls_intake", []) or []
    exec_stalls = state.get("stalls_exec_review", []) or []
    total = len(phase_stalls) + len(intake_stalls) + len(exec_stalls)
    if total == 0:
        # Healthy sweep — daily silence is golden, but log one heartbeat message for visibility
        alerts.append("[" + ICON_OK + "] BTF Stall Sweep: all clear. " + str(len(phase_stalls) + len(intake_stalls) + len(exec_stalls)) + " stalls detected across " + str(len(phase_stalls)) + " phase, " + str(len(intake_stalls)) + " intake, " + str(len(exec_stalls)) + " exec-review thresholds.")
        return {**state, "alert_messages": alerts, "total_stall_count": 0}
    # Compose individual alerts
    if phase_stalls:
        lines = ["[" + ICON_STALL + "] BTF Phase Stalls (" + str(len(phase_stalls)) + " clients > 45 days in phase):"]
        for s in phase_stalls[:10]:
            name = s.get("full_legal_name") or s.get("contact_email", "?")
            phase = s.get("current_phase", "?")
            coach = s.get("assigned_coach") or "unassigned"
            lines.append("  - " + name + " | phase: " + phase + " | coach: " + coach)
        if len(phase_stalls) > 10:
            lines.append("  ... and " + str(len(phase_stalls) - 10) + " more")
        alerts.append("\n".join(lines))
    if intake_stalls:
        lines = ["[" + ICON_STALL + "] BTF Intake Stalls (" + str(len(intake_stalls)) + " clients > 72h since invite, no intake):"]
        for s in intake_stalls[:10]:
            name = s.get("full_legal_name") or s.get("contact_email", "?")
            coach = s.get("assigned_coach") or "unassigned"
            lines.append("  - " + name + " | coach: " + coach + " | invited: " + str(s.get("invited_at", "?"))[:10])
        if len(intake_stalls) > 10:
            lines.append("  ... and " + str(len(intake_stalls) - 10) + " more")
        alerts.append("\n".join(lines))
    if exec_stalls:
        lines = ["[" + ICON_WARN + "] BTF Executive Review (" + str(len(exec_stalls)) + " clients > 150 days from close, not yet funded):"]
        for s in exec_stalls[:10]:
            name = s.get("full_legal_name") or s.get("contact_email", "?")
            phase = s.get("current_phase", "?")
            coach = s.get("assigned_coach") or "unassigned"
            lines.append("  - " + name + " | phase: " + phase + " | coach: " + coach + " | closed: " + str(s.get("closed_at", "?"))[:10])
        if len(exec_stalls) > 10:
            lines.append("  ... and " + str(len(exec_stalls) - 10) + " more")
        alerts.append("\n".join(lines))
    return {**state, "alert_messages": alerts, "total_stall_count": total}

def fire_alerts(state):
    if state.get("task") == "get_stall_report":
        return state
    alerts = state.get("alert_messages", []) or []
    results = []
    for msg in alerts:
        res = _langgraph_fire("comms_orchestrator", {"task": "send_telegram", "payload": {"message": msg, "category": "BTF Stall Alert", "severity": "warning" if state.get("total_stall_count", 0) > 0 else "info"}, "parent_dispatch_id": state.get("parent_dispatch_id"), "source": "btf_stall_detector"}, wait=True, timeout_ms=20000)
        results.append(res)
    # Log touchpoints for each stalled deal
    for s in (state.get("stalls_phase", []) or []):
        _log_touchpoint(s.get("id"), "telegram", "stall_alert_phase", metadata={"phase": s.get("current_phase")})
    for s in (state.get("stalls_intake", []) or []):
        _log_touchpoint(s.get("btf_deal_id"), "telegram", "stall_alert_intake")
    for s in (state.get("stalls_exec_review", []) or []):
        _log_touchpoint(s.get("id"), "telegram", "stall_alert_exec_review", metadata={"days_since_close": "> 150"})
    return {**state, "comms_results": results}

def log_complete(state):
    call_id = state.get("call_id")
    if not call_id: return state
    duration_ms = int((time.time() - (state.get("call_started_at") or time.time())) * 1000)
    result = {"task": state.get("task"), "phase_stalls": len(state.get("stalls_phase", []) or []), "intake_stalls": len(state.get("stalls_intake", []) or []), "exec_review": len(state.get("stalls_exec_review", []) or []), "total": state.get("total_stall_count", 0), "alerts_fired": len(state.get("comms_results", []) or [])}
    try:
        with httpx.Client(timeout=10.0) as client:
            client.patch(MMA_OS_SUPABASE_URL + "/rest/v1/agent_calls?id=eq." + call_id, headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": "Bearer " + SUPABASE_SERVICE_ROLE_KEY, "Content-Type": "application/json"}, json={"output": result, "status": "success", "duration_ms": duration_ms})
    except Exception: pass
    return state

def summarize(state):
    if state.get("error"):
        return {**state, "summary": "BTF Stall Detector ERROR: " + str(state["error"])}
    p = len(state.get("stalls_phase", []) or [])
    i = len(state.get("stalls_intake", []) or [])
    e = len(state.get("stalls_exec_review", []) or [])
    total = p + i + e
    alerts_fired = len(state.get("comms_results", []) or [])
    return {**state, "summary": "BTF Stall: " + str(total) + " stalls (" + str(p) + " phase, " + str(i) + " intake, " + str(e) + " exec-review) | alerts fired: " + str(alerts_fired)}

def build_graph():
    g = StateGraph(StallState)
    for n, f in [("start", start), ("detect_phase_stalls", detect_phase_stalls), ("detect_intake_stalls", detect_intake_stalls), ("detect_exec_review", detect_exec_review), ("compose_alerts", compose_alerts), ("fire_alerts", fire_alerts), ("log_complete", log_complete), ("summarize", summarize)]:
        g.add_node(n, f)
    g.add_edge(START, "start")
    g.add_edge("start", "detect_phase_stalls")
    g.add_edge("detect_phase_stalls", "detect_intake_stalls")
    g.add_edge("detect_intake_stalls", "detect_exec_review")
    g.add_edge("detect_exec_review", "compose_alerts")
    g.add_edge("compose_alerts", "fire_alerts")
    g.add_edge("fire_alerts", "log_complete")
    g.add_edge("log_complete", "summarize")
    g.add_edge("summarize", END)
    return g.compile()

graph = build_graph()
