"""Stable bridge error codes (mcp-bridge design, Error Handling table)."""

from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    SCHEMA_VERSION = "SCHEMA_VERSION"
    RPC_PROTOCOL = "RPC_PROTOCOL"
    DAEMON_UNAVAILABLE = "DAEMON_UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    FLIGHT_WATCH_BUSY = "FLIGHT_WATCH_BUSY"
    FLIGHT_WATCH_HALTED = "FLIGHT_WATCH_HALTED"
    NOT_FOUND = "NOT_FOUND"
    SEQUENCE_EPOCH_CHANGED = "SEQUENCE_EPOCH_CHANGED"
    INSPECTION_REQUIRED = "INSPECTION_REQUIRED"
    INSPECTION_STALE = "INSPECTION_STALE"
    AGC_UNAVAILABLE = "AGC_UNAVAILABLE"
    KEY_REL_ACTIVE = "KEY_REL_ACTIVE"
    OPR_ERR_ACTIVE = "OPR_ERR_ACTIVE"
    UNSUPPORTED_COMMAND = "UNSUPPORTED_COMMAND"
    CATALOG_MISMATCH = "CATALOG_MISMATCH"
    PLAN_MISMATCH = "PLAN_MISMATCH"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    AUTH_INVALID = "AUTH_INVALID"
    AUTH_EXPIRED = "AUTH_EXPIRED"
    AUTH_USED = "AUTH_USED"
    STATE = "STATE"
    COMMAND_CLOSED = "COMMAND_CLOSED"
    BUSY = "BUSY"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"
    POSTCONDITION_MISMATCH = "POSTCONDITION_MISMATCH"
    AUDIT_FAILURE = "AUDIT_FAILURE"
    INTERNAL = "INTERNAL"


type DetailValue = str | int | bool | None


class BridgeError(Exception):
    """Expected domain rejection; surfaced as a structured ``ok:false`` tool result."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        retryable: bool = False,
        frame_seq: int | None = None,
        details: dict[str, DetailValue] | None = None,
    ) -> None:
        super().__init__(f"{code.value}: {message}")
        self.code = code
        self.message = message
        self.retryable = retryable
        self.frame_seq = frame_seq
        self.details: dict[str, DetailValue] = dict(details or {})
