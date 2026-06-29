# Doctrine S74 - verify_jwt = false for Custom Bearer Auth
# Codified: 2026-06-29 (originally) | File created + amendment added: 2026-06-29 (this session)
# Status: CANONICAL.

## The principle

When a Supabase Edge Function uses CUSTOM bearer-token authentication (verifying the Authorization header against an env-stored API key), the deployment MUST explicitly set `verify_jwt: false`.

If `verify_jwt: true` (the Supabase default), the platform's JWT validation layer rejects any request whose Authorization header isn't a valid Supabase-issued JWT, BEFORE the request reaches your function code. Your custom bearer check never runs, every legitimate caller gets 401 UNAUTHORIZED_INVALID_JWT_FORMAT, and you spend hours debugging.

## When this applies

Every Edge Function that authenticates via a custom API key (MMA_OS_BRIDGE_API_KEY, LANGGRAPH_WRITER_API_KEY, GITHUB_WRITER_KEY, etc.) needs `verify_jwt: false`. This is most of our writer/bridge/relay functions.

## When this does NOT apply

Functions that genuinely want Supabase JWT validation (e.g. functions called from the Paige frontend with a logged-in user's anon JWT) should keep `verify_jwt: true`. These functions read `req.headers.get('Authorization')`, verify it's a valid Supabase JWT, then often derive `user.id` from the validated JWT.

## How to set it correctly (per deploy path)

### Path A — Supabase CLI (recommended)
```toml
# supabase/config.toml
[functions.your-function-name]
verify_jwt = false
```
Then `supabase functions deploy your-function-name`. Reliable.

### Path B — `edge-function-writer` Edge Function (our purpose-built writer per Doctrine S89)
```json
POST /functions/v1/edge-function-writer
{
  "verb": "deploy_function",
  "function_slug": "your-function-name",
  "verify_jwt": false,
  "files": [...]
}
```
The `verify_jwt: false` field maps directly to the Supabase Management API deploy payload. Reliable.

### Path C — Supabase Management API directly
```
POST /v1/projects/{ref}/functions/deploy?slug={slug}
{
  "slug": "your-function-name",
  "verify_jwt": false,
  "files": [...]
}
```
Reliable.

## AMENDMENT (2026-06-29): Supabase MCP `deploy_edge_function` tool defaults verify_jwt to TRUE and does NOT expose an override parameter

Discovered during the LANGGRAPH secret extraction session:

The Supabase MCP `deploy_edge_function` tool (the one available to Claude in Cowork via the Supabase MCP server) does NOT expose a `verify_jwt` parameter in its JSON schema. On every deploy it defaults to `verify_jwt: true` regardless of any `config` exports inside the function code (which only work via Supabase CLI, not API).

**Symptoms:**
- Function deploys successfully via deploy_edge_function MCP tool
- Function code passes its own custom bearer check on paper
- All calls return 401 UNAUTHORIZED_INVALID_JWT_FORMAT
- `list_edge_functions` shows `verify_jwt: true` on the function

**Workaround patterns:**

### Workaround 1 — Dual-header pattern (no redeploy needed)
For a function deployed with verify_jwt: true that you can't easily redeploy:
- Authorization header: carry Supabase anon JWT (satisfies platform JWT layer)
- X-Bridge-Auth header: carry your custom bearer (satisfies your function's check)

Function code:
```typescript
const bridge = req.headers.get('X-Bridge-Auth') ||
  req.headers.get('Authorization')?.replace(/^Bearer\s+/i, '').trim() || '';
if (bridge !== EXPECTED_KEY) return unauthorized();
```

This works because Supabase's JWT layer only inspects the `Authorization` header. Your custom auth lives elsewhere. The anon JWT is publicly available via `get_publishable_keys` — it's the same key any logged-out client uses.

### Workaround 2 — Switch to `edge-function-writer` for the deploy
The `edge-function-writer` Edge Function we built per Doctrine S89 wraps the Supabase Management API and DOES expose the `verify_jwt` field. Call it instead of the Supabase MCP tool when verify_jwt: false is required from the start.

### Workaround 3 — Use Supabase CLI from local dev
If you're at a workstation with the Supabase CLI installed, `supabase functions deploy --no-verify-jwt your-function-name` honors the flag. Cowork's sandbox doesn't have the CLI installed, so this is operator-only.

## Test ritual after deploying any custom-bearer Edge Function

1. `list_edge_functions` → confirm `verify_jwt: false` on the row
2. Fire a known-good request via pg_net (in-Supabase HTTP, no sandbox restrictions)
3. Confirm response status (200 or expected error code) — not 401 UNAUTHORIZED_INVALID_JWT_FORMAT
4. If 401 with that exact message: verify_jwt is still true, fix before continuing

## Cross-doctrine consistency

- **Doctrine S60** (Chrome-first verification) — Workaround test ritual aligns: use `get_logs` for post-mortem, pg_net for active probing
- **Doctrine S89** (Code Writer Agent Per Location) — `edge-function-writer` is the canonical deploy path when verify_jwt: false is required from the start
- **Doctrine S91** (SUPABASE_ prefix reserved) — same family of "Supabase platform footguns we documented after stepping on them"
- **Doctrine S119** (Conversational Control Plane) — most of the MCP tool surface depends on custom-bearer-auth Edge Functions, so getting this right is foundational

## Bottom line

Custom bearer auth = verify_jwt: false. Use Supabase CLI, edge-function-writer, or Management API directly for the deploy. The Supabase MCP `deploy_edge_function` tool is not safe for this case without the dual-header workaround.
