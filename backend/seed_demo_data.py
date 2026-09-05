"""Seed realistic-looking intraday movement for the demo. Standalone; never calls Twelve Data.

Why this exists: the whole submission window (Sat 5 Sep - Mon 7 Sep 2026, US Labor
Day) falls while US markets are closed, so /poll-prices keeps returning Friday's
close and nothing ever "changes since your last visit". This script fabricates a
short random walk per whitelisted ticker so the diff, volume-spike and attention
score logic have something to show. It is deliberately separate from the real
polling code in app.py and only touches price_snapshots and last_seen.

Usage (from backend/, with the venv interpreter):
    venv\\Scripts\\python.exe seed_demo_data.py            full reseed: delete rows from previous runs,
                                                           insert 3-4 fresh steps per ticker, reset test users
    venv\\Scripts\\python.exe seed_demo_data.py --advance  append ONE more step per ticker, stamped now.
                                                           Run it between two refreshes to make a diff appear live.
    venv\\Scripts\\python.exe seed_demo_data.py --dry-run  print the plan, write nothing
Options:
    --seed N          reproducible walk (a full reseed defaults to 2026; --advance is random)
    --spike AAPL,NVDA which tickers get a volume spike on their last step(s) (default: 2 picked by the RNG)

Re-runnable: the id of every row this script inserts is recorded in
seed_demo_state.json. A full reseed deletes those rows first, so the newest
poller-written snapshot is always the baseline the walk starts from.

What is and is not fabricated:
    fabricated : price, percent_change (kept coherent with the implied previous close), volume, captured_at
    real       : day_high, day_low, week52_high, week52_low, average_volume (copied from the baseline row);
                 prices are kept inside the real day range so the row never contradicts itself
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

from scoring import compute_attention

HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env")

DEMO_SYMBOLS = ("AAPL", "TSLA", "MSFT", "GOOGL", "AMZN", "NVDA")  # keep in sync with ALLOWED_SYMBOLS in app.py
TEST_USER_EMAILS = ("verify@example.com", "second@example.com")
STATE_FILE = HERE / "seed_demo_state.json"

STEPS_PER_TICKER = (3, 4)          # a full reseed inserts this many rows per ticker
STEP_PCT_RANGE = (0.5, 3.0)        # size of each move, in percent
MAX_DRIFT_PCT = 5.0                # beyond this distance from the baseline the walk is pulled back
SPAN_HOURS = 3.0                   # seeded rows are spread over roughly the last N hours
LAST_ROW_MINUTES_AGO = 5           # ... ending this many minutes before now
NORMAL_VOLUME_RANGE = (0.75, 1.25)  # multiple of average_volume on ordinary steps
SPIKE_VOLUME_RANGE = (1.7, 2.5)     # multiple of average_volume on spike steps (flag fires above 1.5x)
SPIKE_TICKER_COUNT = 2
DEFAULT_SEED = 2026

INSERT_SQL = """
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
        return {"seeded_snapshot_ids": [], "spike_symbols": []}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))


def latest_snapshots(cur, symbols):
    """Newest price_snapshots row per symbol (whatever is left after the cleanup step)."""
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


def next_price(rng, price, baseline, day_low, day_high):
    """One step of 0.5-3%: random direction, pulled back toward the baseline once the
    walk has drifted more than MAX_DRIFT_PCT, and kept strictly inside the real day
    range (a price above day_high would contradict the row itself). When the full
    move would leave the range, a partial move toward that edge is taken instead of
    clamping, so prices do not pile up exactly on the day high/low."""
    magnitude = rng.uniform(*STEP_PCT_RANGE) / 100
    drift_pct = (price - baseline) / baseline * 100
    if abs(drift_pct) > MAX_DRIFT_PCT:
        direction = -1 if drift_pct > 0 else 1
    else:
        direction = rng.choice((-1, 1))
    candidate = price * (1 + direction * magnitude)
    if day_low is not None and day_high is not None and day_high > day_low:
        margin = (day_high - day_low) * 0.02
        low_bound, high_bound = day_low + margin, day_high - margin
        if not low_bound <= candidate <= high_bound:
            room = (high_bound - price) if direction > 0 else (price - low_bound)
            if room <= 0:  # already at that edge: turn around
                direction = -direction
                room = (high_bound - price) if direction > 0 else (price - low_bound)
            candidate = price + direction * max(room, 0) * rng.uniform(0.3, 0.9)
    return float(money(candidate))


