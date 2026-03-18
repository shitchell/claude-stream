"""Date/time parsing utility for human-friendly date strings.

Adapted from the countdown script's parse_timestring function.
Supports ISO dates, natural language, keywords, and relative times.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from dateutil.parser import parse as dateutil_parse


def _now() -> datetime:
    """Get current time (UTC). Separated for testability."""
    return datetime.now(timezone.utc)


# Keyword substitutions applied before dateutil parsing
def _get_substitutions() -> list[tuple[str, str]]:
    """Get keyword substitutions based on current time.

    Uses _now() as base so mocking works consistently in tests.
    """
    now = _now()
    return [
        (r"\bnoon\b", "12:00"),
        (r"\bmidnight\b", "00:00"),
        (r"\btoday\b", now.strftime("%B %d, %Y")),
        (r"\btomorrow\b", (now + timedelta(days=1)).strftime("%B %d, %Y")),
    ]


# Regex for relative time: "now +/-N unit" or just "+/-N unit" or "N unit"
_RELATIVE_RE = re.compile(
    r"^(?:now\s+)?([+-])?\s*(\d+)\s*"
    r"(s|seconds?|m|minutes?|h|hrs?|hours?|d|days?|w|wks?|weeks?"
    r"|M|months?|y|yrs?|years?)$",
    # Note: NO re.IGNORECASE — "m" (minutes) vs "M" (months) is intentional
)

# Regex for "N units ago" syntax: "30 minutes ago", "2 hours ago"
_AGO_RE = re.compile(
    r"^(\d+)\s+" r"(seconds?|minutes?|hours?|days?|weeks?|months?|years?)" r"\s+ago$",
    re.IGNORECASE,
)

# Map lowercase unit names to seconds (for "ago" syntax)
_AGO_UNIT_SECONDS: dict[str, int] = {
    "second": 1,
    "seconds": 1,
    "minute": 60,
    "minutes": 60,
    "hour": 3600,
    "hours": 3600,
    "day": 86400,
    "days": 86400,
    "week": 604800,
    "weeks": 604800,
    "month": 2629743,
    "months": 2629743,
    "year": 31556926,
    "years": 31556926,
}

# Map unit strings to seconds
_UNIT_SECONDS: dict[str, int] = {}
for _names, _secs in [
    (("s", "second", "seconds"), 1),
    (("m", "minute", "minutes"), 60),
    (("h", "hr", "hrs", "hour", "hours"), 3600),
    (("d", "day", "days"), 86400),
    (("w", "wk", "wks", "week", "weeks"), 604800),
    (("M", "month", "months"), 2629743),
    (("y", "yr", "yrs", "year", "years"), 31556926),
]:
    for _name in _names:
        _UNIT_SECONDS[_name] = _secs


def _ensure_aware(dt: datetime) -> datetime:
    """Ensure a datetime is timezone-aware (assume UTC if naive)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_datetime(text: str) -> datetime:
    """Parse a human-friendly date/time string into a timezone-aware datetime.

    Supports:
    - ISO dates: 2026-03-17, 2026-03-17T14:23:05, 2026-03-17T14:23:05Z
    - Natural language: March 17 2026, Monday at 5pm (via dateutil)
    - Keywords: noon, midnight, today, tomorrow
    - Relative times: now -2h, +30m, 5d, now +1w, 30 minutes ago

    Returns:
        A timezone-aware datetime in UTC.

    Raises:
        ValueError: If the string cannot be parsed.
    """
    text = text.strip()
    if not text:
        raise ValueError("Empty date string")

    # Check for relative time pattern
    match = _RELATIVE_RE.match(text)
    if match:
        sign_str, num_str, unit = match.groups()
        sign = -1 if sign_str == "-" else 1
        seconds = int(num_str) * _UNIT_SECONDS.get(unit, 1)
        return _now() + timedelta(seconds=sign * seconds)

    # Check for "N units ago" pattern
    ago_match = _AGO_RE.match(text)
    if ago_match:
        num_str, unit = ago_match.groups()
        seconds = int(num_str) * _AGO_UNIT_SECONDS.get(unit.lower(), 1)
        return _now() - timedelta(seconds=seconds)

    # Apply keyword substitutions
    processed = text.lower()
    for keyword, substitution in _get_substitutions():
        processed = re.sub(keyword, substitution, processed, flags=re.IGNORECASE)

    # Parse with dateutil
    try:
        result = dateutil_parse(processed)
    except (ValueError, OverflowError) as e:
        raise ValueError(f"Cannot parse date: {text!r}") from e

    return _ensure_aware(result)
