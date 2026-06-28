# Paige → MMA OS Bridge Contract

**Verb:** `handle_new_lead`
**Direction:** Paige (Lovable) → MMA OS sales_department (LangGraph Tier -1)
**Trigger:** Every successful public /signup completion on portal.mogulmakeracademy.com
**Doctrine refs:** §82 (two-way mirror), §88 (agent swarm), §104 (Paige positioning)

## TL;DR for Lovable

**One field is required: `email`.** Send whatever else from the wizard makes sense — extras are stored in `agent_calls.input` for analytics and the more you send, the smarter the routing.

## Bridge call shape

```http
POST https://slcqeiqcrhepicqxqjng.supabase.co/functions/v1/langgraph-bridge
Authorization: Bearer <LANGGRAPH_WRITER_API_KEY>
Content-Type: application/json

{
  "verb": "fire_agent",
  "graph_id": "sales_department",
  "input": {
    "task": "handle_new_lead",
    "payload": { ... see below ... },
    "source": "paige_public_signup"
  },
  "wait": false,
  "timeout_ms": 30000
}
```

`wait: false` is recommended — fire-and-forget so /signup completes fast.

## Payload fields

### Required

| field | type | notes |
|---|---|---|
| `email` | string | The only hard requirement. Universal join key. |

### Optional but consumed (the more, the better)

| field | type | notes |
|---|---|---|
| `first_name` | string | CRM upsert + Telegram display |
| `last_name` | string | CRM upsert |
| `source` | string | Default `"unknown"`. Recommend `"paige_public_signup"` |
| `persona` | string | `auto` / `credit` / `funding` / `business` — tagged as `persona:<value>` |
| `funding_goal_cents` | int | Drives qualification |
| `has_entity` | bool | Has LLC/Corp |
| `entity_state` | string | If has_entity: state |
| `business_type` | string | Industry / model |
| `credit_snapshot` | object | `{personal_fico, business_credit_status, ...}` |
| `attribution_source` | string | Where they heard about MMA |
| `lifecycle_stage` | string | Paige routing hint |
| `next_path` | string | Paige route decision |

### Anything else

Send it. Extras land in `agent_calls.input` JSONB. Zero schema risk.

## Qualification logic (sales_dept v4)

| Condition | Qualification | Tags | Telegram severity |
|---|---|---|---|
| `funding_goal_cents >= 5,000,000` AND `has_entity == true` | **BTF_QUALIFIED** | `new_lead`, `paige_signup`, `btf_qualified_lead`, `persona:<x>` | **warning** (call ASAP) |
| `funding_goal_cents > 0` (any goal) | **LAUNCHPAD** | `new_lead`, `paige_signup`, `launchpad_lead`, `persona:<x>` | info |
| Otherwise | **EXPLORER** | `new_lead`, `paige_signup`, `explorer_lead` | info |

## What sales_dept does on receipt

1. CRM upsert (triggers Paige mirror per Doctrine §82)
2. Smart Telegram notify (severity per qualification)
3. Logs to `agent_calls` (full audit trail)

## Failure modes

| Failure | Behavior |
|---|---|
| Missing `email` | Returns `{"error": "email required"}` |
| Bridge timeout | Logged, no client-facing impact |
| Telegram down | Logged, classification still recorded |
| Bad field types | Coerced safely (int() default 0) |

## Versioning

- **v1** (sales_dept v3): `email`, `first_name`, `last_name`, `source` only
- **v2** (sales_dept v4, current): adds rich fields + smart qualification

**No payload change required from Paige to upgrade.** v2 is additive.

## For Lovable: what helps most

1. `funding_goal_cents` as integer (not string)
2. `has_entity` as boolean
3. `persona` from the wizard
4. `source: "paige_public_signup"`
5. `wait: false` on the bridge call

Everything else is bonus.
