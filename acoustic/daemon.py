"""Apollo-26 acoustic daemon: composition root, pipeline orchestration, local RPC, CLI.

Pipeline:  AudioSource -> StreamingReceiver -> validate_frame (pure pre-check)
-> stage inbox -> validate_and_commit_frame (FileSequenceStore) -> promote inbox
-> publish (RPC waiters + WebSocket).  Rejections become immutable files in
``telemetry/rejected``.  The daemon hosts the single AgcEngine writer and
refuses any ``dsky.execute`` that is not canonical and authorized.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import os
import shutil
import sys
import uuid
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

import numpy as np

from acoustic.agc_host import AgcHost
from acoustic.audio import (
    AudioSource,
    AudioSourceError,
    LoopbackSource,
    MicrophoneSource,
    SourceMetadata,
    WavFileSource,
    decode_wav_bytes,
)
from acoustic.clock import Clock, SystemClock, format_timestamp, parse_timestamp
from acoustic.command_catalog import CommandCatalog, CommandFields, PlanError
from acoustic.config import (
    LOOPBACK_HOST,
    ConfigError,
    load_key_material,
    merged_environment,
    require_loopback_host,
    require_port,
)
from acoustic.execution import ExecutionJournal, ExecutionRecord, ExecutionStatus
from acoustic.frame import (
    KeyMaterial,
    RejectReason,
    Verdict,
    validate_and_commit_frame,
    validate_frame,
)
from acoustic.modem import DemodulatorConfig, FrequencyAnomaly
from acoustic.modem import SourceKind as ModemSourceKind
from acoustic.receiver import (
    AnomalyEvent,
    CandidateEvent,
    CandidateLoss,
    CarrierEvent,
    LostCandidateEvent,
    ReceiverEvent,
    StreamingReceiver,
)
from acoustic.rpc_server import RpcError, RpcServer
from acoustic.schemas import ContractSchemas, ContractViolation, load_catalog_document
from acoustic.sequence import FileSequenceStore, SequenceStoreError
from acoustic.telemetry_store import (
    TelemetryStore,
    TelemetryStoreError,
    atomic_write_json,
    build_record,
)
from acoustic.web import EventBus, WebServer
from agc_core import COMP_ACTY_PERIOD_MS, AgcEngine

_LOG = logging.getLogger("apollo26.daemon")
DEFAULT_HTTP_PORT: Final = 8026
DEFAULT_RPC_PORT: Final = 8027
IDENTITY_SCHEMA_VERSION: Final = "1.0"
AUDIT_BACKFILL_LIMIT: Final = 500
_READ_BUDGET_BYTES: Final = 56 * 1024
_SPECTRUM_FFT: Final = 2048
_SPECTRUM_MAX_HZ: Final = 4000.0


class DaemonErrorCode(StrEnum):
    SEQUENCE_MISSING = "SEQUENCE_MISSING"
    SEQUENCE_STATE = "SEQUENCE_STATE"
    IDENTITY = "IDENTITY"
    RECOVERY_CONFLICT = "RECOVERY_CONFLICT"


class DaemonStartupError(RuntimeError):
    def __init__(self, code: DaemonErrorCode, message: str) -> None:
        super().__init__(f"{code.value}: {message}")
        self.code = code


class ComponentStatus(StrEnum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    STOPPED = "STOPPED"


@dataclass(frozen=True, slots=True)
class DaemonPaths:
    telemetry_dir: Path

    @property
    def inbox(self) -> Path:
        return self.telemetry_dir / "inbox"

    @property
    def rejected(self) -> Path:
        return self.telemetry_dir / "rejected"

    @property
    def state(self) -> Path:
        return self.telemetry_dir / "state"

    @property
    def sequence_file(self) -> Path:
        return self.state / "sequence.json"

    @property
    def identity_file(self) -> Path:
        return self.state / "daemon-identity.json"

    @property
    def executions_root(self) -> Path:
        return self.state / "executions"

    @property
    def archive(self) -> Path:
        return self.state / "archive"


@dataclass
class SourceSummary:
    kind: str
    sample_rate_hz: int
    accepted_seqs: list[int] = field(default_factory=list)
    rejected_reasons: list[str] = field(default_factory=list)
    anomalies: int = 0

    def to_json(self) -> dict[str, Any]:
        return {
            "source": self.kind,
            "sample_rate_hz": self.sample_rate_hz,
            "accepted_seqs": self.accepted_seqs,
            "rejected_reasons": self.rejected_reasons,
            "frequency_anomalies": self.anomalies,
        }


def _read_identity(path: Path) -> str | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as error:
        raise DaemonStartupError(DaemonErrorCode.IDENTITY, f"unreadable {path.name}") from error
    if (
        not isinstance(data, dict)
        or data.get("schema_version") != IDENTITY_SCHEMA_VERSION
        or not isinstance(data.get("sequence_epoch"), str)
    ):
        raise DaemonStartupError(DaemonErrorCode.IDENTITY, f"malformed {path.name}")
    return str(uuid.UUID(data["sequence_epoch"]))


def load_test_summary(path: Path, schemas: ContractSchemas) -> dict[str, Any] | None:
    """Read the test-runner summary (``scripts/write_test_summary.py`` output) once at startup.

    Returns ``None`` when the file is absent or does not match the ``test.summary``
    event contract; the console then shows UNMEASURED instead of a guessed result.
    """

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        _LOG.info("no test summary at %s; console shows UNMEASURED", path)
        return None
    except (OSError, json.JSONDecodeError) as error:
        _LOG.warning("ignoring unreadable test summary %s: %s", path, error)
        return None
    probe = {
        "schema_version": "1.0",
        "event_id": 1,
        "timestamp": "2026-01-01T00:00:00.000Z",
        "type": "test.summary",
        "data": data,
    }
    try:
        schemas.validate_ws_event(probe)
    except ContractViolation as error:
        _LOG.warning("ignoring test summary %s that violates the event contract: %s", path, error)
        return None
    return dict(data)


def provision_sequence(paths: DaemonPaths, last_accepted_seq: int, new_epoch: str) -> Path | None:
    """Explicit reprovisioning: archive old evidence, start a new epoch, write sequence.

    Old inbox records and execution journals move to ``state/archive/<old-epoch>``
    so reused sequence numbers can never be confused with pre-reset frames.
    """

    paths.state.mkdir(parents=True, exist_ok=True)
    paths.inbox.mkdir(parents=True, exist_ok=True)
    old_epoch = _read_identity(paths.identity_file) or "unversioned"
    archived: Path | None = None
    movable = [entry for entry in paths.inbox.iterdir() if entry.name.endswith((".json", ".staged"))]
    if movable or paths.executions_root.exists():
        archived = paths.archive / old_epoch
        suffix = 0
        while archived.exists():
            suffix += 1
            archived = paths.archive / f"{old_epoch}-{suffix}"
        (archived / "inbox").mkdir(parents=True)
        for entry in movable:
            shutil.move(str(entry), str(archived / "inbox" / entry.name))
        if paths.executions_root.exists():
            shutil.move(str(paths.executions_root), str(archived / "executions"))
    atomic_write_json(
        paths.identity_file,
        {"schema_version": IDENTITY_SCHEMA_VERSION, "sequence_epoch": new_epoch},
    )
    FileSequenceStore(paths.sequence_file).provision(last_accepted_seq)
    return archived


class Daemon:
    """Single-process owner of acceptance, sequence, AGC state, and local listeners."""

    def __init__(
        self,
        *,
        paths: DaemonPaths,
        keys: KeyMaterial,
        clock: Clock,
        schemas: ContractSchemas,
        catalog: CommandCatalog,
        instance_id: str,
        host: str = LOOPBACK_HOST,
        web_port: int | None = DEFAULT_HTTP_PORT,
        rpc_port: int | None = DEFAULT_RPC_PORT,
        static_dir: Path | None = None,
        loopback_source: LoopbackSource | None = None,
        comp_acty_ticks: bool = True,
        new_epoch: str | None = None,
        test_summary: dict[str, Any] | None = None,
    ) -> None:
        self._paths = paths
        self._keys = keys
        self._clock = clock
        self._schemas = schemas
        self._catalog = catalog
        self._instance_id = str(uuid.UUID(instance_id))
        self._host_name = require_loopback_host(host)
        self._web_port = None if web_port is None else require_port(web_port)
        self._rpc_port = None if rpc_port is None else require_port(rpc_port)
        self._static_dir = static_dir
        self._loopback = loopback_source
        self._comp_acty_ticks = comp_acty_ticks
        self._new_epoch = new_epoch or str(uuid.uuid4())
        self._test_summary = None if test_summary is None else dict(test_summary)
        self._epoch = ""
        self._sequence = FileSequenceStore(paths.sequence_file)
        self._telemetry = TelemetryStore(paths.inbox, paths.rejected, schemas, self._instance_id)
        self._journal: ExecutionJournal | None = None
        self._accepted: list[dict[str, Any]] = []
        self._by_seq: dict[int, dict[str, Any]] = {}
        self._frames_changed = asyncio.Condition()
        self.anomalies: deque[FrequencyAnomaly] = deque(maxlen=256)
        self.bus = EventBus(schemas, clock)
        self.agc = AgcHost(AgcEngine(), clock, self._publish_agc_state)
        self._rpc: RpcServer | None = None
        self._web: WebServer | None = None
        self._tasks: list[asyncio.Task[Any]] = []
        self._daemon_status = ComponentStatus.STOPPED
        self._audio_status = ComponentStatus.STOPPED
        self._awaiting = 0
        self._started = False

    # ------------------------------------------------------------------ identity
    @property
    def instance_id(self) -> str:
        return self._instance_id

    @property
    def sequence_epoch(self) -> str:
        return self._epoch

    @property
    def rpc_port(self) -> int:
        if self._rpc is None:
            raise RuntimeError("RPC listener is disabled")
        return self._rpc.port

    @property
    def web_port(self) -> int:
        if self._web is None:
            raise RuntimeError("web listener is disabled")
        return self._web.port

    @property
    def listener_addresses(self) -> list[tuple[str, int]]:
        addresses: list[tuple[str, int]] = []
        if self._rpc is not None:
            addresses.extend(tuple(sock.getsockname()[:2]) for sock in self._rpc.sockets)
        if self._web is not None:
            addresses.extend(tuple(address[:2]) for address in self._web.addresses)
        return addresses

    @property
    def accepted_records(self) -> list[dict[str, Any]]:
        return list(self._accepted)

    # ------------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        epoch = _read_identity(self._paths.identity_file)
        if epoch is None:
            if self._paths.sequence_file.exists():
                epoch = self._new_epoch
                atomic_write_json(
                    self._paths.identity_file,
                    {"schema_version": IDENTITY_SCHEMA_VERSION, "sequence_epoch": epoch},
                )
                _LOG.warning("created missing daemon identity with epoch %s", epoch)
        try:
            state = self._sequence.load()
        except SequenceStoreError as error:
            code = (
                DaemonErrorCode.SEQUENCE_MISSING
                if error.code.value == "MISSING"
                else DaemonErrorCode.SEQUENCE_STATE
            )
            raise DaemonStartupError(
                code,
                f"{error} -- provision explicitly with: apollo26 --provision-sequence 0",
            ) from error
        assert epoch is not None
        self._epoch = epoch
        try:
            self._telemetry.recover(state.last_accepted_seq)
            records = self._telemetry.load_accepted()
        except (ContractViolation, OSError, ValueError) as error:
            raise DaemonStartupError(DaemonErrorCode.RECOVERY_CONFLICT, str(error)) from error
        for record in records:
            self._index(record)
        self._journal = ExecutionJournal(
            self._paths.executions_root / self._epoch,
            lambda data: self._schemas.validate_rpc("/$defs/executionRecord", data),
        )
        self._journal.load(format_timestamp(self._clock.now_utc()))
        if self._rpc_port is not None:
            self._rpc = RpcServer(self, self._schemas, self._host_name, self._rpc_port)
            await self._rpc.start()
        if self._web_port is not None:
            self._web = WebServer(
                bus=self.bus,
                initial_events=self._initial_events,
                static_dir=self._static_dir,
                loopback_sink=self._loopback_sink if self._loopback is not None else None,
                host=self._host_name,
                port=self._web_port,
            )
            await self._web.start()
        if self._comp_acty_ticks:
            self._tasks.append(asyncio.create_task(self._tick_loop()))
        self._daemon_status = ComponentStatus.READY
        self._started = True
        self._publish_status()
        _LOG.info(
            "daemon ready epoch=%s last_seq=%d listeners=%s",
            self._epoch,
            state.last_accepted_seq,
            self.listener_addresses,
        )

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()
        if self._rpc is not None:
            await self._rpc.stop()
            self._rpc = None
        if self._web is not None:
            await self._web.stop()
            self._web = None
        self._daemon_status = ComponentStatus.STOPPED
        self._started = False

    async def _tick_loop(self) -> None:
        while True:
            await self._clock.sleep_ms(COMP_ACTY_PERIOD_MS)
            self.agc.tick_comp_acty()

    # ------------------------------------------------------------------ events
    def _system_status(self) -> dict[str, Any]:
        if self.agc.busy:
            flight_watch = "PROCESSING"
        elif self._awaiting:
            flight_watch = "WAITING"
        else:
            flight_watch = "STANDBY"
        return {
            "daemon": self._daemon_status.value,
            "audio": self._audio_status.value,
            "agc": "BUSY" if self.agc.busy else "READY",
            "flight_watch": flight_watch,
        }

    def _initial_events(self) -> list[dict[str, Any]]:
        events = [
            self.bus.make_event("system.status", self._system_status()),
            self.bus.make_event("agc.state", self.agc.ws_state()),
        ]
        if self._test_summary is not None:
            events.append(self.bus.make_event("test.summary", dict(self._test_summary)))
        # Audit backfill: accepted frames of the current epoch, oldest first, bounded to the
        # console's 500-row window. Rejected frames are only on disk and are not backfilled.
        for record in self._accepted[-AUDIT_BACKFILL_LIMIT:]:
            events.append(self.bus.make_event("telemetry.frame", record))
        return events

    def _publish_status(self) -> None:
        self.bus.publish("system.status", self._system_status())

    def _publish_agc_state(self) -> None:
        self.bus.publish("agc.state", self.agc.ws_state())

    def _publish_spectrum(self, receiver: StreamingReceiver, sample_rate: int) -> None:
        samples = receiver.latest(_SPECTRUM_FFT)
        if samples.size < _SPECTRUM_FFT:
            return
        spectrum = np.abs(np.fft.rfft(samples * np.hanning(samples.size))) * (2.0 / samples.size)
        frequencies = np.fft.rfftfreq(samples.size, 1.0 / sample_rate)
        mask = frequencies <= _SPECTRUM_MAX_HZ
        bins = frequencies[mask][:256]
        power = 20.0 * np.log10(spectrum[mask][:256] + 1e-9)
        self.bus.publish(
            "audio.spectrum",
            {
                "sample_rate_hz": sample_rate,
                "bin_hz": [round(float(value), 2) for value in bins],
                "power_db": [round(float(value), 2) for value in power],
            },
        )

    # ------------------------------------------------------------------ acceptance
    def _index(self, record: dict[str, Any]) -> None:
        seq = int(record["frame"]["seq"])
        self._accepted.append(record)
        self._by_seq[seq] = record

    async def process_candidate(
        self, raw: bytes, source: SourceMetadata, deviation_hz: float | None
    ) -> dict[str, Any]:
        """Validate one untrusted candidate; returns the written telemetry record."""

        received_at = self._clock.now_utc()
        pre = validate_frame(raw, self._keys, self._sequence)
        if pre.accepted and pre.frame is not None:
            record = build_record(
                received_at=received_at,
                source=source,
                frequency_deviation_hz=deviation_hz,
                raw=raw,
                frame=pre.frame,
                checks=pre.checks,
                reason=None,
            )
            try:
                staged = self._telemetry.stage_accepted(pre.frame.seq, record)
            except TelemetryStoreError as error:
                # Fail closed: nothing staged means the sequence is not committed.
                _LOG.error("inbox staging failed for seq=%d: %s", pre.frame.seq, error)
                pre = replace(pre, verdict=Verdict.REJECTED, reason=RejectReason.INTERNAL, frame=None)
                staged = None
            result = (
                validate_and_commit_frame(raw, self._keys, self._sequence)
                if staged is not None
                else pre
            )
            if result.accepted and staged is not None:
                self._telemetry.promote(staged)
                self._index(record)
                async with self._frames_changed:
                    self._frames_changed.notify_all()
                self.bus.publish("telemetry.frame", record)
                _LOG.info("accepted %s seq=%d", record["frame"]["frame_type"], pre.frame.seq)
                return record
            if staged is not None:
                self._telemetry.discard(staged)
            pre = result
        reason = pre.reason or RejectReason.INTERNAL
        record = build_record(
            received_at=received_at,
            source=source,
            frequency_deviation_hz=deviation_hz,
            raw=raw,
            frame=None,
            checks=pre.checks,
            reason=reason,
        )
        self._telemetry.write_rejected(record, received_at)
        self.bus.publish("telemetry.frame", record)
        _LOG.info("rejected candidate reason=%s", reason.value)
        return record

    def _record_loss(self, event: LostCandidateEvent, source: SourceMetadata) -> dict[str, Any]:
        received_at = self._clock.now_utc()
        reason = RejectReason.SYNC if event.loss is CandidateLoss.SYNC else RejectReason.LENGTH
        record = build_record(
            received_at=received_at,
            source=source,
            frequency_deviation_hz=event.frequency_deviation_hz,
            raw=None,
            frame=None,
            checks=None,
            reason=reason,
            modem_sync_ok=event.loss is not CandidateLoss.SYNC,
        )
        self._telemetry.write_rejected(record, received_at)
        self.bus.publish("telemetry.frame", record)
        return record

    async def _handle_events(
        self, events: list[ReceiverEvent], source: SourceMetadata, summary: SourceSummary
    ) -> None:
        for event in events:
            if isinstance(event, CandidateEvent):
                record = await self.process_candidate(event.raw, source, event.frequency_deviation_hz)
                if record["verdict"] == "ACCEPTED":
                    summary.accepted_seqs.append(record["frame"]["seq"])
                else:
                    summary.rejected_reasons.append(record["reason"])
            elif isinstance(event, LostCandidateEvent):
                record = self._record_loss(event, source)
                summary.rejected_reasons.append(record["reason"])
            elif isinstance(event, AnomalyEvent):
                summary.anomalies += 1
                self.anomalies.append(event.anomaly)
                _LOG.warning(
                    "FREQUENCY ANOMALY: expected %.0f Hz measured %.1f Hz (deviation %.1f Hz > 50 Hz)",
                    event.anomaly.expected_frequency_hz,
                    event.anomaly.measured_frequency_hz,
                    event.anomaly.absolute_deviation_hz,
                )
            elif isinstance(event, CarrierEvent):
                self.agc.set_uplink(event.active)

    async def run_source(self, source: AudioSource) -> SourceSummary:
        """Drive one source through the shared receiver/validator pipeline until EOF."""

        meta = source.metadata
        receiver = StreamingReceiver(
            DemodulatorConfig(sample_rate=meta.sample_rate), ModemSourceKind(meta.kind.value)
        )
        summary = SourceSummary(meta.kind.value, meta.sample_rate)
        self._audio_status = ComponentStatus.READY
        self._publish_status()
        spectrum_every = meta.sample_rate // 2
        since_spectrum = 0
        overflows = source.overflows
        try:
            async for block in source.blocks():
                if source.overflows != overflows:
                    overflows = source.overflows
                    _LOG.warning("audio queue overflow; discarding receiver state")
                    await self._handle_events(receiver.reset(), meta, summary)
                await self._handle_events(receiver.feed(block), meta, summary)
                since_spectrum += block.size
                if since_spectrum >= spectrum_every:
                    since_spectrum = 0
                    if self.bus.subscriber_count:
                        self._publish_spectrum(receiver, meta.sample_rate)
            await self._handle_events(receiver.flush(), meta, summary)
        except AudioSourceError:
            self._audio_status = ComponentStatus.DEGRADED
            self._publish_status()
            raise
        self._audio_status = ComponentStatus.STOPPED
        self._publish_status()
        return summary

    async def _loopback_sink(self, body: bytes) -> dict[str, Any]:
        assert self._loopback is not None
        try:
            rate, pcm = decode_wav_bytes(body)
        except AudioSourceError as error:
            return {"ok": False, "error": str(error)}
        if rate != self._loopback.metadata.sample_rate:
            return {"ok": False, "error": f"loopback expects {self._loopback.metadata.sample_rate} Hz"}
        await self._loopback.push(pcm)
        return {"ok": True, "queued_samples": int(pcm.size)}

    # ------------------------------------------------------------------ RPC
    async def handle_rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "telemetry.read":
            return self._telemetry_read(params["after_seq"], params["limit"])
        if method == "telemetry.await":
            return await self._telemetry_await(params["after_seq"], params["timeout_ms"])
        if method == "agc.inspect":
            return self.agc.inspect(self._catalog.version)
        if method == "execution.preflight":
            seq = params["frame_seq"]
            record = self._by_seq.get(seq)
            execution = self._journal_or_fail().get(seq)
            return {
                "snapshot": self.agc.inspect(self._catalog.version),
                "command_known": record is not None and record["frame"]["frame_type"] == "COMMAND",
                "execution": None if execution is None else execution.to_json(),
            }
        if method == "execution.get":
            execution = self._journal_or_fail().get(params["frame_seq"])
            return {"execution": None if execution is None else execution.to_json()}
        if method == "dsky.execute":
            return await self._dsky_execute(params)
        raise RpcError("INVALID_ARGUMENT", f"unknown method {method}")

    def _journal_or_fail(self) -> ExecutionJournal:
        if self._journal is None:
            raise RpcError("AGC_UNAVAILABLE", "daemon is not started", True)
        return self._journal

    def _telemetry_read(self, after_seq: int, limit: int) -> dict[str, Any]:
        frames: list[dict[str, Any]] = []
        budget = _READ_BUDGET_BYTES
        truncated = False
        for record in self._accepted:
            if record["frame"]["seq"] <= after_seq:
                continue
            size = len(json.dumps(record, separators=(",", ":")))
            if len(frames) >= limit or size > budget:
                truncated = True
                break
            budget -= size
            frames.append(record)
        high_water = self._accepted[-1]["frame"]["seq"] if self._accepted else 0
        return {"frames": frames, "high_water_seq": high_water, "truncated": truncated}

    def _first_after(self, after_seq: int) -> dict[str, Any] | None:
        return next((r for r in self._accepted if r["frame"]["seq"] > after_seq), None)

    async def _telemetry_await(self, after_seq: int, timeout_ms: int) -> dict[str, Any]:
        found = self._first_after(after_seq)
        if found is not None:
            return {"status": "FRAME", "frame": found}
        self._awaiting += 1
        self._publish_status()
        try:
            async with asyncio.timeout(timeout_ms / 1000.0):
                async with self._frames_changed:
                    while (found := self._first_after(after_seq)) is None:
                        await self._frames_changed.wait()
        except TimeoutError:
            return {"status": "TIMEOUT", "frame": None}
        finally:
            self._awaiting -= 1
            self._publish_status()
        return {"status": "FRAME", "frame": found}

    def _check_auth(self, frame_seq: int, auth_seq: int | None, command: dict[str, Any]) -> None:
        if auth_seq is None:
            raise RpcError("AUTH_REQUIRED", f"COMMAND {frame_seq} is critical and has no AUTH")
        auth = self._by_seq.get(auth_seq)
        if auth is None or auth["frame"]["frame_type"] != "AUTH" or auth["frame"]["ref_seq"] != frame_seq:
            raise RpcError("AUTH_INVALID", f"seq {auth_seq} is not an accepted AUTH for {frame_seq}")
        deadline = parse_timestamp(command["received_at"]) + timedelta(
            milliseconds=self._catalog.hold_expiry_ms
        )
        if parse_timestamp(auth["received_at"]) >= deadline:
            raise RpcError(
                "AUTH_EXPIRED",
                f"AUTH {auth_seq} arrived after the {self._catalog.hold_expiry_ms // 1000} s hold window",
            )
        if self._journal_or_fail().auth_in_use(auth_seq):
            raise RpcError("AUTH_USED", f"AUTH {auth_seq} was already consumed")

    async def _dsky_execute(self, params: dict[str, Any]) -> dict[str, Any]:
        """Independent daemon-side execution guard (cannot be bypassed by a local client)."""

        journal = self._journal_or_fail()
        frame_seq: int = params["frame_seq"]
        if params["catalog_version"] != self._catalog.version:
            raise RpcError("CATALOG_MISMATCH", "catalog version differs from daemon")
        command = self._by_seq.get(frame_seq)
        if command is None or command["frame"]["frame_type"] != "COMMAND":
            raise RpcError("NOT_FOUND", f"no accepted COMMAND with seq {frame_seq}")
        existing = journal.get(frame_seq)
        if existing is not None:
            if existing.plan_digest == params["plan_digest"]:
                return {"execution": existing.to_json(), "idempotent_replay": True}
            raise RpcError("IDEMPOTENCY_CONFLICT", f"COMMAND {frame_seq} already has an execution")
        if self.agc.busy:
            raise RpcError("BUSY", "another DSKY sequence is executing", True)
        async with self.agc.writer_lock:
            self._publish_status()
            view = self.agc.view()
            frame = command["frame"]
            fields = CommandFields(
                seq=frame["seq"],
                critical=frame["critical"],
                verb=frame["verb"],
                noun=frame["noun"],
                program=frame["program"],
                r1_centidegrees=frame["r1_centidegrees"],
                r2_centidegrees=frame["r2_centidegrees"],
                delta_v_tenths_fps=frame["delta_v_tenths_fps"],
            )
            try:
                self._catalog.check_preconditions(view)
                plan = self._catalog.plan(fields, view)
            except PlanError as error:
                raise RpcError(error.code.value, str(error)) from error
            if tuple(params["keys"]) != plan.keys or params["plan_digest"] != plan.plan_digest:
                raise RpcError("PLAN_MISMATCH", "keys are not the canonical plan for this frame")
            if params["expected_revision"] != self.agc.control_revision:
                raise RpcError("INSPECTION_STALE", "AGC state changed since inspection")
            auth_seq: int | None = params["auth_seq"]
            if plan.critical or auth_seq is not None:
                self._check_auth(frame_seq, auth_seq, command)
            started = ExecutionRecord(
                frame_seq=frame_seq,
                operation_id=params["operation_id"],
                plan_digest=plan.plan_digest,
                catalog_version=self._catalog.version,
                status=ExecutionStatus.STARTED,
                keys_total=len(plan.keys),
                keys_accepted=0,
                auth_seq=auth_seq,
                started_at=format_timestamp(self._clock.now_utc()),
                finished_at=None,
                pre_revision=self.agc.control_revision,
                post_revision=None,
                error_code=None,
            )
            journal.put(started)
            outcome = await self.agc.press_sequence(plan.keys, self._catalog.min_cadence_ms)
            final = replace(
                started,
                status=ExecutionStatus.EXECUTED if outcome.error is None else ExecutionStatus.FAILED,
                keys_accepted=outcome.keys_accepted,
                finished_at=format_timestamp(self._clock.now_utc()),
                post_revision=self.agc.control_revision,
                error_code=outcome.error,
            )
            journal.put(final)
        self._publish_status()
        _LOG.info(
            "dsky.execute seq=%d status=%s keys=%d/%d",
            frame_seq,
            final.status.value,
            final.keys_accepted,
            final.keys_total,
        )
        return {"execution": final.to_json(), "idempotent_replay": False}


# ---------------------------------------------------------------------- CLI
def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="apollo26", description="Apollo-26 acoustic daemon")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--input", type=Path, help="process a mono 16-bit WAV file")
    source.add_argument("--loopback", action="store_true", help="accept WAV via POST /loopback")
    source.add_argument("--device", help="sounddevice input device (index or name)")
    parser.add_argument("--host", default=LOOPBACK_HOST, help="listener host (only 127.0.0.1)")
    parser.add_argument("--port", type=int, default=DEFAULT_HTTP_PORT, help="HTTP/WebSocket port")
    parser.add_argument("--rpc-port", type=int, default=DEFAULT_RPC_PORT, help="MCP RPC port")
    parser.add_argument("--telemetry-dir", type=Path, default=Path("telemetry"))
    parser.add_argument("--contracts-dir", type=Path, default=Path("contracts"))
    parser.add_argument("--static-dir", type=Path, default=Path("web-dashboard") / "out")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument(
        "--test-summary",
        type=Path,
        default=Path("docs") / "test-summary.json",
        help="test-runner summary published to the console as test.summary",
    )
    parser.add_argument("--sample-rate", type=int, choices=(44100, 48000), help="microphone rate")
    parser.add_argument(
        "--serve-after-input",
        action="store_true",
        help="with --input: keep RPC/web listeners running after the WAV is drained",
    )
    parser.add_argument(
        "--provision-sequence",
        type=int,
        metavar="N",
        help="explicitly (re)provision last_accepted_seq=N with a new epoch, then exit",
    )
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


async def _serve_forever(daemon: Daemon, source: AudioSource | None) -> None:
    tasks: list[asyncio.Task[Any]] = []
    if source is not None:
        tasks.append(asyncio.create_task(daemon.run_source(source)))
    try:
        await asyncio.Event().wait()
    finally:
        if source is not None:
            await source.close()
        for task in tasks:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, AudioSourceError):
                await task


async def _run(args: argparse.Namespace, keys: KeyMaterial) -> int:
    schemas = ContractSchemas.load(args.contracts_dir)
    catalog = CommandCatalog(load_catalog_document(args.contracts_dir, schemas))
    paths = DaemonPaths(args.telemetry_dir)
    clock = SystemClock()
    one_shot = args.input is not None and not args.serve_after_input
    loopback = LoopbackSource() if args.loopback else None
    source: AudioSource | None = None
    if args.input is not None:
        source = WavFileSource(args.input)
    daemon = Daemon(
        paths=paths,
        keys=keys,
        clock=clock,
        schemas=schemas,
        catalog=catalog,
        instance_id=str(uuid.uuid4()),
        host=args.host,
        web_port=None if one_shot else args.port,
        rpc_port=None if one_shot else args.rpc_port,
        static_dir=args.static_dir,
        loopback_source=loopback,
        comp_acty_ticks=not one_shot,
        test_summary=None if one_shot else load_test_summary(args.test_summary, schemas),
    )
    await daemon.start()
    try:
        if one_shot:
            assert source is not None
            summary = await daemon.run_source(source)
            print(json.dumps(summary.to_json()), flush=True)
            return 0
        if source is None:
            source = loopback or MicrophoneSource(
                device=int(args.device) if args.device and args.device.isdigit() else args.device,
                sample_rate=args.sample_rate,
            )
        if args.input is not None:
            summary = await daemon.run_source(source)
            print(json.dumps(summary.to_json()), flush=True)
            source = None
        await _serve_forever(daemon, source)
        return 0
    finally:
        await daemon.stop()


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    try:
        require_loopback_host(args.host)
        require_port(args.port)
        require_port(args.rpc_port)
        paths = DaemonPaths(args.telemetry_dir)
        if args.provision_sequence is not None:
            archived = provision_sequence(paths, args.provision_sequence, str(uuid.uuid4()))
            print(
                json.dumps(
                    {
                        "provisioned_last_accepted_seq": args.provision_sequence,
                        "archived_to": None if archived is None else str(archived),
                    }
                )
            )
            return 0
        keys = load_key_material(merged_environment(os.environ, args.env_file))
    except ConfigError as error:
        print(f"apollo26: configuration error: {error}", file=sys.stderr)
        return 2
    except SequenceStoreError as error:
        print(f"apollo26: sequence provisioning failed: {error}", file=sys.stderr)
        return 3
    try:
        return asyncio.run(_run(args, keys))
    except DaemonStartupError as error:
        print(f"apollo26: startup refused: {error}", file=sys.stderr)
        return 3
    except AudioSourceError as error:
        print(f"apollo26: audio source error: {error}", file=sys.stderr)
        return 4
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
