# How to start the bot (when you turn your computer on)

## The short version: you don't have to do anything.

The bot starts itself. As long as your computer is **on** and you're **logged in**,
it automatically checks Dick Capital every 30 minutes and posts any new picks to
your Discord. You do **not** need to open Cursor, click a button, or run a command
for this to happen.

So the real "startup steps" are just:

1. Turn on your computer.
2. Log in like you normally do.
3. That's it. Within 30 minutes the bot runs on its own.

## The only thing that stops it

The bot can't run while your computer is **off or asleep**. The moment you turn it
back on, it picks up again automatically. And it remembers everything it has
already posted, so:

- You won't get duplicate alerts.
- It won't skip the picks it missed while the computer was off — it catches them
  on the next run.

---

## Optional: make it check RIGHT NOW (instead of waiting up to 30 min)

If you just turned your computer on after it was off for a while and you want it to
catch up immediately:

1. Open this project in Cursor.
2. In the top menu, click **Terminal** → **New Terminal**. A box opens at the bottom.
3. Click inside that box, type this line exactly, and press Enter:

   ```
   .\.venv\Scripts\python.exe bot.py
   ```

4. Wait about 15 seconds. When you get your normal prompt back, it's finished.
   Any new picks will now be in your Discord.

## Optional: check that it's actually working

Two easy ways, pick either:

- **Look at Discord** — if there were new picks, they'll be in your `#alerts` channel.
- **Look at the log** — open the file `bot.log` in this folder and scroll to the very
  bottom. If the newest lines say `=== bot run start ===` and `=== bot run end ===`
  with today's date, it ran fine.

---

*That's the whole thing. Turn the computer on, log in, and the bot takes care of
the rest.*
