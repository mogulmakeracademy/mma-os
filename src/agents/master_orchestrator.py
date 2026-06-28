"""
Master Orchestrator — LangGraph v2.4
v2.4: ALL 7 domains route to LangGraph orchestrators. Zero stubs remaining.
"""
from __future__ import annotations
import os, json, time
from typing import TypedDict, Optional
import httpx
from langgraph.graph import StateGraph, START, END

MMA_OS_FUNCTIONS_BASE = os.environ.get("MMA_OS_FUNCTIONS_BASE", "https://slcqeiqcrhepicqxqjng.supabase.co/functions/v1")
MMA_OS_SUPABASE_URL = os.environ.get("MMA_OS_SUPABASE_URL", "https://slcqeiqcrhepicqxqjng.supabase.co")
LANGGRAPH_BRIDGE_URL = f"{MMA_OS_FUNCTIONS_BASE}/langgraph-bridge"
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
LANGGRAPH_WRITER_API_KEY = os.environ.get("LANGGRAPH_WRITER_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

DOMAIN_REGISTRY = {
    "comms":      {"type": "langgraph", "graph_id": "comms_orchestrator"},
    "revenue":    {"type": "langgraph", "graph_id": "revenue_orchestrator"},
    "crm":        {"type": "langgraph", "graph_id": "crm_orchestrator"},
    "monitoring": {"type": "langgraph", "graph_id": "monitoring_orchestrator"},
    "lifecycle":  {"type": "langgraph", "graph_id": "lifecycle_orchestrator"},
    "content":    {"type": "langgraph", "graph_id": "content_orchestrator"},
    "support":    {"type": "langgraph", "graph_id": "support_orchestrator"},
}

class MasterState(TypedDict, total=False):
    source: str
    actor: str
    text: str
    context: dict
    intent_hint: Optional[str]
    resolved_intent: dict
    dispatch_id: str
    dispatch_started_at: float
    dispatch_result: dict
    summary: str
    error: Optional[str]

def _post(url, body, bearer, timeout=30.0):
    if not bearer: return {"ok": False, "error": "missing bearer"}
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.post(url, headers={"Authorization": f"Bearer {bearer}", "Content-Type": "application/json"}, json=body)
            try: return r.json()
            except Exception: return {"ok": False, "error": "non-json"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

def _langgraph_fire(graph_id, input_data, wait=True, timeout_ms=60000):
    return _post(LANGGRAPH_BRIDGE_URL, {"verb": "fire_agent", "graph_id": graph_id, "input": input_data, "wait": wait, "timeout_ms": timeout_ms}, LANGGRAPH_WRITER_API_KEY, timeout=timeout_ms/1000 + 10)

def _supabase_insert(table, payload):
    if not SUPABASE_SERVICE_ROLE_KEY: return {"ok": False}
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.post(f"{MMA_OS_SUPABASE_URL}/rest/v1/{table}", headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}", "Content-Type": "application/json", "Prefer": "return=representation"}, json=payload)
            data = r.json()
            return {"ok": r.status_code < 300, "row": data[0] if isinstance(data, list) and data else None}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

def _supabase_patch(table, pk_field, pk_value, payload):
    if not SUPABASE_SERVICE_ROLE_KEY: return {"ok": False}
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.patch(f"{MMA_OS_SUPABASE_URL}/rest/v1/{table}?{pk_field}=eq.{pk_value}", headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}", "Content-Type": "application/json"}, json=payload)
            return {"ok": r.status_code < 300}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

def _heuristic_intent(text):
    lower = text.lower()
    if any(k in lower for k in ("campaign", "engine v4", "cohort", "skool 45", "kill switch", "pause campaign", "fire campaign")):
        return {"domain": "revenue", "action": "unknown", "payload": {"raw": text}, "confidence": 0.5, "reasoning": "heuristic revenue"}
    if any(k in lower for k in ("system health", "qc check", "audit", "drift", "recent alerts", "dispatches")):
        return {"domain": "monitoring", "action": "unknown", "payload": {"raw": text}, "confidence": 0.5, "reasoning": "heuristic monitoring"}
    if any(k in lower for k in ("tag", "tier badge", "add note", "update contact", "ghl contact", "search contact")):
        return {"domain": "crm", "action": "unknown", "payload": {"raw": text}, "confidence": 0.5, "reasoning": "heuristic crm"}
    if any(k in lower for k in ("tier move", "upgrade to premium", "downgrade", "move from")):
        return {"domain": "lifecycle", "action": "unknown", "payload": {"raw": text}, "confidence": 0.5, "reasoning": "heuristic lifecycle"}
    if any(k in lower for k in ("mogul brief", "coffee hour", "editorial", "weekly market", "draft content")):
        return {"domain": "content", "action": "unknown", "payload": {"raw": text}, "confidence": 0.5, "reasoning": "heuristic content"}
    if any(k in lower for k in ("support ticket", "customer support", "escalate", "triage")):
        return {"domain": "support", "action": "unknown", "payload": {"raw": text}, "confidence": 0.5, "reasoning": "heuristic support"}
    if any(k in lower for k in ("telegram", "alert", "notify", "send a", "email antonio", "sms antonio", "message me")):
        return {"domain": "comms", "action": "notify_admin", "payload": {"message": text}, "confidence": 0.5, "reasoning": "heuristic comms"}
    return {"domain": "unknown", "action": "unknown", "payload": {}, "confidence": 0.0, "reasoning": "heuristic miss"}

def _claude_resolve_intent(text, source, context, hint):
    if not ANTHROPIC_API_KEY:
        h = _heuristic_intent(text); h["reasoning"] = "no Anthropic key, " + h["reasoning"]; return h
    system_prompt = (
        "You are the Master Orchestrator of MMA OS. Classify the request into a domain and action.\n\n"
        "DOMAINS:\n"
        "- comms: Send messages (Telegram, Email, SMS, admin alerts)\n"
        "- crm: GHL contact-level ops (tags, notes, contact fields). NOT campaigns.\n"
        "- lifecycle: Tier transitions, campaign enrollment changes, lifecycle stage moves\n"
        "- revenue: Campaign fires/kills/pauses, Engine v4.5 controls, cohort operations\n"
        "- monitoring: System health, agent diagnostics, recent dispatches/alerts, audits\n"
        "- content: Editorial pipeline (Mogul Brief, Coffee Hour, Weekly Market Watch)\n"
        "- support: Customer support tickets, escalations\n"
        "- unknown: Out of scope\n\n"
        "Examples:\n"
        "'Send Antonio a Telegram' = comms.send_telegram\n"
        "'Tag Tashia VIP' = crm.add_tag\n"
        "'Run Skool campaign' = revenue.fire_campaign\n"
        "'Move Tashia to Premium' = lifecycle.tier_change\n"
        "'Show system health' = monitoring.get_system_health_summary\n"
        "'List editorial drafts' = content.list_editorial_drafts\n"
        "'Triage this ticket' = support.triage_ticket\n\n"
        'Return ONLY JSON: { "domain": str, "action": str, "payload": dict, "confidence": 0..1, "reasoning": str }'
    )
    hint_str = f"\nHint: {hint}" if hint else ""
    user_msg = f"Source: {source}\nContext: {json.dumps(context)[:500]}{hint_str}\n\nRequest:\n{text}"
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post("https://api.anthropic.com/v1/messages", headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}, json={"model": ANTHROPIC_MODEL, "max_tokens": 800, "system": system_prompt, "messages": [{"role": "user", "content": user_msg}]})
            try: data = resp.json()
            except Exception:
                h = _heuristic_intent(text); h["reasoning"] = f"LLM non-json; " + h["reasoning"]; return h
            content_blocks = data.get("content", [])
            raw = "".join(b.get("text", "") for b in content_blocks if b.get("type") == "text").strip()
            if not raw:
                h = _heuristic_intent(text); h["reasoning"] = f"LLM empty; " + h["reasoning"]; return h
            if raw.startswith("\u0060\u0060\u0060"): raw = raw.split("\n", 1)[-1]
            if raw.endswith("\u0060\u0060\u0060"): raw = raw.rsplit("\u0060\u0060\u0060", 1)[0]
            try: return json.loads(raw)
            except Exception:
                h = _heuristic_intent(text); h["reasoning"] = f"LLM unparseable: {raw[:100]}; " + h["reasoning"]; return h
    except Exception as exc:
        h = _heuristic_intent(text); h["reasoning"] = f"LLM exception: {exc}; " + h["reasoning"]; return h

def resolve_intent(state):
    state = {**state, "error": None, "dispatch_started_at": time.time()}
    text = (state.get("text") or "").strip()
    if not text:
        return {**state, "error": "no text provided", "resolved_intent": {"domain": "unknown", "action": "unknown", "payload": {}, "confidence": 0.0, "reasoning": "empty input"}}
    return {**state, "resolved_intent": _claude_resolve_intent(text=text, source=state.get("source", "unknown"), context=state.get("context", {}), hint=state.get("intent_hint"))}

def log_dispatch_start(state):
    intent = state.get("resolved_intent", {}) or {}
    res = _supabase_insert("agent_dispatches", {"source": state.get("source", "unknown"), "actor": state.get("actor"), "raw_text": (state.get("text") or "")[:2000], "resolved_intent": intent, "dispatch_target": intent.get("domain", "unknown"), "status": "pending"})
    if res.get("ok") and res.get("row"):
        return {**state, "dispatch_id": res["row"]["id"]}
    return state

def dispatch_to_domain(state):
    if state.get("error"): return state
    intent = state.get("resolved_intent", {}) or {}
    domain = intent.get("domain", "unknown")
    entry = DOMAIN_REGISTRY.get(domain)
    if not entry:
        return {**state, "dispatch_result": {"ok": False, "error": f"unknown_domain:{domain}"}}
    if entry["type"] == "langgraph":
        result = _langgraph_fire(graph_id=entry["graph_id"], input_data={"task": intent.get("action", "unknown"), "payload": intent.get("payload", {}), "parent_dispatch_id": state.get("dispatch_id"), "source": state.get("source"), "actor": state.get("actor")}, wait=True, timeout_ms=45000)
        return {**state, "dispatch_result": result}
    return {**state, "dispatch_result": {"ok": False, "error": f"unsupported_type:{entry['type']}"}}

def log_dispatch_complete(state):
    dispatch_id = state.get("dispatch_id")
    if not dispatch_id: return state
    duration_ms = int((time.time() - (state.get("dispatch_started_at") or time.time())) * 1000)
    result = state.get("dispatch_result", {})
    status = "completed" if result.get("ok") else "failed"
    if state.get("resolved_intent", {}).get("domain") == "unknown": status = "unknown_intent"
    _supabase_patch("agent_dispatches", "id", dispatch_id, {"dispatch_result": result, "status": status, "duration_ms": duration_ms})
    return state

def summarize(state):
    intent = state.get("resolved_intent", {}) or {}
    result = state.get("dispatch_result", {}) or {}
    if state.get("error"):
        summary = f"Master ERROR: {state['error']}"
    elif intent.get("domain") == "unknown":
        summary = f"Master v2.4: unknown (conf {intent.get('confidence', 0)}) -- {intent.get('reasoning', 'n/a')[:120]}"
    elif result.get("ok"):
        summary = f"Master v2.4 -> {intent.get('domain')}.{intent.get('action')} OK (conf {intent.get('confidence', 0)})"
    else:
        summary = f"Master v2.4 -> {intent.get('domain')}.{intent.get('action')} FAILED: {result.get('error', 'unknown')}"
    return {**state, "summary": summary}

def build_graph():
    g = StateGraph(MasterState)
    for n, f in [("resolve_intent", resolve_intent), ("log_dispatch_start", log_dispatch_start), ("dispatch_to_domain", dispatch_to_domain), ("log_dispatch_complete", log_dispatch_complete), ("summarize", summarize)]:
        g.add_node(n, f)
    g.add_edge(START, "resolve_intent")
    g.add_edge("resolve_intent", "log_dispatch_start")
    g.add_edge("log_dispatch_start", "dispatch_to_domain")
    g.add_edge("dispatch_to_domain", "log_dispatch_complete")
    g.add_edge("log_dispatch_complete", "summarize")
    g.add_edge("summarize", END)
    return g.compile()

graph = build_graph()
