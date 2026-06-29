# Doctrine S115 - Paige Multi-Tenant Pivot (The SaaS Exit Vehicle Moment)
# Source: Antonio Cook | Codified: 2026-06-29
# Status: CANONICAL. Captures the architectural moment where Paige becomes a true B2B SaaS.

## The pivot

**Paige stops being Antonio's single-org CRM and becomes a multi-tenant SaaS.**

Any qualified buyer (coach, agency, enterprise) can subscribe to the CRM suite, get their own branded workspace, and onboard their consumers underneath their tenant. This is the foundation for the $100M-$1B exit story (Doctrine S72 + S77).

## The new offer catalog

**Tenant-facing offers** (what a buyer subscribes to from us):
| Slug | Name | Price | Limits |
|---|---|---|---|
| crm_coach | Coach Workspace | $97/mo | 1 owner seat + up to 25 customers |
| crm_agency | Agency Workspace | $297/mo | 5 team seats + up to 250 customers |
| crm_enterprise | Enterprise | custom | sales-led |

**Customer-facing offers** (what a tenant enrolls a consumer in):
| Slug | Name | Price |
|---|---|---|
| btf_pif | BTF Pay in Full | $4,997 |
| btf_split | BTF Split | $1,997 down + $1,000 x 3 |
| btf_getstarted | BTF Get-Started | $997 + $497/mo |
| paige_free / paige_starter / paige_growth / paige_scale / paige_enterprise | Paige plan tiers | existing pricing |

**Retired from offer picker (legacy aliases preserved):** btf (generic), premium, vip, accel, launch (LaunchPad slug), and community offerings.

## What this means for MMA OS

### All Paige writes must stamp tenant_id
Every MMA OS write to Paige (via paige-mcp-proxy, paige-mcp-bridge, mma-os-bridge upsert_contact_mirror) now flows through Antonio's tenant_id. Best implementation: the proxy auto-injects tenant_id from the bearer-key context, so MMA OS agents do not need to know about tenancy. Schema-side change is invisible to LangGraph agents.

### Tenant-scoped Paige tables (need tenant_id on all writes)
- clients, deals, pipelines, pipeline_stages, tasks
- paige_coach_assignments, paige_pending_approvals, invitations
- email_send_log, email_templates, paige_conversations
- paige_workflow_runs, paige_audit_log

The 9 BTF lifecycle/stall templates pushed earlier on 2026-06-29 (btf_welcome, btf_intake_reminder, btf_weekly_progress, btf_phase_advance, btf_payment_received, btf_funded, btf_doc_requested, btf_stall_doc, btf_stall_intake) + the 15 BTF Education templates already in production all need to be backfilled to Antonio's tenant_id when Lovable runs the migration.

### User-scoped Paige tables (inherit tenant from clients.tenant_id)
- businesses, credit_*, paige_btf_documents

### RLS layered model
- Platform owner (Antonio) sees all tenants
- Tenant owner/admin sees their tenant only
- Tenant coach/member sees only assigned contacts within their tenant
- Consumer (linked_user_id) sees only their own rows regardless of tenant

### BTF pricing change implications
The customer-facing BTF tiers in the new catalog DIFFER slightly from the BTF Service Agreement v1 skeleton drafted earlier:

OLD (drafted in agreement v1):
- Pay-In-Full: $4,997
- Split: $2,500 + $2,497 Day 30
- Get-Started: $1,000 + $497/mo x 8

NEW (Lovable offer catalog):
- btf_pif: $4,997 (unchanged)
- btf_split: $1,997 down + $1,000 x 3 (CHANGED total still $4,997 but different schedule)
- btf_getstarted: $997 + $497/mo (CHANGED initial down + open-ended monthly)

**BTF Service Agreement v1 needs an amendment to match new pricing before next client signs.** Any clients currently in-flight under the OLD pricing schedule remain grandfathered at their existing terms — handled externally by the founder per Doctrine S116 until the system is fully functional.

### LaunchPad disposition
LaunchPad slug is being dropped from the offer picker but the launchpad_orchestrator agent (Tier 1 Stream #3) is still deployed in LangGraph. Confirm with Antonio whether:
- Option A: Retire launchpad_orchestrator entirely (LaunchPad product sunset)
- Option B: Keep launchpad_orchestrator running for grandfathered LaunchPad subscribers, no new signups
- Option C: LaunchPad becomes a sub-product of a tenant's offering (re-architected later)

### Doctrine cross-references
- **Doctrine S82** (every MMA OS customer write mirrors to Paige) — Now: every MMA OS write mirrors to Paige IN ANTONIO'S TENANT until tenant context is explicitly switched
- **Doctrine S86** (GHL = comms + tags, Paige = pipeline) — Unchanged at the architecture level, but now PER-TENANT in Paige
- **Doctrine S104** (Paige as sales machine for capital professionals) — This pivot REALIZES that vision; the tenant model is how loan officers, brokers, CDFIs get their own workspaces
- **Doctrine S109** (Antonio = MMA OS admin only, Lovable = Paige admin only) — UNCHANGED; tenant migration handled entirely by Lovable
- **Doctrine S114** (Template content/delivery separation) — UNCHANGED; templates still stored in Paige's email_templates table, just now per-tenant. MMA OS pushes to Antonio's tenant by default.
- **Doctrine S116** (Build the system, not the use case) — Customer-specific handling stays external to the system. The system bends for no individual customer.

## Out of scope (Phase 2/3 — NOT being built now)
- Tenant-level custom domains (needs Vercel/Cloudflare wildcard config)
- Per-tenant Stripe Connect (tenants billing their own consumers directly)
- Cross-tenant data export / migration tooling

## Rollout order (Lovable's plan)
1. Offer catalog refactor + legacy aliases (immediate, no schema change)
2. tenants / tenant_members / tenant_invite_tokens migration + backfill Antonio's tenant
3. Add tenant_id to in-scope tables + backfill + RLS rewrite behind feature flag
4. Tenant switcher + Platform/Tenants page (platform-owner only)
5. Workspace settings (brand + invite link) + accept-tenant-invite edge function
6. Stripe products + /get-started page + provision-tenant edge function + webhook sync
7. Flip feature flag, retire legacy single-org policies

## MMA OS-side actions required (parallel to Lovable's work)
1. Confirm with Lovable that paige-mcp-proxy auto-injects tenant_id from the bearer-key context (no MMA OS agent code changes needed)
2. Verify Antonio's tenant_id post-migration; capture in internal_secrets table as ANTONIO_TENANT_ID
3. Update BTF Service Agreement v1 pricing references to match new btf_pif/btf_split/btf_getstarted schedule (deferred to legal_drafting_agent or manual update)
4. Resolve LaunchPad disposition (retire, grandfather, or re-architect)

## Why this moment matters

Multi-tenancy is the line between "founder's tool" and "company that sells software." Before today, Paige was Antonio's internal CRM with a brand. After today, it's a SaaS product with paying tenants and a real ARR ladder ($97 -> $297 -> custom). Every architectural decision from this day forward gets evaluated through "does this work for 1 tenant or 1,000 tenants?"

The exit story is now coherent: capital-professional ICP (Doctrine S104) + multi-tenant SaaS (this doctrine) + cross-system observability (Doctrine S77) + exit-ready posture (Doctrine S72) + generalized system (Doctrine S116).
