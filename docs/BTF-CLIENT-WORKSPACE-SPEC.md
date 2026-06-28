# BTF Client Workspace v1 — Specification
# Built inside Paige Agent AI (project 65f20d64-d5a9-4b15-bc8d-3f11f7921f16)
# White-labeled as "BTF Client Workspace" — do NOT expose "Paige" branding to clients
# Source: Antonio Cook | Drafted: 2026-06-28 | Doctrine §99 (BTF Canon) compliance

## What this is

Jacqueline Turner closed BUILD-to-FUND on 2026-06-24 ($1,000 collected, $3,997 remaining on Get-Started Plan). She needs a portal — a place to:
  - Submit her intake data
  - Upload documents we request
  - See progress through BUILD -> STACK -> FUND
  - Message her assigned MMA coach
  - Track payment status
  - Celebrate funding outcome

This is the FIRST customer-facing experience in Paige. Subsequent BTF clients will use the same workspace.

## Positioning

  - Branding shown to client:     "Build to Fund Client Workspace" (by Mogul Maker Academy)
  - Branding NOT shown to client: "Paige Agent AI" or "Paige"
  - URL pattern:                  workspace.buildbuyingpower.com OR portal.mogulmakeracademy.com (TBD)
  - Coach assignment:             Each client assigned to Antonio Daniel or Tony Robinson (existing Paige coaches)
  - Source of truth:              mma-os Supabase project (slcqeiqcrhepicqxqjng), btf_deals table
  - Paige acts as:                The UI/UX + auth layer + document storage. Reads/writes btf_deals via mma-os-bridge Edge Function.

## User flows

### Flow 1: Client onboarding (new BTF close -> portal access)

  1. BTF deal closed and logged in mma-os.btf_deals (manually OR via sales_department.log_btf_close)
  2. Trigger: white-labeled invite email to client (no "Paige" branding)
     Subject: "Welcome to your Build to Fund Workspace"
     Body:    Welcome from Antonio + login link + what to expect
  3. Client clicks invite -> sets password -> lands on Onboarding Wizard
  4. Onboarding Wizard collects intake data (see Section: Intake Data Model below)
  5. After wizard: lands on Dashboard with Phase 1 BUILD checklist visible + assigned coach card

### Flow 2: Coach interaction

  6. Coach (Antonio Daniel / Tony Robinson) logs into Paige internal view (existing)
  7. Coach sees their assigned BTF clients in a list
  8. Coach can: message client, request a document, mark a checklist item complete, advance phase
  9. Client sees updates in real time on their workspace dashboard

### Flow 3: Phase progression

  10. Coach marks Phase 1 items complete one by one
  11. When all Phase 1 items checked: "Advance to Phase 2 (STACK)" button enables
  12. Coach clicks -> phase advances -> client sees confetti + new Phase 2 checklist
  13. Repeat for STACK and FUND phases
  14. Phase 3 complete -> Funding Outcome view unlocks (amount, lender, terms)

## Required UI sections (client view)

### Section A: Dashboard (landing page)
  - Welcome banner: "Welcome back, {first_name}"
  - Current phase indicator (visual: BUILD -> STACK -> FUND with current highlighted)
  - Phase X progress (e.g., "4 of 6 items complete in Phase 1: BUILD")
  - Assigned coach card (photo, name, "Message your coach" button)
  - Payment status mini-card ($1,000 collected of $4,997, next payment expected: $497 by 2026-07-24)
  - Recent activity feed (last 5 events: doc uploaded, item completed, message received)
  - "What's next" callout (the next action the client needs to take)

### Section B: Phase Tracker (full view)
  - Three phase cards: BUILD (current), STACK (locked), FUND (locked)
  - Click into a phase -> full checklist with status per item:
    - Phase 1 BUILD: entity formation, EIN acquisition, business address, business phone, business email, business banking
    - Phase 2 STACK: vendor tradelines, retail tradelines, financial tradelines, bureau reporting verification
    - Phase 3 FUND: lender matching, application strategy, application submission, funding outcome
  - Each item shows: status (pending / in-progress / complete), assigned-to (client or MMA team), due date, notes
  - Locked phases show: "Unlocks after Phase X completes"

