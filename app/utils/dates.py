"""Shared date-parsing helpers used across scrapers."""

import datetime


def parse_date(s: str | None) -> datetime.datetime | None:
    """Parse a date string in common US/EU formats. Handles ``YYYY-MM`` too."""
    if not s:
        return None
    s = s.strip()[:10]
    # Handle "2026-07" (year-month only) → first of month
    if len(s) == 7 and s[4] == "-":
        s = f"{s}-01"
    for fmt in ("%Y-%m-%d", "%B %d %Y", "%b %d %Y", "%B %Y"):
        try:
            return datetime.datetime.strptime(s.replace(",", ""), fmt)
        except ValueError:
            continue
    return None
