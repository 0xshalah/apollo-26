"""Explicit, fail-closed sequence persistence boundary."""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

from acoustic.frame import MAX_SEQUENCE, SequenceAccessError

SEQUENCE_SCHEMA_VERSION: Final = "1.0"


class SequenceStatus(StrEnum):
    UNINITIALIZED = "UNINITIALIZED"
    READY = "READY"
    EXHAUSTED = "EXHAUSTED"
    DEGRADED = "DEGRADED"


class SequenceErrorCode(StrEnum):
    MISSING = "MISSING"
    UNREADABLE = "UNREADABLE"
    MALFORMED = "MALFORMED"
    UNSUPPORTED_VERSION = "UNSUPPORTED_VERSION"
    OUT_OF_RANGE = "OUT_OF_RANGE"
    NOT_LOADED = "NOT_LOADED"
    REPLAY = "REPLAY"
    EXHAUSTED = "EXHAUSTED"
    COMMIT = "COMMIT"
    PROVISION = "PROVISION"


class SequenceStoreError(SequenceAccessError):
    """Stable adapter error without exposing file contents or key material."""

    def __init__(self, code: SequenceErrorCode, operation: str, path: Path) -> None:
        super().__init__(f"sequence {operation} failed: {code.value} ({path})")
        self.code = code
        self.operation = operation
        self.path = path


@dataclass(frozen=True, slots=True)
class SequenceState:
    schema_version: str
    last_accepted_seq: int

    def __post_init__(self) -> None:
        if self.schema_version != SEQUENCE_SCHEMA_VERSION:
            raise ValueError("unsupported sequence schema version")
        if (
            type(self.last_accepted_seq) is not int
            or not 0 <= self.last_accepted_seq <= MAX_SEQUENCE
        ):
            raise ValueError("last_accepted_seq is outside uint32 domain")


class FileSequenceStore:
    """Single-owner JSON store using flush, close, and same-directory replace."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self._path = Path(path)
        self._state: SequenceState | None = None
        self._status = SequenceStatus.UNINITIALIZED

    @property
    def path(self) -> Path:
        return self._path

    @property
    def status(self) -> SequenceStatus:
        return self._status

    @property
    def last_accepted_seq(self) -> int:
        if self._state is None:
            raise SequenceStoreError(SequenceErrorCode.NOT_LOADED, "read", self._path)
        return self._state.last_accepted_seq

    def provision(self, last_accepted_seq: int = 0) -> SequenceState:
        """Explicitly create or replace state; normal loading never auto-provisions."""

        try:
            state = SequenceState(SEQUENCE_SCHEMA_VERSION, last_accepted_seq)
        except ValueError as error:
            self._degrade()
            raise SequenceStoreError(
                SequenceErrorCode.OUT_OF_RANGE, "provision", self._path
            ) from error
        try:
            self._atomic_write(state, "provision", SequenceErrorCode.PROVISION)
        except SequenceStoreError:
            self._degrade()
            raise
        self._set_state(state)
        return state

    def load(self) -> SequenceState:
        """Load and validate existing state, degrading on every unsafe condition."""

        self._degrade()
        try:
            text = self._path.read_text(encoding="utf-8")
        except FileNotFoundError as error:
            raise SequenceStoreError(SequenceErrorCode.MISSING, "load", self._path) from error
        except OSError as error:
            raise SequenceStoreError(SequenceErrorCode.UNREADABLE, "load", self._path) from error

        try:
            value = json.loads(text)
        except json.JSONDecodeError as error:
            raise SequenceStoreError(SequenceErrorCode.MALFORMED, "load", self._path) from error
        if type(value) is not dict or set(value) != {"schema_version", "last_accepted_seq"}:
            raise SequenceStoreError(SequenceErrorCode.MALFORMED, "load", self._path)
        if value["schema_version"] != SEQUENCE_SCHEMA_VERSION:
            raise SequenceStoreError(
                SequenceErrorCode.UNSUPPORTED_VERSION, "load", self._path
            )
        sequence = value["last_accepted_seq"]
        if type(sequence) is not int or not 0 <= sequence <= MAX_SEQUENCE:
            raise SequenceStoreError(SequenceErrorCode.OUT_OF_RANGE, "load", self._path)

        state = SequenceState(SEQUENCE_SCHEMA_VERSION, sequence)
        self._set_state(state)
        return state

    def commit(self, next_seq: int) -> None:
        """Persist a strictly newer sequence and fail closed on write errors."""

        if self._state is None:
            raise SequenceStoreError(SequenceErrorCode.NOT_LOADED, "commit", self._path)
        if self._state.last_accepted_seq == MAX_SEQUENCE:
            self._status = SequenceStatus.EXHAUSTED
            raise SequenceStoreError(SequenceErrorCode.EXHAUSTED, "commit", self._path)
        if type(next_seq) is not int or not 1 <= next_seq <= MAX_SEQUENCE:
            raise SequenceStoreError(SequenceErrorCode.OUT_OF_RANGE, "commit", self._path)
        if next_seq <= self._state.last_accepted_seq:
            raise SequenceStoreError(SequenceErrorCode.REPLAY, "commit", self._path)

        next_state = SequenceState(SEQUENCE_SCHEMA_VERSION, next_seq)
        try:
            self._atomic_write(next_state, "commit", SequenceErrorCode.COMMIT)
        except SequenceStoreError:
            self._degrade()
            raise
        self._set_state(next_state)

    def _set_state(self, state: SequenceState) -> None:
        self._state = state
        self._status = (
            SequenceStatus.EXHAUSTED
            if state.last_accepted_seq == MAX_SEQUENCE
            else SequenceStatus.READY
        )

    def _degrade(self) -> None:
        self._state = None
        self._status = SequenceStatus.DEGRADED

    def _atomic_write(
        self,
        state: SequenceState,
        operation: str,
        error_code: SequenceErrorCode,
    ) -> None:
        payload = json.dumps(
            {
                "schema_version": state.schema_version,
                "last_accepted_seq": state.last_accepted_seq,
            },
            separators=(",", ":"),
            sort_keys=True,
        ) + "\n"
        descriptor: int | None = None
        temporary_path: Path | None = None
        try:
            descriptor, temporary_name = tempfile.mkstemp(
                dir=self._path.parent,
                prefix=f".{self._path.name}.",
                suffix=".tmp",
                text=True,
            )
            temporary_path = Path(temporary_name)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                descriptor = None
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self._path)
            temporary_path = None
        except OSError as error:
            if descriptor is not None:
                os.close(descriptor)
            if temporary_path is not None:
                with contextlib.suppress(OSError):
                    temporary_path.unlink(missing_ok=True)
            raise SequenceStoreError(error_code, operation, self._path) from error
