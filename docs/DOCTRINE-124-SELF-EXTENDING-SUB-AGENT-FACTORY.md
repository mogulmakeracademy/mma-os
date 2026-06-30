# Doctrine §124 — Self-Extending Sub-Agent Factory

**Codified:** 2026-06-29
**Trigger:** Lovable shipped the Sub-Agent Factory UI at `/admin/sub-agents → Proposals tab`. Paige (and admins) can now propose new sub-agents at runtime. Soft agents ship instantly; hard agents route through the Approvals Hub. This is meta-programmable AI architecture — the system extends its own capability surface based on observed user needs, with a structural safety distinction between low-risk and high-risk extensions.

---

## The Principle

A conversational AI platform that cannot extend itself stagnates. Every observed user request that the current sub-agent roster cannot handle becomes either a manual ticket for the engineering team or a permanent gap in capability. Both outcomes are bad.

A platform that *can* extend itself without any safety distinction is also bad — it has no structural barrier between "add a new prompt that uses existing tools" (low risk) and "add a new external API integration with new auth credentials" (high risk). The first is essentially a configuration change; the second is shipping new code into production.

The right architecture is **a factory with a structural split**:

- **Soft agents** = new prompt + existing tools, no new external dependencies, no new schema → ship instantly to the registry, immediately available to the orchestrator
- **Hard agents** = new tool definitions / new external API / new schema / new credentials → route through the Approvals Hub for human review before activation

The split is not arbitrary. It maps directly to attack surface: soft agents introduce no new attack surface; hard agents do.

---

## Soft vs Hard — The Decision Criteria

A proposed sub-agent is **soft** if and only if ALL of the following are true:

1. **Tools subset**: every tool the proposed agent calls is already in the platform's tool registry (`paige-mcp` or `paige-ai-chat`)
2. **No new credentials**: the agent does not require any new API keys, OAuth client, or external auth
3. **No new schema**: the agent does not require new tables, columns, or RLS policies
4. **No new outbound network call**: the agent does not initiate any HTTP request to a domain not already in the allowlist
5. **No new compliance surface**: the agent does not handle a new class of regulated data (e.g., HIPAA, PCI) that requires separate review
6. **Prompt-only change**: the agent is a system prompt + tool subset + trigger phrases, with no new TypeScript/Deno code

If any of those is false, the proposed agent is **hard** and must route through Approvals.

The runtime classifier (in `paige-orchestrator` or its proposal submission Edge Function) should make this determination automatically based on the proposal payload. The proposer (Paige or admin) does not get to declare its own classification — that would defeat the safety distinction.

---

## The Approval Flow for Hard Agents

Hard agents are routed to the Approvals Hub with the same machinery that handles human-review-required workflows (per §122):

1. Proposer submits agent spec via Sub-Agent Factory UI or `propose_subagent` MCP verb (when shipped)
2. Classifier marks it as `hard` based on the criteria above
3. Approval row created in `paige_pending_approvals` with category=`sub_agent_proposal`
4. Admin (Owner-only for hard agents per §123 role-gating future doctrine) reviews:
   - Code diff if the agent ships new Edge Function code
   - Tool registry diff if the agent declares new tools
   - Schema migration plan if the agent declares new tables
   - External API documentation link if the agent calls a new service
   - Threat model assessment for the new attack surface
5. On approve: agent is registered, code/schema is deployed, tools are added to the registry
6. On reject: proposal archived with rationale; proposer can iterate and resubmit

The Approvals reviewer is the platform owner (Antonio) for hard agents, not a delegated admin. Code-shipping authority does not delegate.

---

## Why the Distinction Matters

A soft agent that says "you are a Coffee Pairing Sommelier — when asked, suggest a coffee based on the user's mood" introduces no new risk. The orchestrator simply has a new tool labeled `coffee-pairing-sommelier`. If the orchestrator never invokes it, nothing happens. If a user asks for coffee pairing, the agent fires with the orchestrator's existing tool set (LLM call + maybe a `search_kb` tool). No new credentials. No new outbound calls. No new schema. Reversible by deleting one registry row.

A hard agent that says "you are a Plaid Banking Aggregator — pull transaction history for the user's linked accounts" introduces enormous new risk: new credentials (Plaid API keys), new outbound calls (Plaid API), new schema (transaction storage), new compliance surface (GLBA, possibly PCI). If shipped without review, a misconfigured one could leak the API key to client-side code, store sensitive transaction data in an unscoped table, or trigger reconciliation cascades the team is not prepared to support.

