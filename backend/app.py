import logging
import os
import threading
import time
from datetime import timedelta
from urllib.parse import quote_plus

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, get_jwt_identity, jwt_required
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, literal_column, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

from market_data import InvalidSymbolError, MarketDataError, fetch_quote
from scoring import compute_attention

load_dotenv()

app = Flask(__name__)

# The React dev server (port 3000) calls Flask (port 5000) cross-origin. Only the
# listed origins are allowed, the JWT arrives in the Authorization header (not a
# cookie) so credentials stay off, and FRONTEND_ORIGINS can override the list.
FRONTEND_ORIGINS = [
    origin.strip()
    for origin in os.getenv('FRONTEND_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000').split(',')
    if origin.strip()
]
CORS(
    app,
    origins=FRONTEND_ORIGINS,
    allow_headers=['Content-Type', 'Authorization'],
    methods=['GET', 'POST', 'DELETE', 'OPTIONS'],
    supports_credentials=False,
)

db_password = quote_plus(os.getenv('DB_PASSWORD', ''))

app.config['SQLALCHEMY_DATABASE_URI'] = (
    f"mysql+pymysql://{os.getenv('DB_USER')}:{db_password}"
    f"@{os.getenv('DB_HOST')}/{os.getenv('DB_NAME')}"
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'dev-secret-change-this')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=24)  # long enough to survive a demo session
# flask-jwt-extended defaults to {"msg": ...}; use the same {"message": ...} key as our own errors
app.config['JWT_ERROR_MESSAGE_KEY'] = 'message'

db = SQLAlchemy(app)
jwt = JWTManager(app)
app.logger.setLevel(logging.INFO)  # so poll progress shows in the dev console

# Twelve Data's free tier is 8 requests/minute and 800/day, and NSE tickers need
# a paid plan, so the watchlist is restricted to these US tickers for the demo.
ALLOWED_SYMBOLS = ("AAPL", "TSLA", "MSFT", "GOOGL", "AMZN", "NVDA")

SPARKLINE_POINTS = 15  # recent prices per stock returned by GET /watchlist for the trend line

# Polling stays inside the free tier however long the watched set grows: calls are
# spaced POLL_INTER_CALL_DELAY_SECONDS apart and, after every POLL_RATE_LIMIT_PER_MINUTE
# calls, the job waits out the remainder of that 60-second window.
POLL_RATE_LIMIT_PER_MINUTE = 8
POLL_INTER_CALL_DELAY_SECONDS = 1.0
_poll_lock = threading.Lock()  # one poll at a time, so a double-click cannot double-spend credits


# --------------------------------------------------------------------------
# Models - these map onto the hand-created MySQL tables; db.create_all() is
# intentionally never called so the schema stays the single source of truth.
# --------------------------------------------------------------------------
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())


class Stock(db.Model):
    __tablename__ = 'stocks'
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(20), unique=True, nullable=False)
    company_name = db.Column(db.String(150), nullable=False)
    current_price = db.Column(db.Numeric(12, 2))
    market = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())


class WatchlistItem(db.Model):
    __tablename__ = 'watchlist'
    __table_args__ = (db.UniqueConstraint('user_id', 'stock_id'),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    stock_id = db.Column(db.Integer, db.ForeignKey('stocks.id'), nullable=False)
    added_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())


class PriceSnapshot(db.Model):
    __tablename__ = 'price_snapshots'
    id = db.Column(db.Integer, primary_key=True)
    stock_id = db.Column(db.Integer, db.ForeignKey('stocks.id'), nullable=False)
    price = db.Column(db.Numeric(12, 2), nullable=False)
    percent_change = db.Column(db.Numeric(8, 4))
    volume = db.Column(db.BigInteger)
    average_volume = db.Column(db.BigInteger)
    day_high = db.Column(db.Numeric(12, 2))
    day_low = db.Column(db.Numeric(12, 2))
    week52_high = db.Column(db.Numeric(12, 2))
    week52_low = db.Column(db.Numeric(12, 2))
    is_market_open = db.Column(db.Boolean)
    captured_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())


