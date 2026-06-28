"""Monitoring-DX v1.1 — URL-encode timestamps, simplified table-recency checks."""
from __future__ import annotations
import os, time
from typing import TypedDict, Optional, List
from urllib.parse import quote
import httpx
from langgraph.graph import StateGraph, START, END
from datetime import datetime, timezone

MMA_OS_FUNCTIONS_BASE = os.environ.get("MMA_OS_FUNCTIONS_BASE", "https://slcqeiqcrhepicqxqjng.supabase.co/functions/v1")
MMA_OS_SUPABASE_URL = os.environ.get("MMA_OS_SUPABASE_URL", "https://slcqeiqcrhepicqxqjng.supabase.co")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
MMA_OS_BRIDGE_API_KEY = os.environ.get("MMA_OS_BRIDGE_API_KEY", "")
N8N_WRITER_API_KEY = os.environ.get("N8N_WRITER_API_KEY", "")
QC_WORKFLOW_ID = "gM2HiJy9kCcUtCoe"
RECENT_HOURS = 24

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

def _supabase_get_count(table, time_col=None, hours_back=24):
    """Get count of rows. If time_col set, filter to last N hours. Uses Prefer header for exact count."""
    if not SUPABASE_SERVICE_ROLE_KEY: return {"ok": False, "count": 0}
    try:
        with httpx.Client(timeout=10.0) as client:
            url = f"{MMA_OS_SUPABASE_URL}/rest/v1/{table}?limit=1"
            if time_col:
                threshold = (datetime.now(timezone.utc) - __import__('datetime').timedelta(hours=hours_back)).isoformat()
                url += f"&{time_col}=gte.{quote(threshold)}"
            r = client.get(url, headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}", "Prefer": "count=exact"})
            count = 0
            cr = r.headers.get("content-range", "")
            if "/" in cr:
                try: count = int(cr.split("/")[-1])
                except Exception: count = 0
            return {"ok": r.status_code < 300, "count": count, "status": r.status_code}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "count": 0}

def _supabase_upsert(table, payload, on_conflict):
    if not SUPABASE_SERVICE_ROLE_KEY: return {"ok": False}
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.post(f"{MMA_OS_SUPABASE_URL}/rest/v1/{table}?on_conflict={on_conflict}", headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}", "Content-Type": "application/json", "Prefer": "return=representation,resolution=merge-duplicates"}, json=payload)
            return {"ok": r.status_code < 300}
    except Exception: return {"ok": False}

def _bridge_alert(msg, sev="warning", meta=None):
    return _post(f"{MMA_OS_FUNCTIONS_BASE}/mma-os-bridge", {"verb": "push_admin_notification", "category": "monitoring_dx", "severity": sev, "message": msg, "metadata": meta or {}}, MMA_OS_BRIDGE_API_KEY)

def run_health_checks(state):
    results = []
    qc_res = _post(f"{MMA_OS_FUNCTIONS_BASE}/n8n-writer", {"verb": "get_workflow", "id": QC_WORKFLOW_ID}, N8N_WRITER_API_KEY)
    qc_ok = qc_res["status"] == 200 and qc_res["body"].get("workflow", {}).get("active") is True
    results.append({"agent": "qc_agent_v1_workflow", "domain": "monitoring", "tier": 2, "status": "healthy" if qc_ok else "down", "raw": qc_res})
    sh = _supabase_get_count("system_health", "last_check_at", RECENT_HOURS)
    results.append({"agent": "system_health_recent", "domain": "monitoring", "tier": 2, "status": "healthy" if sh.get("count", 0) > 0 else "down", "raw": {"recent_rows": sh.get("count", 0)}})
    ad = _supabase_get_count("agent_dispatches", "created_at", RECENT_HOURS)
    results.append({"agent": "agent_dispatches_recent", "domain": "monitoring", "tier": 2, "status": "healthy" if ad.get("count", 0) > 0 else "down", "raw": {"recent_rows": ad.get("count", 0)}})
    # activities is fine if accessible even with 0 rows (some agents log via bridge, not directly)
    ac = _supabase_get_count("activities")
    results.append({"agent": "activities_table_accessible", "domain": "monitoring", "tier": 2, "status": "healthy" if ac.get("ok") else "down", "raw": {"accessible": ac.get("ok"), "total_rows": ac.get("count")}})
    return {**state, "check_results": results, "failures": [r for r in results if r["status"] != "healthy"]}

def attempt_self_heal(state):
    heal = []
    for f in state.get("failures", []) or []:
        if f["agent"] == "qc_agent_v1_workflow":
            res = _post(f"{MMA_OS_FUNCTIONS_BASE}/n8n-writer", {"verb": "activate_workflow", "id": QC_WORKFLOW_ID}, N8N_WRITER_API_KEY)
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
    return {**state, "escalations": [{"channel": "telegram_admin", "result": _bridge_alert(f"Monitoring-DX v1.1: {len(failures)} item(s) unhealthy:\n{bullets}", "warning", {"failures": failures})}]}

def summarize(state):
    checks = state.get("check_results", []) or []
    healthy = sum(1 for r in checks if r["status"] == "healthy")
    total = len(checks)
    esc = len(state.get("escalations", []) or [])
    return {**state, "summary": f"Monitoring-DX v1.1: {healthy}/{total} healthy" + ("" if healthy == total else f", {esc} escalation(s)")}

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
