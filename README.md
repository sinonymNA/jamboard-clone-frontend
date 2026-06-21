# Brand Engine

Brand Engine watches TikTok Shop and Meta Ad Library for products that are
already proven winners, finds a demographic angle the current sellers are
ignoring, checks whether the math works (margins, supplier cost), and
builds you a complete launch package. You approve or kill at a few defined
checkpoints; everything else runs on its own.

## What Brand Engine Does

Two surveillance feeds run in parallel, every morning and evening:

- **TikTok Shop** — younger audience, impulse buys, visual products.
- **Meta Ad Library** — older audience, considered purchases, ads that
  have been running a long time because they work.

A product appearing in **both** feeds at once is a Priority 1 find. A
product in only one feed is Priority 2. Everything else is ignored.

For every qualifying find, Brand Engine:

1. Looks up a supplier and calculates real margins. If the margins don't
   work, the product is dropped — no exceptions, regardless of how good
   everything else looks.
2. Identifies a demographic the current sellers aren't serving (the
   "blind spot") and writes four research docs about that audience.
3. Scores the opportunity 0-100 across demand, timing, margins, audience
   clarity, and content potential.
4. If the score clears the bar, sends you a Discord approval request.

When you approve, it generates all the store copy, pricing, and a
step-by-step setup checklist. When the store goes live, it generates
TikTok scripts, ad concepts, and a creator brief. It tracks performance
data you enter daily and tells you when to cut, hold, or scale.

**Important — read before running this against real accounts:** the
surveillance and supplier-lookup steps drive a real Chrome browser to
read public pages on TikTok Shop, Meta Ad Library, CJDropshipping, and
AliExpress. This is the same approach commercial ad-spy / product-research
tools use, but automated browsing of any site is subject to that site's
terms of service — review them for your situation before leaving this
running unattended. Meta Ad Library in particular also exposes an official
public API designed for ad transparency research; if you hit friction with
the browser-based approach, consider that as an alternative data source.

## Prerequisites

- Windows desktop, left on and logged in (the agent drives the actual
  screen via mouse/keyboard, so nothing else can use the machine while a
  task runs).
- Python 3.11 or newer.
- Google Chrome installed.
- An Anthropic API key — [platform.anthropic.com](https://platform.anthropic.com).
- A Discord server you control, with a webhook URL for the channel you
  want notifications in.
- A Shopify account (for the store-building step — you build the store,
  Brand Engine prepares everything to paste in).

## Setup (3 Steps)

1. Clone this repo.
2. Run `setup.bat`. It installs dependencies and creates your `.env` file.
3. Open `.env` and fill in `ANTHROPIC_API_KEY` and `DISCORD_WEBHOOK_URL`.

Then run `run.bat`. Leave the window open — closing it stops the system.

### Discord Reply Reading (optional but recommended)

A plain Discord webhook can *send* messages but cannot *read* your
replies. To let Brand Engine parse "APPROVE", "SKIP", "STATUS" etc.
automatically, create a Discord bot:

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications),
   create a New Application, then add a Bot user to it.
2. Under Bot settings, enable the "Message Content Intent".
3. Copy the bot token into `.env` as `DISCORD_BOT_TOKEN`.
4. Invite the bot to your server with "Read Message History" and "View
   Channel" permissions.
5. Right-click your notifications channel → Copy Channel ID (enable
   Developer Mode in Discord settings if you don't see this option), and
   put it in `.env` as `DISCORD_CHANNEL_ID`.

Without this, Brand Engine still sends every notification — you'll just
need to act on store building / content briefs manually rather than by
replying in Discord.

## Daily Operations

**Every morning at 07:00** you get a Daily Brief: active store
performance, anything that needs your input, and what's in the pipeline.

**When a new product is found**, you get an approval request with the
score, the blind spot angle, and the margins. Reply:
- `APPROVE` — builds the full store package.
- `SKIP` — drops it.
- `REPORT <product>` — full detail on what was found.

**Daily performance entry** (prompted at 08:00): reply with
`StoreName $spend/$revenue` for each active store, or `SKIP` to carry
yesterday's numbers forward.

**Manual product ideas**: drop them in `data/queue.txt` as a scratchpad.
Brand Engine doesn't auto-ingest this file yet — it's there so you don't
lose an idea you spot outside the automated sweeps.

## Your Daily Time Commitment

- Morning brief review: 5 minutes
- Approval decisions: 2 minutes per product
- Performance data entry: 2 minutes
- Store setup when needed: 30 minutes
- Ad setup when needed: 10 minutes

Most days, under 15 minutes total.

## Understanding Your Reports

Everything lives under `data/`:

- `data/brand_engine.db` — the full history: every product, score, and
  performance entry.
- `data/reports/<product-slug>/foundational_docs/` — deep research,
  avatar, offer, and necessary-beliefs docs for that product's audience.
- `data/reports/<product-slug>/store_assets/` — generated store copy.
- `data/reports/<product-slug>/content_briefs/` — TikTok scripts, ad
  concepts, captions, and the UGC creator brief.
- `data/autopsies/<product-slug>.json` — why a killed product failed.
- `data/scoring_weights.json` — how the scoring dimensions are currently
  weighted (adjusts automatically as outcomes accumulate).

## Known Limitations (by design)

- **Facebook 2FA**: Brand Engine cannot log into Ads Manager itself. It
  prepares a complete ad brief and you paste the settings in — about 10
  minutes.
- **Video footage**: Brand Engine cannot film anything. It writes a
  complete brief for a Billo/Fiverr creator instead (24-48hr turnaround).
- **Store building**: Brand Engine cannot create the Shopify store. It
  generates every piece of copy and a step-by-step checklist — about 30
  minutes to execute.
- **Ads Manager data**: Brand Engine cannot read your spend/revenue
  automatically (2FA again). You enter it once a day via Discord — under
  2 minutes.
- **Site structure changes**: if TikTok Shop's layout changes, the system
  falls back to the Creator Marketplace bestseller view and alerts you if
  even that fails.

## Troubleshooting

- **Nothing happens at the scheduled time** — check `brand_engine.log` in
  the repo root. Every job logs its start/failure there.
- **"CAPTCHA detected" alert** — the system skips that source for the run
  and tries the fallback (if one exists). No action needed unless it
  recurs every day.
- **"2FA wall" alert** — log into the relevant site manually in Chrome,
  then re-run; the session is cached afterward.
- **Discord replies aren't being picked up** — confirm
  `DISCORD_BOT_TOKEN` and `DISCORD_CHANNEL_ID` are set and the bot has
  channel access (see setup above).
- **Database looks wrong / want a clean slate** — stop the app and delete
  `data/brand_engine.db`; it's recreated automatically on next start.

## The Improvement Loop

Every time a product reaches a final outcome (profitable, killed, paused),
that result feeds back into the system:

- **At 5 products**: scoring weights get their first adjustment based on
  which of the five scoring dimensions actually predicted success.
- **At 10 products**: autopsy patterns start showing up — recurring
  reasons products fail get surfaced as Discord alerts ("products with X
  characteristic have failed 3 of 3 times").
- **At 20 products**: the performance-context summary prepended to every
  new blind-spot and scoring prompt becomes meaningfully specific to your
  results rather than generic.
- **At 50 products**: scoring weights and filters should reflect a fairly
  mature picture of what works for your specific store portfolio.

None of this requires you to do anything — it happens automatically as
outcomes accumulate in the database.
