# Doctrine S118 - Master Tenant vs Sub-Tenant Automation Capability
# Source: Antonio Cook (directive 2026-06-29)
# Status: CANONICAL. Defines what MMA (master tenant) gets that other Paige tenants do NOT get.

## The directive

Mogul Maker Academy is the MASTER TENANT on PaigeAgent AI. Every other tenant is a SUB-TENANT. These two categories get fundamentally different automation capabilities, and Paige is designed around that distinction.

## The principle

**Master tenant gets hardwired backend automation. Sub-tenants connect their own automation via external platforms.**

Paige does NOT bundle a workflow engine for every tenant. Each tenant brings their own automation platform (MailChimp, ActiveCampaign, Make, Zapier, self-hosted n8n, etc.) and connects via Paige's webhooks, MCP, or OAuth 2 surfaces. Paige stays lean by not trying to be everything to everyone.

## What the MASTER TENANT (MMA) gets

- Direct LangGraph swarm wired to Paige's backend via Edge Function env vars (LANGGRAPH_BASE_URL, LANGGRAPH_API_KEY)
- Direct n8n workflows registered in paige_workflow_registry, dispatchable from Paige's run_workflow MCP
- Direct edge function callouts to MMA OS infrastructure (paige-mcp-proxy, mma-os-bridge, github-writer, etc.)
- Provider field in workflow registry can be 'langgraph', 'n8n', 'direct_edge_function' — all hardwired
- Full visibility into queued/running/succeeded/failed workflow state via paige_workflow_runs

This is operationally identical to how GoHighLevel HQ has direct DB + automation access to GHL's own infrastructure, while customer agencies on GHL use GHL's surface.

## What SUB-TENANTS get

- Paige UI + Paige API + Paige MCP (all the public product surface)
- Webhook endpoints they can POST to (e.g. their MailChimp completes a flow, sends to Paige)
- OAuth 2 connections to their own external automation platforms
- Their own MCP integration if they want to drive Paige from their own LLM
- NO direct env-var wired backend access. NO ability to register a 'langgraph' or 'n8n' provider that calls infrastructure they don't own.

Sub-tenants build their automation in their world (whatever platform they choose) and connect via Paige's public surface. Paige is the orchestrator + data layer; the sub-tenant's automation tool is their muscle.

## Why this division wins

1. **Paige stays lean as a product.** No need to ship a workflow engine, run cron infrastructure for every tenant, or maintain integration depth with 50+ automation platforms inside Paige. Each tenant brings their own.

2. **Master tenant gets velocity.** MMA can ship complex multi-system automation (LangGraph + n8n + Supabase + GHL + Skool + Telegram) because we ARE the platform builders. That's our advantage as the master tenant during the build phase.

3. **Sub-tenants get freedom.** A coach who lives in MailChimp doesn't have to learn n8n. A broker who runs ActiveCampaign doesn't have to migrate. They use Paige for CRM + client management + tenant-aware sending, and keep their existing automation stack.

4. **Doctrine S117 compliance.** Paige stays tenant-agnostic in its codebase. MMA-specific automation lives in MMA OS, outside Paige's repo. Sub-tenants' automation lives in their own platforms, outside Paige's repo. Paige is the connective tissue, not the muscle.

## What this means for new integrations

When Antonio (or future engineering team) adds support for a new sub-tenant automation platform — MailChimp, ActiveCampaign, Make, Zapier, etc. — the work is:

- Add an OAuth 2 connection card in Paige's tenant settings
- Build the webhook bridge (Paige fires events to the tenant's platform, OR receives events from it)
- Register provider type if needed (probably 'webhook_external' or per-platform like 'mailchimp')

NOT: bundle a workflow engine inside Paige for that tenant.

## The Paige-as-GoHighLevel analogy

GoHighLevel = platform. Their HQ has direct access to their infrastructure.
Agencies on GHL = tenants. They use GHL's UI + API + webhooks; they don't get GHL's direct DB.

PaigeAgent AI = platform. MMA HQ (us) has direct access to Paige + MMA OS LangGraph/n8n hardwired in.
Coaches/brokers on Paige = sub-tenants. They use Paige's UI + API + MCP + webhooks; they don't get MMA OS's LangGraph.

Same model, our product.

## What the dispatcher behavior in run_workflow reflects

When run_workflow is called with a langgraph- or n8n-provider workflow:
- Master tenant context: dispatcher reads LANGGRAPH_BASE_URL / N8N_BASE_URL from env, calls out, gets execution_id back
- Sub-tenant context (future): dispatcher should reject or route to the tenant's own connected external platform

This means provider field 'langgraph' and 'n8n' are implicitly master-tenant-only providers. Sub-tenant workflow registry entries should use provider 'webhook_external', 'mailchimp', 'zapier', etc. — never 'langgraph' or direct 'n8n' against MMA infrastructure.

Lovable should enforce this when sub-tenants onboard: their workflow registry rows cannot use master-tenant-reserved providers.

## Cross-doctrine consistency

- **Doctrine S104** (Paige Positioning as sales machine for capital pros) — UNCHANGED, still the product north star
- **Doctrine S109** (Antonio = MMA OS admin only, Lovable = Paige admin only) — UNCHANGED, access boundaries respected
- **Doctrine S115** (Multi-tenant pivot) — extended: not just any tenant, but TIERED tenants with master + sub categories
- **Doctrine S116** (Build the system, not the use case) — UNCHANGED, master tenant special-casing is at the CAPABILITY layer, not the CODE layer (Paige codebase stays tenant-agnostic)
- **Doctrine S117** (Entity Separation + MCP Control Plane) — sharpened: this doctrine adds the implementation detail of WHAT each tenant category gets

## Bottom line

We are the master tenant. We get hardwired backend access because we built the backend. Sub-tenants get tenant surface access plus connectors to their own platforms. Paige stays lean. MMA stays fast. Sub-tenants stay independent.