def build_walk(rng, base, steps, spike_steps, timestamps):
    """Rows for one ticker: a random walk from the baseline row, one row per timestamp."""
    baseline = float(base["price"])
    day_low = float(base["day_low"]) if base["day_low"] is not None else None
    day_high = float(base["day_high"]) if base["day_high"] is not None else None
    average_volume = base["average_volume"] or base["volume"] or 0
    base_pct = float(base["percent_change"]) if base["percent_change"] is not None else 0.0
    implied_previous_close = baseline / (1 + base_pct / 100)  # keeps percent_change coherent

    rows = []
    price = baseline
    for index, captured_at in enumerate(timestamps):
        price = next_price(rng, price, baseline, day_low, day_high)
        is_spike = index >= steps - spike_steps
        multiplier = rng.uniform(*(SPIKE_VOLUME_RANGE if is_spike else NORMAL_VOLUME_RANGE))
        rows.append({
            "stock_id": base["stock_id"],
            "price": money(price),
            "percent_change": pct4((price / implied_previous_close - 1) * 100),
            "volume": int(average_volume * multiplier),
            "average_volume": base["average_volume"],
            "day_high": base["day_high"],
            "day_low": base["day_low"],
            "week52_high": base["week52_high"],
            "week52_low": base["week52_low"],
            "is_market_open": 0,
            "captured_at": captured_at,
            "is_spike": is_spike,
        })
    return rows