class LastSeen(db.Model):
    """What a user saw the last time they viewed a stock: one row per user+stock, upserted on each view."""
    __tablename__ = 'last_seen'
    __table_args__ = (db.UniqueConstraint('user_id', 'stock_id'),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    stock_id = db.Column(db.Integer, db.ForeignKey('stocks.id'), nullable=False)
    last_seen_price = db.Column(db.Numeric(12, 2))
    last_seen_volume = db.Column(db.BigInteger)
    last_seen_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def error(message, status):
    return jsonify({"message": message}), status


def missing_fields(data, fields):
    """Names of required string fields that are absent or blank in a JSON body."""
    if not isinstance(data, dict):
        return list(fields)
    return [f for f in fields if not isinstance(data.get(f), str) or not data[f].strip()]


def current_user_id():
    """User id from the verified JWT - never from the request body."""
    return int(get_jwt_identity())


def _num(value):
    return float(value) if value is not None else None


def _iso(dt):
    return dt.isoformat() if dt is not None else None


def snapshot_from_quote(stock_id, quote):
    """Build a PriceSnapshot row from a parsed Twelve Data quote (the poller will reuse this)."""
    return PriceSnapshot(
        stock_id=stock_id,
        price=quote['price'],
        percent_change=quote['percent_change'],
        volume=quote['volume'],
        average_volume=quote['average_volume'],
        day_high=quote['day_high'],
        day_low=quote['day_low'],
        week52_high=quote['week52_high'],
        week52_low=quote['week52_low'],
        is_market_open=quote['is_market_open'],
    )


def create_stock_from_provider(symbol):
    """Look the ticker up on Twelve Data, insert the `stocks` row and seed its
    first price_snapshot so the watchlist has data before the poller runs.

    Raises InvalidSymbolError / MarketDataError from fetch_quote. If two
    requests race to create the same symbol, the loser re-reads the winner's row.
    """
    quote = fetch_quote(symbol)
    stock = Stock(
        symbol=symbol,
        company_name=(quote['company_name'] or symbol)[:150],
        market=(quote['market'] or '')[:50] or None,
        current_price=quote['price'],
    )
    db.session.add(stock)
    try:
        db.session.flush()  # assigns stock.id
        db.session.add(snapshot_from_quote(stock.id, quote))
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        stock = Stock.query.filter_by(symbol=symbol).first()
        if stock is None:
            raise
    return stock


def watched_stocks():
    """Distinct stocks on at least one user's watchlist: the shared poll set.

    Ten users watching AAPL cost one API call, not ten; personalization happens
    later via last_seen, never via per-user fetches.
    """
    return (
        Stock.query.join(WatchlistItem, WatchlistItem.stock_id == Stock.id)
        .distinct()
        .order_by(Stock.symbol)
        .all()
    )


def poll_watched_stocks():
    """Fetch a fresh quote for every watched stock and append one price_snapshots
    row each (captured_at defaults to now() in the DB), updating stocks.current_price.

    Every ticker is committed on its own, so a failure (bad response, rate limit,
    network) is logged, recorded in the result and the loop moves on; nothing
    already written is lost. Returns a summary the caller can inspect.
    """
    stocks = watched_stocks()
    started = time.monotonic()
    window_started = started
    calls_in_window = 0
    succeeded, failed = [], []

    for index, stock in enumerate(stocks):
        if calls_in_window >= POLL_RATE_LIMIT_PER_MINUTE:
            pause = 60 - (time.monotonic() - window_started)
            if pause > 0:
                app.logger.info("poll: %d calls this minute, pausing %.1fs before %s",
                                calls_in_window, pause, stock.symbol)
                time.sleep(pause)
            window_started = time.monotonic()
            calls_in_window = 0
        elif index > 0:
            time.sleep(POLL_INTER_CALL_DELAY_SECONDS)
        calls_in_window += 1

        try:
            quote = fetch_quote(stock.symbol)
            snapshot = snapshot_from_quote(stock.id, quote)
            db.session.add(snapshot)
            stock.current_price = quote['price']
            db.session.commit()
            app.logger.info("poll: %s -> %s (snapshot %s)", stock.symbol, quote['price'], snapshot.id)
            succeeded.append({
                "symbol": stock.symbol,
                "price": _num(quote['price']),
                "is_market_open": quote['is_market_open'],
                "snapshot_id": snapshot.id,
            })
        except MarketDataError as exc:
            db.session.rollback()
            app.logger.warning("poll: %s failed (%s): %s", stock.symbol, exc.status_code, exc.message)
            failed.append({"symbol": stock.symbol, "error": exc.message, "status_code": exc.status_code})
        except Exception as exc:  # e.g. a DB hiccup - still keep going for the other tickers
            db.session.rollback()
            app.logger.exception("poll: %s failed unexpectedly", stock.symbol)
            failed.append({"symbol": stock.symbol, "error": f"{type(exc).__name__}: {exc}"})

    if not stocks:
        status = "nothing_to_poll"
    elif not failed:
        status = "ok"
    elif succeeded:
        status = "partial"
    else:
        status = "failed"
    return {
        "status": status,
        "polled": len(stocks),
        "succeeded": succeeded,
        "failed": failed,
        "duration_seconds": round(time.monotonic() - started, 1),
    }


def watchlist_query(user_id):
    """One user's watchlist rows, each joined to that stock's most recent snapshot
    and to what this user saw on their previous visit (last_seen).

    A single SQL statement regardless of watchlist size (no N+1): the LEFT JOIN
    picks the snapshot whose id is MAX(id) for the stock, and age_seconds is
    computed by the database clock so stale data can be flagged consistently.
    Rows are (WatchlistItem, Stock, PriceSnapshot | None, age_seconds | None, LastSeen | None).
    """
    latest = aliased(PriceSnapshot)
    latest_snapshot_id = (
        select(func.max(latest.id))
        .where(latest.stock_id == Stock.id)
        .correlate(Stock)
        .scalar_subquery()
    )
    age_seconds = func.timestampdiff(literal_column('SECOND'), PriceSnapshot.captured_at, func.now())
    return (
        db.session.query(WatchlistItem, Stock, PriceSnapshot, age_seconds, LastSeen)
        .join(Stock, Stock.id == WatchlistItem.stock_id)
        .outerjoin(PriceSnapshot, PriceSnapshot.id == latest_snapshot_id)
        .outerjoin(LastSeen, (LastSeen.user_id == user_id) & (LastSeen.stock_id == Stock.id))
        .filter(WatchlistItem.user_id == user_id)
        .order_by(WatchlistItem.added_at.desc(), WatchlistItem.id.desc())
    )


def sparklines_for(stock_ids):
    """Last SPARKLINE_POINTS prices per stock, oldest -> newest, in ONE query.

    ROW_NUMBER() partitioned by stock (MySQL 8) keeps this a single statement no
    matter how many stocks are watched. Ordered by snapshot id, i.e. insertion
    order, which is chronological for poller-written rows and guarantees the
    final point is the same row as `latest`.
    """
    if not stock_ids:
        return {}
    recency = func.row_number().over(
        partition_by=PriceSnapshot.stock_id, order_by=PriceSnapshot.id.desc()
    ).label('recency')
    ranked = (
        select(PriceSnapshot.stock_id, PriceSnapshot.price, recency)
        .where(PriceSnapshot.stock_id.in_(stock_ids))
        .subquery()
    )
    rows = db.session.execute(
        select(ranked.c.stock_id, ranked.c.price)
        .where(ranked.c.recency <= SPARKLINE_POINTS)
        .order_by(ranked.c.stock_id, ranked.c.recency.desc())
    ).all()
    series = {}
    for stock_id, price in rows:
        series.setdefault(stock_id, []).append(_num(price))
    return series


def serialize_watchlist_row(item, stock, snapshot, age_seconds, last_seen, sparkline=None):
    """Shape one watchlist row for the API. `last_seen` must be the row as it was
    BEFORE this request touches it, so the diff is against the previous visit."""
    latest = None
    if snapshot is not None:
        latest = {
            "sparkline": sparkline if sparkline is not None else [],
            "price": _num(snapshot.price),
            "percent_change": _num(snapshot.percent_change),
            "volume": snapshot.volume,
            "average_volume": snapshot.average_volume,
            "day_high": _num(snapshot.day_high),
            "day_low": _num(snapshot.day_low),
            "week52_high": _num(snapshot.week52_high),
            "week52_low": _num(snapshot.week52_low),
            "is_market_open": snapshot.is_market_open,
            "captured_at": _iso(snapshot.captured_at),
            "age_seconds": int(age_seconds) if age_seconds is not None else None,
        }
        latest.update(compute_attention(
            price=snapshot.price,
            volume=snapshot.volume,
            average_volume=snapshot.average_volume,
            week52_high=snapshot.week52_high,
            week52_low=snapshot.week52_low,
            last_seen_price=last_seen.last_seen_price if last_seen is not None else None,
        ))
    return {
        "watchlist_id": item.id,
        "stock_id": stock.id,
        "symbol": stock.symbol,
        "company_name": stock.company_name,
        "market": stock.market,
        "added_at": _iso(item.added_at),
        "last_seen": None if last_seen is None else {
            "price": _num(last_seen.last_seen_price),
            "volume": last_seen.last_seen_volume,
            "at": _iso(last_seen.last_seen_at),
        },
        "latest": latest,
    }


def record_last_seen(user_id, rows):
    """Upsert last_seen for every watched stock that has a snapshot, in ONE statement.

    Called only after the response rows are serialized, so the diff the user
    receives is measured against their previous visit, and this visit becomes
    the baseline for the next one. INSERT ... ON DUPLICATE KEY UPDATE relies on
    the UNIQUE(user_id, stock_id) key; last_seen_at defaults to now() on insert.
    """
    values = [
        {
            "user_id": user_id,
            "stock_id": stock.id,
            "last_seen_price": snapshot.price,
            "last_seen_volume": snapshot.volume,
        }
        for _item, stock, snapshot, _age, _previous in rows
        if snapshot is not None
    ]
    if not values:
        return
    stmt = mysql_insert(LastSeen).values(values)
    stmt = stmt.on_duplicate_key_update(
        last_seen_price=stmt.inserted.last_seen_price,
        last_seen_volume=stmt.inserted.last_seen_volume,
        last_seen_at=func.now(),
    )
    db.session.execute(stmt)
    db.session.commit()


@app.errorhandler(HTTPException)
def handle_http_exception(exc):
    """Return Flask's own 404/405/415 errors as JSON instead of HTML pages."""
    return error(exc.description, exc.code)


# --------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------
@app.route('/signup', methods=['POST'])
def signup():
    data = request.get_json(silent=True)
    missing = missing_fields(data, ['name', 'email', 'password'])
    if missing:
        return error(f"Missing or empty field(s): {', '.join(missing)}", 400)

    email = data['email'].strip().lower()
    if User.query.filter_by(email=email).first():
        return error("Email already registered", 409)

    new_user = User(
        name=data['name'].strip(),
        email=email,
        password_hash=generate_password_hash(data['password']),
    )
    db.session.add(new_user)
    try:
        db.session.commit()
    except IntegrityError:  # concurrent signup with the same email
        db.session.rollback()
        return error("Email already registered", 409)
    return jsonify({"message": "User created"}), 201


@app.route('/login', methods=['POST'])
def login():
    data = request.get_json(silent=True)
    missing = missing_fields(data, ['email', 'password'])
    if missing:
        return error(f"Missing or empty field(s): {', '.join(missing)}", 400)

    user = User.query.filter_by(email=data['email'].strip().lower()).first()
    if user and check_password_hash(user.password_hash, data['password']):
        token = create_access_token(identity=str(user.id))
        return jsonify({"access_token": token}), 200
    return error("Invalid credentials", 401)


@app.route('/me', methods=['GET'])
@jwt_required()
def me():
    user = db.session.get(User, current_user_id())
    if user is None:
        return error("User no longer exists", 404)
    return jsonify({"user_id": user.id, "name": user.name, "email": user.email}), 200


# --------------------------------------------------------------------------
# Watchlist - every route scopes by the JWT identity, never a body user_id
# --------------------------------------------------------------------------
@app.route('/watchlist', methods=['GET'])
@jwt_required()
def get_watchlist():
    user_id = current_user_id()
    rows = watchlist_query(user_id).all()
    sparklines = sparklines_for([stock.id for _item, stock, _snap, _age, _prev in rows])
    items = [serialize_watchlist_row(*row, sparkline=sparklines.get(row[1].id)) for row in rows]  # diff vs. previous visit...
    record_last_seen(user_id, rows)                                                                # ...then this visit becomes the baseline
    return jsonify({"watchlist": items, "count": len(items)}), 200


@app.route('/watchlist', methods=['POST'])
@jwt_required()
def add_to_watchlist():
    user_id = current_user_id()
    data = request.get_json(silent=True)
    if missing_fields(data, ['symbol']):
        return error("Request body must include a non-empty 'symbol'", 400)

    symbol = data['symbol'].strip().upper()
    if symbol not in ALLOWED_SYMBOLS:
        return error(
            f"'{symbol}' is not supported. Allowed tickers: {', '.join(ALLOWED_SYMBOLS)}", 400
        )

    stock = Stock.query.filter_by(symbol=symbol).first()
    if stock is not None:
        if WatchlistItem.query.filter_by(user_id=user_id, stock_id=stock.id).first():
            return error(f"{symbol} is already on your watchlist", 409)
    else:
        try:
            stock = create_stock_from_provider(symbol)
        except InvalidSymbolError as exc:
            return error(exc.message, 404)
        except MarketDataError as exc:
            return error(exc.message, exc.status_code)

    item = WatchlistItem(user_id=user_id, stock_id=stock.id)
    db.session.add(item)
    try:
        db.session.commit()
    except IntegrityError:  # concurrent add of the same stock by the same user
        db.session.rollback()
        return error(f"{symbol} is already on your watchlist", 409)

    row = watchlist_query(user_id).filter(WatchlistItem.id == item.id).first()
    sparkline = sparklines_for([stock.id]).get(stock.id)
    return jsonify({
        "message": f"{symbol} added to watchlist",
        "item": serialize_watchlist_row(*row, sparkline=sparkline),
    }), 201


@app.route('/watchlist/<int:stock_id>', methods=['DELETE'])
@jwt_required()
def remove_from_watchlist(stock_id):
    user_id = current_user_id()
    item = WatchlistItem.query.filter_by(user_id=user_id, stock_id=stock_id).first()
    if item is None:
        return error("That stock is not on your watchlist", 404)

    db.session.delete(item)
    db.session.commit()
    return jsonify({"message": "Removed from watchlist", "stock_id": stock_id}), 200


# --------------------------------------------------------------------------
# Data ingestion - manual trigger, no JWT by design (internal/admin use).
# A scheduler was deliberately left out to keep the demo simple and debuggable.
# --------------------------------------------------------------------------
def demo_mode_enabled():
    """DEMO_MODE=true blocks live polling so a stray POST /poll-prices cannot
    overwrite the seeded demo snapshots with the frozen holiday-weekend close.
    Unset counts as ON (fail-safe); set DEMO_MODE=false in backend/.env and
    restart the server to poll for real."""
    return os.getenv('DEMO_MODE', 'true').strip().lower() not in ('0', 'false', 'no', 'off')


@app.route('/poll-prices', methods=['POST'])
def poll_prices():
    if demo_mode_enabled():
        return error(
            "Polling is disabled while DEMO_MODE is on: a real poll would overwrite the seeded demo "
            "snapshots with the frozen Friday close. Set DEMO_MODE=false in backend/.env and restart "
            "the server to re-enable it.",
            423,
        )
    if not _poll_lock.acquire(blocking=False):
        return error("A poll is already in progress; wait for it to finish", 409)
    try:
        result = poll_watched_stocks()
    finally:
        _poll_lock.release()
    return jsonify(result), 200


@app.route('/db-check')
def db_check():
    from sqlalchemy import text
    result = db.session.execute(text("SHOW TABLES;"))
    tables = [row[0] for row in result]
    return {"connected": True, "tables": tables}


if __name__ == '__main__':
    app.run(debug=True, port=5000)
