"""
BTF Education Engine v2 - LangGraph (Tier 1 specialized agent #24)

LIVE MODE - sends via paige-mcp-proxy then send_btf_template_email.
Doctrine S73 safety: BTF_EDUCATION_TEST_RECIPIENT env var override routes ALL sends
to that address instead of customer email, until Antonio unsets the var.

Doctrine S103 + S105 compliance.
Tasks: daily_education_sweep, get_education_report, skip_for_deal.
"""
from __future__ import annotations
import os, time
import json as _json
from typing import TypedDict, Optional, List
from urllib.parse import quote
import httpx
from langgraph.graph import StateGraph, START, END
from datetime import datetime, timezone, timedelta

ICON_OK = "OK"
ICON_WARN = "WARN"
ICON_EDU = "EDU"

MMA_OS_FUNCTIONS_BASE = os.environ.get("MMA_OS_FUNCTIONS_BASE", "https://slcqeiqcrhepicqxqjng.supabase.co/functions/v1")
MMA_OS_SUPABASE_URL = os.environ.get("MMA_OS_SUPABASE_URL", "https://slcqeiqcrhepicqxqjng.supabase.co")
LANGGRAPH_BRIDGE_URL = MMA_OS_FUNCTIONS_BASE + "/langgraph-bridge"
PAIGE_MCP_PROXY_URL = MMA_OS_FUNCTIONS_BASE + "/paige-mcp-proxy"
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
LANGGRAPH_WRITER_API_KEY = os.environ.get("LANGGRAPH_WRITER_API_KEY", "")
MMA_OS_BRIDGE_API_KEY = os.environ.get("MMA_OS_BRIDGE_API_KEY", "") or LANGGRAPH_WRITER_API_KEY
BTF_EDUCATION_TEST_RECIPIENT = os.environ.get("BTF_EDUCATION_TEST_RECIPIENT", "")
BTF_WORKSPACE_BASE_URL = os.environ.get("BTF_WORKSPACE_BASE_URL", "https://portal.mogulmakeracademy.com/workspace")

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
    sends_failed: List[dict]
    sends_test_redirected: List[dict]
    comms_results: List[dict]
    summary: str
    error: Optional[str]

def _post(url, body, bearer, timeout=20.0):
    if not bearer: return {"ok": False, "error": "missing bearer"}
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.post(url, headers={"Authorization": "Bearer " + bearer, "Content-Type": "application/json"}, json=body)
            try: return r.json()
            except Exception: return {"ok": False, "error": "non-json", "status": r.status_code}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

def _langgraph_fire(graph_id, input_data, wait=True, timeout_ms=20000):
    return _post(LANGGRAPH_BRIDGE_URL, {"verb": "fire_agent", "graph_id": graph_id, "input": input_data, "wait": wait, "timeout_ms": timeout_ms}, LANGGRAPH_WRITER_API_KEY, timeout=timeout_ms/1000 + 10)

def _paige_mcp_call(method, params, timeout_s=20.0):
    res = _post(PAIGE_MCP_PROXY_URL, {"method": method, "params": params}, MMA_OS_BRIDGE_API_KEY, timeout=timeout_s)
    if not res.get("ok"): return res
    mcp_resp = res.get("mcp_response", {})
    if mcp_resp.get("error"): return {"ok": False, "error": mcp_resp.get("error")}
    content_list = (mcp_resp.get("result") or {}).get("content") or [{}]
    content = content_list[0].get("text", "")
    try:
        parsed = _json.loads(content) if content else {}
    except Exception:
        parsed = {"raw": content}
    return {"ok": parsed.get("ok", True), "result": parsed}

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
    state = {**state, "error": None, "call_started_at": time.time(), "sends_attempted": [], "sends_successful": [], "sends_failed": [], "sends_test_redirected": [], "comms_results": []}
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
    if state.get("task") == "skip_for_deal":
        return state
    now_iso = datetime.now(timezone.utc).isoformat()
    enc = quote(now_iso)
    res = _sb_get("btf_deals?status=eq.active&education_enabled=eq.true&education_drip_completed_at=is.null&education_next_send_at=lte." + enc + "&select=id,contact_email,full_legal_name,current_phase,education_step,assigned_coach&order=education_next_send_at.asc&limit=50")
    due = res["body"] if isinstance(res["body"], list) else []
    return {**state, "due_enrollments": due}

