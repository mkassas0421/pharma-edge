"""Shared date-parsing helpers used across scrapers."""

import datetime


def parse_date(s: str | None) -> datetime.datetime | None:
    """Parse a date string in common US/EU formats. Handles ``YYYY-MM`` too.

    Text formats ("July 30, 2026") are tried on the full string first; the
    10-char truncation is only a fallback for ISO strings with a time
    component ("2026-07-30T12:00:00").
    """
    if not s:
        return None
    s = s.strip()
    # Handle "2026-07" (year-month only) → first of month
    if len(s) == 7 and s[4] == "-":
        s = f"{s}-01"
    cleaned = s.replace(",", "")
    for fmt in ("%Y-%m-%d", "%B %d %Y", "%b %d %Y", "%B %Y"):
        try:
            return datetime.datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    # Fallback: truncated ISO date with a time component
    s10 = cleaned[:10]
    if s10 != cleaned:
        try:
            return datetime.datetime.strptime(s10, "%Y-%m-%d")
        except ValueError:
            return None
    return None
