"""Dick Capital Substack -> Discord bot (Phase 1: posts).

Polls Substack for new paid posts, extracts actionable stock picks with
Claude, and posts them to a Discord channel.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

import re
import httpx
import yfinance as yf
from anthropic import Anthropic
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

LOG_FILE = Path(__file__).parent / "bot.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("dickcap")

SUBSTACK_COOKIE = os.environ["SUBSTACK_COOKIE"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
DISCORD_BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
DISCORD_CHANNEL_ID = os.environ["DISCORD_CHANNEL_ID"]
PUBLICATION_HOST = os.environ.get("SUBSTACK_PUBLICATION_HOST", "dickcapital.substack.com")
PUBLICATION_ID = 6321441    # Substack publication ID — change to target a different publication
AUTHOR_USER_ID = 394376039  # User ID of the author whose chat messages we want — found via the chat API response

STATE_FILE = Path(__file__).parent / "state.json"
CHAT_STATE_FILE = Path(__file__).parent / "chat_state.json"
# Look like a normal browser. Substack is behind Cloudflare, which 403s
# obvious bot User-Agents coming from datacenter IPs (e.g. GitHub Actions).
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
BROWSER_HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://substack.com/",
}

claude = Anthropic(api_key=ANTHROPIC_API_KEY)


def load_seen() -> set[int]:
    if not STATE_FILE.exists():
        return set()
    return set(json.loads(STATE_FILE.read_text())["seen_post_ids"])


def save_seen(seen: set[int]) -> None:
    STATE_FILE.write_text(json.dumps({"seen_post_ids": sorted(seen)}, indent=2))


def fetch_recent_posts(limit: int = 10) -> list[dict[str, Any]]:
    url = f"https://{PUBLICATION_HOST}/api/v1/posts?limit={limit}"
    r = httpx.get(
        url,
        headers={**BROWSER_HEADERS, "Cookie": SUBSTACK_COOKIE},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def html_to_text(html: str) -> str:
    return BeautifulSoup(html, "html.parser").get_text(separator="\n").strip()


EXTRACTION_PROMPT = """You are analyzing a post from the "Dick Capital" investing newsletter to extract actionable stock recommendations.

Post title: {title}
Post date: {date}
Post URL: {url}

Post content:
---
{body}
---

Return a JSON object with this exact structure:
{{
  "is_actionable": true | false,
  "summary": "one or two sentence summary of the post's main point",
  "picks": [
    {{
      "ticker": "AMZN",
      "action": "buy" | "sell" | "add" | "trim" | "hold" | "watch",
      "sizing": "any sizing info mentioned (e.g. '.5% position', '5% of portfolio') or null",
      "thesis": "1-3 sentence summary of why he's recommending this",
      "conviction": "high" | "medium" | "low",
      "quote": "a direct quote from the post that justifies this extraction",
      "time_horizon": "short-term | swing | medium-term | long-term | null (if not stated)",
      "entry_price": "any entry / cost-basis price mentioned, like '$34.21' or 'on a pullback to $30', or null",
      "stop_loss": "any stop loss / max-pain price mentioned, or null",
      "target_price": "any price target or upside target mentioned, or null",
      "constraints": "any other rules he gives — e.g. 'only on dips', 'scale in', 'avoid above $X', 'wait for earnings', or null"
    }}
  ]
}}

Set is_actionable=true only if the post recommends specific buy/sell/add/trim actions on specific tickers. Macro essays, market color, and general commentary should be is_actionable=false with picks=[].

For each field, extract ONLY what is explicitly stated in the post. If the post doesn't mention something, use null. Do not invent or infer values.

