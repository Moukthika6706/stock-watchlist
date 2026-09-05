"""Thin client for the Twelve Data /quote endpoint.

Kept free of Flask/DB imports so the same fetch+parse code can be reused by the
background poller later without importing the web app.
"""
import os
from decimal import Decimal, InvalidOperation

import requests

QUOTE_URL = "https://api.twelvedata.com/quote"
REQUEST_TIMEOUT_SECONDS = 10

TWO_PLACES = Decimal("0.01")      # matches DECIMAL(12,2) columns
FOUR_PLACES = Decimal("0.0001")   # matches DECIMAL(8,4) percent_change


class MarketDataError(Exception):
    """Provider unreachable, rate-limited, or returned an unexpected payload."""

    def __init__(self, message, status_code=502):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class InvalidSymbolError(MarketDataError):
    """Twelve Data does not recognise the ticker."""

    def __init__(self, symbol):
        super().__init__(f"Unknown ticker symbol '{symbol}'", status_code=404)
        self.symbol = symbol


def _decimal(value, places):
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value)).quantize(places)
    except (InvalidOperation, ValueError):
        return None


def _integer(value):
    if value in (None, ""):
        return None
    try:
        return int(Decimal(str(value)))
    except (InvalidOperation, ValueError):
        return None


def parse_quote(payload):
    """Normalise a raw Twelve Data quote into the columns we persist."""
    fifty_two = payload.get("fifty_two_week") or {}
    return {
        "symbol": (payload.get("symbol") or "").upper(),
        "company_name": payload.get("name") or payload.get("symbol") or "",
        "market": payload.get("exchange"),
        "price": _decimal(payload.get("close"), TWO_PLACES),
        "percent_change": _decimal(payload.get("percent_change"), FOUR_PLACES),
        "volume": _integer(payload.get("volume")),
        "average_volume": _integer(payload.get("average_volume")),
        "day_high": _decimal(payload.get("high"), TWO_PLACES),
        "day_low": _decimal(payload.get("low"), TWO_PLACES),
        "week52_high": _decimal(fifty_two.get("high"), TWO_PLACES),
        "week52_low": _decimal(fifty_two.get("low"), TWO_PLACES),
        "is_market_open": bool(payload.get("is_market_open", False)),
    }


def fetch_quote(symbol):
    """Fetch and parse the latest quote for one symbol (costs 1 API credit).

    Raises InvalidSymbolError for unknown tickers and MarketDataError for
    network failures, rate limiting (429) or malformed responses.
    """
    api_key = os.getenv("API_KEY")
    if not api_key:
        raise MarketDataError("API_KEY is not configured on the server", status_code=500)

    try:
        response = requests.get(
            QUOTE_URL,
            params={"symbol": symbol, "apikey": api_key},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise MarketDataError(f"Market data provider unreachable: {exc}") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise MarketDataError("Market data provider returned a non-JSON response") from exc

    if payload.get("status") == "error" or response.status_code != 200:
        code = payload.get("code", response.status_code)
        if code == 404:
            raise InvalidSymbolError(symbol)
        if code == 429:
            raise MarketDataError(
                "Market data rate limit reached (8 requests/minute on the free tier); "
                "try again in a minute",
                status_code=429,
            )
        raise MarketDataError(payload.get("message") or "Market data provider error")

    quote = parse_quote(payload)
    if quote["price"] is None:
        raise MarketDataError(f"Market data provider returned no price for '{symbol}'")
    return quote
