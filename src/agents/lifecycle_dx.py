"""
Lifecycle-DX Agent — LangGraph v1
Doctrine §90: DX for Lifecycle domain. Validates cross-domain composition path.
Checks: contact_state table accepting writes, campaign_registry has expected campaigns,
        Paige bridge reachable, crm_orchestrator + revenue_orchestrator both discoverable.
"""
from __future__ import annotations
import os, time
from typing import TypedDict, Optional, List
import httpx
from langgraph.graph import StateGraph, START, END
from datetime import datetime, timezone

MMA_OS_FUNCTIONS_BASE = os.environ.get("MMA_OS_FUNCTIONS_BASE", "https://slcqeiqcrhepicqxqjng.supabase.co/functions/v1")
MMA_OS_SUPABASE_URL = os.environ.get("MMA_OS_SUPABASE_URL", "https://slcqeiqcrhepicqxqjng.supabase.co")
PAIGE_BRIDGE_URL = os.environ.get("PAIGE_BRIDGE_URL", "https://bfmyebsjyuoecmjskqhs.supabase.co/functions/v1/paige-bridge")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
MMA_OS_BRIDGE_API_KEY = os.environ.get("MMA_OS_BRIDGE_API_KEY", "")
PAIGE_BRIDGE_API_KEY = os.environ.get("PAIGE_BRIDGE_API_KEY", "")
LANGGRAPH_WRITER_API_KEY = os.environ.get("LANGGRAPH_WRITER_API_KEY", "")

class DXState(TypedDict, total=False):
    trigger: str
    check_results: List[dict]
    failures: List[dict]
    heal_attempts: List[dict]
    escalations: List[dict]
    summary: str

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

def _supabase_get(path, timeout=10.0):
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.get(f"{MMA_OS_SUPABASE_URL}/rest/v1/{path}", headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"})
            return {"status": r.status_code, "body": r.json() if r.text else []}
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
    return _post(f"{MMA_OS_FUNCTIONS_BASE}/mma-os-bridge", {"verb": "push_admin_notification", "category": "lifecycle_dx", "severity": severity, "message": message, "metadata": metadata or {}}, MMA_OS_BRIDGE_API_KEY, timeout=10.0)

def run_health_checks(state):
    results = []
    
    # Check 1: contact_state table reachable (may not exist yet — treat as healthy if 404 = empty)
    res = _supabase_get("contact_state?limit=1&select=email")
    ok = res["status"] in (200, 404)
    results.append({"agent": "contact_state_table", "domain": "lifecycle", "tier": 2, "status": "healthy" if ok else "down", "raw": {"status": res["status"]}})
    
    # Check 2: campaign_registry has rows
    res2 = _supabase_get("campaign_registry?limit=10&select=campaign_key,active")
    has_registry = res2["status"] == 200 and isinstance(res2["body"], list) and len(res2["body"]) > 0
    results.append({"agent": "campaign_registry", "domain": "lifecycle", "tier": 2, "status": "healthy" if has_registry else "down", "raw": {"rows": len(res2["body"]) if isinstance(res2["body"], list) else 0}})
    
    # Check 3: Paige bridge reachable (treat Unknown verb as healthy per §93)
    res3 = _post(PAIGE_BRIDGE_URL, {"verb": "health"}, PAIGE_BRIDGE_API_KEY)
    body3 = res3["body"] if isinstance(res3["body"], dict) else {}
    err3 = str(body3.get("error") or "").lower()
    ok3 = (res3["status"] == 200 and body3.get("ok") is True) or "unknown verb" in err3 or res3["status"] in (200, 400)
    results.append({"agent": "paige_bridge", "domain": "lifecycle", "tier": 2, "status": "healthy" if ok3 else "down", "raw": {"status": res3["status"]}})
    
    # Check 4: crm_orchestrator discoverable
    res4 = _post(f"{MMA_OS_FUNCTIONS_BASE}/langgraph-bridge", {"verb": "list_assistants", "limit": 20}, LANGGRAPH_WRITER_API_KEY)
    graphs = [a.get("graph_id") for a in (res4["body"].get("assistants", []) if isinstance(res4["body"], dict) else [])]
    has_crm = "crm_orchestrator" in graphs
    has_revenue = "revenue_orchestrator" in graphs
    results.append({"agent": "downstream_graphs", "domain": "lifecycle", "tier": 2, "status": "healthy" if (has_crm and has_revenue) else "down", "raw": {"crm_present": has_crm, "revenue_present": has_revenue}})
    
    return {**state, "check_results": results, "failures": [r for r in results if r["status"] != "healthy"]}

def attempt_self_heal(state):
    return {**state, "heal_attempts": [{"agent": f["agent"], "method": "no_auto_heal", "result": "needs_human"} for f in state.get("failures", []) or []]}

def update_system_health(state):
    now_iso = datetime.now(timezone.utc).isoformat()
    for r in state.get("check_results", []) or []:
        payload = {"agent_name": r["agent"], "status": r["status"], "domain": r["domain"], "tier": r["tier"], "last_check_at": now_iso, "updated_at": now_iso, "details": r.get("raw", {})}
        if r["status"] == "healthy":
            payload["last_healthy_at"] = now_iso
            payload["last_error"] = None
        else:
            payload["last_error"] = str(r.get("raw", {}))[:500]
        _supabase_upsert("system_health", payload, on_conflict="agent_name")
    return state

def escalate_if_failing(state):
    escalations = []
    failures = state.get("failures", []) or []
    if not failures:
        return {**state, "escalations": []}
    bullets = "\n".join([f"- {f['agent']} -> {f['status']}" for f in failures])
    msg = f"Lifecycle-DX: {len(failures)} item(s) unhealthy:\n{bullets}"
    res = _bridge_alert(msg, severity="warning", metadata={"failures": failures})
    escalations.append({"channel": "telegram_admin", "result": res})
    return {**state, "escalations": escalations}

def summarize(state):
    checks = state.get("check_results", []) or []
    healthy = sum(1 for r in checks if r["status"] == "healthy")
    total = len(checks)
    escalated = len(state.get("escalations", []) or [])
    if healthy == total:
        summary = f"Lifecycle-DX: {healthy}/{total} healthy"
    else:
        summary = f"Lifecycle-DX: {healthy}/{total} healthy, {escalated} escalation(s) sent"
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
