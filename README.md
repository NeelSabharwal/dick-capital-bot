# Substack → Discord Pick Bot

A personal automation that watches a paid Substack publication and pushes structured stock-pick alerts to a private Discord channel.

## What it does

Every 30 minutes the bot:

1. **Pulls new essay posts** from the publication via the authenticated Substack JSON API.
2. **Pulls new top-level chat messages** from the publication's subscriber chat.
3. **Sends each new item to Claude** (Anthropic's API) which decides whether it's an actionable trade recommendation and, if so, extracts a structured record: ticker, action (buy/sell/add/trim/hold/watch), sizing, conviction, time horizon, entry/stop/target prices, supporting quote, etc.
4. **Enriches each pick** with the current price, today's change, percent-vs-entry, and 2–3 recent headlines from Yahoo Finance — all free, no API key.
5. **Posts a rich embed** to Discord with everything above plus a row of clickable research links (Yahoo, TradingView, MarketWatch, Seeking Alpha, Google News).
6. **Tracks state** so the same post or chat message never gets re-analyzed.

Non-actionable essay posts (macro essays, market commentary) get a small grey card with just a one-line summary. Non-actionable chat messages are skipped silently to keep the noise down.

## Data flow

```
                   ┌──────────────────────────────┐
                   │       Substack JSON API      │
                   │  (authenticated via cookie)  │
                   └──────────┬───────────────────┘
                              │
              ┌───────────────┴────────────────┐
              │                                │
       posts API                        chat API (community)
       /api/v1/posts          /api/v1/community/publications/{id}/posts
              │                                │
              ▼                                ▼
        ┌──────────────────────────────────────────┐
        │   state filter — skip already-seen IDs   │
        │   (essay state + chat state, separate)   │
        └──────────────────┬───────────────────────┘
                           │
              chat: keep only messages where user_id ∈ allowlist
                           │
                           ▼
        ┌──────────────────────────────────────────┐
        │      Claude API — structured extraction  │
        │  {ticker, action, sizing, conviction,    │
        │   horizon, entry, stop, target, quote}   │
        └──────────────────┬───────────────────────┘
                           │
                           ▼
        ┌──────────────────────────────────────────┐
        │   yfinance enrichment (price + news)     │
        └──────────────────┬───────────────────────┘
                           │
                           ▼
        ┌──────────────────────────────────────────┐
        │       Discord REST API (bot token)       │
        │  → posts embed to one channel            │
        └──────────────────────────────────────────┘
```

## Project layout

```
.
├── bot.py            single-file pipeline (~330 lines)
├── .env              local secrets (gitignored)
├── .env.example      template showing required vars
├── .gitignore        excludes .env, state files, venv
├── requirements.txt  Python deps
├── state.json        seen essay-post IDs (created at runtime)
├── chat_state.json   seen chat thread UUIDs (created at runtime)
├── bot.log           append-only run log (created at runtime)
└── .venv/            isolated Python environment
```

`bot.py` has two pipelines that share helpers:

- `process_posts()` — handles essay posts.
- `process_chat()` — handles chat threads.
- `enrichment_fields()` — adds price/news/research to any embed.

Both pipelines call into the same `send_embed()` and Claude extraction helpers.

## Configuration

Publication-specific values live as constants at the top of `bot.py`:

```python
PUBLICATION_ID  = 6321441    # Substack publication ID
AUTHOR_USER_ID  = 394376039  # Whose chat messages to analyze
```

Secrets live in `.env` (never committed):

| Var | Where to get it |
|---|---|
| `SUBSTACK_COOKIE` | DevTools → Application → Cookies → `substack.sid` value (must be a paid subscriber) |
| `DISCORD_BOT_TOKEN` | discord.com/developers/applications → your app → Bot → Reset Token |
| `DISCORD_CHANNEL_ID` | Discord (Developer Mode on) → right-click channel → Copy Channel ID |
| `ANTHROPIC_API_KEY` | console.anthropic.com → API Keys → Create Key |
| `SUBSTACK_PUBLICATION_HOST` | The publication's subdomain, e.g. `foo.substack.com` |

## Setup

Requires Python 3.11+ and a paid subscription to the target publication.

```powershell
# 1. Create venv and install deps
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2. Copy the template and fill in your secrets
copy .env.example .env
# then edit .env with the values from the table above

# 3. Update PUBLICATION_ID and AUTHOR_USER_ID at the top of bot.py
#    (find them in the chat API response — see "Finding the IDs" below)

# 4. Run it
.venv\Scripts\python.exe bot.py
```

First run marks all current essay posts (except the latest, as a demo) and all current chat threads as already-seen, so you don't get spammed with backlog.

## Running on a schedule

Register a user-level Windows Scheduled Task (no admin needed) using `pythonw.exe` so no console window appears. Output goes to `bot.log`.

```powershell
$projectDir = "C:\path\to\this\folder"
$action  = New-ScheduledTaskAction -Execute "$projectDir\.venv\Scripts\pythonw.exe" -Argument "bot.py" -WorkingDirectory $projectDir
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 30)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
Register-ScheduledTask -TaskName "SubstackPickBot" -Action $action -Trigger $trigger -Settings $settings
```

The machine needs to be on and awake for runs to fire — missed runs aren't backfilled. For 24/7 coverage move it to a cheap VPS, cloud function, or any always-on host.

## How the chat filter works

The chat endpoint returns *every* top-level message — the author's and other subscribers'. By default the bot keeps only messages where `user_id == AUTHOR_USER_ID`. Other users' messages are added to the seen-state so they don't get re-checked, but they're not sent to Claude or posted to Discord.

To allowlist additional users (e.g. specific subscribers whose calls you also want to capture), replace the single-ID check in `process_chat()` with a set:

```python
ALLOWED_USER_IDS = {AUTHOR_USER_ID, <other_user_id>, ...}
# then:
if t.get("user_id") not in ALLOWED_USER_IDS:
    ...
```

### Finding the IDs

Both `PUBLICATION_ID` and `AUTHOR_USER_ID` are visible in the chat API response. The quickest way:

1. Open the publication's chat in your browser while logged in.
2. Press F12 → Network tab → filter `api` → refresh.
3. Find the request to `/api/v1/community/publications/<PUBLICATION_ID>/posts` — that gives you the publication ID.
4. Inspect the response JSON. Each `threads[i].communityPost.user` object has the author's `id` and `name`. Copy the IDs of whoever you want to analyze.

## Cost

| Component | Provider | Cost |
|---|---|---|
| Extraction (essays + chat) | Claude Sonnet 4.6 | ~$0.01 per pick analyzed |
| Price + headlines | Yahoo Finance via yfinance | free |
| Substack reads | Substack | free (you're a paid subscriber) |
| Discord posting | Discord | free |
| Scheduling | Windows Task Scheduler | free |

For a publication that posts a few picks per week, total ongoing cost is well under $1/month. Anthropic gives $5 free credit on signup, which lasts roughly a year and a half at typical usage.

## Personal-use note

This bot reads content via an authenticated subscriber session and posts to one private Discord channel. It is not a redistribution tool — output should never be reposted, made public, or shared with third parties. You should be a paid subscriber to any publication you point this at.

Automated access is generally against Substack's ToS even for paid content. Practical enforcement against personal-use readers is essentially nil, but if your account is your only access to the publication, keep the poll interval conservative (the default 30 min is fine; don't crank it below ~5 min).

## Extending

Reasonable next features:

- **Notes pipeline** — Substack's Twitter-like short-form posts (`substack.com/@<handle>/notes`)
- **Bull/bear TL;DR** — add ~150 output tokens to each extraction call; pennies/month
- **Independent research** — Claude + web-search tool for high-conviction picks (~$1.50/month)
- **Persistent watchlist** — Notion or Airtable mirror of Discord output
- **Reaction-based state** — emoji reactions on Discord to mark picks as bought / skipped / watching
- **Cloud-hosted runner** — small VPS or scheduled cloud function so it runs 24/7
