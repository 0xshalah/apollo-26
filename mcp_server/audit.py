"""Immutable audit events (``contracts/mcp-audit-event.schema.json``), one file each."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Protocol

from mcp_server.clock import Clock, format_timestamp
from mcp_server.contracts import BridgeContracts, SchemaError

_LOG = logging.getLogger(__name__)


class AuditError(RuntimeError):
    pass


class AuditWriter(Protocol):
    def write(self, event_id: int, event: dict[str, Any]) -> None: ...


class FileAuditWriter:
    def __init__(self, directory: Path) -> None:
        self._dir = directory

    def write(self, event_id: int, event: dict[str, Any]) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        final = self._dir / f"{event_id:08d}.json"
        if final.exists():
            raise AuditError(f"audit event {event_id} already exists")
        descriptor, name = tempfile.mkstemp(dir=self._dir, prefix=".evt.", suffix=".tmp")
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(event, handle, sort_keys=True, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(name, final)
        except OSError as error:
            with contextlib.suppress(OSError):
                Path(name).unlink(missing_ok=True)
            raise AuditError(f"cannot persist audit event {event_id}") from error


class MemoryAuditWriter:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.fail = False

    def write(self, event_id: int, event: dict[str, Any]) -> None:
        if self.fail:
            raise AuditError("injected audit failure")
        self.events.append(event)


class AuditSink:
    def __init__(
        self, writer: AuditWriter, contracts: BridgeContracts, clock: Clock, session_id: str
    ) -> None:
        self._writer = writer
        self._contracts = contracts
        self._clock = clock
        self._session_id = session_id
        self._next_id = 1

    def emit(
        self,
        event_type: str,
        *,
        request_id: str | None = None,
        frame_seq: int | None = None,
        ref_seq: int | None = None,
        sequence_epoch: str | None = None,
        agc_revision: int | None = None,
        plan_digest: str | None = None,
        decision: str | None = None,
        error_code: str | None = None,
        command_state: str | None = None,
        details: dict[str, str | int | bool | None] | None = None,
        required: bool = False,
    ) -> None:
        """Publish one event; ``required`` events raise ``AuditError`` on failure."""

        event = {
            "schema_version": "1.0",
            "session_id": self._session_id,
            "event_id": self._next_id,
            "timestamp": format_timestamp(self._clock.now()),
            "event_type": event_type,
            "request_id": request_id,
            "frame_seq": frame_seq,
            "ref_seq": ref_seq,
            "sequence_epoch": sequence_epoch,
            "agc_revision": agc_revision,
            "plan_digest": plan_digest,
            "decision": decision,
            "error_code": error_code,
            "command_state": command_state,
            "details": dict(details or {}),
        }
        try:
            self._contracts.validate_audit(event)
            self._writer.write(self._next_id, event)
        except (AuditError, SchemaError, OSError) as error:
            _LOG.error("audit %s for frame %s failed: %s", event_type, frame_seq, error)
            if required:
                raise AuditError(str(error)) from error
            return
        self._next_id += 1
