"""Injected wall clock for the MCP bridge."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class FixedStepClock:
    """Deterministic test clock; time moves only via ``advance_ms``."""

    def __init__(self, start: datetime | None = None) -> None:
        self._now = start or datetime(2026, 11, 20, 12, 0, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self._now

    def advance_ms(self, milliseconds: int) -> None:
        if milliseconds < 0:
            raise ValueError("clock cannot move backwards")
        self._now += timedelta(milliseconds=milliseconds)


def format_timestamp(moment: datetime) -> str:
    utc = moment.astimezone(UTC)
    return utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc.microsecond // 1000:03d}Z"


def parse_timestamp(text: str) -> datetime:
    value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("timestamp must carry a UTC offset")
    return value.astimezone(UTC)
