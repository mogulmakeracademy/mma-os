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
| `email` | string | The only hard requirement. Used as universal join key. |

### Optional but consumed (the more, the better)

| field | type | notes |
|---|---|---|
| `first_name` | string | Used for CRM upsert + Telegram display |
| `last_name` | string | Used for CRM upsert |
| `source` | string | Default: `"unknown"`. Recommend: `"paige_public_signup"` |
| `persona` | string | `"auto"` `"credit"` `"funding"` `"business"` — gets tagged as `persona:<value>` |
| `funding_goal_cents` | int | Goal amount in cents. Drives qualification. |
| `has_entity` | bool | Whether they have an LLC/Corp set up |
| `entity_state` | string | If has_entity: which state |
| `business_type` | string | Industry / business model |
| `credit_snapshot` | object | `{personal_fico, business_credit_status, ...}` — stored verbatim |
| `attribution_source` | string | Where they heard about MMA (Workshop, YouTube, referral, etc.) |
| `lifecycle_stage` | string | Paige routing hint: `"lead"` `"workspace_ready"` `"coach_qualify"` |
| `next_path` | string | Paige decided route: `"/workspace"` or `"/signup/coach-qualify"` |

### Anything else

Send it. Extras land in `agent_calls.input` as JSONB. Zero risk of breaking the bridge with new fields.

## Qualification logic (sales_dept v4)

The agent classifies every lead into one of three buckets and tags + notifies accordingly:

| Condition | Qualification | Tags applied | Telegram severity |
|---|---|---|---|
| `funding_goal_cents >= 5,000,000` AND `has_entity == true` | **BTF_QUALIFIED** | `new_lead`, `paige_signup`, `btf_qualified_lead`, `persona:<x>` | **warning** (call ASAP) |
| `funding_goal_cents > 0` (any goal) | **LAUNCHPAD** | `new_lead`, `paige_signup`, `launchpad_lead`, `persona:<x>` | info |
| Otherwise | **EXPLORER** | `new_lead`, `paige_signup`, `explorer_lead` | info |

## What sales_dept does on receipt

1. **CRM upsert** — fires `crm_orchestrator.upsert_contact` with email + name + tags (this triggers the Paige mirror back via Doctrine §82 — so the loop is closed)
2. **Smart Telegram notify** — different message + severity per qualification tier
3. **Logs everything to `agent_calls`** — full audit trail with timing

## Failure modes

| Failure | Behavior |
|---|---|
| Missing `email` | Returns `{"error": "email required"}`. Paige should validate before sending. |
| Bridge timeout | sales_dept returns error in `agent_calls.output`, no client-facing impact (fire-and-forget) |
| Telegram down | Logged, classification still recorded in agent_calls.input |
| Bad field types | Coerced safely (e.g., int(funding_goal_cents) with default 0) |

## Versioning

- **v1** (sales_dept v3): `email`, `first_name`, `last_name`, `source` only
- **v2** (sales_dept v4, current): adds persona/funding/entity/credit/attribution + smart qualification

**No payload change required from Paige to upgrade.** v2 is purely additive — old payloads still work, new fields just enable smarter routing.

## For Lovable: what would help most

1. ✅ Send `funding_goal_cents` as integer (not string)
2. ✅ Send `has_entity` as boolean
3. ✅ Send `persona` from the wizard
4. ✅ Include `source: "paige_public_signup"` so analytics know where leads came from
5. ✅ `wait: false` on the bridge call to keep /signup snappy

Everything else is bonus. Bridge is type-safe via your `BridgeVerb` enum on the Paige side — MMA OS does not impose a schema beyond `email` being non-empty.
