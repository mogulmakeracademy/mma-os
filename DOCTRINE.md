# MMA OS Doctrine Ledger

The canonical record of architectural decisions and operating principles for MMA OS.

Each entry is a **§N: Title** plus a one-paragraph statement. Doctrines are immutable once codified — amendments get a new §N.

---

## §88: The Brain Doesn't Act, It Delegates

The Master Orchestrator NEVER does work itself. It always calls a domain agent. Domain agents NEVER do work themselves — they always call a specialist. Specialists are where actual work happens (sending email, writing to Supabase, calling Paige). This hierarchy gives us quality (specialized prompts), debuggability (clear delegation chain), and extensibility (add a specialist without touching the orchestrator).

## §89: Code Writer Agent Per Location

Every system where we write code or config gets a dedicated child agent that can perform writes WITHOUT Claude driving a browser. GitHub → `github_writer`. n8n → `n8n_writer`. Supabase Edge Functions → `edge_function_writer`. Notion → `notion_writer`. LangGraph → `langgraph_bridge` (fire_agent verb). Each is callable by the Master Orchestrator and logs every write to `activities` for audit. This is the operational backbone of Doctrine §88 (the Brain delegates) at the code-mutation layer.

**Status: COMPLETE — 2026-06-29.** All 5 writers LIVE + verified:
- `github-writer` v1 (commit 401b1db proves write path)
- `n8n-writer` v1 (enumerated 100 workflows, 55 active)
- `notion-writer` v1 (Notion Integration MMA reachable)
- `edge-function-writer` v7 (deployed itself via Supabase Mgmt API)
- `langgraph-bridge` v1 (3 LangGraph agents discoverable: customer_memory, contact_sync, brain_health_monitor)

## §90: Diagnostic+Fix Child Per Domain (DX agents)

Every domain orchestrator has a sibling DX child agent that watches the specialists in its domain, detects breakage via known-good test fires, attempts auto-fixes (credential re-attach, kill+restart, state reset), and escalates to the Master + Telegram only when it can't self-heal. DX agents share a `system_health` table. The Master can call any DX agent ad hoc ("Comms DX — is Engine v4.5 healthy?"). Self-healing is a first-class capability, not an afterthought.

## §91: Supabase Secret Naming — Avoid Reserved Prefixes

Supabase Functions Secrets reject any name starting with `SUPABASE_` (reserved for system-managed: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_ANON_KEY, etc.). For our own Supabase Management API token, canonical name is **`SUPA_MGMT_TOKEN`**. Edge Functions that need this token MUST implement a multi-name fallback chain (SUPA_MGMT_TOKEN → SUPA_MANAGEMENT_TOKEN → MGMT_TOKEN → SB_MGMT_TOKEN) and report which name was found in their `health` response. This is a once-and-only mistake — we never deploy code that hardcodes a single SUPABASE_-prefixed env var name for a user-provided secret again.

## §92: Server-Side Verification via get_logs, Test Fires via Chrome

Two different verification jobs require two different tools:
- **Inspecting production traffic / past invocations** → Supabase MCP `get_logs` (server-side, no outbound call needed, shows all status codes + timing across functions)
- **Firing a NEW test request to see response body** → Chrome JS fetch (because Cowork sandbox cannot make outbound HTTPS to Supabase)

Never use Chrome when get_logs answers the question, never use get_logs when you need to see a JSON response body. Both tools have a permanent place in the verification toolkit.

---

*Last updated: 2026-06-29 — §91 + §92 added autonomously via github_writer Edge Function. The writer agents are now codifying doctrine about themselves. Full loop closed.*
