# Doctrine S110 - Legal Department + Client Onboarding Flow
# Source: Antonio Cook | Codified: 2026-06-29
# Status: CANONICAL. Defines the WHO + WHEN + HOW of converting leads to clients.

## The principle

**Every paid Client must sign a service agreement before workspace access is granted.**
**Every BTF (and future DFY) program enrollment routes through a single Onboarding Flow inside Paige.**
**The Onboarding Flow trigger is ALWAYS manual** — a rep (Antonio, coach, sales) actively initiates it. Triggers can be voice-activated via synced LLM (Claude/ChatGPT) over the Paige MCP, but the underlying action is human-initiated.

## The Legal Department (Tier -1 Department Head)

A new department in the MMA OS swarm. Composes:
  - legal_orchestrator (Tier 1, NEW) — manages agreement lifecycle + deliverables tracking
  - compliance_orchestrator (future) — surfaces regulatory flags on marketing claims, content, ad copy
  - crm_orchestrator — for client record updates
  - comms_orchestrator — for sending agreement-related emails

Responsibilities:
  - Hold the canonical service agreement template (versioned in mma-os/docs/legal/)
  - Generate per-client agreement instances with filled-in fields (name, payment plan, date, etc.)
  - Track signed status per client
  - Track program deliverables status (what we promised vs delivered)
  - Surface compliance violations in customer-facing content
  - Maintain refund eligibility timer per client (3-day rescission, 30-day window, post-30 no-refund states)

## The Six-Stage BTF Onboarding Flow

STAGE 1: TRIGGER (manual rep action)
  Rep fires sales_dept.send_workspace_invite(deal_id). Paige creates Client account, sends welcome email with magic-link.

STAGE 2: AGREEMENT SIGNING
  Client clicks magic-link, lands at Sign Agreement screen (NOT workspace home yet). Display BTF Service Agreement personalized with Client name + Entity + Payment Plan. Capture electronic signature (typed name + signature pad + IP + timestamp + user agent). Mandatory — cannot proceed without signing. Store signed PDF in paige_signed_agreements table. Paige fires agreement_signed event → MMA OS legal_orchestrator logs.

STAGE 3: PAYMENT TERMS ACCEPTANCE
  Display selected Payment Plan + Total + Schedule. Capture Client confirmation of payment method + recurring billing authorization. Mandatory. Store billing authorization. Paige fires payment_authorized event → MMA OS sales_dept records.

STAGE 4: INTAKE FORM
  Multi-step intake (Entity Info, Personal Info, Business Profile, Funding Goal, Documents I Have). Capture SSN (encrypted), entity formation date, EIN status, address, banking situation. Paige fires intake_submitted event → MMA OS advances current_phase pre_build → build.

STAGE 5: INITIAL DOCUMENT UPLOAD
  Required + optional documents checklist. Required: Government ID. Optional: Articles of Organization, EIN letter, recent bank statements. Files to client record document vault. Paige fires documents_initial_uploaded → MMA OS coach_orchestrator pings assigned coach.

STAGE 6: WORKSPACE HANDOFF + WELCOME
  Full BTF workspace home (voice chat, task list, phase tracker, coach thread, document vault). Send btf_welcome email via send_btf_template_email. btf_education_engine queues Email #1 for Day +4. Coach assigned, sends first welcome message via send_btf_message.

## What this enforces

  - No client enters workspace without a signed agreement on file
  - No client receives education emails before phase advances to "build" (only after intake)
  - No coach work begins before agreement + payment + intake all complete
  - Legal Department has audit trail of every state transition

## Trigger via voice (future)

Antonio via Claude/ChatGPT with Paige MCP synced: "Start onboarding for Jacqueline Turner" → LLM calls Paige MCP bridge verb send_workspace_invite → Paige creates account + emails magic-link → Antonio gets Telegram confirmation.

The voice flow is just a wrapper over the same manual trigger.

## Lead vs Client distinction

See Doctrine S111. A Lead becomes a Client at STAGE 3 completion (agreement signed + payment authorized). Before then: lifecycle_stage IN (new_lead, qualified, hot_lead, won). After: client_active.

## Out of scope for v1

  - Voice-activated trigger (future Phase 4)
  - Recurring payment integration (TBD processor — Stripe, PayPal, Square)
  - Educational materials beyond 15-email sequence (pamphlets, booklets, LaunchPad — future)
  - AI research integrations (LexisNexis, D&B, info matching — future)
  - EIN filing automation on Client's behalf (future, requires signed POA)
