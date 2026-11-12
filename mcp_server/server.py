"""MCP stdio adapter exposing exactly the six Apollo-26 Flight Watch tools."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

import mcp.types as types
from jsonschema import Draft202012Validator
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from mcp_server.audit import AuditSink, FileAuditWriter
from mcp_server.clock import Clock, SystemClock
from mcp_server.contracts import BridgeContracts
from mcp_server.errors import BridgeError, ErrorCode
from mcp_server.ledger import FileLedgerPersistence, Ledger
from mcp_server.planner import CanonicalPlanner
from mcp_server.rpc_client import LOOPBACK_HOST, DaemonPort, DaemonRpcClient
from mcp_server.service import FlightMarker, FlightWatchService

_LOG = logging.getLogger("apollo26.mcp")
SERVER_NAME: Final = "apollo26-flight-watch"
DEFAULT_RPC_PORT: Final = 8027
_SEQ = {"type": "integer", "minimum": 1, "maximum": 4294967295}
_KEY_ENUM = [
    "VERB", "NOUN", "DIGIT_0", "DIGIT_1", "DIGIT_2", "DIGIT_3", "DIGIT_4", "DIGIT_5",
    "DIGIT_6", "DIGIT_7", "DIGIT_8", "DIGIT_9", "PLUS", "MINUS", "ENTR", "PRO", "CLR",
    "RSET", "KEY_REL",
]  # fmt: skip

TOOL_SCHEMAS: Final[dict[str, dict[str, Any]]] = {
    "read_telemetry_frames": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "since_seq": {"type": "integer", "minimum": 0, "maximum": 4294967295, "default": 0},
            "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 100},
        },
    },
    "await_telemetry_frame": {
        "type": "object",
        "additionalProperties": False,
        "required": ["timeout_sec"],
        "properties": {"timeout_sec": {"type": "number", "minimum": 0.1, "maximum": 30.0}},
    },
    "inspect_agc_status": {"type": "object", "additionalProperties": False, "properties": {}},
    "plan_dsky_sequence": {
        "type": "object",
        "additionalProperties": False,
        "required": ["frame_seq"],
        "properties": {"frame_seq": _SEQ},
    },
    "execute_dsky_sequence": {
        "type": "object",
        "additionalProperties": False,
        "required": ["keys", "frame_seq"],
        "properties": {
            "keys": {"type": "array", "minItems": 1, "maxItems": 128, "items": {"enum": _KEY_ENUM}},
            "frame_seq": _SEQ,
        },
    },
    "verify_crc16": {
        "type": "object",
        "additionalProperties": False,
        "required": ["hex_payload"],
        "properties": {
            "hex_payload": {
                "type": "string",
                "pattern": "^([0-9a-fA-F]{2}){2,4096}$",
            }
        },
    },
}

TOOL_DESCRIPTIONS: Final = {
    "read_telemetry_frames": "Read daemon-accepted frames (CRC/HMAC/sequence already validated) with seq > since_seq. Read-only; does not move the Flight Watch cursor.",
    "await_telemetry_frame": "Flight Watch runtime entry: wait up to timeout_sec for the next accepted COMMAND or AUTH. Returns status FRAME or TIMEOUT plus the COMMAND/AUTH lifecycle result.",
    "inspect_agc_status": "Read a coherent AGC/DSKY snapshot (program, VERB/NOUN, R1-R3, lamps, state revision). Required after each COMMAND delivery and before planning/executing; valid for 20 s and only while the AGC state revision is unchanged.",
    "plan_dsky_sequence": "Deterministically derive the only canonical DSKY key sequence, postcondition, criticality, and AUTH state for an accepted COMMAND. Does not actuate.",
    "execute_dsky_sequence": "WRITE: send the canonical keys for frame_seq to the AGC after the code-enforced safety gate (fresh inspection, exact canonical plan, KEY REL off, operator AUTH for critical commands). Never auto-approve.",
    "verify_crc16": "Audit utility: CRC-16/CCITT-FALSE over all bytes except the final two, compared with the final two (big-endian). No side effects; a match does not imply authenticity.",
}


def tool_definitions() -> list[types.Tool]:
    return [
        types.Tool(name=name, description=TOOL_DESCRIPTIONS[name], inputSchema=schema)
        for name, schema in TOOL_SCHEMAS.items()
    ]


async def dispatch(service: FlightWatchService, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Validate tool input once against its schema, then call the service."""

    schema = TOOL_SCHEMAS.get(name)
    if schema is None:
        raise BridgeError(ErrorCode.INVALID_ARGUMENT, f"unknown tool {name}")
    error = next(iter(Draft202012Validator(schema).iter_errors(arguments)), None)
    if error is not None:
        raise BridgeError(ErrorCode.INVALID_ARGUMENT, f"invalid arguments: {error.message[:200]}")
    if name == "read_telemetry_frames":
        return await service.read_telemetry_frames(
            arguments.get("since_seq", 0), arguments.get("limit", 100)
        )
    if name == "await_telemetry_frame":
        return await service.await_telemetry_frame(float(arguments["timeout_sec"]))
    if name == "inspect_agc_status":
        return await service.inspect_agc_status()
    if name == "plan_dsky_sequence":
        return await service.plan_dsky_sequence(arguments["frame_seq"])
    if name == "execute_dsky_sequence":
        return await service.execute_dsky_sequence(list(arguments["keys"]), arguments["frame_seq"])
    return await service.verify_crc16(arguments["hex_payload"])


