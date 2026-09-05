# StockSense demo runbook

The demo credentials are **not** in this file. They live in `backend/.env`
(`DEMO_EMAIL`, `DEMO_PASSWORD`, `DEMO_NAME`) and, on the demo machine, in the untracked
`DEMO_CREDENTIALS.md` next to this file. Everything else needed to reach the state where
the main feature does something is here.

The whole demo hinges on one fact: **every `GET /watchlist` consumes the "since you last
checked" diff.** Logging in, loading the page and clicking Refresh all call it. The ARM
command below puts the demo account back into the pre-reveal state in about two seconds.
Run it right before you walk on, and again after any stray refresh.

Two hard rules while `DEMO_MODE=true` (it is, in `backend/.env`; unset also counts as on):

- Never click Refresh before the reveal. If it happens, re-run ARM (section b).
- `POST /poll-prices` is refused with 423. Leave it that way until after judging.

---

## a) One-time setup from a clean database

Prerequisites: MySQL 8 running on localhost:3306, Python 3.12, Node 22, and `backend/.env`
filled in from `backend/.env.example` (it must contain the `DB_*` values, `DEMO_MODE=true`,
`DEMO_EMAIL`, `DEMO_PASSWORD`, `DEMO_NAME`). `frontend/.env` is a copy of
`frontend/.env.example`.

Terminal 1 (backend), from the repo root:

```bat
cd backend
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe reset_db.py --yes
venv\Scripts\python.exe seed_demo_data.py --arm
venv\Scripts\python.exe app.py
```

- `reset_db.py --yes` creates the database if needed and drops and recreates all six tables.
- `seed_demo_data.py --arm` creates the six stocks with their real Friday-close reference
  row, creates the demo account with all six tickers on its watchlist, writes about three
  hours of price history ending 25 minutes ago, records that as the account's last visit,
  and inserts the "now" move for every ticker. It prints the expected tier table (below).
- `app.py` serves the API on http://127.0.0.1:5000. Leave it running.

Terminal 2 (frontend), from the repo root:

```bat
cd frontend
npm ci
npm start
```

Serves http://localhost:3000. Leave it running. Open that URL in Chrome. If the page shows
someone else's watchlist, click the avatar (top right) and Sign out.

Expected table printed by `--arm` (every run, every time):

| Ticker | Last seen | Now    | Move    | Vol x | Score | Category  |
|--------|-----------|--------|---------|-------|-------|-----------|
| NVDA   | 231.20    | 233.75 | +1.10%  | 1.90  | 100   | Immediate attention |
| TSLA   | 360.40    | 354.30 | −1.69%  | 1.80  | 70    | Important |
| AMZN   | 256.90    | 260.50 | +1.40%  | 1.10  | 40    | Monitor   |
| MSFT   | 503.10    | 507.65 | +0.90%  | 0.90  | 36    | Monitor   |
| AAPL   | 322.40    | 323.35 | +0.29%  | 1.20  | 12    | Stable    |
| GOOGL  | 341.10    | 340.40 | −0.21%  | 0.80  | 8     | Stable    |

If the command prints `REFUSING TO ARM`, the story no longer matches scoring.py or the
day ranges changed; read the lines it prints and do not demo until it arms.

---

## b) ARM: put the demo account back into the pre-reveal state

From the repo root, any time, about two seconds:

```bat
cd backend
venv\Scripts\python.exe seed_demo_data.py --arm
```

Safe to run repeatedly. It removes the rows it wrote last time and rewrites them, so the
history stays the same length, the "last visit" moves to 25 minutes before now, and the
"updated just now" labels are fresh. It never touches other users. It never calls the
market-data API.

After ARM, the very next `GET /watchlist` for the demo account shows the diff. That next
call is your reveal: either the login (section c, step 1) or a click on Refresh.

Armed looks like: headline "4 stocks need your attention" with four badge rows.
Disarmed looks like: headline "1 stock needs your attention" with a single MONITOR row
for NVDA reading "NVDA is flat since your last visit, on 1.9x normal volume and trading
near its 52-week high.", and every table row at 0.0%. NVDA never drops to Stable while
armed data is loaded, because its volume spike and 52-week proximity (30 + 30 = 60) do not
depend on when you last looked; only the price-move component does.

---

## c) Demo click sequence

Start armed (run section b within the last few minutes) and logged out.

