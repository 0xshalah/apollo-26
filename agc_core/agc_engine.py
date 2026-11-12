"""Pure deterministic engine for the Apollo-26 AGC/DSKY subset."""

from __future__ import annotations

from collections.abc import Iterable
from typing import NoReturn

from .dsky import MIN_KEY_CADENCE_MS, V25_NOUN, parse_display_word
from .errors import AgcDomainError, AgcErrorCode
from .models import (
    AgcSnapshot,
    CompActyTick,
    DisplayBusy,
    DisplayUnit,
    DisplayValue,
    DskyKey,
    DskyState,
    EntryKind,
    KeyResult,
    LampState,
    MachineRegister,
    OperationResult,
    PendingEntry,
    Program,
    ReceiverActivity,
    RegisterValue,
    ZeroSign,
)
from .programs import FIRST_COMP_ACTY_TICK, SUPPORTED_PROGRAM_DIGITS
from .word import AgcWord

ERASABLE_WORDS = 2048
SCHEMA_VERSION = 1
SUBSET_ID = "apollo26-agc-subset-v1"


class _LogicalFailure(Exception):
    def __init__(self, code: AgcErrorCode, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class AgcEngine:
    """State owner for erasable memory, registers, DSKY, and P00/P40."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        zero = AgcWord(0)
        self._erasable: list[AgcWord] = [zero] * ERASABLE_WORDS
        self._registers: dict[MachineRegister, AgcWord] = {
            register: zero for register in MachineRegister
        }
        self._program = Program.P00
        self._dsky_state = DskyState.IDLE
        self._verb_display: int | None = None
        self._noun_display: int | None = None
        self._pending: PendingEntry | None = None
        self._r: list[AgcWord] = [zero, zero, zero]
        self._comp_acty = False
        self._uplink_acty = False
        self._key_rel = False
        self._opr_err = False
        self._last_accepted_key_ms: int | None = None
        self._next_comp_acty_tick: int | None = None
        self._revision = 0

    @property
    def last_accepted_key_ms(self) -> int | None:
        return self._last_accepted_key_ms

    @property
    def revision(self) -> int:
        return self._revision

    def _check_address(self, address: object) -> int:
        if (
            not isinstance(address, int)
            or isinstance(address, bool)
            or not 0 <= address < ERASABLE_WORDS
        ):
            raise AgcDomainError(
                AgcErrorCode.ADDRESS_RANGE,
                "erasable address must be an integer in 0..2047",
            )
        return address

    @staticmethod
    def _check_word(word: object) -> AgcWord:
        if not isinstance(word, AgcWord):
            raise AgcDomainError(AgcErrorCode.WORD_RANGE, "write value must be an AgcWord")
        return word

    @staticmethod
    def _check_register(register: object) -> MachineRegister:
        if not isinstance(register, MachineRegister):
            raise AgcDomainError(
                AgcErrorCode.REGISTER,
                "register must be MachineRegister.A, L, Q, or Z",
            )
        return register

    def read_memory(self, address: int) -> AgcWord:
        return self._erasable[self._check_address(address)]

    def read_erasable(self, address: int) -> AgcWord:
        return self.read_memory(address)

    def write_memory(self, address: int, word: AgcWord) -> OperationResult:
        checked_address = self._check_address(address)
        checked_word = self._check_word(word)
        if self._erasable[checked_address] != checked_word:
            self._erasable[checked_address] = checked_word
            self._revision += 1
        return OperationResult(True, self._revision)

    def write_erasable(self, address: int, word: AgcWord) -> OperationResult:
        return self.write_memory(address, word)

    def read_register(self, register: MachineRegister) -> AgcWord:
        return self._registers[self._check_register(register)]

    def write_register(self, register: MachineRegister, word: AgcWord) -> OperationResult:
        checked_register = self._check_register(register)
        checked_word = self._check_word(word)
        if self._registers[checked_register] != checked_word:
            self._registers[checked_register] = checked_word
            self._revision += 1
        return OperationResult(True, self._revision)

    def set_receiver_activity(self, event: ReceiverActivity) -> OperationResult:
        if not isinstance(event, ReceiverActivity) or not isinstance(event.active, bool):
            raise TypeError("event must be ReceiverActivity(bool)")
        if self._uplink_acty != event.active:
            self._uplink_acty = event.active
            self._revision += 1
        return OperationResult(True, self._revision)

    def set_display_busy(self, event: DisplayBusy) -> OperationResult:
        if not isinstance(event, DisplayBusy) or not isinstance(event.active, bool):
            raise TypeError("event must be DisplayBusy(bool)")
        if self._key_rel != event.active:
            self._key_rel = event.active
            self._revision += 1
        return OperationResult(True, self._revision)

    def apply_p40_tick(self, tick: CompActyTick) -> OperationResult:
        if (
            not isinstance(tick, CompActyTick)
            or not isinstance(tick.index, int)
            or isinstance(tick.index, bool)
            or self._program is not Program.P40
            or tick.index != self._next_comp_acty_tick
        ):
            return OperationResult(
                False,
                self._revision,
                AgcErrorCode.SCHEDULER_STATE,
                "tick is not the exact pending P40 boundary",
            )
        self._comp_acty = not self._comp_acty
        self._next_comp_acty_tick = tick.index + 1
        self._revision += 1
        return OperationResult(True, self._revision)

    def press_key(self, key: DskyKey, at_ms: int) -> KeyResult:
        if not isinstance(key, DskyKey):
            raise AgcDomainError(
                AgcErrorCode.INVALID_KEY_SEQUENCE,
                "key must be a typed DskyKey",
            )
        if self._key_rel:
            return KeyResult(
                False,
                self._revision,
                AgcErrorCode.KEY_REL_ACTIVE,
                "KEY REL lamp is active",
            )
        if not isinstance(at_ms, int) or isinstance(at_ms, bool) or at_ms < 0:
            return KeyResult(
                False,
                self._revision,
                AgcErrorCode.TIME_REGRESSION,
                "key timestamp must be a nonnegative integer",
            )
        if self._last_accepted_key_ms is not None:
            if at_ms < self._last_accepted_key_ms:
                return KeyResult(
                    False,
                    self._revision,
                    AgcErrorCode.TIME_REGRESSION,
                    "key timestamp regressed",
                )
            if at_ms - self._last_accepted_key_ms < MIN_KEY_CADENCE_MS:
                return KeyResult(
                    False,
                    self._revision,
                    AgcErrorCode.KEY_CADENCE,
                    "accepted keys must be at least 100 ms apart",
                )

        if self._dsky_state is DskyState.OPR_ERR and key is not DskyKey.RSET:
            return KeyResult(
                False,
                self._revision,
                AgcErrorCode.OPR_ERR_LATCHED,
                "OPR ERR is latched; only RSET can clear it",
            )

        before = self._visible_fingerprint()
        try:
            self._dispatch_key(key)
        except _LogicalFailure as failure:
            self._last_accepted_key_ms = at_ms
            self._dsky_state = DskyState.OPR_ERR
            self._opr_err = True
            if self._visible_fingerprint() != before:
                self._revision += 1
            return KeyResult(True, self._revision, failure.code, failure.message)

        self._last_accepted_key_ms = at_ms
        if self._visible_fingerprint() != before:
            self._revision += 1
        return KeyResult(True, self._revision)

    def press_keys(self, events: Iterable[tuple[DskyKey, int]]) -> tuple[KeyResult, ...]:
        """Process keys in order and stop on the first failure or OPR ERR."""

        results: list[KeyResult] = []
        for key, at_ms in events:
            result = self.press_key(key, at_ms)
            results.append(result)
            if not result.success or self._opr_err:
                break
        return tuple(results)

    def _dispatch_key(self, key: DskyKey) -> None:
        if key is DskyKey.RSET:
            self._clear_transient()
            self._opr_err = False
            return
        if key is DskyKey.KEY_REL:
            self._clear_transient()
            return

        state = self._dsky_state
        if state is DskyState.IDLE:
            self._dispatch_idle(key)
        elif state is DskyState.VERB_ENTRY:
            self._dispatch_verb(key)
        elif state is DskyState.NOUN_ENTRY:
            self._dispatch_noun(key)
        elif state is DskyState.DATA_ENTRY:
            self._dispatch_data(key)
        else:
            self._fail(AgcErrorCode.INVALID_KEY_SEQUENCE, "key is invalid in current state")

    def _dispatch_idle(self, key: DskyKey) -> None:
        if key is DskyKey.VERB:
            self._dsky_state = DskyState.VERB_ENTRY
            self._pending = PendingEntry(EntryKind.VERB)
            return
        if key is DskyKey.NOUN and self._pending is not None:
            if self._pending.kind is EntryKind.V25_NOUN:
                self._dsky_state = DskyState.NOUN_ENTRY
                self._pending = PendingEntry(EntryKind.NOUN)
                return
        self._fail(AgcErrorCode.INVALID_KEY_SEQUENCE, "IDLE accepts VERB or pending V25 NOUN")

    def _dispatch_verb(self, key: DskyKey) -> None:
        pending = self._require_pending(EntryKind.VERB)
        digit = key.digit
        if digit is not None:
            if len(pending.digits) >= 2:
                self._fail(AgcErrorCode.INVALID_KEY_SEQUENCE, "verb has exactly two digits")
            self._pending = PendingEntry(EntryKind.VERB, pending.digits + (digit,))
            return
        if key is DskyKey.CLR:
            if not pending.digits:
                self._fail(AgcErrorCode.INVALID_KEY_SEQUENCE, "verb buffer is empty")
            self._pending = PendingEntry(EntryKind.VERB, pending.digits[:-1])
            return
        if key is not DskyKey.ENTR:
            self._fail(AgcErrorCode.INVALID_KEY_SEQUENCE, "invalid key during verb entry")
        if len(pending.digits) != 2:
            self._fail(AgcErrorCode.INVALID_KEY_SEQUENCE, "verb requires two digits")
        verb = pending.digits[0] * 10 + pending.digits[1]
        if verb == 25:
            self._dsky_state = DskyState.IDLE
            self._pending = PendingEntry(EntryKind.V25_NOUN)
        elif verb == 34:
            self._activate_program(Program.P00)
            self._verb_display = 34
            self._dsky_state = DskyState.IDLE
            self._pending = None
        elif verb == 37:
            self._dsky_state = DskyState.DATA_ENTRY
            self._pending = PendingEntry(EntryKind.PROGRAM)
        else:
            self._fail(AgcErrorCode.UNSUPPORTED_VERB, f"verb {verb:02d} is unsupported")

    def _dispatch_noun(self, key: DskyKey) -> None:
        pending = self._require_pending(EntryKind.NOUN)
        digit = key.digit
        if digit is not None:
            if len(pending.digits) >= 2:
                self._fail(AgcErrorCode.INVALID_KEY_SEQUENCE, "noun has exactly two digits")
            self._pending = PendingEntry(EntryKind.NOUN, pending.digits + (digit,))
            return
        if key is DskyKey.CLR:
            if not pending.digits:
                self._fail(AgcErrorCode.INVALID_KEY_SEQUENCE, "noun buffer is empty")
            self._pending = PendingEntry(EntryKind.NOUN, pending.digits[:-1])
            return
        if key is not DskyKey.ENTR:
            self._fail(AgcErrorCode.INVALID_KEY_SEQUENCE, "invalid key during noun entry")
        if len(pending.digits) != 2:
            self._fail(AgcErrorCode.INVALID_KEY_SEQUENCE, "noun requires two digits")
        noun = pending.digits[0] * 10 + pending.digits[1]
        if noun != V25_NOUN:
            self._fail(AgcErrorCode.UNSUPPORTED_NOUN, f"noun {noun:02d} is unsupported")
        self._dsky_state = DskyState.DATA_ENTRY
        self._pending = PendingEntry(EntryKind.R1)

    def _dispatch_data(self, key: DskyKey) -> None:
        if self._pending is None:
            self._fail(AgcErrorCode.INVALID_KEY_SEQUENCE, "missing data entry buffer")
        pending = self._pending
        if pending.kind is EntryKind.PROGRAM:
            self._dispatch_program_data(key, pending)
            return
        if pending.kind not in (EntryKind.R1, EntryKind.R2, EntryKind.R3):
            self._fail(AgcErrorCode.INVALID_KEY_SEQUENCE, "invalid data field")
        self._dispatch_v25_data(key, pending)

    def _dispatch_program_data(self, key: DskyKey, pending: PendingEntry) -> None:
        digit = key.digit
        if digit is not None:
            if len(pending.digits) >= 2:
                self._fail(AgcErrorCode.INVALID_KEY_SEQUENCE, "program has exactly two digits")
            self._pending = PendingEntry(EntryKind.PROGRAM, pending.digits + (digit,))
            return
        if key is DskyKey.CLR:
            if not pending.digits:
                self._fail(AgcErrorCode.INVALID_KEY_SEQUENCE, "program buffer is empty")
            self._pending = PendingEntry(EntryKind.PROGRAM, pending.digits[:-1])
            return
        if key is not DskyKey.ENTR:
            self._fail(AgcErrorCode.INVALID_KEY_SEQUENCE, "V37 requires program digits then ENTR")
        if len(pending.digits) != 2:
            self._fail(AgcErrorCode.INVALID_KEY_SEQUENCE, "program requires two digits")
        program = SUPPORTED_PROGRAM_DIGITS.get(pending.digits)
        if program is None:
            target = pending.digits[0] * 10 + pending.digits[1]
            self._fail(
                AgcErrorCode.UNSUPPORTED_PROGRAM,
                f"program {target:02d} is unsupported",
            )
        self._activate_program(program)
        self._verb_display = 37
        self._noun_display = None
        self._dsky_state = DskyState.IDLE
        self._pending = None

    def _dispatch_v25_data(self, key: DskyKey, pending: PendingEntry) -> None:
        if key in (DskyKey.PLUS, DskyKey.MINUS):
            if pending.sign is not None or pending.digits:
                self._fail(AgcErrorCode.INVALID_KEY_SEQUENCE, "field sign must occur exactly once first")
            sign = ZeroSign.POSITIVE if key is DskyKey.PLUS else ZeroSign.NEGATIVE
            self._pending = PendingEntry(pending.kind, sign=sign, staged_raw=pending.staged_raw)
            return
        digit = key.digit
        if digit is not None:
            if pending.sign is None or len(pending.digits) >= 5:
                self._fail(
                    AgcErrorCode.INVALID_KEY_SEQUENCE,
                    "field requires a sign and at most five digits",
                )
            self._pending = PendingEntry(
                pending.kind,
                pending.digits + (digit,),
                pending.sign,
                pending.staged_raw,
            )
            return
        if key is DskyKey.CLR:
            if pending.digits:
                self._pending = PendingEntry(
                    pending.kind,
                    pending.digits[:-1],
                    pending.sign,
                    pending.staged_raw,
                )
                return
            if pending.sign is not None:
                self._pending = PendingEntry(
                    pending.kind,
                    staged_raw=pending.staged_raw,
                )
                return
            self._fail(AgcErrorCode.INVALID_KEY_SEQUENCE, "data field is empty")
        is_final = pending.kind is EntryKind.R3
        if key is DskyKey.PRO and not is_final:
            self._fail(AgcErrorCode.INVALID_KEY_SEQUENCE, "PRO may terminate only R3")
        if key not in (DskyKey.ENTR, DskyKey.PRO):
            self._fail(AgcErrorCode.INVALID_KEY_SEQUENCE, "invalid key during data entry")
        word = self._parse_pending_word(pending)
        staged = pending.staged_raw + (word.data_raw,)
        if not is_final:
            next_kind = EntryKind.R2 if pending.kind is EntryKind.R1 else EntryKind.R3
            self._pending = PendingEntry(next_kind, staged_raw=staged)
            return
        if len(staged) != 3:
            self._fail(AgcErrorCode.INVALID_KEY_SEQUENCE, "V25 requires three fields")
        self._dsky_state = DskyState.EXECUTING
        new_values = [AgcWord(raw) for raw in staged]
        self._r = new_values
        self._verb_display = 25
        self._noun_display = V25_NOUN
        self._pending = None
        self._dsky_state = DskyState.IDLE

    @staticmethod
    def _parse_pending_word(pending: PendingEntry) -> AgcWord:
        try:
            return parse_display_word(pending.sign, pending.digits)
        except AgcDomainError as error:
            raise _LogicalFailure(error.code, error.message) from error

    def _activate_program(self, program: Program) -> None:
        self._program = program
        if program is Program.P40:
            self._comp_acty = True
            self._next_comp_acty_tick = FIRST_COMP_ACTY_TICK
        else:
            self._comp_acty = False
            self._next_comp_acty_tick = None

    def _clear_transient(self) -> None:
        self._dsky_state = DskyState.IDLE
        self._pending = None

    def _require_pending(self, kind: EntryKind) -> PendingEntry:
        if self._pending is None or self._pending.kind is not kind:
            self._fail(AgcErrorCode.INVALID_KEY_SEQUENCE, "entry buffer does not match state")
        return self._pending

    @staticmethod
    def _fail(code: AgcErrorCode, message: str) -> NoReturn:
        raise _LogicalFailure(code, message)

    @staticmethod
    def _display(word: AgcWord, unit: DisplayUnit) -> DisplayValue:
        return DisplayValue(
            word=word,
            raw_data=word.data_raw,
            physical_raw=word.physical_raw,
            signed_value=word.signed_value,
            zero_sign=word.zero_sign,
            wire_unit=unit,
        )

    def snapshot(self) -> AgcSnapshot:
        registers = tuple(
            RegisterValue(
                register=register,
                word=self._registers[register],
                raw_data=self._registers[register].data_raw,
                physical_raw=self._registers[register].physical_raw,
            )
            for register in MachineRegister
        )
        return AgcSnapshot(
            schema_version=SCHEMA_VERSION,
            subset_id=SUBSET_ID,
            revision=self._revision,
            program=self._program,
            dsky_state=self._dsky_state,
            verb_display=self._verb_display,
            noun_display=self._noun_display,
            pending_entry=self._pending,
            r1=self._display(self._r[0], DisplayUnit.CENTIDEGREES),
            r2=self._display(self._r[1], DisplayUnit.CENTIDEGREES),
            r3=self._display(self._r[2], DisplayUnit.TENTHS_FPS),
            registers=registers,
            lamps=LampState(
                comp_acty=self._comp_acty,
                uplink_acty=self._uplink_acty,
                key_rel=self._key_rel,
                opr_err=self._opr_err,
            ),
            next_comp_acty_tick=self._next_comp_acty_tick,
        )

    def _visible_fingerprint(self) -> tuple[object, ...]:
        return (
            self._program,
            self._dsky_state,
            self._verb_display,
            self._noun_display,
            self._pending,
            tuple(self._r),
            tuple((register, self._registers[register]) for register in MachineRegister),
            self._comp_acty,
            self._uplink_acty,
            self._key_rel,
            self._opr_err,
            self._next_comp_acty_tick,
        )
