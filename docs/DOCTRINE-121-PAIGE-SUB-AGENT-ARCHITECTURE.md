# Doctrine §121 — Paige Sub-Agent Architecture

**Codified:** 2026-06-29
**Trigger:** Lovable Pass 1-5 shipment + Sub-Agent Factory UI completed the Paige-as-Orchestrator architecture. Paige now operates as an intent router + memory + synthesis + compliance gate, delegating narrow-domain work to 11 specialized sub-agents implemented as Edge Functions. This is the **direct architectural mirror of Doctrine §88 (Master Orchestrator + 7 DX agents in MMA OS)**, applied one tenant layer down at the Paige platform layer.

---

## The Principle

A conversational AI platform should be composed of two distinct layers:

1. **Orchestrator layer** — owns intent routing, conversation memory, final answer synthesis, tone consistency, and the compliance gate before any action is taken
2. **Sub-agent layer** — each agent has narrow scope, its own system prompt, its own tool subset, and returns structured JSON back to the orchestrator

The orchestrator sees sub-agents as tools. The sub-agents do not see each other. The orchestrator is responsible for choosing which sub-agent (or sequence of sub-agents) to invoke for any given user intent.

This pattern is what enables an LLM-powered product to scale beyond toy prompts into genuine production capability — the orchestrator's prompt stays small and stable while specialized capability is added as new sub-agents without prompt bloat.

---

## The Paige Sub-Agent Roster (as of 2026-06-29)

| # | Slug | Name | Domain | Runtime |
|---|---|---|---|---|
| 1 | `fundability-diagnostician` | Fundability Diagnostician | BUILD-to-FUND | local |
| 2 | `data-consistency-auditor` | Data Consistency Auditor | Compliance Infrastructure | local |
| 3 | `legal-compliance-reviewer` | Legal & Compliance Reviewer | Compliance | local |
| 4 | `business-credit-strategist` | Business Credit Strategist | STACK Phase | local |
| 5 | `funding-path-architect` | Funding Path Architect | FUND Phase | local |
| 6 | `financial-research` | Financial Research Agent | Market Data | local |
| 7 | `market-research` | Market & Competitive Research | Industry Intel | local |
| 8 | `content-outreach-drafter` | Content & Outreach Drafter | Comms | local |
| 9 | `intake-concierge` | Onboarding/Intake Concierge | Phase 0 Intake | local |
| 10 | `sales-pipeline` | Sales/Pipeline Agent | Sales Ops | local |
| 11 | `coach-copilot` | Coach Copilot | Coach Console | local |

**All 11 implemented as Supabase Edge Functions** (the "local" runtime label distinguishes from a future LangGraph-routed runtime). Pass 4 promoted the three originally-planned LangGraph agents (data-consistency-auditor, financial-research, market-research) to local edge functions, which is the right call for sub-second response latency from a chat surface.

Each sub-agent has:
- A **system prompt** scoped to its domain
- A **tool subset** (subset of the full Paige MCP surface)
- **Trigger phrases** the orchestrator uses to route intent (e.g., "am I ready to be funded" → fundability-diagnostician)
- A **structured JSON output schema** the orchestrator parses for synthesis

---

## How Paige Orchestrates

The orchestrator (`paige-orchestrator` Edge Function, exposed via `paige-ai-chat` for in-app + `delegate_to_subagent` MCP tool for external Claude Desktop / ChatGPT / voice clients) runs the AI SDK `streamText` loop with sub-agents registered as tools.

User intent flow:
1. User says/types something to Paige
2. Paige reads the trigger phrase, conversation memory, and current contact context
3. Paige decides: answer directly OR delegate to one (or more, in sequence) sub-agents
4. Sub-agent runs with its scoped prompt + tools, returns structured JSON
5. Paige synthesizes the structured output into a natural-language response
6. Paige logs the invocation to `paige_subagent_invocations` (audit + debug trail readable via `get_subagent_history`)

This means the user always talks to Paige. The sub-agents are invisible. The orchestrator preserves tone, memory, and compliance regardless of which specialist did the underlying work.

---

## MCP Surface — How External Agents Use the Sub-Agents

MMA OS Claude (and any other MCP-aware LLM) can call into the sub-agent layer directly via three MCP tools:

- `list_subagents(query?, domain?)` — discover the roster + match against natural-language query
- `delegate_to_subagent(slug, contact_id, input?)` — invoke a specific sub-agent with context
- `get_subagent_history(slug?, contact_id?, limit?)` — read the audit log

