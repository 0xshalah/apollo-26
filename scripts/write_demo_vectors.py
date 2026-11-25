"""Write ``contracts/vectors/dsky-demo.json`` from the real Python planner and AGC engine.

The browser demo (``web-dashboard/lib/demo/``) ports the canonical planner and the
DSKY key handling to TypeScript. These vectors are the equality test: the
TypeScript tests replay every scenario and must reproduce the same keys,
critical reasons, postconditions, key results, and AGC state.

    python scripts/write_demo_vectors.py          # rewrite the committed file
    python scripts/write_demo_vectors.py --check  # exit 1 if the file is stale
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agc_core import AgcEngine, DskyKey, Program  # noqa: E402
from mcp_server.errors import BridgeError  # noqa: E402
from mcp_server.planner import AgcState, CanonicalPlanner, Command  # noqa: E402

CATALOG = ROOT / "contracts" / "dsky-command-catalog-v1.json"
OUTPUT = ROOT / "contracts" / "vectors" / "dsky-demo.json"
CADENCE_MS = 100


def _command(seq: int, verb: int, noun: int, program: int, **payload: Any) -> dict[str, Any]:
    return {
        "seq": seq,
        "critical": bool(payload.get("critical", False)),
        "verb": verb,
        "noun": noun,
        "program": program,
        "r1_centidegrees": payload.get("r1", 0),
        "r2_centidegrees": payload.get("r2", 0),
        "delta_v_tenths_fps": payload.get("dv", 0),
    }


# Each scenario starts from a fresh engine. A step is either a COMMAND (plan it
# against the current state, then press the canonical keys if a plan exists) or a
# raw key list pressed 100 ms apart.
SCENARIOS: list[dict[str, Any]] = [
    {
        "id": "v25_load",
        "steps": [{"command": _command(1, 25, 81, 0, r1=1250, r2=420, dv=3120)}],
    },
    {
        "id": "p40_burn_then_terminate",
        "steps": [
            {"command": _command(2, 37, 0, 40, r1=1250, r2=420, dv=3120, critical=True)},
            {"command": _command(4, 34, 0, 0)},
            {"command": _command(5, 37, 0, 0)},
        ],
    },
    {
        "id": "p40_zero_delta_v_unflagged",
        "steps": [{"command": _command(6, 37, 0, 40, r1=100, r2=200, dv=0)}],
    },
    {
        "id": "v37_while_p40",
        "steps": [
            {"command": _command(7, 37, 0, 40, r1=1, r2=2, dv=3)},
            {"command": _command(8, 37, 0, 40, r1=1, r2=2, dv=3)},
        ],
    },
    {
        "id": "negative_and_limit_values",
        "steps": [{"command": _command(9, 25, 81, 0, r1=-1250, r2=16383, dv=-16383)}],
    },
    {
        "id": "unsupported_commands",
        "steps": [
            {"command": _command(10, 16, 0, 0)},
            {"command": _command(11, 25, 81, 0, r1=20000)},
            {"command": _command(12, 37, 0, 0, r1=5)},
            {"command": _command(13, 37, 0, 99)},
        ],
    },
    {
        "id": "delta_v_threshold_boundary",
        "steps": [
            {"command": _command(14, 37, 0, 40, dv=1)},
            {"command": _command(15, 34, 0, 0)},
            {"command": _command(16, 37, 0, 40, dv=-1)},
        ],
    },
    {
        "id": "data_entry_pro_clr_and_cadence",
        "steps": [
            {
                "keys": [
                    "VERB", "DIGIT_2", "DIGIT_5", "ENTR", "NOUN", "DIGIT_8", "DIGIT_1", "ENTR",
                    "PLUS", "DIGIT_7", "CLR", "DIGIT_8", "ENTR",
                    "MINUS", "CLR", "PLUS", "DIGIT_3", "ENTR",
                    "PLUS", "DIGIT_4", "PRO",
                ]
            },
            {
                "keys": [
                    "VERB", "DIGIT_2", "DIGIT_5", "ENTR", "NOUN", "DIGIT_8", "DIGIT_1", "ENTR",
                    "PLUS", "DIGIT_1", "PRO",
                ]
            },
            {"keys": ["RSET", "VERB", "DIGIT_3"], "gap_ms": 50},
            {"keys": ["KEY_REL", "VERB", "DIGIT_3", "DIGIT_4", "ENTR"], "gap_ms": 150},
        ],
    },
    {
        "id": "invalid_keys_latch_opr_err",
        "steps": [
            {"keys": ["NOUN"]},
            {"keys": ["VERB"]},
            {"keys": ["RSET", "VERB", "DIGIT_9", "DIGIT_9", "ENTR"]},
            {"keys": ["RSET", "VERB", "DIGIT_3", "DIGIT_7", "ENTR", "DIGIT_9", "DIGIT_9", "ENTR"]},
            {
                "keys": [
                    "RSET", "VERB", "DIGIT_2", "DIGIT_5", "ENTR", "NOUN", "DIGIT_8", "DIGIT_1",
                    "ENTR", "PLUS", "DIGIT_1", "DIGIT_6", "DIGIT_3", "DIGIT_8", "DIGIT_4", "ENTR",
                ]
            },
            {
                "keys": [
                    "RSET", "VERB", "DIGIT_2", "DIGIT_5", "ENTR",
                    "NOUN", "DIGIT_1", "DIGIT_6", "ENTR",
                ]
            },
            {"keys": ["RSET", "VERB", "DIGIT_2", "CLR", "DIGIT_3", "DIGIT_4", "ENTR"]},
        ],
    },
]  # fmt: skip


def _state(engine: AgcEngine) -> dict[str, Any]:
    """Same projection as ``AgcHost.view`` (the RPC ``agcSnapshot`` control fields)."""

    snap = engine.snapshot()
    return {
        "program": 40 if snap.program is Program.P40 else 0,
        "verb": snap.verb_display or 0,
        "noun": snap.noun_display or 0,
        "r1": snap.r1.signed_value,
        "r2": snap.r2.signed_value,
        "r3": snap.r3.signed_value,
        "input_state": snap.dsky_state.value,
        "pending_entry": None if snap.pending_entry is None else snap.pending_entry.kind.value,
        "key_rel": snap.lamps.key_rel,
        "opr_err": snap.lamps.opr_err,
    }


def _agc_state(state: dict[str, Any]) -> AgcState:
    return AgcState(
        state_revision=0,
        program=state["program"],
        verb=state["verb"],
        noun=state["noun"],
        r1=state["r1"],
        r2=state["r2"],
        r3=state["r3"],
        input_state=state["input_state"],
        pending_entry=state["pending_entry"],
        key_rel=state["key_rel"],
        opr_err=state["opr_err"],
        snapshot_digest="",
    )


def _press(
    engine: AgcEngine, keys: list[str], clock: list[int], gap_ms: int = CADENCE_MS
) -> list[dict[str, Any]]:
    results = []
    for name in keys:
        clock[0] += gap_ms
        result = engine.press_key(DskyKey[name], clock[0])
        results.append(
            {
                "key": name,
                "accepted": result.accepted,
                "error": None if result.error is None else result.error.value,
            }
        )
    return results


def build() -> dict[str, Any]:
    planner = CanonicalPlanner(json.loads(CATALOG.read_text(encoding="utf-8")))
    scenarios = []
    for scenario in SCENARIOS:
        engine = AgcEngine()
        clock = [0]
        steps = []
        for step in scenario["steps"]:
            before = _state(engine)
            out: dict[str, Any] = {"state_before": before}
            if "command" in step:
                frame = step["command"]
                out["command"] = frame
                try:
                    plan = planner.plan(
                        Command.from_frame({**frame, "frame_type": "COMMAND"}), _agc_state(before)
                    )
                except BridgeError as error:
                    out["plan_error"] = error.code.value
                    out["state_after"] = _state(engine)
                    steps.append(out)
                    continue
                out["plan"] = {
                    "command_id": plan.command_id,
                    "keys": list(plan.keys),
                    "critical_reasons": [reason.value for reason in plan.critical_reasons],
                    "postcondition": plan.postcondition.to_json(),
                }
                keys = list(plan.keys)
            else:
                keys = step["keys"]
                out["keys"] = keys
            gap_ms = step.get("gap_ms", CADENCE_MS)
            if gap_ms != CADENCE_MS:
                out["gap_ms"] = gap_ms
            out["key_results"] = _press(engine, keys, clock, gap_ms)
            out["state_after"] = _state(engine)
            if "plan" in out:
                out["postcondition_matched"] = plan.postcondition.matches(
                    _agc_state(out["state_after"])
                )
            steps.append(out)
        scenarios.append({"id": scenario["id"], "steps": steps})
    return {
        "schema_version": "1.0",
        "description": (
            "Generated by scripts/write_demo_vectors.py from mcp_server.planner and "
            "agc_core.AgcEngine. Do not edit by hand."
        ),
        "catalog_version": planner.catalog_version,
        "key_cadence_ms": CADENCE_MS,
        "scenarios": scenarios,
    }


def render() -> str:
    return json.dumps(build(), indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--check", action="store_true", help="fail if the committed file is stale")
    args = parser.parse_args(argv)
    text = render()
    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != text:
            print(f"{OUTPUT} is stale; run scripts/write_demo_vectors.py", file=sys.stderr)
            return 1
        return 0
    OUTPUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
