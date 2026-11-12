"""Daemon HTTP + WebSocket boundary: static console, schema-valid events, host guards."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import aiohttp
import pytest

from acoustic.clock import ManualClock
from acoustic.daemon import Daemon
from tests.harness import SCHEMAS, command_bytes, provision, rejected_records, start_daemon, transmit, with_bad_crc

pytestmark = pytest.mark.integration


@pytest.fixture
def static_dir(tmp_path: Path) -> Path:
    root = tmp_path / "out"
    (root / "console").mkdir(parents=True)
    (root / "index.html").write_text("<h1>index</h1>", encoding="utf-8")
    (root / "console" / "index.html").write_text("<h1>console</h1>", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("do not serve", encoding="utf-8")
    return root


@pytest.fixture
async def daemon(tmp_path: Path, static_dir: Path) -> AsyncIterator[Daemon]:
    telemetry = tmp_path / "telemetry"
    provision(telemetry)
    instance = await start_daemon(telemetry, ManualClock(), static_dir=static_dir)
    try:
        yield instance
    finally:
        await instance.stop()


def _url(daemon: Daemon, path: str) -> str:
    return f"http://127.0.0.1:{daemon.web_port}{path}"


async def _collect(ws: aiohttp.ClientWebSocketResponse, wanted: set[str], limit: float = 3.0) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    seen: set[str] = set()
    async with asyncio.timeout(limit):
        while not wanted <= seen:
            message = await ws.receive()
            assert message.type is aiohttp.WSMsgType.TEXT, message
            event = json.loads(message.data)
            events.append(event)
            seen.add(event["type"])
    return events


async def test_ui_req_static_console_is_served(daemon: Daemon) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.get(_url(daemon, "/")) as response:
            assert response.status == 200
            assert "index" in await response.text()
        async with session.get(_url(daemon, "/console/")) as response:
            assert response.status == 200
            assert "console" in await response.text()
        async with session.get(_url(daemon, "/missing")) as response:
            assert response.status == 404


async def test_static_root_cannot_be_escaped(daemon: Daemon) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.get(_url(daemon, "/..%2Fsecret.txt")) as response:
            assert response.status in (403, 404)
            assert "do not serve" not in await response.text()


async def test_dns_rebinding_host_header_is_refused(daemon: Daemon) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.get(_url(daemon, "/"), headers={"Host": "attacker.example"}) as response:
            assert response.status == 403


async def test_websocket_events_are_schema_valid_and_carry_real_frames(
    daemon: Daemon, tmp_path: Path
) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(_url(daemon, "/ws")) as ws:
            initial = await _collect(ws, {"agc.state", "system.status"})
            await transmit(daemon, command_bytes(7))
            await transmit(daemon, with_bad_crc(command_bytes(8)))
            later = await _collect(ws, {"telemetry.frame"})
            deadline = asyncio.get_running_loop().time() + 3.0
            while sum(1 for e in later if e["type"] == "telemetry.frame") < 2:
                assert asyncio.get_running_loop().time() < deadline, later
                later += await _collect(ws, {"telemetry.frame"})

    for event in [*initial, *later]:
        SCHEMAS.validate_ws_event(event)
    frames = [event["data"] for event in later if event["type"] == "telemetry.frame"]
    verdicts = {(item["verdict"], item["reason"]) for item in frames}
    assert ("ACCEPTED", "OK") in verdicts
    assert ("REJECTED", "CRC") in verdicts
    assert any(item["frame"] and item["frame"]["seq"] == 7 for item in frames if item["verdict"] == "ACCEPTED")
    assert rejected_records(tmp_path / "telemetry")


def test_ui_req_test_summary_loader_accepts_only_contract_valid_reports(tmp_path: Path) -> None:
    from acoustic.daemon import load_test_summary

    valid = {"profile": "full", "passed": 128, "failed": 0, "skipped": 0, "report_path": "docs/pbt-report.md"}
    good = tmp_path / "good.json"
    good.write_text(json.dumps(valid), encoding="utf-8")
    assert load_test_summary(good, SCHEMAS) == valid

    padded = tmp_path / "padded.json"
    padded.write_text(json.dumps({**valid, "duration_s": 1.0}), encoding="utf-8")
    assert load_test_summary(padded, SCHEMAS) is None

    negative = tmp_path / "negative.json"
    negative.write_text(json.dumps({**valid, "failed": -1}), encoding="utf-8")
    assert load_test_summary(negative, SCHEMAS) is None

    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert load_test_summary(broken, SCHEMAS) is None
    assert load_test_summary(tmp_path / "missing.json", SCHEMAS) is None


async def test_ui_req_console_receives_test_summary_from_report(tmp_path: Path, static_dir: Path) -> None:
    telemetry = tmp_path / "telemetry"
    provision(telemetry)
    summary = {"profile": "full", "passed": 3, "failed": 1, "skipped": 2, "report_path": "docs/pbt-report.md"}
    instance = await start_daemon(telemetry, ManualClock(), static_dir=static_dir, test_summary=summary)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(_url(instance, "/ws")) as ws:
                events = await _collect(ws, {"test.summary"})
        published = [event for event in events if event["type"] == "test.summary"]
        assert len(published) == 1
        SCHEMAS.validate_ws_event(published[0])
        assert published[0]["data"] == summary
    finally:
        await instance.stop()


async def test_ui_req_no_test_summary_event_without_report(daemon: Daemon) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(_url(daemon, "/ws")) as ws:
            events = await _collect(ws, {"agc.state", "system.status"})
            # A summary would be sent right after the initial snapshot; allow time for it.
            with pytest.raises(TimeoutError):
                async with asyncio.timeout(0.5):
                    message = await ws.receive()
                    events.append(json.loads(message.data))
    assert all(event["type"] != "test.summary" for event in events)


async def test_ui_req_console_backfills_frames_accepted_before_it_connected(daemon: Daemon) -> None:
    await transmit(daemon, command_bytes(3))
    await transmit(daemon, command_bytes(4))
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(_url(daemon, "/ws")) as ws:
            events: list[dict[str, Any]] = []
            async with asyncio.timeout(3.0):
                while sum(1 for e in events if e["type"] == "telemetry.frame") < 2:
                    message = await ws.receive()
                    events.append(json.loads(message.data))
    for event in events:
        SCHEMAS.validate_ws_event(event)
    frames = [e["data"] for e in events if e["type"] == "telemetry.frame"]
    assert [f["frame"]["seq"] for f in frames] == [3, 4]
    assert all(f["verdict"] == "ACCEPTED" for f in frames)
    ids = [e["event_id"] for e in events]
    assert ids == sorted(ids) and len(set(ids)) == len(ids)
