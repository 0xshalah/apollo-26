from __future__ import annotations

from agc_core import (
    AgcEngine,
    AgcErrorCode,
    DisplayBusy,
    DskyKey,
    DskyState,
    EntryKind,
    ReceiverActivity,
)


def test_agc_req_6_first_key_99ms_boundary_and_rejected_anchor() -> None:
    engine = AgcEngine()
    first = engine.press_key(DskyKey.VERB, 0)
    after_first = engine.snapshot()
    assert first.success

    too_fast = engine.press_key(DskyKey.DIGIT_3, 99)
    assert not too_fast.success
    assert too_fast.code is AgcErrorCode.KEY_CADENCE
    assert engine.snapshot() == after_first
    assert engine.last_accepted_key_ms == 0

    boundary = engine.press_key(DskyKey.DIGIT_3, 100)
    assert boundary.success
    assert engine.snapshot().pending_entry is not None
    assert engine.snapshot().pending_entry.digits == (3,)


def test_agc_req_6_key_rel_guard_precedes_time_and_preserves_anchor() -> None:
    engine = AgcEngine()
    engine.press_key(DskyKey.VERB, 100)
    engine.set_display_busy(DisplayBusy(True))
    before = engine.snapshot()
    rejected = engine.press_key(DskyKey.RSET, -1)
    assert rejected.code is AgcErrorCode.KEY_REL_ACTIVE
    assert engine.snapshot() == before
    assert engine.last_accepted_key_ms == 100

    engine.set_display_busy(DisplayBusy(False))
    assert engine.press_key(DskyKey.RSET, 200).success


def test_agc_req_6_negative_and_regressing_time_do_not_mutate() -> None:
    engine = AgcEngine()
    before = engine.snapshot()
    negative = engine.press_key(DskyKey.VERB, -1)
    assert negative.code is AgcErrorCode.TIME_REGRESSION
    assert engine.snapshot() == before

    engine.press_key(DskyKey.VERB, 500)
    entered = engine.snapshot()
    regressing = engine.press_key(DskyKey.DIGIT_2, 499)
    assert regressing.code is AgcErrorCode.TIME_REGRESSION
    assert engine.snapshot() == entered


def test_agc_req_5_clr_and_key_rel_cancel_transient_entry() -> None:
    engine = AgcEngine()
    assert engine.press_key(DskyKey.VERB, 0).success
    assert engine.press_key(DskyKey.DIGIT_2, 100).success
    assert engine.press_key(DskyKey.CLR, 200).success
    pending = engine.snapshot().pending_entry
    assert pending is not None and pending.digits == ()

    assert engine.press_key(DskyKey.KEY_REL, 300).success
    snapshot = engine.snapshot()
    assert snapshot.dsky_state is DskyState.IDLE
    assert snapshot.pending_entry is None


def test_agc_prop_4_invalid_logical_key_latches_opr_err_and_protects_state() -> None:
    engine = AgcEngine()
    protected = (
        engine.snapshot().program,
        engine.snapshot().r1,
        engine.snapshot().r2,
        engine.snapshot().r3,
        engine.snapshot().registers,
        engine.read_memory(0),
    )
    result = engine.press_key(DskyKey.DIGIT_1, 0)
    assert result.accepted
    assert result.code is AgcErrorCode.INVALID_KEY_SEQUENCE
    snapshot = engine.snapshot()
    assert snapshot.dsky_state is DskyState.OPR_ERR
    assert snapshot.lamps.opr_err
    assert (
        snapshot.program,
        snapshot.r1,
        snapshot.r2,
        snapshot.r3,
        snapshot.registers,
        engine.read_memory(0),
    ) == protected


def test_agc_prop_5_opr_err_is_latched_and_only_rset_recovers() -> None:
    engine = AgcEngine()
    engine.press_key(DskyKey.NOUN, 0)
    latched = engine.snapshot()
    blocked = engine.press_key(DskyKey.VERB, 100)
    assert blocked.code is AgcErrorCode.OPR_ERR_LATCHED
    assert engine.snapshot() == latched
    assert engine.last_accepted_key_ms == 0

    recovered = engine.press_key(DskyKey.RSET, 100)
    assert recovered.success
    assert engine.snapshot().dsky_state is DskyState.IDLE
    assert not engine.snapshot().lamps.opr_err


def test_agc_req_7_timing_guard_wins_while_opr_err_is_latched() -> None:
    engine = AgcEngine()
    engine.press_key(DskyKey.NOUN, 100)
    result = engine.press_key(DskyKey.VERB, 199)
    assert result.code is AgcErrorCode.KEY_CADENCE
    assert engine.snapshot().lamps.opr_err


def test_agc_req_15_unsupported_verb_has_specific_stable_code() -> None:
    engine = AgcEngine()
    results = engine.press_keys(
        (
            (DskyKey.VERB, 0),
            (DskyKey.DIGIT_9, 100),
            (DskyKey.DIGIT_9, 200),
            (DskyKey.ENTR, 300),
            (DskyKey.RSET, 400),
        )
    )
    assert len(results) == 4
    assert results[-1].code is AgcErrorCode.UNSUPPORTED_VERB
    assert engine.snapshot().lamps.opr_err


def test_agc_req_13_explicit_activity_events_are_idempotent() -> None:
    engine = AgcEngine()
    first = engine.set_receiver_activity(ReceiverActivity(True))
    assert engine.snapshot().lamps.uplink_acty
    second = engine.set_receiver_activity(ReceiverActivity(True))
    assert second.revision == first.revision

    busy = engine.set_display_busy(DisplayBusy(True))
    assert busy.revision == first.revision + 1
    assert engine.snapshot().lamps.key_rel


def test_agc_req_5_completed_v25_exposes_typed_pending_noun_marker() -> None:
    engine = AgcEngine()
    engine.press_keys(
        (
            (DskyKey.VERB, 0),
            (DskyKey.DIGIT_2, 100),
            (DskyKey.DIGIT_5, 200),
            (DskyKey.ENTR, 300),
        )
    )
    snapshot = engine.snapshot()
    assert snapshot.dsky_state is DskyState.IDLE
    assert snapshot.pending_entry is not None
    assert snapshot.pending_entry.kind is EntryKind.V25_NOUN
    assert engine.press_key(DskyKey.NOUN, 400).success
    assert engine.snapshot().dsky_state is DskyState.NOUN_ENTRY