def spread_timestamps(rng, steps, start_at, end_at):
    """`steps` strictly increasing timestamps between start_at and end_at with some jitter."""
    total = (end_at - start_at).total_seconds()
    if total <= 0 or steps == 1:
        return [end_at] * steps if steps == 1 else [start_at + timedelta(seconds=60 * i) for i in range(steps)]
    slot = total / steps
    stamps = []
    for i in range(steps):
        nominal = slot * (i + 1)
        jitter = rng.uniform(-0.3, 0.3) * slot
        seconds = min(max(nominal + jitter, (stamps[-1] - start_at).total_seconds() + 60 if stamps else 0), total)
        stamps.append(start_at + timedelta(seconds=int(seconds)))
    return stamps


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--advance", action="store_true",
                        help="append one more step per ticker stamped now (do not delete or reset anything)")
    parser.add_argument("--dry-run", action="store_true", help="print the plan and write nothing")
    parser.add_argument("--seed", type=int, default=None, help="RNG seed for a reproducible walk")
    parser.add_argument("--spike", default=None, help="comma-separated tickers that get a volume spike")
    args = parser.parse_args()

    if args.seed is not None:
        rng = random.Random(args.seed)
    elif args.advance:
        rng = random.Random()
    else:
        rng = random.Random(DEFAULT_SEED)

    state = load_state()
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT NOW() AS now")
    now = cur.fetchone()["now"]  # the database clock, the same one captured_at defaults to

    deleted_snapshots = deleted_last_seen = 0
    if not args.advance:
        previous_ids = state.get("seeded_snapshot_ids", [])
        if previous_ids:
            placeholders = ",".join(["%s"] * len(previous_ids))
            cur.execute(f"DELETE FROM price_snapshots WHERE id IN ({placeholders})", previous_ids)
            deleted_snapshots = cur.rowcount
        cur.execute(
            """
            DELETE ls FROM last_seen ls
            JOIN users u ON u.id = ls.user_id
            JOIN stocks s ON s.id = ls.stock_id
            WHERE u.email IN ({}) AND s.symbol IN ({})
            """.format(",".join(["%s"] * len(TEST_USER_EMAILS)), ",".join(["%s"] * len(DEMO_SYMBOLS))),
            (*TEST_USER_EMAILS, *DEMO_SYMBOLS),
        )
        deleted_last_seen = cur.rowcount

    bases = latest_snapshots(cur, DEMO_SYMBOLS)
    available = [s for s in DEMO_SYMBOLS if s in bases]
    missing = [s for s in DEMO_SYMBOLS if s not in bases]

    if args.spike:
        spike_symbols = {s.strip().upper() for s in args.spike.split(",") if s.strip()}
    elif args.advance and state.get("spike_symbols"):
        spike_symbols = set(state["spike_symbols"])
    else:
        spike_symbols = set(rng.sample(available, min(SPIKE_TICKER_COUNT, len(available))))

    inserted_ids = []
    summary = []
    for symbol in available:
        base = bases[symbol]
        if args.advance:
            steps, spike_steps = 1, (1 if symbol in spike_symbols else 0)
            timestamps = [now]
        else:
            steps = rng.choice(STEPS_PER_TICKER)
            spike_steps = rng.choice((1, 2)) if symbol in spike_symbols else 0
            # Spread over the last SPAN_HOURS regardless of when the last real poll ran;
            # only the final row is guaranteed to be newer than the baseline row.
            start_at = now - timedelta(hours=SPAN_HOURS)
            end_at = max(now - timedelta(minutes=LAST_ROW_MINUTES_AGO), base["captured_at"] + timedelta(minutes=1))
            timestamps = spread_timestamps(rng, steps, start_at, end_at)

        rows = build_walk(rng, base, steps, spike_steps, timestamps)
        ids = []
        for row in rows:
            if args.dry_run:
                ids.append(None)
                continue
            cur.execute(INSERT_SQL, (
                row["stock_id"], row["price"], row["percent_change"], row["volume"], row["average_volume"],
                row["day_high"], row["day_low"], row["week52_high"], row["week52_low"],
                row["is_market_open"], row["captured_at"],
            ))
            ids.append(cur.lastrowid)
        inserted_ids.extend(i for i in ids if i is not None)

        last = rows[-1]
        first_view = compute_attention(last["price"], last["volume"], last["average_volume"],
                                       last["week52_high"], last["week52_low"], last_seen_price=None)
        returning = compute_attention(last["price"], last["volume"], last["average_volume"],
                                      last["week52_high"], last["week52_low"], last_seen_price=base["price"])
        prices = [float(r["price"]) for r in rows]
        summary.append({
            "symbol": symbol,
            "baseline": float(base["price"]),
            "steps": steps,
            "low": min(prices),
            "high": max(prices),
            "last": prices[-1],
            "change_pct": (prices[-1] / float(base["price"]) - 1) * 100,
            "spike": "yes" if spike_steps else "no",
            "volume_ratio": last["volume"] / last["average_volume"] if last["average_volume"] else None,
            "first_view": f"{first_view['attention_score']} {first_view['attention_category']}",
            "returning": f"{returning['attention_score']} {returning['attention_category']}",
            "ids": f"{ids[0]}-{ids[-1]}" if ids[0] is not None and len(ids) > 1 else (str(ids[0]) if ids[0] is not None else "-"),
            "window": f"{timestamps[0]:%H:%M}->{timestamps[-1]:%H:%M}",
        })

    if args.dry_run:
        conn.rollback()
    else:
        conn.commit()
        state["seeded_snapshot_ids"] = (state.get("seeded_snapshot_ids", []) if args.advance else []) + inserted_ids
        state["spike_symbols"] = sorted(spike_symbols)
        state["last_run"] = now.isoformat(sep=" ")
        state["mode"] = "advance" if args.advance else "reseed"
        save_state(state)
    conn.close()

    mode = "DRY RUN (nothing written)" if args.dry_run else ("ADVANCE" if args.advance else "FULL RESEED")
    print(f"\n{mode} at {now:%Y-%m-%d %H:%M:%S} (database clock)")
    if not args.advance:
        print(f"  deleted {deleted_snapshots} previously seeded snapshot(s), "
              f"{deleted_last_seen} last_seen row(s) for {', '.join(TEST_USER_EMAILS)}")
    if missing:
        print(f"  skipped {', '.join(missing)}: no snapshot yet (add to a watchlist or run POST /poll-prices first)")
    print(f"  volume spike on: {', '.join(sorted(spike_symbols)) or 'none'}\n")

    header = (f"{'Ticker':6} {'Baseline':>9} {'Rows':>4} {'Sim. low':>9} {'Sim. high':>9} {'Last':>9} "
              f"{'vs base':>8} {'Spike':>5} {'Vol x':>5}  {'1st view':<14} {'Returning':<21} {'Snapshot ids':<13} Window")
    print(header)
    print("-" * len(header))
    for s in summary:
        vol = f"{s['volume_ratio']:.2f}" if s["volume_ratio"] is not None else "-"
        print(f"{s['symbol']:6} {s['baseline']:>9.2f} {s['steps']:>4} {s['low']:>9.2f} {s['high']:>9.2f} {s['last']:>9.2f} "
              f"{s['change_pct']:>+7.2f}% {s['spike']:>5} {vol:>5}  {s['first_view']:<14} {s['returning']:<21} {s['ids']:<13} {s['window']}")
    print("\n  '1st view' = score a user sees right after login (no previous visit);"
          " 'Returning' = score for a user whose last visit saw the baseline price.")
    if not args.advance and not args.dry_run:
        print("  Next: log in and load the watchlist (clean first view), then run this script with --advance and refresh to see the diff.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
