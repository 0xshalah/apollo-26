"""Program constants for the simplified Apollo-26 AGC subset."""

from __future__ import annotations

from .models import Program

COMP_ACTY_PERIOD_MS = 500
FIRST_COMP_ACTY_TICK = 1
SUPPORTED_PROGRAM_DIGITS: dict[tuple[int, int], Program] = {
    (0, 0): Program.P00,
    (4, 0): Program.P40,
}
