"""Kiro PreToolUse hook: block shell tools while a Flight Watch session is live.

The MCP server writes ``telemetry/FLIGHT_MODE`` when Flight Watch starts waiting
for frames and removes it on clean shutdown. While the marker exists, shell
tools are refused with exit code 2 (Kiro blocks the tool and shows stderr).

This is a defense-in-depth layer (steering S-01). The normative safety gate is
``mcp_server/safety_gate.py`` plus the daemon-side execution guard.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MARKER = ROOT / "telemetry" / "FLIGHT_MODE"


def main() -> int:
    # Hook context arrives on stdin; drain it so the producer never blocks.
    try:
        sys.stdin.read()
    except (OSError, ValueError):
        pass
    if not MARKER.exists():
        return 0
    try:
        details = MARKER.read_text(encoding="utf-8").strip().replace("\n", ", ")
    except OSError:
        details = "unreadable marker"
    sys.stderr.write(
        "Apollo-26 Flight Watch is live (" + details + "). "
        "Shell tools are blocked by steering rule S-01; use only the Apollo-26 MCP tools. "
        "If no Flight Watch session is running, the operator may delete telemetry/FLIGHT_MODE.\n"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
