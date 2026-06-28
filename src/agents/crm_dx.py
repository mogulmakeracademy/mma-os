"""
CRM-DX Agent — LangGraph v1
Doctrine §90: Diagnostic+Fix child for the CRM domain.
Checks GHL API auth, contacts endpoint, pipelines endpoint, ghl-webhook-receiver.
"""
from __future__ import annotations
import os, time
from typing import TypedDict, Optional, List
import httpx
from urllib.parse import urlencode
from langgraph.graph import StateGraph, START, END
from datetime import datetime, timezone

MMA_OS_FUNCTIONS_BASE = os.environ.get("MMA_OS_FUNCTIONS_BASE", "https://slcqeiqcrhepicqxqjng.supabase.co/functions/v1")
MMA_OS_SUPABASE_URL = os.environ.get("MMA_OS_SUPABASE_URL", "https://slcqeiqcrhepicqxqjng.supabase.co")
GHL_BASE_URL = os.environ.get("GHL_BASE_URL", "https://services.leadconnectorhq.com")
GHL_PIT_TOKEN = os.environ.get("GHL_PIT_TOKEN", "") or os.environ.get("GHL_PIT", "")
GHL_LOCATION_ID = os.environ.get("GHL_LOCATION_ID", "")
GHL_API_VERSION = os.environ.get("GHL_API_VERSION", "2021-07-28")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
MMA_OS_BRIDGE_API_KEY = os.environ.get("MMA_OS_BRIDGE_API_KEY", "")

class DXState(TypedDict, total=False):
    trigger: str
    check_results: List[dict]
    failures: List[dict]
    heal_attempts: List[dict]
    escalations: List[dict]
    summary: str

def _ghl_get(path, query=None, timeout=10.0):
    if not GHL_PIT_TOKEN:
        return {"status": 0, "body": {"error": "GHL_PIT_TOKEN not set"}}
    try:
        with httpx.Client(timeout=timeout) as client:
            url = f"{GHL_BASE_URL}{path}"
            if query:
                url += "?" + urlencode({k: v for k, v in query.items() if v is not None})
            r = client.get(url, headers={"Authorization": f"Bearer {GHL_PIT_TOKEN}", "Version": GHL_API_VERSION, "Accept": "application/json"})
            try:
                return {"status": r.status_code, "body": r.json()}
            except Exception:
                return {"status": r.status_code, "body": {"raw": r.text[:200]}}
    except Exception as exc:
        return {"status": 0, "body": {"error": str(exc)}}

def _post(url, body, bearer, timeout=10.0):
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.post(url, headers={"Authorization": f"Bearer {bearer}", "Content-Type": "application/json"}, json=body)
            try:
                return {"status": r.status_code, "body": r.json()}
            except Exception:
                return {"status": r.status_code, "body": {"raw": r.text[:200]}}
    except Exception as exc:
        return {"status": 0, "body": {"error": str(exc)}}

def _supabase_upsert(table, payload, on_conflict):
    if not SUPABASE_SERVICE_ROLE_KEY:
        return {"ok": False}
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.post(f"{MMA_OS_SUPABASE_URL}/rest/v1/{table}?on_conflict={on_conflict}", headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}", "Content-Type": "application/json", "Prefer": "return=representation,resolution=merge-duplicates"}, json=payload)
            return {"ok": r.status_code < 300}
    except Exception:
        return {"ok": False}

def _bridge_alert(message, severity="warning", metadata=None):
    return _post(f"{MMA_OS_FUNCTIONS_BASE}/mma-os-bridge", {"verb": "push_admin_notification", "category": "crm_dx", "severity": severity, "message": message, "metadata": metadata or {}}, MMA_OS_BRIDGE_API_KEY, timeout=10.0)

def run_health_checks(state):
    results = []
    res = _ghl_get(f"/locations/{GHL_LOCATION_ID}") if GHL_LOCATION_ID else {"status": 0, "body": {"error": "GHL_LOCATION_ID not set"}}
    results.append({"agent": "ghl_api_auth", "domain": "crm", "tier": 2, "status": "healthy" if res["status"] == 200 else "down", "raw": res})
    res2 = _ghl_get("/contacts/", query={"locationId": GHL_LOCATION_ID, "limit": 1})
    results.append({"agent": "ghl_contacts_endpoint", "domain": "crm", "tier": 2, "status": "healthy" if res2["status"] == 200 else "down", "raw": res2})
    res3 = _ghl_get("/opportunities/pipelines", query={"locationId": GHL_LOCATION_ID})
    results.append({"agent": "ghl_pipelines_endpoint", "domain": "crm", "tier": 2, "status": "healthy" if res3["status"] == 200 else "down", "raw": res3})
    res4 = _post(f"{MMA_OS_FUNCTIONS_BASE}/ghl-webhook-receiver", {"verb": "health"}, MMA_OS_BRIDGE_API_KEY)
    body4 = res4["body"] if isinstance(res4["body"], dict) else {}
    err4 = str(body4.get("error") or "").lower()
    ok4 = (res4["status"] == 200 and body4.get("ok") is True) or "unknown verb" in err4 or res4["status"] in (200, 400)
    results.append({"agent": "ghl_webhook_receiver", "domain": "crm", "tier": 2, "status": "healthy" if ok4 else "down", "raw": res4})
    return {**state, "check_results": results, "failures": [r for r in results if r["status"] != "healthy"]}

def attempt_self_heal(state):
    return {**state, "heal_attempts": [{"agent": f["agent"], "method": "no_auto_heal", "result": "needs_human"} for f in state.get("failures", []) or []]}

def update_system_health(state):
    now_iso = datetime.now(timezone.utc).isoformat()
    for r in state.get("check_results", []) or []:
        payload = {"agent_name": r["agent"], "status": r["status"], "domain": r["domain"], "tier": r["tier"], "last_check_at": now_iso, "updated_at": now_iso, "details": {"raw_status": r.get("raw", {}).get("status")}}
        if r["status"] == "healthy":
            payload["last_healthy_at"] = now_iso
            payload["last_error"] = None
        else:
            payload["last_error"] = str(r.get("raw", {}).get("body", {}))[:500]
        _supabase_upsert("system_health", payload, on_conflict="agent_name")
    return state

def escalate_if_failing(state):
    escalations = []
    failures = state.get("failures", []) or []
    if not failures:
        return {**state, "escalations": []}
    bullets = "\n".join([f"- {f['agent']} -> {f['status']}" for f in failures])
    msg = f"CRM-DX: {len(failures)} item(s) unhealthy:\n{bullets}"
    res = _bridge_alert(msg, severity="warning", metadata={"failures": failures})
    escalations.append({"channel": "telegram_admin", "result": res})
    return {**state, "escalations": escalations}

def summarize(state):
    checks = state.get("check_results", []) or []
    healthy = sum(1 for r in checks if r["status"] == "healthy")
    total = len(checks)
    escalated = len(state.get("escalations", []) or [])
    if healthy == total:
        summary = f"CRM-DX: {healthy}/{total} healthy"
    else:
        summary = f"CRM-DX: {healthy}/{total} healthy, {escalated} escalation(s) sent"
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
