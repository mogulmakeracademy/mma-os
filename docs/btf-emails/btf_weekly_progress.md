---
template_id: btf_weekly_progress
trigger: Every Friday 9 AM ET — auto-generated from btf_phase_items + btf_touchpoints data
from: antonio@mogulmakeracademy.com
reply_to: antonio@mogulmakeracademy.com
voice: status report meets founder check-in
status: DRAFT v2 (Workshop Wednesday removed — BTF clients already converted, do not need re-sold)
---

Subject: Your Week with MMA — {{phase_name}} progress

Hey {{preferred_name|first_name}},

Here's where you stand at the end of the week.

**Current Phase:** {{phase_name}} ({{phase_position}} of 3)
**Items complete this week:** {{items_completed_this_week}}
**Items still in progress:** {{items_in_progress}}
**Next action on you:** {{next_client_action_or_none}}

{{#if items_completed_this_week_list}}
**What got done:**
{{items_completed_this_week_list}}
{{/if}}

{{#if next_client_action_or_none}}
**What I need from you this week:**
{{next_client_action_or_none}}

[Open your workspace →]({{portal_url}})
{{/if}}

{{#if no_client_action_pending}}
Nothing on your plate from us this week — we're working in the background. State filings and tradeline reports are processing. You'll see updates in your workspace as they land.
{{/if}}

A reminder: Phase {{phase_position}} typically takes {{expected_phase_duration}}. You're {{days_in_phase}} days in. {{pace_status}}

Keep going.

— Antonio

P.S. — Your assigned coach is {{coach_name}}. They check the workspace daily. If you have a question that can't wait, message them inside the portal — don't email me directly unless it's urgent.
