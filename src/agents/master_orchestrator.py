"""
Master Orchestrator — LangGraph v2 (LLM resilience + URL collision fix)
v2 fixes:
  - LLM call returns empty content -> fall back to heuristic instead of erroring
  - LLM call bumped timeout 20s -> 30s
  - API error response surfaced in reasoning for debugging
  - Switched SUPABASE_URL -> MMA_OS_SUPABASE_URL to avoid env collision
"""
from __future__ import annotations
import os, json, time
from typing import TypedDict, Optional
import httpx
from langgraph.graph import StateGraph, START, END

MMA_OS_FUNCTIONS_BASE = os.environ.get("MMA_OS_FUNCTIONS_BASE", "https://slcqeiqcrhepicqxqjng.supabase.co/functions/v1")
MMA_OS_SUPABASE_URL = os.environ.get("MMA_OS_SUPABASE_URL", "https://slcqeiqcrhepicqxqjng.supabase.co")
MMA_OS_BRIDGE_URL = f"{MMA_OS_FUNCTIONS_BASE}/mma-os-bridge"
LANGGRAPH_BRIDGE_URL = f"{MMA_OS_FUNCTIONS_BASE}/langgraph-bridge"
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
MMA_OS_BRIDGE_API_KEY = os.environ.get("MMA_OS_BRIDGE_API_KEY", "")
LANGGRAPH_WRITER_API_KEY = os.environ.get("LANGGRAPH_WRITER_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5-20251022")

