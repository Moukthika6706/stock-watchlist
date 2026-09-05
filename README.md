# StockSense

A stock watchlist that answers one question: **what changed since *you* last looked?**
Every trading app shows a 1-day or 1-week price feed; this one keeps a per-user baseline
of what each person saw on their previous visit and, on the next visit, ranks the
watchlist by how much deserves attention now. The ranking is a transparent three-rule
score, never a black box, and every sentence on the screen is templated from real fields.

Built for the Code by Groww campus challenge (72-hour build). React (JavaScript) frontend,
Flask backend, MySQL, JWT auth, Twelve Data for quotes.

---

## Run it

Verified from a clean state on Windows 11 with the versions below. The macOS/Linux
equivalents are the usual ones (`venv/bin/python`, `cp` instead of `copy`); they were not
exercised here.

**Prerequisites**

| Tool | Version used |
|---|---|
| Python | 3.12.2 |
| Node.js / npm | 22.13.1 / 11.4.2 |
| MySQL Server | 8.0 (8.0.39 server, 8.0.46 client) running on localhost:3306 |

**1. Backend environment**

```bat
cd backend
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
```

Edit `backend\.env`: set `DB_USER`, `DB_PASSWORD`, `DB_HOST` (`localhost`), and
`DB_NAME` (`stock_watchlist`) for a MySQL user that can create a database; set
`JWT_SECRET_KEY` to any long random string; set `DEMO_EMAIL`, `DEMO_PASSWORD`,
`DEMO_NAME` for the demo account you want created. `API_KEY` (Twelve Data) is only needed
for live polling and for adding a ticker the database has never seen; the demo needs
neither. Leave `DEMO_MODE=true`.

If MySQL rejects the connection with a message about the `cryptography` package, your
MySQL user authenticates with `caching_sha2_password` over an insecure channel; run
`venv\Scripts\python.exe -m pip install cryptography` and retry.

**2. Database: create, load schema, seed the demo**

```bat
venv\Scripts\python.exe reset_db.py --yes
venv\Scripts\python.exe seed_demo_data.py --arm
```

`reset_db.py` creates the database named in `.env` if it does not exist and runs
`schema.sql` (drop and create all six tables; the database itself is kept). `--arm`
creates the six supported stocks with their real Friday-close reference row, creates the
demo account with all six on its watchlist, writes about three hours of price history, and
records a "last visit" 25 minutes ago, so the first login already shows a populated digest.

Manual alternative for the schema, verified with the MySQL client:

```bat
mysql -u root -p -e "CREATE DATABASE stock_watchlist"
mysql -u root -p stock_watchlist < schema.sql
```

**3. Backend**

```bat
venv\Scripts\python.exe app.py
```

Serves `http://127.0.0.1:5000`. `GET /db-check` lists the tables if the DB connection works.

**4. Frontend** (second terminal, repo root)

```bat
cd frontend
copy .env.example .env
npm ci
npm start
```

Serves `http://localhost:3000`. Log in with the `DEMO_EMAIL` / `DEMO_PASSWORD` you put in
`backend\.env`. The demo runbook, including how to re-arm the digest after any refresh, is
in [DEMO.md](DEMO.md).

---

## Architecture

```
 Browser (React 19, CRA, port 3000)
   │  axios, JWT in Authorization header, CORS-scoped to the dev origin
   ▼
 Flask 3 (port 5000)  ── flask-jwt-extended (24h access tokens)
   │  SQLAlchemy 2 + PyMySQL
   ▼
 MySQL 8: users · stocks · watchlist · price_snapshots · last_seen · price_alerts
   ▲
   │  POST /poll-prices  (manual trigger; refused while DEMO_MODE=true)
 market_data.fetch_quote ──▶ Twelve Data /quote  (one call per distinct watched ticker)
   │
 seed_demo_data.py  (writes snapshots + the demo account's last_seen; never calls the API)
```

