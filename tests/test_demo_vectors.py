"""The browser demo's golden vectors must match the current Python planner and AGC engine."""

from __future__ import annotations

import json

from scripts.write_demo_vectors import OUTPUT, render


def test_demo_vectors_are_current() -> None:
    assert OUTPUT.exists(), "run scripts/write_demo_vectors.py"
    assert OUTPUT.read_text(encoding="utf-8") == render(), "run scripts/write_demo_vectors.py"


def test_demo_vectors_cover_the_safety_story() -> None:
    document = json.loads(render())
    steps = {s["id"]: s["steps"] for s in document["scenarios"]}
    burn = steps["p40_burn_then_terminate"][0]
    assert burn["plan"]["critical_reasons"] == ["NONZERO_P40_ACTIVATION", "FRAME_CRITICAL_FLAG"]
    assert len(burn["plan"]["keys"]) == 36
    assert burn["postcondition_matched"] is True
    assert steps["p40_burn_then_terminate"][1]["plan"]["critical_reasons"] == ["V34_WHILE_P40"]
    assert steps["v37_while_p40"][1]["plan"]["critical_reasons"] == ["V37_WHILE_P40"]
    assert steps["p40_zero_delta_v_unflagged"][0]["plan"]["critical_reasons"] == []
    assert [s["plan_error"] for s in steps["unsupported_commands"]] == ["UNSUPPORTED_COMMAND"] * 4
    assert all(s["state_after"]["opr_err"] for s in steps["invalid_keys_latch_opr_err"][:-1])