def process_sends(state):
    if state.get("task") not in ("daily_education_sweep",):
        return state
    due = state.get("due_enrollments", []) or []
    if not due:
        return state
    successful = []
    failed = []
    test_redirected = []
    attempted = []
    test_mode = bool(BTF_EDUCATION_TEST_RECIPIENT)
    for deal in due:
        deal_id = deal.get("id")
        phase = (deal.get("current_phase") or "build").lower()
        topic_phase = phase if phase in ("build", "stack", "fund") else "build"
        if phase == "pre_build":
            topic_phase = "build"
        if phase == "funded":
            _sb_patch("btf_deals", "id", deal_id, {"education_drip_completed_at": datetime.now(timezone.utc).isoformat()})
            continue
        next_position = int(deal.get("education_step", 0)) + 1
        topic_res = _sb_get("btf_education_topics?phase=eq." + topic_phase + "&position=eq." + str(next_position) + "&limit=1")
        topics = topic_res["body"] if isinstance(topic_res["body"], list) else []
        if not topics:
            phase_order = ["build", "stack", "fund"]
            try: next_phase_idx = phase_order.index(topic_phase) + 1
            except ValueError: next_phase_idx = len(phase_order)
            if next_phase_idx >= len(phase_order):
                _sb_patch("btf_deals", "id", deal_id, {"education_drip_completed_at": datetime.now(timezone.utc).isoformat()})
                continue
            next_phase = phase_order[next_phase_idx]
            topic_res2 = _sb_get("btf_education_topics?phase=eq." + next_phase + "&position=eq.1&limit=1")
            topics = topic_res2["body"] if isinstance(topic_res2["body"], list) else []
            if not topics: continue
            next_position = 1
        topic = topics[0]
        paige_key = topic.get("paige_template_key")
        if not paige_key:
            failed.append({"deal_id": deal_id, "email": deal.get("contact_email"), "error": "topic missing paige_template_key", "topic_key": topic.get("topic_key")})
            continue
        true_recipient = deal.get("contact_email")
        actual_recipient = BTF_EDUCATION_TEST_RECIPIENT if test_mode else true_recipient
        first_name = ""
        if deal.get("full_legal_name"):
            first_name = deal["full_legal_name"].split(" ")[0]
        vars_obj = {
            "first_name": first_name,
            "current_phase": (deal.get("current_phase") or "BUILD").upper(),
            "coach_name": deal.get("assigned_coach") or "your coach",
            "workspace_url": BTF_WORKSPACE_BASE_URL
        }
        attempted.append({"deal_id": deal_id, "true_recipient": true_recipient, "actual_recipient": actual_recipient, "topic_key": topic.get("topic_key"), "test_mode": test_mode})
        send_res = _paige_mcp_call("tools/call", {
            "name": "send_btf_template_email",
            "arguments": {"to_email": actual_recipient, "template_key": paige_key, "vars": vars_obj}
        }, timeout_s=20.0)
        if send_res.get("ok"):
            msg_id = (send_res.get("result") or {}).get("message_id")
            entry = {"deal_id": deal_id, "true_recipient": true_recipient, "actual_recipient": actual_recipient, "topic_key": topic.get("topic_key"), "message_id": msg_id}
            if test_mode:
                test_redirected.append(entry)
                _log_touchpoint(deal_id, "email", "education_drip_test_redirected", metadata={"topic_key": topic.get("topic_key"), "true_recipient": true_recipient, "actual_recipient": actual_recipient, "message_id": msg_id})
            else:
                successful.append(entry)
                _log_touchpoint(deal_id, "email", "education_drip_sent", metadata={"topic_key": topic.get("topic_key"), "stack": "paige_mcp_proxy", "message_id": msg_id})
            if not test_mode:
                next_send = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
                _sb_patch("btf_deals", "id", deal_id, {"education_step": next_position, "education_next_send_at": next_send})
        else:
            failed.append({"deal_id": deal_id, "email": actual_recipient, "topic_key": topic.get("topic_key"), "error": str(send_res.get("error"))})
            _log_touchpoint(deal_id, "email", "education_drip_failed", metadata={"topic_key": topic.get("topic_key"), "error": str(send_res.get("error"))})
    return {**state, "sends_attempted": attempted, "sends_successful": successful, "sends_failed": failed, "sends_test_redirected": test_redirected}

def deliver_digest(state):
    if state.get("task") not in ("daily_education_sweep",):
        return state
    attempted = state.get("sends_attempted", []) or []
    successful = state.get("sends_successful", []) or []
    failed = state.get("sends_failed", []) or []
    redirected = state.get("sends_test_redirected", []) or []
    if not attempted:
        return state
    lines = ["[" + ICON_EDU + "] BTF Education Drip - daily sweep"]
    if BTF_EDUCATION_TEST_RECIPIENT:
        lines.append("[" + ICON_WARN + "] TEST MODE active - all sends redirected to " + BTF_EDUCATION_TEST_RECIPIENT)
    lines.append("Attempted: " + str(len(attempted)) + " | Live sent: " + str(len(successful)) + " | Test redirected: " + str(len(redirected)) + " | Failed: " + str(len(failed)))
    if successful:
        lines.append("")
        lines.append("*Live sends (real customers):*")
        for s in successful[:10]:
            lines.append("  - " + (s.get("true_recipient") or "?") + " <- " + (s.get("topic_key") or "?"))
    if redirected:
        lines.append("")
        lines.append("*Test redirected (would have sent to customers):*")
        for s in redirected[:10]:
            lines.append("  - " + (s.get("true_recipient") or "?") + " <- " + (s.get("topic_key") or "?"))
    if failed:
        lines.append("")
        lines.append("*Failed:*")
        for s in failed[:10]:
            err = (s.get("error") or "?")[:120]
            lines.append("  - " + (s.get("email") or s.get("deal_id") or "?") + " | " + err)
    msg = "\n".join(lines)
    sev = "info" if not failed else "warning"
    res = _langgraph_fire("comms_orchestrator", {"task": "send_telegram", "payload": {"message": msg, "category": "BTF Education", "severity": sev}, "parent_dispatch_id": state.get("parent_dispatch_id"), "source": "btf_education_engine"}, wait=True, timeout_ms=20000)
    return {**state, "comms_results": [res]}

def handle_skip(state):
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
    result = {"task": state.get("task"), "due_count": len(state.get("due_enrollments", []) or []), "attempted": len(state.get("sends_attempted", []) or []), "successful": len(state.get("sends_successful", []) or []), "redirected": len(state.get("sends_test_redirected", []) or []), "failed": len(state.get("sends_failed", []) or []), "test_mode": bool(BTF_EDUCATION_TEST_RECIPIENT)}
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
    r = len(state.get("sends_test_redirected", []) or [])
    f = len(state.get("sends_failed", []) or [])
    mode = " [TEST MODE]" if BTF_EDUCATION_TEST_RECIPIENT else ""
    return {**state, "summary": "BTF Education sweep" + mode + ": " + str(a) + " attempted, " + str(s) + " live sent, " + str(r) + " test redirected, " + str(f) + " failed"}

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
