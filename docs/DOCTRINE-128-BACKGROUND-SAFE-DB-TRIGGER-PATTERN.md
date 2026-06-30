# Doctrine §128 — Background-Safe DB Trigger Pattern

**Codified:** 2026-06-29
**Trigger:** Lovable shipped notify-team-event Edge Function with three new triggers (tasks insert/update → notify assignee, growth_form_submissions insert → notify all admins, clients.assigned_coach_user_id change → notify the coach). All wrapped in EXCEPTION WHEN OTHERS so a notification failure can never block the originating write. Helper functions REVOKEd from PUBLIC/anon/authenticated so only the database can invoke. This doctrine generalizes that pattern for all future trigger-driven side effects.

---

## The Principle

A database trigger that fans out side effects (notifications, HTTP calls, mirror writes, audit logs) MUST satisfy two safety properties:

1. **Trigger failures cannot block the originating write.** If a user creates a task, the task must be created even if the notification fan-out fails. The notification is a downstream consequence, not a prerequisite. Otherwise the trigger becomes a single point of failure that can take down the application.

2. **Trigger helper functions cannot be invoked by application roles.** If a helper function is callable by `authenticated` or `anon`, an attacker (or a buggy client) can call it directly with arbitrary arguments. The helper should be invokable ONLY by the database itself (the `postgres` role, in the context of a trigger firing).

Both properties are enforced at the schema layer, not in application code. Application code that respects these properties only by convention is fragile; the next developer to add a trigger will skip the safety.

---

## The Two Safety Mechanisms

### 1. `EXCEPTION WHEN OTHERS` wrap on the fan-out

Every trigger function that calls an external dependency (HTTP, another schema, an Edge Function) must wrap the call in a `BEGIN ... EXCEPTION WHEN OTHERS ... END` block. The exception handler logs the failure to an internal audit table but does NOT re-raise:

```sql
CREATE OR REPLACE FUNCTION public._on_task_assigned()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
  BEGIN
    PERFORM net.http_post(
      url := 'https://...functions.supabase.co/notify-team-event',
      headers := jsonb_build_object('Authorization', 'Bearer ' || current_setting('app.notify_key', true)),
      body := jsonb_build_object(
        'event', 'task_assigned',
        'task_id', NEW.id,
        'assignee_id', NEW.user_id
      )
    );
  EXCEPTION WHEN OTHERS THEN
    -- Log to internal audit, do NOT re-raise — originating INSERT must succeed.
    INSERT INTO public._trigger_failures (trigger_name, target_id, error_message, raised_at)
    VALUES ('_on_task_assigned', NEW.id, SQLERRM, now());
  END;
  RETURN NEW;
END;
$$;
```

The `INSERT INTO _trigger_failures` inside the EXCEPTION block makes failures visible without making them fatal. A dashboard query against `_trigger_failures` surfaces patterns (e.g., "notify-team-event has been failing for 2 hours, the function might be down"). Without the audit log, silent swallows become silent bugs.

### 2. `REVOKE` from application roles

Trigger helper functions must explicitly revoke EXECUTE from `PUBLIC`, `anon`, and `authenticated`:

```sql
REVOKE EXECUTE ON FUNCTION public._on_task_assigned() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public._on_task_assigned() FROM anon;
REVOKE EXECUTE ON FUNCTION public._on_task_assigned() FROM authenticated;
```

With those revocations, the function can only be invoked by:
- The `postgres` role (used by trigger machinery)
- The `service_role` (which has bypass privileges)

Application users cannot call `_on_task_assigned` directly via PostgREST, even if they discover its existence. This closes the attack vector where a user crafts a direct RPC call to fire arbitrary notifications.

The naming convention (`_` prefix on internal helpers) signals "do not call directly" to humans. The REVOKE enforces it on the database.

---

## Why Both Properties Are Necessary

The two properties protect against different failure modes:

| Property | Protects against |
|---|---|
| EXCEPTION WHEN OTHERS | External dependency failure (HTTP timeout, Edge Function down, downstream table locked) cascading into application failure (writes start failing because the trigger throws) |
| REVOKE from app roles | Attacker (or buggy client) directly invoking the trigger helper to fan out malicious notifications, bypassing the source-of-truth event that should have triggered them |

