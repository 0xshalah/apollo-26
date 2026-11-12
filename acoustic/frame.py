"""Pure codec and ordered validation for Apollo-26 acoustic frames."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, replace
from enum import IntEnum, StrEnum
from typing import Protocol

FRAME_SIZE = 34
SYNC = b"\xA5\x26"
VERSION = 1
HMAC_SIZE = 8
MAX_SEQUENCE = 0xFFFFFFFF


class FrameType(IntEnum):
    """Wire-level frame discriminator."""

    COMMAND = 0x01
    AUTH = 0x02


class RejectReason(StrEnum):
    """Stable validation reason codes from the wire contract."""

    LENGTH = "LENGTH"
    SYNC = "SYNC"
    VERSION = "VERSION"
    TYPE = "TYPE"
    CRC = "CRC"
    FLAGS = "FLAGS"
    HMAC = "HMAC"
    REPLAY = "REPLAY"
    RANGE = "RANGE"
    STATE = "STATE"
    INTERNAL = "INTERNAL"


class Verdict(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class FrameValueError(ValueError):
    """A typed frame contains a value outside the v1 domain."""


class FrameDecodeError(ValueError):
    """A byte string cannot be decoded as a structurally valid v1 frame."""

    def __init__(self, reason: RejectReason) -> None:
        super().__init__(reason.value)
        self.reason = reason


class SequenceAccessError(RuntimeError):
    """A sequence adapter cannot safely load or commit state."""


@dataclass(frozen=True, slots=True)
class KeyMaterial:
    """Already-validated frame keys injected by the composition boundary."""

    link_key: bytes
    operator_key: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.link_key, bytes) or not self.link_key:
            raise FrameValueError("link_key must be non-empty bytes")
        if not isinstance(self.operator_key, bytes) or not self.operator_key:
            raise FrameValueError("operator_key must be non-empty bytes")


@dataclass(frozen=True, slots=True)
class CommandFrame:
    seq: int
    critical: bool
    verb: int
    noun: int
    program: int
    r1_centidegrees: int
    r2_centidegrees: int
    delta_v_tenths_fps: int

    @property
    def frame_type(self) -> FrameType:
        return FrameType.COMMAND

    @property
    def ref_seq(self) -> int:
        return 0

    def __post_init__(self) -> None:
        _require_uint("seq", self.seq, 32, minimum=1)
        if type(self.critical) is not bool:
            raise FrameValueError("critical must be bool")
        _validate_payload_ranges(
            self.verb,
            self.noun,
            self.program,
            self.r1_centidegrees,
            self.r2_centidegrees,
            self.delta_v_tenths_fps,
        )


@dataclass(frozen=True, slots=True)
class AuthFrame:
    seq: int
    ref_seq: int

    @property
    def frame_type(self) -> FrameType:
        return FrameType.AUTH

    @property
    def critical(self) -> bool:
        return False

    @property
    def verb(self) -> int:
        return 0

    @property
    def noun(self) -> int:
        return 0

    @property
    def program(self) -> int:
        return 0

    @property
    def r1_centidegrees(self) -> int:
        return 0

    @property
    def r2_centidegrees(self) -> int:
        return 0

    @property
    def delta_v_tenths_fps(self) -> int:
        return 0

    def __post_init__(self) -> None:
        _require_uint("seq", self.seq, 32, minimum=1)
        _require_uint("ref_seq", self.ref_seq, 32, minimum=1)


type Frame = CommandFrame | AuthFrame


@dataclass(frozen=True, slots=True)
class ValidationChecks:
    """Results of gates; ``None`` means that a later gate was not run."""

    length: bool
    sync: bool | None = None
    version: bool | None = None
    frame_type: bool | None = None
    crc: bool | None = None
    semantics: bool | None = None
    hmac: bool | None = None
    sequence: bool | None = None
    range: bool | None = None


@dataclass(frozen=True, slots=True)
class ValidationResult:
    verdict: Verdict
    reason: RejectReason | None
    frame: Frame | None
    checks: ValidationChecks

    @property
    def accepted(self) -> bool:
        return self.verdict is Verdict.ACCEPTED


class ReplayState(Protocol):
    """Minimal immutable view required by the pure replay gate."""

    @property
    def last_accepted_seq(self) -> int: ...


class SequenceStore(ReplayState, Protocol):
    """Loaded persistence handoff used only after all pure gates pass."""

    def load(self) -> ReplayState: ...

    def commit(self, next_seq: int) -> None: ...


@dataclass(frozen=True, slots=True)
class _WireFields:
    frame_type: FrameType
    seq: int
    ref_seq: int
    flags: int
    verb: int
    noun: int
    program: int
    r1: int
    r2: int
    delta_v: int


def _require_int(name: str, value: object) -> int:
    if type(value) is not int:
        raise FrameValueError(f"{name} must be int")
    return value


def _require_uint(name: str, value: object, bits: int, *, minimum: int = 0) -> None:
    integer = _require_int(name, value)
    if not minimum <= integer <= (1 << bits) - 1:
        raise FrameValueError(f"{name} is outside uint{bits} domain")


def _require_sint(name: str, value: object, bits: int) -> None:
    integer = _require_int(name, value)
    minimum = -(1 << (bits - 1))
    maximum = (1 << (bits - 1)) - 1
    if not minimum <= integer <= maximum:
        raise FrameValueError(f"{name} is outside int{bits} domain")


def _validate_payload_ranges(
    verb: object,
    noun: object,
    program: object,
    r1: object,
    r2: object,
    delta_v: object,
) -> None:
    for name, value in (("verb", verb), ("noun", noun), ("program", program)):
        integer = _require_int(name, value)
        if not 0 <= integer <= 99:
            raise FrameValueError(f"{name} must be in 0..99")
    _require_sint("r1_centidegrees", r1, 16)
    _require_sint("r2_centidegrees", r2, 16)
    _require_sint("delta_v_tenths_fps", delta_v, 32)


def crc16_ccitt_false(data: bytes) -> int:
    """Return CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF)."""

    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def _authenticator(body_without_auth: bytes, key: bytes) -> bytes:
    return hmac.new(key, body_without_auth, hashlib.sha256).digest()[:HMAC_SIZE]


def _select_key(frame_type: FrameType, keys: KeyMaterial) -> bytes:
    return keys.link_key if frame_type is FrameType.COMMAND else keys.operator_key


def encode_frame(frame: Frame, key: bytes | KeyMaterial) -> bytes:
    """Encode a validated typed frame into the canonical 34-byte representation."""

    if not isinstance(frame, (CommandFrame, AuthFrame)):
        raise TypeError("frame must be CommandFrame or AuthFrame")
    selected_key = _select_key(frame.frame_type, key) if isinstance(key, KeyMaterial) else key
    if not isinstance(selected_key, bytes) or not selected_key:
        raise FrameValueError("key must be non-empty bytes")

    output = bytearray(FRAME_SIZE)
    output[0:2] = SYNC
    output[2] = VERSION
    output[3] = frame.frame_type
    output[4:8] = frame.seq.to_bytes(4, "big")
    output[8:12] = frame.ref_seq.to_bytes(4, "big")
    output[12] = 1 if frame.critical else 0
    output[13] = frame.verb
    output[14] = frame.noun
    output[15] = frame.program
    output[16:18] = frame.r1_centidegrees.to_bytes(2, "big", signed=True)
    output[18:20] = frame.r2_centidegrees.to_bytes(2, "big", signed=True)
    output[20:24] = frame.delta_v_tenths_fps.to_bytes(4, "big", signed=True)
    output[24:32] = _authenticator(bytes(output[2:24]), selected_key)
    output[32:34] = crc16_ccitt_false(bytes(output[2:32])).to_bytes(2, "big")
    return bytes(output)


def _parse_fields(data: bytes) -> _WireFields:
    return _WireFields(
        frame_type=FrameType(data[3]),
        seq=int.from_bytes(data[4:8], "big"),
        ref_seq=int.from_bytes(data[8:12], "big"),
        flags=data[12],
        verb=data[13],
        noun=data[14],
        program=data[15],
        r1=int.from_bytes(data[16:18], "big", signed=True),
        r2=int.from_bytes(data[18:20], "big", signed=True),
        delta_v=int.from_bytes(data[20:24], "big", signed=True),
    )


def _semantics_valid(fields: _WireFields) -> bool:
    if fields.flags & 0xFE:
        return False
    if fields.frame_type is FrameType.COMMAND:
        return fields.ref_seq == 0
    return (
        fields.ref_seq != 0
        and fields.flags == 0
        and fields.verb == 0
        and fields.noun == 0
        and fields.program == 0
        and fields.r1 == 0
        and fields.r2 == 0
        and fields.delta_v == 0
    )


def _ranges_valid(fields: _WireFields) -> bool:
    return fields.seq != 0 and all(
        0 <= value <= 99 for value in (fields.verb, fields.noun, fields.program)
    )


def _to_frame(fields: _WireFields) -> Frame:
    if fields.frame_type is FrameType.COMMAND:
        return CommandFrame(
            seq=fields.seq,
            critical=bool(fields.flags & 1),
            verb=fields.verb,
            noun=fields.noun,
            program=fields.program,
            r1_centidegrees=fields.r1,
            r2_centidegrees=fields.r2,
            delta_v_tenths_fps=fields.delta_v,
        )
    return AuthFrame(seq=fields.seq, ref_seq=fields.ref_seq)


def decode_frame(data: bytes, key: bytes | KeyMaterial | None = None) -> Frame:
    """Decode a structurally valid frame; optionally verify its HMAC."""

    if len(data) != FRAME_SIZE:
        raise FrameDecodeError(RejectReason.LENGTH)
    if data[0:2] != SYNC:
        raise FrameDecodeError(RejectReason.SYNC)
    if data[2] != VERSION:
        raise FrameDecodeError(RejectReason.VERSION)
    try:
        frame_type = FrameType(data[3])
    except ValueError as error:
        raise FrameDecodeError(RejectReason.TYPE) from error
    expected_crc = int.from_bytes(data[32:34], "big")
    if crc16_ccitt_false(data[2:32]) != expected_crc:
        raise FrameDecodeError(RejectReason.CRC)
    fields = _parse_fields(data)
    if not _semantics_valid(fields):
        raise FrameDecodeError(RejectReason.FLAGS)
    if key is not None:
        selected_key = _select_key(frame_type, key) if isinstance(key, KeyMaterial) else key
        if not hmac.compare_digest(data[24:32], _authenticator(data[2:24], selected_key)):
            raise FrameDecodeError(RejectReason.HMAC)
    if not _ranges_valid(fields):
        raise FrameDecodeError(RejectReason.RANGE)
    return _to_frame(fields)


def _last_sequence(replay_state: int | ReplayState) -> int | None:
    try:
        value = replay_state if type(replay_state) is int else replay_state.last_accepted_seq
    except SequenceAccessError:
        return None
    if type(value) is not int or not 0 <= value <= MAX_SEQUENCE:
        return None
    return value


def _rejected(reason: RejectReason, checks: ValidationChecks) -> ValidationResult:
    return ValidationResult(Verdict.REJECTED, reason, None, checks)


def validate_frame(
    data: bytes,
    keys: KeyMaterial,
    replay_state: int | ReplayState,
) -> ValidationResult:
    """Validate a candidate in the contract's exact first-failure order."""

    checks = ValidationChecks(length=len(data) == FRAME_SIZE)
    if not checks.length:
        return _rejected(RejectReason.LENGTH, checks)

    checks = replace(checks, sync=data[0:2] == SYNC)
    if not checks.sync:
        return _rejected(RejectReason.SYNC, checks)

    checks = replace(checks, version=data[2] == VERSION)
    if not checks.version:
        return _rejected(RejectReason.VERSION, checks)

    type_valid = data[3] in (FrameType.COMMAND, FrameType.AUTH)
    checks = replace(checks, frame_type=type_valid)
    if not type_valid:
        return _rejected(RejectReason.TYPE, checks)

    expected_crc = int.from_bytes(data[32:34], "big")
    checks = replace(checks, crc=crc16_ccitt_false(data[2:32]) == expected_crc)
    if not checks.crc:
        return _rejected(RejectReason.CRC, checks)

    fields = _parse_fields(data)
    checks = replace(checks, semantics=_semantics_valid(fields))
    if not checks.semantics:
        return _rejected(RejectReason.FLAGS, checks)

    selected_key = _select_key(fields.frame_type, keys)
    expected_hmac = _authenticator(data[2:24], selected_key)
    checks = replace(checks, hmac=hmac.compare_digest(data[24:32], expected_hmac))
    if not checks.hmac:
        return _rejected(RejectReason.HMAC, checks)

    last_accepted_seq = _last_sequence(replay_state)
    if last_accepted_seq is None:
        return _rejected(RejectReason.STATE, checks)
    checks = replace(checks, sequence=fields.seq != 0 and fields.seq > last_accepted_seq)
    if not checks.sequence:
        return _rejected(RejectReason.REPLAY, checks)

    checks = replace(checks, range=_ranges_valid(fields))
    if not checks.range:
        return _rejected(RejectReason.RANGE, checks)

    return ValidationResult(Verdict.ACCEPTED, None, _to_frame(fields), checks)


def validate_and_commit_frame(
    data: bytes,
    keys: KeyMaterial,
    sequence_store: SequenceStore,
) -> ValidationResult:
    """Validate against loaded state and atomically commit an accepted sequence."""

    result = validate_frame(data, keys, sequence_store)
    if not result.accepted:
        return result
    assert result.frame is not None
    try:
        sequence_store.commit(result.frame.seq)
    except SequenceAccessError:
        return ValidationResult(Verdict.REJECTED, RejectReason.INTERNAL, None, result.checks)
    return result
