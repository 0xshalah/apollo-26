"""The real stdio MCP server starts, lists exactly the six tools, and answers calls."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from tests.harness import ROOT

pytestmark = pytest.mark.integration

EXPECTED_TOOLS = {
    "read_telemetry_frames",
    "await_telemetry_frame",
    "inspect_agc_status",
    "plan_dsky_sequence",
    "execute_dsky_sequence",
    "verify_crc16",
}
GOLDEN_COMMAND = "a52601010000002a000000000125002804e201a4000079e003ef57ace1ee8c8d7be6"


def _payload(result: object) -> dict[str, object]:
    structured = getattr(result, "structuredContent", None)
    if structured:
        return dict(structured)
    content = getattr(result, "content")
    return json.loads(content[0].text)


async def test_mcp_server_lists_six_tools_and_verifies_crc(tmp_path: Path) -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "mcp_server.server",
            "--contracts-dir",
            str(ROOT / "contracts"),
            "--state-dir",
            str(tmp_path / "mcp"),
            "--no-flight-marker",
            "--rpc-port",
            "1",
        ],
        cwd=str(ROOT),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            assert {tool.name for tool in tools.tools} == EXPECTED_TOOLS

            good = _payload(await session.call_tool("verify_crc16", {"hex_payload": GOLDEN_COMMAND[4:]}))
            assert good["ok"] is True
            assert good["data"]["matches"] is True  # type: ignore[index]

            corrupted = GOLDEN_COMMAND[4:-2] + ("00" if not GOLDEN_COMMAND.endswith("00") else "01")
            bad = _payload(await session.call_tool("verify_crc16", {"hex_payload": corrupted}))
            assert bad["data"]["matches"] is False  # type: ignore[index]

            offline = _payload(await session.call_tool("inspect_agc_status", {}))
            assert offline["ok"] is False


def test_flight_mode_guard_blocks_only_while_marker_exists() -> None:
    script = ROOT / "scripts" / "hooks" / "flight_mode_guard.py"
    marker = ROOT / "telemetry" / "FLIGHT_MODE"
    assert not marker.exists(), "a live Flight Watch marker exists; stop it before running tests"
    allowed = subprocess.run([sys.executable, str(script)], input="{}", capture_output=True, text=True, check=False)
    assert allowed.returncode == 0
    marker.write_text("session_id=test\nstarted_at=2026-11-20T12:00:00.000Z\n", encoding="utf-8")
    try:
        blocked = subprocess.run([sys.executable, str(script)], input="{}", capture_output=True, text=True, check=False)
    finally:
        marker.unlink()
    assert blocked.returncode == 2
    assert "Flight Watch is live" in blocked.stderr


def test_mcp_req_execute_is_never_auto_approved() -> None:
    """MCP config (template and installed copy, if present) must not auto-approve writes."""

    candidates = [ROOT / "docs" / "kiro-mcp.json", ROOT / ".kiro" / "settings" / "mcp.json"]
    checked = 0
    for path in candidates:
        if not path.exists():
            continue
        servers = json.loads(path.read_text(encoding="utf-8"))["mcpServers"]
        for name, server in servers.items():
            approved = server.get("autoApprove", [])
            assert "*" not in approved, f"{path}:{name} auto-approves everything"
            assert "execute_dsky_sequence" not in approved, f"{path}:{name} auto-approves execute"
        checked += 1
    assert checked >= 1


def test_kiro_hooks_reference_existing_commands() -> None:
    hooks_dir = ROOT / ".kiro" / "hooks"
    names = {path.stem for path in hooks_dir.glob("*.json")}
    assert {"flight-mode-shell-guard", "test-after-spec-task", "pbt-on-save"} <= names
    for path in hooks_dir.glob("*.json"):
        document = json.loads(path.read_text(encoding="utf-8"))
        for hook in document["hooks"]:
            command = hook["action"]["command"]
            script = next(part for part in command.split() if part.startswith("scripts\\"))
            assert (ROOT / script.replace("\\", "/")).exists(), f"{path.name}: missing {script}"
