"""n8n REST API client — read execution history + workflow metadata."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx


def _client() -> httpx.Client:
    base_url = os.environ["N8N_BASE_URL"].rstrip("/")
    api_key = os.environ["N8N_API_KEY"]
    return httpx.Client(
        base_url=f"{base_url}/api/v1",
        headers={"X-N8N-API-KEY": api_key, "Accept": "application/json"},
        timeout=httpx.Timeout(30.0),
    )


def list_workflows(active_only: bool = True) -> list[dict[str, Any]]:
    """List all workflows visible to this API key. Returns id, name, active, etc."""
    with _client() as c:
        params = {"active": "true"} if active_only else {}
        res = c.get("/workflows", params=params)
        res.raise_for_status()
        data = res.json()
        return data.get("data", [])


def get_workflow(workflow_id: str) -> dict[str, Any]:
    """Fetch one workflow's full definition."""
    with _client() as c:
        res = c.get(f"/workflows/{workflow_id}")
        res.raise_for_status()
        return res.json()


def list_executions(
    *,
    workflow_id: str | None = None,
    status: str | None = None,
    since: datetime | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """List recent executions. status one of: success/error/waiting/running."""
    with _client() as c:
        params: dict[str, Any] = {"limit": limit, "includeData": "false"}
        if workflow_id is not None:
            params["workflowId"] = workflow_id
        if status is not None:
            params["status"] = status
        res = c.get("/executions", params=params)
        res.raise_for_status()
        executions = res.json().get("data", [])
        if since is not None:
            executions = [
                e
                for e in executions
                if datetime.fromisoformat(e["startedAt"].replace("Z", "+00:00")) >= since
            ]
        return executions


def workflow_health_snapshot(
    lookback_hours: int = 24,
) -> list[dict[str, Any]]:
    """Compute per-workflow health for active workflows over the lookback window.

    Returns list of:
      { workflow_id, name, active, expected_cron, last_run_at, success_count,
        error_count, status_summary }
    """
    since = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    workflows = list_workflows(active_only=True)
    snapshot: list[dict[str, Any]] = []

    for wf in workflows:
        wf_id = wf["id"]
        execs = list_executions(workflow_id=wf_id, since=since, limit=50)
        success = sum(1 for e in execs if e.get("status") == "success")
        error = sum(1 for e in execs if e.get("status") == "error")
        last = execs[0] if execs else None
        snapshot.append(
            {
                "workflow_id": wf_id,
                "name": wf.get("name"),
                "active": wf.get("active", False),
                "trigger_count": len(wf.get("triggerCount", []) or []),
                "last_run_at": last.get("startedAt") if last else None,
                "last_status": last.get("status") if last else None,
                "success_count": success,
                "error_count": error,
                "total_runs": len(execs),
            }
        )
    return snapshot
