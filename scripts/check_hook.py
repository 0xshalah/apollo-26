"""Developer check: run the quick-tests hook command exactly as Kiro would and record the result."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
result = subprocess.run(
    ["cmd", "/c", r"scripts\hooks\quick_tests.cmd"],
    cwd=ROOT,
    capture_output=True,
    text=True,
    check=False,
)
report = ROOT / "telemetry" / "state" / "hook-run.txt"
report.write_text(
    f"exit={result.returncode}\n--- stdout ---\n{result.stdout[-3000:]}\n--- stderr ---\n{result.stderr[-2000:]}\n",
    encoding="utf-8",
)
