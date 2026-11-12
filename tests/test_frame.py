from __future__ import annotations

import json
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from acoustic.frame import (
    FRAME_SIZE,
    AuthFrame,
    CommandFrame,
    Frame,
    FrameDecodeError,
    KeyMaterial,
    RejectReason,
    Verdict,
    crc16_ccitt_false,
    decode_frame,
    encode_frame,
    validate_frame,
)

VECTOR_PATH = Path(__file__).parents[1] / "contracts" / "vectors" / "frames.json"
VECTORS = json.loads(VECTOR_PATH.read_text(encoding="utf-8"))
KEYS = KeyMaterial(
    link_key=VECTORS["demo_keys"]["link"].encode(),
    operator_key=VECTORS["demo_keys"]["operator"].encode(),
)


def _typed_frame(vector: dict[str, object]) -> Frame:
    fields = vector["frame"]
    assert isinstance(fields, dict)
    if fields["frame_type"] == "COMMAND":
        return CommandFrame(
            seq=fields["seq"],
            critical=fields["critical"],
            verb=fields["verb"],
            noun=fields["noun"],
            program=fields["program"],
            r1_centidegrees=fields["r1_centidegrees"],
            r2_centidegrees=fields["r2_centidegrees"],
            delta_v_tenths_fps=fields["delta_v_tenths_fps"],
        )
    return AuthFrame(seq=fields["seq"], ref_seq=fields["ref_seq"])


def _accepted_vectors() -> list[dict[str, object]]:
    return [vector for vector in VECTORS["vectors"] if "expected_hex" in vector]


@pytest.mark.parametrize("vector", _accepted_vectors(), ids=lambda item: str(item["id"]))
def test_golden_vectors_match_independent_bytes(vector: dict[str, object]) -> None:
    frame = _typed_frame(vector)
    raw = encode_frame(frame, KEYS)

    assert len(raw) == FRAME_SIZE
    assert raw.hex() == vector["expected_hex"]
    assert decode_frame(raw, KEYS) == frame
    result = validate_frame(raw, KEYS, replay_state=0)
    assert result.verdict is Verdict.ACCEPTED
    assert result.reason is None
    assert result.frame == frame


def test_golden_derived_crc_and_replay_verdicts() -> None:
    source = bytes.fromhex(_accepted_vectors()[0]["expected_hex"])
    mutated = bytearray(source)
    mutated[20] ^= 1

    crc_result = validate_frame(bytes(mutated), KEYS, replay_state=0)
    replay_result = validate_frame(source, KEYS, replay_state=42)

    assert crc_result.reason is RejectReason.CRC
    assert crc_result.checks.hmac is None
    assert replay_result.reason is RejectReason.REPLAY
    assert replay_result.checks.hmac is True


def test_validation_order_and_skipped_checks_are_stable() -> None:
    raw = bytearray(bytes.fromhex(_accepted_vectors()[0]["expected_hex"]))
    raw[0] ^= 1
    raw[2] = 99
    raw[32:34] = b"\0\0"

    result = validate_frame(bytes(raw), KEYS, replay_state=0)

    assert result.reason is RejectReason.SYNC
    assert result.checks.sync is False
    assert result.checks.version is None
    assert result.checks.crc is None


def test_version_precedes_type_and_crc() -> None:
    raw = bytearray(bytes.fromhex(_accepted_vectors()[0]["expected_hex"]))
    raw[2] = 99
    raw[3] = 99

    result = validate_frame(bytes(raw), KEYS, replay_state=0)

    assert result.reason is RejectReason.VERSION
    assert result.checks.frame_type is None
    assert result.checks.crc is None


def test_length_rejection_does_not_index_short_input() -> None:
    result = validate_frame(b"\xA5", KEYS, replay_state=0)

    assert result.reason is RejectReason.LENGTH
    assert result.frame is None
    assert result.checks.sync is None


def test_auth_payload_semantics_precede_hmac() -> None:
    raw = bytearray(bytes.fromhex(_accepted_vectors()[1]["expected_hex"]))
    raw[13] = 1
    raw[24] ^= 1
    raw[32:34] = crc16_ccitt_false(bytes(raw[2:32])).to_bytes(2, "big")

    result = validate_frame(bytes(raw), KEYS, replay_state=0)

    assert result.reason is RejectReason.FLAGS
    assert result.checks.hmac is None


