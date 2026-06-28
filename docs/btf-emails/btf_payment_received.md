---
template_id: btf_payment_received
trigger: Event — Payment installment recorded via sales_dept.record_btf_payment
from: antonio@mogulmakeracademy.com
voice: warm acknowledgment, no friction
status: DRAFT v1
---

Subject: Got it — payment received

Hey {{preferred_name|first_name}},

Quick confirmation:

**Payment received: ${{amount_usd}}**
Collected so far: ${{collected_total_usd}} of $4,997
{{#if remaining_usd_gt_zero}}
Remaining: ${{remaining_usd}}
Next installment expected: {{next_payment_date}}
{{/if}}
{{#if paid_in_full}}
**You are paid in full. Thank you.**
{{/if}}

No action needed. Just wanted to confirm it is on file and you are good to keep moving through your phase work.

If anything looks off, reply directly to this email — it comes to me.

— Antonio
