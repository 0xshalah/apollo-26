from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from hypothesis import given
from hypothesis import strategies as st

from agc_core import (
    ERASABLE_WORDS,
    AgcDomainError,
    AgcEngine,
    AgcErrorCode,
    AgcWord,
    MachineRegister,
)


def test_agc_req_4_reset_has_exactly_2048_positive_zero_words() -> None:
    engine = AgcEngine()
    assert ERASABLE_WORDS == 2048
    assert all(engine.read_memory(address).data_raw == 0 for address in range(ERASABLE_WORDS))
    assert all(engine.read_register(register).data_raw == 0 for register in MachineRegister)


@given(
    address=st.integers(min_value=0, max_value=2047),
    raw=st.integers(min_value=0, max_value=0x7FFF),
)
def test_agc_prop_1_memory_round_trip(address: int, raw: int) -> None:
    engine = AgcEngine()
    word = AgcWord(raw)
    result = engine.write_memory(address, word)
    assert result.success
    assert engine.read_memory(address) == word
    assert engine.read_memory(address).physical_raw == word.physical_raw


@given(
    register=st.sampled_from(tuple(MachineRegister)),
    raw=st.integers(min_value=0, max_value=0x7FFF),
)
def test_agc_prop_1_register_round_trip(register: MachineRegister, raw: int) -> None:
    engine = AgcEngine()
    word = AgcWord(raw)
    engine.write_register(register, word)
    assert engine.read_register(register) == word


@pytest.mark.parametrize("address", [-1, 2048, True])
def test_agc_req_3_invalid_address_preserves_state(address: int) -> None:
    engine = AgcEngine()
    engine.write_memory(0, AgcWord(123))
    before_snapshot = engine.snapshot()
    before_word = engine.read_memory(0)
    with pytest.raises(AgcDomainError) as raised:
        engine.write_memory(address, AgcWord(456))
    assert raised.value.code is AgcErrorCode.ADDRESS_RANGE
    assert engine.snapshot() == before_snapshot
    assert engine.read_memory(0) == before_word


def test_agc_req_3_invalid_register_preserves_state() -> None:
    engine = AgcEngine()
    before = engine.snapshot()
    with pytest.raises(AgcDomainError) as raised:
        engine.write_register("A", AgcWord(1))  # type: ignore[arg-type]
    assert raised.value.code is AgcErrorCode.REGISTER
    assert engine.snapshot() == before


def test_agc_req_14_snapshot_and_nested_values_are_immutable() -> None:
    snapshot = AgcEngine().snapshot()
    with pytest.raises(FrozenInstanceError):
        snapshot.revision = 4  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        snapshot.lamps.comp_acty = True  # type: ignore[misc]


def test_agc_req_15_stable_error_code_set() -> None:
    assert {code.value for code in AgcErrorCode} == {
        "PARITY",
        "WORD_RANGE",
        "ADDRESS_RANGE",
        "REGISTER",
        "KEY_REL_ACTIVE",
        "KEY_CADENCE",
        "TIME_REGRESSION",
        "INVALID_KEY_SEQUENCE",
        "OPR_ERR_LATCHED",
        "UNSUPPORTED_VERB",
        "UNSUPPORTED_NOUN",
        "UNSUPPORTED_PROGRAM",
        "DISPLAY_RANGE",
        "SCHEDULER_STATE",
    }
