# StockSense — See what changed. Know what matters.

A stock watchlist that doesn't just show prices — it tells you what actually changed since you last looked, and how much it matters.

Built for **Code by Groww (CODE 2026)**.

## The idea

Most watchlists answer "what is the price right now." This one answers a different question: **"what changed since I last checked, and does it deserve my attention?"**

Every stock gets a personalized comparison against this specific user's last visit, and a transparent **Attention Score (0–100)** that explains, in plain terms, why it scored the way it did — no black box.

## Features

- **Personal "since you last checked" digest** — a plain-English summary of what moved, sorted by how much it matters, built fresh for each user
- **Attention Score with a visible breakdown** — every score shows exactly which factors contributed and why (price move, volume spike, 52-week milestone)
- **Real price history** — sparklines and 52-week range indicators built from actual stored snapshots, not placeholders
- **Cross-device persistence** — your watchlist and viewing history are tied to your account, not your browser
- **Stale-data awareness** — every price shows how fresh it is, and the app knows when the market is actually open

## Tech stack

| Layer | Choice |
|---|---|
| Frontend | React (JavaScript) |
| Backend | Flask (Python) |
| Database | MySQL |
| Auth | JWT (24-hour tokens) |
| Market data | [Twelve Data](https://twelvedata.com) API |

**Why this stack:** built in what we already knew well, under a 72-hour deadline — fast, reliable iteration mattered more than using unfamiliar tools to look impressive.

## Architecture

**Database — 6 tables:**
- `users` — accounts
- `stocks` — static ticker metadata + a cached latest price
- `watchlist` — who's watching what (join table)
- `price_snapshots` — **shared market history.** One row per stock per poll. Powers sparklines, volume-spike detection, and milestone checks.
- `last_seen` — **personal memory.** One row per user per stock, updated on every view. This is what makes the diff personal instead of global.
- `price_alerts` — passive user-defined price thresholds (schema only, not yet wired to a route)

**Scaling design:** prices are polled once per unique ticker across *all* users, not once per user's watchlist — 500 users watching the same stock costs one API call, not 500. Personalization lives entirely in `last_seen`, decoupled from the shared price data.

**The Attention Score:**
