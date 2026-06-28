"""
BTF Education Engine - LangGraph v1 (Tier 1 specialized agent #24)

Doctrine S103 + S105 compliance:
  - BTF-exclusive education stream (DFY clients only, never Skool members)
  - 3-day cadence during active phase
  - Send stack: Paige Edge Function -> Resend (NOT GHL)

Doctrine S106 compliance:
  - Reads btf_deals (single source of truth for BTF cohort)
  - Mirrors touchpoints to btf_touchpoints (audit)

Tasks:
  - daily_education_sweep    Run every morning 10 AM ET, advance any due education sends
  - get_education_report     Return due/upcoming sends without firing (used by reporting)
  - skip_for_deal            Disable education for a specific deal (coach manual override)

OPERATING MODE: STUB-AWARE
  When PAIGE_BTF_SEND_URL is not configured (Paige Day 8 pending), the engine logs
  what WOULD send and digests to Telegram. Zero customer emails fire from this engine
  until Paige email_templates table is ready.

Doctrine S97 compliance: no backslashes or inner-doubles in f-strings.
Doctrine S98 compliance: 1x/day cron, no firing per individual customer event.
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
ICON_EDU = "EDU"
ICON_BTF = "BTF"

MMA_OS_FUNCTIONS_BASE = os.environ.get("MMA_OS_FUNCTIONS_BASE", "https://slcqeiqcrhepicqxqjng.supabase.co/functions/v1")
MMA_OS_SUPABASE_URL = os.environ.get("MMA_OS_SUPABASE_URL", "https://slcqeiqcrhepicqxqjng.supabase.co")
LANGGRAPH_BRIDGE_URL = MMA_OS_FUNCTIONS_BASE + "/langgraph-bridge"
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
LANGGRAPH_WRITER_API_KEY = os.environ.get("LANGGRAPH_WRITER_API_KEY", "")
PAIGE_BTF_SEND_URL = os.environ.get("PAIGE_BTF_SEND_URL", "")
PAIGE_BTF_SEND_KEY = os.environ.get("PAIGE_BTF_SEND_KEY", "")

class EducationState(TypedDict, total=False):
    task: str
    payload: dict
    parent_dispatch_id: Optional[str]
    source: Optional[str]
    call_id: str
    call_started_at: float
    due_enrollments: List[dict]
    sends_attempted: List[dict]
    sends_successful: List[dict]
    sends_stubbed: List[dict]
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

def _sb_patch(table, pk_field, pk_value, payload):
    if not SUPABASE_SERVICE_ROLE_KEY: return {"ok": False}
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.patch(MMA_OS_SUPABASE_URL + "/rest/v1/" + table + "?" + pk_field + "=eq." + pk_value, headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": "Bearer " + SUPABASE_SERVICE_ROLE_KEY, "Content-Type": "application/json"}, json=payload)
            return {"ok": r.status_code < 300, "status": r.status_code}
    except Exception: return {"ok": False}

def _sb_insert(table, payload):
    if not SUPABASE_SERVICE_ROLE_KEY: return {"ok": False}
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.post(MMA_OS_SUPABASE_URL + "/rest/v1/" + table, headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": "Bearer " + SUPABASE_SERVICE_ROLE_KEY, "Content-Type": "application/json", "Prefer": "return=representation"}, json=payload)
            d = r.json() if r.text else None
            return {"ok": r.status_code < 300, "row": d[0] if isinstance(d, list) and d else d}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

def _log_touchpoint(btf_deal_id, layer, touchpoint_type, metadata=None):
    if not btf_deal_id: return
    _sb_insert("btf_touchpoints", {"btf_deal_id": btf_deal_id, "layer": layer, "touchpoint_type": touchpoint_type, "direction": "outbound", "metadata": metadata or {}})

def start(state):
    state = {**state, "error": None, "call_started_at": time.time(), "sends_attempted": [], "sends_successful": [], "sends_stubbed": [], "comms_results": []}
    task = (state.get("task") or "daily_education_sweep").strip().lower()
    aliases = {
        "daily_education_sweep": ["education_sweep", "edu_sweep", "morning_education"],
        "get_education_report": ["education_report", "edu_report"],
        "skip_for_deal": ["skip_education", "disable_education"]
    }
    canonical = task
    for canon, alist in aliases.items():
        if task == canon or task in alist:
            canonical = canon
            break
    log_res = _sb_insert("agent_calls", {"parent_dispatch_id": state.get("parent_dispatch_id"), "parent_agent": "btf_education_engine", "child_agent": "self", "child_tier": 1, "task": canonical, "input": state.get("payload", {}), "status": "pending"})
    call_id = log_res["row"]["id"] if log_res.get("ok") and log_res.get("row") else None
    return {**state, "task": canonical, "call_id": call_id}

def fetch_due_enrollments(state):
    """Find all BTF deals with due education send."""
    if state.get("task") == "skip_for_deal":
        return state
    now_iso = datetime.now(timezone.utc).isoformat()
    enc = quote(now_iso)
    # Active deals, education enabled, drip not yet completed, next_send_at <= now
    res = _sb_get("btf_deals?status=eq.active&education_enabled=eq.true&education_drip_completed_at=is.null&education_next_send_at=lte." + enc + "&select=id,contact_email,full_legal_name,current_phase,education_step,assigned_coach&order=education_next_send_at.asc&limit=50")
    due = res["body"] if isinstance(res["body"], list) else []
    return {**state, "due_enrollments": due}

def process_sends(state):
    """For each due enrollment: lookup next topic, send (or stub), advance step."""
    if state.get("task") not in ("daily_education_sweep",):
        return state
    due = state.get("due_enrollments", []) or []
    if not due:
        return state
    stack_ready = bool(PAIGE_BTF_SEND_URL and PAIGE_BTF_SEND_KEY)
    successful = []
    stubbed = []
    attempted = []
    for deal in due:
        deal_id = deal.get("id")
        phase = (deal.get("current_phase") or "build").lower()
        # Map BTF phase names to education topic phases
        topic_phase = phase if phase in ("build", "stack", "fund") else "build"
        # If phase is pre_build, send build topics. If funded, drip is done.
        if phase == "pre_build":
            topic_phase = "build"
        if phase == "funded":
            # Mark drip complete, skip
            _sb_patch("btf_deals", "id", deal_id, {"education_drip_completed_at": datetime.now(timezone.utc).isoformat()})
            continue
        next_position = int(deal.get("education_step", 0)) + 1
        # Lookup next topic
        topic_res = _sb_get("btf_education_topics?phase=eq." + topic_phase + "&position=eq." + str(next_position) + "&limit=1")
        topics = topic_res["body"] if isinstance(topic_res["body"], list) else []
        if not topics:
            # No more topics in this phase, advance to next phase OR complete
            phase_order = ["build", "stack", "fund"]
            try:
                next_phase_idx = phase_order.index(topic_phase) + 1
            except ValueError:
                next_phase_idx = len(phase_order)
            if next_phase_idx >= len(phase_order):
                _sb_patch("btf_deals", "id", deal_id, {"education_drip_completed_at": datetime.now(timezone.utc).isoformat()})
                continue
            # Try position 1 of next phase
            next_phase = phase_order[next_phase_idx]
            topic_res2 = _sb_get("btf_education_topics?phase=eq." + next_phase + "&position=eq.1&limit=1")
            topics = topic_res2["body"] if isinstance(topic_res2["body"], list) else []
            if not topics:
                continue
            next_position = 1
        topic = topics[0]
        attempted.append({"deal_id": deal_id, "email": deal.get("contact_email"), "topic_key": topic.get("topic_key")})
        if stack_ready and topic.get("paige_template_key"):
            # SEND via Paige + Resend (production path)
            send_result = _post(PAIGE_BTF_SEND_URL, {"contact_email": deal.get("contact_email"), "template_key": topic.get("paige_template_key"), "vars": {"first_name": (deal.get("full_legal_name") or "").split(" ")[0] if deal.get("full_legal_name") else "", "current_phase": deal.get("current_phase"), "coach_name": deal.get("assigned_coach") or "your coach"}}, PAIGE_BTF_SEND_KEY, timeout=20.0)
            if send_result.get("ok"):
                successful.append({"deal_id": deal_id, "email": deal.get("contact_email"), "topic_key": topic.get("topic_key")})
                _log_touchpoint(deal_id, "email", "education_drip_sent", metadata={"topic_key": topic.get("topic_key"), "stack": "paige_resend"})
        else:
            # STUB MODE: log what WOULD send (Paige Day 8 pending)
            stubbed.append({"deal_id": deal_id, "email": deal.get("contact_email"), "topic_key": topic.get("topic_key"), "title": topic.get("title")})
            _log_touchpoint(deal_id, "stubbed", "education_drip_stubbed", metadata={"topic_key": topic.get("topic_key"), "reason": "PAIGE_BTF_SEND_URL not configured"})
        # Advance step + schedule next (3 days out)
        next_send = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        _sb_patch("btf_deals", "id", deal_id, {"education_step": next_position, "education_next_send_at": next_send})
    return {**state, "sends_attempted": attempted, "sends_successful": successful, "sends_stubbed": stubbed}

def deliver_digest(state):
    """Telegram digest to Antonio with summary."""
    if state.get("task") not in ("daily_education_sweep",):
        return state
    attempted = state.get("sends_attempted", []) or []
    successful = state.get("sends_successful", []) or []
    stubbed = state.get("sends_stubbed", []) or []
    if not attempted:
        return state
    lines = ["[" + ICON_EDU + "] BTF Education Drip - daily sweep"]
    lines.append("Attempted: " + str(len(attempted)) + " | Sent: " + str(len(successful)) + " | Stubbed (Paige pending): " + str(len(stubbed)))
    if successful:
        lines.append("")
        lines.append("**Sent today:**")
        for s in successful[:10]:
            lines.append("  - " + (s.get("email") or "?") + " <- " + (s.get("topic_key") or "?"))
    if stubbed:
        lines.append("")
        lines.append("**Would have sent (stub mode):**")
        for s in stubbed[:10]:
            lines.append("  - " + (s.get("email") or "?") + " <- " + (s.get("title") or "?"))
    msg = "\n".join(lines)
    res = _langgraph_fire("comms_orchestrator", {"task": "send_telegram", "payload": {"message": msg, "category": "BTF Education", "severity": "info"}, "parent_dispatch_id": state.get("parent_dispatch_id"), "source": "btf_education_engine"}, wait=True, timeout_ms=20000)
    return {**state, "comms_results": [res]}

def handle_skip(state):
    """Manual coach override: disable education for a specific deal."""
    if state.get("task") != "skip_for_deal":
        return state
    payload = state.get("payload") or {}
    deal_id = payload.get("deal_id")
    if not deal_id:
        return {**state, "error": "deal_id required for skip_for_deal"}
    _sb_patch("btf_deals", "id", deal_id, {"education_enabled": False})
    return state

def log_complete(state):
    call_id = state.get("call_id")
    if not call_id: return state
    duration_ms = int((time.time() - (state.get("call_started_at") or time.time())) * 1000)
    result = {"task": state.get("task"), "due_count": len(state.get("due_enrollments", []) or []), "attempted": len(state.get("sends_attempted", []) or []), "successful": len(state.get("sends_successful", []) or []), "stubbed": len(state.get("sends_stubbed", []) or [])}
    _sb_patch("agent_calls", "id", call_id, {"output": result, "status": "success", "duration_ms": duration_ms})
    return state

def summarize(state):
    if state.get("error"):
        return {**state, "summary": "BTF Education ERROR: " + str(state["error"])}
    task = state.get("task")
    if task == "skip_for_deal":
        return {**state, "summary": "BTF Education: deal opted out of drip"}
    if task == "get_education_report":
        return {**state, "summary": "BTF Education report: " + str(len(state.get("due_enrollments", []) or [])) + " enrollments due"}
    a = len(state.get("sends_attempted", []) or [])
    s = len(state.get("sends_successful", []) or [])
    st = len(state.get("sends_stubbed", []) or [])
    return {**state, "summary": "BTF Education sweep: " + str(a) + " attempted, " + str(s) + " sent, " + str(st) + " stubbed (Paige pending)"}

def build_graph():
    g = StateGraph(EducationState)
    for n, f in [("start", start), ("fetch_due_enrollments", fetch_due_enrollments), ("process_sends", process_sends), ("deliver_digest", deliver_digest), ("handle_skip", handle_skip), ("log_complete", log_complete), ("summarize", summarize)]:
        g.add_node(n, f)
    g.add_edge(START, "start")
    g.add_edge("start", "fetch_due_enrollments")
    g.add_edge("fetch_due_enrollments", "process_sends")
    g.add_edge("process_sends", "deliver_digest")
    g.add_edge("deliver_digest", "handle_skip")
    g.add_edge("handle_skip", "log_complete")
    g.add_edge("log_complete", "summarize")
    g.add_edge("summarize", END)
    return g.compile()

graph = build_graph()
