---
template_id: btf_education_drip
trigger: Every 3 days during active phase (BUILD/STACK/FUND). Variants per phase + topic.
from: antonio@mogulmakeracademy.com
reply_to: antonio@mogulmakeracademy.com
voice: founder-direct teaching, one concept per email, no fluff
status: CONCEPT v0 — Antonio's strategic direction 2026-06-28
---

## Purpose

BTF clients have already paid $4,997. They do NOT need to be re-sold the program.
What they DO need: continuous education that reinforces WHY they chose BTF + builds
their confidence + competence as the process unfolds.

This is the EXCLUSIVE content stream — only BTF clients get it. NOT in the free
community, NOT in the Workshop Wednesday cycle, NOT recyclable to non-clients.

## Cadence

Every ~3 days during their active phase. Skip on weekends. Skip if a coach call
happened in the last 48h (don't crowd the inbox).

## Content topic ideas (one per email — keep tight)

**Phase 1 BUILD topics:**
- "Why your entity structure matters more than your industry"
- "The 5 things every banker actually checks on your business address"
- "EIN explained — and the most common mistake people make on the application"
- "How business banking decisions today affect your funding ceiling in 12 months"
- "The 3 things on your personal credit that affect your business funding (and the 47 that don't)"

**Phase 2 STACK topics:**
- "Why tradeline ORDER matters more than tradeline count"
- "D&B PAYDEX explained — what 80 actually means"
- "Net 30 vs Net 60 vs Revolving — when each one helps you"
- "The 2 retail tradelines that move your file fastest (and the 5 that don't)"
- "Why we're not opening that business credit card yet (and when we will)"

**Phase 3 FUND topics:**
- "Lender categories explained — banks vs credit unions vs online vs SBA"
- "Why some lenders approve files that others reject (it's not what you think)"
- "Application timing — why we wait 90 days from your last tradeline"
- "What a banker actually sees when they pull your file"
- "The single biggest mistake people make on the funding application (and how we avoid it)"

## Schema mapping (when this gets built)

Stored in Paige email_templates table with:
- template_id: btf_education_drip_phase_{n}_topic_{slug}
- pulls phase + topic from a content schedule per client
- skips if last touchpoint < 48h ago

## Status

Not yet implemented — this is Antonio's strategic direction for the
BTF-exclusive nurture stream that REPLACES Workshop Wednesday cross-promotion.
Build order: after Paige Day 8 ships + btf_welcome/intake_reminder/weekly_progress
are live in production.
