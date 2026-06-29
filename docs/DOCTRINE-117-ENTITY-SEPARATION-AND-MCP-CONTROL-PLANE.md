# Doctrine S117 - Entity Separation and MCP Control Plane
# Source: Antonio Cook (directive 2026-06-29 post multi-tenant pivot)
# Status: CANONICAL. Foundational rule for how Paige, MMA, and the operator stack relate.

## The directive

Three entities. Cleanly separated. Do not conflate.

1. **PaigeAgent AI** = the CRM SaaS product (multi-tenant, vertical-specific to capital professionals)
2. **Mogul Maker Academy** (MMA) = an operating business that happens to be the FIRST TENANT on PaigeAgent AI
3. **The Operator Stack** (Antonio + Claude + MMA OS LangGraph swarm + n8n) = the team running MMA's offerings on top of PaigeAgent AI

Antonio owns all three but they must be treated as separate companies architecturally.

## PaigeAgent AI ICP (Doctrine S104 restated + sharpened)

PaigeAgent AI is built for capital professionals - any finance pro who services clients with money-related needs:
  - Loan officers (residential + commercial)
  - Commercial loan brokers
  - Credit specialists / credit repair professionals
  - CDFIs (Community Development Financial Institutions)
  - Auto industry F&I managers
  - Independent financial advisors
  - Credit unions

MMA happens to be in this category (business credit + funding through BTF). But MMA is one customer of Paige - not the reason Paige exists. Paige exists to serve every capital professional like Antonio.

## What lives where

| Concern | Lives in | Why |
|---|---|---|
| Generic multi-tenant CRM features (pipelines, contacts, deals, RLS, billing, storefront, branding, invites) | **Paige codebase (Lovable)** | These work for ANY capital professional |
| MMA-specific workflows, automations, agents, decision logic | **MMA OS (mma-os repo, LangGraph swarm, n8n)** | This is MMA's brain. Other tenants will build their own brains. |
| MMA's data + brand + offers + signed agreements + tenant config | **MMA tenant inside Paige** (as ROWS, not code) | Configured at the tenant level. Other tenants store their own at their tenant level. |

## Hard-coding rules

### Paige codebase (Lovable)
**NEVER hard-code MMA-specific anything.** Build for the generic capital professional ICP. If a Paige feature would only make sense for MMA, that feature does not belong in Paige - it belongs in MMA OS or as configurable tenant settings.

Examples of what NOT to hard-code in Paige:
  - MMA offers (BTF tiers, Paige consumer tiers) - these come from tenant_products / tenant_prices
  - MMA branding (Navy/Gold, Bookman, portal.mogulmakeracademy.com) - these come from tenants.brand
  - MMA workflows (BTF Education Engine, BTF Stall Detector, Skool Nurture) - these live in MMA OS
  - MMA staff (coaches, admins) - these are tenant_members rows
  - Any phrase like "we sell BTF" or "Mogul Maker Academy is our company"

### MMA OS (Antonio's operator stack)
**CAN hard-code MMA-specific workflows + automations + agents** because that is MMA OS's purpose. MMA OS exists to run MMA's business. It is the brain of the FIRST tenant.

Still bound by Doctrine S116 - no hard-coded customer or staff names. Only Antonio's name appears.

### MMA tenant data
**Configured, not hard-coded.** Products, branding, automations-triggered-from-Paige, all live as data in Paige tables under MMA's tenant_id. Editable in the admin UI like any other tenant would edit theirs.

## Email + domain defaults (per Antonio 2026-06-29)

**Platform default**: paigeagent.ai (notify@paigeagent.ai for transactional, system-level emails). Every new tenant gets this out of the box. Mirrors how GoHighLevel / LeadConnector default to gohighlevel.com until the tenant connects their own domain.

**MMA tenant override**: portal.mogulmakeracademy.com (alerts@portal.mogulmakeracademy.com). This is the MMA tenant's custom sender configured in tenants.brand. When MMA sends, MMA's domain appears. When other tenants send, their domain (or paigeagent.ai default) appears.

The tenant_sender_identity() SQL helper already does this correctly per Lovable's Part 3a build.

## MCP Control Plane (the future architecture)

Eventually, MMA OS will NOT write to Paige's Supabase directly. Instead:

  - MMA OS LangGraph agents and n8n workflows will call Paige MCP over OAuth 2
  - The MCP becomes the public API contract between any tenant's automation layer and Paige
  - MMA is the first user of this contract. Future tenants will use the same contract with their own OAuth 2 credentials
  - Paige stays genuinely tenant-agnostic because every consumer (including MMA OS) uses the same MCP surface

**Why MCP control plane wins**:
  1. Forces Paige's API to be coherent enough for external developers (not just internal team)
  2. Makes Paige a real product, not Antonio's private CRM
  3. Other tenants can build their own automation layers without needing Supabase access
  4. Cleaner security model - OAuth 2 scopes per tenant vs shared bearer keys

## Migration path: from current state to MCP-first

**Current state (transitional)**: MMA OS writes directly to Paige Supabase via service-role keys + paige-mcp-proxy. This is fine for now because Paige has one tenant.

**Future state (post-MCP)**: MMA OS authenticates to Paige MCP via OAuth 2. Every Paige write goes through the MCP. The paige-mcp-proxy Edge Function may still exist as a convenience wrapper, but the underlying contract is OAuth 2 + MCP, not Supabase admin access.

**When to migrate**: When Antonio is ready to onboard the second tenant. Until then, the current direct-access pattern works because MMA is the only consumer. The MCP migration is the line between "single-tenant SaaS" and "true SaaS."

## What this means for Claude (me)

1. When I work on Paige codebase changes (via Lovable), I am building for the capital-professional ICP, not for MMA. MMA needs are a subset.
2. When I work on MMA OS, I am building for MMA specifically. Hard-coded MMA workflows are correct here.
3. When I read code in either codebase, I evaluate it against this separation. If MMA logic shows up in Paige code, that is a violation of S117 and should be moved.
4. The eventual goal is MCP control - I will operate Paige via OAuth 2 + MCP, not via direct Supabase access. Currently the access path is transitional.

## Cross-doctrine consistency

- **Doctrine S104** (Paige Positioning) — sharpened: PaigeAgent AI for capital professionals as the ICP, MMA is one such professional
- **Doctrine S109** (Antonio = MMA OS admin only, Lovable = Paige admin only) — UNCHANGED, MCP migration further enforces this boundary
- **Doctrine S114** (Template content/delivery separation) — UNCHANGED, MMA OS owns content, Paige stores+delivers
- **Doctrine S115** (Multi-tenant pivot) — operationalized: this doctrine explains WHO each tenant is and how Paige stays agnostic
- **Doctrine S116** (Build the system, not the use case) — extended: the principle now applies at the entity level. Paige is built for the ARCHETYPE of capital professional, not for the SPECIFIC tenant MMA.

## Bottom line

PaigeAgent AI is a product Antonio is selling. Mogul Maker Academy is a business Antonio is running. They both happen to be his. They are not the same thing. Code, doctrines, and decisions reflect that separation at every level.
