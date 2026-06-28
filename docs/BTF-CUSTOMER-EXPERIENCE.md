# BTF Customer Experience Blueprint v1
# Source: Antonio Cook | Codified: 2026-06-28 | Doctrine §103
# Status: CANONICAL. Source of truth for ALL BTF client touchpoints.

## Purpose

Define every touchpoint a BUILD-to-FUND client experiences from close to funded and beyond. Every email, every in-portal nudge, every Telegram alert to Antonio, every coach human touch. The full operating system for keeping clients engaged, on-track, and feeling personally cared for through a 3-6 month implementation.

## Four Touchpoint Layers

| Layer | Delivers | When | Owner | Cadence |
|---|---|---|---|---|
| In-Portal | Status, requests, messages, progress visuals | Real-time on event | Paige BTF Workspace | continuous |
| Email | Welcome, progress, celebrations, requests | Cadence + triggers | n8n + Resend + comms_orchestrator | weekly + event-driven |
| Telegram (Antonio) | New close, phase advance, doc stalled, payment, funded | Real-time events | comms_orchestrator | event-driven |
| Live human (coach) | Phase kickoff, monthly review, escalation response | MONTHLY + triggered | Antonio Daniel / Tony Robinson | monthly |

**Critical clarification:** Coach human check-ins are MONTHLY, not weekly. State filings + credit bureau reporting take WEEKS — weekly coach calls would feel empty. Email cadence stays weekly for momentum + visibility.

## Complete Timeline

### Day 0 — Close Event

Triggered by: BTF deal logged via sales_department.log_btf_close

Touchpoints fired immediately:
  - **Telegram to Antonio**: "[BTF] NEW CLOSE: {full_name} | {payment_plan} | source: {source}"
  - **Email to client** (from antonio@mogulmakeracademy.com): "Welcome to BUILD-to-FUND — let us get you funded" — personal welcome + invite link + Week 1 expectations
  - **Paige**: workspace row created, coach auto-assigned via round-robin (unless manual_handling=true)
  - **btf_touchpoints row logged**: type=close_email_sent, template=welcome_v1

### Day 1 — Activation

  - **In-portal welcome banner**: "Welcome back, {first_name}. Your assigned coach is {coach_name}. They will be in touch shortly."
  - **Telegram to Antonio**: "[BTF] {first_name} logged in to workspace for first time"
  - **Email to client** (24h after invite if not logged in): "Your workspace is ready — let us start"

### Day 1-3 — Intake

  - **In-portal nudge**: "Complete your intake form so your coach can prepare Phase 1"
  - **On intake submission**: portal confetti + coach notified
  - **Telegram to Antonio** if intake stalled >48h: "[BTF] {name} has not started intake — coach should reach out"
  - **Email to client** if stalled >72h: gentle "Your coach is waiting for your intake to get started"

### Day 3 — Phase 1 BUILD Kickoff

  - **Coach human touchpoint**: Phase 1 Kickoff Call (30 min) — walks client through Phase 1 plan
  - **In-portal**: Phase 1 checklist activated with assigned items
  - **Email to client** post-call: "Here is your Phase 1 plan + first 3 documents we need"
  - **In-portal doc requests posted** by coach
  - **Telegram to Antonio**: "[BTF] {name} Phase 1 kickoff complete"

### Day 3 to ~Day 30 — Phase 1: BUILD (Formation + Fundable Foundation)

Expected duration: 2-6 weeks (state filing dependency). Coach checks in MONTHLY.

Recurring touchpoints:
  - **Email weekly Friday** (auto-generated from progress data): "Your Week with MMA — Phase 1 progress"
  - **In-portal real-time**: every doc upload → coach notified, every coach response → client notified
  - **Telegram to Antonio**: on each Phase 1 item complete + at 50% complete + at 100% complete
  - **Telegram to Antonio** for STALL alerts: any item assigned-to-client open >7 days, any doc request unfulfilled >14 days

End-of-phase:
  - **Coach human touchpoint**: Monthly Phase 1 Review (~Day 30) — review, set Phase 2 expectations
  - **All Phase 1 items complete** → Phase 2 unlock event

