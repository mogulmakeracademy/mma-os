# Doctrine S112 - Specialist Sub-Agent Pattern (Tier 2 Architecture)
# Source: Antonio Cook | Codified: 2026-06-29
# Status: CANONICAL. Extends Doctrine S88 (agent swarm pattern) with a deeper-tier specialization rule.

## The principle

**When a Tier 1 orchestrator has 3+ distinct sub-tasks with different skill profiles + tool requirements + cadences, decompose into Tier 2 specialists.**

The orchestrator becomes a router. The specialists do the work.

## When this pattern APPLIES

- A domain involves multiple cognitive modes (research, drafting, evaluation)
- Each sub-task needs different tool access (e.g. one needs a corpus search, another needs template rendering, a third needs content scanning)
- Cadences differ wildly (one runs episodically when triggered, another runs continuously on a content stream)
- Outputs are categorically different (research memos vs filled documents vs blocking flags)

## When this pattern DOES NOT apply

Most domains. The default architecture (Tier 1 orchestrator + Tier 1 DX) is sufficient for >80% of work. Decomposing into Tier 2 specialists adds complexity. Reserve it for domains that genuinely need it.

## Example: Legal Department (canonical implementation)

```
TIER -1: legal_department (Department Head)
  composes:
  TIER 1: legal_orchestrator (domain router)
    spawns when needed:
      TIER 2: legal_research_agent
        skill: statute lookups, case law, regulatory guidance
        cadence: episodic
        outputs: research memos to knowledge base
      TIER 2: legal_drafting_agent
        skill: template-fill + jurisdiction logic
        cadence: high volume (per client onboarding)
        outputs: filled agreement instances
      TIER 2: legal_compliance_agent
        skill: rule-library scan against content
        cadence: continuous (every customer-facing publish)
        outputs: blocking flags + redline suggestions
  TIER 1: crm_orchestrator (existing)
  TIER 1: comms_orchestrator (existing)
```

## Future candidates for this pattern

When marketing layer ships (Doctrine S107), if the workload justifies it:
- content_orchestrator could decompose: content_research + content_drafting + content_distribution + ad_optimization

When sales scales: sales_orchestrator could decompose: prospecting + outreach_drafting + follow_up + close

But again — only decompose when the workload + skill divergence justifies it. Single-agent simplicity wins by default.

## Implementation notes

- Tier 2 agents are spawned BY their Tier 1 orchestrator (not by master_orchestrator directly)
- Tier 2 agents have a narrower TASK_REGISTRY scoped to their specialty
- Tier 1 orchestrator owns the "which specialist for which task" routing logic
- Tier 1 orchestrator handles result aggregation if multiple specialists ran on the same request
- Tier 2 agents log to agent_calls like everyone else, with parent_agent = the Tier 1 orchestrator