**Authorization scope:** `crm.read` for the read tools, `workflows.run` for `delegate_to_subagent` (treated as a workflow invocation per Paige's scope model).

---

## Self-Extending — The Sub-Agent Factory

As of the Sub-Agent Factory UI ship, Paige (and admins) can **propose new sub-agents** at runtime:

- **Soft agents** (new prompt + existing tools, no new external dependencies) → ship instantly to the registry
- **Hard agents** (new tools, new external API, new schema) → routed through the Approvals Hub for human review before activation

This is meta-programmability. Paige can extend her own capability surface based on observed user requests. The Approvals gate prevents runaway agent proliferation.

This is also why we see runtime=local for all 11 agents currently registered — Pass 4 consolidated everything into the local edge-function pattern, and the factory will keep emitting local agents by default. LangGraph remains an option for heavy compute or cross-tenant orchestration agents (per Doctrine §118).

---

## Cross-System Mirror — Why This Matches MMA OS §88

| Layer | MMA OS (§88) | Paige (§121) |
|---|---|---|
| Tenant scope | Cross-business brain | Per-tenant CRM platform |
| Orchestrator | `master_orchestrator` LangGraph agent | `paige-orchestrator` Edge Function |
| Sub-agents | 7 DX agents (comms, revenue, crm, monitoring, lifecycle, content, support) | 11 sub-agents (this doctrine) |
| Sub-agent runtime | LangGraph Platform (Python) | Supabase Edge Functions (Deno/TS) |
| Compliance gate | TASK_REGISTRY allow-list (§96) | Legal Compliance Reviewer sub-agent + Approvals Hub |
| Memory | Per-agent state + customer_profiles table | Conversation memory + paige_subagent_invocations log |
| Dispatch | langgraph-bridge (§89 writer pattern) | delegate_to_subagent MCP verb |

The pattern is identical at the architectural level. The implementations differ because each platform optimizes for its own substrate (Python+LangGraph for cross-business intelligence; TS+Edge Functions for sub-second chat).

---

## Federation Boundary — Who Owns What

With Paige sub-agents now live, there is a clear **federation question** for MMA OS: which agent layer should own which work?

**Paige sub-agents own (client-facing):**
- Per-client intelligence: fundability checks, BTF phase analysis, capital stack recommendations
- Compliance gates on per-client actions (CROA, FCRA, GLBA, FDCPA)
- Per-client content drafting routed through Approvals
- Client-facing intake conversation
- Coach-assignment-aware queries

**MMA OS LangGraph agents own (business-wide):**
- Cross-tenant orchestration (master_orchestrator)
- Aggregate analytics + KPI brief generation (operations_department, monitoring_dx)
- Brain coherence + knowledge base health (brain_health_monitor)
- Customer memory across all touch points (customer_memory)
- BTF education engine (long-running send sequences across many clients)
- Cross-system mirror pattern (sales_department, revenue_orchestrator)

**Both have a copy of the same domain only when** the work is unmistakably scoped to one tenant (client-facing) vs. business-wide (analytics). When in doubt: client-facing work belongs to Paige; business-wide work belongs to MMA OS.

Going forward, **MMA OS should prefer `delegate_to_subagent` over reimplementing client-facing intelligence in its own LangGraph layer.** This avoids duplication and keeps Paige as the canonical client-facing intelligence surface.

---

## Related Doctrines

- **§88** — Master Orchestrator Agent (the MMA OS sibling pattern)
- **§89** — Code Writer Agent per location (sub-agents follow this pattern — each one writes to its own domain)
- **§95** — Bug → Fix → Codify ritual
- **§117** — Entity Separation + MCP Control Plane (Paige is the product; MMA is one tenant of the product)
- **§118** — Master Tenant vs Sub-Tenant Automation (the MMA tenant has hardwired MMA OS LangGraph access; sub-tenants will only have Paige sub-agents)
- **§119** — Conversational Control Plane (this doctrine is what makes §119 work — without the sub-agent layer, the orchestrator would have to know everything)
- **§122** — Two-Phase Commit for AI-Staged Writes (the safety net for sub-agents that propose data changes)

---

## Postscript — Why This Architecture Wins

The alternative — a single monolithic prompt that knows everything — degrades quickly. The orchestrator + sub-agent split lets each prompt stay small and stable, lets new domains be added without regression risk, lets compliance live in a dedicated sub-agent that other sub-agents must route through for sensitive actions, and lets MMA OS reuse Paige's intelligence layer without duplicating it.

The Sub-Agent Factory adds the meta-programmable layer: Paige can extend her own capability surface based on observed user requests. Soft agents ship instantly; hard agents go through Approvals. This is how a conversational platform genuinely scales.
