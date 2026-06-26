# 🚀 Push mma-os to GitHub

This scaffold lives in your `/outputs/mma-os/` folder. Follow these steps to push it to GitHub and connect to LangGraph Platform.

## Step 1 — Create the GitHub repo

1. Go to https://github.com/new
2. **Repository name:** `mma-os`
3. **Visibility:** Private (recommended) — this contains sensitive operational details
4. **Initialize:** Leave everything UNCHECKED (no README, .gitignore, license — we have them)
5. Click **Create repository**

Copy the repo URL (e.g. `git@github.com:mrmogulmaker/mma-os.git`)

## Step 2 — Push the scaffold

Open Terminal on your Mac, then:

```bash
cd ~/Desktop                                    # or wherever you want it on your drive
# Drag the mma-os folder from your Cowork outputs window into Terminal AFTER `cp -r `:
cp -r [DRAG mma-os FOLDER HERE] ./mma-os
cd mma-os

git init
git add .
git commit -m "Initial scaffold: Supabase + LangGraph + Brain Health Monitor"
git branch -M main
git remote add origin git@github.com:YOUR-GITHUB-USERNAME/mma-os.git
git push -u origin main
```

## Step 3 — Connect to LangGraph Platform

1. Go to https://smith.langchain.com
2. Open the **LangGraph Platform** tab
3. Click **+ New Deployment**
4. Select **GitHub** → choose the `mma-os` repo
5. Branch: `main`
6. Click **Configure**

## Step 4 — Set environment variables

In LangGraph Platform deployment settings, add each of these. (Values are in `.env.example` for reference — fill the empty ones from the listed source.)

| Variable | Where to get it |
|---|---|
| `SUPABASE_URL` | Pre-filled: `https://kkjnxlbfrvixftgxxtax.supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase Dashboard → Settings → API → service_role (**reveal + copy**) |
| `SUPABASE_ANON_KEY` | Pre-filled: `sb_publishable_fYhalU2egCTzhTmhFGAQWg_XISdPnU8` |
| `N8N_BASE_URL` | Pre-filled: `https://mogulmakeracademy.app.n8n.cloud` |
| `N8N_API_KEY` | n8n → Settings → n8n API → Create API Key |
| `TELEGRAM_BOT_TOKEN` | Already in n8n credentials. Copy from Telegram Bridge credential. |
| `TELEGRAM_CHAT_ID` | Already in n8n. Same source. |
| `ANTHROPIC_API_KEY` | https://console.anthropic.com → API Keys → Create |
| `OPENAI_API_KEY` | https://platform.openai.com → API Keys → Create |
| `GHL_PIT_TOKEN` | Pre-filled |
| `GHL_LOCATION_ID` | Pre-filled |

## Step 5 — Deploy + verify

1. Click **Deploy** in LangGraph Platform
2. Wait ~2 minutes for build
3. Once green, go to the deployment's **Studio** tab
4. Run the `brain_health_monitor` graph manually with input `{"lookback_hours": 24}`
5. Check Telegram — you should get a Brain Health digest within ~15 seconds

## Step 6 — Schedule daily fire

In LangGraph Platform → your deployment → **Scheduled invocations**:
- Graph: `brain_health_monitor`
- Cron: `0 10 * * *` (6:00 AM ET = 10:00 AM UTC)
- Input: `{"lookback_hours": 24}`

## What this gives you

After Step 5, you have:
- ✅ The first LangGraph agent live
- ✅ Daily 6 AM ET Telegram digest of all workflow health
- ✅ Activity logged into Supabase for permanent audit trail
- ✅ End-to-end proof that LangGraph → Supabase → n8n → Telegram works

After this, every future agent is just a new file in `src/agents/` and a new entry in `langgraph.json`. The hard infrastructure work is done.
