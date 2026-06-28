# PME Revenue Architecture (Master)
# Source: Antonio Cook | Codified: 2026-06-28 | Doctrine ÃÂÃÂ§99 + ÃÂÃÂ§100 + ÃÂÃÂ§101
# Status: LOCKED. Any structural change requires Antonio sign-off.

## DOCTRINE ÃÂÃÂ§101 ÃÂ¢ÃÂÃÂ The Three Revenue Streams (+ Future Fourth)

Project Mogul Enterprise operates THREE primary revenue streams today, with a fourth in development.

### STREAM #1 ÃÂ¢ÃÂÃÂ Mogul Maker Academy Community (Subscription)

Product:   Skool community + tiered education
Pricing:   FREE | Premium $44/mo | VIP $97/mo  (Note: legacy $8/mo Standard tier exists for grandfathered subscribers; no longer offered)
Role:      Audience-building, nurture, community moat, top of the revenue ladder
Channels:  Workshop Wednesday (weekly live), Coffee Hour (weekly), 3M curriculum
Status:    LIVE (169 Skool members as of 2026-06; includes legacy $8 grandfathered cohort)
Owns:      lifecycle_orchestrator + comms_orchestrator + content_orchestrator

### STREAM #2 ÃÂ¢ÃÂÃÂ BUILD-to-FUND (High-Ticket DFY)

Product:   Done-for-you formation + business credit + funding (BUILD/STACK/FUND)
Pricing:   $4,997 flat ÃÂ¢ÃÂÃÂ 3 plans (Pay-in-Full | Split | Get-Started)
Role:      High-ticket implementation. The biggest single revenue lever.
Channels:  Workshop Wednesday close, sales calls, paid ads (Meta + Google warm)
Status:    LIVE ÃÂ¢ÃÂÃÂ first close Jacqueline Turner (payment 2026-06-24)
Owns:      sales_department + customer_success_department

### STREAM #3 ÃÂ¢ÃÂÃÂ The Launch Pad (Lead Magnet + MRR)

Product:   Fundability assessment + personalized roadmap + AI Coach
Pricing:   FREE 2-min check (lead capture) | $19/mo unlocks full experience
Role:      Dual function:
             a) Lead magnet for Streams #1 + #2 (paid $19 customers ARE BTF prospects)
             b) Recurring MRR product
Channels:  Paid ads (Meta + Google cold), Workshop Wed, organic SEO
Status:    LIVE in Lovable (cozy-builds-together / build-bloom)
Live URL:  https://cozy-builds-together.lovable.app
Lovable:   project_id aade69f4-7f3f-447c-a864-9a59738df52a
Owns:      TBD ÃÂ¢ÃÂÃÂ needs its own orchestrator (launchpad_orchestrator?) eventually

### STREAM #4 ÃÂ¢ÃÂÃÂ Paige Agent Platform (Future B2B SaaS ÃÂ¢ÃÂÃÂ IN DEVELOPMENT)

