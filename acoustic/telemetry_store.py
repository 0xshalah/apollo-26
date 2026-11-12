"""Telemetry records (``contracts/telemetry-frame.schema.json``) and their atomic store.

Accepted path (acoustic-link design §10.2):
    stage ``inbox/.<seq>.json.staged`` -> commit sequence -> promote to ``inbox/<seq>.json``.
Rejected records are immutable files with unique names under ``rejected/``.
Every write is temp file + flush + fsync + ``os.replace`` in the same directory.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Final

from acoustic.audio import SourceMetadata
from acoustic.clock import format_timestamp
from acoustic.frame import (
    FRAME_SIZE,
    AuthFrame,
    CommandFrame,
    Frame,
    FrameType,
    RejectReason,
    ValidationChecks,
)
from acoustic.schemas import ContractSchemas

_LOG = logging.getLogger(__name__)
SCHEMA_VERSION: Final = "1.0"
_FINAL_NAME = re.compile(r"^([0-9]{1,10})\.json$")
_STAGED_NAME = re.compile(r"^\.([0-9]{1,10})\.json\.staged$")


class TelemetryStoreError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def _frame_object(frame: Frame, raw: bytes) -> dict[str, Any]:
    frame_type = "COMMAND" if frame.frame_type is FrameType.COMMAND else "AUTH"
    return {
        "version": 1,
        "frame_type": frame_type,
        "seq": frame.seq,
        "ref_seq": frame.ref_seq,
        "critical": frame.critical,
        "verb": frame.verb,
        "noun": frame.noun,
        "program": frame.program,
        "r1_centidegrees": frame.r1_centidegrees,
        "r2_centidegrees": frame.r2_centidegrees,
        "delta_v_tenths_fps": frame.delta_v_tenths_fps,
        "hmac_hex": raw[24:32].hex(),
        "crc_hex": raw[32:34].hex(),
        "raw_hex": raw.hex(),
    }


def _validation_object(checks: ValidationChecks | None, *, sync_ok: bool) -> dict[str, Any]:
    if checks is None:
        # Modem-level loss: no complete 34-byte candidate reached the codec.
        return {
            "length": False,
            "sync": sync_ok,
            "crc": None,
            "hmac": None,
            "sequence": None,
            "range": None,
        }
    return {
        "length": checks.length,
        "sync": bool(checks.sync),
        "crc": checks.crc,
        "hmac": checks.hmac,
        "sequence": checks.sequence,
        "range": checks.range,
    }


def build_record(
    *,
    received_at: datetime,
    source: SourceMetadata,
    frequency_deviation_hz: float | None,
    raw: bytes | None,
    frame: Frame | None,
    checks: ValidationChecks | None,
    reason: RejectReason | None,
    modem_sync_ok: bool = False,
) -> dict[str, Any]:
    """Project a validation outcome onto the telemetry contract.

    ``frame`` is populated only for accepted frames: rejected bytes are untrusted
    and the reason code plus ``validation`` checks carry the audit evidence.
    ``frequency_deviation_hz`` is required by the schema; when the modem could not
    qualify an estimate the record carries ``0.0`` and ``snr_db`` stays null
    (UNMEASURED) -- see the mcp-bridge implementation notes.
    """

    accepted = reason is None
    if accepted and (frame is None or raw is None or len(raw) != FRAME_SIZE):
        raise ValueError("accepted records require frame and 34 raw bytes")
    return {
        "schema_version": SCHEMA_VERSION,
        "received_at": format_timestamp(received_at),
        "source": {
            "kind": source.kind.value,
            "sample_rate_hz": source.sample_rate,
            "snr_db": None,
            "frequency_deviation_hz": round(float(frequency_deviation_hz or 0.0), 3),
        },
        "frame": _frame_object(frame, raw) if accepted and frame and raw else None,
        "validation": _validation_object(checks, sync_ok=modem_sync_ok),
        "verdict": "ACCEPTED" if accepted else "REJECTED",
        "reason": "OK" if accepted else reason.value,  # type: ignore[union-attr]
    }


def frame_from_record(record: dict[str, Any]) -> Frame:
    """Rebuild a typed frame from an already schema-validated accepted record."""

    data = record["frame"]
    if data["frame_type"] == "AUTH":
        return AuthFrame(seq=data["seq"], ref_seq=data["ref_seq"])
    return CommandFrame(
        seq=data["seq"],
        critical=data["critical"],
        verb=data["verb"],
        noun=data["noun"],
        program=data["program"],
        r1_centidegrees=data["r1_centidegrees"],
        r2_centidegrees=data["r2_centidegrees"],
        delta_v_tenths_fps=data["delta_v_tenths_fps"],
    )


def atomic_write_json(path: Path, payload: object) -> None:
    """Write JSON through a same-directory temp file and atomic replace."""

    text = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    descriptor: int | None = None
    temporary: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
        temporary = Path(name)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            descriptor = None
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary is not None:
            with contextlib.suppress(OSError):
                temporary.unlink(missing_ok=True)


@dataclass(frozen=True, slots=True)
class StagedRecord:
    seq: int
    path: Path
    record: dict[str, Any]


class TelemetryStore:
    """Filesystem adapter for ``telemetry/inbox`` and ``telemetry/rejected``."""

    def __init__(self, inbox_dir: Path, rejected_dir: Path, schemas: ContractSchemas, writer_id: str) -> None:
        self._inbox = inbox_dir
        self._rejected = rejected_dir
        self._schemas = schemas
        self._writer_id = writer_id[:8]
        self._counter = 0
        inbox_dir.mkdir(parents=True, exist_ok=True)
        rejected_dir.mkdir(parents=True, exist_ok=True)

    @property
    def inbox_dir(self) -> Path:
        return self._inbox

    @property
    def rejected_dir(self) -> Path:
        return self._rejected

    def stage_accepted(self, seq: int, record: dict[str, Any]) -> StagedRecord:
        self._schemas.validate_telemetry(record)
        path = self._inbox / f".{seq}.json.staged"
        try:
            atomic_write_json(path, record)
        except OSError as error:
            raise TelemetryStoreError("INBOX_STAGE", f"cannot stage seq {seq}") from error
        return StagedRecord(seq, path, record)

    def discard(self, staged: StagedRecord) -> None:
        with contextlib.suppress(FileNotFoundError):
            staged.path.unlink()

    def promote(self, staged: StagedRecord) -> Path:
        final = self._inbox / f"{staged.seq}.json"
        try:
            os.replace(staged.path, final)
        except OSError as error:
            raise TelemetryStoreError("INBOX_PROMOTE", f"cannot promote seq {staged.seq}") from error
        return final

    def write_rejected(self, record: dict[str, Any], received_at: datetime) -> Path:
        self._schemas.validate_telemetry(record)
        self._counter += 1
        stamp = int(received_at.timestamp() * 1000)
        name = f"{stamp:013d}-{self._writer_id}-{self._counter:06d}-{record['reason']}.json"
        path = self._rejected / name
        try:
            atomic_write_json(path, record)
        except OSError as error:
            raise TelemetryStoreError("AUDIT_WRITE_FAILED", f"cannot write {name}") from error
        return path

    def recover(self, last_accepted_seq: int) -> list[int]:
        """Resolve staged records left by a crash; returns promoted sequences.

        A staged record equal to the persisted sequence without a final file is
        promoted once.  A staged record newer than the persisted sequence was never
        committed and is discarded.  Anything else is redundant and removed.
        """

        promoted: list[int] = []
        for entry in sorted(self._inbox.iterdir()):
            match = _STAGED_NAME.match(entry.name)
            if not match:
                continue
            seq = int(match.group(1))
            final = self._inbox / f"{seq}.json"
            if seq == last_accepted_seq and not final.exists():
                record = json.loads(entry.read_text(encoding="utf-8"))
                self._schemas.validate_telemetry(record)
                os.replace(entry, final)
                promoted.append(seq)
                _LOG.warning("recovered staged inbox record seq=%d", seq)
            else:
                entry.unlink()
                _LOG.warning("discarded uncommitted/redundant staged record seq=%d", seq)
        return promoted

    def load_accepted(self, limit: int = 10_000) -> list[dict[str, Any]]:
        """Load final inbox records (schema-validated), sorted by sequence."""

        sequences: list[int] = []
        for entry in self._inbox.iterdir():
            match = _FINAL_NAME.match(entry.name)
            if match:
                sequences.append(int(match.group(1)))
        records: list[dict[str, Any]] = []
        for seq in sorted(sequences)[-limit:]:
            path = self._inbox / f"{seq}.json"
            record = json.loads(path.read_text(encoding="utf-8"))
            self._schemas.validate_telemetry(record)
            if record["verdict"] != "ACCEPTED" or record["frame"]["seq"] != seq:
                raise TelemetryStoreError("INBOX_CORRUPT", f"{path.name} does not match its name")
            records.append(record)
        return records
