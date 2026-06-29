# Doctrine S119 - Conversational Control Plane (Natural Language Operates Everything)
# Source: Antonio Cook (directive 2026-06-29)
# Status: CANONICAL. The product north star for PaigeAgent AI: voice/chat drives the platform; the UI is the verify layer.

## The directive

A tenant on PaigeAgent AI should be able to run their entire business from their phone, by voice, through an LLM (Claude, ChatGPT, or any MCP-capable AI). The platform UI exists to SEE and VERIFY what was done — not as the primary interface for DOING.

## The translation stack

| Layer | Role | Why |
|---|---|---|
| LLM client (Claude, ChatGPT, mobile voice) | Translates natural language to MCP tool calls | LLMs are best-in-class at NL parsing |
| Paige MCP | Validates, scopes, and executes against Paige's data + workflows | Single source of truth for the platform's public API |
| Paige Agent AI (in-product skills) | Executes deeper inside the platform when users prefer in-platform chat | Convenience for users who don't connect external LLMs |
| Lovable | Translates natural language to code (building new tools, new platform features) | Same NL skill but applied to the codebase |
| Paige UI | Verify + audit + occasional manual click | Backstop, not primary |

Antonio operates: voice command → Claude (NL → MCP) → Paige MCP → action executed → result visible in Paige UI.
Future tenant operates: voice command → their LLM → their tenant-scoped Paige MCP → action executed within their tenant only.

## What MUST be voice-controllable (i.e., exposed as MCP tools)

Every reversible operation. If a human can do it from the UI, an LLM should be able to do it via MCP. Examples:

- Create + update contacts, deals, tasks, notes
- Move contacts through lifecycle stages and pipeline stages
- Send emails (templated and ad-hoc)
- Send SMS
- Create + send invoices
- Schedule + cancel meetings
- Enroll contacts in workflows / nurture sequences
- Trigger workflows by name
- Read every list view, every detail view, every report
- Create new workflows (voice-build automations)
- Manage Paige Agent AI's own knowledge base and skill configs
- Edit agent prompts and behavior parameters
- View workflow run history, retry failed runs

## What requires CONFIRMATION (not voice-only)

Destructive or financially-significant operations route through paige_pending_approvals first. Examples:

- Delete contact / deal / tenant data
- Refund or void a charge
- Cancel a subscription
- Mass-edit operations affecting >N records
- Permanently remove a workflow that has historical runs
- Anything that crosses out-of-tenant boundary (when master tenant performs cross-tenant ops)

These are NOT excluded from MCP — they're just gated by an approval queue that the requester (or another authorized user) confirms before execution.

## What is NEVER exposed as a sub-tenant MCP tool

Cross-tenant navigation. NO tool should let a sub-tenant tenant_X see, list, switch into, or operate on data inside tenant_Y. Period.

Tools that traverse the tenant boundary (list_tenants, switch_active_tenant, peek_tenant_data) exist ONLY for the platform owner (master tenant Antonio / MMA) and are scope-gated to `platform_owner` role.

This is a SECURITY rule, not a convenience rule. RLS already enforces this at the data layer per Doctrine S115. The MCP tool layer enforces it at the API layer. Two locks.

## The Paige Agent AI brain is itself voice-controllable

Every tenant's instance of Paige Agent AI has:
- A system prompt / personality config
- A knowledge base (rag_documents + future paige_skills)
- A set of skills the in-product agent can execute

These are user-editable data. Therefore they get MCP tools:
- list_paige_skills
- update_paige_skill_config
- list_paige_knowledge_documents
- upsert_paige_knowledge_document
- get_paige_agent_config
- update_paige_agent_config (system prompt, persona, defaults)

So Antonio (via Claude) can voice-edit how Paige Agent AI talks, what it knows, and what it can do. Same for any tenant operating on their own instance.

## Mobile + voice = the actual product

The vision: a capital professional sits in their car at 9pm, says into their phone "Claude, add Maria Lopez as a new BTF lead, source LinkedIn, qualified bucket, assign to Antonio Daniel as coach, send her the BTF intro email."

What happens behind the scenes:
1. Voice → Claude (mobile app)
2. Claude → Paige MCP `create_contact` + `update_lifecycle_stage` + `assign_coach` + `send_btf_template_email`
3. Paige executes against the tenant's data
4. Claude confirms back: "Done — Maria Lopez created in BTF Qualified, Antonio Daniel assigned, BTF intro email queued. Want me to schedule her enrollment call?"
5. The next morning, the tenant sees it all in the Paige UI dashboard, verified.

THAT is the experience. Not clicking through 14 menus. Not learning a CRM. Talking to it.

## What this means for build priorities

Every new platform feature shipped from this point forward MUST consider: "What is the MCP tool surface for this?" alongside "What is the UI for this?"

A feature that exists in UI but has no MCP tool is INCOMPLETE per this doctrine. Add the MCP tool before declaring the feature shipped.

Doctrine S118 (master tenant hardwiring) still applies: MMA OS gets first-class backend automation; sub-tenants get the MCP surface + their own connector platforms (MailChimp, ActiveCampaign). But the MCP surface is the same for all tenants from a voice-control perspective.

## Cross-doctrine consistency

- **Doctrine S104** (Paige Positioning) — operationalized: voice control IS the differentiator from generic CRMs
- **Doctrine S115** (Multi-tenant pivot) — RLS at data layer + tool-absence at MCP layer = two locks against cross-tenant traversal
- **Doctrine S117** (Entity Separation + MCP Control Plane) — extended: MCP is not just inter-system control, it's the user-facing operational surface
- **Doctrine S118** (Master Tenant vs Sub-Tenant Automation) — refined: master tenant gets backend automation hardwiring AND the same MCP surface; sub-tenants get only the MCP surface + their own external automation
- **Doctrine S87** (When an MCP exists for a system, USE it) — extended to: when an operation exists in UI, EXPOSE it as MCP

## Bottom line

The platform isn't a CRM with optional AI. It's an AI-operated business surface where the CRM is the substrate. The UI is the proof. The MCP is the product.