1. **Log in** with the demo credentials, click **Continue**.
   Expect, immediately, no warm-up clicks:
   - Green digest: **"4 stocks need your attention"**, "Last visit today, H:MM PM. 4 of 6
     stocks moved enough to mention." (H:MM is 25 minutes before you ran ARM.)
   - Four rows, in this order:
     `IMMEDIATE  NVDA is up 1.1% since your last visit, on 1.9x normal volume and trading near its 52-week high.`
     `IMPORTANT  TSLA is down 1.7% since your last visit, on 1.8x normal volume.`
     `MONITOR    AMZN is up 1.4% since your last visit.`
     `MONITOR    MSFT is up 0.9% since your last visit.`
   - Table sorted NVDA, TSLA, AMZN, MSFT, AAPL, GOOGL; the two Stable rows show +0.3% and
     −0.2%; every row says "updated just now"; top right says **Market closed** (correct,
     it is a US holiday weekend; the data is real Friday-close data plus a seeded move).
   Talking point: "This is what you see when you come back. Not a quote screen: what changed
   since *you* last looked, ranked."

2. **Click the NVDA row.** A panel opens: "Why NVDA scores 100 / 100" with three plain
   reasons (price move +40, volume 1.90x +30, within 2% of 52-week high +30) and the
   formula. Talking point: "No black box. Every score is three rules you can read."
   Click the row again to close it.

3. **Click Refresh.** The digest collapses to **"1 stock needs your attention"** with one
   MONITOR row: "NVDA is flat since your last visit, on 1.9x normal volume and trading near
   its 52-week high." Every table row becomes 0.0% with "last seen $… · just now"; NVDA's
   pill drops from Immediate to Monitor, the other three to Stable. Talking point: "You just
   acknowledged it. The price moves are gone because you have seen them; NVDA stays flagged
   because heavy volume at a 52-week high is still true whether or not you looked." This is
   the product's core idea, so show it deliberately, not by accident.

4. **Re-arm live (optional, strong):** open a third terminal (leave the backend and frontend
   terminals running), `cd backend`, then `venv\Scripts\python.exe seed_demo_data.py --arm`.
   Back in the browser click **Refresh**. The four rows return. Talking point: "That was the
   market moving while you were away." (The seed script stands in for the poller; the poller
   is `POST /poll-prices`, disabled during the demo because US markets are closed.)

5. **Add / remove:** click **Remove** on GOOGL: the count drops to 5 of 5 and the digest
   recomputes without a network reload. Click **+ Add stock**: the picker lists only the
   six supported tickers with the five already-added ones disabled; add GOOGL back.

6. **Sign out** (avatar, top right) if you want to show login persistence: log back in and
   the list is exactly where you left it, because the watchlist and the last-seen baseline
   live server-side, not in the browser.

Do not open with a fresh signup: a new account needs two loads before the digest can show
anything (first load records the baseline). If asked, show signup last.

---

## d) Recovery

| Symptom | Fix |
|---|---|
| Someone clicked Refresh (or reloaded) before the reveal; digest shows only the NVDA Monitor row and 0.0% everywhere | Run ARM (section b), then click Refresh. Ten seconds. |
| Browser still logged in after a database reset | Harmless: the demo account is recreated with the same id, so the old session keeps working. Sign out and back in if you want the clean login moment. |
| Backend restarted or crashed | Nothing is lost; state is in MySQL. Restart it: `cd backend` then `venv\Scripts\python.exe app.py`. If the page shows "We couldn't load your watchlist", click **Try again**. If the last ARM was before the restart it is still armed. |
| Port 5000 already in use | Kill the old python: `taskkill /F /IM python.exe` (this kills every python.exe; then restart the backend). |
| Frontend blank or "Cannot reach the API" | Backend is down (row above). If the frontend itself died: Terminal 2, `npm start`. |
| DB in an unknown state, or someone polled with DEMO_MODE off | Run section a again from `reset_db.py --yes`. The demo account is recreated with the same credentials. About ten seconds. Then log in. |
| Logged in as the wrong user | Avatar, Sign out, log in as the demo account. |
| Login form does not react to Enter | Click **Continue**. |
| Someone asks to see live polling | Explain DEMO_MODE (it returns 423 with the reason). To actually poll: set `DEMO_MODE=false` in `backend/.env`, restart the backend, `curl -X POST http://127.0.0.1:5000/poll-prices`. Markets are closed all weekend, so it writes Friday's close again and **disarms the story**; run ARM afterwards. |

Reproducibility: the tiers are fixed by the STORY table in `backend/seed_demo_data.py`,
not by randomness. The history sparkline uses `--seed 2026` (the default). Running section
a twice from a clean database yields the same six categories every time.

---

## e) Demo account

Credentials are in `backend/.env` (`DEMO_EMAIL`, `DEMO_PASSWORD`, `DEMO_NAME`) and, on the
demo machine, in the untracked `DEMO_CREDENTIALS.md`. If you change them in `.env`, run ARM
again; it creates the account if it is missing.
