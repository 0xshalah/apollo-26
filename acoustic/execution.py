"""Durable DSKY execution journal (one immutable-until-terminal file per frame_seq)."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Any

from acoustic.telemetry_store import atomic_write_json

_LOG = logging.getLogger(__name__)
_NAME = re.compile(r"^([0-9]{1,10})\.json$")


class ExecutionStatus(StrEnum):
    STARTED = "STARTED"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"


class ExecutionErrorCode(StrEnum):
    KEY_REL_ACTIVE = "KEY_REL_ACTIVE"
    OPR_ERR_ACTIVE = "OPR_ERR_ACTIVE"
    KEY_REJECTED = "KEY_REJECTED"
    INTERRUPTED = "INTERRUPTED"


@dataclass(frozen=True, slots=True)
class ExecutionRecord:
    frame_seq: int
    operation_id: str
    plan_digest: str
    catalog_version: str
    status: ExecutionStatus
    keys_total: int
    keys_accepted: int
    auth_seq: int | None
    started_at: str
    finished_at: str | None
    pre_revision: int
    post_revision: int | None
    error_code: ExecutionErrorCode | None

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["error_code"] = None if self.error_code is None else self.error_code.value
        return data

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> ExecutionRecord:
        return cls(
            frame_seq=int(data["frame_seq"]),
            operation_id=str(data["operation_id"]),
            plan_digest=str(data["plan_digest"]),
            catalog_version=str(data["catalog_version"]),
            status=ExecutionStatus(data["status"]),
            keys_total=int(data["keys_total"]),
            keys_accepted=int(data["keys_accepted"]),
            auth_seq=None if data["auth_seq"] is None else int(data["auth_seq"]),
            started_at=str(data["started_at"]),
            finished_at=None if data["finished_at"] is None else str(data["finished_at"]),
            pre_revision=int(data["pre_revision"]),
            post_revision=None if data["post_revision"] is None else int(data["post_revision"]),
            error_code=None if data["error_code"] is None else ExecutionErrorCode(data["error_code"]),
        )


class ExecutionJournal:
    """Filesystem journal; one record per frame sequence, written atomically."""

    def __init__(self, directory: Path, validate: Any) -> None:
        self._dir = directory
        self._validate = validate
        self._records: dict[int, ExecutionRecord] = {}
        directory.mkdir(parents=True, exist_ok=True)

    def load(self, finished_at: str) -> list[ExecutionRecord]:
        """Load records; STARTED entries from a previous process are closed as INTERRUPTED.

        AGC state is process-local, so an execution that was running when the
        daemon stopped can never complete; it stays closed (never retried).
        """

        interrupted: list[ExecutionRecord] = []
        for entry in sorted(self._dir.iterdir()):
            if not _NAME.match(entry.name):
                continue
            data = json.loads(entry.read_text(encoding="utf-8"))
            self._validate(data)
            record = ExecutionRecord.from_json(data)
            if record.status is ExecutionStatus.STARTED:
                record = replace(
                    record,
                    status=ExecutionStatus.FAILED,
                    finished_at=finished_at,
                    error_code=ExecutionErrorCode.INTERRUPTED,
                )
                self.put(record)
                interrupted.append(record)
                _LOG.warning("execution seq=%d closed as INTERRUPTED after restart", record.frame_seq)
            self._records[record.frame_seq] = record
        return interrupted

    def get(self, frame_seq: int) -> ExecutionRecord | None:
        return self._records.get(frame_seq)

    def auth_in_use(self, auth_seq: int) -> bool:
        return any(record.auth_seq == auth_seq for record in self._records.values())

    def put(self, record: ExecutionRecord) -> None:
        payload = record.to_json()
        self._validate(payload)
        atomic_write_json(self._dir / f"{record.frame_seq}.json", payload)
        self._records[record.frame_seq] = record