def build_server(service: FlightWatchService) -> Server[Any, Any]:
    server: Server[Any, Any] = Server(SERVER_NAME)

    @server.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
    async def list_tools() -> list[types.Tool]:
        return tool_definitions()

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def call_tool(name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
        return await dispatch(service, name, arguments or {})

    return server


def build_service(
    *,
    contracts_dir: Path,
    state_dir: Path,
    rpc_port: int,
    marker_path: Path | None,
    clock: Clock | None = None,
    daemon: DaemonPort | None = None,
    session_id: str | None = None,
) -> FlightWatchService:
    contracts = BridgeContracts.load(contracts_dir)
    planner = CanonicalPlanner(contracts.catalog)
    session = session_id or str(uuid.uuid4())
    clock = clock or SystemClock()
    return FlightWatchService(
        daemon=daemon or DaemonRpcClient(contracts, rpc_port, LOOPBACK_HOST),
        planner=planner,
        ledger=Ledger(FileLedgerPersistence(state_dir / "ledger.json")),
        audit=AuditSink(FileAuditWriter(state_dir / "audit" / session), contracts, clock, session),
        clock=clock,
        session_id=session,
        marker=FlightMarker(marker_path),
    )


async def _serve(service: FlightWatchService) -> None:
    server = build_server(service)
    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())
    finally:
        await service.close()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="apollo26-mcp", description="Apollo-26 MCP stdio server")
    parser.add_argument("--rpc-port", type=int, default=DEFAULT_RPC_PORT)
    parser.add_argument("--contracts-dir", type=Path, default=Path("contracts"))
    parser.add_argument("--state-dir", type=Path, default=Path("telemetry") / "state" / "mcp")
    parser.add_argument("--flight-marker", type=Path, default=Path("telemetry") / "FLIGHT_MODE")
    parser.add_argument("--no-flight-marker", action="store_true")
    parser.add_argument("--log-level", default="WARNING")
    args = parser.parse_args(argv)
    # stdout carries MCP JSON-RPC; logs go to stderr only.
    logging.basicConfig(level=getattr(logging, str(args.log_level).upper(), logging.WARNING), stream=sys.stderr)
    service = build_service(
        contracts_dir=args.contracts_dir,
        state_dir=args.state_dir,
        rpc_port=args.rpc_port,
        marker_path=None if args.no_flight_marker else args.flight_marker,
    )
    asyncio.run(_serve(service))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