Return ONLY the JSON object, no other text, no code fences."""


def extract_picks(post: dict[str, Any]) -> dict[str, Any]:
    body_text = html_to_text(post["body_html"])
    if len(body_text) > 30000:
        body_text = body_text[:30000] + "\n...[truncated]"
    prompt = EXTRACTION_PROMPT.format(
        title=post["title"],
        date=post["post_date"],
        url=post["canonical_url"],
        body=body_text,
    )
    msg = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return json.loads(raw)


ACTION_COLORS = {
    "buy": 0x2ecc71, "add": 0x2ecc71,
    "sell": 0xe74c3c, "trim": 0xe74c3c,
    "hold": 0xf1c40f, "watch": 0x3498db,
}
ACTION_EMOJI = {
    "buy": "🟢", "add": "🟢",
    "sell": "🔴", "trim": "🔴",
    "hold": "🟡", "watch": "👀",
}
CONVICTION_DOTS = {"high": "●●●", "medium": "●●○", "low": "●○○"}


# ============================================================================
# ENRICHMENT (price + news + research links) — all free, no API keys
# ============================================================================

def get_ticker_info(ticker: str) -> dict[str, Any]:
    """Fetch price + recent news from Yahoo Finance. Returns {} on any failure."""
    try:
        t = yf.Ticker(ticker)
        fi = t.fast_info
        price = getattr(fi, "last_price", None)
        prev_close = getattr(fi, "previous_close", None)
        change_pct = ((price - prev_close) / prev_close * 100) if (price and prev_close) else None

        headlines = []
        try:
            for n in (t.news or [])[:3]:
                # yfinance returns either {title, link} (old) or {content: {title, canonicalUrl.url}} (new)
                content = n.get("content") or {}
                title = content.get("title") or n.get("title")
                url = (
                    (content.get("canonicalUrl") or {}).get("url")
                    or (content.get("clickThroughUrl") or {}).get("url")
                    or n.get("link")
                )
                if title and url:
                    headlines.append({"title": title, "url": url})
        except Exception:
            pass

        return {"price": price, "change_pct": change_pct, "headlines": headlines}
    except Exception as e:
        log.warning(f"yfinance lookup failed for {ticker}: {e}")
        return {}


def research_links(ticker: str) -> str:
    """One-line row of clickable research links."""
    return (
        f"[Yahoo](https://finance.yahoo.com/quote/{ticker}) • "
        f"[TradingView](https://www.tradingview.com/symbols/{ticker}/) • "
        f"[MarketWatch](https://www.marketwatch.com/investing/stock/{ticker}) • "
        f"[Seeking Alpha](https://seekingalpha.com/symbol/{ticker}) • "
        f"[Google News](https://www.google.com/search?q={ticker}+stock+news&tbm=nws)"
    )


def _parse_price_number(s: str | None) -> float | None:
    if not s:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    return float(m.group(1)) if m else None


def enrichment_fields(ticker: str, entry_price: str | None = None) -> list[dict[str, Any]]:
    """Build the price/news/research field block for an embed."""
    info = get_ticker_info(ticker)
    fields: list[dict[str, Any]] = []

    price = info.get("price")
    if price:
        change = info.get("change_pct")
        if change is not None:
            arrow = "🟢" if change >= 0 else "🔴"
            value = f"${price:.2f}  {arrow} {change:+.2f}%"
        else:
            value = f"${price:.2f}"
        fields.append({"name": "Price now", "value": value, "inline": True})

        entry_num = _parse_price_number(entry_price)
        if entry_num:
            diff_pct = (price - entry_num) / entry_num * 100
            arrow = "🟢" if diff_pct >= 0 else "🔴"
            fields.append({
                "name": "vs. Entry",
                "value": f"{arrow} {diff_pct:+.2f}% (entry ${entry_num:.2f})",
                "inline": True,
            })

    if info.get("headlines"):
        lines = []
        for h in info["headlines"]:
            title = h["title"]
            if len(title) > 90:
                title = title[:87] + "..."
            lines.append(f"• [{title}]({h['url']})")
        fields.append({"name": "Recent news", "value": "\n".join(lines), "inline": False})

    fields.append({"name": "Research", "value": research_links(ticker), "inline": False})
    return fields


def send_embed(embed: dict[str, Any]) -> None:
    # Clamp to Discord's hard limits so one long field can't make Discord reject
    # the whole alert (title 256, description 4096, field name 256, field value 1024).
    if embed.get("title"):
        embed["title"] = embed["title"][:256]
    if embed.get("description"):
        embed["description"] = embed["description"][:4096]
    for f in embed.get("fields", []):
        f["name"] = f["name"][:256]
        v = f.get("value") or "—"
        f["value"] = v if len(v) <= 1024 else v[:1023] + "…"

    url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages"
    r = httpx.post(
        url,
        headers={
            "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
            "Content-Type": "application/json",
        },
        json={"embeds": [embed]},
        timeout=30,
    )
    r.raise_for_status()


def post_to_discord(post: dict[str, Any], analysis: dict[str, Any]) -> None:
    title = post["title"]
    url = post["canonical_url"]
    post_ts = post["post_date"]  # ISO 8601, Discord renders as local time

    if not analysis.get("picks"):
        send_embed({
            "title": f"📄 {title}",
            "url": url,
            "description": analysis.get("summary", "(no summary)"),
            "color": 0x95a5a6,
            "timestamp": post_ts,
            "footer": {"text": "Dick Capital • No actionable picks"},
        })
        return

    for pick in analysis["picks"]:
        action = pick.get("action", "watch")
        fields = [
            {"name": "Sizing", "value": pick.get("sizing") or "—", "inline": True},
            {"name": "Conviction", "value": CONVICTION_DOTS.get(pick.get("conviction", ""), pick.get("conviction", "—")), "inline": True},
            {"name": "Time Horizon", "value": pick.get("time_horizon") or "—", "inline": True},
        ]
        if any(pick.get(k) for k in ("entry_price", "stop_loss", "target_price")):
            fields.extend([
                {"name": "Entry", "value": pick.get("entry_price") or "—", "inline": True},
                {"name": "Stop Loss", "value": pick.get("stop_loss") or "—", "inline": True},
                {"name": "Target", "value": pick.get("target_price") or "—", "inline": True},
            ])
        fields.extend(enrichment_fields(pick["ticker"], pick.get("entry_price")))
        if pick.get("constraints"):
            fields.append({"name": "Constraints", "value": pick["constraints"], "inline": False})
        fields.append({"name": "From", "value": f"[{title}]({url})", "inline": False})
        quote = " ".join((pick.get("quote") or "").split())  # collapse stray line breaks
        if quote:
            fields.append({"name": "Quote", "value": f"> {quote[:500]}", "inline": False})
        send_embed({
            "title": f"{ACTION_EMOJI.get(action, '📌')} {action.upper()} ${pick['ticker']}",
            "url": url,
            "description": pick.get("thesis", ""),
            "color": ACTION_COLORS.get(action, 0xf1c40f),
            "timestamp": post_ts,
            "fields": fields,
            "footer": {"text": "Dick Capital"},
        })


# ============================================================================
# CHAT (Phase 2)
# ============================================================================

def load_chat_seen() -> set[str]:
    if not CHAT_STATE_FILE.exists():
        return set()
    return set(json.loads(CHAT_STATE_FILE.read_text())["seen_chat_post_ids"])


def save_chat_seen(seen: set[str]) -> None:
    CHAT_STATE_FILE.write_text(json.dumps({"seen_chat_post_ids": sorted(seen)}, indent=2))


def fetch_chat_threads(limit: int = 20) -> list[dict[str, Any]]:
    url = f"https://substack.com/api/v1/community/publications/{PUBLICATION_ID}/posts"
    r = httpx.get(
        url,
        headers={**BROWSER_HEADERS, "Cookie": SUBSTACK_COOKIE},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    threads = [t.get("communityPost") for t in data.get("threads", []) if t.get("communityPost")]
    return threads[:limit]


CHAT_EXTRACTION_PROMPT = """You are analyzing a chat message from "Dick Capital" (a paid investing newsletter) to extract actionable stock recommendations.

