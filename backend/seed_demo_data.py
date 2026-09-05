"""Seed and ARM the demo. Standalone; never calls Twelve Data.

Why this exists: the submission window (Sat 5 Sep - Mon 7 Sep 2026, US Labor Day)
falls while US markets are closed, so live quotes never change and the
"since you last checked" digest could never show anything. This script writes a
deterministic story into price_snapshots and sets the demo account's last_seen
so that the next GET /watchlist shows a real, tiered diff.

Usage (from backend/, venv interpreter):
    venv\\Scripts\\python.exe seed_demo_data.py --arm       (also the default)
        1. deletes the rows written by previous runs (tracked in seed_demo_state.json)
        2. makes sure the six stocks exist, inserting the real Friday-close
           reference snapshot for any stock that has none (i.e. after reset_db.py)
        3. writes ~3 hours of plausible history per ticker, ending 25 minutes ago
           at the STORY "base" price
        4. creates the demo account (DEMO_EMAIL / DEMO_PASSWORD / DEMO_NAME from .env)
           if missing, puts all six tickers on its watchlist, and sets its
           last_seen to the base prices
        5. inserts the STORY "target" row for every ticker, stamped now
        => the demo account is ARMED: its next GET /watchlist shows the diff.
    venv\\Scripts\\python.exe seed_demo_data.py --dry-run   print the plan, write nothing
    venv\\Scripts\\python.exe seed_demo_data.py --advance   append one random step per
        ticker stamped now (ad-hoc only; the arm is what the demo uses)
Options: --seed N (history walk RNG; default 2026 and documented in DEMO.md).

Reproducibility: the tier outcome depends only on STORY (absolute prices and
volume multiples), not on the RNG. The RNG only shapes the sparkline history.
The script recomputes every tier with scoring.compute_attention before
writing and refuses to arm if the result differs from EXPECTED.

What is and is not fabricated:
    fabricated : prices, volumes and captured_at of the history/target rows,
                 percent_change (kept coherent with the implied previous close)
    real       : day range, 52-week range, average volume, company names
                 (REFERENCE = Twelve Data's Friday 2026-09-04 close, captured 2026-09-05)
    every fabricated price stays inside that ticker's real day range, and
    is_market_open is written as false because the market really is closed.
"""
import argparse
import json
import os
import random
import sys
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pymysql
import pymysql.cursors
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

from scoring import compute_attention

HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env")

DEMO_SYMBOLS = ("AAPL", "TSLA", "MSFT", "GOOGL", "AMZN", "NVDA")  # keep in sync with ALLOWED_SYMBOLS in app.py
STATE_FILE = HERE / "seed_demo_state.json"
DEFAULT_SEED = 2026

STEPS_PER_TICKER = (3, 4)          # history rows per ticker
STEP_PCT_RANGE = (0.5, 3.0)        # size of each history move, in percent
MAX_DRIFT_PCT = 5.0                # pull the history walk back beyond this distance from its start
SPAN_HOURS = 3.0                   # history is spread over roughly the last N hours ...
HISTORY_ENDS_MINUTES_AGO = 25      # ... ending here, at the STORY base price = the demo user's last visit
NORMAL_VOLUME_RANGE = (0.75, 1.25)

# Real Friday 2026-09-04 close for each ticker, exactly as Twelve Data returned it.
# Used as the first snapshot when a stock has none (clean database).
REFERENCE = {
    "AAPL": dict(company_name="Apple Inc.", market="NASDAQ", price="319.97", percent_change="-2.5106",
                 volume=39551800, average_volume=37060060, day_high="328.93", day_low="317.86",
                 week52_high="344.57", week52_low="225.95"),
    "TSLA": dict(company_name="Tesla, Inc.", market="NASDAQ", price="354.08", percent_change="-5.9224",
                 volume=64829000, average_volume=42099670, day_high="364.69", day_low="351.32",
                 week52_high="498.83", week52_low="297.38"),
    "MSFT": dict(company_name="Microsoft Corporation Common Stock", market="NASDAQ", price="499.70",
                 percent_change="-2.0427", volume=18074400, average_volume=22119700, day_high="511.00",
                 day_low="499.36", week52_high="553.72", week52_low="349.20"),
    "GOOGL": dict(company_name="Alphabet Inc. Class A Common Stock", market="NASDAQ", price="338.46",
                  percent_change="-1.1738", volume=23157700, average_volume=23945000, day_high="343.53",
                  day_low="337.09", week52_high="408.61", week52_low="226.11"),
    "AMZN": dict(company_name="Amazon.com Inc.", market="NASDAQ", price="258.51", percent_change="-0.1506",
                 volume=30698000, average_volume=32001660, day_high="261.12", day_low="255.29",
                 week52_high="287.20", week52_low="196.00"),
    "NVDA": dict(company_name="NVIDIA Corporation", market="NASDAQ", price="230.36", percent_change="0.8361",
                 volume=134946800, average_volume=159261450, day_high="234.76", day_low="229.63",
                 week52_high="236.54", week52_low="164.07"),
}

