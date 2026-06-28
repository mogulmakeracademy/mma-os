# MMA OS Doctrine Ledger

The canonical record of architectural decisions and operating principles for MMA OS.

Each entry is a **§N: Title** plus a one-paragraph statement. Doctrines are immutable once codified — amendments get a new §N.

---

## §88: The Brain Doesn't Act, It Delegates

The Master Orchestrator NEVER does work itself. It always calls a domain agent. Domain agents NEVER do work themselves — they always call a specialist. Specialists are where actual work happens (sending email, writing to Supabase, calling Paige). This hierarchy gives us quality (specialized prompts), debuggability (clear delegation chain), and extensibility (add a specialist without touching the orchestrator).

## §89: Code Writer Agent Per Location

Every system where we write code or config gets a dedicated child agent that can perform writes WITHOUT Claude driving a browser. GitHub → `github_writer`. n8n → `n8n_writer`. Supabase Edge Functions → `edge_function_writer`. Notion → `notion_writer`. Each is callable by the Master Orchestrator and logs every write to `activities` for audit. This is the operational backbone of Doctrine §88 (the Brain delegates) at the code-mutation layer.

## §90: Diagnostic+Fix Child Per Domain (DX agents)

Every domain orchestrator has a sibling DX child agent that watches the specialists in its domain, detects breakage via known-good test fires, attempts auto-fixes (credential re-attach, kill+restart, state reset), and escalates to the Master + Telegram only when it can't self-heal. DX agents share a `system_health` table. The Master can call any DX agent ad hoc ("Comms DX — is Engine v4.5 healthy?"). Self-healing is a first-class capability, not an afterthought.

---

*Created: 2026-06-28 — first commit via github_writer Edge Function (Doctrine §89 first live deliverable, replaces broken GitHub MCP write path)*