Product:   B2B SaaS CRM + AI agent platform (currently MMA's internal CRM)
Pricing:   TBD
Role:      Long-term exit vehicle ($100M-$1B target per Doctrine ÃÂÃÂ§72)
Status:    BETA ÃÂ¢ÃÂÃÂ internal team only (Antonio, Antonio Daniel, Tashia, Tony Robinson coaches)
Roadmap:   Internal Q3 -> Brokers Q4 -> Consumer 2027
Owns:      Mirror writes from MMA OS per Doctrine ÃÂÃÂ§82 (two-way sync)

## THE FUNNEL (How They Compose)

```
                COLD TRAFFIC (paid ads + organic + referral)
                            |
                            v
              +-----------------------------+
              | The Launch Pad FREE check   |  <-- Stream #3 entry
              | (2-min fundability score)   |
              +-----------------------------+
                            |
                            v
              +-----------------------------+
              | Free MMA Skool Community    |  <-- Stream #1 free tier
              | (nurture + Workshop Wed)    |
              +-----------------------------+
                            |
            +---------------+---------------+
            v               v               v
   +----------------+ +-------------+ +----------------+
   | Standard $8mo  | | LaunchPad   | | BUILD-to-FUND  |
   | Premium $44mo  | | $19/mo     | | $4,997 DFY     |
   | VIP $97/mo     | | (MRR product)| | (high-ticket)  |
   |  Stream #1     | | Stream #3   | |  Stream #2     |
   +----------------+ +-------------+ +----------------+
                            |
                            v
                  +-----------------------+
                  | Funded business +     |
                  | future VAULT tier     |
                  +-----------------------+
```

## SCALING MOTION (Doctrine ÃÂÃÂ§72 alignment)

By 90 days (2026-09-26):
  Stream #1 ÃÂ¢ÃÂÃÂ Predictable Skool growth + paid tier upgrade rate baseline
  Stream #2 ÃÂ¢ÃÂÃÂ Multiple BTF clients moving Phase 1 -> Phase 3 + 2nd+ FUNDED client
  Stream #3 ÃÂ¢ÃÂÃÂ LaunchPad MRR > $5K/mo (265+ paid subscribers) + lead-to-BTF conversion rate measured
  Stream #4 ÃÂ¢ÃÂÃÂ Paige Agent first external broker beta seat

## BTF DETAIL (Stream #2 Canon ÃÂ¢ÃÂÃÂ see also docs/BUILD-TO-FUND-CANON.md)

[See dedicated file for full BTF briefing]

Promise:    "We build your business into one that can actually borrow."
Signature:  "We borrow to start. Then we build to own."
Phases:     BUILD (formation) -> STACK (credit) -> FUND (capital)
Personas:   High Earner | Builder In Motion
Anchor:     Jacqueline Turner ÃÂ¢ÃÂÃÂ first paying client 2026-06-24

## LAUNCH PAD DETAIL (Stream #3 Canon)

Repo:       Lovable project cozy-builds-together (aade69f4-7f3f-447c-a864-9a59738df52a)
Branding:   Mogul Maker Academy (navy/gold, Bookman serif)
Front door: "See if lenders would say yes ÃÂ¢ÃÂÃÂ and get your score." (FREE 2-min check)
Auth:       Google SSO | Apple SSO | Email+phone form (TCPA consent)
Paywall:    $19/mo unlocks full experience (trial: 30 days per Lovable description)
Features:   Fundability score, personalized roadmap, AI Coach, industry risk overlay
Stripe:     Integrated (per Lovable description)
Lead capture flow: form -> score -> trial -> $19/mo OR drop into MMA Skool

## BRAND SPINE (Doctrine ÃÂÃÂ§99 ÃÂ¢ÃÂÃÂ applies to ALL THREE STREAMS)

Master framework:   3M  Make / Manage / Multiply
Anchor philosophy:  Money Follows Management
Core thesis:        Borrower to Banker
Public location:    Atlanta, GA
Voice:              Conversational, candid, founder-direct, never corporate
Audiences:          Entrepreneurs, business owners, founders, builders, bosses

Brand colors:
  Navy        #081428
  Gold        #D4AF37
  Off-white   #F5F5F5
  Warm tint   #FAF6EC

Typography:
  Headers   Bookman Old Style (fallback Cambria)
  Body      Calibri or system sans

NEVER (across all three streams):
  - "operator" in public-facing copy
  - FCRA/dispute/credit-repair language (BTF lane separation)
  - Lithonia (always Atlanta)

## DEPARTMENT OWNERSHIP MAP (MMA OS)

Stream #1 (MMA Community):    lifecycle_orchestrator + comms_orchestrator + content_orchestrator
Stream #2 (BUILD-to-FUND):    sales_department + customer_success_department
Stream #3 (Launch Pad):       TBD launchpad_orchestrator (Phase 4 build)
Stream #4 (Paige):            paige_sync_bridge (two-way mirror, Doctrine ÃÂÃÂ§82)

Cross-stream: operations_department brief includes all three streams in morning digest
Cross-stream: master_orchestrator routes Workshop Wed + new lead events to the right stream


## CORRECTION LOG

2026-06-28  LaunchPad price corrected from $199/mo to $19/mo per Antonio direct. All references updated. This shifts positioning from premium tool to frictionless lead-magnet MRR tier.

2026-06-28  MMA Standard $8/mo tier REMOVED from active offers. Grandfathered subscribers remain. Premium $44/mo is now the entry paid tier. 3M Framework correction: Premium = MAKE IT + MANAGE IT (entry doing tier), VIP = MULTIPLY IT (scaling tier). Free = Observer (no 3M stage).

## DOCTRINE §102 OVERLAY (added 2026-06-28)

This architecture document describes the PRODUCTS we offer and how they relate. It does NOT prescribe a single customer path. Per Doctrine §102 (Multi-Door Entry Model), customers may enter through ANY of: Launch Pad, MMA Skool community (free or referral), live free workshops, paid tiers directly, BUILD-to-FUND directly, or referrals.

Read this doc as a PORTFOLIO of independent product propositions. Customers MAY adopt only one. There is no forced sequence. See docs/DOCTRINE-102-MULTI-DOOR-ENTRY.md for the canonical framing.