| Table | Holds |
|---|---|
| `users` | id, name, unique email, password hash (Werkzeug scrypt) |
| `stocks` | one row per ticker: symbol, company name, exchange, cached current price |
| `watchlist` | who watches what; `UNIQUE(user_id, stock_id)` |
| `price_snapshots` | **append-only, shared** price history: one row per poll per stock (price, day change %, volume, average volume, day and 52-week ranges, market-open flag, `captured_at`). Nothing is ever updated in place. |
| `last_seen` | **one mutable row per user per stock** (`UNIQUE(user_id, stock_id)`): the price, volume and time that user last saw. Upserted on every `GET /watchlist`. |
| `price_alerts` | passive ABOVE/BELOW thresholds. Reserved by the schema; no endpoint reads or writes it yet. |

That split is the core idea. Market data is a fact shared by everyone and accumulates;
"what you saw" is personal and is overwritten each visit. A diff is one row per user per
stock, however many users watch the same ticker.

---

## Design decisions

### a) What counts as a meaningful change

Every stock gets a 0-100 attention score from three rules ([backend/scoring.py](backend/scoring.py)):

```
score = min(40, 40 × |% change since this user's last visit|)     (percentage points)
      + 30  if today's volume  > 1.5 × its average volume
      + 30  if price is within 2% of the 52-week high or low
categories: 0-30 Stable · 31-60 Monitor · 61-80 Important · 81-100 Immediate attention
```

Why these weights: the price move since *your* last visit is the trigger and gets the
largest single weight, but it is capped at 40 on purpose, so a price move alone can never
climb past Monitor. The two 30-point context rules are deliberately equal to each other and
each smaller than the move; they cannot promote a stock past Monitor on their own either
(a lone flag scores exactly 30, which is still Stable). Reaching the top tier requires all
three to agree. The thresholds (1.5× volume, 2% band, 1% for full price points) are
judgment calls chosen for a six-ticker demo universe, not fitted to data; they are named
constants in one file, and the response carries every intermediate value so the UI can
show the working.

The exact boundaries, computed by calling the scoring function at the edges:

| Result | Exact condition |
|---|---|
| Stable (≤ 30) | a lone move up to 0.76%, or a lone volume spike, or a lone 52-week milestone |
| Monitor (31-60) | a lone move of 0.78% or more (caps at 40); one flag plus a move up to 0.75%; both flags with no move (60) |
| Important (61-80) | one flag plus a move of 0.78% or more (caps at 70); both flags plus a move under 0.52% |
| Immediate (81-100) | both flags plus a move of 0.52% or more; 1% or more gives 100 |

**The objection, answered up front.** Volume ratio and 52-week proximity are not diffs,
they are *state*. A stock can therefore hold a Monitor tier with a 0.0% move since your
last visit. This is deliberate. The panel answers "what deserves attention now", not only
"what changed". Change is the trigger and carries the heaviest single weight, but a 1% move
mid-range on normal volume is noise, while the same 1% move at a 52-week high on double
volume is signal. Volume and proximity are the context that decides whether a change
matters.

Worked example, straight from the seeded demo data (NVDA, real 52-week high 236.54):

| Visit | Price | Move since last visit | Volume | Distance to 52w high | Score |
|---|---|---|---|---|---|
| Armed login | 233.75 vs 231.20 last seen | +1.10% → 40 pts | 1.90× → +30 | 1.18% below → +30 | **100, Immediate** |
| Refresh straight after | 233.75 vs 233.75 | 0.00% → 0 pts | 1.90× → +30 | 1.18% below → +30 | **60, Monitor** |

After you have acknowledged the move, the price component is gone because you have seen
it; NVDA stays flagged because heavy volume at a 52-week high is still true whether or not
you looked. The digest sentence changes accordingly, from "is up 1.1% since your last
visit, on 1.9x normal volume and trading near its 52-week high" to "is flat since your last
visit, on 1.9x normal volume and trading near its 52-week high".

### b) What information to surface, and what not to

The screen leads with a digest: "N stocks need your attention", N rows sorted by score,
one templated sentence each, then the table sorted the same way. N is defined once (stocks
not classified Stable) and drives the headline, the summary line and the row list, so the
three can never disagree.

A per-user diff instead of a timeframe toggle is the differentiator. Every trading app
already shows 1D and 1W; none of them show "since you personally last looked". A 1W column
tells a user who checked an hour ago nothing new, and a 1D column hides a move from a user
who has been away a week. The baseline that matters is the user's own last visit, and only
the server knows it.

