# Doctrine S116 - Build the System, Not the Use Case
# Source: Antonio Cook (verbatim directive 2026-06-29)
# Status: CANONICAL. Lifetime rule for how Claude, Lovable, and future agents approach BTF + Paige + every future product.

## Antonio's verbatim directive

"I don't need you to hard code anything about Jacqueline. I don't want you guys referring back to Jacqueline all the time about client experience and all of that other stuff. We don't want to do that. We just want the function to work properly."

## The principle

**Build the function. Do not build the customer.**

The system either works for every client of its archetype, or it does not work. Specific named customers are NEVER targets of system optimization, test cases, or architectural decisions. The founder handles VIP clients externally when needed — that is the founder's prerogative — but the SYSTEM does not bend for any one person.

## What this means in practice

### What we DO

- Build flows that work for any BTF client #1 through #1,000 identically
- Test against archetypes: a generic "BTF Get-Started client" or "first-week Paige tenant"
- Use synthetic test personas (mrmogulmaker+test@gmail.com or similar Antonio-controlled addresses)
- Generalize patterns across all clients in a tier (every Get-Started client gets the same intake, the same drip, the same coach assignment logic)
- Trust the system to handle whoever shows up next

### What we DO NOT

- Hard-code customer-specific values (no client_id constants, no IF customer_name = X branches)
- Create per-client workflows, agents, or templates
- Reference real client names in code, doctrines, or build instructions
- Block on "does this work for [specific customer]" when we should be asking "does this work for everyone like that customer"
- Build Jacqueline-shaped infrastructure (or any-other-specific-person-shaped infrastructure)

### The "externally handled VIP" pattern

When a high-priority customer needs special handling that the system does not yet support, the FOUNDER handles them outside the system (manual emails, direct calls, bespoke arrangements). The system is NOT modified to accommodate them. This preserves system integrity while giving the founder flexibility.

Acceptable: "I will personally handle Jacqueline's onboarding via direct email until the system is fully functional."

Not acceptable: "Add a special-case branch in btf_onboarding_engine for Jacqueline."

## Why this matters for the exit story

Multi-tenant SaaS (Doctrine S115) gets valued on REPEATABLE process, not on heroic founder effort. Every client-specific hack in the codebase is a debt the acquirer prices into the deal at a discount. Every generalized flow that handles ANY client in its archetype is an asset.

The buyer asks: "Will this still work when Antonio is no longer answering Jacqueline's emails personally?" The answer must be YES, because the SYSTEM works — not because Antonio works.

## Test directive

When Claude or Lovable starts to write "for Jacqueline" or "Jacqueline-specific" or references any named client in build instructions, STOP. Rewrite the instruction so it describes the ARCHETYPE the system serves, not the PERSON who happens to be in that archetype right now.

Before: "Update Jacqueline's btf_deals row before flipping the engine live."
After: "Ensure the FIRST BTF client through the onboarding flow has a complete btf_deals row (all required fields populated) before flipping the engine live."

Same outcome. Different mental model. The second one extends to client #2, #3, #1,000.

## Cross-doctrine consistency

- **Doctrine S72** (Exit-Ready Architecture) — This doctrine is its operating principle at the customer level
- **Doctrine S73** (Test fires route to Antonio first) — Synthetic test personas use Antonio's own email, never real customer addresses
- **Doctrine S113** (Legal Dept — one template per program, not per client) — Same principle at the legal layer
- **Doctrine S114** (Template content/delivery separation) — Templates are PER PROGRAM not PER CLIENT
- **Doctrine S115** (Multi-tenant pivot) — Multi-tenant only works if the system is generalized; this doctrine is what enables that
