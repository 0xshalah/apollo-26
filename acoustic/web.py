"""Loopback-only HTTP + WebSocket adapter (aiohttp).

* ``GET /ws``: read-only console stream of events validated against
  ``contracts/websocket-events.schema.json``.
* ``POST /loopback``: WAV injection, enabled only in ``--loopback`` mode.
* Everything else: static files from ``web-dashboard/out/`` when present.

The UI cannot mutate AGC state through this adapter.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Final

from aiohttp import WSMsgType, web

from acoustic.clock import Clock, format_timestamp
from acoustic.config import require_loopback_host, require_port
from acoustic.schemas import ContractSchemas

_LOG = logging.getLogger(__name__)
MAX_LOOPBACK_BYTES: Final = 4 * 1024 * 1024
_SUBSCRIBER_QUEUE: Final = 256


class EventBus:
    """Validates and fans out console events; slow subscribers are dropped."""

    def __init__(self, schemas: ContractSchemas, clock: Clock) -> None:
        self._schemas = schemas
        self._clock = clock
        self._next_id = 1
        self._subscribers: set[asyncio.Queue[dict[str, Any] | None]] = set()

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def make_event(self, event_type: str, data: dict[str, Any]) -> dict[str, Any]:
        event = {
            "schema_version": "1.0",
            "event_id": self._next_id,
            "timestamp": format_timestamp(self._clock.now_utc()),
            "type": event_type,
            "data": data,
        }
        self._schemas.validate_ws_event(event)
        self._next_id += 1
        return event

    def publish(self, event_type: str, data: dict[str, Any]) -> dict[str, Any]:
        event = self.make_event(event_type, data)
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                _LOG.warning("dropping slow WebSocket subscriber")
                self._subscribers.discard(queue)
                with contextlib.suppress(asyncio.QueueFull):
                    queue.put_nowait(None)
        return event

    def subscribe(self) -> asyncio.Queue[dict[str, Any] | None]:
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(_SUBSCRIBER_QUEUE)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any] | None]) -> None:
        self._subscribers.discard(queue)


class WebServer:
    def __init__(
        self,
        *,
        bus: EventBus,
        initial_events: Callable[[], list[dict[str, Any]]],
        static_dir: Path | None,
        loopback_sink: Callable[[bytes], Awaitable[dict[str, Any]]] | None,
        host: str,
        port: int,
    ) -> None:
        self._bus = bus
        self._initial_events = initial_events
        self._static_dir = static_dir.resolve() if static_dir is not None and static_dir.is_dir() else None
        self._loopback_sink = loopback_sink
        self._host = require_loopback_host(host)
        self._port = require_port(port)
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._bound_port: int | None = None

    @property
    def port(self) -> int:
        if self._bound_port is None:
            raise RuntimeError("web server is not started")
        return self._bound_port

    @property
    def addresses(self) -> list[Any]:
        """Bound socket addresses, e.g. ``[('127.0.0.1', 8026)]``."""

        return [] if self._runner is None else list(self._runner.addresses)

    def _app(self) -> web.Application:
        app = web.Application(client_max_size=MAX_LOOPBACK_BYTES, middlewares=[self._host_guard])
        app.router.add_get("/ws", self._ws)
        app.router.add_post("/loopback", self._loopback)
        app.router.add_get("/{tail:.*}", self._static)
        return app

    @web.middleware
    async def _host_guard(
        self, request: web.Request, handler: Callable[[web.Request], Awaitable[web.StreamResponse]]
    ) -> web.StreamResponse:
        # DNS-rebinding guard: only loopback host names may address the daemon.
        host = (request.host or "").rsplit(":", 1)[0].strip("[]").lower()
        if host not in ("127.0.0.1", "localhost"):
            raise web.HTTPForbidden(text="loopback host required")
        return await handler(request)

    async def start(self) -> int:
        self._runner = web.AppRunner(self._app(), access_log=None)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, host=self._host, port=self._port)
        await self._site.start()
        addresses = self.addresses
        self._bound_port = int(addresses[0][1]) if addresses else self._port
        return self._bound_port

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
            self._site = None

    async def _ws(self, request: web.Request) -> web.StreamResponse:
        socket = web.WebSocketResponse(heartbeat=20)
        await socket.prepare(request)
        queue = self._bus.subscribe()
        sender = asyncio.create_task(self._forward(socket, queue))
        try:
            async for message in socket:
                if message.type in (WSMsgType.ERROR, WSMsgType.CLOSE):
                    break
                # The console is read-only; inbound messages are ignored.
        finally:
            self._bus.unsubscribe(queue)
            sender.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await sender
        return socket

    async def _forward(
        self, socket: web.WebSocketResponse, queue: asyncio.Queue[dict[str, Any] | None]
    ) -> None:
        try:
            for event in self._initial_events():
                await socket.send_str(json.dumps(event, separators=(",", ":")))
            while True:
                event = await queue.get()
                if event is None:
                    await socket.close()
                    return
                await socket.send_str(json.dumps(event, separators=(",", ":")))
        except (ConnectionError, RuntimeError) as error:
            _LOG.info("WebSocket subscriber closed: %s", error)

    async def _loopback(self, request: web.Request) -> web.StreamResponse:
        if self._loopback_sink is None:
            raise web.HTTPNotFound(text="loopback input is not enabled (start with --loopback)")
        body = await request.read()
        result = await self._loopback_sink(body)
        return web.json_response(result)

    async def _static(self, request: web.Request) -> web.StreamResponse:
        if self._static_dir is None:
            return web.Response(
                text="Apollo-26 daemon is running. Build web-dashboard/out to serve the console.\n",
                content_type="text/plain",
            )
        tail = request.match_info.get("tail", "").strip("/")
        candidates = (
            [self._static_dir / "index.html"]
            if not tail
            else [
                self._static_dir / tail,
                self._static_dir / f"{tail}.html",
                self._static_dir / tail / "index.html",
            ]
        )
        for candidate in candidates:
            resolved = candidate.resolve()
            if not resolved.is_relative_to(self._static_dir):
                raise web.HTTPForbidden(text="path escapes static root")
            if resolved.is_file():
                return web.FileResponse(resolved)
        raise web.HTTPNotFound()
