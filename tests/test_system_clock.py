"""Real-clock regression for the DSKY key cadence (live run 2026-11-12).

Every other daemon test uses ``ManualClock``. The live Flight Watch run failed
at key 2/29 with KEY_REJECTED because ``asyncio.sleep(0.1)`` on Windows /
Python 3.12 returned after 93-94 ms as measured by ``time.monotonic``
(GetTickCount64, 15.625 ms resolution), and the engine enforces >= 100 ms.
"""

from __future__ import annotations

import asyncio

import pytest

from acoustic.agc_host import AgcHost
from acoustic.clock import SystemClock
from agc_core import MIN_KEY_CADENCE_MS, AgcEngine


def test_system_clock_sleep_never_returns_early() -> None:
    clock = SystemClock()

    async def measure() -> list[int]:
        deltas = []
        for _ in range(12):
            start = clock.monotonic_ms()
            await clock.sleep_ms(25)
            deltas.append(clock.monotonic_ms() - start)
        return deltas

    deltas = asyncio.run(measure())
    assert min(deltas) >= 25, deltas


@pytest.mark.slow
def test_real_clock_v25_n81_sequence_meets_key_cadence() -> None:
    keys = (
        "VERB", "DIGIT_2", "DIGIT_5", "ENTR",
        "NOUN", "DIGIT_8", "DIGIT_1", "ENTR",
        "PLUS", "DIGIT_0", "DIGIT_1", "DIGIT_2", "DIGIT_5", "DIGIT_0", "ENTR",
        "PLUS", "DIGIT_0", "DIGIT_0", "DIGIT_4", "DIGIT_2", "DIGIT_0", "ENTR",
        "PLUS", "DIGIT_0", "DIGIT_3", "DIGIT_1", "DIGIT_2", "DIGIT_0", "ENTR",
    )  # fmt: skip
    host = AgcHost(AgcEngine(), SystemClock(), lambda: None)

    async def run():
        async with host.writer_lock:
            return await host.press_sequence(keys, MIN_KEY_CADENCE_MS)

    outcome = asyncio.run(run())
    assert outcome.error is None
    assert outcome.keys_accepted == len(keys)
    view = host.view()
    assert (view.verb, view.noun) == (25, 81)
    assert (view.r1, view.r2, view.r3) == (1250, 420, 3120)
    assert not view.opr_err
