# Doctrine S105 - Per-Product Send Layer
# Source: Antonio Cook | Codified: 2026-06-28

## The hard rule

One agent swarm. Three send stacks. Do not mix them.

| Offer | Send Stack | Domain/Brand | Why |
|---|---|---|---|
| MMA Skool Community ($1/$44/$97) | GHL > SMTP | mogulmakeracademy.com | Skool members already live in GHL |
| Paige DFY Services (BTF $4,997 + future) | Paige Edge Function > Resend | portal.mogulmakeracademy.com | DFY experience, owned end-to-end |
| LaunchPad SaaS ($19/mo) | LaunchPad Resend | launchpad.mogulmakeracademy.com (TBD) | SaaS product, separate customer experience |
| Internal alerts (Antonio, coaches, admin) | Telegram | n/a | Always. Never customer-facing. |

## What this means for agents

comms_orchestrator routes by lifecycle_stage:
  - lifecycle_stage IN (skool_member, skool_lead) -> GHL send path
  - lifecycle_stage IN (btf_active, dfy_active, paige_client) -> Paige + Resend send path
  - lifecycle_stage IN (launchpad_user) -> LaunchPad Resend send path
  - Internal context -> Telegram

## What this PROHIBITS

  - BTF client emails firing via GHL (wrong sender brand, no white-label)
  - Skool nurture emails firing via Paige Resend (wrong list, no MMA branding)
  - LaunchPad onboarding via GHL (wrong product context)

## Cross-stack signals are OK and required

Same brain. Different send pipes. Same customer journey.
