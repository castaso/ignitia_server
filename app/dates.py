"""Date parsing helpers.

The client sends date query params as `dd-MMM-yyyy` (e.g. 05-Aug-2026) and
`date_time` on check-in as `yyyy-MM-dd`. Parse all reasonable forms.
"""

from datetime import datetime

_FORMATS = (
    "%d-%b-%Y",  # 05-Aug-2026 (client query params)
    "%d-%b-%Y %H:%M:%S",
    "%Y-%m-%d",  # 2026-08-05 (client check-in body)
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
    "%d/%m/%Y",
)


def parse_datetime(value: str | None):
    """Return a datetime or None for any supported format."""
    if not value:
        return None
    value = value.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    for fmt in _FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    try:
        from datetime import datetime as _dt

        return _dt.fromisoformat(value)
    except ValueError:
        return None


def parse_date(value: str | None):
    """Return a datetime at midnight or None."""
    dt = parse_datetime(value)
    if dt is None:
        return None
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def date_key(value: str | None) -> str | None:
    """Normalise any supported input to `yyyy-MM-dd`."""
    dt = parse_date(value)
    return dt.strftime("%Y-%m-%d") if dt else None


def datetime_key(dt: datetime) -> str:
    """Format a datetime as the client expects: yyyy-MM-ddTHH:mm:ss."""
    return dt.strftime("%Y-%m-%dT%H:%M:%S")
