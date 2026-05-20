# How your bot works now

## You don't have to start anything — ever.

Your bot **runs in the cloud**, not on your computer. There's nothing to turn on,
no app to open, no command to type. It works 24/7 whether your laptop is on, off,
asleep, or closed.

Here's the whole thing in one line:

> **Dick posts → you get the email → the bot reads it → it posts the pick to your
> Discord `#alerts`, about 1–2 minutes later.**

That's it. You can ignore it and it just works.

## What's doing the work (so you know)

Three free helpers, all running on their own:

1. **A Gmail watcher** (a tiny script on your `nsabharwal2006@gmail.com` account)
   checks every minute for a new email from Dick Capital.
2. When it sees one, it **wakes up the bot on GitHub** (a free service).
3. The bot **reads the pick from the email**, looks up the price and recent news,
   and **posts it to Discord.**

Your old laptop bot is **switched off** now — you don't need it, and leaving it on
would have caused duplicate alerts.

## How to check it's working

Easiest: **just look at your Discord `#alerts` channel.** If picks are showing up,
it's working.

If you ever want to look under the hood:

- **GitHub:** go to your repo → **Actions** tab. Each run is a line — a green ✓
  means it ran fine. (Repo: `github.com/NeelSabharwal/dick-capital-bot`)
- **Gmail watcher:** go to **script.google.com**, open the project, click the
  **clock icon** (Triggers) to confirm it's still scheduled, or **Executions** to
  see its recent runs.

## What it costs

Almost nothing. The Gmail watcher, the GitHub runner, the price/news, and the
research links are all **free**. The only paid part is the tiny **Claude** step
that reads each pick (~1–3¢ per pick) — well under **$1–2 a month**.

## Good to know

- **It covers Dick's chat trade updates** (the "Bought $AMKR," "Adding ENPH" posts)
  — your main signal. His occasional long essay write-ups aren't fully covered;
  ask Claude to help if you ever want those too.
- **Want it changed?** (different alerts, formatting, filters, etc.) Just open this
  project in Cursor and tell Claude what you want.
- **If alerts ever stop:** check that the email still arrives in
  `nsabharwal2006@gmail.com`, then check the GitHub **Actions** tab for a red ✗.
  Or just ask Claude to take a look.

---

*Set it and forget it. Turn your computer off and the picks still come in.*