### Section C: Document Upload
  - Drop zone for files (drag-drop OR click to upload)
  - Per-document "requested" cards (e.g., "Driver's License — requested by your coach on 2026-06-25, status: pending upload")
  - Uploaded docs list with download/view links
  - File types: PDF, JPG, PNG, DOCX up to 25 MB

### Section D: Intake Form (collected during onboarding wizard, editable later)
  - Personal: full legal name, preferred name, DOB, personal address, personal phone, personal email
  - Existing entity (if any): name, structure (LLC/SCorp/CCorp/SoleProp), state, formation date, EIN
  - Business address (physical or virtual), business phone, business email
  - Business banking: which bank, account type, age of account
  - Business credit status: which bureaus reporting
  - Personal credit band: excellent / good / fair / building
  - Funding goal: dollar amount + timeline
  - Existing tradelines: vendor + retail counts
  - Industry / NAICS code
  - W-2 income
  - Credit partner available: yes/no/details

### Section E: Coach Messages
  - Thread view with assigned coach
  - File attachments inline
  - Coach can pin important messages
  - Client gets email notification on new coach message
  - Coach gets internal notification on new client message

### Section F: Payment Status
  - Current plan (Get-Started / Split / Pay-in-Full)
  - Total: $4,997
  - Collected: $1,000
  - Remaining: $3,997
  - Payment history (list of installments)
  - Next payment expected date (computed from plan + last payment)
  - "Manual handling" flag respected — if true, hide auto-reminder language; if false, show "Your next payment of $497 is due on 2026-07-24"
  - Link to "Update payment method" (NOT in v1 scope — placeholder only)

### Section G: Funding Outcome (locked until Phase 3 completes)
  - "Funding secured" banner
  - Amount funded, lender(s), terms summary
  - Confetti animation on unlock
  - "Share your win" prompt (optional — generates a social-ready graphic)
  - Next step: invitation to start business #2 (the Paige multi-business future)

## Required UI sections (coach view — internal)

### Coach Dashboard
  - List of assigned BTF clients with quick-glance status (phase, % complete, last activity, flag if needs attention)
  - "Needs attention" filter (stuck > 7 days, doc pending > 14 days, payment overdue, etc.)

### Per-client coach view
  - All sections the client sees
  - PLUS: phase advancement controls
  - PLUS: request-a-document modal
  - PLUS: mark-item-complete controls
  - PLUS: add-private-note (not visible to client)
  - PLUS: trigger MMA OS actions (e.g., "Log new payment", "Update plan", "Escalate to Antonio")

## Schema (Paige side — additions to existing Paige Supabase)

Note: the canonical BTF deal data lives in mma-os.btf_deals (Supabase project slcqeiqcrhepicqxqjng). Paige stores UI-specific state + reads BTF data via mma-os-bridge.

### Paige.btf_workspace_settings
  - id (uuid pk)
  - client_id (fk to Paige clients.id)
  - mma_os_btf_deal_id (uuid — pointer to mma-os.btf_deals.id)
  - portal_invited_at (timestamptz)
  - portal_first_login_at (timestamptz)
  - intake_submitted_at (timestamptz)
  - intake_data (jsonb — full intake form responses)
  - assigned_coach_id (fk to Paige coaches)
  - last_activity_at (timestamptz)
  - created_at, updated_at

### Paige.btf_phase_items (phase 1/2/3 checklist instances per client)
  - id (uuid pk)
  - client_id (fk)
  - phase (text: 'build' | 'stack' | 'fund')
  - item_key (text: 'entity_formation', 'ein_acquisition', etc.)
  - title (text)
  - status (text: 'pending' | 'in_progress' | 'complete')
  - assigned_to (text: 'client' | 'mma_team')
  - due_at (timestamptz, nullable)
  - notes (text)
  - completed_at, completed_by
  - created_at, updated_at

### Paige.btf_document_requests
  - id (uuid pk)
  - client_id (fk)
  - phase_item_id (fk, nullable — what item this doc is for)
  - title (text — "Driver's License")
  - description (text)
  - status (text: 'pending' | 'uploaded' | 'approved' | 'rejected')
  - requested_at, requested_by
  - file_url (text, nullable — when uploaded)
  - file_name, file_size, file_type
  - uploaded_at, uploaded_by
  - approved_at, approved_by
  - rejection_reason