DOMAIN_REGISTRY = {
    "comms": {"type": "langgraph", "graph_id": "comms_orchestrator"},
    "crm": {"type": "stub", "note": "crm_orchestrator pending"},
    "lifecycle": {"type": "stub", "note": "lifecycle_orchestrator pending"},
    "revenue": {"type": "stub", "note": "revenue_orchestrator pending"},
    "monitoring": {"type": "stub", "note": "monitoring_orchestrator pending"},
    "content": {"type": "stub", "note": "content_orchestrator pending"},
    "support": {"type": "n8n_webhook", "url": os.environ.get("CS_WEBHOOK_URL", "")},
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
    if not bearer:
        return {"ok": False, "error": "missing bearer token"}
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, headers={"Authorization": f"Bearer {bearer}", "Content-Type": "application/json"}, json=body)
            try:
                return resp.json()
            except Exception:
                return {"ok": False, "error": f"non-json response"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

def _langgraph_fire(graph_id, input_data, wait=True, timeout_ms=60000):
    return _post(LANGGRAPH_BRIDGE_URL, {"verb": "fire_agent", "graph_id": graph_id, "input": input_data, "wait": wait, "timeout_ms": timeout_ms}, LANGGRAPH_WRITER_API_KEY, timeout=timeout_ms/1000 + 10)

def _supabase_insert(table, payload):
    if not SUPABASE_SERVICE_ROLE_KEY:
        return {"ok": False, "error": "SUPABASE_SERVICE_ROLE_KEY not set"}
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(f"{MMA_OS_SUPABASE_URL}/rest/v1/{table}", headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}", "Content-Type": "application/json", "Prefer": "return=representation"}, json=payload)
            data = resp.json()
            if resp.status_code >= 300:
                return {"ok": False, "status": resp.status_code, "error": data}
            return {"ok": True, "row": data[0] if isinstance(data, list) and data else data}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

def _supabase_patch(table, pk_field, pk_value, payload):
    if not SUPABASE_SERVICE_ROLE_KEY:
        return {"ok": False, "error": "SUPABASE_SERVICE_ROLE_KEY not set"}
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.patch(f"{MMA_OS_SUPABASE_URL}/rest/v1/{table}?{pk_field}=eq.{pk_value}", headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}", "Content-Type": "application/json", "Prefer": "return=representation"}, json=payload)
            return {"ok": resp.status_code < 300, "status": resp.status_code}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

def _heuristic_intent(text):
    """Keyword-based fallback when LLM is unavailable or returns empty."""
    lower = text.lower()
    if any(k in lower for k in ("telegram", "alert", "notify", "send", "email", "sms", "message", "tell", "ping", "alive")):
        return {"domain": "comms", "action": "notify_admin", "payload": {"message": text}, "confidence": 0.5, "reasoning": "heuristic match"}
    if any(k in lower for k in ("tag", "ghl", "contact", "lead", "opportunity")):
        return {"domain": "crm", "action": "unknown", "payload": {"raw": text}, "confidence": 0.4, "reasoning": "heuristic crm match"}
    if any(k in lower for k in ("campaign", "enroll", "fire", "send to cohort", "skool")):
        return {"domain": "revenue", "action": "unknown", "payload": {"raw": text}, "confidence": 0.4, "reasoning": "heuristic revenue match"}
    return {"domain": "unknown", "action": "unknown", "payload": {}, "confidence": 0.0, "reasoning": "heuristic miss"}

def _claude_resolve_intent(text, source, context, hint):
    if not ANTHROPIC_API_KEY:
        h = _heuristic_intent(text)
        h["reasoning"] = "no Anthropic key, " + h["reasoning"]
        return h

    system_prompt = (
        "You are the Master Orchestrator of MMA OS. Classify the request into a domain and action.\n"
        "Domains: comms, crm, lifecycle, revenue, monitoring, content, support, unknown.\n"
        'Return ONLY JSON: { "domain": str, "action": str, "payload": dict, "confidence": 0..1, "reasoning": str }'
    )
    hint_str = f"\nHint: {hint}" if hint else ""
    user_msg = f"Source: {source}\nContext: {json.dumps(context)[:500]}{hint_str}\n\nRequest:\n{text}"

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post("https://api.anthropic.com/v1/messages", headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}, json={"model": ANTHROPIC_MODEL, "max_tokens": 800, "system": system_prompt, "messages": [{"role": "user", "content": user_msg}]})
            http_status = resp.status_code
            try:
                data = resp.json()
            except Exception:
                # Non-JSON response (rare). Fall back to heuristic.
                h = _heuristic_intent(text)
                h["reasoning"] = f"LLM non-json (http {http_status}); " + h["reasoning"]
                return h
            content_blocks = data.get("content", [])
            raw = "".join(b.get("text", "") for b in content_blocks if b.get("type") == "text").strip()
            if not raw:
                # Empty content — likely API error. Fall back to heuristic.
                api_error = data.get("error", {}).get("message", "no error msg")[:200] if isinstance(data.get("error"), dict) else str(data)[:200]
                h = _heuristic_intent(text)
                h["reasoning"] = f"LLM empty (http {http_status}, api_err: {api_error}); " + h["reasoning"]
                return h
            if raw.startswith("\u0060\u0060\u0060"):
                raw = raw.split("\n", 1)[-1]
            if raw.endswith("\u0060\u0060\u0060"):
                raw = raw.rsplit("\u0060\u0060\u0060", 1)[0]
            try:
                return json.loads(raw)
            except Exception:
                # LLM returned text but not valid JSON. Fall back to heuristic.
                h = _heuristic_intent(text)
                h["reasoning"] = f"LLM unparseable: {raw[:100]}; " + h["reasoning"]
                return h
    except Exception as exc:
        h = _heuristic_intent(text)
        h["reasoning"] = f"LLM exception: {exc}; " + h["reasoning"]
        return h

def resolve_intent(state):
    state = {**state, "error": None, "dispatch_started_at": time.time()}
    text = (state.get("text") or "").strip()
    if not text:
        return {**state, "error": "no text provided", "resolved_intent": {"domain": "unknown", "action": "unknown", "payload": {}, "confidence": 0.0, "reasoning": "empty input"}}
    intent = _claude_resolve_intent(text=text, source=state.get("source", "unknown"), context=state.get("context", {}), hint=state.get("intent_hint"))
    return {**state, "resolved_intent": intent}

def log_dispatch_start(state):
    intent = state.get("resolved_intent", {}) or {}
    res = _supabase_insert("agent_dispatches", {"source": state.get("source", "unknown"), "actor": state.get("actor"), "raw_text": (state.get("text") or "")[:2000], "resolved_intent": intent, "dispatch_target": intent.get("domain", "unknown"), "status": "pending"})
    if res.get("ok"):
        return {**state, "dispatch_id": res["row"]["id"]}
    return state

