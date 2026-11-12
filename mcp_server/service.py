"""Flight Watch application service behind the six MCP tools.

Every tool returns the shared result envelope of mcp-bridge design §7.1:
``{"schema_version": "1.0", "request_id", "ok": true, "data"}`` or
``{"schema_version": "1.0", "request_id", "ok": false, "error": {...}}``.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, Final

from mcp_server.audit import AuditError, AuditSink
from mcp_server.clock import Clock, format_timestamp, parse_timestamp
from mcp_server.crc import ALGORITHM, crc16_ccitt_false
from mcp_server.errors import BridgeError, ErrorCode
from mcp_server.ledger import (
    OPEN_STATES,
    AuthState,
    CommandRecord,
    CommandState,
    Ledger,
    LedgerError,
)
from mcp_server.planner import AgcState, CanonicalPlanner, Command, Plan, precondition_error
from mcp_server.rpc_client import DaemonPort, DaemonRejected, OutcomeUnknown, RpcReply
from mcp_server.safety_gate import Decision, GateRequest, InspectionContext, SafetyGate

_LOG = logging.getLogger(__name__)
SCHEMA_VERSION: Final = "1.0"
_HEX = re.compile(r"^[0-9a-fA-F]+$")
_EXECUTE_DEADLINE_MS: Final = 30_000
_READ_DEADLINE_MS: Final = 5_000
_RECONCILE_ATTEMPTS: Final = 3

_DAEMON_CODES: Final = {code.value: code for code in ErrorCode}


class FlightMarker:
    """``telemetry/FLIGHT_MODE`` live-session marker read by the PreToolUse hook."""

    def __init__(self, path: Path | None) -> None:
        self._path = path
        self._active = False

    def activate(self, session_id: str, now: datetime) -> None:
        if self._path is None or self._active:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_name(self._path.name + ".tmp")
        temporary.write_text(f"session_id={session_id}\nstarted_at={format_timestamp(now)}\n", encoding="utf-8")
        temporary.replace(self._path)
        self._active = True

    def release(self) -> None:
        if self._path is not None and self._active:
            with contextlib.suppress(FileNotFoundError):
                self._path.unlink()
            self._active = False


def _ok(request_id: str, data: dict[str, Any]) -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "request_id": request_id, "ok": True, "data": data}


def _fail(request_id: str, error: BridgeError) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "request_id": request_id,
        "ok": False,
        "error": {
            "code": error.code.value,
            "message": error.message,
            "retryable": error.retryable,
            "frame_seq": error.frame_seq,
            "details": error.details,
        },
    }


def _translate(rejected: DaemonRejected, frame_seq: int | None = None) -> BridgeError:
    code = _DAEMON_CODES.get(rejected.code, ErrorCode.INTERNAL)
    return BridgeError(
        code,
        f"daemon: {rejected.message}",
        retryable=rejected.retryable,
        frame_seq=frame_seq,
    )


class FlightWatchService:
    def __init__(
        self,
        *,
        daemon: DaemonPort,
        planner: CanonicalPlanner,
        ledger: Ledger,
        audit: AuditSink,
        clock: Clock,
        session_id: str,
        marker: FlightMarker | None = None,
        id_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
    ) -> None:
        self._daemon = daemon
        self._planner = planner
        self._gate = SafetyGate(planner)
        self._ledger = ledger
        self._audit = audit
        self._clock = clock
        self.session_id = session_id
        self._marker = marker or FlightMarker(None)
        self._new_id = id_factory
        self._inspection: InspectionContext | None = None
        self._instance_id: str | None = None
        self._await_lock = asyncio.Lock()
        self._execute_lock = asyncio.Lock()
        self._reconciled = False
        self.halted = False
        self._audit.emit("session.start", details={"catalog_version": planner.catalog_version})

    # ------------------------------------------------------------ plumbing
    async def _run(
        self, tool: str, body: Callable[[str], Awaitable[dict[str, Any]]]
    ) -> dict[str, Any]:
        request_id = self._new_id()
        self._audit.emit("tool.call", request_id=request_id, details={"tool": tool})
        try:
            return _ok(request_id, await body(request_id))
        except BridgeError as error:
            return _fail(request_id, error)
        except DaemonRejected as rejected:
            return _fail(request_id, _translate(rejected))
        except (LedgerError, AuditError) as error:
            _LOG.error("%s request_id=%s failed closed: %s", tool, request_id, error)
            code = ErrorCode.AUDIT_FAILURE if isinstance(error, AuditError) else ErrorCode.INTERNAL
            return _fail(request_id, BridgeError(code, "bridge persistence failed; nothing was actuated"))
        except Exception:
            _LOG.exception("%s request_id=%s failed with an unexpected error", tool, request_id)
            return _fail(request_id, BridgeError(ErrorCode.INTERNAL, "internal bridge error"))

    async def _call(self, method: str, params: dict[str, Any], deadline_ms: int) -> RpcReply:
        reply = await self._daemon.call(method, params, deadline_ms)
        self._observe(reply.daemon_instance_id, reply.sequence_epoch)
        return reply

    def _observe(self, instance_id: str, epoch: str) -> None:
        if self._ledger.epoch is None:
            self._ledger.commit(epoch=epoch)
        elif self._ledger.epoch != epoch:
            old = self._ledger.epoch
            self._inspection = None
            self._ledger.commit(reset=True, epoch=epoch, cursor=0)
            self._audit.emit(
                "reconciliation",
                sequence_epoch=epoch,
                decision="RECONCILE",
                error_code=ErrorCode.SEQUENCE_EPOCH_CHANGED.value,
                details={"previous_epoch": old},
            )
            raise BridgeError(
                ErrorCode.SEQUENCE_EPOCH_CHANGED,
                "daemon sequence was reprovisioned; all pending COMMAND/AUTH were invalidated",
            )
        if self._instance_id is not None and self._instance_id != instance_id:
            self._inspection = None
            self._reconciled = False
        self._instance_id = instance_id

    def _require_epoch(self) -> str:
        epoch = self._ledger.epoch
        if epoch is None:
            raise BridgeError(ErrorCode.DAEMON_UNAVAILABLE, "daemon epoch unknown", retryable=True)
        return epoch

    async def _reconcile_open_claims(self) -> None:
        """Restart path: close EXECUTING/OUTCOME_UNKNOWN records from the daemon journal."""

        if self._reconciled:
            return
        for record in self._ledger.records():
            if record.state in (CommandState.EXECUTING, CommandState.OUTCOME_UNKNOWN):
                reply = await self._call("execution.get", {"frame_seq": record.frame_seq}, _READ_DEADLINE_MS)
                await self._apply_reconciled(record, reply.result["execution"])
        self._reconciled = True

    # ------------------------------------------------------------ expiry
    def _expire_if_due(self, record: CommandRecord) -> CommandRecord:
        if record.state is CommandState.HELD and self._clock.now() >= self._gate.hold_deadline(record):
            record = self._ledger.update(
                record, state=CommandState.EXPIRED, auth_state=AuthState.EXPIRED, error_code="AUTH_EXPIRED"
            )
            self._audit.emit(
                "command.expired",
                frame_seq=record.frame_seq,
                sequence_epoch=record.sequence_epoch,
                command_state=record.state.value,
                error_code="AUTH_EXPIRED",
            )
        return record

    # ------------------------------------------------------------ tools
    async def read_telemetry_frames(self, since_seq: int = 0, limit: int = 100) -> dict[str, Any]:
        async def body(request_id: str) -> dict[str, Any]:
            reply = await self._call(
                "telemetry.read", {"after_seq": since_seq, "limit": limit}, _READ_DEADLINE_MS
            )
            frames = reply.result["frames"]
            next_since = frames[-1]["frame"]["seq"] if frames else since_seq
            return {
                "frames": frames,
                "next_since_seq": next_since,
                "truncated": reply.result["truncated"],
                "sequence_epoch": reply.sequence_epoch,
            }

        return await self._run("read_telemetry_frames", body)

    async def await_telemetry_frame(self, timeout_sec: float) -> dict[str, Any]:
        async def body(request_id: str) -> dict[str, Any]:
            if self._await_lock.locked():
                raise BridgeError(ErrorCode.BUSY, "another await_telemetry_frame is in progress", retryable=True)
            async with self._await_lock:
                self._marker.activate(self.session_id, self._clock.now())
                timeout_ms = max(0, min(30_000, int(round(timeout_sec * 1000))))
                cursor = self._ledger.cursor
                reply = await self._call(
                    "telemetry.await",
                    {"after_seq": cursor, "timeout_ms": timeout_ms},
                    timeout_ms + _READ_DEADLINE_MS,
                )
                if reply.result["status"] == "TIMEOUT":
                    return {
                        "status": "TIMEOUT",
                        "frame": None,
                        "cursor_seq": cursor,
                        "sequence_epoch": reply.sequence_epoch,
                        "lifecycle": None,
                    }
                record = reply.result["frame"]
                lifecycle = await self._ingest(request_id, record, reply.sequence_epoch)
                return {
                    "status": "FRAME",
                    "frame": record,
                    "cursor_seq": record["frame"]["seq"],
                    "sequence_epoch": reply.sequence_epoch,
                    "lifecycle": lifecycle,
                }

        return await self._run("await_telemetry_frame", body)

    async def _ingest(self, request_id: str, record: dict[str, Any], epoch: str) -> dict[str, Any]:
        frame = record["frame"]
        seq = frame["seq"]
        now = self._clock.now()
        if frame["frame_type"] == "COMMAND":
            command = Command.from_frame(frame)
            state, auth_state, reasons, note = CommandState.READY, AuthState.NOT_REQUIRED, (), None
            try:
                snapshot = await self._call("agc.inspect", {}, _READ_DEADLINE_MS)
                plan = self._planner.plan(command, AgcState.from_snapshot(snapshot.result))
                reasons = tuple(reason.value for reason in plan.critical_reasons)
            except BridgeError as error:
                if error.code is ErrorCode.UNSUPPORTED_COMMAND:
                    note = error.code.value
                else:  # AGC unreadable at delivery: fail closed as HELD.
                    reasons = ("FRAME_CRITICAL_FLAG",) if command.critical else ()
                    note = error.code.value
                    state, auth_state = CommandState.HELD, AuthState.REQUIRED
            except DaemonRejected as rejected:
                reasons, note = (), rejected.code
                state, auth_state = CommandState.HELD, AuthState.REQUIRED
            if reasons:
                state, auth_state = CommandState.HELD, AuthState.REQUIRED
            entry = CommandRecord(
                frame_seq=seq,
                sequence_epoch=epoch,
                frame=frame,
                received_at=record["received_at"],
                delivered_at=format_timestamp(now),
                state=state,
                auth_state=auth_state,
                critical_reasons=reasons,
                error_code=note,
            )
            self._ledger.commit(updates=[entry], cursor=seq)
            self._audit.emit(
                "frame.delivered",
                request_id=request_id,
                frame_seq=seq,
                sequence_epoch=epoch,
                command_state=state.value,
                details={"frame_type": "COMMAND", "critical_reasons": ",".join(reasons)},
            )
            return {
                "frame_seq": seq,
                "command_state": state.value,
                "auth_state": auth_state.value,
                "critical_reasons": list(reasons),
                "error_code": note,
            }
        return self._ingest_auth(request_id, record, epoch)

    def _ingest_auth(self, request_id: str, record: dict[str, Any], epoch: str) -> dict[str, Any]:
        frame = record["frame"]
        seq, ref = frame["seq"], frame["ref_seq"]
        target = self._ledger.get(ref)
        error: ErrorCode | None = None
        updates: list[CommandRecord] = []
        if target is None:
            error = ErrorCode.STATE  # AUTH-before-COMMAND or unknown COMMAND
        else:
            target = self._expire_if_due(target)
            if target.state is CommandState.EXPIRED:
                error = ErrorCode.AUTH_EXPIRED
            elif target.state not in OPEN_STATES or target.auth_state in (
                AuthState.MATCHED,
                AuthState.CONSUMED,
            ):
                error = ErrorCode.AUTH_USED
            elif parse_timestamp(record["received_at"]) >= self._gate.hold_deadline(target):
                error = ErrorCode.AUTH_EXPIRED
                if target.state is CommandState.HELD:
                    updates.append(
                        replace(target, state=CommandState.EXPIRED, auth_state=AuthState.EXPIRED)
                    )
            else:
                updates.append(
                    replace(
                        target,
                        state=CommandState.READY,
                        auth_state=AuthState.MATCHED,
                        auth_seq=seq,
                    )
                )
        self._ledger.commit(updates=updates, cursor=seq)
        current = updates[0] if updates else target
        self._audit.emit(
            "auth.rejected" if error else "auth.accepted",
            request_id=request_id,
            frame_seq=ref if target is not None else None,
            ref_seq=ref,
            sequence_epoch=epoch,
            error_code=None if error is None else error.value,
            command_state=None if current is None else current.state.value,
            details={"auth_seq": seq},
        )
        return {
            "frame_seq": ref,
            "auth_seq": seq,
            "command_state": None if current is None else current.state.value,
            "auth_state": None if current is None else current.auth_state.value,
            "critical_reasons": [] if current is None else list(current.critical_reasons),
            "error_code": None if error is None else error.value,
        }

    async def inspect_agc_status(self) -> dict[str, Any]:
        async def body(request_id: str) -> dict[str, Any]:
            reply = await self._call("agc.inspect", {}, _READ_DEADLINE_MS)
            snapshot = reply.result
            state = AgcState.from_snapshot(snapshot)
            self._inspection = InspectionContext(
                session_id=self.session_id,
                sequence_epoch=reply.sequence_epoch,
                state_revision=state.state_revision,
                captured_at=self._clock.now(),
                snapshot_digest=state.snapshot_digest,
                state=state,
            )
            self._audit.emit(
                "inspection",
                request_id=request_id,
                sequence_epoch=reply.sequence_epoch,
                agc_revision=state.state_revision,
                details={"key_rel": state.key_rel, "opr_err": state.opr_err, "program": state.program},
            )
            data = {key: value for key, value in snapshot.items() if key not in ("engine_revision", "catalog_version")}
            data["sequence_epoch"] = reply.sequence_epoch
            return data

        return await self._run("inspect_agc_status", body)

    async def plan_dsky_sequence(self, frame_seq: int) -> dict[str, Any]:
        async def body(request_id: str) -> dict[str, Any]:
            record = self._ledger.get(frame_seq)
            if record is None:
                raise BridgeError(ErrorCode.NOT_FOUND, f"COMMAND {frame_seq} was not delivered", frame_seq=frame_seq)
            record = self._expire_if_due(record)
            if record.state not in OPEN_STATES:
                raise BridgeError(
                    ErrorCode.COMMAND_CLOSED,
                    f"COMMAND {frame_seq} is {record.state.value}",
                    frame_seq=frame_seq,
                )
            preflight = await self._call("execution.preflight", {"frame_seq": frame_seq}, _READ_DEADLINE_MS)
            current = AgcState.from_snapshot(preflight.result["snapshot"])
            stale = self._gate.check_inspection(
                session_id=self.session_id,
                sequence_epoch=preflight.sequence_epoch,
                record=record,
                inspection=self._inspection,
                current=current,
                now=self._clock.now(),
            )
            if stale is not None:
                raise stale
            assert self._inspection is not None
            blocked = precondition_error(self._inspection.state)
            if blocked is not None:
                blocked.frame_seq = frame_seq
                raise blocked
            plan = self._planner.plan(Command.from_frame(record.frame), self._inspection.state)
            if plan.critical and record.auth_state is AuthState.NOT_REQUIRED:
                record = self._ledger.update(record, state=CommandState.HELD, auth_state=AuthState.REQUIRED)
            record = self._ledger.update(
                record, critical_reasons=tuple(reason.value for reason in plan.critical_reasons)
            )
            self._audit.emit(
                "plan.generated",
                request_id=request_id,
                frame_seq=frame_seq,
                sequence_epoch=preflight.sequence_epoch,
                agc_revision=self._inspection.state_revision,
                plan_digest=plan.plan_digest,
                command_state=record.state.value,
            )
            return {
                "frame_seq": frame_seq,
                "sequence_epoch": preflight.sequence_epoch,
                "inspection_revision": self._inspection.state_revision,
                "catalog_version": plan.catalog_version,
                "command_id": plan.command_id,
                "keys": list(plan.keys),
                "plan_digest": plan.plan_digest,
                "critical": plan.critical,
                "critical_reasons": [reason.value for reason in plan.critical_reasons],
                "auth_state": record.auth_state.value,
                "postcondition": plan.postcondition.to_json(),
            }

        return await self._run("plan_dsky_sequence", body)

    async def execute_dsky_sequence(self, keys: list[str], frame_seq: int) -> dict[str, Any]:
        async def body(request_id: str) -> dict[str, Any]:
            if self._execute_lock.locked():
                raise BridgeError(ErrorCode.BUSY, "another execution is in progress", retryable=True, frame_seq=frame_seq)
            async with self._execute_lock:
                return await self._execute(request_id, tuple(keys), frame_seq)

        return await self._run("execute_dsky_sequence", body)

    async def _execute(self, request_id: str, keys: tuple[str, ...], frame_seq: int) -> dict[str, Any]:
        await self._reconcile_open_claims()
        record = self._ledger.get(frame_seq)
        if record is not None:
            record = self._expire_if_due(record)
        current: AgcState | None = None
        daemon_execution: dict[str, Any] | None = None
        epoch = self._require_epoch()
        if record is not None and record.state in OPEN_STATES:
            try:
                preflight = await self._call("execution.preflight", {"frame_seq": frame_seq}, _READ_DEADLINE_MS)
            except BridgeError as error:
                raise BridgeError(
                    ErrorCode.AGC_UNAVAILABLE if error.code is ErrorCode.DAEMON_UNAVAILABLE else error.code,
                    f"preflight failed: {error.message}",
                    frame_seq=frame_seq,
                ) from error
            epoch = preflight.sequence_epoch
            current = AgcState.from_snapshot(preflight.result["snapshot"])
            daemon_execution = preflight.result["execution"]
        decision = self._gate.evaluate(
            GateRequest(
                session_id=self.session_id,
                sequence_epoch=epoch,
                frame_seq=frame_seq,
                keys=keys,
                record=record,
                inspection=self._inspection,
                current=current,
                daemon_execution=daemon_execution,
                now=self._clock.now(),
                halted=self.halted,
            )
        )
        if decision.decision is Decision.RECONCILE:
            assert record is not None
            return await self._replay(request_id, record)
        if not decision.allowed:
            assert decision.error is not None
            if decision.expire_command and record is not None:
                record = self._ledger.update(
                    record, state=CommandState.EXPIRED, auth_state=AuthState.EXPIRED, error_code="AUTH_EXPIRED"
                )
            self._audit.emit(
                "gate.decision",
                request_id=request_id,
                frame_seq=frame_seq,
                sequence_epoch=epoch,
                agc_revision=None if current is None else current.state_revision,
                decision="REJECT",
                error_code=decision.error.code.value,
                command_state=None if record is None else record.state.value,
            )
            raise decision.error
        assert record is not None and decision.plan is not None and current is not None
        return await self._actuate(request_id, record, decision.plan, decision.auth_seq, current, epoch)

    async def _actuate(
        self,
        request_id: str,
        record: CommandRecord,
        plan: Plan,
        auth_seq: int | None,
        current: AgcState,
        epoch: str,
    ) -> dict[str, Any]:
        execution_id = self._new_id()
        # Atomic claim: READY/HELD -> EXECUTING and MATCHED -> CONSUMED in one ledger commit.
        record = self._ledger.update(
            record,
            state=CommandState.EXECUTING,
            auth_state=AuthState.CONSUMED if auth_seq is not None else record.auth_state,
            plan_digest=plan.plan_digest,
            execution_id=execution_id,
        )
        self._inspection = None
        try:
            self._audit.emit(
                "gate.decision",
                request_id=request_id,
                frame_seq=record.frame_seq,
                ref_seq=auth_seq,
                sequence_epoch=epoch,
                agc_revision=current.state_revision,
                plan_digest=plan.plan_digest,
                decision="ALLOW",
                command_state=record.state.value,
                details={"critical_reasons": ",".join(plan.critical_reasons)},
                required=True,
            )
        except AuditError as error:
            self._ledger.update(record, state=CommandState.FAILED, error_code=ErrorCode.AUDIT_FAILURE.value)
            raise BridgeError(
                ErrorCode.AUDIT_FAILURE, "allow decision could not be audited; nothing was actuated", frame_seq=record.frame_seq
            ) from error
        params = {
            "operation_id": execution_id,
            "frame_seq": record.frame_seq,
            "catalog_version": plan.catalog_version,
            "plan_digest": plan.plan_digest,
            "keys": list(plan.keys),
            "expected_revision": current.state_revision,
            "min_cadence_ms": 100,
            "auth_seq": auth_seq,
        }
        try:
            reply = await self._call("dsky.execute", params, _EXECUTE_DEADLINE_MS)
            execution = reply.result["execution"]
        except DaemonRejected as rejected:
            # The daemon refused before actuation; the claim stays closed (no retry).
            error = _translate(rejected, record.frame_seq)
            failed = self._ledger.update(record, state=CommandState.FAILED, error_code=error.code.value)
            self._store_result(failed, ok=False, error=error, data=None)
            self._audit.emit(
                "execution.result",
                request_id=request_id,
                frame_seq=record.frame_seq,
                sequence_epoch=epoch,
                plan_digest=plan.plan_digest,
                decision="REJECT",
                error_code=error.code.value,
                command_state=CommandState.FAILED.value,
            )
            raise error from rejected
        except (OutcomeUnknown, BridgeError) as error:
            record = self._ledger.update(record, state=CommandState.OUTCOME_UNKNOWN, error_code="OUTCOME_UNKNOWN")
            self._audit.emit(
                "execution.result",
                request_id=request_id,
                frame_seq=record.frame_seq,
                sequence_epoch=epoch,
                plan_digest=plan.plan_digest,
                decision="RECONCILE",
                error_code="OUTCOME_UNKNOWN",
                command_state=record.state.value,
            )
            execution = await self._reconcile_lookup(record.frame_seq)
            if execution is None:
                self.halted = True
                raise BridgeError(
                    ErrorCode.OUTCOME_UNKNOWN,
                    "execution confirmation lost; reconcile only, never resend",
                    frame_seq=record.frame_seq,
                ) from error
        return await self._finish(request_id, record, plan, execution, epoch)

    async def _reconcile_lookup(self, frame_seq: int) -> dict[str, Any] | None:
        for _ in range(_RECONCILE_ATTEMPTS):
            try:
                reply = await self._call("execution.get", {"frame_seq": frame_seq}, _READ_DEADLINE_MS)
            except (BridgeError, DaemonRejected) as error:
                _LOG.warning("reconcile execution.get seq=%d failed: %s", frame_seq, error)
                await asyncio.sleep(0.2)
                continue
            execution = reply.result["execution"]
            if execution is not None and execution["status"] != "STARTED":
                return execution
            await asyncio.sleep(0.2)
        return None

    async def _apply_reconciled(self, record: CommandRecord, execution: dict[str, Any] | None) -> None:
        if execution is None or execution["status"] == "STARTED":
            # Nothing durable on the daemon side: the attempt stays closed.
            self._ledger.update(record, state=CommandState.FAILED, error_code="OUTCOME_UNKNOWN")
            return
        status = CommandState.EXECUTED if execution["status"] == "EXECUTED" else CommandState.FAILED
        updated = self._ledger.update(record, state=status, error_code=execution["error_code"])
        data = self._result_data(updated, execution, postcondition_matched=None)
        self._store_result(updated, ok=status is CommandState.EXECUTED, error=None if status is CommandState.EXECUTED else BridgeError(ErrorCode.EXECUTION_FAILED, "reconciled failure"), data=data)
        self._audit.emit(
            "reconciliation",
            frame_seq=record.frame_seq,
            sequence_epoch=record.sequence_epoch,
            decision="RECONCILE",
            command_state=status.value,
        )

    def _result_data(
        self, record: CommandRecord, execution: dict[str, Any], postcondition_matched: bool | None
    ) -> dict[str, Any]:
        return {
            "frame_seq": record.frame_seq,
            "execution_id": record.execution_id,
            "status": execution["status"],
            "idempotent_replay": False,
            "plan_digest": execution["plan_digest"],
            "keys_accepted": execution["keys_accepted"],
            "keys_total": execution["keys_total"],
            "started_at": execution["started_at"],
            "finished_at": execution["finished_at"],
            "pre_revision": execution["pre_revision"],
            "post_revision": execution["post_revision"],
            "postcondition_matched": postcondition_matched,
            "daemon_error_code": execution["error_code"],
        }

    def _store_result(
        self, record: CommandRecord, *, ok: bool, error: BridgeError | None, data: dict[str, Any] | None
    ) -> None:
        stored: dict[str, Any] = {"ok": ok, "data": data}
        if error is not None:
            stored["error"] = {"code": error.code.value, "message": error.message, "details": error.details}
        self._ledger.update(record, result=stored)

    async def _finish(
        self,
        request_id: str,
        record: CommandRecord,
        plan: Plan,
        execution: dict[str, Any],
        epoch: str,
    ) -> dict[str, Any]:
        post_reply = await self._call("agc.inspect", {}, _READ_DEADLINE_MS)
        post = AgcState.from_snapshot(post_reply.result)
        matched = execution["status"] == "EXECUTED" and plan.postcondition.matches(post)
        status = CommandState.EXECUTED if matched else CommandState.FAILED
        error: BridgeError | None = None
        if not matched:
            self.halted = True
            code = (
                ErrorCode.EXECUTION_FAILED
                if execution["status"] != "EXECUTED"
                else ErrorCode.POSTCONDITION_MISMATCH
            )
            error = BridgeError(
                code,
                "execution did not reach the canonical postcondition; Flight Watch HALTED",
                frame_seq=record.frame_seq,
                details={
                    "keys_accepted": execution["keys_accepted"],
                    "keys_total": execution["keys_total"],
                    "daemon_error_code": execution["error_code"],
                },
            )
        record = self._ledger.update(record, state=status, error_code=None if error is None else error.code.value)
        data = self._result_data(record, execution, matched)
        self._store_result(record, ok=matched, error=error, data=data)
        self._audit.emit(
            "postcondition.result",
            request_id=request_id,
            frame_seq=record.frame_seq,
            sequence_epoch=epoch,
            agc_revision=post.state_revision,
            plan_digest=plan.plan_digest,
            decision="ALLOW" if matched else "REJECT",
            error_code=None if error is None else error.code.value,
            command_state=status.value,
        )
        if error is not None:
            raise error
        return data

    async def _replay(self, request_id: str, record: CommandRecord) -> dict[str, Any]:
        if record.state in (CommandState.EXECUTING, CommandState.OUTCOME_UNKNOWN):
            execution = await self._reconcile_lookup(record.frame_seq)
            if execution is None:
                raise BridgeError(
                    ErrorCode.OUTCOME_UNKNOWN, "execution outcome still unknown; not resending", frame_seq=record.frame_seq
                )
            await self._apply_reconciled(record, execution)
            refreshed = self._ledger.get(record.frame_seq)
            assert refreshed is not None
            record = refreshed
        self._audit.emit(
            "gate.decision",
            request_id=request_id,
            frame_seq=record.frame_seq,
            sequence_epoch=record.sequence_epoch,
            plan_digest=record.plan_digest,
            decision="RECONCILE",
            command_state=record.state.value,
        )
        stored = record.result or {"ok": False, "data": None, "error": {"code": "EXECUTION_FAILED", "message": "no stored result", "details": {}}}
        if stored["ok"] and stored["data"] is not None:
            return {**stored["data"], "idempotent_replay": True}
        failure = stored.get("error") or {"code": "EXECUTION_FAILED", "message": "failed", "details": {}}
        details = dict(failure.get("details") or {})
        details["idempotent_replay"] = True
        raise BridgeError(
            _DAEMON_CODES.get(failure["code"], ErrorCode.EXECUTION_FAILED),
            f"stored result: {failure['message']}",
            frame_seq=record.frame_seq,
            details=details,
        )

    async def verify_crc16(self, hex_payload: str) -> dict[str, Any]:
        async def body(request_id: str) -> dict[str, Any]:
            if (
                not isinstance(hex_payload, str)
                or len(hex_payload) % 2
                or not 4 <= len(hex_payload) <= 8192
                or not _HEX.match(hex_payload)
            ):
                raise BridgeError(
                    ErrorCode.INVALID_ARGUMENT, "hex_payload must be even-length hex for 2..4096 bytes"
                )
            data = bytes.fromhex(hex_payload)
            computed = crc16_ccitt_false(data[:-2])
            supplied = int.from_bytes(data[-2:], "big")
            return {
                "input_bytes": len(data),
                "algorithm": ALGORITHM,
                "computed_crc_hex": f"{computed:04x}",
                "supplied_crc_hex": f"{supplied:04x}",
                "matches": computed == supplied,
            }

        return await self._run("verify_crc16", body)

    async def close(self) -> None:
        self._marker.release()
        self._audit.emit("session.stop")