Surfaced per row: price, a 15-point sparkline, the change since last seen with the price
and time you last saw, the tier pill, the 52-week range with a marker, and a freshness
label. Clicking a row opens "Why X scores N / 100" with the three rule results and the
formula. Not surfaced: day change %, distance-to-range percentages, raw volumes. They are
in the API response for anyone who wants them, but on screen they would compete with the
one question the product is about.

### c) How state persists across sessions and devices

`last_seen` lives server-side, keyed by user and stock, not in `localStorage`. Log in from
another browser or machine and the baseline follows the account. The browser stores only
the JWT (24-hour lifetime); the watchlist and the baseline are always read from the server.

Inside `GET /watchlist` the ordering is: read the user's existing `last_seen` rows (joined
into the same query as the latest snapshot), compute and serialise the diff against them,
and only then upsert `last_seen` to the current values in one `INSERT ... ON DUPLICATE KEY
UPDATE` statement. Every call therefore consumes the diff, and a second refresh immediately
afterwards correctly shows 0.0% change on every row: the second visit is compared against
the first, not against the visit before it.

Because of that, the frontend calls `GET /watchlist` only when the user asks: on login, on
page load, and on the explicit Refresh button (guarded so it cannot double-fire). There is
no polling, no refetch on focus or tab visibility, and add/remove update local state from
their own responses rather than re-fetching, because any silent refetch would erase the
diff the user came to read.

The honest cost of a stateful diff: a brand-new user has nothing to compare against. Their
first load records the baseline and the digest says so ("Now tracking 6 stocks ... From
your next visit on, this space reports what changed since you last looked"); the feature
has something to say from the second visit onward. A timeframe toggle would work on the
first visit. We accepted one empty visit in exchange for a baseline that is actually
personal.

### d) Stale, delayed and conflicting data

- **Freshness is measured by the database clock, not the browser's.** `GET /watchlist`
  returns `age_seconds` for each stock's latest snapshot, computed in SQL as
  `TIMESTAMPDIFF(SECOND, captured_at, NOW())`, and the UI renders it as "updated just now",
  "12m ago", "3h ago". A client whose clock is wrong cannot make stale data look fresh.
- **Market open/closed comes from the data, not the calendar.** Twelve Data returns
  `is_market_open` with every quote; it is stored per snapshot and the header shows "Market
  closed" or "Market open" from the latest row. During a holiday weekend it says closed and
  looks intentional.
- **Snapshots are append-only.** The application never updates or deletes a snapshot: a
  late or corrected price adds a row, so what a user was shown earlier is never destroyed.
  "Latest" is defined as the highest snapshot id per stock, which is insertion order and,
  for poller-written rows, chronological. (The demo seed script is the one exception: it
  deletes and rewrites only the rows it wrote itself, tracked by id in a local state file.)
- **The poller degrades per ticker.** A failed quote (bad symbol, rate limit, network) is
  logged and recorded in the poll result; the other tickers still commit. Twelve Data
  errors surface with their own meaning (404 unknown symbol, 429 rate limit, 502 anything
  else) rather than as generic failures.
- **The universe is six US tickers** (`AAPL TSLA MSFT GOOGL AMZN NVDA`), whitelisted on
  `POST /watchlist`. NSE symbols were not available on the Twelve Data plan used for this
  build, and the whitelist also protects the free tier's rate limit during testing.

What is *not* handled: the exchange's own quote timestamp is not stored (only when we
polled), so a quote that Twelve Data itself served late is indistinguishable from a fresh
one. The schema has no column for it.

### e) Scale

Polling is per distinct ticker across all watchlists, never per user per stock: the poller
selects `DISTINCT` stocks that appear in any `watchlist` row. N users on the same 6 tickers
cost 6 API calls per poll, not 6N. Personalisation is entirely the `last_seen` row, which
costs one small upsert per visible row per visit.

Within a poll, calls are spaced one second apart and, after every 8 calls, the job waits
out the rest of that 60-second window, so it stays inside the free tier's 8-per-minute
limit however long the list grows. A non-blocking lock refuses a second concurrent poll.

`GET /watchlist` is two `SELECT`s and one upsert regardless of watchlist size: one query
joins watchlist → stocks → latest snapshot (correlated `MAX(id)`) → `last_seen`, and one
window-function query fetches the last 15 prices for all watched stocks at once. No per-row
queries.

