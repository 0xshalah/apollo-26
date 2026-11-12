"""Shared fixtures-as-functions for daemon / MCP integration tests (no devices, no network
beyond 127.0.0.1)."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from acoustic.audio import SourceKind, SourceMetadata, split_blocks
from acoustic.clock import ManualClock
from acoustic.command_catalog import CommandCatalog
from acoustic.daemon import Daemon, DaemonPaths, provision_sequence
from acoustic.frame import AuthFrame, CommandFrame, KeyMaterial, encode_frame
from acoustic.modem import modulate
from acoustic.schemas import ContractSchemas, load_catalog_document
from mcp_server.audit import AuditSink, MemoryAuditWriter
from mcp_server.contracts import BridgeContracts
from mcp_server.ledger import Ledger, MemoryLedgerPersistence
from mcp_server.planner import CanonicalPlanner
from mcp_server.rpc_client import DaemonRpcClient
from mcp_server.service import FlightWatchService

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"
LINK_KEY = b"apollo26-link-demo-key-v1"
OPERATOR_KEY = b"apollo26-operator-demo-key-v1"
KEYS = KeyMaterial(LINK_KEY, OPERATOR_KEY)
RATE = 48_000

SCHEMAS = ContractSchemas.load(CONTRACTS)
CATALOG_DOC = load_catalog_document(CONTRACTS, SCHEMAS)
CATALOG = CommandCatalog(CATALOG_DOC)
BRIDGE_CONTRACTS = BridgeContracts.load(CONTRACTS)


def command_bytes(
    seq: int,
    *,
    verb: int = 25,
    noun: int = 81,
    program: int = 0,
    r1: int = 1250,
    r2: int = 420,
    dv: int = 3120,
    critical: bool = False,
    key: bytes = LINK_KEY,
) -> bytes:
    frame = CommandFrame(seq, critical, verb, noun, program, r1, r2, dv)
    return encode_frame(frame, key)


def p40_bytes(seq: int, dv: int = 1200, *, critical: bool = False, key: bytes = LINK_KEY) -> bytes:
    return command_bytes(seq, verb=37, noun=0, program=40, r1=1250, r2=420, dv=dv, critical=critical, key=key)


def auth_bytes(seq: int, ref_seq: int, *, key: bytes = OPERATOR_KEY) -> bytes:
    return encode_frame(AuthFrame(seq, ref_seq), key)


def with_bad_crc(raw: bytes) -> bytes:
    mutated = bytearray(raw)
    mutated[20] ^= 0x01
    return bytes(mutated)


def burst(*frames: bytes, gap_s: float = 0.3, lead_s: float = 0.3, tail_s: float = 0.6) -> NDArray[np.float64]:
    parts: list[NDArray[np.float64]] = [np.zeros(int(RATE * lead_s))]
    for index, raw in enumerate(frames):
        if index:
            parts.append(np.zeros(int(RATE * gap_s)))
        parts.append(modulate(raw, RATE, amplitude=0.6))
    parts.append(np.zeros(int(RATE * tail_s)))
    return np.concatenate(parts)


class ArraySource:
    """Deterministic in-memory AudioSource (loopback kind) for pipeline tests."""

    def __init__(self, pcm: NDArray[np.float64], kind: SourceKind = SourceKind.LOOPBACK, chunk: int | None = None) -> None:
        self._pcm = np.asarray(pcm, dtype=np.float64)
        self._meta = SourceMetadata(kind, RATE)
        self._chunk = chunk
        self.overflows = 0

    @property
    def metadata(self) -> SourceMetadata:
        return self._meta

    async def blocks(self) -> AsyncIterator[NDArray[np.float64]]:
        if self._chunk is None:
            pieces = split_blocks(self._pcm, RATE)
        else:
            pieces = [self._pcm[i : i + self._chunk] for i in range(0, self._pcm.size, self._chunk)]
        for piece in pieces:
            yield piece

    async def close(self) -> None:
        return None


def provision(telemetry_dir: Path, last_seq: int = 0) -> str:
    epoch = str(uuid.uuid4())
    provision_sequence(DaemonPaths(telemetry_dir), last_seq, epoch)
    return epoch


async def start_daemon(
    telemetry_dir: Path,
    clock: ManualClock,
    *,
    listeners: bool = True,
    static_dir: Path | None = None,
    loopback_source: Any = None,
    test_summary: dict[str, Any] | None = None,
) -> Daemon:
    daemon = Daemon(
        paths=DaemonPaths(telemetry_dir),
        keys=KEYS,
        clock=clock,
        schemas=SCHEMAS,
        catalog=CATALOG,
        instance_id=str(uuid.uuid4()),
        web_port=0 if listeners else None,
        rpc_port=0 if listeners else None,
        static_dir=static_dir,
        loopback_source=loopback_source,
        comp_acty_ticks=False,
        test_summary=test_summary,
    )
    await daemon.start()
    return daemon


async def transmit(daemon: Daemon, *frames: bytes, **kwargs: Any) -> Any:
    return await daemon.run_source(ArraySource(burst(*frames, **kwargs)))


def make_service(
    rpc_port: int, clock: ManualClock, session_id: str | None = None
) -> tuple[FlightWatchService, MemoryAuditWriter, MemoryLedgerPersistence]:
    writer = MemoryAuditWriter()
    persistence = MemoryLedgerPersistence()
    session = session_id or str(uuid.uuid4())
    service = FlightWatchService(
        daemon=DaemonRpcClient(BRIDGE_CONTRACTS, rpc_port),
        planner=CanonicalPlanner(BRIDGE_CONTRACTS.catalog),
        ledger=Ledger(persistence),
        audit=AuditSink(writer, BRIDGE_CONTRACTS, clock, session),
        clock=clock,
        session_id=session,
    )
    return service, writer, persistence


async def await_inspect_plan(
    service: FlightWatchService, clock: ManualClock, frame_seq: int
) -> dict[str, Any]:
    """Inspect (after delivery) then plan; returns the plan tool result."""

    clock.advance_ms(1)
    inspected = await service.inspect_agc_status()
    assert inspected["ok"], inspected
    return await service.plan_dsky_sequence(frame_seq)


def inbox_records(telemetry_dir: Path) -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((telemetry_dir / "inbox").glob("[0-9]*.json"))
    ]


def rejected_records(telemetry_dir: Path) -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((telemetry_dir / "rejected").glob("*.json"))
    ]
