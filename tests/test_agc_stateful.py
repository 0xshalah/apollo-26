from __future__ import annotations

from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, precondition, rule

from agc_core import (
    AgcEngine,
    AgcErrorCode,
    AgcWord,
    CompActyTick,
    DisplayBusy,
    DskyKey,
    DskyState,
    MachineRegister,
    Program,
    ReceiverActivity,
    ZeroSign,
    word_from_signed,
)

_DIGITS = tuple(
    (
        DskyKey.DIGIT_0,
        DskyKey.DIGIT_1,
        DskyKey.DIGIT_2,
        DskyKey.DIGIT_3,
        DskyKey.DIGIT_4,
        DskyKey.DIGIT_5,
        DskyKey.DIGIT_6,
        DskyKey.DIGIT_7,
        DskyKey.DIGIT_8,
        DskyKey.DIGIT_9,
    )
)


def _number_keys(value: int) -> tuple[DskyKey, ...]:
    sign = DskyKey.MINUS if value < 0 else DskyKey.PLUS
    return (sign, *(_DIGITS[int(char)] for char in str(abs(value))), DskyKey.ENTR)


class AgcReferenceMachine(RuleBasedStateMachine):
    """Independent public-boundary model for stable command states and guards."""

    def __init__(self) -> None:
        super().__init__()
        self.engine = AgcEngine()
        self.now = 0
        self.program = Program.P00
        self.raw_values = (0, 0, 0)
        self.comp_acty = False
        self.uplink_acty = False
        self.key_rel = False
        self.opr_err = False
        self.next_tick: int | None = None
        self.revision = 0
        self.verb: int | None = None
        self.noun: int | None = None
        self.memory: dict[int, int] = {}
        self.registers = {register: 0 for register in MachineRegister}

    def _send(self, keys: tuple[DskyKey, ...]) -> None:
        for key in keys:
            before_revision = self.engine.snapshot().revision
            result = self.engine.press_key(key, self.now)
            assert result.success
            assert result.revision == before_revision + 1
            self.revision += 1
            self.now += 100

    @rule(active=st.booleans())
    def set_key_rel(self, active: bool) -> None:
        before = self.revision
        result = self.engine.set_display_busy(DisplayBusy(active))
        if active != self.key_rel:
            self.revision += 1
        self.key_rel = active
        assert result.revision == self.revision
        assert self.revision - before in (0, 1)

    @rule(active=st.booleans())
    def set_uplink(self, active: bool) -> None:
        result = self.engine.set_receiver_activity(ReceiverActivity(active))
        if active != self.uplink_acty:
            self.revision += 1
        self.uplink_acty = active
        assert result.revision == self.revision

    @rule(address=st.integers(min_value=0, max_value=2047), raw=st.integers(0, 0x7FFF))
    def write_memory(self, address: int, raw: int) -> None:
        previous = self.memory.get(address, 0)
        result = self.engine.write_memory(address, AgcWord(raw))
        if previous != raw:
            self.revision += 1
        self.memory[address] = raw
        assert result.revision == self.revision
        assert self.engine.read_memory(address).data_raw == raw

    @rule(
        register=st.sampled_from(tuple(MachineRegister)),
        raw=st.integers(min_value=0, max_value=0x7FFF),
    )
    def write_register(self, register: MachineRegister, raw: int) -> None:
        if self.registers[register] != raw:
            self.revision += 1
        self.registers[register] = raw
        result = self.engine.write_register(register, AgcWord(raw))
        assert result.revision == self.revision

    @precondition(lambda self: not self.key_rel and not self.opr_err)
    @rule(program_number=st.sampled_from((0, 40)))
    def canonical_v37(self, program_number: int) -> None:
        target = program_number
        keys = (
            DskyKey.VERB,
            DskyKey.DIGIT_3,
            DskyKey.DIGIT_7,
            DskyKey.ENTR,
            _DIGITS[target // 10],
            _DIGITS[target % 10],
            DskyKey.ENTR,
        )
        self._send(keys)
        self.program = Program.P40 if target == 40 else Program.P00
        self.comp_acty = target == 40
        self.next_tick = 1 if target == 40 else None
        self.verb = 37
        self.noun = None

    @precondition(lambda self: not self.key_rel and not self.opr_err)
    @rule(
        r1=st.integers(min_value=-16383, max_value=16383),
        r2=st.integers(min_value=-16383, max_value=16383),
        r3=st.integers(min_value=-16383, max_value=16383),
    )
    def canonical_v25(self, r1: int, r2: int, r3: int) -> None:
        keys = (
            DskyKey.VERB,
            DskyKey.DIGIT_2,
            DskyKey.DIGIT_5,
            DskyKey.ENTR,
            DskyKey.NOUN,
            DskyKey.DIGIT_8,
            DskyKey.DIGIT_1,
            DskyKey.ENTR,
            *_number_keys(r1),
            *_number_keys(r2),
            *_number_keys(r3),
        )
        self._send(keys)
        self.raw_values = tuple(word_from_signed(value).data_raw for value in (r1, r2, r3))
        self.verb = 25
        self.noun = 81

    @precondition(lambda self: not self.key_rel and not self.opr_err)
    @rule()
    def canonical_v34(self) -> None:
        self._send(
            (DskyKey.VERB, DskyKey.DIGIT_3, DskyKey.DIGIT_4, DskyKey.ENTR)
        )
        self.program = Program.P00
        self.comp_acty = False
        self.next_tick = None
        self.verb = 34

    @precondition(lambda self: not self.key_rel and not self.opr_err)
    @rule()
    def invalid_idle_digit_latches_opr_err(self) -> None:
        result = self.engine.press_key(DskyKey.DIGIT_9, self.now)
        assert result.accepted
        assert result.code is AgcErrorCode.INVALID_KEY_SEQUENCE
        self.now += 100
        self.opr_err = True
        self.revision += 1

    @precondition(lambda self: self.opr_err and not self.key_rel)
    @rule()
    def rset_recovers_opr_err(self) -> None:
        result = self.engine.press_key(DskyKey.RSET, self.now)
        assert result.success
        self.now += 100
        self.opr_err = False
        self.revision += 1

    @precondition(lambda self: self.opr_err and not self.key_rel)
    @rule(key=st.sampled_from(tuple(key for key in DskyKey if key is not DskyKey.RSET)))
    def opr_err_blocks_non_rset(self, key: DskyKey) -> None:
        before = self.engine.snapshot()
        result = self.engine.press_key(key, self.now)
        assert result.code is AgcErrorCode.OPR_ERR_LATCHED
        assert self.engine.snapshot() == before

    @precondition(lambda self: self.key_rel)
    @rule(key=st.sampled_from(tuple(DskyKey)), timestamp=st.integers(min_value=-10, max_value=10000))
    def key_rel_blocks_every_key(self, key: DskyKey, timestamp: int) -> None:
        before = self.engine.snapshot()
        anchor = self.engine.last_accepted_key_ms
        result = self.engine.press_key(key, timestamp)
        assert result.code is AgcErrorCode.KEY_REL_ACTIVE
        assert self.engine.snapshot() == before
        assert self.engine.last_accepted_key_ms == anchor

    @precondition(lambda self: self.now >= 100 and not self.key_rel)
    @rule(key=st.sampled_from(tuple(DskyKey)))
    def cadence_rejection_preserves_state(self, key: DskyKey) -> None:
        before = self.engine.snapshot()
        anchor = self.engine.last_accepted_key_ms
        result = self.engine.press_key(key, self.now - 1)
        assert result.code is AgcErrorCode.KEY_CADENCE
        assert self.engine.snapshot() == before
        assert self.engine.last_accepted_key_ms == anchor

    @precondition(lambda self: self.program is Program.P40 and self.next_tick is not None)
    @rule()
    def exact_tick_toggles_comp_acty(self) -> None:
        assert self.next_tick is not None
        result = self.engine.apply_p40_tick(CompActyTick(self.next_tick))
        assert result.success
        self.next_tick += 1
        self.comp_acty = not self.comp_acty
        self.revision += 1

    @rule(index=st.integers(min_value=-2, max_value=20))
    def invalid_tick_preserves_state(self, index: int) -> None:
        if self.program is Program.P40 and index == self.next_tick:
            return
        before = self.engine.snapshot()
        result = self.engine.apply_p40_tick(CompActyTick(index))
        assert result.code is AgcErrorCode.SCHEDULER_STATE
        assert self.engine.snapshot() == before

    @invariant()
    def agc_prop_2_8_9_snapshot_matches_reference_model(self) -> None:
        snapshot = self.engine.snapshot()
        assert snapshot.revision == self.revision
        assert snapshot.program is self.program
        assert snapshot.dsky_state is (DskyState.OPR_ERR if self.opr_err else DskyState.IDLE)
        assert snapshot.pending_entry is None
        assert (snapshot.r1.raw_data, snapshot.r2.raw_data, snapshot.r3.raw_data) == self.raw_values
        assert snapshot.verb_display == self.verb
        assert snapshot.noun_display == self.noun
        assert snapshot.lamps.comp_acty is self.comp_acty
        assert snapshot.lamps.uplink_acty is self.uplink_acty
        assert snapshot.lamps.key_rel is self.key_rel
        assert snapshot.lamps.opr_err is self.opr_err
        assert snapshot.next_comp_acty_tick == self.next_tick
        assert {item.register: item.raw_data for item in snapshot.registers} == self.registers
        assert self.engine.snapshot() == snapshot
        if self.program is Program.P00:
            assert not snapshot.lamps.comp_acty
            assert snapshot.next_comp_acty_tick is None
        for raw, display in zip(self.raw_values, (snapshot.r1, snapshot.r2, snapshot.r3), strict=True):
            expected_zero = (
                ZeroSign.POSITIVE
                if raw == 0
                else ZeroSign.NEGATIVE
                if raw == 0x7FFF
                else ZeroSign.NOT_ZERO
            )
            assert display.zero_sign is expected_zero


TestAgcStateful = AgcReferenceMachine.TestCase
