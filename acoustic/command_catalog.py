"""Daemon-side interpreter of ``contracts/dsky-command-catalog-v1.json``.

The daemon uses it as an independent execution guard: ``dsky.execute`` is
refused unless the requested keys equal the canonical plan recomputed here
from the daemon's own accepted frame and AGC state, and unless critical
commands carry a matching, fresh, unused AUTH.  The normative authorization
logic lives in ``mcp_server/safety_gate.py``; this is defense in depth so a
local client cannot bypass the gate.  ``tests/test_catalog_equivalence.py``
proves this interpreter and ``mcp_server.planner`` agree.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final

_SIGN_KEYS: Final = ("PLUS", "MINUS")
PAYLOAD_FIELDS: Final = ("program", "r1_centidegrees", "r2_centidegrees", "delta_v_tenths_fps")
IMPLEMENTED_RULES: Final = frozenset(
    {"V37_WHILE_P40", "V34_WHILE_P40", "NONZERO_P40_ACTIVATION", "FRAME_CRITICAL_FLAG"}
)


class CriticalReason(StrEnum):
    V37_WHILE_P40 = "V37_WHILE_P40"
    V34_WHILE_P40 = "V34_WHILE_P40"
    NONZERO_P40_ACTIVATION = "NONZERO_P40_ACTIVATION"
    FRAME_CRITICAL_FLAG = "FRAME_CRITICAL_FLAG"


class PlanErrorCode(StrEnum):
    UNSUPPORTED_COMMAND = "UNSUPPORTED_COMMAND"
    KEY_REL_ACTIVE = "KEY_REL_ACTIVE"
    OPR_ERR_ACTIVE = "OPR_ERR_ACTIVE"
    AGC_UNAVAILABLE = "AGC_UNAVAILABLE"


class PlanError(ValueError):
    def __init__(self, code: PlanErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class CommandFields:
    seq: int
    critical: bool
    verb: int
    noun: int
    program: int
    r1_centidegrees: int
    r2_centidegrees: int
    delta_v_tenths_fps: int

    def field(self, name: str) -> int:
        if name not in PAYLOAD_FIELDS:
            raise KeyError(name)
        value: int = getattr(self, name)
        return value


@dataclass(frozen=True, slots=True)
class AgcView:
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


@dataclass(frozen=True, slots=True)
class Postcondition:
    program: int
    verb: int
    noun: int
    r1: int
    r2: int
    r3: int


@dataclass(frozen=True, slots=True)
class CanonicalPlan:
    command_id: str
    frame_seq: int
    catalog_version: str
    keys: tuple[str, ...]
    postcondition: Postcondition
    critical_reasons: frozenset[CriticalReason]
    plan_digest: str

    @property
    def critical(self) -> bool:
        return bool(self.critical_reasons)


def plan_digest(catalog_version: str, frame_seq: int, keys: tuple[str, ...] | list[str]) -> str:
    payload = json.dumps(
        {"catalog_version": catalog_version, "frame_seq": frame_seq, "keys": list(keys)},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class CommandCatalog:
    def __init__(self, document: dict[str, Any]) -> None:
        rule_ids = {rule["id"] for rule in document["criticality"]["rules"]}
        if rule_ids != IMPLEMENTED_RULES:
            raise ValueError(f"catalog criticality rules {sorted(rule_ids)} are not implemented")
        if document["criticality"]["frame_critical_flag"] != "ADD_ONLY":
            raise ValueError("catalog frame flag policy must be ADD_ONLY")
        self._doc = document
        self.version: str = document["catalog_version"]
        self.threshold: int = document["criticality"]["p40_critical_delta_v_threshold_tenths_fps"]
        self.hold_expiry_ms: int = document["authorization"]["hold_expiry_ms"]
        self.min_cadence_ms: int = document["execution"]["min_key_cadence_ms"]
        self.keys: frozenset[str] = frozenset(document["keys"])
        self._encodings: dict[str, dict[str, Any]] = document["field_encodings"]
        self._segments: dict[str, list[Any]] = document["segments"]
        self._commands: list[dict[str, Any]] = document["commands"]
        for command in self._commands:
            for segment in command["segments"]:
                if segment not in self._segments:
                    raise ValueError(f"command {command['id']} uses unknown segment {segment}")

    def _select(self, command: CommandFields) -> dict[str, Any]:
        matches = [
            entry
            for entry in self._commands
            if entry["match"]
            == {"verb": command.verb, "noun": command.noun, "program": command.program}
        ]
        if len(matches) != 1:
            raise PlanError(
                PlanErrorCode.UNSUPPORTED_COMMAND,
                f"no catalog entry for V{command.verb:02d} N{command.noun:02d} P{command.program:02d}",
            )
        entry = matches[0]
        for name in entry["require_zero"]:
            if command.field(name) != 0:
                raise PlanError(
                    PlanErrorCode.UNSUPPORTED_COMMAND, f"{entry['id']} requires {name} = 0"
                )
        return entry

    def _encode(self, value: int, encoding: str) -> list[str]:
        spec = self._encodings[encoding]
        if not spec["min"] <= value <= spec["max"]:
            raise PlanError(
                PlanErrorCode.UNSUPPORTED_COMMAND,
                f"value {value} is not representable as {encoding} ({spec['min']}..{spec['max']})",
            )
        if encoding == "SIGNED_5":
            sign = _SIGN_KEYS[1] if value < 0 else _SIGN_KEYS[0]
            return [sign, *(f"DIGIT_{digit}" for digit in f"{abs(value):05d}")]
        if encoding == "DIGITS_2":
            return [f"DIGIT_{digit}" for digit in f"{value:02d}"]
        raise ValueError(f"unknown encoding {encoding}")

    @staticmethod
    def check_preconditions(view: AgcView) -> None:
        if view.key_rel:
            raise PlanError(PlanErrorCode.KEY_REL_ACTIVE, "KEY REL is active")
        if view.opr_err:
            raise PlanError(PlanErrorCode.OPR_ERR_ACTIVE, "OPR ERR is active")
        if view.input_state != "IDLE" or view.pending_entry is not None:
            raise PlanError(PlanErrorCode.AGC_UNAVAILABLE, "DSKY input is not idle")

    def plan(self, command: CommandFields, view: AgcView) -> CanonicalPlan:
        entry = self._select(command)
        keys: list[str] = []
        for segment in entry["segments"]:
            for token in self._segments[segment]:
                if isinstance(token, str):
                    keys.append(token)
                else:
                    keys.extend(self._encode(command.field(token["field"]), token["encoding"]))
        post = entry["postcondition"]
        program = view.program if post["program"] == "UNCHANGED" else post["program"]
        noun = view.noun if post["noun"] == "UNCHANGED" else post["noun"]
        if post["registers"] == "UNCHANGED":
            registers = (view.r1, view.r2, view.r3)
        else:
            mapping = post["registers"]
            registers = (
                command.field(mapping["r1"]),
                command.field(mapping["r2"]),
                command.field(mapping["r3"]),
            )
        postcondition = Postcondition(program, post["verb"], noun, *registers)
        reasons: set[CriticalReason] = set()
        if command.verb == 37 and view.program == 40:
            reasons.add(CriticalReason.V37_WHILE_P40)
        if command.verb == 34 and view.program == 40:
            reasons.add(CriticalReason.V34_WHILE_P40)
        if (
            postcondition.program == 40
            and view.program != 40
            and abs(command.delta_v_tenths_fps) > self.threshold
        ):
            reasons.add(CriticalReason.NONZERO_P40_ACTIVATION)
        if command.critical:
            reasons.add(CriticalReason.FRAME_CRITICAL_FLAG)
        key_tuple = tuple(keys)
        return CanonicalPlan(
            command_id=entry["id"],
            frame_seq=command.seq,
            catalog_version=self.version,
            keys=key_tuple,
            postcondition=postcondition,
            critical_reasons=frozenset(reasons),
            plan_digest=plan_digest(self.version, command.seq, key_tuple),
        )