### Paige.btf_messages (coach-client thread)
  - id (uuid pk)
  - client_id (fk)
  - sender_type (text: 'client' | 'coach')
  - sender_id (text)
  - body (text)
  - attachments (jsonb array)
  - pinned (boolean)
  - read_at (timestamptz)
  - created_at

## Integration with mma-os

Paige reads/writes BTF data via the mma-os-bridge Edge Function (already deployed at https://slcqeiqcrhepicqxqjng.supabase.co/functions/v1/mma-os-bridge).

New verbs to add to mma-os-bridge (Edge Function update on mma-os side):
  - get_btf_deal_by_id      Returns full btf_deal row for the workspace to display
  - update_btf_phase        Coach advances client to next phase (writes mma-os.btf_deals.current_phase)
  - record_btf_payment      Coach logs a new payment (writes mma-os.btf_deals.payment_collected_cents)
  - get_btf_workspace_summary  Returns deal + checklist progress for dashboard

## Auth + invite flow

  - Paige already has invite_user action (held per Doctrine §46 due to branding concerns)
  - For BTF: use a NEW white-labeled invite path that does NOT expose "Paige"
  - Invite email: from antonio@mogulmakeracademy.com OR a no-reply MMA address
  - Subject: "Welcome to your Build to Fund Workspace"
  - Login page: brand-aligned (Navy #081428, Gold #D4AF37, Bookman headers) — NO "Paige" anywhere
  - Footer: "Powered by Mogul Maker Academy" (no Paige mention)

## Phase 1 scope (v1 — ship-able in 1-2 weeks)

What MUST be in v1:
  - Dashboard (Section A) — minimum: welcome, current phase, coach card, payment status
  - Phase Tracker (Section B) — Phase 1 checklist functional, Phase 2 + 3 visible but locked
  - Document Upload (Section C) — basic drop zone + requested docs list
  - Intake Form (Section D) — full intake collected during onboarding wizard
  - Coach Messages (Section E) — basic thread
  - Payment Status (Section F) — display only (no payment processing in v1)
  - Coach Dashboard + Per-client coach view (minimum: see client, message, mark items, advance phase)
  - mma-os-bridge integration (4 new verbs)
  - White-labeled invite flow

What CAN slip to v2:
  - Funding Outcome view (Section G — locked behind Phase 3 anyway, time to build it before any client gets there)
  - "Needs attention" filter on coach dashboard
  - File approval workflow (v1: all uploaded docs are auto-listed; v2: coach can approve/reject)
  - Social share graphic generation
  - "Update payment method" (v2 — Stripe/PayPal integration)

## Success criteria

v1 ships when:
  - Jacqueline can log into her workspace
  - She can complete the intake wizard
  - She can see Phase 1 BUILD checklist
  - She can upload at least 1 document
  - She can message her assigned coach
  - She can see her payment status ($1,000 / $4,997 / remaining $3,997)
  - A coach (Antonio Daniel or Tony Robinson) can mark her Phase 1 items complete
  - Phase advancement works (Phase 1 -> Phase 2)
  - All changes propagate to mma-os.btf_deals correctly

## What this UNLOCKS

  - Jacqueline has a real portal experience (matches DFY pricing)
  - Future BTF clients onboard in minutes via the same workspace
  - Coaches have a unified view to manage all BTF clients
  - mma-os agents (sales_department) can query Paige workspace status for cross-system briefs
  - Paige goes from "internal beta" to "first external consumer-facing product"
  - Foundation for Paige's broader B2B SaaS rollout (Doctrine §72 exit-ready)

## Out of scope for v1

  - Payment processing (PayPal/Stripe integration inside the workspace)
  - Multi-business management (one client = one BTF deal in v1)
  - Mobile app (responsive web only)
  - Custom domain (lives at paige-agent-ai.lovable.app/btf-client/{id} in v1)
  - White-label for OTHER MMA programs beyond BTF
