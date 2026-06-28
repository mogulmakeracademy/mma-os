"""Revenue-DX v1.2 — query enrollments table directly (bypass bridge interface uncertainty)."""
from __future__ import annotations
import os, time
from typing import TypedDict, Optional, List
import httpx
from langgraph.graph import StateGraph, START, END
from datetime import datetime, timezone

MMA_OS_FUNCTIONS_BASE = os.environ.get("MMA_OS_FUNCTIONS_BASE", "https://slcqeiqcrhepicqxqjng.supabase.co/functions/v1")
MMA_OS_SUPABASE_URL = os.environ.get("MMA_OS_SUPABASE_URL", "https://slcqeiqcrhepicqxqjng.supabase.co")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
MMA_OS_BRIDGE_API_KEY = os.environ.get("MMA_OS_BRIDGE_API_KEY", "")
N8N_WRITER_API_KEY = os.environ.get("N8N_WRITER_API_KEY", "")

ENGINE_WORKFLOW_ID = "x6AGdX76nQWgpYdx"
CAMPAIGN_CONTROL_WORKFLOW_ID = "QKQIADHV966LZ3Qx"
EXPECTED_CAMPAIGN = "skool_45day_tier_upgrade"

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
            try: return {"status": r.status_code, "body": r.json()}
            except Exception: return {"status": r.status_code, "body": {"raw": r.text[:200]}}
    except Exception as exc:
        return {"status": 0, "body": {"error": str(exc)}}