def dispatch_to_domain(state):
    if state.get("error"):
        return state
    intent = state.get("resolved_intent", {}) or {}
    domain = intent.get("domain", "unknown")
    registry_entry = DOMAIN_REGISTRY.get(domain)
    if not registry_entry:
        return {**state, "dispatch_result": {"ok": False, "error": f"unknown_domain:{domain}", "status": "unknown_intent"}}
    target_type = registry_entry["type"]
    if target_type == "stub":
        return {**state, "dispatch_result": {"ok": True, "stub": True, "domain": domain, "note": registry_entry["note"], "intent": intent}}
    if target_type == "langgraph":
        result = _langgraph_fire(graph_id=registry_entry["graph_id"], input_data={"task": intent.get("action", "unknown"), "payload": intent.get("payload", {}), "parent_dispatch_id": state.get("dispatch_id"), "source": state.get("source"), "actor": state.get("actor")}, wait=True, timeout_ms=45000)
        return {**state, "dispatch_result": result}
    if target_type == "n8n_webhook":
        url = registry_entry.get("url")
        if not url:
            return {**state, "dispatch_result": {"ok": False, "error": "n8n_webhook_url_not_set"}}
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(url, json={"text": state.get("text"), "actor": state.get("actor"), "source": state.get("source"), "intent": intent})
                return {**state, "dispatch_result": {"ok": resp.status_code < 300, "status": resp.status_code}}
        except Exception as exc:
            return {**state, "dispatch_result": {"ok": False, "error": str(exc)}}
    return {**state, "dispatch_result": {"ok": False, "error": f"unsupported_target_type:{target_type}"}}

def log_dispatch_complete(state):
    dispatch_id = state.get("dispatch_id")
    if not dispatch_id:
        return state
    started = state.get("dispatch_started_at") or time.time()
    duration_ms = int((time.time() - started) * 1000)
    result = state.get("dispatch_result", {})
    status = "completed" if result.get("ok") else "failed"
    if state.get("resolved_intent", {}).get("domain") == "unknown":
        status = "unknown_intent"
    _supabase_patch("agent_dispatches", "id", dispatch_id, {"dispatch_result": result, "status": status, "duration_ms": duration_ms})
    return state

def summarize(state):
    intent = state.get("resolved_intent", {}) or {}
    result = state.get("dispatch_result", {}) or {}
    if state.get("error"):
        summary = f"Master ERROR: {state['error']}"
    elif intent.get("domain") == "unknown":
        summary = f"Master v2: unknown (conf {intent.get('confidence', 0)}) -- {intent.get('reasoning', 'n/a')[:120]}"
    elif result.get("stub"):
        summary = f"Master v2 -> {intent.get('domain')} (stub): {result.get('note')}"
    elif result.get("ok"):
        summary = f"Master v2 -> {intent.get('domain')}.{intent.get('action')} OK (conf {intent.get('confidence', 0)})"
    else:
        summary = f"Master v2 -> {intent.get('domain')}.{intent.get('action')} FAILED: {result.get('error', 'unknown')}"
    return {**state, "summary": summary}

def build_graph():
    g = StateGraph(MasterState)
    g.add_node("resolve_intent", resolve_intent)
    g.add_node("log_dispatch_start", log_dispatch_start)
    g.add_node("dispatch_to_domain", dispatch_to_domain)
    g.add_node("log_dispatch_complete", log_dispatch_complete)
    g.add_node("summarize", summarize)
    g.add_edge(START, "resolve_intent")
    g.add_edge("resolve_intent", "log_dispatch_start")
    g.add_edge("log_dispatch_start", "dispatch_to_domain")
    g.add_edge("dispatch_to_domain", "log_dispatch_complete")
    g.add_edge("log_dispatch_complete", "summarize")
    g.add_edge("summarize", END)
    return g.compile()

graph = build_graph()
