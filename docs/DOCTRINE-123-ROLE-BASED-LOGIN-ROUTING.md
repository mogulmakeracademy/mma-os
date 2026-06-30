# Doctrine §123 — Role-Based Login Routing for Multi-Tenant SaaS

**Codified:** 2026-06-29
**Trigger:** Lovable shipped role-based routing — login flow now routes by role rather than a single landing page for everyone. Redirect runs at `/auth` login AND as a guard on `/app` itself, so bookmarked links and stale sessions land in the right place. `?stay=1` flag + session marker preserves the "View client experience" use case for internal users.

---

## The Principle

In a multi-tenant SaaS with multiple distinct user surfaces (admin CRM vs broker app vs client workspace vs client portal), **every user role must have one canonical home**, and the platform must route the user there automatically on every entry — login, bookmark hit, deep link, refresh of a stale URL.

A single shared landing page for "everyone who logs in" is a UX failure and a security failure simultaneously:
- **UX:** Coaches and clients see surfaces they don't need (or can't use), creating cognitive load on every login
- **Security:** Surfaces gated only by "is logged in" rather than "is the right role for this surface" leak the existence of admin features to client users, even if the actual data is RLS-protected

The fix is structural: each role gets a route, the platform routes there, period.

---

## The Paige Role → Route Mapping (as of 2026-06-29)

| Role | Canonical Home | Surface Type |
|---|---|---|
| `admin`, `coach` | `/admin` | Tenant-wide CRM |
| `broker`, `broker_team_member` | `/broker/app` | Broker portal |
| BTF workspace client (linked to tenant `clients` row) | `/workspace` | High-touch client workspace |
| Everyone else (default client) | `/app` | Paige client portal |

---

## The Two-Point Enforcement Pattern

Routing cannot be enforced at just one point. The implementation uses **two enforcement points**:

1. **Login redirect** — at `/auth` after successful credentials, the auth handler reads role and `window.location.replace`s to the canonical home
2. **Entry guard on `/app`** — if a user lands on `/app` (via bookmark, stale session, deep link from an email sent months ago), the route component checks role and redirects out if the role doesn't match `/app`

The entry guard catches the cases the login redirect misses: bookmarks saved before role changes, deep links from old emails, browser autofills that hit the wrong route. Without it, the redirect-only approach breaks the moment a user clicks an old link.

---

## The Preview Override Pattern — `?stay=1`

Internal users (admins, owner) sometimes need to see what the client experience looks like. The naive solution — letting admins land on `/app` — breaks the entry guard and creates an "is this admin on the client side or are they actually a client" ambiguity.

The right pattern is an **explicit opt-in flag**:

- Internal user clicks "View client experience" in admin shell → navigated to `/app?stay=1`
- Entry guard reads `?stay=1` AND a session marker → allows the visit
- Admin shell renders a "Return to Admin" banner anchored to the session marker
- Banner click clears the session marker → next visit to `/app` triggers the normal redirect

This preserves both safety (no accidental admin-as-client confusion) and the legitimate use case (admins previewing the client UX without logging out and re-logging in as a client).

---

## Why This Matters Cross-System

MMA OS generates URLs into Paige in many places: Telegram alerts with links to specific contacts, email campaign CTAs pointing to /admin views, BTF onboarding emails pointing to /workspace, agent-generated draft-review links pointing to /admin/approvals.

**Rule for all URL-generating code in MMA OS:** generate URLs against the role-appropriate route prefix, never a generic one. If an alert is meant for a coach, the URL must be `/admin/...` not `/app/...`. If a workspace client gets a magic link, it must point to `/workspace/...` not `/app/...`. Sending a coach to `/app` works (the entry guard redirects them) but adds a wasted hop and looks broken to the user.

**Rule for tenant-aware URL generation:** when MMA OS generates a deep link for a sub-tenant's user (post-Doctrine §115), it must use the sub-tenant's subdomain or path prefix, not the master MMA tenant's. URL generators must consume the tenant config from `clients.tenant_id` or equivalent.

---

## The Future Phase: Per-Feature Gating Within `/admin`

This doctrine establishes the **between-surface** routing. The **within-surface** gating is a separate concern that Lovable is shipping next:

- `Owner` (Antonio) — everything plus Platform/Tenants, MCP OAuth clients, API keys, platform-wide billing, Sub-Agent Forge "hard agents"
- `Admin` — tenant-wide CRM + ops, integrations, workflows, growth, approvals, members & roles within tenant, settings
- `Coach` — only assigned contacts/pipeline/tasks/approvals + messaging + funding lens (read), NO integrations/settings/members/workflows/growth
- `Finance` / `Sales` / `Viewer` — scoped slices already in the DB role enum, not yet surfaced
- `Client` — workspace + portal only, never `/admin`

The implementation pattern Lovable identified — a single `<RoleGate roles={["admin","owner"]}>` wrapper applied at the route level — is the right shape. Routes that surface API keys, workflows, integrations, member/role management, billing, or platform settings get wrapped with the Owner/Admin allowlist. Routes that surface per-contact data get wrapped with `can_access_contact()` scoping. This is the canonical pattern; reach for ad-hoc role checks scattered through page components is a code smell that should be refactored back to the wrapper.

When this lands (planned next turn at Lovable), it earns its own doctrine (§125 — Per-Feature Role Gating).

---

## Related Doctrines

- **§115** — Paige Multi-Tenant Pivot (this doctrine is the SaaS onboarding-flow corollary of the multi-tenant pivot)
- **§117** — Entity Separation + MCP Control Plane (per-tenant routing falls out naturally from entity separation)
- **§118** — Master Tenant vs Sub-Tenant Automation Capability (role gating differs between master tenant and sub-tenants — sub-tenants don't see the Sub-Agent Forge hard-agents path)
- **§119** — Conversational Control Plane (voice/chat must respect role context — same user said the same words from coach role vs admin role should not see the same set of actions)
- **§121** — Paige Sub-Agent Architecture (sub-agents inherit the calling user's role context when they decide what to surface)

---

## Postscript — The Bookmark Problem

The single most common failure mode for role-based platforms is the **stale bookmark**. A user bookmarked the wrong route months ago. The platform changed its routing model. The bookmark still resolves to an HTTP 200 page that ignores the user's role and renders something nonsensical or, worse, leaks information.

The two-point enforcement pattern (login redirect AND entry guard) is the only durable solution. The entry guard is the safety net that catches every stale bookmark, every deep link from an old email, every browser autofill. Without it, the platform looks broken to users whose bookmarks predate the routing change. With it, the platform self-corrects on every entry.

The `?stay=1` flag is the escape hatch that prevents the safety net from becoming a cage for the legitimate preview use case. Without it, internal users can never see the client UX without painful workarounds. With it, the preview is one click away and reversible.

Both pieces are required. Neither alone is sufficient.
