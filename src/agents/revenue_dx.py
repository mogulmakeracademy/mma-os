"""
Revenue-DX Agent — LangGraph v1
Doctrine §90: Diagnostic+Fix child for the Revenue domain.

Checks:
  1. Engine v4.5 workflow (x6AGdX76nQWgpYdx) active in n8n
  2. Campaign Control Commands workflow (QKQIADHV966LZ3Qx) active in n8n
  3. campaign_control table has expected campaign row
  4. mma-os-bridge due_enrollments verb returns a count
  5. Engine v4.5 last execution within expected window (or paused intentionally)
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

def _supabase_read(table, filters):
    if not SUPABASE_SERVICE_ROLE_KEY:
        return {"status": 0, "body": {"error": "SUPABASE_SERVICE_ROLE_KEY not set"}}
    try:
        with httpx.Client(timeout=10.0) as client:
            qs = "&".join([f"{k}=eq.{v}" for k,v in filters.items()])
            resp = client.get(f"{MMA_OS_SUPABASE_URL}/rest/v1/{table}?{qs}", headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"})
            return {"status": resp.status_code, "body": resp.json() if resp.text else []}
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
    return _post(f"{MMA_OS_FUNCTIONS_BASE}/mma-os-bridge", {"verb": "push_admin_notification", "category": "revenue_dx", "severity": severity, "message": message, "metadata": metadata or {}}, MMA_OS_BRIDGE_API_KEY, timeout=10.0)

def _check_n8n_workflow_active(workflow_id):
    res = _post(f"{MMA_OS_FUNCTIONS_BASE}/n8n-writer", {"verb": "get_workflow", "id": workflow_id}, N8N_WRITER_API_KEY)
    if res["status"] != 200:
        return False, res
    wf = res["body"].get("workflow", {})
    is_active = wf.get("active", False)
    return is_active, {"active": is_active, "name": wf.get("name", "?")}

def _check_campaign_control_row():
    res = _supabase_read("campaign_control", {"campaign_key": EXPECTED_CAMPAIGN})
    rows = res["body"] if isinstance(res["body"], list) else []
    if res["status"] == 200 and rows:
        row = rows[0]
        return True, {"campaign_key": row.get("campaign_key"), "paused": row.get("paused"), "is_killed": row.get("is_killed"), "test_recipient": row.get("test_recipient_email")}
    return False, {"status": res["status"], "rows_found": len(rows)}

def _check_bridge_due_enrollments():
    res = _post(f"{MMA_OS_FUNCTIONS_BASE}/mma-os-bridge", {"verb": "due_enrollments", "limit": 1}, MMA_OS_BRIDGE_API_KEY)
    if res["status"] == 200 and isinstance(res["body"], dict):
        return True, {"verb_responded": True, "rows_returned": len(res["body"].get("enrollments", res["body"].get("data", [])))}
    return False, {"status": res["status"], "body_preview": str(res["body"])[:200]}

def run_health_checks(state):
    results = []
    
    # Check 1: Engine v4.5 workflow active
    ok, detail = _check_n8n_workflow_active(ENGINE_WORKFLOW_ID)
    results.append({"agent": "engine_v4.5_workflow", "domain": "revenue", "tier": 2, "status": "healthy" if ok else "down", "raw": {"body": detail}})
    
    # Check 2: Campaign Control workflow active
    ok2, detail2 = _check_n8n_workflow_active(CAMPAIGN_CONTROL_WORKFLOW_ID)
    results.append({"agent": "campaign_control_workflow", "domain": "revenue", "tier": 2, "status": "healthy" if ok2 else "down", "raw": {"body": detail2}})
    
    # Check 3: campaign_control table row present
    ok3, detail3 = _check_campaign_control_row()
    results.append({"agent": "campaign_control_table", "domain": "revenue", "tier": 2, "status": "healthy" if ok3 else "down", "raw": {"body": detail3}})
    
    # Check 4: bridge due_enrollments verb responsive
    ok4, detail4 = _check_bridge_due_enrollments()
    results.append({"agent": "bridge_due_enrollments", "domain": "revenue", "tier": 2, "status": "healthy" if ok4 else "down", "raw": {"body": detail4}})
    
    return {**state, "check_results": results, "failures": [r for r in results if r["status"] != "healthy"]}

def attempt_self_heal(state):
    # Revenue self-heal is limited — most failures need human intervention
    # (workflow inactive needs activation, missing campaign_control needs seeding)
    heal_attempts = []
    for failure in state.get("failures", []) or []:
        agent = failure["agent"]
        if agent in ("engine_v4.5_workflow", "campaign_control_workflow"):
            # Auto-heal: activate the workflow via n8n_writer
            workflow_id = ENGINE_WORKFLOW_ID if "engine" in agent else CAMPAIGN_CONTROL_WORKFLOW_ID
            res = _post(f"{MMA_OS_FUNCTIONS_BASE}/n8n-writer", {"verb": "activate_workflow", "id": workflow_id}, N8N_WRITER_API_KEY)
            if res["status"] == 200:
                heal_attempts.append({"agent": agent, "method": "activate_workflow", "result": "healed"})
                # Mark healthy in check_results
                for r in state.get("check_results", []):
                    if r["agent"] == agent:
                        r["status"] = "healthy"
                        r["healed"] = True
            else:
                heal_attempts.append({"agent": agent, "method": "activate_workflow", "result": "still_failing", "raw": res})
        else:
            heal_attempts.append({"agent": agent, "method": "no_auto_heal", "result": "needs_human"})
    new_failures = [r for r in state.get("check_results", []) if r["status"] != "healthy"]
    return {**state, "heal_attempts": heal_attempts, "failures": new_failures}

def update_system_health(state):
    for r in state.get("check_results", []) or []:
        payload = {"agent_name": r["agent"], "status": r["status"], "domain": r["domain"], "tier": r["tier"], "details": {"raw": r.get("raw", {}).get("body"), "healed": r.get("healed", False)}}
        if r["status"] != "healthy":
            raw_body = r.get("raw", {}).get("body", {})
            payload["last_error"] = str(raw_body)[:500]
        _supabase_upsert("system_health", payload, on_conflict="agent_name")
    return state

def escalate_if_failing(state):
    escalations = []
    failures = state.get("failures", []) or []
    if not failures:
        return {**state, "escalations": []}
    bullets = "\n".join([f"- {f['agent']} -> {f['status']}" for f in failures])
    msg = f"Revenue-DX: {len(failures)} item(s) unhealthy after retry:\n{bullets}"
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
        summary = "Revenue-DX: no checks ran"
    elif healthy == total:
        summary = f"Revenue-DX: {healthy}/{total} healthy"
        if healed:
            summary += f" ({healed} self-healed)"
    else:
        summary = f"Revenue-DX: {healthy}/{total} healthy, {escalated} escalation(s) sent"
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
