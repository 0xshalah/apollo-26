"""Immutable values shared by the Apollo-26 AGC domain."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from .errors import AgcErrorCode

if TYPE_CHECKING:
    from .word import AgcWord


class ZeroSign(str, Enum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    NOT_ZERO = "NOT_ZERO"


class Program(str, Enum):
    P00 = "P00"
    P40 = "P40"


class MachineRegister(str, Enum):
    A = "A"
    L = "L"
    Q = "Q"
    Z = "Z"


class DskyState(str, Enum):
    IDLE = "IDLE"
    VERB_ENTRY = "VERB_ENTRY"
    NOUN_ENTRY = "NOUN_ENTRY"
    DATA_ENTRY = "DATA_ENTRY"
    EXECUTING = "EXECUTING"
    OPR_ERR = "OPR_ERR"


class DskyKey(str, Enum):
    VERB = "VERB"
    NOUN = "NOUN"
    DIGIT_0 = "0"
    DIGIT_1 = "1"
    DIGIT_2 = "2"
    DIGIT_3 = "3"
    DIGIT_4 = "4"
    DIGIT_5 = "5"
    DIGIT_6 = "6"
    DIGIT_7 = "7"
    DIGIT_8 = "8"
    DIGIT_9 = "9"
    ZERO = "0"
    ONE = "1"
    TWO = "2"
    THREE = "3"
    FOUR = "4"
    FIVE = "5"
    SIX = "6"
    SEVEN = "7"
    EIGHT = "8"
    NINE = "9"
    PLUS = "+"
    MINUS = "-"
    ENTR = "ENTR"
    PRO = "PRO"
    CLR = "CLR"
    RSET = "RSET"
    KEY_REL = "KEY_REL"

    @property
    def digit(self) -> int | None:
        return int(self.value) if len(self.value) == 1 and self.value.isdigit() else None


class DisplayUnit(str, Enum):
    CENTIDEGREES = "CENTIDEGREES"
    TENTHS_FPS = "TENTHS_FPS"


class EntryKind(str, Enum):
    VERB = "VERB"
    NOUN = "NOUN"
    PROGRAM = "PROGRAM"
    V25_NOUN = "V25_NOUN"
    R1 = "R1"
    R2 = "R2"
    R3 = "R3"


@dataclass(frozen=True, slots=True)
class CompActyTick:
    index: int


@dataclass(frozen=True, slots=True)
class ReceiverActivity:
    active: bool


@dataclass(frozen=True, slots=True)
class DisplayBusy:
    active: bool


@dataclass(frozen=True, slots=True)
class OperationResult:
    success: bool
    revision: int
    error: AgcErrorCode | None = None
    message: str | None = None

    @property
    def code(self) -> AgcErrorCode | None:
        return self.error


@dataclass(frozen=True, slots=True)
class KeyResult:
    """Result of one key attempt.

    ``accepted`` means the key passed KEY REL and timing guards and was consumed.
    A consumed but logically invalid key has ``accepted=True`` and a stable error.
    """

    accepted: bool
    revision: int
    error: AgcErrorCode | None = None
    message: str | None = None

    @property
    def success(self) -> bool:
        return self.accepted and self.error is None

    @property
    def code(self) -> AgcErrorCode | None:
        return self.error

    @property
    def rejected(self) -> bool:
        return not self.success


@dataclass(frozen=True, slots=True)
class PendingEntry:
    kind: EntryKind
    digits: tuple[int, ...] = ()
    sign: ZeroSign | None = None
    staged_raw: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class DisplayValue:
    word: AgcWord
    raw_data: int
    physical_raw: int
    signed_value: int
    zero_sign: ZeroSign
    wire_unit: DisplayUnit


@dataclass(frozen=True, slots=True)
class RegisterValue:
    register: MachineRegister
    word: AgcWord
    raw_data: int
    physical_raw: int


@dataclass(frozen=True, slots=True)
class LampState:
    comp_acty: bool
    uplink_acty: bool
    key_rel: bool
    opr_err: bool


@dataclass(frozen=True, slots=True)
class AgcSnapshot:
    schema_version: int
    subset_id: str
    revision: int
    program: Program
    dsky_state: DskyState
    verb_display: int | None
    noun_display: int | None
    pending_entry: PendingEntry | None
    r1: DisplayValue
    r2: DisplayValue
    r3: DisplayValue
    registers: tuple[RegisterValue, ...]
    lamps: LampState
    next_comp_acty_tick: int | None

    @property
    def prog_display(self) -> int:
        return 0 if self.program is Program.P00 else 40

    def _register_value(self, register: MachineRegister) -> RegisterValue:
        return next(value for value in self.registers if value.register is register)

    @property
    def a(self) -> RegisterValue:
        return self._register_value(MachineRegister.A)

    @property
    def l(self) -> RegisterValue:
        return self._register_value(MachineRegister.L)

    @property
    def q(self) -> RegisterValue:
        return self._register_value(MachineRegister.Q)

    @property
    def z(self) -> RegisterValue:
        return self._register_value(MachineRegister.Z)

    @property
    def comp_acty(self) -> bool:
        return self.lamps.comp_acty

    @property
    def uplink_acty(self) -> bool:
        return self.lamps.uplink_acty

    @property
    def key_rel(self) -> bool:
        return self.lamps.key_rel

    @property
    def opr_err(self) -> bool:
        return self.lamps.opr_err
