# Paige Agent AI — MCP Connection Guide

**Audience:** Tenant admins, developers, integration partners, and end-users connecting Paige Agent AI as an MCP server in Claude Desktop or ChatGPT Desktop.

**Source-of-truth captured:** 2026-06-30

This document is preserved here in the mma-os repository as the canonical investor-diligence record. The public-facing version of this content should be published on the Paige Agent AI product documentation surface (docs.paigeagent.ai or equivalent) when that build ships.

---

## Overview

Paige Agent AI exposes a remote MCP server (Model Context Protocol) that lets users connect any MCP-aware AI client — Claude Desktop, Claude Web, ChatGPT Desktop, ChatGPT Web, or other compatible clients — to perform CRM, BTF program management, workflow execution, and self-service customer operations directly from the AI chat.

The MCP server enforces a four-tier authorization model:

- **Platform Owner** — full platform.* + admin.* + crm.* + btf.* + workflows.run access
- **Tenant Owner** — crm.* + btf.* + workflows.run + admin.read/write + admin.delete within their tenant
- **Tenant Admin** — crm.read/write/delete + btf.* + workflows.run + admin.read/write within their tenant
- **Workspace Member (End-User)** — self.read/write/chat scoped to the user's own data only

The server auto-detects the caller's role from their authenticated database row and grants the appropriate scope. End-users cannot escalate to admin tools via consent-request manipulation — scope is determined server-side, not by the requesting client.

---

## Claude Desktop Connection

Claude Desktop supports remote MCP servers with OAuth on Pro, Team, and Enterprise plans via Settings → Connectors → "Add custom connector." No config file editing is required for the OAuth flow — it uses the same handshake as Claude Web.

### Steps

1. Open Claude Desktop
2. Go to **Settings → Connectors → Add custom connector**
3. **Name:** `Paige Agent AI`
4. **Remote MCP server URL:**
   ```
   https://bfmyebsjyuoecmjskqhs.supabase.co/functions/v1/paige-mcp
   ```
5. Click **Connect**
6. Your browser opens the Paige OAuth authorize page
7. Sign in with your Paige Agent AI account
8. Approve the connection
9. Claude Desktop receives the token and the Paige tools appear in your tool surface

### Troubleshooting

If the "Add custom connector" option is missing, one of two things is true:

- You are on the Free tier (custom connectors are gated to Pro+)
- Your Claude Desktop build is outdated — update via Help → Check for Updates

### Fallback for Free Tier (stdio bridge via mcp-remote)

For Free-tier users or users on older Desktop builds without remote MCP support, the open-source `mcp-remote` shim proxies a local stdio MCP connection to the remote OAuth-protected server.

Edit your `claude_desktop_config.json` file at the appropriate platform location:

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

Add the following configuration block:

```json
{
  "mcpServers": {
    "paige": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "https://bfmyebsjyuoecmjskqhs.supabase.co/functions/v1/paige-mcp"
      ]
    }
  }
}
```

Restart Claude Desktop after saving the file. The first time `mcp-remote` connects, it opens a browser window for the OAuth flow and caches the token locally for subsequent sessions.

---

## ChatGPT Desktop Connection

ChatGPT Desktop uses the same connector configuration as ChatGPT Web. There is no separate Desktop-only MCP configuration. If your connector works in ChatGPT Web, it will work in ChatGPT Desktop — provided your Desktop application is on a sufficiently recent build.

### Steps to Add Paige in ChatGPT

1. Go to **Settings → Connectors → Create**
2. **MCP Server URL:** the same Paige MCP URL above
3. Complete the OAuth popup
4. The Paige tools appear in your connector list

### Troubleshooting ChatGPT Desktop

If Desktop does not see connectors that work in Web:

1. Confirm you are signed into the same ChatGPT account in both Desktop and Web
2. Update Desktop to the latest build — Desktop tends to lag Web for connector rollouts by 1 to 2 releases
3. Sign out and sign back in to force a connector refresh
4. Confirm your plan tier supports custom MCP connectors — Plus, Pro, Business, and Enterprise tiers are supported; Free is not

---

## Server Architecture Notes

### Identical Behavior Across Clients

The Paige MCP server code is identical regardless of which client connects — the same OAuth discovery endpoints, the same tool definitions, the same scope grants. There is no special-casing for Web versus Desktop, or for Claude versus ChatGPT.

Differences in observed behavior are exclusively client-side. Older Desktop builds either lack the custom-connector UI entirely or use outdated MCP transport versions. Updating the client application to the latest build is almost always the resolution for connection failures.

### Role-Based Tool Surface

The tools and scopes exposed to a given session are determined by the calling user's role at authentication time. Tenant Admins receive the full CRM, BTF, and Workflows tool surface, plus bulk operations, automatically via the autograft logic. End-users receive only the self.* tool surface scoped to their own data. No per-client configuration is required to manage this — the server resolves scope from the user's role record.

### Audit and Compliance

Every MCP tool invocation is logged with the calling user, the affected target (where applicable), the tool name, and the result. Mutating operations write to `paige_audit_log` with sufficient detail for downstream compliance review.

Destructive operations (bulk_delete_contacts, suspend_tenant, remove_coach_role) require explicit confirm parameters with two-step dry-run preview flows and additional scope gates beyond the default crm.write or admin.write grants.

---

## Pending Improvements

### MCP Client Picker Logo

The MCP server's OAuth Protected Resource Metadata at `/.well-known/oauth-protected-resource` should advertise a `logo_uri` pointing to a hosted PNG of the Paige Agent AI brand mark. Without this, Claude and ChatGPT's connector picker UIs display a default placeholder icon instead of the Paige logo. This is a one-line server addition planned in a future maintenance pass.

---

## Related Documentation

- Legal terms: `/legal/terms`, `/legal/privacy`, `/legal/aup`
- Platform MSA: `/legal/tenant-msa`
- Communications consent: `/legal/communications-consent`
- ESIGN consent: `/legal/esign`

---

*This document is the canonical investor-diligence record for the MCP connection process. It is preserved in the mma-os repository under version control. The public-facing version published on the Paige Agent AI product documentation site may be updated independently as the connection process evolves.*
