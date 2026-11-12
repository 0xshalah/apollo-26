"""Stable domain errors for the pure Apollo-26 AGC subset."""

from __future__ import annotations

from enum import Enum
from typing import Final


class AgcErrorCode(str, Enum):
    """Machine-readable failure codes exposed by the AGC core."""

    PARITY = "PARITY"
    WORD_RANGE = "WORD_RANGE"
    ADDRESS_RANGE = "ADDRESS_RANGE"
    REGISTER = "REGISTER"
    KEY_REL_ACTIVE = "KEY_REL_ACTIVE"
    KEY_CADENCE = "KEY_CADENCE"
    TIME_REGRESSION = "TIME_REGRESSION"
    INVALID_KEY_SEQUENCE = "INVALID_KEY_SEQUENCE"
    OPR_ERR_LATCHED = "OPR_ERR_LATCHED"
    UNSUPPORTED_VERB = "UNSUPPORTED_VERB"
    UNSUPPORTED_NOUN = "UNSUPPORTED_NOUN"
    UNSUPPORTED_PROGRAM = "UNSUPPORTED_PROGRAM"
    DISPLAY_RANGE = "DISPLAY_RANGE"
    SCHEDULER_STATE = "SCHEDULER_STATE"


class AgcDomainError(ValueError):
    """Typed exception for invalid values at a public domain boundary."""

    def __init__(self, code: AgcErrorCode, message: str) -> None:
        self.code: Final[AgcErrorCode] = code
        self.message: Final[str] = message
        super().__init__(f"{code.value}: {message}")
