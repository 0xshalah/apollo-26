"""P7: a critical command without a matched operator AUTH is never allowed to actuate.

Exercises ``SafetyGate.evaluate`` directly over generated AGC states, commands,
AUTH lifecycle states, key sequences, and clock offsets. A companion property
checks the gate is not vacuous: a fresh, canonical, authorized request is allowed.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from hypothesis import assume, given
from hypothesis import strategies as st

from mcp_server.clock import format_timestamp
from mcp_server.ledger import AuthState, CommandRecord, CommandState
from mcp_server.planner import AgcState, CanonicalPlanner, Command
from mcp_server.safety_gate import Decision, GateRequest, InspectionContext, SafetyGate
from tests.harness import BRIDGE_CONTRACTS

PLANNER = CanonicalPlanner(BRIDGE_CONTRACTS.catalog)
GATE = SafetyGate(PLANNER)
EPOCH = "00000000-0000-4000-8000-000000000026"
SESSION = "p7-session"
T0 = datetime(2026, 11, 20, 12, 0, 0, tzinfo=UTC)
REGISTER = st.integers(min_value=-16383, max_value=16383)
KEY_NAMES = tuple(BRIDGE_CONTRACTS.catalog["keys"])


def _frame(seq: int, verb: int, noun: int, program: int, r1: int, r2: int, dv: int, flag: bool) -> dict[str, object]:
    return {
        "version": 1,
        "frame_type": "COMMAND",
        "seq": seq,
        "ref_seq": 0,
        "critical": flag,
        "verb": verb,
        "noun": noun,
        "program": program,
        "r1_centidegrees": r1,
        "r2_centidegrees": r2,
        "delta_v_tenths_fps": dv,
        "hmac_hex": "00" * 8,
        "crc_hex": "0000",
        "raw_hex": "00" * 34,
    }


@st.composite
def critical_scenarios(draw: st.DrawFn) -> tuple[dict[str, object], AgcState]:
    """Commands that the catalog classifies as critical for the generated AGC state."""

    kind = draw(st.sampled_from(("V37_P00_WHILE_P40", "V34_WHILE_P40", "P40_ACTIVATION")))
    seq = draw(st.integers(min_value=2, max_value=10_000))
    flag = draw(st.booleans())
    r1, r2, r3 = draw(REGISTER), draw(REGISTER), draw(REGISTER)
    if kind == "P40_ACTIVATION":
        dv = draw(REGISTER.filter(lambda value: value != 0))
        frame = _frame(seq, 37, 0, 40, draw(REGISTER), draw(REGISTER), dv, flag)
        program = 0
    else:
        verb = 37 if kind == "V37_P00_WHILE_P40" else 34
        frame = _frame(seq, verb, 0, 0, 0, 0, 0, flag)
        program = 40
    state = AgcState(
        state_revision=draw(st.integers(min_value=0, max_value=1_000)),
        program=program,
        verb=draw(st.sampled_from((0, 25, 34, 37))),
        noun=draw(st.sampled_from((0, 81))),
        r1=r1,
        r2=r2,
        r3=r3,
        input_state="IDLE",
        pending_entry=None,
        key_rel=False,
        opr_err=False,
        snapshot_digest="digest",
    )
    return frame, state


def _record(frame: dict[str, object], state: CommandState, auth: AuthState, auth_seq: int | None) -> CommandRecord:
    return CommandRecord(
        frame_seq=int(frame["seq"]),  # type: ignore[arg-type]
        sequence_epoch=EPOCH,
        frame=frame,
        received_at=format_timestamp(T0),
        delivered_at=format_timestamp(T0 + timedelta(milliseconds=10)),
        state=state,
        auth_state=auth,
        auth_seq=auth_seq,
    )


def _inspection(state: AgcState) -> InspectionContext:
    return InspectionContext(
        session_id=SESSION,
        sequence_epoch=EPOCH,
        state_revision=state.state_revision,
        captured_at=T0 + timedelta(milliseconds=20),
        snapshot_digest=state.snapshot_digest,
        state=state,
    )


@given(
    scenario=critical_scenarios(),
    lifecycle=st.sampled_from(
        (
            (CommandState.HELD, AuthState.REQUIRED),
            (CommandState.READY, AuthState.NOT_REQUIRED),
            (CommandState.READY, AuthState.REQUIRED),
            (CommandState.HELD, AuthState.CONSUMED),
            (CommandState.HELD, AuthState.EXPIRED),
        )
    ),
    use_canonical_keys=st.booleans(),
    random_keys=st.lists(st.sampled_from(KEY_NAMES), max_size=40),
    elapsed_ms=st.integers(min_value=21, max_value=40_000),
)
def test_p7_critical_without_matched_auth_never_allows(
    scenario: tuple[dict[str, object], AgcState],
    lifecycle: tuple[CommandState, AuthState],
    use_canonical_keys: bool,
    random_keys: list[str],
    elapsed_ms: int,
) -> None:
    frame, state = scenario
    plan = PLANNER.plan(Command.from_frame(frame), state)
    assert plan.critical, "scenario generator must only produce critical commands"
    keys = plan.keys if use_canonical_keys else tuple(random_keys)
    command_state, auth_state = lifecycle
    decision = GATE.evaluate(
        GateRequest(
            session_id=SESSION,
            sequence_epoch=EPOCH,
            frame_seq=int(frame["seq"]),  # type: ignore[arg-type]
            keys=keys,
            record=_record(frame, command_state, auth_state, None),
            inspection=_inspection(state),
            current=state,
            daemon_execution=None,
            now=T0 + timedelta(milliseconds=elapsed_ms),
            halted=False,
        )
    )
    assert decision.decision is not Decision.ALLOW


@given(scenario=critical_scenarios(), elapsed_ms=st.integers(min_value=21, max_value=4_999))
def test_p7_companion_fresh_canonical_matched_auth_is_allowed(
    scenario: tuple[dict[str, object], AgcState], elapsed_ms: int
) -> None:
    frame, state = scenario
    seq = int(frame["seq"])  # type: ignore[arg-type]
    plan = PLANNER.plan(Command.from_frame(frame), state)
    decision = GATE.evaluate(
        GateRequest(
            session_id=SESSION,
            sequence_epoch=EPOCH,
            frame_seq=seq,
            keys=plan.keys,
            record=_record(frame, CommandState.READY, AuthState.MATCHED, seq + 1),
            inspection=_inspection(state),
            current=state,
            daemon_execution=None,
            now=T0 + timedelta(milliseconds=elapsed_ms),
            halted=False,
        )
    )
    assert decision.decision is Decision.ALLOW
    assert decision.auth_seq == seq + 1


@given(
    scenario=critical_scenarios(),
    key_rel=st.booleans(),
    opr_err=st.booleans(),
    revision_shift=st.integers(min_value=0, max_value=3),
)
def test_p7_gate_rejects_unsafe_agc_state_even_with_matched_auth(
    scenario: tuple[dict[str, object], AgcState], key_rel: bool, opr_err: bool, revision_shift: int
) -> None:
    assume(key_rel or opr_err or revision_shift)
    frame, inspected = scenario
    seq = int(frame["seq"])  # type: ignore[arg-type]
    plan = PLANNER.plan(Command.from_frame(frame), inspected)
    current = AgcState(
        state_revision=inspected.state_revision + revision_shift,
        program=inspected.program,
        verb=inspected.verb,
        noun=inspected.noun,
        r1=inspected.r1,
        r2=inspected.r2,
        r3=inspected.r3,
        input_state="IDLE",
        pending_entry=None,
        key_rel=key_rel,
        opr_err=opr_err,
        snapshot_digest="digest",
    )
    decision = GATE.evaluate(
        GateRequest(
            session_id=SESSION,
            sequence_epoch=EPOCH,
            frame_seq=seq,
            keys=plan.keys,
            record=_record(frame, CommandState.READY, AuthState.MATCHED, seq + 1),
            inspection=_inspection(inspected),
            current=current,
            daemon_execution=None,
            now=T0 + timedelta(milliseconds=100),
            halted=False,
        )
    )
    assert decision.decision is not Decision.ALLOW
