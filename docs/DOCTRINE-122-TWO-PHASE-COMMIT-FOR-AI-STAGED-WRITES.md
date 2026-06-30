# Doctrine §122 — Two-Phase Commit for AI-Staged Writes

**Codified:** 2026-06-29
**Trigger:** Lovable shipped `paige_ingestion_proposals` + 8 new MCP tools (`propose_client_update`, `ingest_credit_scores`, `ingest_banking_snapshot`, `append_client_memory`, `search_clients_fuzzy`, `list_my_proposals`, `confirm_proposal`, `reject_proposal`) operationalizing the safety layer for voice/LLM dictation of client data. New Field Ingestion tab at `/admin/approvals` for human review of anything flagged `needs_review`.

---

## The Principle

Any AI-driven write into a customer record that could materially affect funding decisions, compliance posture, or financial position **must NOT commit directly**. The write must be staged as a *proposal*, validated against a battery of hallucination guards, and either auto-applied (if all guards pass) or routed to human review (if any guard flags).

This is the database equivalent of a two-phase commit:
- **Phase 1 (propose):** AI submits the intended change as a row in a proposals table with status `pending`
- **Phase 2 (commit or reject):** A human reviewer (or an auto-apply rule if all guards passed) confirms → status flips to `applied` and the change is written; or rejects → status `rejected` and the change is discarded

This is not optional for sensitive data classes. It is the only safe pattern for voice-driven CRM at production scale.

---

## The Proposal Lifecycle

```
  ┌─────────┐    guards     ┌──────────────┐    human    ┌─────────┐
  │ pending │──────pass─────│ auto-applied │             │ applied │
  └────┬────┘                └──────────────┘     ┌──────│         │
       │                                          │      └─────────┘
       │                                          │
       │ guards flag                              │
       ▼                                          │
  ┌──────────────┐         confirm_proposal()     │
  │ needs_review │────────────────────────────────┘
  └──────┬───────┘
         │
         │ reject_proposal()           expiry timer
         ▼                                  ▼
  ┌──────────┐                       ┌─────────┐
  │ rejected │                       │ expired │
  └──────────┘                       └─────────┘
```

Five canonical statuses (per Paige `list_my_proposals` enum): `pending`, `needs_review`, `applied`, `rejected`, `expired`.

Note: `pending` and `needs_review` are *distinct* — `pending` means "submitted, guards not yet evaluated", `needs_review` means "guards evaluated and flagged a concern requiring human disposition."

---

## The Hallucination Guards (Paige Implementation Reference)

At minimum, every AI-staged write must pass:

1. **Range checks** — numeric values within plausible bounds (FICO 300–850, business credit 0–100, account balances ≥ 0 unless explicitly overdraft type)
2. **Magnitude-of-change checks** — bureau score deltas > 40 points flagged for human review (likely typo, hallucinated digit, or wrong client); banking deltas > 50% MoM flagged similarly
3. **Fuzzy-match disambiguation** — before writing to a contact, `search_clients_fuzzy` must return a single high-confidence match; multiple matches or low confidence → `needs_review` with disambiguation candidates listed
4. **Confidence flags** — the calling AI must self-report its confidence (`high`, `medium`, `low`); anything `medium` or below auto-routes to `needs_review` regardless of other checks
5. **Tenant scoping** — proposal target_contact_id must belong to the calling tenant (per §118); cross-tenant writes are rejected at the schema layer
6. **Idempotency** — proposals carry an idempotency key derived from `(tenant_id, contact_id, field, source_event_id)` so retries don't double-apply

Additional guards by data class:
- **Credit score writes:** require source attribution (bureau name + report pull date)
- **Banking writes:** require account masking (last-4 only stored; full account number rejected)
- **PII writes:** any change to legal name, SSN, EIN, or DOB always routes to `needs_review`
- **Compliance-sensitive language** (CROA, FCRA, GLBA, FDCPA): routes through the Legal Compliance Reviewer sub-agent first; flagged language never auto-applies

---

## Why This Doctrine Exists

LLMs hallucinate. Voice transcription mis-hears. The same surname applies to multiple clients. A score of "705" might be transcribed as "750" with confidence. A coach dictating "Susan Williams" might mean either of two clients with that name.

