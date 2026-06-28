# BTF Email Template: btf_doc_requested

**Trigger:** Event — coach requests a document from BTF client (via Paige UI button)
**Sender:** Coach (via Antonio brand: founders@mogulmakeracademy.com)
**Reply-To:** Assigned coach
**Voice:** Direct, action-oriented, helpful — Antonio founder voice
**Variables:** {{first_name}}, {{doc_name}}, {{doc_reason}}, {{current_phase}}, {{coach_name}}, {{upload_url}}

---

## Subject (variants)

Primary: `Quick ask — need {{doc_name}} to keep {{current_phase}} moving`
Fallback: `{{first_name}}, one thing on my list for you`

## Preheader

Coach {{coach_name}} flagged a document we need to advance your file.

## Body

```
Hey {{first_name}},

Quick one — your coach {{coach_name}} is working through your {{current_phase}} file and flagged that we need **{{doc_name}}** to keep things moving.

**Why we need it:**
{{doc_reason}}

**How to send it:**
Just upload it inside your workspace — takes about 30 seconds:

[Upload {{doc_name}}]({{upload_url}})

**Timeline:**
We need this within the next 7 days to keep your phase timeline on track. If you hit a snag finding it, reply to this email and {{coach_name}} will hop in.

You're doing the work. We're doing the chasing. Together we get you funded.

— Antonio
Founder, Mogul Maker Academy

P.S. If you've already sent this and we're asking again, ping us — sometimes the system needs a nudge.
```

## Notes

- Pairs with btf_stall_doc (fires if no upload within 14 days)
- {{upload_url}} is the deep-link into client workspace document section
- {{doc_reason}} is filled by coach when raising the request (1-2 sentence rationale)
