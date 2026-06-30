# Doctrine §126 — Federation Boundary Between Paige Sub-Agents and MMA OS LangGraph Agents (v1)

**Codified:** 2026-06-29 — **v1, open to amendment**
**Trigger:** Paige sub-agent roster reached 12 (11 original + funnel-architect first §124 Factory shipment) with MMA OS LangGraph roster at 7 DX agents + 3 department heads + 4 standalone agents. Without a federation boundary, the two platforms will duplicate work across client-facing intelligence and business-wide brain — wasted engineering, conflicting answers when both layers handle the same domain, and unclear ownership when bugs surface.

---

## The Principle

A two-platform architecture where one platform sits per-tenant (Paige) and the other sits cross-tenant (MMA OS) MUST have an explicit federation boundary. The boundary answers the question: **for any given user intent, which platform owns the answer?**

The wrong answer is "whichever was built first" or "whichever the developer remembers." The right answer is a doctrine that maps capabilities to platforms based on architectural fit, not historical accident.

This doctrine is **v1**. It captures the recommendation as of 2026-06-29. Antonio retains authority to amend specific tier assignments; the framework itself (3-tier classification, default-to-Paige for client-facing) is the persistent contribution.

---

## The Three-Tier Classification

### Tier A — Paige Sub-Agents are Canonical (deprecate MMA OS overlap)

These capabilities live entirely on the Paige side. MMA OS equivalents (where they exist) should be deprecated or scoped to business-wide cousin work only.

| Capability | Paige sub-agent | MMA OS overlap action |
|---|---|---|
| Fundability check on a client | `fundability-diagnostician` | none — no overlap |
| Data consistency 7-channel audit | `data-consistency-auditor` | none — no overlap |
| Legal/compliance review of client-facing language | `legal-compliance-reviewer` | none — no overlap |
| Business credit tradeline strategy | `business-credit-strategist` | none — no overlap |
| Capital stack / lender matching | `funding-path-architect` | none — no overlap |
| Lender / SBA rate research | `financial-research` | none — no overlap |
| NAICS / industry research | `market-research` | none — no overlap |
| Phase 0 intake conversation | `intake-concierge` | none — no overlap |
| Coach book-of-business view | `coach-copilot` | none — no overlap |
| Funnel / landing page generation | `funnel-architect` (§124 first-shipment) | none — no overlap |
| **Client-facing content drafting** | `content-outreach-drafter` | **MMA OS `content_orchestrator` parts that draft client-facing copy should migrate to delegate_to_subagent** |

### Tier B — Both Keep, Clear Scope Distinction (no migration, doctrine clarification only)

These capabilities have a Paige version AND an MMA OS version that do different things despite similar names. Keep both. Codify the scope split.

| Capability | Paige sub-agent scope | MMA OS agent scope |
|---|---|---|
| Sales pipeline | `sales-pipeline` — per-tenant client follow-ups, stalled-lead surfacing for one coach's book | `sales_department` — cross-tenant analytics, revenue forecasting, BTF/LaunchPad pipeline aggregation |

(Currently only this one Tier B entry. Add more as overlaps emerge.)

### Tier C — MMA OS Owns (no Paige overlap, no change needed)

These capabilities have no Paige equivalent and should not get one. They are business-wide infrastructure, not per-tenant intelligence.

| Capability | MMA OS agent |
|---|---|
| Customer memory across all touch points | `customer_memory` |
| Brain coherence / KB health monitor | `brain_health_monitor` |
| Master morning brief generator | `operations_department` |
| BTF education engine (long-running deterministic sequence) | `btf_education_engine` |
| BTF stall detection cross-program | `btf_stall_detector` |
| LaunchPad lifecycle orchestration | `launchpad_orchestrator` |
| 6 remaining DX agents (revenue/crm/lifecycle/monitoring/support/comms) | each `*_dx` + `*_orchestrator` pair |
| Customer success / sales / operations department heads | `customer_success_department`, `sales_department`, `operations_department` |
| Cross-business code-writer agents | `github_writer`, `n8n_writer`, `notion_writer`, `edge_function_writer` |

---

## The Going-Forward Rule

**For any new capability being designed:**