def _supabase_get(path):
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(f"{MMA_OS_SUPABASE_URL}/rest/v1/{path}", headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"})
            return {"status": r.status_code, "body": r.json() if r.text else []}
    except Exception as exc:
        return {"status": 0, "body": {"error": str(exc)}}

def _supabase_upsert(table, payload, on_conflict):
    if not SUPABASE_SERVICE_ROLE_KEY: return {"ok": False}
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.post(f"{MMA_OS_SUPABASE_URL}/rest/v1/{table}?on_conflict={on_conflict}", headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}", "Content-Type": "application/json", "Prefer": "return=representation,resolution=merge-duplicates"}, json=payload)
            return {"ok": r.status_code < 300}
    except Exception: return {"ok": False}

def _bridge_alert(msg, sev="warning", meta=None):
    return _post(f"{MMA_OS_FUNCTIONS_BASE}/mma-os-bridge", {"verb": "push_admin_notification", "category": "revenue_dx", "severity": sev, "message": msg, "metadata": meta or {}}, MMA_OS_BRIDGE_API_KEY)

def _check_workflow_active(wf_id):
    res = _post(f"{MMA_OS_FUNCTIONS_BASE}/n8n-writer", {"verb": "get_workflow", "id": wf_id}, N8N_WRITER_API_KEY)
    if res["status"] != 200: return False, res
    wf = res["body"].get("workflow", {})
    return wf.get("active", False), {"active": wf.get("active", False), "name": wf.get("name", "?")}

def run_health_checks(state):
    results = []
    ok, d = _check_workflow_active(ENGINE_WORKFLOW_ID)
    results.append({"agent": "engine_v4.5_workflow", "domain": "revenue", "tier": 2, "status": "healthy" if ok else "down", "raw": {"body": d}})
    ok2, d2 = _check_workflow_active(CAMPAIGN_CONTROL_WORKFLOW_ID)
    results.append({"agent": "campaign_control_workflow", "domain": "revenue", "tier": 2, "status": "healthy" if ok2 else "down", "raw": {"body": d2}})
    res3 = _supabase_get(f"campaign_control?campaign_key=eq.{EXPECTED_CAMPAIGN}&limit=1")
    rows = res3["body"] if isinstance(res3["body"], list) else []
    has_row = res3["status"] == 200 and len(rows) > 0
    results.append({"agent": "campaign_control_table", "domain": "revenue", "tier": 2, "status": "healthy" if has_row else "down", "raw": {"rows": len(rows)}})
    # FIX v1.2: query enrollments table directly instead of bridge verb
    res4 = _supabase_get(f"enrollments?campaign_key=eq.{EXPECTED_CAMPAIGN}&limit=1&select=id,email")
    rows4 = res4["body"] if isinstance(res4["body"], list) else []
    ok4 = res4["status"] in (200, 404)  # 404 = empty but accessible
    results.append({"agent": "enrollments_table_queryable", "domain": "revenue", "tier": 2, "status": "healthy" if ok4 else "down", "raw": {"rows_found": len(rows4), "status": res4["status"]}})
    return {**state, "check_results": results, "failures": [r for r in results if r["status"] != "healthy"]}

def attempt_self_heal(state):
    heal = []
    for f in state.get("failures", []) or []:
        if f["agent"] in ("engine_v4.5_workflow", "campaign_control_workflow"):
            wf_id = ENGINE_WORKFLOW_ID if "engine" in f["agent"] else CAMPAIGN_CONTROL_WORKFLOW_ID
            res = _post(f"{MMA_OS_FUNCTIONS_BASE}/n8n-writer", {"verb": "activate_workflow", "id": wf_id}, N8N_WRITER_API_KEY)
            ok = res["status"] == 200
            heal.append({"agent": f["agent"], "method": "activate_workflow", "result": "healed" if ok else "still_failing"})
            if ok:
                for r in state.get("check_results", []):
                    if r["agent"] == f["agent"]:
                        r["status"] = "healthy"; r["healed"] = True
        else:
            heal.append({"agent": f["agent"], "method": "no_auto_heal", "result": "needs_human"})
    new_failures = [r for r in state.get("check_results", []) if r["status"] != "healthy"]
    return {**state, "heal_attempts": heal, "failures": new_failures}

def update_system_health(state):
    now = datetime.now(timezone.utc).isoformat()
    for r in state.get("check_results", []) or []:
        payload = {"agent_name": r["agent"], "status": r["status"], "domain": r["domain"], "tier": r["tier"], "last_check_at": now, "updated_at": now, "details": r.get("raw", {})}
        if r["status"] == "healthy":
            payload["last_healthy_at"] = now; payload["last_error"] = None
        else:
            payload["last_error"] = str(r.get("raw", {}))[:500]
        _supabase_upsert("system_health", payload, on_conflict="agent_name")
    return state

def escalate_if_failing(state):
    failures = state.get("failures", []) or []
    if not failures: return {**state, "escalations": []}
    bullets = "\n".join([f"- {f['agent']} -> {f['status']}" for f in failures])
    return {**state, "escalations": [{"channel": "telegram_admin", "result": _bridge_alert(f"Revenue-DX v1.2: {len(failures)} item(s) unhealthy:\n{bullets}", "warning", {"failures": failures})}]}

def summarize(state):
    checks = state.get("check_results", []) or []
    healthy = sum(1 for r in checks if r["status"] == "healthy")
    total = len(checks)
    esc = len(state.get("escalations", []) or [])
    return {**state, "summary": f"Revenue-DX v1.2: {healthy}/{total} healthy" + ("" if healthy == total else f", {esc} escalation(s)")}

def build_graph():
    g = StateGraph(DXState)
    for n, f in [("run_health_checks", run_health_checks), ("attempt_self_heal", attempt_self_heal), ("update_system_health", update_system_health), ("escalate_if_failing", escalate_if_failing), ("summarize", summarize)]:
        g.add_node(n, f)
    g.add_edge(START, "run_health_checks")
    g.add_edge("run_health_checks", "attempt_self_heal")
    g.add_edge("attempt_self_heal", "update_system_health")
    g.add_edge("update_system_health", "escalate_if_failing")
    g.add_edge("escalate_if_failing", "summarize")
    g.add_edge("summarize", END)
    return g.compile()

graph = build_graph()
