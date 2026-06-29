# Doctrine §120 — Schema Constraints Must Mirror Application Enums

**Codified:** 2026-06-29
**Trigger:** `paige_workflow_runs_status_check` incident — Paige completion poller correctly mapped LangGraph `success` → `succeeded`, but the database CHECK constraint allowed only `{completed, failed}` (legacy vocabulary). Every terminal status UPDATE was silently rejected. Workflow runs sat in `running` forever even though LangGraph had finished executing them in ~50 seconds. `cancel_workflow_run` MCP tool errored out the same way for the same reason.

---

## The Principle

When a column's permitted values are constrained at the schema layer (CHECK constraint, ENUM type, foreign key to a lookup table), the application code that writes to that column **must produce values from a strict subset** of what the schema allows.

Mismatches between the schema's allowed set and the application's written set manifest as **silently failing UPDATEs** — one of the worst bug classes in the system. The dispatch appears to succeed, the API returns 200, no exception is thrown, but the row's state never changes. Downstream pollers loop indefinitely. Cancel operations fail mysteriously. The bug is invisible until you go look at the actual row.

---

## The Triggering Incident

| Layer | Allowed values |
|---|---|
| `paige_workflow_runs_status_check` (DB) | `completed`, `failed` |
| Paige MCP `list_workflow_runs` enum (API) | `queued`, `running`, `succeeded`, `failed`, `cancelled` |
| `dispatch-queued-workflow-runs` completion poller (app code) | writes `succeeded` for LangGraph `success`, `failed` for LangGraph `error\|timeout\|interrupted` |

Three layers, three vocabularies. The poller's `succeeded` write hit a CHECK constraint that didn't list `succeeded`. Postgres rejected. The poller's try/catch swallowed the rejection. The row stayed in `running`. The sweeper saw a stale `running` row and re-dispatched. New LangGraph thread, new execution ID, same outcome. Repeat every 60 seconds for 30 minutes until human noticed.

Resolution required:
1. Replace the CHECK constraint to allow `{queued, running, succeeded, failed, cancelled}`
2. Migrate legacy `completed` rows to `succeeded` for reporting consistency
3. Backfill rows stuck in `running` > 5 min (Postgres terminal status was now writable)

---

## The Rule

For every column with a constrained domain:

1. **Define the canonical value set in ONE place.** Preferred order:
   - Lookup table with FK reference (best — additions are INSERTs, no migration needed)
   - Postgres ENUM type (good — additions are ALTER TYPE)
   - CHECK constraint listing literals (worst — every addition is a migration + drift risk)

2. **If a literal CHECK constraint is unavoidable**, the application must either:
   - Introspect `pg_constraint` to read the allowed list at runtime, OR
   - Have the constraint values generated from the same source as the application enum (codegen)
   
   Never hardcode a parallel literal list in the application.

3. **When adding a new value, the order matters:**
   - **First:** ship the schema migration that extends the constraint
   - **Then:** ship the application code that writes the new value
   - **Never the reverse**

4. **When removing a value:**
   - Only remove from the constraint AFTER verifying every application code path has been updated to not write it
   - Migrate existing rows with the removed value to a still-permitted value FIRST

---

## Detection Pattern — The Symptom Triad

The following triad is the fingerprint of an enum-drift bug:

1. An UPDATE/INSERT that appears to succeed (200 response from API, no thrown exception)
2. A row whose status field DOES NOT change after the write
3. A polling loop, sweeper, or retry mechanism that keeps observing the same state across cycles

When you see this triad, the FIRST diagnostic is:

```sql
SELECT conname, pg_get_constraintdef(oid) 
FROM pg_constraint 
WHERE conrelid = 'your_table_here'::regclass 
  AND contype = 'c';
```

Compare the allowed values against every literal the application code can write. The two sets must overlap fully for every code path.

---

## The Preferred Pattern — Lookup Table with FK

For any status-like field that may grow over time, prefer a lookup table:

