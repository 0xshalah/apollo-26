from __future__ import annotations

from collections.abc import Iterable

from agc_core import (
    AgcEngine,
    AgcErrorCode,
    CompActyTick,
    DisplayUnit,
    DskyKey,
    Program,
    ZeroSign,
    word_from_signed,
)

DIGITS = {
    0: DskyKey.DIGIT_0,
    1: DskyKey.DIGIT_1,
    2: DskyKey.DIGIT_2,
    3: DskyKey.DIGIT_3,
    4: DskyKey.DIGIT_4,
    5: DskyKey.DIGIT_5,
    6: DskyKey.DIGIT_6,
    7: DskyKey.DIGIT_7,
    8: DskyKey.DIGIT_8,
    9: DskyKey.DIGIT_9,
}


def _send(engine: AgcEngine, keys: Iterable[DskyKey], start: int = 0) -> int:
    at_ms = start
    for key in keys:
        result = engine.press_key(key, at_ms)
        assert result.success, result
        at_ms += 100
    return at_ms


def _v37(program: int) -> tuple[DskyKey, ...]:
    return (
        DskyKey.VERB,
        DskyKey.DIGIT_3,
        DskyKey.DIGIT_7,
        DskyKey.ENTR,
        DIGITS[program // 10],
        DIGITS[program % 10],
        DskyKey.ENTR,
    )


def _field(value: int, negative_zero: bool = False) -> tuple[DskyKey, ...]:
    sign = DskyKey.MINUS if value < 0 or negative_zero else DskyKey.PLUS
    digits = tuple(DIGITS[int(character)] for character in str(abs(value)))
    return (sign, *digits, DskyKey.ENTR)


def _v25(r1: int, r2: int, r3: int, *, r2_negative_zero: bool = False) -> tuple[DskyKey, ...]:
    return (
        DskyKey.VERB,
        DskyKey.DIGIT_2,
        DskyKey.DIGIT_5,
        DskyKey.ENTR,
        DskyKey.NOUN,
        DskyKey.DIGIT_8,
        DskyKey.DIGIT_1,
        DskyKey.ENTR,
        *_field(r1),
        *_field(r2, r2_negative_zero),
        *_field(r3),
    )


def test_agc_prop_6_canonical_v37_activates_p40() -> None:
    engine = AgcEngine()
    _send(engine, _v37(40))
    snapshot = engine.snapshot()
    assert snapshot.program is Program.P40
    assert snapshot.verb_display == 37
    assert snapshot.prog_display == 40
    assert snapshot.lamps.comp_acty
    assert snapshot.next_comp_acty_tick == 1


def test_agc_req_8_canonical_v37_to_p00_preserves_display_values() -> None:
    engine = AgcEngine()
    at_ms = _send(engine, _v25(123, -456, 789))
    before = (engine.snapshot().r1, engine.snapshot().r2, engine.snapshot().r3)
    _send(engine, _v37(0), at_ms)
    snapshot = engine.snapshot()
    assert snapshot.program is Program.P00
    assert (snapshot.r1, snapshot.r2, snapshot.r3) == before
    assert not snapshot.lamps.comp_acty


def test_agc_req_8_v37_noun_deviation_preserves_program() -> None:
    engine = AgcEngine()
    at_ms = _send(engine, _v37(40))
    prefix = (
        DskyKey.VERB,
        DskyKey.DIGIT_3,
        DskyKey.DIGIT_7,
        DskyKey.ENTR,
    )
    at_ms = _send(engine, prefix, at_ms)
    result = engine.press_key(DskyKey.NOUN, at_ms)
    assert result.code is AgcErrorCode.INVALID_KEY_SEQUENCE
    assert engine.snapshot().program is Program.P40


def test_agc_req_8_unsupported_v37_target_preserves_program() -> None:
    engine = AgcEngine()
    result = engine.press_keys(tuple(zip(_v37(12), range(0, 700, 100), strict=True)))
    assert result[-1].code is AgcErrorCode.UNSUPPORTED_PROGRAM
    assert engine.snapshot().program is Program.P00


def test_agc_prop_7_v25_commits_three_values_atomically_and_preserves_negative_zero() -> None:
    engine = AgcEngine()
    _send(engine, _v25(-16383, 0, 16383, r2_negative_zero=True))
    snapshot = engine.snapshot()
    assert snapshot.r1.signed_value == -16383
    assert snapshot.r1.raw_data == word_from_signed(-16383).data_raw
    assert snapshot.r1.wire_unit is DisplayUnit.CENTIDEGREES
    assert snapshot.r2.signed_value == 0
    assert snapshot.r2.zero_sign is ZeroSign.NEGATIVE
    assert snapshot.r2.raw_data == 0x7FFF
    assert snapshot.r3.signed_value == 16383
    assert snapshot.r3.wire_unit is DisplayUnit.TENTHS_FPS
    assert snapshot.verb_display == 25
    assert snapshot.noun_display == 81


def test_agc_prop_7_out_of_range_v25_never_partially_commits() -> None:
    engine = AgcEngine()
    at_ms = _send(engine, _v25(1, 2, 3))
    before = (engine.snapshot().r1, engine.snapshot().r2, engine.snapshot().r3)
    prefix = (
        DskyKey.VERB,
        DskyKey.DIGIT_2,
        DskyKey.DIGIT_5,
        DskyKey.ENTR,
        DskyKey.NOUN,
        DskyKey.DIGIT_8,
        DskyKey.DIGIT_1,
        DskyKey.ENTR,
        DskyKey.PLUS,
        DskyKey.DIGIT_9,
        DskyKey.DIGIT_9,
        DskyKey.DIGIT_9,
        DskyKey.DIGIT_9,
        DskyKey.DIGIT_9,
    )
    at_ms = _send(engine, prefix, at_ms)
    result = engine.press_key(DskyKey.ENTR, at_ms)
    assert result.code is AgcErrorCode.DISPLAY_RANGE
    snapshot = engine.snapshot()
    assert snapshot.lamps.opr_err
    assert (snapshot.r1, snapshot.r2, snapshot.r3) == before


def test_agc_req_9_pro_may_terminate_only_r3() -> None:
    engine = AgcEngine()
    prefix = (
        DskyKey.VERB,
        DskyKey.DIGIT_2,
        DskyKey.DIGIT_5,
        DskyKey.ENTR,
        DskyKey.NOUN,
        DskyKey.DIGIT_8,
        DskyKey.DIGIT_1,
        DskyKey.ENTR,
        DskyKey.PLUS,
        DskyKey.DIGIT_1,
    )
    at_ms = _send(engine, prefix)
    result = engine.press_key(DskyKey.PRO, at_ms)
    assert result.code is AgcErrorCode.INVALID_KEY_SEQUENCE
    assert engine.snapshot().r1.raw_data == 0


def test_agc_req_10_v34_terminates_p40_and_preserves_values() -> None:
    engine = AgcEngine()
    at_ms = _send(engine, _v37(40))
    at_ms = _send(engine, _v25(100, -200, 300), at_ms)
    values = (engine.snapshot().r1, engine.snapshot().r2, engine.snapshot().r3)
    at_ms = _send(
        engine,
        (DskyKey.VERB, DskyKey.DIGIT_3, DskyKey.DIGIT_4, DskyKey.ENTR),
        at_ms,
    )
    snapshot = engine.snapshot()
    assert snapshot.program is Program.P00
    assert snapshot.verb_display == 34
    assert (snapshot.r1, snapshot.r2, snapshot.r3) == values
    assert not snapshot.lamps.comp_acty
    assert snapshot.next_comp_acty_tick is None
    assert not engine.apply_p40_tick(CompActyTick(1)).success


def test_agc_prop_8_comp_acty_accepts_only_exact_next_tick() -> None:
    engine = AgcEngine()
    _send(engine, _v37(40))
    before = engine.snapshot()
    skipped = engine.apply_p40_tick(CompActyTick(2))
    assert skipped.code is AgcErrorCode.SCHEDULER_STATE
    assert engine.snapshot() == before

    assert engine.apply_p40_tick(CompActyTick(1)).success
    assert not engine.snapshot().lamps.comp_acty
    after_one = engine.snapshot()
    duplicate = engine.apply_p40_tick(CompActyTick(1))
    assert duplicate.code is AgcErrorCode.SCHEDULER_STATE
    assert engine.snapshot() == after_one
    assert engine.apply_p40_tick(CompActyTick(2)).success
    assert engine.snapshot().lamps.comp_acty


def test_m3_v37_then_v25_has_exact_deterministic_snapshot() -> None:
    first = AgcEngine()
    second = AgcEngine()
    sequence = (*_v37(40), *_v25(1234, -567, 89))
    for engine in (first, second):
        _send(engine, sequence)
        engine.apply_p40_tick(CompActyTick(1))
        engine.apply_p40_tick(CompActyTick(2))
    snapshot = first.snapshot()
    assert snapshot == second.snapshot()
    assert snapshot.program is Program.P40
    assert (snapshot.r1.signed_value, snapshot.r2.signed_value, snapshot.r3.signed_value) == (
        1234,
        -567,
        89,
    )
    assert snapshot.lamps.comp_acty
    assert not snapshot.lamps.opr_err