The distinction is not "AI vs human can decide" — it is "what does the new capability cost to undo if it's wrong." Soft agents undo with a registry delete. Hard agents may require code rollbacks, schema migrations, credential rotations, and customer notifications. The Approvals gate is the structural acknowledgment of that cost asymmetry.

---

## Apply to MMA OS

MMA OS has the same architectural shape — agents can extend each other (per §88 Master Orchestrator + §89 Code Writer Agents). The same soft/hard distinction applies:

**Soft agent extensions in MMA OS** (auto-ship via the existing writer agents):
- Adding a new system prompt to an existing LangGraph agent
- Adding a new TASK_REGISTRY alias for an existing action (per §96)
- Adding a new pointer to `campaign_content_registry` (per §64)
- Adding a new trigger keyword to the master_orchestrator's routing layer

**Hard agent extensions in MMA OS** (require Antonio review):
- Adding a new LangGraph agent (new file in `agents/`, new graph_id, new entry in langgraph.json)
- Adding a new Edge Function (new code, new auth, new outbound calls)
- Adding a new external API integration (new credentials, new outbound domains)
- Adding a new Supabase table or RLS policy
- Modifying the langgraph-bridge to add a new verb

The github-writer / n8n-writer / notion-writer / edge-function-writer agents (per §89) ALL operate on the soft side by default — they apply human-authored specs. Any agent that wants to generate a new spec end-to-end without human review is by definition hard and must route through Antonio's Telegram approval (per §108) before commit.

---

## The Reversibility Test

When in doubt about whether an extension is soft or hard, apply the **Reversibility Test**:

> If this extension turns out to be wrong, how long does it take to undo? Who needs to be notified? What customer-facing impact does the rollback have?

- **Soft**: undo time < 5 minutes, no notifications needed, zero customer impact
- **Hard**: undo time > 5 minutes, OR requires customer notification, OR has customer impact during rollback

The test forces an honest assessment of cost asymmetry. Anything that fails the soft criteria fails the test and routes to Approvals.

---

## Cross-Tenant Implications

When Paige onboards sub-tenants (per §115), the Factory must enforce that sub-tenant proposals stay within the sub-tenant's scope:

- Sub-tenant admins can propose **soft agents scoped to their own tenant**
- Sub-tenant admins **CANNOT** propose hard agents (those affect platform infrastructure, which is master-tenant authority per §118)
- Master tenant admin (Antonio) can propose hard agents that are platform-wide or scoped to any tenant

The scope check is enforced at the proposal-submission Edge Function: `caller.tenant_id != "master" AND proposal.classification == "hard" → reject 403`.

---

## Related Doctrines

- **§88** — Master Orchestrator Agent (the MMA OS sibling pattern that this doctrine extends with the soft/hard distinction)
- **§89** — Code Writer Agent per location (writers are the soft-side mechanism; hard-side requires Antonio approval)
- **§108** — Alert Routing Rule (hard-agent approvals route to Antonio Telegram per the revenue/compliance alert tier)
- **§115** — Paige Multi-Tenant Pivot (sub-tenants inherit the factory but are scope-limited)
- **§118** — Master Tenant vs Sub-Tenant Automation (hard-agent authority is master-tenant-only)
- **§121** — Paige Sub-Agent Architecture (the architecture this factory extends)
- **§122** — Two-Phase Commit for AI-Staged Writes (the same Approvals Hub infrastructure handles both hard-agent proposals and AI-staged writes)

---

## Postscript — The Anti-Pattern This Avoids

Without the soft/hard distinction, two failure modes emerge:

**Failure Mode 1 — Frozen Platform:** Every extension requires engineering review. The Coffee Pairing Sommelier example sits in a backlog for weeks because there's no fast path for low-risk additions. Paige cannot adapt to user needs at the speed users surface them. The platform feels static. Users stop asking for things they assume won't happen.

**Failure Mode 2 — Runaway AI:** Every extension auto-ships because that's easier than designing a gate. Paige decides to integrate with Plaid one afternoon because a user asked about banking history. The Plaid API key is checked into the public registry. Customer transactions are stored in an unscoped table. A coach in a sub-tenant discovers they can query every other sub-tenant's transaction history. Discovery is six weeks later via a customer complaint. The company is now a news story.

The soft/hard split avoids both. Coffee Pairing Sommelier ships in 30 seconds. Plaid integration sits in Antonio's Telegram approval queue until he has time to think about the threat model. The platform stays adaptive AND stays safe.

That balance is what this doctrine codifies.
