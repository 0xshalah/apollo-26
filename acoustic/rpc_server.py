"""Newline-delimited JSON RPC server for the MCP bridge, bound only to 127.0.0.1.

Contract: ``contracts/mcp-daemon-rpc.schema.json``.  Every request is validated
before dispatch and every response before it is written.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Final, Protocol

from acoustic.config import require_loopback_host, require_port
from acoustic.schemas import ContractSchemas, ContractViolation

_LOG = logging.getLogger(__name__)
MAX_MESSAGE_BYTES: Final = 65_536
SCHEMA_VERSION: Final = "1.0"


@dataclass
class RpcError(Exception):
    code: str
    message: str
    retryable: bool = False
    details: dict[str, str | int | bool | None] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class RpcHandler(Protocol):
    @property
    def instance_id(self) -> str: ...

    @property
    def sequence_epoch(self) -> str: ...

    async def handle_rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]: ...


class RpcServer:
    def __init__(self, handler: RpcHandler, schemas: ContractSchemas, host: str, port: int) -> None:
        self._handler = handler
        self._schemas = schemas
        self._host = require_loopback_host(host)
        self._port = require_port(port)
        self._server: asyncio.Server | None = None
        self._connections: set[asyncio.Task[None]] = set()

    @property
    def port(self) -> int:
        if self._server is None:
            raise RuntimeError("RPC server is not started")
        return int(self._server.sockets[0].getsockname()[1])

    @property
    def sockets(self) -> list[Any]:
        return [] if self._server is None else list(self._server.sockets)

    async def start(self) -> int:
        self._server = await asyncio.start_server(
            self._on_client, host=self._host, port=self._port, limit=MAX_MESSAGE_BYTES
        )
        return self.port

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            for task in list(self._connections):
                task.cancel()
            with contextlib.suppress(OSError):
                await self._server.wait_closed()
            self._server = None

    def _envelope(self, request_id: str | None) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "request_id": request_id,
            "daemon_instance_id": self._handler.instance_id,
            "sequence_epoch": self._handler.sequence_epoch,
        }

    def _error(self, request_id: str | None, error: RpcError) -> dict[str, Any]:
        response = self._envelope(request_id)
        response["ok"] = False
        response["error"] = {
            "code": error.code,
            "message": error.message[:512],
            "retryable": error.retryable,
            "details": dict(error.details),
        }
        return response

    async def _respond(self, raw_line: bytes) -> dict[str, Any]:
        try:
            message = json.loads(raw_line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self._error(None, RpcError("RPC_PROTOCOL", "message is not UTF-8 JSON"))
        request_id = message.get("request_id") if isinstance(message, dict) else None
        if not isinstance(request_id, str):
            request_id = None
        if isinstance(message, dict) and message.get("schema_version") not in (None, SCHEMA_VERSION):
            return self._error(request_id, RpcError("SCHEMA_VERSION", "unsupported schema_version"))
        try:
            self._schemas.validate_rpc("/$defs/request", message)
        except ContractViolation as violation:
            return self._error(request_id, RpcError("INVALID_ARGUMENT", str(violation)))
        method: str = message["method"]
        try:
            result = await asyncio.wait_for(
                self._handler.handle_rpc(method, message["params"]),
                timeout=message["deadline_ms"] / 1000.0,
            )
        except RpcError as error:
            return self._error(request_id, error)
        except TimeoutError:
            return self._error(request_id, RpcError("TIMEOUT", f"{method} exceeded its deadline", True))
        except Exception:
            _LOG.exception("RPC %s request_id=%s failed", method, request_id)
            return self._error(request_id, RpcError("INTERNAL", "internal daemon error"))
        response = self._envelope(request_id)
        response["ok"] = True
        response["result"] = result
        try:
            self._schemas.validate_rpc("/$defs/successResponse", response)
            self._schemas.validate_rpc(f"/$defs/results/{method}", result)
        except ContractViolation as violation:
            _LOG.error("RPC %s produced an invalid response: %s", method, violation)
            return self._error(request_id, RpcError("INTERNAL", "daemon response violated contract"))
        return response

    async def _on_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        if task is not None:
            self._connections.add(task)
        try:
            while True:
                try:
                    line = await reader.readline()
                except (ValueError, asyncio.LimitOverrunError):
                    response = self._error(None, RpcError("RPC_PROTOCOL", "message exceeds 64 KiB"))
                    writer.write(json.dumps(response).encode() + b"\n")
                    await writer.drain()
                    return
                if not line:
                    return
                if not line.strip():
                    continue
                response = await self._respond(line)
                encoded = json.dumps(response, separators=(",", ":")).encode("utf-8") + b"\n"
                if len(encoded) > MAX_MESSAGE_BYTES:
                    encoded = (
                        json.dumps(
                            self._error(
                                response.get("request_id"),
                                RpcError("INTERNAL", "response exceeds 64 KiB; lower the limit"),
                            )
                        ).encode()
                        + b"\n"
                    )
                writer.write(encoded)
                await writer.drain()
        except (ConnectionError, asyncio.CancelledError):
            return
        finally:
            if task is not None:
                self._connections.discard(task)
            writer.close()
            with contextlib.suppress(OSError):
                await writer.wait_closed()
