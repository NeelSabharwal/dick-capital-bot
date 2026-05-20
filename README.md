# Substack → Discord Pick Bot

A personal automation that watches the paid **Dick Capital** Substack and pushes
structured stock-pick alerts to a private Discord channel — running **entirely in
the cloud, for free, with no computer left on.**

> **Plain-English version:** see [START-HERE.md](START-HERE.md). This file is the
> technical reference.

## How it works (current, live setup)

The bot is **email-driven**. When Dick starts a new chat thread, Substack emails
the subscriber — and that email already contains the pick text. So instead of
scraping Substack, the bot reads the pick from the email:

```
Dick posts a chat thread
        │
        ▼
Substack sends an email  ──►  Gmail (nsabharwal2006@gmail.com)
        │                       sender: dickcapital@substack.com
        │                       subject: "💬 New thread from Dick Capital"
        ▼
Google Apps Script watcher  (gmail-watcher.gs, runs every 1 min)
        │   finds the new email, sends its text to GitHub
        ▼
GitHub repository_dispatch  (event_type: new-substack-email)
        │
        ▼
GitHub Actions  (.github/workflows/bot.yml)
        │   runs:  python bot.py --from-email
        ▼
bot.py  →  Claude extracts {ticker, action, sizing, thesis, …}
        →  yfinance adds price + recent news (free)
        →  posts a rich embed to Discord
```

End-to-end latency is about **1–2 minutes** after Dick posts. Everything runs on
Google's and GitHub's servers, so the user's laptop is never involved.

### Why email instead of scraping Substack directly?

Substack sits behind Cloudflare, which **returns `403 Forbidden` to requests from
datacenter IPs** (GitHub Actions, and every other free cloud host). A valid
subscriber cookie does not help — it's the server's IP that's blocked. The
notification email is the workaround: it reaches Gmail normally and contains the
pick, so the cloud bot never has to call Substack.

## The two modes of `bot.py`

`bot.py` has one entry point with two modes:

| Command | Mode | Where it runs | Status |
|---|---|---|---|
| `python bot.py --from-email` | Reads the pick from an email passed in via env vars (`EMAIL_BODY`, `EMAIL_CHAT_URL`, `EMAIL_DATE`). **No Substack call.** | GitHub Actions | ✅ **Live** |
| `python bot.py` | Scrapes Substack directly (`process_posts()` + `process_chat()`). | Anywhere with a residential IP | ⏸️ Legacy — works only from a home IP; the Windows task that ran it is **disabled** |

The scraping mode still works from a residential connection (it's how the bot ran
originally), but it is **not** used in the live cloud setup because of the 403
above. It's kept for reference and for the one thing the email path can't fully
cover — see "Known limitation" below.

## Project layout

```
.
├── bot.py                      pipeline: --from-email mode + legacy scrape mode
├── gmail-watcher.gs            Google Apps Script that watches Gmail and pokes GitHub
├── .github/workflows/bot.yml   GitHub Actions workflow (runs the bot on dispatch)
├── START-HERE.md               plain-English owner's guide
├── README.md                   this file
├── .env.example                template showing required vars (for local scrape mode)
├── .env                        local secrets (gitignored — never committed)
├── requirements.txt            Python deps
├── state.json                  seen essay-post IDs (legacy scrape mode)
└── chat_state.json             seen chat thread UUIDs (legacy scrape mode)
```

Key functions in `bot.py`:

- `process_email()` — live cloud mode; extracts a pick from the email body.
- `process_chat()` / `process_posts()` — legacy scrape mode.
- `extract_chat_picks()` / `extract_picks()` — Claude structured extraction.
- `enrichment_fields()` — adds price/news/research links to any embed.
- `post_chat_to_discord()` / `post_to_discord()` — build + send the Discord embed.
- `send_embed()` — single Discord REST call (clamps fields to Discord's limits).

## Secrets

In the **live cloud setup**, secrets live as **GitHub Actions secrets**
(Repo → Settings → Secrets and variables → Actions), set with `gh secret set -f .env`:

| Secret | Used by | Where to get it |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude extraction | console.anthropic.com → API Keys |
| `DISCORD_BOT_TOKEN` | posting to Discord | discord.com/developers → your app → Bot |
| `DISCORD_CHANNEL_ID` | target channel | Discord (Developer Mode) → right-click channel → Copy ID |
| `SUBSTACK_COOKIE` | legacy scrape mode only (optional) | DevTools → Cookies → `substack.sid` |

The Apps Script watcher needs one more secret of its own: a **GitHub access token**
(classic, `repo` scope) stored as the `GITHUB_TOKEN` Script Property — this is what
lets it fire the `repository_dispatch`.

Publication-specific constants live at the top of `bot.py`:

```python
PUBLICATION_ID  = 6321441    # Dick Capital publication ID
AUTHOR_USER_ID  = 394376039  # Dick's user ID (legacy chat filter)
```

## Setup

The friendly, step-by-step version is in [START-HERE.md](START-HERE.md). In short:

1. **GitHub:** push this repo, then `gh secret set -f .env` to load the secrets.
   The workflow (`.github/workflows/bot.yml`) triggers on `repository_dispatch`
   (type `new-substack-email`) and on manual run.
2. **Gmail watcher:** create a classic GitHub token (`repo` scope), then in
   script.google.com (signed in as the inbox that receives Dick's emails) paste
   `gmail-watcher.gs`, set the `GITHUB_TOKEN` Script Property, run `checkDickCapital`
   once to authorize, and add an **every-1-minute** time-driven trigger.

To test the GitHub side without the watcher, fire a dispatch yourself:

```bash
gh api repos/<owner>/<repo>/dispatches --method POST --input - <<'JSON'
{"event_type":"new-substack-email","client_payload":{"body":"Bought $AMKR 2% position","chat_url":"https://substack.com/chat/6321441","date":"2026-05-20T15:00:00Z"}}
JSON
```

## Cost

| Component | Provider | Cost |
|---|---|---|
| Pick extraction | Claude Sonnet 4.6 | ~1–3¢ per pick analyzed |
| Price + headlines + research links | Yahoo Finance / static URLs | free |
| Gmail watcher | Google Apps Script | free |
| Bot runner | GitHub Actions (public repo) | free |
| Discord posting | Discord | free |

**Only the Claude extraction costs anything**, and only when there's a real pick —
well under ~$1–2/month at Dick's posting volume. The price, news, and research
links on each card are all free.

## Known limitation: essays

The email path covers Dick's **chat trade updates** (the primary signal). His long
**essay posts** are only partially covered: their notification email contains a
preview, not the full essay, and the cloud can't scrape the full text (the 403).
The legacy scrape mode (`python bot.py` on a home IP) is the only thing that reads
essays in full. Re-enable it with `Enable-ScheduledTask DickCapitalBot` if you ever
want essay coverage back.

## The chat filter (legacy scrape mode)

The chat endpoint returns *every* top-level message. `process_chat()` keeps only
messages where `user_id == AUTHOR_USER_ID` (Dick); everyone else's messages are
marked seen but never analyzed or posted. To allowlist more authors, swap the
single-ID check for a set:

```python
ALLOWED_USER_IDS = {AUTHOR_USER_ID, <other_user_id>, ...}
if t.get("user_id") not in ALLOWED_USER_IDS:
    ...
```

`PUBLICATION_ID` and `AUTHOR_USER_ID` are both visible in the chat API response
(F12 → Network → the `/api/v1/community/publications/<id>/posts` request).

## Personal-use note

This bot reads paid content via the subscriber's own email/session and posts to one
private Discord channel. It is **not** a redistribution tool — output should never
be reposted, made public, or shared. Use it only for a publication you pay for.

## Extending

- **Essays in full** — re-enable the home-IP scrape mode, or a residential proxy.
- **Bull/bear TL;DR** — a few more output tokens per extraction; pennies/month.
- **Reaction-based state** — emoji reactions in Discord to mark bought/skipped/watching.
- **Notes pipeline** — Substack's short-form notes.