The next bottleneck, and roughly where: the free tier's **800 credits per day**. With 6
tickers that allows about 133 polls a day; at 60 tickers it is 13, which is no longer
intraday. Past that point the answer is a paid plan or a different feed, not a code change.
Independently of the API, the sparkline query ranks every snapshot of the watched stocks
with `ROW_NUMBER()` before keeping 15 per stock, so its cost grows linearly with history
per stock; the fix is a bounded lateral query or a retention job. Neither limit was load
tested; the numbers above are arithmetic from the API quotas, not measurements.

---

## What was deliberately left out, and why

- **AI-generated news or explanations of price moves.** A language model inventing a
  reason for a move on a financial surface is a hallucination risk that no amount of demo
  polish justifies. Every sentence in the digest is templated from fields the API actually
  returned (move %, volume ratio, 52-week proximity), and the "why this score" panel is the
  three rule results, so nothing on screen can say something the data does not support.
- **Portfolio tracking** (holdings, quantities, P&L). This is a watchlist; users do not own
  anything here, and mixing "what I hold" into "what deserves my attention" would have
  blurred the one question the product answers.
- **Notification delivery** (push, email, SMS). The `price_alerts` table exists in the
  schema, but no endpoint or UI uses it yet, and nothing is sent anywhere. Delivery
  infrastructure is a project of its own; the in-app digest is the notification.
- **Multiple watchlists per user.** One list per account keeps the baseline model simple:
  one `last_seen` row per user per stock, no question of which list a visit "counts" for.
- **Timeframe toggles (1D / 1W / 1M).** They are what every other app shows, and they
  compete with the per-user baseline for the user's attention. The day change is still
  returned by the API; it is not given screen space.
- **A scheduled poller.** Polling is a manual `POST /poll-prices`. During the build window
  US markets were closed for a holiday weekend, so a scheduler would have written the same
  Friday close on a timer while making the seeded demo harder to control. With the free
  tier's daily cap, the cadence needs to be market-hours-aware anyway; that belongs with a
  real scheduler, not a `setInterval`.

---

## API reference