Dropping either one creates a class of bug or vulnerability. Both must be present for every trigger that fans out side effects.

---

## Idempotency Companion Pattern

For side effects that the receiver might process more than once (network retries, duplicate events, replays), the trigger should also include an **idempotency key** in the fan-out payload. The receiver dedupes by key.

The canonical key shape is `(source_table, source_id, event_name)` — e.g., `(tasks, 46c9ef96..., task_assigned)`. The receiver maintains a small dedup table keyed on this tuple. Repeated deliveries within the dedup window are no-ops.

Without idempotency, network retries on a flaky link cause duplicate notifications. With it, the receiver naturally suppresses duplicates and the trigger can be naive about retry semantics.

This is the same pattern §122 uses for `paige_ingestion_proposals` (idempotency derived from `(tenant_id, contact_id, field, source_event_id)`).

---

## Apply to MMA OS

MMA OS has several existing trigger fan-outs that should be audited against this doctrine:

| MMA OS trigger | Current state | §128 compliance |
|---|---|---|
| pg_cron contact drain to Paige | EXCEPTION present, REVOKE not verified | Audit + add REVOKE |
| pg_net dispatch from various Edge Functions | Each function-level handler does its own try/catch | Already compliant by code convention; document the pattern |
| Future: contact upsert → mirror to Paige + log_activity | Not yet shipped | Must adopt EXCEPTION + REVOKE from day one |
| Future: any new trigger added via supabase-mcp apply_migration | Default Supabase MCP templates do NOT include the safety pattern | Update Doctrine §89 (Code Writer Agent) so notion_writer / github_writer / edge_function_writer / future db_writer follow this pattern by default |

**Rule:** any new DB trigger added to either platform must explicitly call out compliance with this doctrine in the migration commit message. PR / commit reviews should check.

---

## When This Doctrine Does NOT Apply

Not every trigger fans out side effects. Some triggers are pure data-shaping (compute a derived column, update an updated_at timestamp, enforce a check). Those triggers do NOT need EXCEPTION WHEN OTHERS — they should fail loudly because their failure means the data is incorrect, and the originating write SHOULD be blocked.

The doctrine applies specifically to triggers whose purpose is **side effects to external systems or asynchronous fan-out**. For those, blocking the originating write on failure is wrong. For pure data integrity triggers, blocking IS the correct behavior.

---

## Related Doctrines

- **§64** — Brain stores POINTERS not COPIES (interacts: trigger fan-outs that mirror data should mirror the pointer, not the copy)
- **§82** — Every customer-data write to MMA OS must mirror to Paige (the mirror is one of these trigger fan-outs — must follow this doctrine)
- **§89** — Code Writer Agent per location (writers must include this pattern in template output)
- **§94** — LLM resilience: catch and re-raise vs swallow (sibling principle for non-trigger code; this doctrine is the trigger-specific application)
- **§108** — Alert Routing Rule (notification fan-outs should route per §108 — Telegram for revenue, email for ops)
- **§120** — Schema Constraints Must Mirror Application Enums (a trigger that writes to a constrained column must produce values from the allowed set)
- **§122** — Two-Phase Commit for AI-Staged Writes (idempotency key pattern shared with this doctrine)

---

## Postscript — The Silent Cascade Failure

The failure mode this doctrine prevents is the **silent cascade**: a notification service goes down for an hour. Triggers that fan out to it start throwing. The throws propagate up through the trigger chain. Originating writes start failing. The application appears to be down — but no app-layer code has changed and no infra alert has fired (because the notification service WAS the alerting infra).

With EXCEPTION WHEN OTHERS, the notification service going down has zero impact on writes. The audit table `_trigger_failures` starts accumulating rows. A daily check on that table catches the issue at the next sweep. Notifications resume when the service comes back. No customer impact.

With REVOKE from app roles, an attacker who discovers the trigger function name cannot fire it directly. They have to actually create the source-of-truth row (creating a real task, real form submission, etc.), which leaves an audit trail and is subject to RLS scrutiny.

Both protections are cheap to add at migration time. Both are expensive to add after a production incident. This doctrine makes them the default.
