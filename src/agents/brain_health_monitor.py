"""Brain Health Monitor — daily LangGraph agent.

Reads n8n execution history + Supabase activity log, reasons about workflow
health using Claude, and sends a Telegram digest with anomalies + actions.

Trigger: Cron via LangGraph Platform (recommended 6 AM ET / 10 UTC daily)
Reads:   automations + activities (Supabase via n8n bridge) + n8n /executions
Writes:  activities (records this run via bridge) + Telegram (digest)
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, TypedDict

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph

from src.lib import n8n_client, telegram_client


# ─── Agent state ──────────────────────────────────────────────────────


class BrainHealthState(TypedDict, total=False):
    lookback_hours: int
    n8n_snapshot: list[dict[str, Any]]
    automation_registry: list[dict[str, Any]]
    anomalies: list[dict[str, Any]]
    digest_text: str
    telegram_sent: bool
    run_summary: dict[str, Any]


# ─── Nodes ────────────────────────────────────────────────────────────


def fetch_n8n_health(state: BrainHealthState) -> BrainHealthState:
    """Pull last-24h execution snapshot from n8n."""
    lookback = state.get("lookback_hours", 24)
    snapshot = n8n_client.workflow_health_snapshot(lookback_hours=lookback)
    return {"n8n_snapshot": snapshot}


def fetch_automation_registry(state: BrainHealthState) -> BrainHealthState:
    """Pull the brain's known automations + their declared health.

    Uses the MMA Supabase Bridge in n8n (no direct Supabase auth needed).
    """
    try:
        registry = n8n_client.call_bridge("read_automation_health")
        if not isinstance(registry, list):
            registry = []
    except Exception as exc:  # noqa: BLE001
        print(f"[brain_health_monitor] bridge read_automation_health failed: {exc}")
        registry = []
    return {"automation_registry": registry}


def detect_anomalies(state: BrainHealthState) -> BrainHealthState:
    """Rule-based anomaly detection BEFORE Claude reasoning."""
    anomalies: list[dict[str, Any]] = []
    for wf in state.get("n8n_snapshot", []):
        wf_id = wf.get("workflow_id")
        name = wf.get("name") or wf_id
        if wf.get("last_status") == "error":
            anomalies.append({
                "severity": "high",
                "kind": "last_run_error",
                "workflow_id": wf_id,
                "name": name,
                "detail": f"Last execution failed at {wf.get('last_run_at')}",
            })
        if wf.get("error_count", 0) > 0 and wf.get("success_count", 0) == 0:
            anomalies.append({
                "severity": "high",
                "kind": "fully_failing",
                "workflow_id": wf_id,
                "name": name,
                "detail": f"{wf.get('error_count')} errors / 0 successes in last 24h",
            })
        if wf.get("total_runs", 0) == 0 and wf.get("active"):
            anomalies.append({
                "severity": "medium",
                "kind": "silent_workflow",
                "workflow_id": wf_id,
                "name": name,
                "detail": "Active but no executions in lookback window",
            })
    return {"anomalies": anomalies}


def reason_with_claude(state: BrainHealthState) -> BrainHealthState:
    """Hand snapshot + anomalies to Claude → human-readable digest with judgment."""
    llm = ChatAnthropic(
        model="claude-sonnet-4-6",
        temperature=0.2,
        max_tokens=2000,
    )
    n8n_snap = state.get("n8n_snapshot", [])
    anomalies = state.get("anomalies", [])
    total = len(n8n_snap)
    healthy = sum(1 for w in n8n_snap if w.get("last_status") == "success")

    system_prompt = (
        "You are the Brain Health Monitor for MMA OS (Mogul Maker Academy "
        "Operating System). You audit n8n workflow execution health and produce "
        "a concise Telegram-formatted digest for Antonio Cook.\n\n"
        "Tone: direct, no fluff, operator-grade. Lead with the verdict. "
        "Group anomalies by severity. If everything is healthy, say so plainly "
        "and don't manufacture concern.\n\n"
        "Format: HTML for Telegram. Use <b> for emphasis. No markdown asterisks. "
        "Hard cap 3500 characters."
    )
    user_payload = {
        "totals": {"active_workflows": total, "successful_last_run": healthy},
        "anomalies": anomalies[:25],
        "top_failing": [
            w for w in n8n_snap if w.get("error_count", 0) > 0
        ][:10],
    }
    response = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=(
            "Today is "
            f"{datetime.now(timezone.utc).strftime('%A %B %d, %Y')}. "
            "Generate the Brain Health digest from this data:\n\n"
            f"{user_payload}"
        )),
    ])
    digest = response.content if isinstance(response.content, str) else str(response.content)
    return {"digest_text": digest}


def send_digest(state: BrainHealthState) -> BrainHealthState:
    """Telegram → Antonio. Records run via MMA Supabase Bridge."""
    text = state.get("digest_text", "(no digest)")
    sent = False
    try:
        telegram_client.send_message(text)
        sent = True
    except Exception as exc:  # noqa: BLE001
        try:
            n8n_client.call_bridge("log_activity", payload={
                "type": "agent.brain_health_monitor.telegram_failed",
                "source": "langgraph",
                "data": {"error": str(exc)},
            })
        except Exception:
            pass
    summary = {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "workflows_audited": len(state.get("n8n_snapshot", [])),
        "anomalies_found": len(state.get("anomalies", [])),
        "telegram_sent": sent,
    }
    try:
        n8n_client.call_bridge("log_activity", payload={
            "type": "agent.brain_health_monitor.run",
            "source": "langgraph",
            "data": summary,
        })
    except Exception as exc:  # noqa: BLE001
        print(f"[brain_health_monitor] bridge log_activity failed: {exc}")
    return {"telegram_sent": sent, "run_summary": summary}


# ─── Graph ────────────────────────────────────────────────────────────


def build_graph() -> Any:
    g = StateGraph(BrainHealthState)
    g.add_node("fetch_n8n_health", fetch_n8n_health)
    g.add_node("fetch_automation_registry", fetch_automation_registry)
    g.add_node("detect_anomalies", detect_anomalies)
    g.add_node("reason_with_claude", reason_with_claude)
    g.add_node("send_digest", send_digest)

    g.set_entry_point("fetch_n8n_health")
    g.add_edge("fetch_n8n_health", "fetch_automation_registry")
    g.add_edge("fetch_automation_registry", "detect_anomalies")
    g.add_edge("detect_anomalies", "reason_with_claude")
    g.add_edge("reason_with_claude", "send_digest")
    g.add_edge("send_digest", END)

    return g.compile()


# LangGraph Platform looks for `graph` in the module
graph = build_graph()