# The demo story. base = price at the demo user's last visit, target = price now.
# All prices sit inside the real day range above. Tier arithmetic (scoring.py):
#   price points = min(40, 40 * |% move|); +30 if volume > 1.5x average; +30 if
#   within 2% of the 52-week high/low; 0-30 Stable, 31-60 Monitor, 61-80
#   Important, 81-100 Immediate. NVDA is the only ticker whose real day range
#   reaches its 52-week band (98% of 236.54 = 231.81 <= day high 234.76).
STORY = {
    #  symbol   base       target     vol x   move     points                      -> tier
    "NVDA": ("231.20", "233.75", 1.9),   # +1.10%  40 + 30 spike + 30 near-high = 100 Immediate
    "TSLA": ("360.40", "354.30", 1.8),   # -1.69%  40 + 30 spike               =  70 Important
    "AMZN": ("256.90", "260.50", 1.1),   # +1.40%  40                          =  40 Monitor
    "MSFT": ("503.10", "507.65", 0.9),   # +0.90%  36                          =  36 Monitor
    "AAPL": ("322.40", "323.35", 1.2),   # +0.29%  12                          =  12 Stable
    "GOOGL": ("341.10", "340.40", 0.8),  # -0.21%   8                          =   8 Stable
}
EXPECTED = {
    "NVDA": "Immediate attention",
    "TSLA": "Important",
    "AMZN": "Monitor",
    "MSFT": "Monitor",
    "AAPL": "Stable",
    "GOOGL": "Stable",
}

