"""Durable Flight Watch cursor + COMMAND/AUTH lifecycle ledger.

The whole ledger is one JSON document written via temp file + atomic rename,
so a cursor advance and the lifecycle ingestion it implies commit together.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from typing import Any, Final, Protocol

SCHEMA_VERSION: Final = "1.0"


class CommandState(StrEnum):
    HELD = "HELD"
    READY = "READY"
    EXECUTING = "EXECUTING"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"


OPEN_STATES: Final = frozenset({CommandState.HELD, CommandState.READY})
CLAIMED_STATES: Final = frozenset(
    {CommandState.EXECUTING, CommandState.EXECUTED, CommandState.FAILED, CommandState.OUTCOME_UNKNOWN}
)


class AuthState(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    REQUIRED = "REQUIRED"
    MATCHED = "MATCHED"
    CONSUMED = "CONSUMED"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True, slots=True)
class CommandRecord:
    frame_seq: int
    sequence_epoch: str
    frame: dict[str, Any]
    received_at: str
    delivered_at: str
    state: CommandState
    auth_state: AuthState
    critical_reasons: tuple[str, ...] = ()
    auth_seq: int | None = None
    plan_digest: str | None = None
    execution_id: str | None = None
    result: dict[str, Any] | None = None
    error_code: str | None = None

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["state"] = self.state.value
        data["auth_state"] = self.auth_state.value
        data["critical_reasons"] = list(self.critical_reasons)
        return data

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> CommandRecord:
        return cls(
            frame_seq=int(data["frame_seq"]),
            sequence_epoch=str(data["sequence_epoch"]),
            frame=dict(data["frame"]),
            received_at=str(data["received_at"]),
            delivered_at=str(data["delivered_at"]),
            state=CommandState(data["state"]),
            auth_state=AuthState(data["auth_state"]),
            critical_reasons=tuple(data["critical_reasons"]),
            auth_seq=data["auth_seq"],
            plan_digest=data["plan_digest"],
            execution_id=data["execution_id"],
            result=data["result"],
            error_code=data["error_code"],
        )


@dataclass
class LedgerState:
    daemon_epoch: str | None = None
    cursor_seq: int = 0
    commands: dict[int, CommandRecord] = field(default_factory=dict)


class LedgerPersistence(Protocol):
    def load(self) -> LedgerState: ...

    def save(self, state: LedgerState) -> None: ...


class LedgerError(RuntimeError):
    pass


class FileLedgerPersistence:
    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> LedgerState:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return LedgerState()
        except (OSError, json.JSONDecodeError) as error:
            raise LedgerError(f"ledger {self._path} unreadable") from error
        if data.get("schema_version") != SCHEMA_VERSION:
            raise LedgerError("unsupported ledger schema_version")
        return LedgerState(
            daemon_epoch=data["daemon_epoch"],
            cursor_seq=int(data["cursor_seq"]),
            commands={int(k): CommandRecord.from_json(v) for k, v in data["commands"].items()},
        )

    def save(self, state: LedgerState) -> None:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "daemon_epoch": state.daemon_epoch,
            "cursor_seq": state.cursor_seq,
            "commands": {str(k): v.to_json() for k, v in sorted(state.commands.items())},
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(dir=self._path.parent, prefix=f".{self._path.name}.", suffix=".tmp")
        temporary: Path | None = Path(name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(name, self._path)
            temporary = None
        finally:
            if temporary is not None:
                with contextlib.suppress(OSError):
                    temporary.unlink(missing_ok=True)


class MemoryLedgerPersistence:
    def __init__(self) -> None:
        self.saved: LedgerState | None = None
        self.fail_next_save = False

    def load(self) -> LedgerState:
        if self.saved is None:
            return LedgerState()
        return LedgerState(self.saved.daemon_epoch, self.saved.cursor_seq, dict(self.saved.commands))

    def save(self, state: LedgerState) -> None:
        if self.fail_next_save:
            self.fail_next_save = False
            raise OSError("injected ledger write failure")
        self.saved = LedgerState(state.daemon_epoch, state.cursor_seq, dict(state.commands))


class Ledger:
    """Transactional view: mutate a copy, persist, then publish in memory."""

    def __init__(self, persistence: LedgerPersistence) -> None:
        self._persistence = persistence
        self._state = persistence.load()

    @property
    def epoch(self) -> str | None:
        return self._state.daemon_epoch

    @property
    def cursor(self) -> int:
        return self._state.cursor_seq

    def get(self, frame_seq: int) -> CommandRecord | None:
        return self._state.commands.get(frame_seq)

    def records(self) -> list[CommandRecord]:
        return list(self._state.commands.values())

    def commit(
        self,
        *,
        updates: list[CommandRecord] | None = None,
        cursor: int | None = None,
        epoch: str | None = None,
        reset: bool = False,
    ) -> None:
        commands = {} if reset else dict(self._state.commands)
        for record in updates or []:
            commands[record.frame_seq] = record
        candidate = LedgerState(
            daemon_epoch=self._state.daemon_epoch if epoch is None else epoch,
            cursor_seq=self._state.cursor_seq if cursor is None else cursor,
            commands=commands,
        )
        try:
            self._persistence.save(candidate)
        except OSError as error:
            raise LedgerError("ledger persistence failed") from error
        self._state = candidate

    def update(self, record: CommandRecord, **changes: Any) -> CommandRecord:
        updated = replace(record, **changes)
        self.commit(updates=[updated])
        return updated
