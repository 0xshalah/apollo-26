"""Pure helpers for DSKY entry fields.

The mutable transition owner is :class:`agc_core.agc_engine.AgcEngine`; this module
keeps field parsing independent and deterministic.
"""

from __future__ import annotations

from .errors import AgcDomainError, AgcErrorCode
from .models import DisplayUnit, ZeroSign
from .word import AgcWord, word_from_signed

V25_NOUN = 81
MIN_KEY_CADENCE_MS = 100


def parse_display_word(sign: ZeroSign | None, digits: tuple[int, ...]) -> AgcWord:
    """Parse one explicitly signed DSKY field without floating point."""

    if sign not in (ZeroSign.POSITIVE, ZeroSign.NEGATIVE) or not 1 <= len(digits) <= 5:
        raise AgcDomainError(
            AgcErrorCode.INVALID_KEY_SEQUENCE,
            "display field requires one sign and one to five digits",
        )
    magnitude = 0
    for digit in digits:
        if not 0 <= digit <= 9:
            raise AgcDomainError(AgcErrorCode.INVALID_KEY_SEQUENCE, "invalid decimal digit")
        magnitude = magnitude * 10 + digit
    if magnitude > 16383:
        raise AgcDomainError(
            AgcErrorCode.DISPLAY_RANGE,
            "display magnitude exceeds 16383",
        )
    value = -magnitude if sign is ZeroSign.NEGATIVE else magnitude
    return word_from_signed(value, sign if magnitude == 0 else ZeroSign.NOT_ZERO)


def unit_for_register(index: int) -> DisplayUnit:
    if index in (1, 2):
        return DisplayUnit.CENTIDEGREES
    if index == 3:
        return DisplayUnit.TENTHS_FPS
    raise AgcDomainError(AgcErrorCode.REGISTER, "display register must be R1, R2, or R3")
