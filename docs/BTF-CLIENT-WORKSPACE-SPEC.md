# BTF Client Workspace v1 — Specification
# Built inside Paige Agent AI (project 65f20d64-d5a9-4b15-bc8d-3f11f7921f16)
# White-labeled as "BTF Client Workspace" — do NOT expose "Paige" branding to clients
# Source: Antonio Cook | Drafted: 2026-06-28 | Doctrine §99 (BTF Canon) compliance
# Status: SUPERSEDED 2026-06-29 — Lovable shipped the 6-step BTF Onboarding Wizard end-to-end per Doctrine §110. Preserved here as reference for archetype-level spec intent.

## What this is

The BTF Client Workspace is the FIRST customer-facing experience in Paige. Every BTF client uses the same workspace — there is no per-client customization (Doctrine §116).

Any BTF client needs a portal — a place to:
  - Submit intake data
  - Upload documents requested by their coach
  - See progress through BUILD -> STACK -> FUND
  - Message their assigned MMA coach
  - Track payment status
  - Celebrate funding outcome

Per Doctrine §116, this spec describes the ARCHETYPE workspace. Any concrete numbers in examples below are illustrative of the BTF Get-Started archetype, not anchored to any individual customer.

## Positioning

  - Branding shown to client:     "Build to Fund Client Workspace" (by Mogul Maker Academy)
  - Branding NOT shown to client: "Paige Agent AI" or "Paige"
  - URL pattern:                  portal.mogulmakeracademy.com
  - Coach assignment:             Each client assigned to an existing Paige coach (resolved by coach_id, not by name in code)
  - Source of truth:              mma-os Supabase project (slcqeiqcrhepicqxqjng), btf_deals table
  - Paige acts as:                The UI/UX + auth layer + document storage. Reads/writes btf_deals via mma-os-bridge.

## User flows

### Flow 1: Client onboarding (new BTF close -> portal access)
  1. BTF deal closed and logged in mma-os.btf_deals (via sales_department.log_btf_close)
  2. Trigger: white-labeled invite email to client (no "Paige" branding)
  3. Client clicks invite -> sets password -> lands on Onboarding Wizard
  4. Wizard collects intake data
  5. After wizard: lands on Dashboard with Phase 1 BUILD checklist + assigned coach card

### Flow 2: Coach interaction
  6. Assigned coach logs into Paige internal view
  7. Coach sees assigned BTF clients in a list
  8. Coach can: message client, request a document, mark a checklist item complete, advance phase
  9. Client sees updates in real time

### Flow 3: Phase progression
  10. Coach marks Phase 1 items complete one by one
  11. When all Phase 1 items checked: "Advance to Phase 2 (STACK)" button enables
  12. Coach clicks -> phase advances -> client sees new Phase 2 checklist
  13. Repeat for STACK and FUND phases
  14. Phase 3 complete -> Funding Outcome view unlocks

## Required UI sections (client view)

### Section A: Dashboard
  - Welcome banner: "Welcome back, {first_name}"
  - Current phase indicator (BUILD -> STACK -> FUND)
  - Phase X progress (e.g., "4 of 6 items complete in Phase 1: BUILD")
  - Assigned coach card (photo, name, "Message your coach" button)
  - Payment status mini-card (collected vs $4,997 vs remaining)
  - Recent activity feed (last 5 events)
  - "What's next" callout

### Section B: Phase Tracker
  - Three phase cards: BUILD (current), STACK (locked), FUND (locked)
  - Click into a phase -> full checklist:
    - Phase 1 BUILD: entity formation, EIN acquisition, business address, business phone, business email, business banking
    - Phase 2 STACK: vendor tradelines, retail tradelines, financial tradelines, bureau reporting verification
    - Phase 3 FUND: lender matching, application strategy, application submission, funding outcome
  - Each item: status, assigned-to (client or MMA team), due date, notes
  - Locked phases show: "Unlocks after Phase X completes"

### Section C: Document Upload
  - Drop zone for files
  - Per-document "requested" cards
  - Uploaded docs list with download/view links
  - File types: PDF, JPG, PNG, DOCX up to 25 MB

### Section D: Intake Form
  - Personal: full legal name, preferred name, DOB, address, phone, email
  - Existing entity: name, structure, state, formation date, EIN
  - Business address, business phone, business email
  - Business banking: which bank, account type, age
  - Business credit status: bureaus reporting
  - Personal credit band
  - Funding goal: dollar + timeline
  - Existing tradelines
  - Industry / NAICS code
  - W-2 income
  - Credit partner available: yes/no

