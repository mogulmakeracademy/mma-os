# MMA OS Doctrine Ledger

The canonical record of architectural decisions and operating principles for MMA OS.

Each entry is a **§N: Title** plus a one-paragraph statement. Doctrines are immutable once codified — amendments get a new §N.

---

## §88: The Brain Doesn't Act, It Delegates

The Master Orchestrator NEVER does work itself. It always calls a domain agent. Domain agents NEVER do work themselves — they always call a specialist. Specialists are where actual work happens (sending email, writing to Supabase, calling Paige). This hierarchy gives us quality (specialized prompts), debuggability (clear delegation chain), and extensibility (add a specialist without touching the orchestrator).

**Status: LIVE — 2026-06-29.** master_orchestrator (Tier 0) + comms_orchestrator (Tier 1) + comms_dx (DX) deployed on LangGraph Platform revision 9e9f7c78.

## §89: Code Writer Agent Per Location

Every system where we write code or config gets a dedicated child agent that can perform writes WITHOUT Claude driving a browser. GitHub → github_writer. n8n → n8n_writer. Supabase Edge Functions → edge_function_writer. Notion → notion_writer. LangGraph → langgraph_bridge (fire_agent verb). Each is callable by the Master Orchestrator and logs every write to activities for audit.

**Status: COMPLETE — 2026-06-29.** All 5 writers LIVE + verified.

## §90: Diagnostic+Fix Child Per Domain (DX agents)

Every domain orchestrator has a sibling DX child agent that watches the specialists in its domain, detects breakage via known-good test fires, attempts auto-fixes (credential re-attach, kill+restart, state reset), and escalates to the Master + Telegram only when it can't self-heal. DX agents share a system_health table. Self-healing is a first-class capability, not an afterthought.

**Status: LIVE — 2026-06-29.** comms_dx v2 deployed, monitors 5 writer agents every fire. Doctrine §93 collision fix applied.

## §91: Supabase Secret Naming — Avoid Reserved Prefixes

Supabase Functions Secrets reject any name starting with SUPABASE_ (reserved for SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_ANON_KEY, etc.). For our own Supabase Management API token, canonical name is **SUPA_MGMT_TOKEN**. Edge Functions that need this token MUST implement a multi-name fallback chain (SUPA_MGMT_TOKEN → SUPA_MANAGEMENT_TOKEN → MGMT_TOKEN → SB_MGMT_TOKEN) and report which name was found in their health response.

## §92: Server-Side Verification via get_logs, Test Fires via Chrome

Two different verification jobs require two different tools:
- **Inspecting production traffic / past invocations** → Supabase MCP get_logs (server-side, no outbound call needed, shows all status codes + timing across functions)
- **Firing a NEW test request to see response body** → Chrome JS fetch (because Cowork sandbox cannot make outbound HTTPS to Supabase)

Never use Chrome when get_logs answers the question, never use get_logs when you need to see a JSON response body. Both tools have a permanent place in the verification toolkit.

## §93: Env Var Collision Avoidance — System-Prefixed Names Only

LangGraph Platform env vars are SHARED across every agent in the same deployment. Generic names like SUPABASE_URL, API_BASE_URL, BRIDGE_URL get clobbered by whichever agent's config was loaded first — and the collision is silent (you discover it at runtime when calls hit the wrong host with 404s). **RULE:** every agent reads system-specific env vars only. Our mma-os Supabase URL: MMA_OS_FUNCTIONS_BASE / MMA_OS_SUPABASE_URL. Paige's Supabase URL: PAIGE_BRIDGE_URL. GHL: GHL_BASE_URL. n8n: N8N_BASE_URL. Every system gets its own prefix. Hardcode the canonical default in code so the agent still works if the env var is missing entirely. Discovered via comms_dx v1 calling /functions/v1/n8n-writer on Paige's project (404) — fixed in v2.

## §94: LLM Call Resilience — Heuristic Fallback Always

Any agent that calls an LLM for classification, routing, or extraction MUST have a heuristic fallback path. Triggers for fallback: HTTP error from API, empty content blocks (most common — Anthropic returns 200 with empty content on certain malformed prompts), non-JSON response, response that doesn't parse as expected, network timeout. Heuristic should produce a reasonable answer (even at low confidence) so the system never fails entirely on routing — degraded routing beats no routing. Always surface the LLM error in the reasoning field so debugging is one trace inspection away. Discovered via master_orchestrator v1 returning unknown with confidence 0.0 on every fire because Anthropic returned empty content — fixed in v2.

## §95: Cross-Graph Context Propagation

When a Tier-N agent dispatches to a Tier-N+1 agent via langgraph-bridge fire_agent, the child's input MUST receive parent_dispatch_id, source, and actor from the parent. Each tier writes its own row to agent_calls with parent_dispatch_id FK pointing back to the master agent_dispatches row. This builds the complete audit chain: agent_dispatches (Tier 0) ← agent_calls (Tier 1) ← agent_calls (Tier 2) ← agent_calls (Tier 3). Without this, debugging "why did this fail at Tier 2?" requires manual log archeology across multiple LangGraph threads. With it, one SQL query joining agent_dispatches → agent_calls by parent_dispatch_id gives the full delegation tree.

---

*Last updated: 2026-06-29 — §93 + §94 + §95 added autonomously via github_writer Edge Function. Every bug we hit becomes a doctrine; every doctrine compounds the team's skill. Skills training built into the build.*
