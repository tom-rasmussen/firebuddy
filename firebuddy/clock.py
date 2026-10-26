from datetime import datetime, timedelta, timezone

_override: datetime | None = None


def now() -> datetime:
    if _override is not None:
        return _override
    return datetime.now(timezone.utc)


def set_override(dt: datetime | None) -> None:
    """Test/sim hook: freeze or advance the clock. Pass None to resume real time."""
    global _override
    _override = dt


def advance(seconds: float) -> datetime:
    global _override
    base = _override if _override is not None else datetime.now(timezone.utc)
    _override = base + timedelta(seconds=seconds)
    return _override
