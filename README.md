# StockSense — See what changed. Know what matters.

<p align="center">
  <img src="logo.png" width="700">
</p>

> *"Every investor deserves to know what changed and why — because for Groww, better decisions start with better insights."*

---
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
Clamped 0–100 → **Stable** (0–30) / **Monitor** (31–60) / **Important** (61–80) / **Immediate attention** (81–100)

Every input is a value already shown elsewhere in the UI — the score is a synthesis of visible data, not a hidden calculation.

## Ticker scope

Six tickers: `AAPL`, `TSLA`, `MSFT`, `GOOGL`, `AMZN`, `NVDA`.

We initially planned to use NSE (Indian exchange) tickers for authenticity with Groww's own market, but testing revealed NSE data sits behind Twelve Data's paid tier. We pivoted to US tickers on the free tier rather than lose build time — the data layer is exchange-agnostic, so adding NSE support later is a config change, not a redesign.

## A note on the demo data

Our entire 72-hour build window overlapped US Labor Day weekend, when US markets are closed — meaning every *real* price poll returns the same frozen Friday-close numbers throughout. Since the core feature is showing *change*, we built a separate, clearly-labeled script (`seed_demo_data.py`) that simulates realistic intraday movement within each stock's real day-range bounds, purely so the "since you last checked" story is demoable. It never touches the real polling logic, and it's documented here rather than hidden — this reflects a real constraint we identified and designed around, not an attempt to fake results.

## What we deliberately didn't build

Scope discipline was itself a design decision, not a shortcut:

- **Portfolio tracking** (holdings, quantities, P&L) — this is a watchlist, not a portfolio; users track stocks, they don't own them here
- **Real alert delivery** (push/email/SMS) — thresholds are stored and shown as an in-app flag only; building delivery infrastructure wasn't worth the risk under time pressure
- **AI-generated explanations for price moves** — real risk of confidently-worded but wrong reasoning in a fintech context; a templated summary from real fields is safer and just as useful
- **Multiple watchlists per user** — the problem statement's minimum bar is a single watchlist
- **1D / 1W / timeframe toggles** — we deliberately replaced generic time-window toggles with something more meaningful: comparison against *this specific user's* last visit, which most watchlists don't do

## Setup

**Backend:**
```bash
cd backend
python -m venv venv
source venv/Scripts/activate   # Windows Git Bash
pip install -r requirements.txt
# create .env with DB_USER, DB_PASSWORD, DB_HOST, DB_NAME, API_KEY
python app.py
```

**Frontend:**
```bash
cd frontend
npm install
npm start
```

**Seed demo data (optional, for a live demo):**
```bash
cd backend
python seed_demo_data.py            # fresh seed
python seed_demo_data.py --advance  # simulate a new price step, to show a live diff
```

## API summary

| Endpoint | Method | Auth | Purpose |
|---|---|---|---|
| `/signup` | POST | — | Create account |
| `/login` | POST | — | Get a JWT |
| `/me` | GET | JWT | Confirm identity |
| `/watchlist` | GET | JWT | List watched stocks with diff + attention score |
| `/watchlist` | POST | JWT | Add a stock (whitelisted tickers only) |
| `/watchlist/<stock_id>` | DELETE | JWT | Remove a stock |
| `/poll-prices` | POST | — (internal) | Refresh live prices from Twelve Data |

## Why this design

Every decision above has a reason we can state and defend out loud — which is the actual point of a 72-hour, no-DSA, "architecture is yours to decide" challenge.
