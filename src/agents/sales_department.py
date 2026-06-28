"""
Sales Department v2 Ã¢ÂÂ LangGraph (Tier -1)
Department Head composing crm + revenue + comms for BUILD-to-FUND sales operations.

Doctrine ÃÂ§99 (BTF Canon) compliance Ã¢ÂÂ owns the BTF sales motion end-to-end.

BTF-specific tasks (Stream #2):
  - log_btf_close          Record a new closed BTF deal -> btf_deals table + notify
  - get_btf_pipeline       Query active BTF deals + phase distribution -> Telegram or return
  - advance_btf_phase      Move a deal pre_build -> build -> stack -> fund -> funded
  - record_btf_payment     Add a payment installment (Split/Get-Started plans)

Existing tasks:
  - daily_sales_brief      Pipeline + hot leads + recent closes + BTF pulse -> Telegram
  - list_active_deals
  - get_pipeline_health
  - handle_new_lead        composite: crm.upsert + tag + notify
  - escalate_hot_lead

Doctrine ÃÂ§97 compliance: no backslashes in f-string expressions. DOLLAR pattern for currency.
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
ICON_BTF = "BTF"
DOLLAR = "$"

MMA_OS_FUNCTIONS_BASE = os.environ.get("MMA_OS_FUNCTIONS_BASE", "https://slcqeiqcrhepicqxqjng.supabase.co/functions/v1")
MMA_OS_SUPABASE_URL = os.environ.get("MMA_OS_SUPABASE_URL", "https://slcqeiqcrhepicqxqjng.supabase.co")
LANGGRAPH_BRIDGE_URL = MMA_OS_FUNCTIONS_BASE + "/langgraph-bridge"
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
LANGGRAPH_WRITER_API_KEY = os.environ.get("LANGGRAPH_WRITER_API_KEY", "")

# BTF phase progression rules per Doctrine ÃÂ§99
BTF_PHASES = ["pre_build", "build", "stack", "fund", "funded"]
BTF_PHASE_NEXT = {"pre_build": "build", "build": "stack", "stack": "fund", "fund": "funded", "funded": "funded"}

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
    btf_deals: List[dict]
    btf_phase_counts: dict
    btf_mrr_potential: int
    pipeline_health: dict
    composite_steps: List[dict]
    btf_deal_result: dict
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

def _sb_get(path):
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(MMA_OS_SUPABASE_URL + "/rest/v1/" + path, headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": "Bearer " + SUPABASE_SERVICE_ROLE_KEY})
            return {"status": r.status_code, "body": r.json() if r.text else []}
    except Exception as exc:
        return {"status": 0, "body": {"error": str(exc)}}

def _sb_insert(table, payload, prefer_return=True):
    if not SUPABASE_SERVICE_ROLE_KEY: return {"ok": False}
    try:
        with httpx.Client(timeout=10.0) as client:
            headers = {"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": "Bearer " + SUPABASE_SERVICE_ROLE_KEY, "Content-Type": "application/json"}
            if prefer_return: headers["Prefer"] = "return=representation"
            r = client.post(MMA_OS_SUPABASE_URL + "/rest/v1/" + table, headers=headers, json=payload)
            d = r.json() if r.text else None
            return {"ok": r.status_code < 300, "row": d[0] if isinstance(d, list) and d else d, "status": r.status_code}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

def _sb_patch(table, pk_field, pk_value, payload, prefer_return=False):
    if not SUPABASE_SERVICE_ROLE_KEY: return {"ok": False}
    try:
        with httpx.Client(timeout=10.0) as client:
            headers = {"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": "Bearer " + SUPABASE_SERVICE_ROLE_KEY, "Content-Type": "application/json"}
            if prefer_return: headers["Prefer"] = "return=representation"
            r = client.patch(MMA_OS_SUPABASE_URL + "/rest/v1/" + table + "?" + pk_field + "=eq." + pk_value, headers=headers, json=payload)
            return {"ok": r.status_code < 300, "status": r.status_code}
    except Exception: return {"ok": False}

def _log_touchpoint(btf_deal_id, layer, touchpoint_type, direction="outbound", metadata=None):
    """Doctrine Â§103: log every customer touchpoint to btf_touchpoints audit table."""
    if not btf_deal_id: return {"ok": False, "skip_reason": "no_deal_id"}
    payload = {
        "btf_deal_id": btf_deal_id,
        "layer": layer,
        "touchpoint_type": touchpoint_type,
        "direction": direction,
        "metadata": metadata or {}
    }
    return _sb_insert("btf_touchpoints", payload, prefer_return=False)

def start(state):
    state = {**state, "error": None, "call_started_at": time.time()}
    task = (state.get("task") or "daily_sales_brief").strip().lower()
    aliases = {
        "daily_sales_brief": ["sales_brief", "pipeline_brief", "deal_brief"],
        "list_active_deals": ["deals", "active_deals", "opportunities"],
        "get_pipeline_health": ["pipeline_health", "pipeline", "deal_velocity"],
        "handle_new_lead": ["new_lead", "lead", "inbound"],
        "escalate_hot_lead": ["hot_lead", "escalate"],
        "log_btf_close": ["btf_close", "close_btf", "new_btf_deal"],
        "get_btf_pipeline": ["btf_pipeline", "btf_deals", "btf_status"],
        "advance_btf_phase": ["btf_advance", "next_phase", "phase_up"],
        "record_btf_payment": ["btf_payment", "record_payment", "payment_installment"],
        "send_workspace_invite": ["invite_workspace", "send_btf_invite", "btf_invite"]
    }
    canonical = task
    for canon, alist in aliases.items():
        if task == canon or task in alist:
            canonical = canon
            break
    log_res = _sb_insert("agent_calls", {"parent_dispatch_id": state.get("parent_dispatch_id"), "parent_agent": "sales_department", "child_agent": "composite", "child_tier": 1, "task": canonical, "input": state.get("payload", {}), "status": "pending"})
    call_id = log_res["row"]["id"] if log_res.get("ok") and log_res.get("row") else None
    return {**state, "task": canonical, "call_id": call_id}

def gather_sales_data(state):
    if state.get("task") != "daily_sales_brief":
        return state
    threshold_7d = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    enc = quote(threshold_7d)
    deals_res = _sb_get("contact_state?lifecycle_stage=in.(opportunity,active_deal,negotiating)&limit=20")
    deals = deals_res["body"] if isinstance(deals_res["body"], list) else []
    hot_res = _sb_get("contact_state?lifecycle_stage=eq.lead&created_at=gte." + enc + "&limit=20")
    hot = hot_res["body"] if isinstance(hot_res["body"], list) else []
    closes_res = _sb_get("enrollments?enrolled_at=gte." + enc + "&limit=20")
    closes = closes_res["body"] if isinstance(closes_res["body"], list) else []
    # BTF deals (active, all phases)
    btf_res = _sb_get("btf_deals?status=eq.active&order=closed_at.desc&limit=50")
    btf = btf_res["body"] if isinstance(btf_res["body"], list) else []
    # Phase counts
    phase_counts = {p: 0 for p in BTF_PHASES}
    for d in btf:
        ph = d.get("current_phase", "pre_build")
        if ph in phase_counts: phase_counts[ph] += 1
    btf_mrr = sum(d.get("payment_remaining_cents", 0) for d in btf if d.get("payment_plan") in ("split", "get_started"))
    return {**state, "active_deals": deals, "hot_leads": hot, "recent_closes": closes, "btf_deals": btf, "btf_phase_counts": phase_counts, "btf_mrr_potential": btf_mrr}

def get_pipeline_data(state):
    if state.get("task") not in ("get_pipeline_health", "get_btf_pipeline"):
        return state
    if state.get("task") == "get_btf_pipeline":
        btf_res = _sb_get("btf_deals?status=eq.active&order=phase_started_at.desc&limit=100")
        btf = btf_res["body"] if isinstance(btf_res["body"], list) else []
        phase_counts = {p: 0 for p in BTF_PHASES}
        for d in btf:
            ph = d.get("current_phase", "pre_build")
            if ph in phase_counts: phase_counts[ph] += 1
        btf_mrr = sum(d.get("payment_remaining_cents", 0) for d in btf if d.get("payment_plan") in ("split", "get_started"))
        return {**state, "btf_deals": btf, "btf_phase_counts": phase_counts, "btf_mrr_potential": btf_mrr}
    deals_res = _sb_get("contact_state?lifecycle_stage=in.(opportunity,active_deal,negotiating)&limit=100")
    deals = deals_res["body"] if isinstance(deals_res["body"], list) else []
    threshold_30d = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    stuck_count = sum(1 for d in deals if d.get("updated_at", "") < threshold_30d)
    return {**state, "active_deals": deals, "pipeline_health": {"total_deals": len(deals), "stuck_30d": stuck_count, "fresh_deals": len(deals) - stuck_count}}

def compose_brief(state):
    if state.get("task") != "daily_sales_brief":
        return state
    deals = state.get("active_deals", []) or []
    hot = state.get("hot_leads", []) or []
    closes = state.get("recent_closes", []) or []
    btf = state.get("btf_deals", []) or []
    phase_counts = state.get("btf_phase_counts", {}) or {}
    btf_mrr = state.get("btf_mrr_potential", 0) // 100
    now_str = datetime.now(timezone.utc).strftime("%A %b %d %Y %H:%M UTC")
    overall_status = ICON_OK if (len(closes) > 0 or len(deals) > 0 or len(btf) > 0) else ICON_WARN
    lines_out = []
    lines_out.append("*Sales Department v2 - Daily Brief*")
    lines_out.append("_" + now_str + "_")
    lines_out.append("")
    lines_out.append("[" + overall_status + "] *Pipeline Pulse*")
    lines_out.append("  - Active deals (other): " + str(len(deals)))
    lines_out.append("  - Hot leads (7d): " + str(len(hot)))
    lines_out.append("  - Closes (7d): " + str(len(closes)))
    lines_out.append("")
    lines_out.append("[" + ICON_BTF + "] *BUILD-to-FUND Pulse*")
    lines_out.append("  - Active BTF clients: " + str(len(btf)))
    for ph in BTF_PHASES:
        n = phase_counts.get(ph, 0)
        if n > 0:
            lines_out.append("    - " + ph + ": " + str(n))
    if btf_mrr > 0:
        lines_out.append("  - Outstanding installments (Split/Get-Started): " + DOLLAR + str(btf_mrr))
    lines_out.append("")
    if hot:
        lines_out.append("*Top hot leads (call today):*")
        for h in hot[:5]:
            lines_out.append("  - " + (h.get("email", "?")) + " (stage: " + (h.get("lifecycle_stage", "?")) + ")")
        lines_out.append("")
    if btf:
        lines_out.append("*BTF clients in flight:*")
        for d in btf[:5]:
            name = d.get("full_legal_name") or d.get("contact_email", "?")
            ph = d.get("current_phase", "?")
            lines_out.append("  - " + name + " | phase: " + ph)
        lines_out.append("")
    if len(closes) > 0:
        lines_out.append("[" + ICON_MONEY + "] *Recent wins: " + str(len(closes)) + " new members this week*")
        lines_out.append("")
    if len(deals) == 0 and len(hot) == 0 and len(btf) == 0:
        lines_out.append("[WARN] *Empty pipeline. Prospect or run ads.*")
    else:
        lines_out.append("[OK] *Action: prioritize hot leads + advance BTF clients in build/stack phases.*")
    return {**state, "brief_text": "\n".join(lines_out)}

def deliver_brief(state):
    if state.get("task") != "daily_sales_brief":
        return state
    brief = state.get("brief_text", "(no brief)")
    res = _langgraph_fire("comms_orchestrator", {"task": "send_telegram", "payload": {"message": brief, "category": "Sales Brief", "severity": "info"}, "parent_dispatch_id": state.get("parent_dispatch_id"), "source": "sales_department", "actor": "sales_dept_head"}, wait=True, timeout_ms=20000)
    return {**state, "comms_result": res}

def handle_specific(state):
    task = state.get("task")
    payload = state.get("payload") or {}
    if task in ("list_active_deals", "get_pipeline_health", "get_btf_pipeline"):
        return state
    if task == "handle_new_lead":
        # sales_dept v4 - smart qualification per Paige bridge contract (docs/PAIGE-MMA-OS-BRIDGE-CONTRACT.md)
        email = payload.get("email")
        if not email: return {**state, "error": "email required"}
        first_name = payload.get("first_name", "") or ""
        last_name = payload.get("last_name", "") or ""
        source = payload.get("source", "unknown") or "unknown"
        persona = (payload.get("persona") or "").strip()
        try: funding_goal_cents = int(payload.get("funding_goal_cents") or 0)
        except Exception: funding_goal_cents = 0
        has_entity = bool(payload.get("has_entity", False))
        entity_state = payload.get("entity_state", "") or ""
        # Qualification per Doctrine S100 (Revenue Ladder)
        if funding_goal_cents >= 5000000 and has_entity:
            qualification = "BTF_QUALIFIED"
            qual_tag = "btf_qualified_lead"
            severity = "warning"
        elif funding_goal_cents > 0:
            qualification = "LAUNCHPAD"
            qual_tag = "launchpad_lead"
            severity = "info"
        else:
            qualification = "EXPLORER"
            qual_tag = "explorer_lead"
            severity = "info"
        tags = ["new_lead", "paige_signup", qual_tag]
        if persona: tags.append("persona:" + persona)
        steps = []
        # 1) CRM upsert (fires Paige mirror per Doctrine S82)
        s1 = _langgraph_fire("crm_orchestrator", {"task": "upsert_contact", "payload": {"email": email, "first_name": first_name, "last_name": last_name, "tags": tags}, "parent_dispatch_id": state.get("parent_dispatch_id"), "source": "sales_new_lead"}, wait=True, timeout_ms=15000)
        steps.append({"step": "upsert_contact", "result": s1})
        # 2) Smart Telegram notify based on qualification
        name_display = (first_name + " " + last_name).strip() or email
        goal_display = (DOLLAR + str(funding_goal_cents // 100)) if funding_goal_cents > 0 else "(no goal)"
        if qualification == "BTF_QUALIFIED":
            msg = "[HOT] BTF-QUALIFIED LEAD: " + name_display + " | goal: " + goal_display + " | entity: " + (entity_state or "yes") + " | persona: " + (persona or "n/a") + " | CALL ASAP"
        elif qualification == "LAUNCHPAD":
            msg = "[NEW] LaunchPad lead: " + name_display + " | goal: " + goal_display + " | persona: " + (persona or "n/a") + " | source: " + source
        else:
            msg = "[NEW] Explorer lead: " + name_display + " | source: " + source + " | persona: " + (persona or "n/a")
        s2 = _langgraph_fire("comms_orchestrator", {"task": "send_telegram", "payload": {"message": msg, "category": "New Lead - " + qualification, "severity": severity}, "parent_dispatch_id": state.get("parent_dispatch_id"), "source": "sales_new_lead"}, wait=True, timeout_ms=15000)
        steps.append({"step": "notify", "result": s2})
        return {**state, "composite_steps": steps, "comms_result": s2}
    if task == "escalate_hot_lead":
        email = payload.get("email", "unknown")
        signal = payload.get("signal", "high engagement detected")
        msg = "HOT LEAD ALERT: " + email + " - " + signal + ". Call within 1hr."
        res = _langgraph_fire("comms_orchestrator", {"task": "send_admin_alert", "payload": {"message": msg, "severity": "warning", "category": "HOT LEAD"}, "parent_dispatch_id": state.get("parent_dispatch_id"), "source": "sales_department"}, wait=True, timeout_ms=15000)
        return {**state, "comms_result": res}
    if task == "log_btf_close":
        # Required: contact_email, full_legal_name, payment_plan, payment_collected_cents
        email = payload.get("contact_email") or payload.get("email")
        if not email: return {**state, "error": "contact_email required for log_btf_close"}
        deal = {
            "contact_email": email,
            "full_legal_name": payload.get("full_legal_name"),
            "preferred_name": payload.get("preferred_name"),
            "persona": payload.get("persona", "tbd"),
            "source": payload.get("source", "unknown"),
            "payment_plan": payload.get("payment_plan", "pay_in_full"),
            "payment_total_cents": int(payload.get("payment_total_cents", 499700)),
            "payment_collected_cents": int(payload.get("payment_collected_cents", 0)),
            "first_contact_at": payload.get("first_contact_at"),
            "enrollment_call_at": payload.get("enrollment_call_at"),
            "closed_at": payload.get("closed_at") or datetime.now(timezone.utc).isoformat(),
            "first_payment_at": payload.get("first_payment_at"),
            "current_phase": "pre_build",
            "funding_goal_cents": payload.get("funding_goal_cents"),
            "assigned_coach": payload.get("assigned_coach"),
            "delivery_notes": payload.get("delivery_notes"),
            "ghl_opportunity_id": payload.get("ghl_opportunity_id"),
            "status": "active"
        }
        res = _sb_insert("btf_deals", deal)
        if not res.get("ok"):
            return {**state, "btf_deal_result": res, "error": "btf insert failed"}
        row = res.get("row", {})
        msg = "[" + ICON_BTF + "] NEW BTF CLOSE: " + (deal.get("full_legal_name") or email) + " | " + deal.get("payment_plan", "?") + " | source: " + deal.get("source", "?")
        notify = _langgraph_fire("comms_orchestrator", {"task": "send_telegram", "payload": {"message": msg, "category": "BTF Close", "severity": "success"}, "parent_dispatch_id": state.get("parent_dispatch_id"), "source": "log_btf_close"}, wait=True, timeout_ms=15000)
        _log_touchpoint(row.get("id") if isinstance(row, dict) else None, "telegram", "new_close", metadata={"payment_plan": deal.get("payment_plan"), "source": deal.get("source")})
        return {**state, "btf_deal_result": res, "comms_result": notify}
    if task == "advance_btf_phase":
        deal_id = payload.get("deal_id") or payload.get("id")
        if not deal_id: return {**state, "error": "deal_id required"}
        # Get current phase
        cur_res = _sb_get("btf_deals?id=eq." + deal_id + "&select=current_phase,full_legal_name,contact_email")
        if not cur_res["body"]: return {**state, "error": "deal not found"}
        cur = cur_res["body"][0]
        cur_phase = cur.get("current_phase", "pre_build")
        next_phase = BTF_PHASE_NEXT.get(cur_phase, cur_phase)
        if next_phase == cur_phase:
            return {**state, "error": "already at final phase or unknown phase"}
        patch_res = _sb_patch("btf_deals", "id", deal_id, {"current_phase": next_phase, "phase_started_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat()})
        name = cur.get("full_legal_name") or cur.get("contact_email", "?")
        msg = "[" + ICON_BTF + "] PHASE ADVANCE: " + name + " moved " + cur_phase + " -> " + next_phase
        notify = _langgraph_fire("comms_orchestrator", {"task": "send_telegram", "payload": {"message": msg, "category": "BTF Phase", "severity": "success"}, "parent_dispatch_id": state.get("parent_dispatch_id"), "source": "advance_btf_phase"}, wait=True, timeout_ms=15000)
        _log_touchpoint(deal_id, "telegram", "phase_advance", metadata={"old_phase": cur_phase, "new_phase": next_phase})
        return {**state, "btf_deal_result": patch_res, "comms_result": notify}
    if task == "record_btf_payment":
        deal_id = payload.get("deal_id") or payload.get("id")
        amount_cents = int(payload.get("amount_cents", 0))
        if not deal_id or amount_cents <= 0:
            return {**state, "error": "deal_id and amount_cents required"}
        cur_res = _sb_get("btf_deals?id=eq." + deal_id + "&select=payment_collected_cents,payment_total_cents,full_legal_name,contact_email")
        if not cur_res["body"]: return {**state, "error": "deal not found"}
        cur = cur_res["body"][0]
        new_collected = int(cur.get("payment_collected_cents", 0)) + amount_cents
        total = int(cur.get("payment_total_cents", 499700))
        patch = {"payment_collected_cents": new_collected, "updated_at": datetime.now(timezone.utc).isoformat()}
        if new_collected >= total: patch["status"] = "active"  # fully paid still active in delivery
        patch_res = _sb_patch("btf_deals", "id", deal_id, patch)
        name = cur.get("full_legal_name") or cur.get("contact_email", "?")
        remaining = max(0, total - new_collected)
        msg = "[" + ICON_MONEY + "] BTF PAYMENT: " + name + " +" + DOLLAR + str(amount_cents // 100) + " | collected " + DOLLAR + str(new_collected // 100) + "/" + DOLLAR + str(total // 100) + " | remaining " + DOLLAR + str(remaining // 100)
        notify = _langgraph_fire("comms_orchestrator", {"task": "send_telegram", "payload": {"message": msg, "category": "BTF Payment", "severity": "success"}, "parent_dispatch_id": state.get("parent_dispatch_id"), "source": "record_btf_payment"}, wait=True, timeout_ms=15000)
        _log_touchpoint(deal_id, "telegram", "payment_received", metadata={"amount_cents": amount_cents, "collected_total_cents": new_collected})
        return {**state, "btf_deal_result": patch_res, "comms_result": notify}
    if task == "send_workspace_invite":
        deal_id = payload.get("deal_id") or payload.get("id")
        if not deal_id: return {**state, "error": "deal_id required"}
        cur_res = _sb_get("btf_deals?id=eq." + deal_id + "&select=contact_email,full_legal_name,preferred_name,paige_client_id")
        if not cur_res["body"]: return {**state, "error": "deal not found"}
        cur = cur_res["body"][0]
        email = cur.get("contact_email")
        name = cur.get("preferred_name") or cur.get("full_legal_name") or "Client"
        # Paige invite endpoint (set via env var when Paige ships Day 3)
        paige_invite_url = os.environ.get("PAIGE_BTF_INVITE_URL", "")
        invite_result = {"ok": False, "skip_reason": "PAIGE_BTF_INVITE_URL not configured (Paige Day 3 pending)"}
        if paige_invite_url:
            invite_result = _post(paige_invite_url, {"contact_email": email, "full_name": cur.get("full_legal_name"), "preferred_name": cur.get("preferred_name"), "btf_deal_id": deal_id, "paige_client_id": cur.get("paige_client_id")}, os.environ.get("PAIGE_BTF_INVITE_KEY", ""), timeout=20.0)
        # Notify Antonio
        notify_msg = "[" + ICON_BTF + "] WORKSPACE INVITE: " + name + " (" + email + ") | status: " + ("sent" if invite_result.get("ok") else "STUB " + str(invite_result.get("skip_reason", "error")))
        notify = _langgraph_fire("comms_orchestrator", {"task": "send_telegram", "payload": {"message": notify_msg, "category": "BTF Invite", "severity": "info" if invite_result.get("ok") else "warning"}, "parent_dispatch_id": state.get("parent_dispatch_id"), "source": "send_workspace_invite"}, wait=True, timeout_ms=15000)
        _log_touchpoint(deal_id, "email", "workspace_invite", metadata={"recipient": email, "invite_status": invite_result.get("ok", False), "endpoint_configured": bool(paige_invite_url)})
        return {**state, "btf_deal_result": invite_result, "comms_result": notify}
    return state

def log_complete(state):
    call_id = state.get("call_id")
    if not call_id: return state
    duration_ms = int((time.time() - (state.get("call_started_at") or time.time())) * 1000)
    result = {"task": state.get("task"), "comms_ok": (state.get("comms_result", {}) or {}).get("ok"), "btf_deal_ok": (state.get("btf_deal_result", {}) or {}).get("ok")}
    _sb_patch("agent_calls", "id", call_id, {"output": result, "status": "success", "duration_ms": duration_ms})
    return state

def summarize(state):
    task = state.get("task")
    if state.get("error"):
        return {**state, "summary": "Sales Dept ERROR: " + str(state["error"])}
    cm = state.get("comms_result", {}) or {}
    delivered = ICON_OK if cm.get("ok") else ICON_WARN
    if task == "daily_sales_brief":
        return {**state, "summary": "Sales." + task + ": " + str(len(state.get("active_deals", []) or [])) + " deals, " + str(len(state.get("hot_leads", []) or [])) + " hot, " + str(len(state.get("btf_deals", []) or [])) + " BTF | brief [" + delivered + "]"}
    if task == "get_btf_pipeline":
        pc = state.get("btf_phase_counts", {}) or {}
        return {**state, "summary": "Sales." + task + ": " + str(sum(pc.values())) + " active BTF deals | phases " + str(pc)}
    if task == "log_btf_close":
        dr = state.get("btf_deal_result", {}) or {}
        return {**state, "summary": "Sales." + task + ": deal " + ("INSERTED" if dr.get("ok") else "FAILED") + " | telegram [" + delivered + "]"}
    if task == "advance_btf_phase":
        return {**state, "summary": "Sales." + task + ": phase advanced | telegram [" + delivered + "]"}
    if task == "record_btf_payment":
        return {**state, "summary": "Sales." + task + ": payment recorded | telegram [" + delivered + "]"}
    if task == "send_workspace_invite":
        ir = state.get("btf_deal_result", {}) or {}
        return {**state, "summary": "Sales." + task + ": invite " + ("SENT" if ir.get("ok") else "STUB") + " | telegram [" + delivered + "]"}
    if task in ("handle_new_lead", "escalate_hot_lead"):
        steps_n = len(state.get("composite_steps", []) or [])
        return {**state, "summary": "Sales." + task + ": " + str(steps_n) + " steps | telegram [" + delivered + "]"}
    return {**state, "summary": "Sales." + str(task) + ": complete"}

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
