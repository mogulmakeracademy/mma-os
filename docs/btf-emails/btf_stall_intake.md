# BTF Email Template: btf_stall_intake

**Trigger:** btf_stall_detector — workspace_invite >72h, no intake_submitted touchpoint
**Sender:** Antonio direct
**Reply-To:** Antonio
**Voice:** Personal check-in — Antonio founder voice, low-friction
**Variables:** {{first_name}}, {{hours_since_invite}}, {{workspace_url}}, {{coach_name}}

---

## Subject (variants)

Primary: `{{first_name}} — got a minute? Let's get your workspace going`
Fallback: `Did you find the workspace login?`

## Preheader

It's a 2-minute intake. We can't start until you're in.

## Body

```
Hey {{first_name}},

Quick personal note from me.

I sent your workspace invite {{hours_since_invite}} hours ago and I haven't seen you log in yet. That's not unusual — life is busy — but I want to make sure nothing got lost in your inbox or buried under a tab.

**Two things I need from you to start the clock:**

1. **Click into your workspace** (this is your home base for the next 90 days):
   [Open Your Workspace]({{workspace_url}})

2. **Complete the intake form** (literally 2 minutes — entity status, funding goal, what you have, what you don't)

That's it. Once that intake is in, your coach {{coach_name}} can build your playbook and we're off and running.

**If something is in your way** — wrong email got the invite, can't find the link, technical issue, second thoughts, anything — just hit reply and tell me. I read every one.

You committed to this. I committed back. Let's get to work.

— Antonio
Founder, Mogul Maker Academy

P.S. The 90-day clock doesn't start until intake is submitted. So you're not behind yet — but every day of delay is a day of fundability you're leaving on the table.
```
