"""Canonical DSKY planner and criticality policy (MCP side).

Deterministic: no clock, randomness, filesystem, network, or agent text enters
``CanonicalPlanner.plan``.  The catalog document is injected already validated.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final

from mcp_server.errors import BridgeError, ErrorCode

FIELD_NAMES: Final = ("program", "r1_centidegrees", "r2_centidegrees", "delta_v_tenths_fps")


class CriticalReason(StrEnum):
    V37_WHILE_P40 = "V37_WHILE_P40"
    V34_WHILE_P40 = "V34_WHILE_P40"
    NONZERO_P40_ACTIVATION = "NONZERO_P40_ACTIVATION"
    FRAME_CRITICAL_FLAG = "FRAME_CRITICAL_FLAG"


@dataclass(frozen=True, slots=True)
class Command:
    """Accepted COMMAND payload as delivered by the daemon (schema-validated)."""

    seq: int
    critical: bool
    verb: int
    noun: int
    program: int
    r1_centidegrees: int
    r2_centidegrees: int
    delta_v_tenths_fps: int

    @classmethod
    def from_frame(cls, frame: dict[str, Any]) -> Command:
        if frame["frame_type"] != "COMMAND":
            raise BridgeError(ErrorCode.NOT_FOUND, f"frame {frame['seq']} is not a COMMAND")
        return cls(
            seq=frame["seq"],
            critical=frame["critical"],
            verb=frame["verb"],
            noun=frame["noun"],
            program=frame["program"],
            r1_centidegrees=frame["r1_centidegrees"],
            r2_centidegrees=frame["r2_centidegrees"],
            delta_v_tenths_fps=frame["delta_v_tenths_fps"],
        )

    def value(self, name: str) -> int:
        return {
            "program": self.program,
            "r1_centidegrees": self.r1_centidegrees,
            "r2_centidegrees": self.r2_centidegrees,
            "delta_v_tenths_fps": self.delta_v_tenths_fps,
        }[name]


@dataclass(frozen=True, slots=True)
class AgcState:
    """Typed view of the daemon ``agcSnapshot`` used by planning and the gate."""

    state_revision: int
    program: int
    verb: int
    noun: int
    r1: int
    r2: int
    r3: int
    input_state: str
    pending_entry: str | None
    key_rel: bool
    opr_err: bool
    snapshot_digest: str

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, Any]) -> AgcState:
        return cls(
            state_revision=snapshot["state_revision"],
            program=snapshot["program"],
            verb=snapshot["verb"],
            noun=snapshot["noun"],
            r1=snapshot["registers"]["r1"],
            r2=snapshot["registers"]["r2"],
            r3=snapshot["registers"]["r3"],
            input_state=snapshot["input_state"],
            pending_entry=snapshot["pending_entry"],
            key_rel=snapshot["lamps"]["key_rel"],
            opr_err=snapshot["lamps"]["opr_err"],
            snapshot_digest=snapshot["snapshot_digest"],
        )


@dataclass(frozen=True, slots=True)
class Postcondition:
    program: int
    verb: int
    noun: int
    r1: int
    r2: int
    r3: int

    def to_json(self) -> dict[str, Any]:
        return {
            "program": self.program,
            "verb": self.verb,
            "noun": self.noun,
            "registers": {"r1": self.r1, "r2": self.r2, "r3": self.r3},
            "required_clear_lamps": ["opr_err"],
        }

    def matches(self, state: AgcState) -> bool:
        return (
            state.program == self.program
            and state.verb == self.verb
            and state.noun == self.noun
            and (state.r1, state.r2, state.r3) == (self.r1, self.r2, self.r3)
            and not state.opr_err
        )


@dataclass(frozen=True, slots=True)
class Plan:
    frame_seq: int
    catalog_version: str
    command_id: str
    keys: tuple[str, ...]
    postcondition: Postcondition
    critical_reasons: tuple[CriticalReason, ...]
    plan_digest: str

    @property
    def critical(self) -> bool:
        return bool(self.critical_reasons)


def compute_plan_digest(catalog_version: str, frame_seq: int, keys: tuple[str, ...]) -> str:
    """SHA-256 over canonical JSON {catalog_version, frame_seq, keys} (catalog ``plan_digest``)."""

    canonical = json.dumps(
        {"catalog_version": catalog_version, "frame_seq": frame_seq, "keys": list(keys)},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def precondition_error(state: AgcState) -> BridgeError | None:
    if state.key_rel:
        return BridgeError(ErrorCode.KEY_REL_ACTIVE, "KEY REL is lit; no keys may be sent")
    if state.opr_err:
        return BridgeError(ErrorCode.OPR_ERR_ACTIVE, "OPR ERR is lit; operator RSET required")
    if state.input_state != "IDLE" or state.pending_entry is not None:
        return BridgeError(
            ErrorCode.AGC_UNAVAILABLE,
            "DSKY input is mid-entry",
            details={"input_state": state.input_state, "pending_entry": state.pending_entry},
        )
    return None


class CanonicalPlanner:
    def __init__(self, catalog: dict[str, Any]) -> None:
        self.catalog_version: str = catalog["catalog_version"]
        criticality = catalog["criticality"]
        declared = {rule["id"] for rule in criticality["rules"]}
        if declared != {reason.value for reason in CriticalReason}:
            raise ValueError("catalog criticality rules differ from the implemented policy")
        self.delta_v_threshold: int = criticality["p40_critical_delta_v_threshold_tenths_fps"]
        self.hold_expiry_ms: int = catalog["authorization"]["hold_expiry_ms"]
        self.inspection_max_age_ms: int = catalog["execution"]["inspection_max_age_ms"]
        self._encodings: dict[str, dict[str, Any]] = catalog["field_encodings"]
        self._segments: dict[str, list[Any]] = catalog["segments"]
        self._entries = {
            (e["match"]["verb"], e["match"]["noun"], e["match"]["program"]): e
            for e in catalog["commands"]
        }
        if len(self._entries) != len(catalog["commands"]):
            raise ValueError("catalog has ambiguous command matches")

    def _expand(self, token: Any, command: Command) -> list[str]:
        if isinstance(token, str):
            return [token]
        value = command.value(token["field"])
        encoding = token["encoding"]
        bounds = self._encodings[encoding]
        if value < bounds["min"] or value > bounds["max"]:
            raise BridgeError(
                ErrorCode.UNSUPPORTED_COMMAND,
                f"{token['field']}={value} cannot be represented ({bounds['min']}..{bounds['max']})",
                frame_seq=command.seq,
                details={"field": token["field"], "value": value},
            )
        if encoding == "DIGITS_2":
            return ["DIGIT_" + char for char in str(value).zfill(2)]
        magnitude = str(abs(value)).zfill(5)
        return ["MINUS" if value < 0 else "PLUS"] + ["DIGIT_" + char for char in magnitude]

    def plan(self, command: Command, state: AgcState) -> Plan:
        entry = self._entries.get((command.verb, command.noun, command.program))
        if entry is None:
            raise BridgeError(
                ErrorCode.UNSUPPORTED_COMMAND,
                f"V{command.verb:02d} N{command.noun:02d} P{command.program:02d} is not in catalog "
                f"{self.catalog_version}",
                frame_seq=command.seq,
            )
        nonzero = [name for name in entry["require_zero"] if command.value(name) != 0]
        if nonzero:
            raise BridgeError(
                ErrorCode.UNSUPPORTED_COMMAND,
                f"{entry['id']} requires zero {', '.join(nonzero)}",
                frame_seq=command.seq,
            )
        keys: list[str] = []
        for segment_name in entry["segments"]:
            for token in self._segments[segment_name]:
                keys.extend(self._expand(token, command))
        spec = entry["postcondition"]
        registers = spec["registers"]
        if registers == "UNCHANGED":
            r1, r2, r3 = state.r1, state.r2, state.r3
        else:
            r1, r2, r3 = (command.value(registers[name]) for name in ("r1", "r2", "r3"))
        postcondition = Postcondition(
            program=state.program if spec["program"] == "UNCHANGED" else spec["program"],
            verb=spec["verb"],
            noun=state.noun if spec["noun"] == "UNCHANGED" else spec["noun"],
            r1=r1,
            r2=r2,
            r3=r3,
        )
        reasons = self.critical_reasons(command, state, postcondition)
        key_tuple = tuple(keys)
        return Plan(
            frame_seq=command.seq,
            catalog_version=self.catalog_version,
            command_id=entry["id"],
            keys=key_tuple,
            postcondition=postcondition,
            critical_reasons=reasons,
            plan_digest=compute_plan_digest(self.catalog_version, command.seq, key_tuple),
        )

    def critical_reasons(
        self, command: Command, state: AgcState, postcondition: Postcondition
    ) -> tuple[CriticalReason, ...]:
        """Union of independently computed reasons; the frame flag can only add."""

        p40_active = state.program == 40
        reasons: list[CriticalReason] = []
        if command.verb == 37 and p40_active:
            reasons.append(CriticalReason.V37_WHILE_P40)
        if command.verb == 34 and p40_active:
            reasons.append(CriticalReason.V34_WHILE_P40)
        if (
            postcondition.program == 40
            and not p40_active
            and abs(command.delta_v_tenths_fps) > self.delta_v_threshold
        ):
            reasons.append(CriticalReason.NONZERO_P40_ACTIVATION)
        if command.critical:
            reasons.append(CriticalReason.FRAME_CRITICAL_FLAG)
        return tuple(reasons)