```sql
CREATE TABLE workflow_run_status (
  status text PRIMARY KEY,
  description text
);

INSERT INTO workflow_run_status VALUES 
  ('queued',    'Dispatched but not yet started'),
  ('running',   'Currently executing'),
  ('succeeded', 'Completed without error'),
  ('failed',    'Terminated with error'),
  ('cancelled', 'Manually stopped before completion');

CREATE TABLE workflow_runs (
  id     uuid PRIMARY KEY,
  status text NOT NULL REFERENCES workflow_run_status(status),
  ...
);
```

Benefits:
- Adding a new status is an INSERT into the lookup table — no schema migration
- Application code can `SELECT * FROM workflow_run_status` to discover the allowed values
- No literal list duplicated across schema + app code
- The FK constraint enforces what the lookup table says — never out of sync

---

## Application-Side Defense

When writing to a constrained column, application code must:

1. **Catch and log constraint violations explicitly** — never with a bare `try/except` that swallows
2. **Surface the failure to the orchestrating layer** — a constraint violation is a correctness failure, not a telemetry failure
3. **Include the column name, attempted value, and constraint name in the log**

Specifically: bridge `logActivity` patterns, completion pollers, sweepers, and any fire-and-forget background work must NEVER swallow constraint violations. Those are bugs to surface, not noise to filter.

---

## Code Review Checklist

When reviewing a PR that adds a new status, lifecycle stage, role, tier, category, or any enum-like value:

- [ ] Does this value need to be written to the database?
- [ ] If yes, is there a CHECK constraint, ENUM type, or FK to a lookup table on that column?
- [ ] Has the constraint/type/lookup been updated to include the new value?
- [ ] Is the schema change ordered BEFORE the application code that writes the new value?
- [ ] If the constraint is a literal CHECK, can we migrate to a lookup table to prevent future drift?
- [ ] Does the write path catch and surface constraint violations explicitly?

---

## Cross-System Implications

This doctrine applies to ALL constrained columns across MMA OS and Paige:
- `paige_workflow_runs.status` (the triggering case)
- `contacts.tier` (Free, Standard, Premium, VIP, Lead Only — any future tier must extend both sides)
- `clients.tier` (mirrored from contacts)
- `workflow_registry.provider` (langgraph_bridge, n8n, direct_edge_function, webhook_external, cron_only — any new provider must extend the constraint)
- `workflow_registry.category` (campaigns, customer_support, observability, funding, editorial, admin)
- `campaign_control.status` (active, paused, killed)
- `enrollments.lifecycle_stage`
- `customer_profiles.relationship_status`

Every one of these is a candidate for the same failure mode. Audit periodically.

---

## Related Doctrines

- **§94** — LLM resilience: catch and re-raise vs swallow (sibling principle)
- **§95** — Bug → Fix → Codify ritual (this doctrine is an artifact of that ritual)
- **§109** — Paige Supabase access lives ONLY with Lovable (which is why we needed cross-team coordination to fix this — the schema lives on her side, we diagnosed on ours)

---

## Postscript — Why This Took 30+ Minutes to Find

The bug was diagnostically hostile because every layer reported success:
- LangGraph API returned 200 to bridge dispatch
- Bridge returned 200 to Paige dispatcher
- Paige `run_workflow` MCP tool returned `ok: true, status: "running"`
- Paige completion poller's UPDATE returned no error (swallowed)
- LangGraph runs themselves completed successfully

Only by calling LangGraph DIRECTLY (bypassing the entire Paige tracking layer, via a fresh diagnostic Edge Function fired via pg_net from MMA OS Postgres) could we see that the runs had already finished. That diagnostic capability — `lg-quick-diag` on slcqeiqcrhepicqxqjng — is preserved as standing infrastructure for future similar investigations.

The lesson: **when every layer reports success but the system isn't progressing, the failure is silent. Hunt for swallowed exceptions and constraint violations first.**
