# Doctrine §125 — Per-Feature Role Gating

**Codified:** 2026-06-29
**Trigger:** Lovable shipped the RoleGate sweep — `useUserRoles` hook (single source of truth for isAdmin/isCoach/isClient/isBroker/isStaff), `<RoleGate allow=[...]>` wrapper with friendly "Restricted area" fallback panel, `<ClientOnly>` wrapper for `/workspace/*` and `/portal/*`, plus toolbar "More" menu that hides admin-only items from coaches. This is the UI-layer complement to §123 (between-surface routing) — §123 routes users to their canonical home; §125 gates the individual features inside that home.

---

## The Principle

The database is the real boundary. RLS policies enforce who can read and write what data. But RLS does not (and should not) gate the UI — a half-rendered page that silently shows empty lists because RLS filtered everything out is a worse UX than a friendly "Restricted area" panel that says "this feature is for admins."

The right architecture has **two layers of gating**:

1. **DB layer (RLS):** the actual security boundary — what data can the user read or write
2. **UI layer (RoleGate):** the UX layer on top — what features does the user see at all

The UI layer can be more permissive than the DB layer (route is visible, RLS returns empty data) or more restrictive (route is hidden, even though RLS would allow). Restrictive UI on top of permissive RLS is the right default for any feature that has no meaningful coach/client interaction — saving the coach from clicking into a settings page where every action will fail.

---

## The 5 Effective Roles (Paige)

| Role | Sees in admin shell | Sees in /workspace | Sees in /portal |
|---|---|---|---|
| `owner` (Antonio) | Everything + Platform/Tenants, MCP OAuth clients, API keys, sub-agent forge "hard agents" | yes (preview) | yes (preview) |
| `admin` | Tenant-wide CRM + ops + integrations + workflows + growth + approvals + members & roles + settings | yes (preview) | yes (preview) |
| `coach` | Assigned contacts + pipeline + tasks + approvals + messaging + funding lens (read), NO integrations/settings/members/workflows/growth | NO (restricted panel) | NO (restricted panel) |
| `client` | NO (restricted panel) | yes | yes |
| `broker`, `broker_team_member` | NO (their own /broker/app surface) | NO | NO |

Three more roles exist in the DB but are not yet surfaced: `finance`, `sales`, `viewer`. Each will get its own gate spec when surfaced.

---

## The Three Gating Primitives

### 1. `useUserRoles` hook

Single source of truth for role checks. Returns booleans: `isOwner`, `isAdmin`, `isCoach`, `isClient`, `isBroker`, `isStaff` (= owner OR admin OR coach). Any role check anywhere in the UI must use this hook. Direct `user.role === "admin"` comparisons scattered through page components are a code smell that must be refactored back to the hook.

### 2. `<RoleGate allow={["admin","owner"]}>...</RoleGate>` wrapper

Wraps a route or feature. If the current user is in the allowed list, renders children. If not, renders the inline access-denied fallback panel ("Restricted area — this feature is for admins"). Used at the route level in `Admin.tsx` to wrap admin-only routes (Settings, Members, Integrations, etc.).

### 3. `<ClientOnly>` wrapper

Special-cased gate for `/workspace/*` and `/portal/*`. Allows clients through. Allows owner/admin through for preview purposes (matches the `?stay=1` pattern from §123). Coaches and brokers see the "Member workspace" fallback panel.

---

## Classification — Admin-Only vs Coach-Friendly

This is the canonical classification as of the Lovable RoleGate sweep ship:

**Admin-only routes (wrapped in `<RoleGate allow={["admin","owner"]}>`)**:
- Settings, Members, Maintenance, Brokers admin
- Integrations Hub + every `/integrations/*` config page
- Signatures, Social, Knowledge Base admin
- Banking, Business Credit, Owner Credit (admin views)
- Subscriptions & Revenue
- Observability (Usage + Errors)
- Platform Tenants

**Coach-friendly (no wrapper, defaults to authenticated)**:
- Dashboard, Contacts, Pipeline, Inbox
- Tasks, Approvals (scoped via `can_access_contact()` at the data layer)
- Workflows, Campaigns
- Bookings, Lead Enrichment
- Funding Lens / Portfolio / Pipeline (read)
- Support
- Affiliates (substituted with `MyReferralsPanel` for coaches instead of admin affiliate management)

**Owner-only routes (wrapped in `<RoleGate allow={["owner"]}>`)** — to ship in next phase:
- Sub-Agent Forge "hard agents" path (per §124)
- Platform-wide billing
- MCP OAuth client management
- Tenant Switcher

---

## The Toolbar Hide-from-Coaches Pattern

The 7-hub toolbar (Dashboard, Contacts, Pipeline, Inbox, Tasks & Approvals, Campaigns, Automation, Insights) is universal — every role sees the same hub bar (subject to RoleGate on routes inside each hub). But the "More" overflow menu is filtered: coaches don't see Members, Integrations, Settings, Maintenance, Brokers admin. Hiding from the menu prevents dead-link clicks; the RoleGate on the destination route is the safety net if a coach somehow gets there via bookmark.

**Rule:** if a feature is admin-only via RoleGate, it must ALSO be hidden from coach-side toolbar menus. The gate is the safety net; the menu hide is the UX.

---

## Apply to MMA OS

MMA OS does not yet have a comparable per-feature UI gating layer because it does not have a user-facing UI in the same shape — it's an orchestration backplane plus Cowork chat surfaces. But the principle applies to the Telegram Command Center and to any future MMA OS admin dashboards:

- The Telegram Command Center `/send`, `/lead`, `/campaign-control` commands are owner-only by Telegram chat ID gate (Antonio's chat ID is hardcoded)
- Future MMA OS dashboards must adopt the same useUserRoles-style hook before exposing any role-mixed surface
- The `<RoleGate>` pattern is the right shape for any future MMA OS UI

---

## Related Doctrines

- **§88** — Master Orchestrator Agent (orchestrator agents respect caller role context)
- **§115** — Paige Multi-Tenant Pivot (per-tenant scoping is layered on top of per-feature role gating)
- **§117** — Entity Separation + MCP Control Plane (role gating respects entity boundaries)
- **§118** — Master Tenant vs Sub-Tenant Automation (sub-tenants do not see master-tenant-only features)
- **§123** — Role-Based Login Routing (this doctrine is the UI complement — §123 routes users to their canonical home, §125 gates the features inside)
- **§124** — Self-Extending Sub-Agent Factory (hard agents are owner-only per §125)

---

## Postscript — The "Half-Rendered Page" Failure Mode

The most common failure mode in role-aware platforms is the **half-rendered page**: a coach navigates to /admin/settings, the route renders, every list query returns empty (because RLS filtered everything), and the coach is left staring at a blank screen wondering "is this broken?"

The blank-screen experience erodes trust faster than a "you don't have access" message ever could. The coach assumes the platform is buggy. They stop trying admin pages. They eventually stop trying anything that isn't labeled "coach". Adoption suffers, but the bug is invisible to the platform team because there's no error anywhere — RLS is working as designed.

The RoleGate pattern surfaces this case with a friendly "Restricted area" panel. The coach immediately understands "this isn't for me." Trust preserved. Adoption preserved. The bug becomes self-evident.