### Phase 1 → Phase 2 Transition

  - **In-portal**: confetti animation, "Phase 1 complete!" banner, Phase 2 STACK unlocked
  - **Email celebration**: "You finished Phase 1 — formation locked, foundation solid"
  - **Telegram to Antonio**: "[BTF] {name} ADVANCED to Phase 2 STACK"

### ~Day 30 to ~Day 120 — Phase 2: STACK (Business Credit, In Order)

Expected duration: 60-90 days (tradeline reporting takes 30-90 days per vendor). Coach checks in MONTHLY.

Recurring touchpoints:
  - **Email weekly Friday**: progress summary + which tradelines reporting, which still pending
  - **Email bi-weekly**: tradeline-specific education ("This week: D&B PAYDEX update")
  - **In-portal real-time**: every tradeline status change visible immediately
  - **Telegram to Antonio**: on each tradeline reporting confirmed, on each new tradeline opened, stalled alerts same as Phase 1

End-of-phase:
  - **Coach human touchpoint**: Monthly Phase 2 Review — confirm credit file reporting properly + ready for Phase 3
  - **Phase 2 complete** → Phase 3 unlock event

### ~Day 120 to ~Day 180 — Phase 3: FUND (Lender Matching + Application)

Expected duration: 30-90 days. Coach engagement INCREASES (this is the closing phase).

Recurring touchpoints:
  - **Email WEEKLY (not Friday — when relevant)**: lender match updates, application status
  - **In-portal real-time**: every lender match + application status change
  - **Telegram to Antonio**: every application submitted, response received, approval/denial
  - **Coach human touchpoint**: BI-WEEKLY in Phase 3 (more urgency at the close)

### Funded Event — The Celebration Touchpoint

This is THE moment. Maximum celebration energy.

  - **In-portal**: massive celebration screen, confetti, FUNDED badge, amount + lender + terms
  - **Email**: "You did it. You are funded." — personal video from Antonio (record once, reuse)
  - **Telegram to Antonio**: "[BTF] {name} FUNDED for ${amount} via {lender}"
  - **Share your win prompt**: generates social-ready graphic (MMA brand frame) for the client to post
  - **Coach human touchpoint**: 30-min Funded Debrief call
  - **btf_touchpoints log**: type=funded_celebration, metadata.amount, metadata.lender

### Post-Funded — Continued Relationship

The relationship doesn not end at funded. It transforms.

  - **Email monthly**: "How is the business doing? Here is what we are seeing in the credit landscape"
  - **Email on milestones**: 6-month anniversary, 1-year anniversary
  - **Email on birthday** (from Antonio personally)
  - **In-portal**: continued access, can keep tracking, can spin up business #2 → graduates to Paige
  - **Workshop Wednesday invite**: continues indefinitely
  - **Coach human touchpoint**: quarterly check-in (less frequent, warm)
  - **Telegram to Antonio**: on any anniversary milestone

## Stall Detection — Automated Alerts

Antonio gets a Telegram alert when ANY of these conditions trigger:

  - Intake form started but not submitted within 72h
  - Document requested by coach but not uploaded within 14 days
  - Phase 1 item assigned-to-client open >7 days
  - Coach message thread idle >14 days (last message was from client)
  - Payment installment overdue (Get-Started or Split plan)
  - Phase has been "current" for >2x expected duration (e.g., Phase 1 >60 days)
  - Client has not logged into portal in 14 days

Each stall alert includes: Client name, what is stalled, assigned coach, suggested next action.

## Email Lifecycle Catalog (canonical templates)

All templates stored in Notion (Doctrine §64 pointer pattern). Engine pulls content at send time, never copies.