Base URL `http://127.0.0.1:5000`. All bodies and responses are JSON. Every error the API
returns on purpose (validation, auth, not found, provider failures, Flask's own 404/405/415)
has the shape `{"message": "..."}`, including those raised by the JWT layer. An unhandled
exception with `debug=True` still returns Flask's HTML debugger page. Protected routes take
`Authorization: Bearer <access_token>`. CORS allows `http://localhost:3000` and
`http://127.0.0.1:3000` (override with `FRONTEND_ORIGINS`), the `Content-Type` and
`Authorization` headers, and no credentials.

**Token failures, two codes.** flask-jwt-extended answers a *missing or expired* token with
`401`, but a *malformed or tampered* token (bad signature, wrong number of segments) with
`422 Unprocessable Entity`. The frontend treats both as "sign in again" for any request that
carried a token; a `401` from `/login` itself (wrong password) carries no token and is left
to the form.

| Method & path | Auth | Request | Success | Errors |
|---|---|---|---|---|
| `POST /signup` | no | `{name, email, password}` | `201 {"message": "User created"}` | `400` missing/empty field · `409` email already registered |
| `POST /login` | no | `{email, password}` | `200 {"access_token"}` (24 h) | `400` missing field · `401` invalid credentials |
| `GET /me` | JWT | – | `200 {user_id, name, email}` | `404` user no longer exists · `401`/`422` token |
| `GET /watchlist` | JWT | – | `200 {count, watchlist: [item]}` (see below). **Side effect:** upserts `last_seen` for every listed stock. | `401`/`422` token |
| `POST /watchlist` | JWT | `{symbol}` (case-insensitive) | `201 {message, item}` | `400` missing symbol or not one of `AAPL TSLA MSFT GOOGL AMZN NVDA` · `404` provider does not know the symbol · `409` already on the watchlist · `429` provider rate limit · `500` `API_KEY` not configured · `502` provider unreachable or malformed reply |
| `DELETE /watchlist/<stock_id>` | JWT | – | `200 {message, stock_id}` | `404` not on this user's watchlist · `401`/`422` token |
| `POST /poll-prices` | **none** (internal trigger) | – | `200 {status, polled, succeeded[], failed[], duration_seconds}`; `status` is `ok`, `partial`, `failed` or `nothing_to_poll` | `423` while `DEMO_MODE` is on · `409` a poll is already running |
| `GET /db-check` | no | – | `200 {connected: true, tables: [...]}` | – |

Notes: `POST /watchlist` only calls Twelve Data when the ticker has never been seen; it then
creates the `stocks` row and seeds its first snapshot. `DELETE` leaves the user's
`last_seen` row in place, so re-adding a stock compares against the last time it was seen.
User identity always comes from the JWT; a `user_id` in a request body is ignored.

**Watchlist item shape** (`GET /watchlist`, `POST /watchlist` → `item`):

```
{
  "watchlist_id", "stock_id", "symbol", "company_name", "market", "added_at",
  "last_seen": null | { "price", "volume", "at" },          // null on a first view
  "latest": null | {                                       // null only if a stock has no snapshot yet
    "price", "percent_change", "volume", "average_volume",
    "day_high", "day_low", "week52_high", "week52_low",
    "is_market_open", "captured_at", "age_seconds",
    "sparkline": [ up to 15 prices, oldest → newest ],
    "change_since_last_visit", "change_since_last_visit_pct",   // omitted entirely on a first view
    "volume_ratio", "volume_spike",
    "distance_to_52w_high_pct", "distance_to_52w_low_pct", "milestones": ["near_52w_high" | "near_52w_low"],
    "attention_score", "attention_category",                    // "Stable" | "Monitor" | "Important" | "Immediate attention"
    "score_breakdown": { "price_change_points", "volume_points", "milestone_points", "reasons": [ ... ] }
  }
}
```

`DEMO_MODE` (backend `.env`): while true, `POST /poll-prices` returns `423` with an
explanation, because a real poll would overwrite the seeded demo snapshots with the frozen
holiday-weekend close. **Unset counts as on** (fail-safe). Set `DEMO_MODE=false` and restart
to poll for real.

---

## Testing

What is covered:

- Frontend unit tests (Jest via react-scripts, `CI=true npx react-scripts test --watchAll=false`):
  2 suites, 12 tests. `Sparkline.test.js` (6) covers empty, undefined, one-point, two-point
  and non-numeric arrays and the direction of a rising series. `AttentionHero.test.js` (6)
  covers the shared-N rule between headline, summary and rows, score ordering, the badge
  labels coming from the single attention module, the N = 0 state, the first-visit copy,
  the empty state, and the "most recent last_seen" timestamp.
- Manual, scripted verification against the running stack (curl and browser): auth flows
  including missing/garbage/expired/tampered tokens, CORS preflight from allowed and foreign
  origins, watchlist add/remove/first-view/second-view, the poller's rate-limit pause and
  per-ticker failure handling (simulated outage), the `DEMO_MODE` refusal, and the seeded
  tier spread. The demo runbook was rehearsed twice from an empty database with identical
  results.

What is not covered: there are no automated backend tests (no pytest suite), no end-to-end
browser tests, no load or latency measurements, and no coverage figure is claimed.

---

## What we would build next

- **A real poller schedule that respects the quota.** Market-hours-aware cadence sized from
  `800 credits/day ÷ distinct tickers`, with backoff on 429. Hard part is not the timer; it
  is deciding what to do when the daily budget runs out mid-session.
- **Store the exchange's quote timestamp** alongside `captured_at`, so "delayed" and "stale"
  are distinguishable. Needs a schema column and a change to the freshness label semantics.
- **Bound the history read.** Replace the window-function sparkline query with a per-stock
  bounded lateral query and add a retention or roll-up job for `price_snapshots`, before
  history per stock reaches the point where the read cost is noticeable.
- **Use `price_alerts`.** Endpoints and an in-app flag when a threshold crosses; still no
  delivery. The interesting question is whether an alert should also bump the attention
  score, which would mix a user-set signal into the shared formula.
- **Per-user thresholds.** Let a user tune the 1.5× and 2% constants. The formula is already
  parameterised in one file; the cost is explaining a score that differs per user.
- **NSE coverage** once a paid feed is available; the code is provider-agnostic only at the
  `market_data.fetch_quote` boundary, so a second provider means a second client module.
