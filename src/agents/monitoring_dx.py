"""
Monitoring-DX Agent — LangGraph v1
Doctrine §90: Diagnostic+Fix for the Monitoring domain.
Meta-monitoring: ensures the monitoring infrastructure itself is healthy.

Checks:
  1. QC Agent v1 workflow active in n8n
  2. system_health table has recent rows (DX agents are writing)
  3. agent_dispatches table accepting writes (master_orchestrator is running)
  4. activities table accepting writes (any agent writing audit)
"""
from __future__ import annotations
import os, time
from typing import TypedDict, Optional, List
import httpx
from urllib.parse import urlencode
from langgraph.graph import StateGraph, START, END
from datetime import datetime, timezone, timedelta

MMA_OS_FUNCTIONS_BASE = os.environ.get("MMA_OS_FUNCTIONS_BASE", "https://slcqeiqcrhepicqxqjng.supabase.co/functions/v1")
MMA_OS_SUPABASE_URL = os.environ.get("MMA_OS_SUPABASE_URL", "https://slcqeiqcrhepicqxqjng.supabase.co")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
MMA_OS_BRIDGE_API_KEY = os.environ.get("MMA_OS_BRIDGE_API_KEY", "")
N8N_WRITER_API_KEY = os.environ.get("N8N_WRITER_API_KEY", "")

QC_AGENT_WORKFLOW_ID = "gM2HiJy9kCcUtCoe"
RECENT_THRESHOLD_HOURS = 24

class DXState(TypedDict, total=False):
    trigger: str
    check_results: List[dict]
    failures: List[dict]
    heal_attempts: List[dict]
    escalations: List[dict]
    summary: str

def _supabase_get(path, timeout=10.0):
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.get(f"{MMA_OS_SUPABASE_URL}/rest/v1/{path}", headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"})
            return {"status": r.status_code, "body": r.json() if r.text else []}
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
    return _post(f"{MMA_OS_FUNCTIONS_BASE}/mma-os-bridge", {"verb": "push_admin_notification", "category": "monitoring_dx", "severity": severity, "message": message, "metadata": metadata or {}}, MMA_OS_BRIDGE_API_KEY, timeout=10.0)

def run_health_checks(state):
    results = []
    threshold = (datetime.now(timezone.utc) - timedelta(hours=RECENT_THRESHOLD_HOURS)).isoformat()
    
    # Check 1: QC Agent v1 workflow active
    qc_res = _post(f"{MMA_OS_FUNCTIONS_BASE}/n8n-writer", {"verb": "get_workflow", "id": QC_AGENT_WORKFLOW_ID}, N8N_WRITER_API_KEY)
    qc_ok = qc_res["status"] == 200 and qc_res["body"].get("workflow", {}).get("active") is True
    results.append({"agent": "qc_agent_v1_workflow", "domain": "monitoring", "tier": 2, "status": "healthy" if qc_ok else "down", "raw": qc_res})
    
    # Check 2: system_health has recent rows
    res2 = _supabase_get(f"system_health?last_check_at=gte.{threshold}&limit=1&select=agent_name,last_check_at")
    has_recent = res2["status"] == 200 and isinstance(res2["body"], list) and len(res2["body"]) > 0
    results.append({"agent": "system_health_recent", "domain": "monitoring", "tier": 2, "status": "healthy" if has_recent else "down", "raw": {"recent_rows": len(res2["body"]) if isinstance(res2["body"], list) else 0}})
    
    # Check 3: agent_dispatches has recent rows (master_orchestrator firing)
    res3 = _supabase_get(f"agent_dispatches?created_at=gte.{threshold}&limit=1&select=id,created_at")
    has_dispatch = res3["status"] == 200 and isinstance(res3["body"], list) and len(res3["body"]) > 0
    results.append({"agent": "agent_dispatches_recent", "domain": "monitoring", "tier": 2, "status": "healthy" if has_dispatch else "down", "raw": {"recent_rows": len(res3["body"]) if isinstance(res3["body"], list) else 0}})
    
    # Check 4: activities accepting writes (any agent writing audit)
    res4 = _supabase_get(f"activities?created_at=gte.{threshold}&limit=1&select=id,created_at")
    has_activity = res4["status"] == 200 and isinstance(res4["body"], list) and len(res4["body"]) > 0
    results.append({"agent": "activities_recent", "domain": "monitoring", "tier": 2, "status": "healthy" if has_activity else "down", "raw": {"recent_rows": len(res4["body"]) if isinstance(res4["body"], list) else 0}})
    
    return {**state, "check_results": results, "failures": [r for r in results if r["status"] != "healthy"]}

def attempt_self_heal(state):
    heal_attempts = []
    for failure in state.get("failures", []) or []:
        if failure["agent"] == "qc_agent_v1_workflow":
            res = _post(f"{MMA_OS_FUNCTIONS_BASE}/n8n-writer", {"verb": "activate_workflow", "id": QC_AGENT_WORKFLOW_ID}, N8N_WRITER_API_KEY)
            if res["status"] == 200:
                heal_attempts.append({"agent": failure["agent"], "method": "activate_workflow", "result": "healed"})
                for r in state.get("check_results", []):
                    if r["agent"] == failure["agent"]:
                        r["status"] = "healthy"
                        r["healed"] = True
            else:
                heal_attempts.append({"agent": failure["agent"], "method": "activate_workflow", "result": "still_failing"})
        else:
            heal_attempts.append({"agent": failure["agent"], "method": "no_auto_heal", "result": "needs_human"})
    new_failures = [r for r in state.get("check_results", []) if r["status"] != "healthy"]
    return {**state, "heal_attempts": heal_attempts, "failures": new_failures}

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
    msg = f"Monitoring-DX: {len(failures)} item(s) unhealthy:\n{bullets}"
    res = _bridge_alert(msg, severity="warning", metadata={"failures": failures})
    escalations.append({"channel": "telegram_admin", "result": res})
    return {**state, "escalations": escalations}

def summarize(state):
    checks = state.get("check_results", []) or []
    healthy = sum(1 for r in checks if r["status"] == "healthy")
    total = len(checks)
    escalated = len(state.get("escalations", []) or [])
    if healthy == total:
        summary = f"Monitoring-DX: {healthy}/{total} healthy"
    else:
        summary = f"Monitoring-DX: {healthy}/{total} healthy, {escalated} escalation(s) sent"
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
