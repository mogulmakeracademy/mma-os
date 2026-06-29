# Doctrine S109 - Paige Supabase Access Boundary
# Source: Antonio Cook | Codified: 2026-06-29
# Status: CANONICAL PERMANENT RULE. Locks the access boundary between MMA OS infra and Paige infra.

## The rule

**Antonio has admin on MMA OS Supabase only (project slcqeiqcrhepicqxqjng).**
**Lovable has admin on Paige Supabase only (project bfmyebsjyuoecmjskqhs).**
**Antonio does NOT have access to Paige Supabase.**
**Lovable does NOT have access to MMA OS Supabase.**

## What this means in practice

ANY change on the Paige side (secrets, schema, RLS, Edge Functions, database, env vars) MUST be routed through Lovable via the project chat at https://lovable.dev/projects/65f20d64-d5a9-4b15-bc8d-3f11f7921f16

Claude should NEVER tell Antonio to:
  - "Go to Paige Supabase dashboard and add/set..."
  - "Open Paige Edge Function secrets and paste..."
  - "Run this SQL in Paige Supabase..."
  - Click any URL pointing at https://supabase.com/dashboard/project/bfmyebsjyuoecmjskqhs/...

Claude SHOULD tell Antonio to:
  - "Paste this into Lovable Paige chat with the instruction: ..."
  - "Ask Lovable to set the secret as ..."
  - "Ask Lovable to apply the migration ..."

## How values move between systems

When MMA OS needs to share a value (API key, config) with Paige:
  1. Antonio (or Claude on Antonio behalf) prepares the value
  2. Antonio pastes the value into Lovable Paige project chat with set-secret instruction
  3. Lovable sets the value in Paige Supabase and confirms
  4. Claude verifies on MMA OS side via Paige MCP proxy (which uses the now-set key)

When Paige needs a value from MMA OS:
  1. Lovable requests the value via Paige project chat or MCP-to-MCP message
  2. Antonio sees the request, retrieves the value, pastes to Lovable
  3. Lovable sets it on Paige side

## Why this matters

  - Preserves single source of truth for who can change what
  - Audit trail: every Paige change has a Lovable chat message backing it
  - Reduces "did I do that or did the other one do that" confusion
  - Safety: limits blast radius if either side credentials are compromised

## Complements Doctrine S53 (Brand Identity Stack)

S53 codifies that all production infra lives on mogulmakeracademy@gmail.com.
S109 codifies WHO operates each piece of that infra on Antonio behalf.
  - MMA OS Supabase: Antonio + Claude (mma-os-bridge, github-writer, langgraph agents, etc.)
  - Paige Supabase: Lovable (Paige Agent AI platform code + secrets)
  - Both are Antonio property; different operators with different daily-driver responsibilities.

## When this rule applies vs. does not

  - **Applies:** Paige Supabase config, Paige Edge Function secrets, Paige database schema, Paige MCP tool definitions, Paige RLS policies, Paige email_templates content management
  - **Does not apply:** Paige MCP tool USAGE (any agent can call any Paige MCP tool via paige-mcp-proxy with MMA_OS_BRIDGE_API_KEY auth — this is read-only-to-Lovable from her perspective, just normal API consumption)
