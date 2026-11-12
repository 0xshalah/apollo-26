"""Daemon-owned host for the single ``AgcEngine`` writer.

Responsibilities: global DSKY writer lock, KEY REL check before every key,
>= 100 ms cadence via the injected clock, OPR ERR check after every key,
P40 COMP ACTY ticks, and the *control revision* used for inspection freshness.

The control revision changes only when operator-relevant state changes
(program, DSKY input, VERB/NOUN, R1-R3, KEY REL, OPR ERR).  COMP ACTY ticks and
UPLINK ACTY toggles are excluded; otherwise P40's 500 ms heartbeat would make
every inspection stale (documented in mcp-bridge implementation notes).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from acoustic.clock import Clock, format_timestamp
from acoustic.command_catalog import AgcView
from acoustic.execution import ExecutionErrorCode
from agc_core import (
    AgcEngine,
    AgcErrorCode,
    AgcSnapshot,
    CompActyTick,
    DisplayBusy,
    DskyKey,
    Program,
    ReceiverActivity,
)


def _program_number(program: Program) -> int:
    return 40 if program is Program.P40 else 0


@dataclass(frozen=True, slots=True)
class SequenceOutcome:
    keys_accepted: int
    error: ExecutionErrorCode | None


class AgcHost:
    def __init__(self, engine: AgcEngine, clock: Clock, on_change: Callable[[], None]) -> None:
        self._engine = engine
        self._clock = clock
        self._on_change = on_change
        self.writer_lock = asyncio.Lock()
        self.keys_pressed = 0
        """Key presses handed to the engine since start (zero-actuation evidence)."""
        self._control_revision = 1
        self._control = self._control_projection(engine.snapshot())

    @property
    def control_revision(self) -> int:
        return self._control_revision

    @property
    def busy(self) -> bool:
        return self.writer_lock.locked()

    @staticmethod
    def _control_projection(snapshot: AgcSnapshot) -> tuple[object, ...]:
        return (
            snapshot.program,
            snapshot.dsky_state,
            snapshot.verb_display,
            snapshot.noun_display,
            snapshot.pending_entry,
            snapshot.r1.raw_data,
            snapshot.r2.raw_data,
            snapshot.r3.raw_data,
            snapshot.lamps.key_rel,
            snapshot.lamps.opr_err,
        )

    def _after_mutation(self) -> None:
        projection = self._control_projection(self._engine.snapshot())
        if projection != self._control:
            self._control = projection
            self._control_revision += 1
        self._on_change()

    def snapshot(self) -> AgcSnapshot:
        return self._engine.snapshot()

    def view(self) -> AgcView:
        snap = self._engine.snapshot()
        return AgcView(
            program=_program_number(snap.program),
            verb=snap.verb_display or 0,
            noun=snap.noun_display or 0,
            r1=snap.r1.signed_value,
            r2=snap.r2.signed_value,
            r3=snap.r3.signed_value,
            input_state=snap.dsky_state.value,
            pending_entry=None if snap.pending_entry is None else snap.pending_entry.kind.value,
            key_rel=snap.lamps.key_rel,
            opr_err=snap.lamps.opr_err,
        )

    def inspect(self, catalog_version: str) -> dict[str, Any]:
        """RPC ``agcSnapshot`` projection (contracts/mcp-daemon-rpc.schema.json)."""

        snap = self._engine.snapshot()
        view = self.view()
        control = {
            "state_revision": self._control_revision,
            "program": view.program,
            "verb": view.verb,
            "noun": view.noun,
            "registers": {"r1": view.r1, "r2": view.r2, "r3": view.r3},
            "input_state": view.input_state,
            "pending_entry": view.pending_entry,
            "key_rel": view.key_rel,
            "opr_err": view.opr_err,
        }
        digest = hashlib.sha256(
            json.dumps(control, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return {
            "state_revision": self._control_revision,
            "engine_revision": snap.revision,
            "captured_at": format_timestamp(self._clock.now_utc()),
            "program": view.program,
            "verb": view.verb,
            "noun": view.noun,
            "registers": {"r1": view.r1, "r2": view.r2, "r3": view.r3},
            "input_state": view.input_state,
            "pending_entry": view.pending_entry,
            "lamps": {
                "comp_acty": snap.lamps.comp_acty,
                "uplink_acty": snap.lamps.uplink_acty,
                "key_rel": snap.lamps.key_rel,
                "opr_err": snap.lamps.opr_err,
            },
            "snapshot_digest": digest,
            "catalog_version": catalog_version,
        }

    def ws_state(self) -> dict[str, Any]:
        """``agc.state`` event data (contracts/websocket-events.schema.json)."""

        snap = self._engine.snapshot()
        view = self.view()
        return {
            "program": view.program,
            "verb": view.verb,
            "noun": view.noun,
            "r1": view.r1,
            "r2": view.r2,
            "r3": view.r3,
            "lamps": {
                "comp_acty": snap.lamps.comp_acty,
                "uplink_acty": snap.lamps.uplink_acty,
                "key_rel": snap.lamps.key_rel,
                "opr_err": snap.lamps.opr_err,
            },
        }

    def set_uplink(self, active: bool) -> None:
        if self._engine.snapshot().lamps.uplink_acty != active:
            self._engine.set_receiver_activity(ReceiverActivity(active))
            self._after_mutation()

    def set_key_rel(self, active: bool) -> None:
        """Display-busy input (KEY REL lamp); used by operator tooling and tests."""

        self._engine.set_display_busy(DisplayBusy(active))
        self._after_mutation()

    def tick_comp_acty(self) -> bool:
        snap = self._engine.snapshot()
        if snap.program is not Program.P40 or snap.next_comp_acty_tick is None:
            return False
        result = self._engine.apply_p40_tick(CompActyTick(snap.next_comp_acty_tick))
        if result.success:
            self._after_mutation()
        return result.success

    async def press_sequence(
        self,
        keys: tuple[str, ...],
        min_cadence_ms: int,
        on_key: Callable[[int], None] | None = None,
    ) -> SequenceOutcome:
        """Press canonical keys; caller must hold ``writer_lock``."""

        if not self.writer_lock.locked():
            raise RuntimeError("press_sequence requires the DSKY writer lock")
        accepted = 0
        for name in keys:
            if self._engine.snapshot().lamps.key_rel:
                return SequenceOutcome(accepted, ExecutionErrorCode.KEY_REL_ACTIVE)
            last = self._engine.last_accepted_key_ms
            now = self._clock.monotonic_ms()
            if last is not None and now - last < min_cadence_ms:
                await self._clock.sleep_ms(min_cadence_ms - (now - last))
            # KEY REL may have lit while waiting for cadence.
            if self._engine.snapshot().lamps.key_rel:
                return SequenceOutcome(accepted, ExecutionErrorCode.KEY_REL_ACTIVE)
            self.keys_pressed += 1
            result = self._engine.press_key(DskyKey[name], self._clock.monotonic_ms())
            if not result.accepted:
                self._after_mutation()
                code = (
                    ExecutionErrorCode.KEY_REL_ACTIVE
                    if result.error is AgcErrorCode.KEY_REL_ACTIVE
                    else ExecutionErrorCode.KEY_REJECTED
                )
                return SequenceOutcome(accepted, code)
            accepted += 1
            self._after_mutation()
            if on_key is not None:
                on_key(accepted)
            if self._engine.snapshot().lamps.opr_err:
                return SequenceOutcome(accepted, ExecutionErrorCode.OPR_ERR_ACTIVE)
        return SequenceOutcome(accepted, None)