Chat messages are SHORT and terse. Common patterns:
- "Trade Update: Adding .5% more ENPH, Adding .25% more TRT"  -> two picks (add ENPH, add TRT)
- "$IPWR .5% add"  -> one minimal pick
- "$SEDG .5% position in tandem with $ENPH, will increase position sizing as we go along"  -> one pick with note
- "SUBSCRIBER CHAT: WEEK OF MAY 18 - MAY 24" -> NOT actionable, just a discussion thread starter
- General market commentary, replies to subscribers, or housekeeping -> NOT actionable

Message body:
---
{body}
---

Posted: {date}

Return a JSON object with this exact structure:
{{
  "is_actionable": true | false,
  "picks": [
    {{
      "ticker": "TICKER",
      "action": "buy" | "sell" | "add" | "trim" | "hold" | "watch",
      "sizing": "any sizing info (e.g. '.5%', '0.25%') or null",
      "thesis": "any reasoning given, or null if message just says action + ticker",
      "entry_price": "any entry price mentioned, or null",
      "stop_loss": "any stop loss mentioned, or null",
      "target_price": "any target price mentioned, or null",
      "time_horizon": "short-term | swing | medium-term | long-term | null",
      "constraints": "any other rules (e.g. 'scale in', 'on dips'), or null"
    }}
  ]
}}

Extract ONLY what is explicitly stated. Do not invent or infer values. If the message is not a trade action, return is_actionable=false and picks=[].