1. Is it scoped to one tenant's client(s)? → **Paige sub-agent** (delegate_to_subagent from MMA OS if MMA OS needs it)
2. Is it cross-tenant, infrastructure, deterministic-sequence, or business-wide analytics? → **MMA OS LangGraph agent**
3. Does it touch BOTH? → **Default to Paige sub-agent + MMA OS thin wrapper** that calls delegate_to_subagent and adds the business-wide context. Avoid duplicating the per-client logic in both places.

When in doubt, default to Paige sub-agent. Reasoning: Paige already has the orchestrator, the safety layer (§122), the role gating (§125), and the Approvals Hub. Building those in MMA OS for a single client-facing use case is reinventing infrastructure that's already in production.

---

## The Migration List (concrete work this doctrine creates)

1. **Audit MMA OS `content_orchestrator`** for parts that draft client-facing copy → flag for migration to `delegate_to_subagent("content-outreach-drafter")`. Keep the business-wide content (Mogul Brief, Market Watch, internal comms) in MMA OS.
2. **Update `master_orchestrator`'s TASK_REGISTRY** with new aliases routing client-facing intents to the Paige delegate verb. Per §96, these aliases need fuzzy matching so "review this draft for the client" routes to the right place.
3. **Add a `paige_proxy` task** to the comms_orchestrator so MMA OS agents can call Paige sub-agents through a single canonical pathway (rather than each agent constructing its own paige-mcp-proxy call).
4. **Document in the master_orchestrator system prompt** that Paige sub-agents exist and when to delegate. The orchestrator should know its options at planning time.

---

## When This Doctrine Doesn't Apply

There are two cases where this doctrine's default-to-Paige rule should NOT apply:

1. **MMA OS internal infrastructure** that happens to involve client data (e.g., `ghl-webhook-receiver` ingests client contact changes — but its purpose is sync infrastructure, not client-facing intelligence). These stay in MMA OS.
2. **Emergency / fallback capability** that needs to function when Paige is down. Critical paths (BTF education engine, payment recovery) must have an MMA OS LangGraph version that works without Paige being available, because Paige is a tenant of MMA OS's revenue stream — if Paige goes down for a day, MMA OS's communications to MMA members cannot also be down. This is the §83 (Cloud-First, Server-Portable) doctrine applied to inter-platform dependency.

---

## Related Doctrines

- **§88** — Master Orchestrator Agent (the MMA OS orchestration spine)
- **§115** — Paige Multi-Tenant Pivot (created the federation question by making Paige a real platform)
- **§117** — Entity Separation + MCP Control Plane (this doctrine operationalizes the separation for agent work)
- **§118** — Master Tenant vs Sub-Tenant Automation (analogous separation at the master tenant level)
- **§121** — Paige Sub-Agent Architecture (defines the Paige side of this boundary)
- **§122** — Two-Phase Commit for AI-Staged Writes (Paige owns the safety layer for client-facing writes — another reason client-facing work belongs to Paige)
- **§83** — Cloud-First, Server-Portable (the override for critical paths that need MMA OS fallback)

---

## v1 Status — Open to Antonio Amendment

The specific tier assignments above represent Claude's recommendation as of 2026-06-29. Antonio retains authority to amend:

- **Tier A additions/removals** (which Paige sub-agents are canonical and which still need MMA OS equivalents)
- **Tier B scope splits** (when two similarly-named agents should both exist)
- **Tier C protection** (which MMA OS agents must NOT be migrated to Paige)
- **Migration list ordering** (what to do first vs defer)

The 3-tier framework itself + the default-to-Paige rule for client-facing work are the persistent contribution of this doctrine. Specific tier assignments are subject to revision as the platforms evolve.

---

## Postscript — Why the Default Matters

A doctrine without a default produces analysis paralysis. Every new capability becomes a 30-minute discussion about "should we build it here or there." The team avoids building because the architectural question is unresolved. New capability ships slowly, both platforms ossify.

A doctrine with a default produces velocity. New client-facing capability defaults to Paige sub-agent unless someone makes the case for MMA OS. The case has to be argued, not assumed. Most cases will be Paige (which is the right answer). The handful of MMA OS cases get the scrutiny they deserve because they're the exception.

That asymmetry — default-to-Paige, exception-needs-justification — is what this doctrine establishes. The specific tier assignments will evolve. The default and the framework should not.