def test_p6_wrong_hmac_with_recomputed_crc_reaches_hmac_gate() -> None:
    raw = bytearray(bytes.fromhex(_accepted_vectors()[0]["expected_hex"]))
    raw[24] ^= 0x80
    raw[32:34] = crc16_ccitt_false(bytes(raw[2:32])).to_bytes(2, "big")

    result = validate_frame(bytes(raw), KEYS, replay_state=0)

    assert result.reason is RejectReason.HMAC
    assert result.checks.crc is True
    assert result.checks.hmac is False
    assert result.checks.sequence is None


sequence = st.integers(min_value=1, max_value=0xFFFFFFFF)
small_field = st.integers(min_value=0, max_value=99)
int16 = st.integers(min_value=-0x8000, max_value=0x7FFF)
int32 = st.integers(min_value=-0x80000000, max_value=0x7FFFFFFF)

command_frames = st.builds(
    CommandFrame,
    seq=sequence,
    critical=st.booleans(),
    verb=small_field,
    noun=small_field,
    program=small_field,
    r1_centidegrees=int16,
    r2_centidegrees=int16,
    delta_v_tenths_fps=int32,
)
auth_frames = st.builds(AuthFrame, seq=sequence, ref_seq=sequence)
frames = st.one_of(command_frames, auth_frames)


@given(frame=frames, hmac_bit=st.integers(min_value=0, max_value=63))
def test_p6_wrong_hmac_with_valid_recomputed_crc_is_rejected(
    frame: Frame, hmac_bit: int
) -> None:
    raw = bytearray(encode_frame(frame, KEYS))
    raw[24 + hmac_bit // 8] ^= 1 << (hmac_bit % 8)
    raw[32:34] = crc16_ccitt_false(bytes(raw[2:32])).to_bytes(2, "big")

    result = validate_frame(bytes(raw), KEYS, replay_state=0)

    assert result.reason is RejectReason.HMAC
    assert result.checks.crc is True
    assert result.checks.hmac is False
    assert result.checks.sequence is None


@given(frame=frames)
def test_p1_frame_byte_round_trip(frame: Frame) -> None:
    encoded = encode_frame(frame, KEYS)

    assert len(encoded) == FRAME_SIZE
    assert decode_frame(encoded, KEYS) == frame
    result = validate_frame(encoded, KEYS, replay_state=0)
    assert result.frame == frame
    assert result.verdict is Verdict.ACCEPTED


@given(
    frame=frames,
    first_bit=st.integers(min_value=0, max_value=FRAME_SIZE * 8 - 1),
    data=st.data(),
)
def test_p4_single_or_double_bit_corruption_rejected(
    frame: Frame, first_bit: int, data: st.DataObject
) -> None:
    raw = bytearray(encode_frame(frame, KEYS))
    raw[first_bit // 8] ^= 1 << (first_bit % 8)
    if data.draw(st.booleans()):
        second_bit = data.draw(
            st.integers(min_value=0, max_value=FRAME_SIZE * 8 - 2).map(
                lambda bit: bit + (bit >= first_bit)
            )
        )
        raw[second_bit // 8] ^= 1 << (second_bit % 8)

    result = validate_frame(bytes(raw), KEYS, replay_state=0)

    assert result.verdict is Verdict.REJECTED
    assert result.frame is None


@given(frame=frames, stale_by=st.integers(min_value=0, max_value=1000))
def test_p6_stale_or_equal_sequence_is_rejected(frame: Frame, stale_by: int) -> None:
    last_accepted = min(0xFFFFFFFF, frame.seq + stale_by)

    result = validate_frame(encode_frame(frame, KEYS), KEYS, replay_state=last_accepted)

    assert result.reason is RejectReason.REPLAY
    assert result.checks.sequence is False
    assert result.checks.range is None


def test_decode_reports_stable_reason() -> None:
    with pytest.raises(FrameDecodeError) as error:
        decode_frame(b"")
    assert error.value.reason is RejectReason.LENGTH
