# Doctrine S113 - Legal Department Philosophy
# Source: Antonio Cook | Codified: 2026-06-29
# Status: CANONICAL. Defines how the Legal Department operates - what it builds, what it doesnt.

## The principle

**One canonical agreement template per program. Not infinite custom variations. Legal agents run silently in the background, checking documents as needed.**

## What the Legal Department DOES

1. **Builds one canonical template per program** — BTF gets one master service agreement. LaunchPad gets one master service agreement. DFY gets one master service agreement. Once built and approved, the template is REUSED for every client in that program.

2. **Generates per-client agreement INSTANCES from the master template** — placeholder fill (client name, address, payment plan, start date) — but the LEGAL TERMS don't change client-to-client.

3. **Runs continuous compliance checking in the background** — every piece of customer-facing content (marketing emails, ad copy, coach scripts, website pages) is silently scanned for CROA / Truth-in-Lending / FTC / state-law violations. Flags + redline suggestions surface ONLY when something is off.

4. **Performs episodic legal research when triggered** — new regulation drops, new state we're operating in, new product line — research is done once, memo goes to knowledge base, never repeated.

## What the Legal Department DOES NOT do

- **Does NOT continuously develop new agreements.** Drafting is a one-time event per program. After the master template is approved, the drafting agent's job is only to fill placeholders for new clients.
- **Does NOT customize agreement terms per client.** Every BTF client gets the SAME agreement terms. Only variable fields (name, plan, dates) differ.
- **Does NOT provide legal advice to clients.** All output is internal-facing or rendered as standardized customer-facing language reviewed in advance.
- **Does NOT replace human legal review for major decisions.** When a master template is created or significantly updated, it MUST be reviewed by a licensed attorney before deployment. The Legal Department drafts; humans approve.

## Build order constraint

**Legal Department code is built AFTER the operational framework is fully functional.** Reason: there is no point in compliance-checking content that doesnt exist yet, and there is no point in generating agreement instances from templates that havent been finalized.

Build sequence:
1. BTF operational framework (intake, onboarding, workspace, lifecycle) — DONE / IN PROGRESS
2. BTF master service agreement template — FIRST USE of Legal Department, after framework lands
3. Legal Department code (legal_orchestrator + 3 specialists) — built to SERVE step 2 + ongoing compliance
4. Subsequent program templates (LaunchPad, DFY) — handled by the same Legal Department once it exists

## Output shapes

| Legal sub-agent | Output | Cadence | Storage |
|---|---|---|---|
| legal_research_agent | Research memo (md) | Episodic | rag_documents (legal_research category) |
| legal_drafting_agent | Filled agreement instance (PDF) | Per client onboarding | paige_signed_agreements (after signature) |
| legal_compliance_agent | Compliance flag + redline | Continuous (every customer-facing publish) | compliance_flags table + Telegram alert if blocking |

## Cross-doctrine consistency

- **Doctrine S110** defines the Legal Department as Tier -1 composing legal_orchestrator + crm + comms. UNCHANGED.
- **Doctrine S112** defines the specialist sub-agent decomposition pattern. The Legal Department is the canonical implementation.
- **Doctrine S111** defines client lifecycle stages. The Legal Department fires at STAGE 3 (agreement signed) and watches all customer-facing comms continuously.
- **Doctrine S66** (Claude BUILDS, n8n/Supabase FIRE) still applies — Claude codes the agents, the agents run on schedule.
- **Doctrine S88** (swarm coordination) still applies — master_orchestrator routes through legal_orchestrator down to specialists, never directly.