Without staged writes, any of these failure modes commit silently to a customer record. The downstream consequences include:
- Wrong client's file gets the update (cross-contamination)
- Wrong score on the funding application (denial, mis-classification)
- Wrong PII on a legal document (compliance exposure)
- Wrong banking data in cash flow analysis (failed underwriting)

With staged writes, the failure manifests as a `needs_review` row that a human can disambiguate before it becomes a database fact. Cost of a flagged proposal: 30 seconds of human attention. Cost of a silent miswrite: a denial, a compliance escalation, or a client churn.

---

## The MCP Surface

Paige exposes 8 tools that implement this doctrine:

**Write side (AI/voice client calls these):**
- `propose_client_update(contact_id, field, value, source, confidence)` — generic typed write proposal
- `ingest_credit_scores(contact_id, bureau, score, pulled_at, confidence)` — credit-bureau-specific shaped proposal
- `ingest_banking_snapshot(contact_id, account_type, last_4, balance, as_of_date, confidence)` — banking-specific shaped proposal
- `append_client_memory(contact_id, note, source)` — append-only memory (less risky, lower bar to apply)
- `search_clients_fuzzy(query)` — required step before any write when client identity is ambiguous

**Review side (human reviewer or auto-apply rule calls these):**
- `list_my_proposals(status?, limit?)` — show staged proposals
- `confirm_proposal(proposal_id, note?)` — apply the change
- `reject_proposal(proposal_id, reason)` — discard the change with audit trail

The two sides are deliberately separated so the proposing AI cannot also confirm its own proposal. Only authorized reviewers (admins, coaches per assignment, or rules that ran all guards green) can confirm.

---

## Apply to MMA OS

MMA OS has parallel ingestion paths that should adopt this doctrine:

| MMA OS write path | Current state | §122 retrofit |
|---|---|---|
| Telegram `/lead` command → GHL contact create | Direct write | Stage as proposal, auto-apply if all required fields present + no fuzzy match conflict |
| Customer Memory Agent → customer_profiles | Direct write with identity check (§81) | Stage as proposal for score/financial fields; keep direct write for behavioral notes |
| ghl-webhook-receiver → contacts mirror | Direct write | Keep direct write (source is GHL itself, not AI inference) |
| BTF education engine → enrollment advance | Direct write | Keep direct write (sequential, deterministic, not AI inference) |

Rule of thumb: **if the value being written is the output of an LLM call, transcription, or vague natural language input, stage it. If it is the output of a deterministic system event (webhook, scheduled task, explicit user form submission), write directly.**

---

## Cross-Tenant Implications

When Paige onboards sub-tenants (per §115 Multi-Tenant Pivot), each sub-tenant inherits this doctrine automatically — `paige_ingestion_proposals` is tenant-scoped at the schema layer. Sub-tenant admins review their own tenant's proposals. No cross-tenant visibility.

When MMA OS calls Paige MCP write tools (via paige-mcp-proxy as the MMA tenant), the proposals route to the MMA tenant's Field Ingestion queue at `/admin/approvals`. Antonio (or assigned coaches) review them just as if a voice client had dictated them.

---

## Related Doctrines

- **§73** — Test fires always route to Antonio (this doctrine extends that safety principle to all AI-staged writes)
- **§81** — Memory Agent must verify subject identity before creating new profiles (sibling principle — identity verification before write)
- **§82** — Every customer-data write to MMA OS must mirror to Paige (interacts with this doctrine — proposals on the Paige side that get applied flow back through the mirror)
- **§94** — LLM resilience: catch and re-raise vs swallow
- **§119** — Conversational Control Plane (this doctrine is the safety net that makes §119 production-safe)
- **§120** — Schema Constraints Must Mirror Application Enums (the status enum on proposals must match every literal the application writes — same lesson applied to this table)
- **§121** — Paige Sub-Agent Architecture (sub-agents that need to write client data must use these proposal verbs, not direct writes)

---

## Postscript — The 30-Second Cost

The single most underestimated cost in voice-driven CRM is the silent miswrite. A coach dictates a credit score on the way home from a client meeting. The wrong digit lands. Three weeks later the funding application returns "denied: insufficient bureau score." The coach is convinced the database is wrong. Investigation reveals the typo. Trust in the system erodes. The next time a coach is about to dictate, they switch to manual entry. The voice interface is dead.

Thirty seconds of human review on a flagged proposal is the price of avoiding that failure mode. This doctrine makes that thirty seconds the default behavior for sensitive writes, not an afterthought.