### Section E: Coach Messages
  - Thread view with assigned coach
  - File attachments inline
  - Coach can pin messages
  - Notifications on new messages

### Section F: Payment Status
  - Current plan (Get-Started / Split / Pay-in-Full)
  - Total: $4,997
  - Collected: {dynamic per client}
  - Remaining: {dynamic per client}
  - Payment history
  - Next payment expected date
  - "Manual handling" flag respected
  - "Update payment method" placeholder (NOT in v1 scope)

### Section G: Funding Outcome (locked until Phase 3 completes)
  - "Funding secured" banner
  - Amount funded, lender(s), terms summary
  - Confetti animation
  - "Share your win" prompt
  - Next step: invitation to start business #2

## Coach view (internal)

### Coach Dashboard
  - List of assigned BTF clients with quick-glance status
  - "Needs attention" filter

### Per-client coach view
  - All sections the client sees
  - PLUS: phase advancement controls
  - PLUS: request-a-document modal
  - PLUS: mark-item-complete controls
  - PLUS: add-private-note (not visible to client)
  - PLUS: trigger MMA OS actions

## Schema (Paige side)

The canonical BTF deal data lives in mma-os.btf_deals. Paige stores UI-specific state + reads via mma-os-bridge.

### Paige.btf_workspace_settings
  id (uuid pk), client_id (fk), mma_os_btf_deal_id (uuid), portal_invited_at, portal_first_login_at, intake_submitted_at, intake_data (jsonb), assigned_coach_id, last_activity_at, timestamps

### Paige.btf_phase_items
  id (uuid pk), client_id (fk), phase, item_key, title, status, assigned_to, due_at, notes, completed_at, completed_by, timestamps

### Paige.btf_document_requests
  id (uuid pk), client_id (fk), phase_item_id (fk nullable), title, description, status, requested_at, requested_by, file_url, file_name, file_size, file_type, uploaded_at, uploaded_by, approved_at, approved_by, rejection_reason

### Paige.btf_messages
  id (uuid pk), client_id (fk), sender_type, sender_id, body, attachments, pinned, read_at, created_at

## Integration with mma-os

Paige reads/writes via mma-os-bridge Edge Function. New verbs to add:
  - get_btf_deal_by_id
  - update_btf_phase
  - record_btf_payment
  - get_btf_workspace_summary

## Auth + invite flow

  - White-labeled invite path that does NOT expose "Paige"
  - Invite email from antonio@mogulmakeracademy.com
  - Subject: "Welcome to your Build to Fund Workspace"
  - Login page: Navy #081428, Gold #D4AF37, Bookman headers — NO "Paige"
  - Footer: "Powered by Mogul Maker Academy"

## Phase 1 scope (v1)

MUST be in v1:
  - Dashboard, Phase Tracker, Document Upload, Intake Form, Coach Messages, Payment Status
  - Coach Dashboard + Per-client coach view
  - mma-os-bridge integration (4 new verbs)
  - White-labeled invite flow

CAN slip to v2:
  - Funding Outcome view
  - "Needs attention" filter on coach dashboard
  - File approval workflow
  - Social share graphic generation
  - "Update payment method" (Stripe/PayPal integration)

## Success criteria

v1 ships when ANY BTF client of the Get-Started archetype can:
  - Log into their workspace
  - Complete the intake wizard
  - See Phase 1 BUILD checklist
  - Upload at least 1 document
  - Message their assigned coach
  - See their payment status (collected vs $4,997 vs remaining)
  - Have an assigned coach mark Phase 1 items complete
  - Have Phase advancement work (Phase 1 -> Phase 2)
  - Have all changes propagate to mma-os.btf_deals correctly

## What this UNLOCKS

  - Any BTF client gets a real portal experience (matches DFY pricing)
  - Future BTF clients onboard in minutes via the same workspace
  - Coaches have a unified view to manage all BTF clients
  - mma-os agents (sales_department) can query Paige workspace status
  - Paige goes from "internal beta" to "first external consumer-facing product"
  - Foundation for Paige's broader B2B SaaS rollout (Doctrine §72 + §115 multi-tenant)

## Out of scope for v1

  - Payment processing inside the workspace
  - Multi-business management (one client = one BTF deal)
  - Mobile app (responsive web only)
  - Custom domain
  - White-label for OTHER MMA programs beyond BTF

## Correction log

2026-06-29  Per Doctrine §116, removed all named-customer + named-coach references. Replaced with archetype phrasing. Coach assignment in code references coach_id (UUID), not human-readable names. Status set to SUPERSEDED — see Doctrine §110 for shipped onboarding flow.
