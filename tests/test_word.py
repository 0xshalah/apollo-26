from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agc_core import (
    NEGATIVE_ZERO,
    POSITIVE_ZERO,
    AgcDomainError,
    AgcErrorCode,
    AgcWord,
    ZeroSign,
    add,
    word_from_signed,
)

RAW_WORDS = st.integers(min_value=0, max_value=0x7FFF)


def _oracle_add(left: int, right: int) -> tuple[int, bool]:
    folded = left + right
    while folded > 0x7FFF:
        folded = (folded & 0x7FFF) + (folded >> 15)

    def signed(raw: int) -> int:
        if raw == 0x7FFF:
            return 0
        return -(~raw & 0x7FFF) if raw & 0x4000 else raw

    x_value, y_value, result_value = signed(left), signed(right), signed(folded)
    overflow = (
        x_value != 0
        and y_value != 0
        and result_value != 0
        and (x_value < 0) == (y_value < 0)
        and (result_value < 0) != (x_value < 0)
    )
    return folded, overflow


def _assert_p8_a(raw: int) -> None:
    word = AgcWord.from_data(raw)
    assert word.physical_raw.bit_count() % 2 == 1
    assert AgcWord.from_physical(word.physical_raw) == word


def _assert_p8_b(raw: int) -> None:
    word = AgcWord(raw)
    assert word.negate().negate() == word
    assert AgcWord(POSITIVE_ZERO).negate().data_raw == NEGATIVE_ZERO
    assert AgcWord(NEGATIVE_ZERO).negate().data_raw == POSITIVE_ZERO
    expected = (
        ZeroSign.POSITIVE
        if raw == POSITIVE_ZERO
        else ZeroSign.NEGATIVE
        if raw == NEGATIVE_ZERO
        else ZeroSign.NOT_ZERO
    )
    assert word.zero_sign is expected


def _assert_p8_c(raw: int) -> None:
    word = AgcWord(raw)
    assert add(word, word.negate()).word.data_raw == NEGATIVE_ZERO


def _assert_p8_d(left: int, right: int) -> None:
    xy = add(AgcWord(left), AgcWord(right))
    yx = add(AgcWord(right), AgcWord(left))
    expected_raw, expected_overflow = _oracle_add(left, right)
    assert xy == yx
    assert xy.word.data_raw == expected_raw
    assert xy.word.physical_raw.bit_count() % 2 == 1
    assert xy.overflow is expected_overflow


@given(RAW_WORDS)
def test_p8_a_valid_representation_and_parity(raw: int) -> None:
    _assert_p8_a(raw)


@given(RAW_WORDS)
def test_p8_b_negation_and_signed_zeros(raw: int) -> None:
    _assert_p8_b(raw)


@given(RAW_WORDS)
def test_p8_c_additive_inverse_is_negative_zero(raw: int) -> None:
    _assert_p8_c(raw)


@given(RAW_WORDS, RAW_WORDS)
def test_p8_d_commutativity_and_overflow_oracle(left: int, right: int) -> None:
    _assert_p8_d(left, right)


@pytest.mark.slow
@settings(max_examples=10_000, deadline=None)
@given(RAW_WORDS)
def test_p8_a_full_10000_valid_representation(raw: int) -> None:
    _assert_p8_a(raw)


@pytest.mark.slow
@settings(max_examples=10_000, deadline=None)
@given(RAW_WORDS)
def test_p8_b_full_10000_negation(raw: int) -> None:
    _assert_p8_b(raw)


@pytest.mark.slow
@settings(max_examples=10_000, deadline=None)
@given(RAW_WORDS)
def test_p8_c_full_10000_additive_inverse(raw: int) -> None:
    _assert_p8_c(raw)


@pytest.mark.slow
@settings(max_examples=10_000, deadline=None)
@given(RAW_WORDS, RAW_WORDS)
def test_p8_d_full_10000_commutativity(left: int, right: int) -> None:
    _assert_p8_d(left, right)


def test_agc_req_1_exhaustive_odd_parity_and_round_trip() -> None:
    for raw in range(0x8000):
        _assert_p8_a(raw)


@pytest.mark.parametrize("raw", [-1, 0x8000, True])
def test_agc_req_1_rejects_data_outside_15_bits(raw: int) -> None:
    with pytest.raises(AgcDomainError) as raised:
        AgcWord(raw)
    assert raised.value.code is AgcErrorCode.WORD_RANGE


@pytest.mark.parametrize("physical", [-1, 0x10000, True])
def test_agc_req_1_rejects_physical_range(physical: int) -> None:
    with pytest.raises(AgcDomainError) as raised:
        AgcWord.from_physical(physical)
    assert raised.value.code is AgcErrorCode.WORD_RANGE


def test_agc_req_1_rejects_even_physical_parity() -> None:
    with pytest.raises(AgcDomainError) as raised:
        AgcWord.from_physical(0)
    assert raised.value.code is AgcErrorCode.PARITY


@pytest.mark.parametrize(
    ("value", "zero_sign", "raw"),
    [
        (0, ZeroSign.POSITIVE, 0x0000),
        (0, ZeroSign.NEGATIVE, 0x7FFF),
        (1, ZeroSign.NOT_ZERO, 0x0001),
        (16383, ZeroSign.NOT_ZERO, 0x3FFF),
        (-1, ZeroSign.NOT_ZERO, 0x7FFE),
        (-16383, ZeroSign.NOT_ZERO, 0x4000),
    ],
)
def test_agc_req_2_signed_conversion_boundaries(
    value: int, zero_sign: ZeroSign, raw: int
) -> None:
    word = word_from_signed(value, zero_sign)
    assert word.data_raw == raw
    assert word.signed_value == value


@pytest.mark.parametrize("value", [-16384, 16384])
def test_agc_req_12_display_range_is_not_truncated(value: int) -> None:
    with pytest.raises(AgcDomainError) as raised:
        word_from_signed(value)
    assert raised.value.code is AgcErrorCode.DISPLAY_RANGE


def test_agc_req_2_end_around_carry_and_overflow_examples() -> None:
    folded = add(AgcWord(0x7FFE), AgcWord(0x0002))
    assert folded.word.data_raw == 0x0001
    assert not folded.overflow
    assert add(AgcWord(0x3FFF), AgcWord(1)).overflow
    assert add(AgcWord(0x4000), AgcWord(0x7FFE)).overflow
    assert not add(AgcWord(1), AgcWord(0x7FFE)).overflow
