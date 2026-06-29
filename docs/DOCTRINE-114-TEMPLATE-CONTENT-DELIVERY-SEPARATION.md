# Doctrine S114 - Template Content/Delivery Separation
# Source: Antonio Cook | Codified: 2026-06-29
# Status: CANONICAL. Resolves the question of who owns email/comms templates across MMA OS and Paige.

## The principle

**MMA OS owns template CONTENT. Paige owns template STORAGE and DELIVERY. LangGraph owns template TRIGGERS.**

Three concerns, three owners, zero ambiguity.

## The division of labor

| Concern | Owner | System | Why |
|---|---|---|---|
| **Template CONTENT** (the actual copy, subject lines, variable placeholders) | MMA OS / Claude / Antonio | Markdown files in mma-os/docs/btf-emails/ + Notion knowledge base | Antonio writes voice. Claude drafts. Edits happen in source-of-truth markdown, pushed to Paige via upsert_email_template MCP. |
| **Template STORAGE** (the database row, key indexing, version history) | Paige | bfmyebsjyuoecmjskqhs.email_templates table | Templates need to be query-able by the system that SENDS them. Storage co-locates with delivery. |
| **Template DELIVERY** (actual SMTP send, Resend integration, bounce handling) | Paige | bfmyebsjyuoecmjskqhs send-transactional-email + auth-email-hook Edge Functions | Single point of integration with Resend. Paige owns all customer-facing email infrastructure per Doctrine S105. |
| **Template TRIGGERS** (deciding WHEN to fire WHICH template for WHOM) | MMA OS (LangGraph) | btf_education_engine, btf_stall_detector, btf_lifecycle_engine + future agents | Trigger logic lives with business logic. LangGraph reads state from MMA OS Supabase, decides, calls paige-mcp-proxy. |

## The workflow

1. **Claude drafts** new template content (markdown) in mma-os/docs/btf-emails/{category}/{slug}.md
2. **Antonio reviews/approves** in chat or PR
3. **upsert_email_template MCP tool** pushes the approved content to Paige's email_templates table (via paige-mcp-proxy)
4. **LangGraph agent fires the trigger** (e.g. btf_education_engine on its 8 AM cron schedule)
5. **send_btf_template_email MCP tool** routes to Paige's send-transactional-email Edge Function
6. **Resend** delivers via portal.mogulmakeracademy.com or notify.paigeagent.ai

## Why this division wins

- **Antonio retains copy control** without needing Lovable in the loop for every wording change
- **Lovable doesn't need to touch templates** after the table schema is finalized - pure data layer
- **Triggers live with business state** - LangGraph already has access to btf_deals, agent_calls, etc. - no need to recreate that data in Paige
- **Single source of truth for content** - markdown in mma-os repo = canonical. If Paige's email_templates row drifts, we re-push from source.
- **Per-program scaling** - add LaunchPad? New folder mma-os/docs/launchpad-emails/, same upsert pattern. Add DFY? Same.

## Cross-doctrine consistency

- **Doctrine S82** (every customer write to MMA OS mirrors to Paige) - data flow direction unchanged
- **Doctrine S105** (per-product send layer) - delivery routing unchanged; this doctrine adds the WHERE-IS-THE-CONTENT clarity
- **Doctrine S109** (Antonio = MMA OS admin only, Lovable = Paige admin only) - access boundaries respected; Antonio edits markdown in mma-os repo (his domain), upsert tool pushes into Paige (Lovable domain) via MCP without crossing admin boundaries
- **Doctrine S113** (Legal Dept philosophy) - same principle: agreements stored in Paige (rag_documents), but content controlled from MMA OS

## What this means in practice for the 9 remaining BTF templates

The 9 remaining BTF lifecycle/stall templates (welcome, intake_reminder, weekly_progress, phase_advance, payment_received, funded, btf_doc_requested, btf_stall_doc, btf_stall_intake):

- Currently exist as markdown in mma-os/docs/btf-emails/
- Need to be pushed to Paige email_templates table via upsert_email_template MCP
- Will be triggered by btf_lifecycle_engine + btf_stall_detector agents

**Antonio controls the copy. Paige stores and ships. LangGraph decides when.**
