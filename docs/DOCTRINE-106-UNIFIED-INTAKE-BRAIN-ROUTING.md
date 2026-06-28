# Doctrine S106 - Unified Intake, Unified Brain, Unified Routing
# Source: Antonio Cook | Codified: 2026-06-28

## The principle

Every lead, from every door, feeds the same brain.
The brain decides where they go, what they get next, and which agent handles them.
Customer never sees the seams.

## All lead-entry doors

| Door | Source | Status |
|---|---|---|
| Skool community signup | Skool platform | Live (Zapier > GHL > MMA OS) |
| Public /signup wizard | portal.mogulmakeracademy.com | Live (Paige Day 5, fires handle_new_lead) |
| Workshop Wednesday landing page | GHL form | Live |
| Coffee Hour landing page | GHL form | Live |
| Lead magnets | TBD | Planned |
| LaunchPad signup | LaunchPad portal | Pending |
| Paid ad landing pages | TBD | Planned (marketing layer) |
| YouTube/TikTok/IG clips | Social > link in bio > landing | Planned (marketing layer) |
| Referral/affiliate | Affiliate program | Planned |
| Direct cold outbound | Manual > CRM | Manual today, agent-driven later |

## The brain job on every intake

1. Dedupe by email (universal join key across MMA OS contacts, Paige clients, GHL contacts)
2. Classify lifecycle_stage (lead / explorer / launchpad_user / mma_member / btf_qualified / btf_active / dfy_active)
3. Determine next step based on what they signed up for + qualification + current stage
4. Route to appropriate offer/agent (sales_dept BTF, launchpad_orchestrator SaaS, nurture engines Skool)
5. Track full journey (every touchpoint, every stage transition, kept in sync via mirror per Doctrine S82)

## What no seams means

A Skool member clicks an ad > fills landing page > fires handle_new_lead > brain recognizes existing Skool member > upgrades lifecycle_stage to mma_member_engaged_with_ad > fires no duplicate welcome > tags for appropriate offer > routes right next-touch via right send stack.

Customer experience is ONE continuous journey. Five systems coordinate behind the scenes.

## The bar

No matter where a customer is being fed in from, the brain knows what to do next.
