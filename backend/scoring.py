"""Attention score: a transparent, rule-based 0-100 score. No ML, no black box.

    score = min(40, 40 * |% change since the user's last visit|)
          + 30 if today's volume is more than 1.5x its average
          + 30 if the price is within 2% of its 52-week high or low
    clamped to 0-100, then bucketed:
          0-30 Stable | 31-60 Monitor | 61-80 Important | 81-100 Immediate attention

The "% change" term is in percentage points, so a 1% move since the last visit
already earns the full 40 (the design doc's "40 * |% change|, capped at 40").
Every intermediate value is returned next to the score so the UI can explain
exactly why a stock landed where it did.

Pure functions only (no Flask, no DB) so this module is trivially testable.
"""

PRICE_CHANGE_MAX_POINTS = 40
PRICE_CHANGE_POINTS_PER_PERCENT = 40
VOLUME_SPIKE_POINTS = 30
VOLUME_SPIKE_RATIO = 1.5
MILESTONE_POINTS = 30
MILESTONE_BAND_PCT = 2.0

CATEGORY_BANDS = (
    (30, "Stable"),
    (60, "Monitor"),
    (80, "Important"),
    (100, "Immediate attention"),
)


def _f(value):
    return float(value) if value is not None else None


def attention_category(score):
    for upper_bound, label in CATEGORY_BANDS:
        if score <= upper_bound:
            return label
    return CATEGORY_BANDS[-1][1]


def compute_attention(price, volume, average_volume, week52_high, week52_low, last_seen_price):
    """Score one stock from its latest snapshot and the user's previous visit.

    `last_seen_price` is None on a first-time view; the price-change term is
    then skipped (0 points) and the change fields are omitted from the result.
    """
    price = _f(price)
    volume = _f(volume)
    average_volume = _f(average_volume)
    week52_high = _f(week52_high)
    week52_low = _f(week52_low)
    last_seen_price = _f(last_seen_price)

    result = {}
    reasons = []

    # 1. Price change since the user's last visit (max 40 points)
    price_points = 0.0
    if price is not None and last_seen_price:  # None or 0 -> nothing to compare against
        change = (price - last_seen_price) / last_seen_price
        change_pct = change * 100
        price_points = min(PRICE_CHANGE_MAX_POINTS, PRICE_CHANGE_POINTS_PER_PERCENT * abs(change_pct))
        result["change_since_last_visit"] = round(change, 6)
        result["change_since_last_visit_pct"] = round(change_pct, 4)
        if round(change_pct, 2) == 0:
            reasons.append("Price unchanged since your last visit (+0.0 pts)")
        else:
            direction = "up" if change_pct > 0 else "down"
            reasons.append(
                f"Price {direction} {abs(change_pct):.2f}% since your last visit (+{price_points:.1f} pts)"
            )
    else:
        reasons.append("First view of this stock, so there is no previous price to compare (+0 pts)")

    # 2. Volume vs. average volume (30 points on a spike)
    volume_ratio = volume / average_volume if (volume is not None and average_volume) else None
    volume_spike = volume_ratio is not None and volume_ratio > VOLUME_SPIKE_RATIO
    volume_points = VOLUME_SPIKE_POINTS if volume_spike else 0
    result["volume_ratio"] = round(volume_ratio, 3) if volume_ratio is not None else None
    result["volume_spike"] = volume_spike
    if volume_ratio is None:
        reasons.append("Volume or average volume unavailable (+0 pts)")
    elif volume_spike:
        reasons.append(
            f"Volume is {volume_ratio:.2f}x its average, above the {VOLUME_SPIKE_RATIO}x "
            f"spike threshold (+{VOLUME_SPIKE_POINTS} pts)"
        )
    else:
        reasons.append(
            f"Volume is {volume_ratio:.2f}x its average, below the {VOLUME_SPIKE_RATIO}x "
            f"spike threshold (+0 pts)"
        )

    # 3. 52-week milestones (30 points if near either end of the range)
    milestones = []
    distance_to_high = distance_to_low = None
    if price is not None and week52_high:
        distance_to_high = (week52_high - price) / week52_high * 100  # positive = below the high
        if distance_to_high <= MILESTONE_BAND_PCT:
            milestones.append("near_52w_high")
    if price is not None and week52_low:
        distance_to_low = (price - week52_low) / week52_low * 100  # positive = above the low
        if distance_to_low <= MILESTONE_BAND_PCT:
            milestones.append("near_52w_low")
    milestone_points = MILESTONE_POINTS if milestones else 0
    result["distance_to_52w_high_pct"] = round(distance_to_high, 2) if distance_to_high is not None else None
    result["distance_to_52w_low_pct"] = round(distance_to_low, 2) if distance_to_low is not None else None
    result["milestones"] = milestones

    if "near_52w_high" in milestones:
        side = "above" if distance_to_high < 0 else "below"
        reasons.append(
            f"Within {MILESTONE_BAND_PCT:g}% of its 52-week high "
            f"({abs(distance_to_high):.2f}% {side} it) (+{MILESTONE_POINTS} pts)"
        )
    if "near_52w_low" in milestones:
        side = "below" if distance_to_low < 0 else "above"
        reasons.append(
            f"Within {MILESTONE_BAND_PCT:g}% of its 52-week low "
            f"({abs(distance_to_low):.2f}% {side} it) (+{MILESTONE_POINTS} pts)"
        )
    if not milestones:
        parts = []
        if distance_to_high is not None:
            parts.append(f"{distance_to_high:.2f}% below its 52-week high")
        if distance_to_low is not None:
            parts.append(f"{distance_to_low:.2f}% above its 52-week low")
        reasons.append((" and ".join(parts) if parts else "52-week range unavailable") + " (+0 pts)")

    total = price_points + volume_points + milestone_points
    score = int(round(max(0.0, min(100.0, total))))
    result["attention_score"] = score
    result["attention_category"] = attention_category(score)
    result["score_breakdown"] = {
        "price_change_points": round(price_points, 1),
        "volume_points": volume_points,
        "milestone_points": milestone_points,
        "reasons": reasons,
    }
    return result
