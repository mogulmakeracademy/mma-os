"""
Comms-DX Agent — LangGraph v3
v3 fix: treat mma-os-bridge "Unknown verb" 200 response as HEALTHY (proves the
function is reachable and processing requests, just doesn't know the health verb).
Eliminates the fallback Telegram spam from v2.
"""
from __future__ import annotations
import os, time
from typing import TypedDict, Optional, List
import httpx
from langgraph.graph import StateGraph, START, END

MMA_OS_FUNCTIONS_BASE = os.environ.get("MMA_OS_FUNCTIONS_BASE", "https://slcqeiqcrhepicqxqjng.supabase.co/functions/v1")
MMA_OS_SUPABASE_URL = os.environ.get("MMA_OS_SUPABASE_URL", "https://slcqeiqcrhepicqxqjng.supabase.co")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
MMA_OS_BRIDGE_API_KEY = os.environ.get("MMA_OS_BRIDGE_API_KEY", "")
N8N_WRITER_API_KEY = os.environ.get("N8N_WRITER_API_KEY", "")
NOTION_WRITER_API_KEY = os.environ.get("NOTION_WRITER_API_KEY", "")
EDGE_FN_WRITER_API_KEY = os.environ.get("EDGE_FN_WRITER_API_KEY", "")
LANGGRAPH_WRITER_API_KEY = os.environ.get("LANGGRAPH_WRITER_API_KEY", "")

HEALTH_CHECKS = [
    {"agent": "mma-os-bridge",        "domain": "comms", "tier": 2, "url": f"{MMA_OS_FUNCTIONS_BASE}/mma-os-bridge",        "key_env": "MMA_OS_BRIDGE_API_KEY",  "body": {"verb": "health"}, "treat_unknown_verb_as_healthy": True},
    {"agent": "n8n-writer",           "domain": "comms", "tier": 2, "url": f"{MMA_OS_FUNCTIONS_BASE}/n8n-writer",           "key_env": "N8N_WRITER_API_KEY",     "body": {"verb": "health"}},
    {"agent": "notion-writer",        "domain": "comms", "tier": 2, "url": f"{MMA_OS_FUNCTIONS_BASE}/notion-writer",        "key_env": "NOTION_WRITER_API_KEY",  "body": {"verb": "health"}},
    {"agent": "edge-function-writer", "domain": "comms", "tier": 2, "url": f"{MMA_OS_FUNCTIONS_BASE}/edge-function-writer", "key_env": "EDGE_FN_WRITER_API_KEY", "body": {"verb": "health"}},
    {"agent": "langgraph-bridge",     "domain": "comms", "tier": 2, "url": f"{MMA_OS_FUNCTIONS_BASE}/langgraph-bridge",     "key_env": "LANGGRAPH_WRITER_API_KEY", "body": {"verb": "health"}},
]

class DXState(TypedDict, total=False):
    trigger: str
    check_results: List[dict]
    failures: List[dict]
    heal_attempts: List[dict]
    escalations: List[dict]
    summary: str
    error: Optional[str]

def _post(url, body, bearer, timeout=10.0):
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, headers={"Authorization": f"Bearer {bearer}", "Content-Type": "application/json"}, json=body)
            try:
                return {"status": resp.status_code, "body": resp.json()}
            except Exception:
                return {"status": resp.status_code, "body": {"raw": resp.text[:200]}}
    except Exception as exc:
        return {"status": 0, "body": {"error": str(exc)}}

def _supabase_upsert(table, payload, on_conflict):
    if not SUPABASE_SERVICE_ROLE_KEY:
        return {"ok": False}
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(f"{MMA_OS_SUPABASE_URL}/rest/v1/{table}?on_conflict={on_conflict}", headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}", "Content-Type": "application/json", "Prefer": "return=representation,resolution=merge-duplicates"}, json=payload)
            return {"ok": resp.status_code < 300}
    except Exception:
        return {"ok": False}

def _bridge_alert(message, severity="warning", metadata=None):
    return _post(f"{MMA_OS_FUNCTIONS_BASE}/mma-os-bridge", {"verb": "push_admin_notification", "category": "comms_dx", "severity": severity, "message": message, "metadata": metadata or {}}, MMA_OS_BRIDGE_API_KEY, timeout=10.0)

def _key_for(env_name):
    return os.environ.get(env_name, "")

def _is_healthy(res, treat_unknown_verb_as_healthy=False):
    if res["status"] != 200:
        return False
    body = res["body"] if isinstance(res["body"], dict) else {}
    # Standard healthy signals
    if body.get("ok") is True or body.get("n8n_reachable") is True or body.get("mgmt_reachable") is True or body.get("langgraph_reachable") is True or body.get("integration") is not None:
        return True
    # v3: function is alive but doesn't know the verb -> still healthy
    if treat_unknown_verb_as_healthy:
        err = (body.get("error") or "").lower()
        if "unknown verb" in err or "verb" in err:
            return True
    return False

