# Doctrine S111 - Lead vs Client State Distinction
# Source: Antonio Cook | Codified: 2026-06-29
# Status: CANONICAL. Locks the data model + UX boundary between Leads and Clients.

## The principle

**A Lead is anyone in the pipeline who has NOT signed a service agreement + authorized payment.**
**A Client is anyone who has signed a service agreement AND authorized payment.**

The transition happens at Onboarding Flow STAGE 3 completion (per Doctrine S110).

## Lifecycle stages — canonical sequence

| Stage | Type | Description |
|---|---|---|
| `new_lead` | Lead | Just entered the funnel (form submit, ad click, referral, manual add) |
| `qualified` | Lead | Has been scored as fit (e.g. sales_dept.handle_new_lead → BTF_QUALIFIED, LAUNCHPAD, EXPLORER) |
| `nurturing` | Lead | In an active nurture sequence (Skool 45-day, etc.) |
| `hot_lead` | Lead | High-intent signals (recent engagement, qualified-bucket call requested) |
| `negotiating` | Lead | Sales conversation active, terms being discussed |
| `won` | Lead (paid, pre-signing) | Paid initial deposit / pay-in-full, but NOT yet signed agreement |
| `client_active` | Client | Signed agreement + payment authorized — workspace access granted |
| `client_paused` | Client | Payment lapse or temporary pause |
| `client_churned` | Client | Terminated (refund issued, cancellation, or non-payment) |
| `client_funded` | Client | Completed BTF program + funded (terminal success state) |
| `client_alumni` | Client | Completed program (funded or not) + transitioned to alumni status |

## Why this distinction matters

### Different UX
  - Leads see the public marketing site or coach-driven sales pages
  - Clients see the BTF workspace with phase tracker, document vault, coach thread

### Different data captured
  - Leads: name, email, phone, source, persona, basic interest
  - Clients: signed agreement, payment authorization, SSN (encrypted), full entity details, document vault

### Different agent treatment
  - Leads: sales_dept owns them, nurture engines fire, no BTF email sequence
  - Clients: customer_success_dept owns them, btf_education_engine fires, btf_stall_detector watches them

### Different access boundaries
  - Leads cannot access client portal workspace features
  - Clients cannot access lead-tier sales pages

## Paige data model implication

Lovable needs to ensure:
  - `clients` table has a `lifecycle_stage` field that supports all 11 values above
  - UI permission gates check `lifecycle_stage` to grant/deny workspace access
  - Search filters distinguish Lead vs Client views
  - Pipeline visualization separates Lead pipeline from Client pipeline
  - "Won" state is the transitional bucket — paid but not yet workspace-active

## MMA OS bridge implication

When Paige fires events for state transitions:
  - new_lead → qualified: sales_dept handles via existing handle_new_lead
  - qualified → won: sales_dept.log_btf_close (existing)
  - won → client_active: NEW event needed — fires after agreement signed + payment authorized
  - client_active → client_funded: existing advance_btf_phase to "funded"

## Special case: Paid but not yet onboarded

Jacqueline as of 2026-06-29 is in this state: she has PAID Antonio outside the system but has NOT signed the agreement or completed onboarding. Her lifecycle_stage should be `won` until she enters the Onboarding Flow and completes STAGES 2-3 of Doctrine S110. Then she becomes `client_active`.

This state is critical — it represents revenue collected that has not yet been formally contracted. Legal Department must track these "open won" deals and ensure agreements get signed before substantial service delivery begins.

## What this PROHIBITS

  - No BTF education emails to anyone not in `client_active` state
  - No coach work assigned to anyone not in `client_active` state
  - No workspace access to anyone not in `client_active` state
  - No marketing-nurture emails to anyone already in `client_active` state (separation of audiences)
