"""AGC 15-bit one's-complement word and odd parity operations."""

from __future__ import annotations

from dataclasses import dataclass

from .errors import AgcDomainError, AgcErrorCode
from .models import ZeroSign

DATA_MASK = 0x7FFF
SIGN_BIT = 0x4000
PHYSICAL_MASK = 0xFFFF
POSITIVE_ZERO = 0x0000
NEGATIVE_ZERO = 0x7FFF


def _require_plain_int(value: object, upper: int, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= upper:
        raise AgcDomainError(
            AgcErrorCode.WORD_RANGE,
            f"{name} must be an integer in 0x0000..0x{upper:04X}",
        )
    return value


@dataclass(frozen=True, slots=True)
class AgcWord:
    """An immutable parity-valid 15-bit AGC data word."""

    data_raw: int

    def __post_init__(self) -> None:
        _require_plain_int(self.data_raw, DATA_MASK, "data word")

    @classmethod
    def from_data(cls, data_raw: int) -> AgcWord:
        return cls(data_raw)

    @classmethod
    def from_physical(cls, physical_raw: int) -> AgcWord:
        physical = _require_plain_int(physical_raw, PHYSICAL_MASK, "physical word")
        if physical.bit_count() % 2 != 1:
            raise AgcDomainError(
                AgcErrorCode.PARITY,
                "physical word must have odd population parity",
            )
        return cls(physical & DATA_MASK)

    @property
    def raw_data(self) -> int:
        return self.data_raw

    @property
    def raw(self) -> int:
        return self.data_raw

    @property
    def parity_bit(self) -> int:
        return 0 if self.data_raw.bit_count() % 2 == 1 else 1

    @property
    def physical_raw(self) -> int:
        return (self.parity_bit << 15) | self.data_raw

    @property
    def signed_value(self) -> int:
        if self.data_raw == NEGATIVE_ZERO:
            return 0
        if self.data_raw & SIGN_BIT:
            return -(~self.data_raw & DATA_MASK)
        return self.data_raw

    def to_int(self) -> int:
        return self.signed_value

    @property
    def zero_sign(self) -> ZeroSign:
        if self.data_raw == POSITIVE_ZERO:
            return ZeroSign.POSITIVE
        if self.data_raw == NEGATIVE_ZERO:
            return ZeroSign.NEGATIVE
        return ZeroSign.NOT_ZERO

    def negate(self) -> AgcWord:
        return AgcWord((~self.data_raw) & DATA_MASK)

    def add(self, other: AgcWord) -> AddResult:
        if not isinstance(other, AgcWord):
            raise AgcDomainError(AgcErrorCode.WORD_RANGE, "operand must be an AgcWord")
        folded = self.data_raw + other.data_raw
        while folded > DATA_MASK:
            folded = (folded & DATA_MASK) + (folded >> 15)
        result = AgcWord(folded)
        left = self.signed_value
        right = other.signed_value
        result_value = result.signed_value
        overflow = (
            left != 0
            and right != 0
            and result_value != 0
            and (left < 0) == (right < 0)
            and (result_value < 0) != (left < 0)
        )
        return AddResult(result, overflow)

    def __neg__(self) -> AgcWord:
        return self.negate()

    def __add__(self, other: AgcWord) -> AddResult:
        return self.add(other)


@dataclass(frozen=True, slots=True)
class AddResult:
    word: AgcWord
    overflow: bool


def word_from_signed(value: int, zero_sign: ZeroSign = ZeroSign.POSITIVE) -> AgcWord:
    """Create a word from a bounded integer while preserving an explicit zero sign."""

    if not isinstance(value, int) or isinstance(value, bool) or not -16383 <= value <= 16383:
        raise AgcDomainError(
            AgcErrorCode.DISPLAY_RANGE,
            "signed word value must be an integer in -16383..16383",
        )
    if value == 0:
        if zero_sign is ZeroSign.POSITIVE:
            return AgcWord(POSITIVE_ZERO)
        if zero_sign is ZeroSign.NEGATIVE:
            return AgcWord(NEGATIVE_ZERO)
        raise AgcDomainError(
            AgcErrorCode.DISPLAY_RANGE,
            "zero requires POSITIVE or NEGATIVE zero sign",
        )
    return AgcWord(value if value > 0 else (~(-value)) & DATA_MASK)


def negate(word: AgcWord) -> AgcWord:
    return word.negate()


def add(left: AgcWord, right: AgcWord) -> AddResult:
    return left.add(right)