Return ONLY the JSON object, no other text, no code fences."""


def extract_chat_picks(post: dict[str, Any]) -> dict[str, Any]:
    body = post.get("body", "") or ""
    prompt = CHAT_EXTRACTION_PROMPT.format(body=body, date=post["created_at"])
    msg = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return json.loads(raw)


def post_chat_to_discord(post: dict[str, Any], analysis: dict[str, Any]) -> None:
    if not analysis.get("picks"):
        return  # skip silent — chat is noisy, only post actual picks
    chat_url = f"https://substack.com/chat/{PUBLICATION_ID}/post/{post['id']}"
    ts = post["created_at"]

    for pick in analysis["picks"]:
        action = pick.get("action", "watch")
        fields = [
            {"name": "Sizing", "value": pick.get("sizing") or "—", "inline": True},
            {"name": "Time Horizon", "value": pick.get("time_horizon") or "—", "inline": True},
            {"name": "Source", "value": f"[💬 Open in chat]({chat_url})", "inline": True},
        ]
        if any(pick.get(k) for k in ("entry_price", "stop_loss", "target_price")):
            fields.extend([
                {"name": "Entry", "value": pick.get("entry_price") or "—", "inline": True},
                {"name": "Stop Loss", "value": pick.get("stop_loss") or "—", "inline": True},
                {"name": "Target", "value": pick.get("target_price") or "—", "inline": True},
            ])
        fields.extend(enrichment_fields(pick["ticker"], pick.get("entry_price")))
        if pick.get("constraints"):
            fields.append({"name": "Constraints", "value": pick["constraints"], "inline": False})

        # Thesis (Claude's summary of Dick's message) becomes the headline line;
        # the raw message text is no longer dumped — the chat link above covers it.
        send_embed({
            "title": f"{ACTION_EMOJI.get(action, '📌')} {action.upper()} ${pick['ticker']}",
            "url": chat_url,
            "description": pick.get("thesis") or "_via subscriber chat_",
            "color": ACTION_COLORS.get(action, 0xf1c40f),
            "timestamp": ts,
            "fields": fields,
            "footer": {"text": "Dick Capital • Chat"},
        })


def process_chat() -> None:
    is_first_run = not CHAT_STATE_FILE.exists()
    seen = load_chat_seen()
    threads = fetch_chat_threads(limit=20)
    threads.sort(key=lambda p: p["created_at"])  # oldest -> newest

    if is_first_run:
        log.info(f"First chat run: marking {len(threads)} existing chat threads as seen (no demo to avoid noise).")
        for t in threads:
            seen.add(t["id"])
        save_chat_seen(seen)
        return

    new = [t for t in threads if t["id"] not in seen]
    if not new:
        log.info(f"No new chat messages. {len(seen)} previously seen.")
        save_chat_seen(seen)
        return

    log.info(f"Processing {len(new)} new chat message(s)...")
    for t in new:
        author = (t.get("user") or {}).get("name", "?")
        body_preview = (t.get("body") or "")[:80]
        log.info(f"  -> chat from {author}: {body_preview!r}")
        if t.get("user_id") != AUTHOR_USER_ID:
            log.info("     (not from Dick — marking seen, skipping analysis)")
            seen.add(t["id"])
            save_chat_seen(seen)
            continue
        try:
            analysis = extract_chat_picks(t)
            post_chat_to_discord(t, analysis)
            seen.add(t["id"])
            save_chat_seen(seen)
        except Exception as e:
            log.exception(f"ERROR on chat {t['id']}: {e}")


# ============================================================================
# MAIN
# ============================================================================

def process_posts() -> None:
    is_first_run = not STATE_FILE.exists()
    seen = load_seen()
    posts = fetch_recent_posts(limit=10)
    posts.sort(key=lambda p: p["post_date"])

    if is_first_run:
        log.info("First posts run: processing most recent post as a demo, marking rest as seen.")
        for p in posts[:-1]:
            seen.add(p["id"])
        new_posts = posts[-1:] if posts else []
    else:
        new_posts = [p for p in posts if p["id"] not in seen]

    if not new_posts:
        log.info(f"No new posts. {len(seen)} previously seen.")
        save_seen(seen)
        return

    log.info(f"Processing {len(new_posts)} post(s)...")
    for post in new_posts:
        log.info(f"  -> {post['title']}")
        try:
            analysis = extract_picks(post)
            post_to_discord(post, analysis)
            seen.add(post["id"])
            save_seen(seen)
        except Exception as e:
            log.exception(f"ERROR on '{post['title']}': {e}")


def main() -> int:
    log.info("=== bot run start ===")
    try:
        process_posts()
    except Exception as e:
        log.exception(f"posts pipeline failed: {e}")
    try:
        process_chat()
    except Exception as e:
        log.exception(f"chat pipeline failed: {e}")
    log.info("=== bot run end ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