INSERT_SNAPSHOT = """
    INSERT INTO price_snapshots
        (stock_id, price, percent_change, volume, average_volume, day_high, day_low,
         week52_high, week52_low, is_market_open, captured_at)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def money(value):
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def pct4(value):
    return Decimal(str(value)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def connect():
    return pymysql.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        cursorclass=pymysql.cursors.DictCursor,
    )


def load_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except FileNotFoundError:
        return {"seeded_snapshot_ids": []}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))


# --------------------------------------------------------------------------- data access
def ensure_stocks(cur, now):
    """Make sure every demo ticker exists with at least one (real) snapshot. Returns {symbol: stock_id}."""
    ids = {}
    for symbol in DEMO_SYMBOLS:
        ref = REFERENCE[symbol]
        cur.execute("SELECT id FROM stocks WHERE symbol = %s", (symbol,))
        row = cur.fetchone()
        if row is None:
            cur.execute(
                "INSERT INTO stocks (symbol, company_name, current_price, market) VALUES (%s, %s, %s, %s)",
                (symbol, ref["company_name"], ref["price"], ref["market"]),
            )
            stock_id = cur.lastrowid
        else:
            stock_id = row["id"]
        ids[symbol] = stock_id
        cur.execute("SELECT COUNT(*) AS n FROM price_snapshots WHERE stock_id = %s", (stock_id,))
        if cur.fetchone()["n"] == 0:
            cur.execute(INSERT_SNAPSHOT, (
                stock_id, ref["price"], ref["percent_change"], ref["volume"], ref["average_volume"],
                ref["day_high"], ref["day_low"], ref["week52_high"], ref["week52_low"], 0,
                now - timedelta(hours=SPAN_HOURS, minutes=15),
            ))
    return ids


def latest_snapshots(cur, symbols):
    placeholders = ",".join(["%s"] * len(symbols))
    cur.execute(
        f"""
        SELECT s.id AS stock_id, s.symbol, p.*
        FROM stocks s
        JOIN price_snapshots p ON p.id = (SELECT MAX(id) FROM price_snapshots WHERE stock_id = s.id)
        WHERE s.symbol IN ({placeholders})
        """,
        symbols,
    )
    return {row["symbol"]: row for row in cur.fetchall()}


def ensure_demo_user(cur):
    email = (os.getenv("DEMO_EMAIL") or "").strip().lower()
    password = os.getenv("DEMO_PASSWORD") or ""
    name = (os.getenv("DEMO_NAME") or "Demo Investor").strip()
    if not email or not password:
        sys.exit("DEMO_EMAIL and DEMO_PASSWORD must be set in backend/.env (see .env.example).")
    cur.execute("SELECT id FROM users WHERE email = %s", (email,))
    row = cur.fetchone()
    if row:
        return row["id"], email, False
    cur.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (%s, %s, %s)",
        (name, email, generate_password_hash(password)),
    )
    return cur.lastrowid, email, True


def ensure_watchlist(cur, user_id, stock_ids):
    for stock_id in stock_ids:
        cur.execute("INSERT IGNORE INTO watchlist (user_id, stock_id) VALUES (%s, %s)", (user_id, stock_id))


def set_last_seen(cur, user_id, stock_id, price, volume, at):
    cur.execute(
        """
        INSERT INTO last_seen (user_id, stock_id, last_seen_price, last_seen_volume, last_seen_at)
        VALUES (%s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE last_seen_price = VALUES(last_seen_price),
                                last_seen_volume = VALUES(last_seen_volume),
                                last_seen_at = VALUES(last_seen_at)
        """,
        (user_id, stock_id, price, volume, at),
    )


# --------------------------------------------------------------------------- history walk
def next_price(rng, price, start, day_low, day_high):
    """One history step of 0.5-3%, pulled back toward the start beyond MAX_DRIFT_PCT and
    kept strictly inside the real day range (partial move toward the edge, no clamping)."""
    magnitude = rng.uniform(*STEP_PCT_RANGE) / 100
    drift_pct = (price - start) / start * 100
    direction = (-1 if drift_pct > 0 else 1) if abs(drift_pct) > MAX_DRIFT_PCT else rng.choice((-1, 1))
    candidate = price * (1 + direction * magnitude)
    if day_low is not None and day_high is not None and day_high > day_low:
        margin = (day_high - day_low) * 0.02
        low_bound, high_bound = day_low + margin, day_high - margin
        if not low_bound <= candidate <= high_bound:
            room = (high_bound - price) if direction > 0 else (price - low_bound)
            if room <= 0:
                direction = -direction
                room = (high_bound - price) if direction > 0 else (price - low_bound)
            candidate = price + direction * max(room, 0) * rng.uniform(0.3, 0.9)
    return float(money(candidate))


def spread_timestamps(rng, steps, start_at, end_at):
    """`steps` strictly increasing timestamps from start_at to exactly end_at, with jitter."""
    total = (end_at - start_at).total_seconds()
    if steps == 1 or total <= 0:
        return [end_at] * steps
    slot = total / steps
    stamps = []
    for i in range(steps - 1):
        nominal = slot * (i + 1)
        jitter = rng.uniform(-0.3, 0.3) * slot
        floor = (stamps[-1] - start_at).total_seconds() + 60 if stamps else 0
        stamps.append(start_at + timedelta(seconds=int(min(max(nominal + jitter, floor), total - 60))))
    stamps.append(end_at)
    return stamps


def snapshot_row(base, price, volume, captured_at, implied_previous_close):
    return {
        "stock_id": base["stock_id"],
        "price": money(price),
        "percent_change": pct4((float(price) / implied_previous_close - 1) * 100),
        "volume": int(volume),
        "average_volume": base["average_volume"],
        "day_high": base["day_high"],
        "day_low": base["day_low"],
        "week52_high": base["week52_high"],
        "week52_low": base["week52_low"],
        "is_market_open": 0,
        "captured_at": captured_at,
    }


def build_history(rng, base, end_price, start_at, end_at):
    """Random walk from the latest real row, forced to finish at end_price at end_at."""
    steps = rng.choice(STEPS_PER_TICKER)
    start = float(base["price"])
    day_low = float(base["day_low"]) if base["day_low"] is not None else None
    day_high = float(base["day_high"]) if base["day_high"] is not None else None
    average_volume = base["average_volume"] or base["volume"] or 0
    base_pct = float(base["percent_change"]) if base["percent_change"] is not None else 0.0
    implied_previous_close = start / (1 + base_pct / 100)

    rows = []
    price = start
    for index, captured_at in enumerate(spread_timestamps(rng, steps, start_at, end_at)):
        price = float(end_price) if index == steps - 1 else next_price(rng, price, start, day_low, day_high)
        volume = average_volume * rng.uniform(*NORMAL_VOLUME_RANGE)
        rows.append(snapshot_row(base, price, volume, captured_at, implied_previous_close))
    return rows, implied_previous_close


def in_day_range(base, price):
    return float(base["day_low"]) <= float(price) <= float(base["day_high"])


# --------------------------------------------------------------------------- modes
def arm(args, rng):
    state = load_state()
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT NOW() AS now")
    now = cur.fetchone()["now"]

    previous_ids = state.get("seeded_snapshot_ids", [])
    deleted = 0
    if previous_ids:
        cur.execute(f"DELETE FROM price_snapshots WHERE id IN ({','.join(['%s'] * len(previous_ids))})", previous_ids)
        deleted = cur.rowcount

    stock_ids = ensure_stocks(cur, now)
    bases = latest_snapshots(cur, DEMO_SYMBOLS)
    user_id, email, created = ensure_demo_user(cur)
    ensure_watchlist(cur, user_id, stock_ids.values())

    start_at = now - timedelta(hours=SPAN_HOURS)
    last_visit_at = now - timedelta(minutes=HISTORY_ENDS_MINUTES_AGO)

    inserted_ids, summary, mismatches = [], [], []
    for symbol in DEMO_SYMBOLS:
        base = bases[symbol]
        base_price, target_price, volume_x = STORY[symbol]
        for label, price in (("base", base_price), ("target", target_price)):
            if not in_day_range(base, price):
                mismatches.append(f"{symbol}: {label} price {price} is outside today's real day range "
                                  f"{base['day_low']}-{base['day_high']}; edit STORY")

        history, implied_prev_close = build_history(rng, base, base_price, start_at, last_visit_at)
        last_visit_row = history[-1]
        target_volume = int((base["average_volume"] or base["volume"]) * volume_x)
        target = snapshot_row(base, target_price, target_volume, now, implied_prev_close)

        verdict = compute_attention(
            price=target["price"], volume=target["volume"], average_volume=target["average_volume"],
            week52_high=target["week52_high"], week52_low=target["week52_low"], last_seen_price=last_visit_row["price"],
        )
        if verdict["attention_category"] != EXPECTED[symbol]:
            mismatches.append(f"{symbol}: computed {verdict['attention_score']} {verdict['attention_category']}, "
                              f"expected {EXPECTED[symbol]}")

        if not args.dry_run:
            for row in history + [target]:
                cur.execute(INSERT_SNAPSHOT, (
                    row["stock_id"], row["price"], row["percent_change"], row["volume"], row["average_volume"],
                    row["day_high"], row["day_low"], row["week52_high"], row["week52_low"],
                    row["is_market_open"], row["captured_at"],
                ))
                inserted_ids.append(cur.lastrowid)
            set_last_seen(cur, user_id, base["stock_id"], last_visit_row["price"], last_visit_row["volume"], last_visit_at)

        summary.append({
            "symbol": symbol,
            "base": float(last_visit_row["price"]),
            "target": float(target["price"]),
            "move": verdict.get("change_since_last_visit_pct"),
            "vol_x": verdict["volume_ratio"],
            "to_high": verdict["distance_to_52w_high_pct"],
            "milestones": ",".join(verdict["milestones"]) or "-",
            "score": verdict["attention_score"],
            "category": verdict["attention_category"],
            "rows": len(history) + 1,
        })

    if mismatches:
        conn.rollback()
        conn.close()
        print("REFUSING TO ARM - the story no longer produces the documented tiers:")
        for line in mismatches:
            print("  -", line)
        return 1

    if args.dry_run:
        conn.rollback()
    else:
        conn.commit()
        save_state({"seeded_snapshot_ids": inserted_ids, "last_run": now.isoformat(sep=" "), "mode": "arm",
                    "seed": args.seed})
    conn.close()

    mode = "DRY RUN (nothing written)" if args.dry_run else "ARMED"
    print(f"\n{mode} at {now:%Y-%m-%d %H:%M:%S} (database clock)")
    print(f"  demo account: {email} ({'created' if created else 'already existed'}), all {len(DEMO_SYMBOLS)} tickers on its watchlist")
    print(f"  last visit recorded at {last_visit_at:%H:%M}; deleted {deleted} row(s) from the previous run; "
          f"history spans {start_at:%H:%M}-{last_visit_at:%H:%M}, targets stamped {now:%H:%M}\n")
    header = (f"{'Ticker':6} {'Last seen':>9} {'Now':>9} {'Move':>7} {'Vol x':>5} {'To 52wH':>8} "
              f"{'Milestone':<13} {'Score':>5} Category")
    print(header)
    print("-" * len(header))
    for s in sorted(summary, key=lambda r: -r["score"]):
        print(f"{s['symbol']:6} {s['base']:>9.2f} {s['target']:>9.2f} {s['move']:>+6.2f}% {s['vol_x']:>5.2f} "
              f"{s['to_high']:>7.2f}% {s['milestones']:<13} {s['score']:>5} {s['category']}")
    significant = sum(1 for s in summary if s["category"] != "Stable")
    print(f"\n  Digest on the next load: \"{significant} stocks need your attention\", "
          f"{significant} of {len(summary)} moved enough to mention.")
    print("  Every GET /watchlist consumes this. Re-run --arm before the reveal if anyone refreshes early.")
    return 0


def advance(args, rng):
    """Ad-hoc: one random step per ticker stamped now. Does not touch last_seen."""
    state = load_state()
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT NOW() AS now")
    now = cur.fetchone()["now"]
    bases = latest_snapshots(cur, DEMO_SYMBOLS)
    inserted = []
    for symbol in DEMO_SYMBOLS:
        base = bases.get(symbol)
        if not base:
            print(f"  skipped {symbol}: no snapshot yet (run --arm first)")
            continue
        start = float(base["price"])
        price = next_price(rng, start, start, float(base["day_low"]), float(base["day_high"]))
        base_pct = float(base["percent_change"] or 0)
        row = snapshot_row(base, price, (base["average_volume"] or base["volume"]) * rng.uniform(*NORMAL_VOLUME_RANGE),
                           now, start / (1 + base_pct / 100))
        print(f"  {symbol}: {start:.2f} -> {price:.2f} ({(price / start - 1) * 100:+.2f}%)")
        if not args.dry_run:
            cur.execute(INSERT_SNAPSHOT, (
                row["stock_id"], row["price"], row["percent_change"], row["volume"], row["average_volume"],
                row["day_high"], row["day_low"], row["week52_high"], row["week52_low"], 0, row["captured_at"],
            ))
            inserted.append(cur.lastrowid)
    if args.dry_run:
        conn.rollback()
    else:
        conn.commit()
        state["seeded_snapshot_ids"] = state.get("seeded_snapshot_ids", []) + inserted
        save_state(state)
    conn.close()
    return 0


def main():
    parser = argparse.ArgumentParser(description="Seed and arm the StockSense demo (see module docstring).")
    parser.add_argument("--arm", action="store_true", help="rebuild history, set the demo account's last_seen, insert the reveal rows (default)")
    parser.add_argument("--advance", action="store_true", help="append one random step per ticker stamped now")
    parser.add_argument("--dry-run", action="store_true", help="print the plan and write nothing")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help=f"RNG seed for the history walk (default {DEFAULT_SEED})")
    args = parser.parse_args()
    rng = random.Random(args.seed)
    if args.advance:
        return advance(args, rng)
    return arm(args, rng)


if __name__ == "__main__":
    sys.exit(main())
