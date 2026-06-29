# Doctrine S108 - Alert Routing Rule
# Source: Antonio Cook | Codified: 2026-06-28
# Status: CANONICAL. Overrides default Telegram-first behavior of all agents.

## The principle

**Telegram is for sales, revenue, and "is the system working" health pings. Not for everything.**
**Email is the default channel for everything else** - Antonio email is connected to every platform and easy to scan in batch.
**In-portal notifications are for customers** (BTF clients, Paige users) - not for internal team alerts.

## Routing matrix

| Signal type | Channel | Examples |
|---|---|---|
| **New sale / payment received** | Telegram | BTF close, LaunchPad signup with conversion, Premium upgrade, payment installment received |
| **Hot lead / BTF qualified** | Telegram | sales_dept handle_new_lead with BTF_QUALIFIED tag, escalate_hot_lead |
| **Revenue milestone** | Telegram | MRR threshold hit, daily/weekly revenue summary, monthly close |
| **System failure / outage** | Telegram | Edge Function 500s, LangGraph deployment errors, bridge timeouts, agent crashes |
| **Critical customer issue** | Telegram | BTF client at exec-review threshold (>150 days), urgent support escalation, refund request |
| **Routine ops digest** | Email | operations_dept morning brief, stall detector daily sweep (with stalls), QC agent runs |
| **Education sends / campaign fires** | Email | BTF education drip digest, Skool nurture sends, campaign completions |
| **Daily/weekly system health** | Email | brain_health_monitor, agent_calls summary, audit log digest |
| **Customer touchpoints** | In-portal + email | BTF client phase advance, doc request, intake reminder (handled by Paige+Resend per S105) |

## What this changes for existing agents

Many agents currently default to Telegram. They need to be retrofitted:

| Agent | Currently fires | Should fire |
|---|---|---|
| operations_department.morning_brief | Telegram | Email (daily 7 AM ET digest) |
| btf_stall_detector (zero-stall days) | Telegram heartbeat | Silent (only Telegram if stalls detected) |
| btf_stall_detector (stalls detected) | Telegram | Telegram (KEEP - that is the value) |
| btf_education_engine.daily_digest | Telegram | Email (daily digest of what sent / would have sent) |
| quality_check_agent (every 15 min runs) | Telegram on errors | Email weekly summary + Telegram only on failure |
| brain_health_monitor | Telegram digest | Email daily, Telegram only on degraded health |
| sales_dept.daily_sales_brief | Telegram | Telegram (KEEP - revenue-relevant) |
| sales_dept.handle_new_lead BTF_QUALIFIED | Telegram | Telegram (KEEP - hot lead) |
| sales_dept.handle_new_lead EXPLORER/LAUNCHPAD | Telegram | Email (not urgent) |
| sales_dept.log_btf_close | Telegram | Telegram (KEEP - revenue moment) |
| sales_dept.record_btf_payment | Telegram | Telegram (KEEP - revenue moment) |
| sales_dept.advance_btf_phase | Telegram | Email (operational, not revenue) |
| customer_memory_agent profile creates | Telegram | Email weekly summary |
| ghl_webhook_receiver routine events | Telegram | Silent (logged only) |

## Implementation note

Until comms_orchestrator has an `internal_email` task wired (TBD next session), agents that should be silenced from Telegram per this rule will be patched to:
  - Log the event to agent_calls (already happens)
  - Skip the comms_orchestrator.send_telegram call
  - When email channel is built: switch to `send_internal_email` task

## What does NOT change

  - Customer-facing comms (BTF emails, Skool nurture, LaunchPad onboarding) - those follow Doctrine S105 (per-product send layer) unchanged
  - Antonio Telegram chat ID 5188669161 remains the destination for ALL Telegram fires
  - Telegram critical signals stay loud - the goal is reducing NOISE, not silencing real urgency

## The litmus test for any new agent

Before firing Telegram, ask: "Does Antonio need to know this RIGHT NOW because money is moving or the system is broken?"
  - YES -> Telegram
  - NO -> Email digest (batched) or silent (logged only)
