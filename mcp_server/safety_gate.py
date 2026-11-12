"""Normative safety gate for ``execute_dsky_sequence`` (steering S-01..S-05, MCP-REQ-8..22).

``SafetyGate.evaluate`` is pure: it receives the trusted ledger record, the
agent's keys, the session's inspection context, and the daemon preflight
snapshot, and returns a decision.  Nothing the agent says can change the
outcome; the frame ``CRITICAL`` flag can only add criticality.

Checks, in order (first failure wins):
1.  Flight Watch not HALTED.
2.  COMMAND known to this session's ledger.
3.  Lifecycle: claimed/terminal -> idempotent replay or conflict; EXPIRED -> closed.
4.  Daemon journal has no foreign execution for the frame.
5.  Inspect-before-act: same session + epoch, captured after delivery, age below the
    catalog ``inspection_max_age_ms`` (20 s in catalog v1.0),
    revision equal to the current daemon control revision.
6.  KEY REL / OPR ERR / DSKY idle preconditions on the *current* snapshot.
7.  Canonical plan recomputed from trusted frame + current snapshot.
8.  Exact key equality with the canonical plan.
9.  Criticality: critical commands need a MATCHED AUTH; HELD expiry after the
    catalog ``hold_expiry_ms`` (120 s in catalog 1.2).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from mcp_server.clock import parse_timestamp
from mcp_server.errors import BridgeError, ErrorCode
from mcp_server.ledger import AuthState, CommandRecord, CommandState
from mcp_server.planner import (
    AgcState,
    CanonicalPlanner,
    Command,
    Plan,
    compute_plan_digest,
    precondition_error,
)


class Decision(StrEnum):
    ALLOW = "ALLOW"
    REJECT = "REJECT"
    RECONCILE = "RECONCILE"


@dataclass(frozen=True, slots=True)
class InspectionContext:
    session_id: str
    sequence_epoch: str
    state_revision: int
    captured_at: datetime
    snapshot_digest: str
    state: AgcState


@dataclass(frozen=True, slots=True)
class GateRequest:
    session_id: str
    sequence_epoch: str
    frame_seq: int
    keys: tuple[str, ...]
    record: CommandRecord | None
    inspection: InspectionContext | None
    current: AgcState | None
    daemon_execution: dict[str, Any] | None
    now: datetime
    halted: bool


@dataclass(frozen=True, slots=True)
class GateDecision:
    decision: Decision
    error: BridgeError | None = None
    plan: Plan | None = None
    auth_seq: int | None = None
    expire_command: bool = False

    @property
    def allowed(self) -> bool:
        return self.decision is Decision.ALLOW


def _reject(code: ErrorCode, message: str, frame_seq: int, **kwargs: Any) -> GateDecision:
    expire = bool(kwargs.pop("expire_command", False))
    return GateDecision(
        Decision.REJECT,
        BridgeError(code, message, frame_seq=frame_seq, details=kwargs or None),
        expire_command=expire,
    )


class SafetyGate:
    def __init__(self, planner: CanonicalPlanner) -> None:
        self._planner = planner
        self._max_age = timedelta(milliseconds=planner.inspection_max_age_ms)
        self._hold = timedelta(milliseconds=planner.hold_expiry_ms)

    def hold_deadline(self, record: CommandRecord) -> datetime:
        return parse_timestamp(record.received_at) + self._hold

    def check_inspection(
        self,
        *,
        session_id: str,
        sequence_epoch: str,
        record: CommandRecord,
        inspection: InspectionContext | None,
        current: AgcState | None,
        now: datetime,
    ) -> BridgeError | None:
        """Inspect-before-act freshness, shared by planning and execution."""

        seq = record.frame_seq
        if (
            inspection is None
            or inspection.session_id != session_id
            or inspection.sequence_epoch != sequence_epoch
            or inspection.captured_at <= parse_timestamp(record.delivered_at)
        ):
            return BridgeError(
                ErrorCode.INSPECTION_REQUIRED,
                "call inspect_agc_status after the COMMAND was delivered",
                frame_seq=seq,
            )
        if now - inspection.captured_at >= self._max_age:
            return BridgeError(
                ErrorCode.INSPECTION_STALE,
                f"inspection is {self._planner.inspection_max_age_ms // 1000} s old or older; call inspect_agc_status again",
                frame_seq=seq,
            )
        if current is None:
            return BridgeError(ErrorCode.AGC_UNAVAILABLE, "current AGC state unreadable", frame_seq=seq)
        if current.state_revision != inspection.state_revision:
            return BridgeError(
                ErrorCode.INSPECTION_STALE,
                "AGC state changed since inspection",
                frame_seq=seq,
                details={"inspected": inspection.state_revision, "current": current.state_revision},
            )
        return None

    def evaluate(self, request: GateRequest) -> GateDecision:
        seq = request.frame_seq
        if request.halted:
            return _reject(
                ErrorCode.FLIGHT_WATCH_HALTED,
                "Flight Watch is HALTED; operator acknowledgement (bridge restart) and a safe AGC state are required",
                seq,
            )
        record = request.record
        if record is None:
            return _reject(ErrorCode.NOT_FOUND, f"COMMAND {seq} was not delivered to this session", seq)

        request_digest = compute_plan_digest(self._planner.catalog_version, seq, request.keys)
        if record.state in (
            CommandState.EXECUTING,
            CommandState.EXECUTED,
            CommandState.FAILED,
            CommandState.OUTCOME_UNKNOWN,
        ):
            if record.plan_digest == request_digest:
                return GateDecision(Decision.RECONCILE)
            return _reject(
                ErrorCode.IDEMPOTENCY_CONFLICT,
                f"COMMAND {seq} was already claimed with a different key sequence",
                seq,
            )
        if record.state is CommandState.EXPIRED:
            return _reject(ErrorCode.COMMAND_CLOSED, f"COMMAND {seq} expired", seq)
        if request.daemon_execution is not None:
            return _reject(
                ErrorCode.COMMAND_CLOSED, f"daemon already holds an execution for {seq}", seq
            )

        inspection_error = self.check_inspection(
            session_id=request.session_id,
            sequence_epoch=request.sequence_epoch,
            record=record,
            inspection=request.inspection,
            current=request.current,
            now=request.now,
        )
        if inspection_error is not None:
            return GateDecision(Decision.REJECT, inspection_error)
        assert request.current is not None
        blocked = precondition_error(request.current)
        if blocked is not None:
            blocked.frame_seq = seq
            return GateDecision(Decision.REJECT, blocked)

        try:
            plan = self._planner.plan(Command.from_frame(record.frame), request.current)
        except BridgeError as error:
            return GateDecision(Decision.REJECT, error)
        if request.keys != plan.keys:
            return _reject(
                ErrorCode.PLAN_MISMATCH,
                "keys differ from the canonical plan; call plan_dsky_sequence and send it unchanged",
                seq,
                expected_keys=len(plan.keys),
                received_keys=len(request.keys),
            )

        auth_seq = record.auth_seq if record.auth_state is AuthState.MATCHED else None
        if plan.critical and auth_seq is None:
            if record.auth_state is AuthState.CONSUMED:
                return _reject(ErrorCode.AUTH_USED, "AUTH for this COMMAND was already consumed", seq)
            if request.now >= self.hold_deadline(record):
                return _reject(
                    ErrorCode.AUTH_EXPIRED,
                    f"critical COMMAND held for {self._planner.hold_expiry_ms // 1000} s without AUTH; "
                    "it is now EXPIRED",
                    seq,
                    expire_command=True,
                )
            return _reject(
                ErrorCode.AUTH_REQUIRED,
                "critical command: wait for an operator AUTH frame with ref_seq equal to this "
                "COMMAND (await_telemetry_frame), then inspect, plan, and execute again",
                seq,
                reasons=",".join(plan.critical_reasons),
            )
        return GateDecision(Decision.ALLOW, plan=plan, auth_seq=auth_seq)
