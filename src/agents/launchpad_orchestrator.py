"""
LaunchPad Orchestrator — LangGraph v1 (Stream #3 agent)

Doctrine §101 Stream #3: The Launch Pad ($19/mo + $47/mo Pro)
  - Lead-magnet first, MRR second
  - Every paid subscriber is a qualified BTF prospect
  - Funnel: free check -> trial -> $19 -> $47 -> $4,997 BTF -> funded

Tasks: handle_signup, handle_trial_end, handle_upgrade_to_pro, handle_cancel,
       daily_launchpad_brief, list_active_subscribers.

Doctrine §97 compliance: no backslashes in f-string expressions.
Doctrine §98 compliance: 1x/day brief, customer-triggered fires for the rest.
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
ICON_NEW = "NEW"
ICON_MONEY = "$$$"

MMA_OS_FUNCTIONS_BASE = os.environ.get("MMA_OS_FUNCTIONS_BASE", "https://slcqeiqcrhepicqxqjng.supabase.co/functions/v1")
MMA_OS_SUPABASE_URL = os.environ.get("MMA_OS_SUPABASE_URL", "https://slcqeiqcrhepicqxqjng.supabase.co")
LANGGRAPH_BRIDGE_URL = MMA_OS_FUNCTIONS_BASE + "/langgraph-bridge"
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
LANGGRAPH_WRITER_API_KEY = os.environ.get("LANGGRAPH_WRITER_API_KEY", "")
DOLLAR = "$"  # avoid f-string interpolation collisions

class LPState(TypedDict, total=False):
    task: str
    payload: dict
    parent_dispatch_id: Optional[str]
    source: Optional[str]
    actor: Optional[str]
    call_id: str
    call_started_at: float
    active_subscribers: List[dict]
    signups_today: List[dict]
    upgrades_today: List[dict]
    cancels_today: List[dict]
    btf_qualified: List[dict]
    mrr_delta: dict
    composite_steps: List[dict]
    brief_text: str
    comms_result: dict
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

def _langgraph_fire(graph_id, input_data, wait=True, timeout_ms=30000):
    return _post(LANGGRAPH_BRIDGE_URL, {"verb": "fire_agent", "graph_id": graph_id, "input": input_data, "wait": wait, "timeout_ms": timeout_ms}, LANGGRAPH_WRITER_API_KEY, timeout=timeout_ms/1000 + 10)

def _supabase_get(path):
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(MMA_OS_SUPABASE_URL + "/rest/v1/" + path, headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": "Bearer " + SUPABASE_SERVICE_ROLE_KEY})
            return {"status": r.status_code, "body": r.json() if r.text else []}
    except Exception as exc:
        return {"status": 0, "body": {"error": str(exc)}}

def _supabase_insert(table, payload):
    if not SUPABASE_SERVICE_ROLE_KEY: return {"ok": False}
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.post(MMA_OS_SUPABASE_URL + "/rest/v1/" + table, headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": "Bearer " + SUPABASE_SERVICE_ROLE_KEY, "Content-Type": "application/json", "Prefer": "return=representation"}, json=payload)
            d = r.json()
            return {"ok": r.status_code < 300, "row": d[0] if isinstance(d, list) and d else None}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

def _supabase_patch(table, pk_field, pk_value, payload):
    if not SUPABASE_SERVICE_ROLE_KEY: return {"ok": False}
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.patch(MMA_OS_SUPABASE_URL + "/rest/v1/" + table + "?" + pk_field + "=eq." + pk_value, headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": "Bearer " + SUPABASE_SERVICE_ROLE_KEY, "Content-Type": "application/json"}, json=payload)
            return {"ok": r.status_code < 300}
    except Exception: return {"ok": False}

def start(state):
    state = {**state, "error": None, "call_started_at": time.time()}
    task = (state.get("task") or "daily_launchpad_brief").strip().lower()
    aliases = {
        "handle_signup": ["new_subscriber", "signup", "new_lp_signup", "launchpad_signup"],
        "handle_trial_end": ["trial_end", "trial_converting", "trial_to_paid"],
        "handle_upgrade_to_pro": ["upgrade", "upgrade_pro", "tier_upgrade"],
        "handle_cancel": ["cancel", "churn", "subscription_cancelled"],
        "daily_launchpad_brief": ["lp_brief", "launchpad_brief", "daily_brief"],
        "list_active_subscribers": ["subscribers", "active_subs", "list_subs"]
    }
    canonical = task
    for canon, alist in aliases.items():
        if task == canon or task in alist:
            canonical = canon
            break
    log_res = _supabase_insert("agent_calls", {"parent_dispatch_id": state.get("parent_dispatch_id"), "parent_agent": "launchpad_orchestrator", "child_agent": "composite", "child_tier": 1, "task": canonical, "input": state.get("payload", {}), "status": "pending"})
    call_id = log_res["row"]["id"] if log_res.get("ok") and log_res.get("row") else None
    return {**state, "task": canonical, "call_id": call_id}

def gather_lp_data(state):
    if state.get("task") != "daily_launchpad_brief":
        return state
    threshold_24h = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    enc = quote(threshold_24h)
    signups_res = _supabase_get("contact_state?tags=cs.{launchpad_standard,launchpad_pro}&created_at=gte." + enc + "&limit=50")
    signups = signups_res["body"] if isinstance(signups_res["body"], list) else []
    upgrades_res = _supabase_get("activities?activity_type=eq.tier_upgrade&occurred_at=gte." + enc + "&limit=50")
    upgrades = upgrades_res["body"] if isinstance(upgrades_res["body"], list) else []
    cancels_res = _supabase_get("activities?activity_type=eq.subscription_cancelled&occurred_at=gte." + enc + "&limit=50")
    cancels = cancels_res["body"] if isinstance(cancels_res["body"], list) else []
    btf_res = _supabase_get("contact_state?tags=cs.{bft_prospect,launchpad_qualified}&limit=20")
    btf = btf_res["body"] if isinstance(btf_res["body"], list) else []
    active_res = _supabase_get("contact_state?tags=cs.{launchpad_standard,launchpad_pro}&select=email,tags&limit=500")
    active = active_res["body"] if isinstance(active_res["body"], list) else []
    return {**state, "signups_today": signups, "upgrades_today": upgrades, "cancels_today": cancels, "btf_qualified": btf, "active_subscribers": active}

def compose_brief(state):
    if state.get("task") != "daily_launchpad_brief":
        return state
    signups = state.get("signups_today", []) or []
    upgrades = state.get("upgrades_today", []) or []
    cancels = state.get("cancels_today", []) or []
    btf = state.get("btf_qualified", []) or []
    active = state.get("active_subscribers", []) or []
    standard_count = sum(1 for a in active if "launchpad_standard" in (a.get("tags") or []))
    pro_count = sum(1 for a in active if "launchpad_pro" in (a.get("tags") or []))
    mrr = (standard_count * 19) + (pro_count * 47)
    net_subs = len(signups) - len(cancels)
    now_str = datetime.now(timezone.utc).strftime("%A %b %d %Y %H:%M UTC")
    overall_status = ICON_OK if net_subs >= 0 else ICON_WARN
    body_lines = []
    body_lines.append("*The Launch Pad - Daily Brief*")
    body_lines.append("_" + now_str + "_")
    body_lines.append("")
    body_lines.append("[" + overall_status + "] *MRR: " + DOLLAR + str(mrr) + "/mo*")
    body_lines.append("  - Standard (" + DOLLAR + "19/mo): " + str(standard_count))
    body_lines.append("  - Pro (" + DOLLAR + "47/mo): " + str(pro_count))
    body_lines.append("")
    body_lines.append("[" + ICON_NEW + "] *Last 24h:*")
    body_lines.append("  - New signups: " + str(len(signups)))
    body_lines.append("  - Upgrades to Pro: " + str(len(upgrades)))
    body_lines.append("  - Cancels: " + str(len(cancels)))
    body_lines.append("  - Net: " + str(net_subs))
    body_lines.append("")
    if signups:
        body_lines.append("*New signups today:*")
        for s in signups[:5]:
            email = s.get("email", "?")
            tier_label = "Pro" if "launchpad_pro" in (s.get("tags") or []) else "Standard"
            body_lines.append("  - " + email + " (" + tier_label + ")")
        body_lines.append("")
    if btf:
        body_lines.append("[" + ICON_MONEY + "] *BTF-qualified leads: " + str(len(btf)) + " (call them this week)*")
        for b in btf[:5]:
            body_lines.append("  - " + (b.get("email", "?")))
        body_lines.append("")
    if cancels:
        body_lines.append("[" + ICON_WARN + "] *Cancels to follow up:*")
        for c in cancels[:3]:
            body_lines.append("  - " + (c.get("email", "?")))
        body_lines.append("")
    if len(signups) == 0 and len(active) == 0:
        body_lines.append("[WARN] *No LaunchPad activity. Time to push ads or Workshop Wed promo.*")
    else:
        body_lines.append("[OK] *Action: contact BTF-qualified leads + investigate cancellations.*")
    brief = "\n".join(body_lines)
    return {**state, "brief_text": brief, "mrr_delta": {"mrr": mrr, "net_subs": net_subs}}

def deliver_brief(state):
    if state.get("task") != "daily_launchpad_brief":
        return state
    brief = state.get("brief_text", "(no brief generated)")
    res = _langgraph_fire("comms_orchestrator", {"task": "send_telegram", "payload": {"message": brief, "category": "Launch Pad Brief", "severity": "info"}, "parent_dispatch_id": state.get("parent_dispatch_id"), "source": "launchpad_orchestrator", "actor": "lp_brain"}, wait=True, timeout_ms=20000)
    return {**state, "comms_result": res}

def handle_specific(state):
    task = state.get("task")
    payload = state.get("payload") or {}
    if task == "list_active_subscribers":
        return state
    if task == "handle_signup":
        email = payload.get("email")
        if not email:
            return {**state, "error": "email required for handle_signup"}
        tier = payload.get("tier", "standard")
        tier_tag = "launchpad_" + tier
        steps = []
        s1 = _langgraph_fire("crm_orchestrator", {"task": "upsert_contact", "payload": {"email": email, "first_name": payload.get("first_name", ""), "last_name": payload.get("last_name", ""), "tags": [tier_tag, "bft_prospect", "lp_subscriber"]}, "parent_dispatch_id": state.get("parent_dispatch_id"), "source": "lp_signup"}, wait=True, timeout_ms=15000)
        steps.append({"step": "crm_upsert", "result": s1})
        s2 = _langgraph_fire("sales_department", {"task": "handle_new_lead", "payload": {"email": email, "first_name": payload.get("first_name", ""), "last_name": payload.get("last_name", ""), "source": "launchpad_" + tier, "persona": "tbd"}, "parent_dispatch_id": state.get("parent_dispatch_id"), "source": "lp_signup"}, wait=True, timeout_ms=15000)
        steps.append({"step": "sales_new_lead", "result": s2})
        price = "47" if tier == "pro" else "19"
        notify_msg = "NEW Launch Pad subscriber: " + email + " | Tier: " + tier.upper() + " | MRR: +" + DOLLAR + price + "/mo"
        s3 = _langgraph_fire("comms_orchestrator", {"task": "send_telegram", "payload": {"message": notify_msg, "category": "LP Signup", "severity": "success"}, "parent_dispatch_id": state.get("parent_dispatch_id"), "source": "lp_signup"}, wait=True, timeout_ms=15000)
        steps.append({"step": "notify", "result": s3})
        return {**state, "composite_steps": steps, "comms_result": s3}
    if task == "handle_trial_end":
        email = payload.get("email")
        converted = payload.get("converted", False)
        steps = []
        if converted:
            msg = "Trial converted to paid: " + (email or "?") + " (" + payload.get("tier", "standard") + ")"
            sev = "success"
        else:
            msg = "Trial ended without conversion: " + (email or "?") + ". Consider winback."
            sev = "warning"
            if email:
                s1 = _langgraph_fire("crm_orchestrator", {"task": "add_tag", "payload": {"email": email, "tag": "lp_trial_lost"}, "parent_dispatch_id": state.get("parent_dispatch_id"), "source": "lp_trial_end"}, wait=True, timeout_ms=15000)
                steps.append({"step": "tag_winback", "result": s1})
        s2 = _langgraph_fire("comms_orchestrator", {"task": "send_telegram", "payload": {"message": msg, "category": "LP Trial End", "severity": sev}, "parent_dispatch_id": state.get("parent_dispatch_id"), "source": "lp_trial_end"}, wait=True, timeout_ms=15000)
        steps.append({"step": "notify", "result": s2})
        return {**state, "composite_steps": steps, "comms_result": s2}
    if task == "handle_upgrade_to_pro":
        email = payload.get("email")
        steps = []
        if email:
            s1 = _langgraph_fire("crm_orchestrator", {"task": "add_tag", "payload": {"email": email, "tag": "launchpad_pro"}, "parent_dispatch_id": state.get("parent_dispatch_id"), "source": "lp_upgrade"}, wait=True, timeout_ms=15000)
            steps.append({"step": "tag_pro", "result": s1})
        msg = "UPGRADE: " + (email or "?") + " upgraded " + DOLLAR + "19 -> " + DOLLAR + "47 Pro. MRR: +" + DOLLAR + "28/mo"
        s2 = _langgraph_fire("comms_orchestrator", {"task": "send_telegram", "payload": {"message": msg, "category": "LP Upgrade", "severity": "success"}, "parent_dispatch_id": state.get("parent_dispatch_id"), "source": "lp_upgrade"}, wait=True, timeout_ms=15000)
        steps.append({"step": "notify", "result": s2})
        return {**state, "composite_steps": steps, "comms_result": s2}
    if task == "handle_cancel":
        email = payload.get("email")
        reason = payload.get("reason", "not specified")
        tier = payload.get("tier", "standard")
        price = "47" if tier == "pro" else "19"
        steps = []
        if email:
            s1 = _langgraph_fire("crm_orchestrator", {"task": "add_tag", "payload": {"email": email, "tag": "lp_cancelled"}, "parent_dispatch_id": state.get("parent_dispatch_id"), "source": "lp_cancel"}, wait=True, timeout_ms=15000)
            steps.append({"step": "tag_cancel", "result": s1})
        msg = "CANCEL: " + (email or "?") + " cancelled " + tier.upper() + ". MRR: -" + DOLLAR + price + "/mo. Reason: " + reason
        s2 = _langgraph_fire("comms_orchestrator", {"task": "send_telegram", "payload": {"message": msg, "category": "LP Cancel", "severity": "warning"}, "parent_dispatch_id": state.get("parent_dispatch_id"), "source": "lp_cancel"}, wait=True, timeout_ms=15000)
        steps.append({"step": "notify", "result": s2})
        return {**state, "composite_steps": steps, "comms_result": s2}
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
        return {**state, "summary": "LP Orch ERROR: " + str(state["error"])}
    cm = state.get("comms_result", {}) or {}
    cm_ok = cm.get("ok", False)
    delivered = ICON_OK if cm_ok else ICON_WARN
    if task == "daily_launchpad_brief":
        mrr = (state.get("mrr_delta", {}) or {}).get("mrr", 0)
        net = (state.get("mrr_delta", {}) or {}).get("net_subs", 0)
        return {**state, "summary": "LP." + task + ": " + DOLLAR + str(mrr) + "/mo MRR | net " + str(net) + " subs | brief [" + delivered + "]"}
    if task == "list_active_subscribers":
        n = len(state.get("active_subscribers", []) or [])
        return {**state, "summary": "LP." + task + ": " + str(n) + " active subscribers"}
    if task in ("handle_signup", "handle_trial_end", "handle_upgrade_to_pro", "handle_cancel"):
        steps_n = len(state.get("composite_steps", []) or [])
        return {**state, "summary": "LP." + task + ": " + str(steps_n) + " steps complete | telegram [" + delivered + "]"}
    return {**state, "summary": "LP." + str(task) + ": complete"}

def build_graph():
    g = StateGraph(LPState)
    for n, f in [("start", start), ("gather_lp_data", gather_lp_data), ("compose_brief", compose_brief), ("deliver_brief", deliver_brief), ("handle_specific", handle_specific), ("log_complete", log_complete), ("summarize", summarize)]:
        g.add_node(n, f)
    g.add_edge(START, "start")
    g.add_edge("start", "gather_lp_data")
    g.add_edge("gather_lp_data", "compose_brief")
    g.add_edge("compose_brief", "deliver_brief")
    g.add_edge("deliver_brief", "handle_specific")
    g.add_edge("handle_specific", "log_complete")
    g.add_edge("log_complete", "summarize")
    g.add_edge("summarize", END)
    return g.compile()

graph = build_graph()
