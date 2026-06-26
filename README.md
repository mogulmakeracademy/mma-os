# MMA OS — Mogul Maker Academy Operating System

LangGraph-powered agent layer for MMA business automation.

## Architecture

```
┌─ Notion (strategic brain — doctrines)
│
├─ LangGraph (reasoning layer) ◄── this repo
│  ├─ Brain Health Monitor       (Phase 1)
│  ├─ Continuous Improvement     (Phase 2)
│  ├─ Paige Coach Assistant      (Phase 3)
│  └─ Autonomous Triage agents   (Phase 4+)
│
├─ n8n (execution layer — cron + integrations)
│
├─ Supabase (spine — data + pgvector + realtime)
│
└─ Google Sheets (human windows — review + KPI)
```

## Project Layout

```
src/
├─ agents/
│  └─ brain_health_monitor.py    # Daily workflow health digest
├─ lib/
│  ├─ supabase_client.py         # Supabase REST + RPC wrapper
│  ├─ n8n_client.py              # n8n execution history + workflow API
│  ├─ telegram_client.py         # Telegram bot send
│  ├─ knowledge.py               # pgvector similarity search
│  └─ claude.py                  # Claude (Anthropic) LLM client
└─ tools/
   ├─ supabase_tools.py          # LangGraph tools for Supabase
   ├─ n8n_tools.py               # LangGraph tools for n8n
   └─ knowledge_tools.py         # LangGraph tools for knowledge base
```

## Setup

1. **Clone + install:**
   ```bash
   git clone git@github.com:mrmogulmaker/mma-os.git
   cd mma-os
   pip install -e .
   ```

2. **Configure environment:**
   ```bash
   cp .env.example .env
   # Fill in keys from Supabase, n8n, Telegram, Anthropic, OpenAI
   ```

3. **Local dev:**
   ```bash
   langgraph dev
   ```

4. **Deploy to LangGraph Platform:**
   Push to GitHub. LangGraph Platform auto-deploys on push.

## Agents

### Brain Health Monitor
Runs daily at 6am ET. Queries n8n execution history + Supabase automations table, reasons about workflow health using Claude, sends Telegram digest with anomalies + recommendations.

**Trigger:** Cron via LangGraph Platform scheduled invocation
**Reads:** `automations`, `activities` (Supabase) + n8n REST API
**Writes:** `activities` (records the run), Telegram (digest)

## Doctrine

This repo is the executable embodiment of MMA OS Doctrines §50, §51, §52:

- **§50** — The Brain Plays Its Position (each tool owns one position)
- **§51** — Knowledge Base Lives Where Agents Can Query It (Notion mirrors to Supabase pgvector)
- **§52** — Four-Layer Brain Architecture (Notion + LangGraph + n8n + Supabase + Sheets)

See SUPABASE_SPINE.md in the parent project for schema reference.
