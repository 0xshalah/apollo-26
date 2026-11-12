"""Injected clock boundary for the daemon (wall time, monotonic ms, sleeping)."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def now_utc(self) -> datetime: ...

    def monotonic_ms(self) -> int: ...

    async def sleep_ms(self, milliseconds: int) -> None:
        """Return only after ``monotonic_ms()`` has advanced by at least ``milliseconds``."""
        ...


class SystemClock:
    """Production clock adapter.

    ``monotonic_ms`` uses ``time.perf_counter_ns`` (monotonic, high resolution).
    On Windows with Python 3.12, ``time.monotonic`` is ``GetTickCount64`` with
    15.625 ms resolution, and ``asyncio.sleep`` can return early by up to one
    tick; that broke the 100 ms DSKY key cadence in a live run. ``sleep_ms``
    therefore re-sleeps until the deadline has passed on this clock.
    """

    def now_utc(self) -> datetime:
        return datetime.now(UTC)

    def monotonic_ms(self) -> int:
        return time.perf_counter_ns() // 1_000_000

    async def sleep_ms(self, milliseconds: int) -> None:
        deadline = self.monotonic_ms() + max(0, milliseconds)
        while (remaining := deadline - self.monotonic_ms()) > 0:
            await asyncio.sleep(remaining / 1000.0)


class ManualClock:
    """Deterministic clock: time only moves through ``advance_ms`` or ``sleep_ms``.

    ``sleep_ms`` advances virtual time immediately and yields to the event loop,
    which makes 100 ms DSKY key cadence testable without real waiting.
    """

    def __init__(self, start: datetime | None = None) -> None:
        self._start = start or datetime(2026, 11, 20, 12, 0, 0, tzinfo=UTC)
        self._elapsed_ms = 0

    def now_utc(self) -> datetime:
        return self._start + timedelta(milliseconds=self._elapsed_ms)

    def monotonic_ms(self) -> int:
        return self._elapsed_ms

    def advance_ms(self, milliseconds: int) -> None:
        if milliseconds < 0:
            raise ValueError("ManualClock cannot move backwards")
        self._elapsed_ms += milliseconds

    async def sleep_ms(self, milliseconds: int) -> None:
        self.advance_ms(max(0, milliseconds))
        await asyncio.sleep(0)

    # mcp_server.clock.Clock compatibility (shared fake in cross-process tests).
    def now(self) -> datetime:
        return self.now_utc()


def format_timestamp(moment: datetime) -> str:
    """RFC 3339 UTC timestamp with millisecond precision."""

    utc = moment.astimezone(UTC)
    return utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc.microsecond // 1000:03d}Z"


def parse_timestamp(text: str) -> datetime:
    value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("timestamp must carry a UTC offset")
    return value.astimezone(UTC)
