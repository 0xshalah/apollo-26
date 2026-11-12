"""End-to-end Flight Watch and abuse scenarios (docs/threat-model.md section 4).

Audio is synthesized with the real modem and fed through the real daemon
pipeline; the MCP tool layer talks to the daemon over its 127.0.0.1 RPC port.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from acoustic.clock import ManualClock
from acoustic.command_catalog import CommandFields
from acoustic.daemon import Daemon
from acoustic.rpc_server import RpcError
from tests.harness import (
    CATALOG,
    CATALOG_DOC,
    LINK_KEY,
    OPERATOR_KEY,
    ArraySource,
    auth_bytes,
    await_inspect_plan,
    command_bytes,
    inbox_records,
    make_service,
    p40_bytes,
    provision,
    rejected_records,
    start_daemon,
    transmit,
    with_bad_crc,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def clock() -> ManualClock:
    return ManualClock()


@pytest.fixture
async def daemon(tmp_path: Path, clock: ManualClock) -> AsyncIterator[Daemon]:
    provision(tmp_path)
    instance = await start_daemon(tmp_path, clock)
    try:
        yield instance
    finally:
        await instance.stop()


def _data(result: dict[str, Any]) -> dict[str, Any]:
    assert result["ok"], result
    return result["data"]


def _code(result: dict[str, Any]) -> str:
    assert not result["ok"], result
    return result["error"]["code"]


async def _deliver(service: Any, timeout_sec: float = 0.5) -> dict[str, Any]:
    return _data(await service.await_telemetry_frame(timeout_sec))


async def test_threat_1_valid_command_executes_canonical_plan(
    daemon: Daemon, clock: ManualClock
) -> None:
    await transmit(daemon, command_bytes(1, r1=1250, r2=420, dv=3120))
    service, _, _ = make_service(daemon.rpc_port, clock)
    delivered = await _deliver(service)
    assert delivered["status"] == "FRAME"
    assert delivered["lifecycle"]["command_state"] == "READY"

    plan = _data(await await_inspect_plan(service, clock, 1))
    assert plan["critical"] is False
    executed = _data(await service.execute_dsky_sequence(plan["keys"], 1))
    assert executed["status"] == "EXECUTED"
    assert executed["keys_accepted"] == executed["keys_total"] == len(plan["keys"])

    snapshot = _data(await service.inspect_agc_status())
    assert snapshot["registers"] == {"r1": 1250, "r2": 420, "r3": 3120}
    await service.close()


async def test_threat_2_bad_crc_is_rejected_and_never_delivered(
    daemon: Daemon, clock: ManualClock, tmp_path: Path
) -> None:
    await transmit(daemon, with_bad_crc(command_bytes(1)))
    assert inbox_records(tmp_path) == []
    reasons = [record["reason"] for record in rejected_records(tmp_path)]
    assert "CRC" in reasons
    service, _, _ = make_service(daemon.rpc_port, clock)
    assert _data(await service.await_telemetry_frame(0.05))["status"] == "TIMEOUT"
    await service.close()


async def test_threat_3_wrong_link_key_with_valid_crc_is_rejected_hmac(
    daemon: Daemon, tmp_path: Path
) -> None:
    await transmit(daemon, command_bytes(1, key=b"attacker-key-not-the-link-key"))
    assert inbox_records(tmp_path) == []
    assert [record["reason"] for record in rejected_records(tmp_path)] == ["HMAC"]


async def test_threat_4_replay_is_rejected_after_daemon_restart(
    tmp_path: Path, clock: ManualClock
) -> None:
    provision(tmp_path)
    first = await start_daemon(tmp_path, clock)
    await transmit(first, command_bytes(5))
    await first.stop()
    assert [record["frame"]["seq"] for record in inbox_records(tmp_path)] == [5]

    second = await start_daemon(tmp_path, clock)
    try:
        await transmit(second, command_bytes(5))
        await transmit(second, command_bytes(4))
        reasons = [record["reason"] for record in rejected_records(tmp_path)]
        assert reasons.count("REPLAY") == 2
        assert [record["frame"]["seq"] for record in inbox_records(tmp_path)] == [5]
    finally:
        await second.stop()


async def test_threat_5_critical_p40_needs_matching_auth_and_executes_once(
    daemon: Daemon, clock: ManualClock
) -> None:
    service, _, _ = make_service(daemon.rpc_port, clock)

    await transmit(daemon, p40_bytes(10, dv=1200))
    held = await _deliver(service)
    assert held["lifecycle"]["command_state"] == "HELD"

    plan = _data(await await_inspect_plan(service, clock, 10))
    assert plan["critical"] is True
    assert _code(await service.execute_dsky_sequence(plan["keys"], 10)) == "AUTH_REQUIRED"

    # AUTH signed with the wrong operator key never leaves the daemon.
    await transmit(daemon, auth_bytes(11, 10, key=b"not-the-operator-key"))
    assert _data(await service.await_telemetry_frame(0.05))["status"] == "TIMEOUT"
    # AUTH signed with the *link* key is also rejected: keys are not interchangeable.
    await transmit(daemon, auth_bytes(12, 10, key=LINK_KEY))
    assert _data(await service.await_telemetry_frame(0.05))["status"] == "TIMEOUT"

    await transmit(daemon, auth_bytes(13, 10, key=OPERATOR_KEY))
    matched = await _deliver(service)
    assert matched["lifecycle"]["auth_state"] == "MATCHED"
    assert matched["lifecycle"]["command_state"] == "READY"

    plan = _data(await await_inspect_plan(service, clock, 10))
    first = _data(await service.execute_dsky_sequence(plan["keys"], 10))
    assert first["status"] == "EXECUTED"
    assert _data(await service.inspect_agc_status())["program"] == 40

    revision_after_first = _snapshot_revision(daemon)
    replay = _data(await service.execute_dsky_sequence(plan["keys"], 10))
    assert replay["idempotent_replay"] is True
    assert replay["keys_accepted"] == first["keys_accepted"]
    assert _snapshot_revision(daemon) == revision_after_first
    await service.close()


async def test_threat_6_auth_reuse_is_rejected(daemon: Daemon, clock: ManualClock) -> None:
    service, _, _ = make_service(daemon.rpc_port, clock)
    await transmit(daemon, p40_bytes(20, dv=900))
    await _deliver(service)
    await transmit(daemon, auth_bytes(21, 20))
    await _deliver(service)
    plan = _data(await await_inspect_plan(service, clock, 20))
    _data(await service.execute_dsky_sequence(plan["keys"], 20))

    await transmit(daemon, auth_bytes(22, 20))
    reused = await _deliver(service)
    assert reused["lifecycle"]["error_code"] == "AUTH_USED"
    await service.close()


async def test_threat_7_noise_never_produces_frames_or_keys(
    daemon: Daemon, clock: ManualClock, tmp_path: Path
) -> None:
    before = _snapshot_revision(daemon)
    generator = np.random.default_rng(26)
    noise = generator.normal(0.0, 0.3, 48_000 * 2)
    await daemon.run_source(ArraySource(noise))
    assert inbox_records(tmp_path) == []
    assert _snapshot_revision(daemon) == before
    service, _, _ = make_service(daemon.rpc_port, clock)
    assert _data(await service.await_telemetry_frame(0.05))["status"] == "TIMEOUT"
    await service.close()


async def test_threat_8_non_canonical_plan_is_rejected(
    daemon: Daemon, clock: ManualClock
) -> None:
    service, _, _ = make_service(daemon.rpc_port, clock)
    await transmit(daemon, command_bytes(30))
    await _deliver(service)
    plan = _data(await await_inspect_plan(service, clock, 30))
    tampered = list(plan["keys"])
    tampered[-2] = "9" if tampered[-2] != "9" else "8"
    assert _code(await service.execute_dsky_sequence(tampered, 30)) == "PLAN_MISMATCH"
    assert _code(await service.execute_dsky_sequence([*plan["keys"], "RSET"], 30)) == "PLAN_MISMATCH"
    await service.close()


async def test_mcp_req_inspect_before_act_is_enforced(daemon: Daemon, clock: ManualClock) -> None:
    service, _, _ = make_service(daemon.rpc_port, clock)
    await transmit(daemon, command_bytes(40))
    await _deliver(service)
    assert _code(await service.plan_dsky_sequence(40)) == "INSPECTION_REQUIRED"
    plan = _data(await await_inspect_plan(service, clock, 40))
    clock.advance_ms(CATALOG_DOC["execution"]["inspection_max_age_ms"])
    assert _code(await service.execute_dsky_sequence(plan["keys"], 40)) == "INSPECTION_STALE"
    await service.close()


async def test_mcp_req_held_command_expires_after_hold_window(
    daemon: Daemon, clock: ManualClock
) -> None:
    service, _, _ = make_service(daemon.rpc_port, clock)
    await transmit(daemon, p40_bytes(50, dv=1500))
    await _deliver(service)
    clock.advance_ms(CATALOG_DOC["authorization"]["hold_expiry_ms"] + 1)
    plan_result = await await_inspect_plan(service, clock, 50)
    assert _code(plan_result) == "COMMAND_CLOSED"

    await transmit(daemon, auth_bytes(51, 50))
    late = await _deliver(service)
    assert late["lifecycle"]["error_code"] == "AUTH_EXPIRED"
    await service.close()


async def test_daemon_refuses_direct_rpc_execution_of_critical_command_without_auth(
    daemon: Daemon,
) -> None:
    """A local client that skips the MCP SafetyGate still cannot actuate a critical command."""

    await transmit(daemon, p40_bytes(60, dv=1200))
    view = daemon.agc.view()
    plan = CATALOG.plan(
        CommandFields(
            seq=60,
            critical=False,
            verb=37,
            noun=0,
            program=40,
            r1_centidegrees=1250,
            r2_centidegrees=420,
            delta_v_tenths_fps=1200,
        ),
        view,
    )
    assert plan.critical
    before = _snapshot_revision(daemon)
    with pytest.raises(RpcError) as raised:
        await daemon.handle_rpc(
            "dsky.execute",
            {
                "frame_seq": 60,
                "keys": list(plan.keys),
                "plan_digest": plan.plan_digest,
                "catalog_version": CATALOG.version,
                "expected_revision": daemon.agc.control_revision,
                "auth_seq": None,
                "operation_id": str(uuid.uuid4()),
                "min_cadence_ms": 100,
            },
        )
    assert raised.value.code == "AUTH_REQUIRED"
    assert _snapshot_revision(daemon) == before


async def test_listeners_bind_only_to_loopback(daemon: Daemon) -> None:
    addresses = daemon.listener_addresses
    assert addresses, "expected RPC and web listeners"
    assert {host for host, _ in addresses} == {"127.0.0.1"}


def _snapshot_revision(daemon: Daemon) -> int:
    return int(daemon.agc.control_revision)
