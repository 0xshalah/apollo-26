"""Loopback-only client for the daemon RPC (``contracts/mcp-daemon-rpc.schema.json``)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Final, Protocol

from mcp_server.contracts import BridgeContracts, SchemaError
from mcp_server.errors import BridgeError, ErrorCode

_LOG = logging.getLogger(__name__)
LOOPBACK_HOST: Final = "127.0.0.1"
MAX_MESSAGE_BYTES: Final = 65_536
SCHEMA_VERSION: Final = "1.0"


@dataclass(frozen=True, slots=True)
class RpcReply:
    result: dict[str, Any]
    daemon_instance_id: str
    sequence_epoch: str


@dataclass
class DaemonRejected(Exception):
    """The daemon answered with a typed error envelope."""

    code: str
    message: str
    retryable: bool
    daemon_instance_id: str
    sequence_epoch: str
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class OutcomeUnknown(Exception):
    """A mutating request was sent but no valid response arrived."""


class DaemonPort(Protocol):
    """What the bridge needs from the daemon; implemented by RPC or test fakes."""

    async def call(self, method: str, params: dict[str, Any], deadline_ms: int) -> RpcReply: ...


class DaemonRpcClient:
    """One TCP connection per request; every message validated once at this boundary."""

    def __init__(self, contracts: BridgeContracts, port: int, host: str = LOOPBACK_HOST) -> None:
        if host != LOOPBACK_HOST:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, f"daemon RPC host must be {LOOPBACK_HOST}")
        if not 1 <= port <= 65535:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, f"invalid daemon RPC port {port}")
        self._contracts = contracts
        self._host = host
        self._port = port

    async def call(self, method: str, params: dict[str, Any], deadline_ms: int) -> RpcReply:
        request_id = str(uuid.uuid4())
        request = {
            "schema_version": SCHEMA_VERSION,
            "request_id": request_id,
            "method": method,
            "deadline_ms": deadline_ms,
            "params": params,
        }
        try:
            self._contracts.validate_rpc("/$defs/request", request)
        except SchemaError as error:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, str(error)) from error
        mutating = method == "dsky.execute"
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port, limit=MAX_MESSAGE_BYTES), 2.0
            )
        except (OSError, TimeoutError) as error:
            raise BridgeError(
                ErrorCode.DAEMON_UNAVAILABLE, f"daemon RPC {self._host}:{self._port} unavailable", retryable=True
            ) from error
        sent = False
        try:
            writer.write(json.dumps(request, separators=(",", ":")).encode("utf-8") + b"\n")
            await writer.drain()
            sent = True
            line = await asyncio.wait_for(reader.readline(), timeout=deadline_ms / 1000.0 + 2.0)
        except (OSError, TimeoutError, ValueError, asyncio.IncompleteReadError) as error:
            if mutating and sent:
                raise OutcomeUnknown(f"{method} confirmation lost") from error
            code = ErrorCode.TIMEOUT if isinstance(error, TimeoutError) else ErrorCode.DAEMON_UNAVAILABLE
            raise BridgeError(code, f"{method} did not complete", retryable=True) from error
        finally:
            writer.close()
            with contextlib.suppress(OSError):
                await writer.wait_closed()
        if not line:
            if mutating:
                raise OutcomeUnknown(f"{method} connection closed before a response")
            raise BridgeError(ErrorCode.DAEMON_UNAVAILABLE, f"{method}: connection closed", retryable=True)
        return self._parse(method, request_id, line)

    def _parse(self, method: str, request_id: str, line: bytes) -> RpcReply:
        try:
            message = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise BridgeError(ErrorCode.RPC_PROTOCOL, "daemon response is not JSON") from error
        if not isinstance(message, dict):
            raise BridgeError(ErrorCode.RPC_PROTOCOL, "daemon response is not an object")
        if message.get("schema_version") != SCHEMA_VERSION:
            raise BridgeError(ErrorCode.SCHEMA_VERSION, "unsupported daemon schema_version")
        pointer = "/$defs/successResponse" if message.get("ok") is True else "/$defs/errorResponse"
        try:
            self._contracts.validate_rpc(pointer, message)
            if message["ok"]:
                self._contracts.validate_rpc(f"/$defs/results/{method}", message["result"])
        except SchemaError as error:
            raise BridgeError(ErrorCode.RPC_PROTOCOL, str(error)) from error
        if message["request_id"] != request_id:
            raise BridgeError(ErrorCode.RPC_PROTOCOL, "daemon response request_id mismatch")
        if not message["ok"]:
            failure = message["error"]
            raise DaemonRejected(
                code=failure["code"],
                message=failure["message"],
                retryable=failure["retryable"],
                daemon_instance_id=message["daemon_instance_id"],
                sequence_epoch=message["sequence_epoch"],
                details=failure["details"],
            )
        return RpcReply(message["result"], message["daemon_instance_id"], message["sequence_epoch"])