def run_health_checks(state):
    results = []
    for check in HEALTH_CHECKS:
        key = _key_for(check["key_env"])
        if not key:
            results.append({"agent": check["agent"], "domain": check["domain"], "tier": check["tier"], "status": "down", "reason": f"writer key {check['key_env']} not configured", "raw": {}})
            continue
        res = _post(check["url"], check["body"], key, timeout=10.0)
        is_ok = _is_healthy(res, check.get("treat_unknown_verb_as_healthy", False))
        results.append({"agent": check["agent"], "domain": check["domain"], "tier": check["tier"], "status": "healthy" if is_ok else "down", "raw": res})
    return {**state, "check_results": results, "failures": [r for r in results if r["status"] != "healthy"]}

def attempt_self_heal(state):
    heal_attempts = []
    for failure in state.get("failures", []) or []:
        match = next((c for c in HEALTH_CHECKS if c["agent"] == failure["agent"]), None)
        if not match:
            continue
        key = _key_for(match["key_env"])
        if not key:
            heal_attempts.append({"agent": failure["agent"], "method": "skip_no_key", "result": "cannot_heal"})
            continue
        time.sleep(2)
        retry = _post(match["url"], match["body"], key, timeout=10.0)
        retry_ok = _is_healthy(retry, match.get("treat_unknown_verb_as_healthy", False))
        heal_attempts.append({"agent": failure["agent"], "method": "retry", "result": "healed" if retry_ok else "still_failing"})
        if retry_ok:
            for r in state.get("check_results", []):
                if r["agent"] == failure["agent"]:
                    r["status"] = "healthy"
                    r["healed"] = True
    new_failures = [r for r in state.get("check_results", []) if r["status"] != "healthy"]
    return {**state, "heal_attempts": heal_attempts, "failures": new_failures}

def update_system_health(state):
    for r in state.get("check_results", []) or []:
        payload = {"agent_name": r["agent"], "status": r["status"], "domain": r["domain"], "tier": r["tier"], "details": {"raw_status": r.get("raw", {}).get("status"), "healed": r.get("healed", False)}}
        if r["status"] != "healthy":
            raw_body = r.get("raw", {}).get("body", {})
            payload["last_error"] = str(raw_body.get("error") or raw_body.get("hint") or raw_body)[:500]
        _supabase_upsert("system_health", payload, on_conflict="agent_name")
    return state

def escalate_if_failing(state):
    escalations = []
    failures = state.get("failures", []) or []
    if not failures:
        return {**state, "escalations": []}
    bullets = "\n".join([f"- {f['agent']} -> {f['status']}" for f in failures])
    msg = f"Comms-DX v3: {len(failures)} specialist(s) unhealthy:\n{bullets}"
    res = _bridge_alert(msg, severity="warning", metadata={"failures": failures, "heal_attempts": state.get("heal_attempts", [])})
    escalations.append({"channel": "telegram_admin", "result": res})
    return {**state, "escalations": escalations}

def summarize(state):
    checks = state.get("check_results", []) or []
    healthy = sum(1 for r in checks if r["status"] == "healthy")
    total = len(checks)
    healed = sum(1 for a in (state.get("heal_attempts", []) or []) if a["result"] == "healed")
    escalated = len(state.get("escalations", []) or [])
    if total == 0:
        summary = "Comms-DX v3: no checks ran"
    elif healthy == total:
        summary = f"Comms-DX v3: {healthy}/{total} healthy"
        if healed:
            summary += f" ({healed} self-healed)"
    else:
        summary = f"Comms-DX v3: {healthy}/{total} healthy, {escalated} escalation(s) sent"
    return {**state, "summary": summary}

def build_graph():
    g = StateGraph(DXState)
    g.add_node("run_health_checks", run_health_checks)
    g.add_node("attempt_self_heal", attempt_self_heal)
    g.add_node("update_system_health", update_system_health)
    g.add_node("escalate_if_failing", escalate_if_failing)
    g.add_node("summarize", summarize)
    g.add_edge(START, "run_health_checks")
    g.add_edge("run_health_checks", "attempt_self_heal")
    g.add_edge("attempt_self_heal", "update_system_health")
    g.add_edge("update_system_health", "escalate_if_failing")
    g.add_edge("escalate_if_failing", "summarize")
    g.add_edge("summarize", END)
    return g.compile()

graph = build_graph()