| ID | Trigger | From | When |
|---|---|---|---|
| btf_welcome | Close event | antonio@mogulmakeracademy.com | Day 0 |
| btf_invite_reminder | Not logged in 24h after invite | antonio@mogulmakeracademy.com | Day 1 |
| btf_intake_reminder | Intake stalled 72h | antonio@mogulmakeracademy.com | Day 3 |
| btf_phase1_kickoff_recap | After Phase 1 kickoff call | coach via portal | Day 3 |
| btf_weekly_progress | Friday 9 AM | antonio@mogulmakeracademy.com | weekly |
| btf_phase_advance | Phase advance event | antonio@mogulmakeracademy.com | event |
| btf_doc_requested | Coach requests document | coach via portal | event |
| btf_payment_received | Payment recorded | antonio@mogulmakeracademy.com | event |
| btf_funded | Funded event | antonio@mogulmakeracademy.com | event (the big one) |
| btf_post_funded_monthly | First of each month post-funded | antonio@mogulmakeracademy.com | monthly |
| btf_anniversary | 6mo + 12mo from close | antonio@mogulmakeracademy.com | milestone |
| btf_birthday | Client birthday | antonio@mogulmakeracademy.com | annual |
| btf_workshop_personalized | Workshop Wednesday Monday-of | comms_orchestrator | weekly |
| btf_stall_intake | Intake stalled 72h | antonio@mogulmakeracademy.com | event |
| btf_stall_doc | Doc unfulfilled 14d | coach via portal | event |

## Telegram Alert Catalog (Antonio personally)

All fire via comms_orchestrator with the belt-and-suspenders Markdown fallback.

| Event | Severity | Message pattern |
|---|---|---|
| New BTF close | success | NEW CLOSE: {name} \| {plan} \| source: {src} |
| Client first login | info | {name} logged in to workspace first time |
| Intake submitted | success | {name} completed intake |
| Phase advance | success | {name} ADVANCED {old_phase} → {new_phase} |
| Item complete (50%) | info | {name} 50% through Phase {n} |
| Item complete (100%) | success | {name} 100% Phase {n} complete — ready to advance |
| Payment received | success | {name} +${amount} \| collected ${total} of $4,997 |
| Funded | success | {name} FUNDED for ${amount} via {lender} |
| Intake stalled 72h | warning | {name} intake stalled >72h — coach should reach out |
| Doc stalled 14d | warning | {name} doc "{title}" unfulfilled >14d |
| Phase stalled 2x duration | warning | {name} Phase {n} open {days}d (expected {expected}) |
| Coach thread idle 14d | warning | {name} has not heard from coach in 14d |
| Payment overdue | warning | {name} payment {installment} overdue {days}d |

## btf_touchpoints Schema (audit log)

Every touchpoint logged for analytics + replay debugging.

```sql
CREATE TABLE public.btf_touchpoints (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  btf_deal_id uuid REFERENCES public.btf_deals(id),
  layer text CHECK (layer IN ('in_portal', 'email', 'telegram', 'live_human')),
  touchpoint_type text NOT NULL,
  direction text DEFAULT 'outbound' CHECK (direction IN ('outbound', 'inbound')),
  metadata jsonb,
  delivered_at timestamptz DEFAULT now(),
  opened_at timestamptz,
  responded_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX btf_touchpoints_deal_idx ON public.btf_touchpoints (btf_deal_id, created_at DESC);
CREATE INDEX btf_touchpoints_type_idx ON public.btf_touchpoints (touchpoint_type);
```

## Doctrine §103 — Touchpoint Hygiene

Every touchpoint MUST:
  - Have a clear PURPOSE (educate, request, celebrate, retain, alert)
  - Log to btf_touchpoints (full audit trail)
  - Respect Doctrine §102 (Multi-Door Entry) — do not assume client came from any prior touchpoint
  - Use the canonical voice (founder-direct, candid, no corporate softening)
  - White-label per Doctrine §46/§123 (no "Paige" exposed to clients)
  - Have a STALL VERSION (what fires if the expected response does not happen)

## Build Order (implementation roadmap)

### Sprint 1 (this week)
  1. btf_touchpoints schema in mma-os Supabase
  2. sales_department.send_workspace_invite task
  3. First 3 email templates in Notion (btf_welcome, btf_invite_reminder, btf_intake_reminder)
  4. Telegram alert wiring for the 3 most important events (new close, phase advance, funded)
  5. Paige Day 4 spec: in-portal nudges + intake wizard + coach message thread

### Sprint 2 (next week)
  6. Stall detection workflow (n8n cron + SQL on btf_touchpoints + btf_deals)
  7. Weekly Friday progress email engine
  8. Remaining 8 email templates
  9. Coach assignment + monthly check-in calendar integration
  10. Funded celebration flow (the big payoff)

### Sprint 3+
  11. Post-funded engagement loop
  12. Anniversary + birthday automation
  13. Share your win social graphic generator
  14. Paige multi-business graduation flow
