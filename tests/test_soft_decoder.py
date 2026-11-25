"""Over-the-air fallback: soft decoder, CRC-guided recovery, repeat handling.

Impaired audio comes from ``tests/channel_sim.py`` (a model of the 12-13 Nov
trials, not a measurement).  Every candidate the fallback produces still goes
through ``validate_frame``; these tests check that the fallback recovers more
frames than the strict decoder and never produces an accepted forgery.
"""

from __future__ import annotations

import numpy as np
import pytest

from acoustic.frame import (
    CommandFrame,
    KeyMaterial,
    RejectReason,
    encode_frame,
    validate_frame,
)
from acoustic.modem import DemodulatorConfig, SourceKind, demodulate, modulate
from acoustic.receiver import CandidateEvent, DuplicateEvent, StreamingReceiver
from acoustic.recovery import RecoveryMethod, bits_to_bytes, crc_consistent, recover
from acoustic.soft_decoder import soft_decode
from tests.channel_sim import LAPTOP_SELF_TEST, Channel, impair

RATE = 48_000
KEYS = KeyMaterial(b"apollo26-link-demo-key-v1", b"apollo26-operator-demo-key-v1")
CONFIG = DemodulatorConfig(sample_rate=RATE)
CONFIG_SOURCE = SourceKind.MICROPHONE


def _frame(seq: int) -> bytes:
    return encode_frame(
        CommandFrame(
            seq=seq,
            critical=False,
            verb=25,
            noun=81,
            program=0,
            r1_centidegrees=1250 + seq,
            r2_centidegrees=420,
            delta_v_tenths_fps=3120,
        ),
        KEYS,
    )


def _burst(raw: bytes, repeat: int = 1, gap_s: float = 0.3) -> np.ndarray:
    tone = modulate(raw, RATE, amplitude=0.6)
    gap = np.zeros(int(RATE * gap_s))
    parts = [np.zeros(int(RATE * 0.4))]
    for _ in range(repeat):
        parts.extend((tone, gap))
    parts.append(np.zeros(int(RATE * 0.4)))
    return np.concatenate(parts)


def _receive(pcm: np.ndarray, *, soft_fallback: bool = True) -> list[object]:
    receiver = StreamingReceiver(CONFIG, CONFIG_SOURCE, soft_fallback=soft_fallback)
    events: list[object] = []
    block = RATE // 10
    for start in range(0, pcm.size, block):
        events.extend(receiver.feed(pcm[start : start + block]))
    events.extend(receiver.flush())
    return events


def _bits(raw: bytes) -> np.ndarray:
    return np.array([(byte >> bit) & 1 for byte in raw for bit in range(8)], dtype=bool)


def _accepted(events: list[object], last_seq: int = 0) -> list[bytes]:
    return [
        event.raw
        for event in events
        if isinstance(event, CandidateEvent) and validate_frame(event.raw, KEYS, last_seq).accepted
    ]


# ---------------------------------------------------------------- soft decoder


def test_soft_decoder_reproduces_clean_frame_bits() -> None:
    raw = _frame(1)
    pcm = _burst(raw)
    result = demodulate(pcm, CONFIG)
    assert result.candidates == (raw,)
    # Feed the transition the strict decoder would report for this burst.
    lead = int(RATE * 0.4)
    transition = lead + 75 * (RATE // 300)
    soft = soft_decode(pcm, CONFIG, transition)
    assert soft is not None
    assert bits_to_bytes(soft.soft_bits > 0) == raw
    assert soft.framing_errors == 0
    assert abs(soft.twist_db) < 1.0


def test_soft_decoder_measures_twist_on_the_sync_word() -> None:
    raw = _frame(2)
    pcm = impair(_burst(raw), RATE, Channel(twist_db=10.0), np.random.default_rng(1))
    lead = int(RATE * 0.4)
    soft = soft_decode(pcm, CONFIG, lead + 75 * (RATE // 300))
    assert soft is not None
    assert 7.0 < soft.twist_db < 13.0
    assert bits_to_bytes(soft.soft_bits > 0) == raw


def test_soft_decoder_returns_none_without_sync() -> None:
    rng = np.random.default_rng(3)
    noise = rng.normal(0.0, 0.2, RATE * 2)
    assert soft_decode(noise, CONFIG, RATE // 2) is None


def test_vectorized_window_scan_matches_per_window_goertzel() -> None:
    from acoustic.modem import _window_tones, goertzel_tone

    rng = np.random.default_rng(7)
    width = RATE // 300
    signals = [
        _burst(_frame(9)),
        impair(_burst(_frame(10)), RATE, LAPTOP_SELF_TEST, rng),
        rng.normal(0.0, 0.1, RATE),
        np.zeros(RATE // 2),
    ]
    for pcm in signals:
        starts = np.arange(0, pcm.size - width + 1, width // 4, dtype=np.int64)
        expected = [goertzel_tone(pcm[s : s + width], CONFIG).tone for s in starts.tolist()]
        assert _window_tones(pcm, starts, width, CONFIG) == expected


# ---------------------------------------------------------------- recovery


def test_recover_returns_clean_frame_without_flips() -> None:
    raw = _frame(3)
    soft = np.where(_bits(raw), 1.0, -1.0)
    recovered = recover([soft])
    assert recovered is not None
    assert recovered.raw == raw
    assert recovered.method is RecoveryMethod.SOFT
    assert recovered.flipped_bits == 0


def test_chase_repairs_low_confidence_bit_errors() -> None:
    raw = _frame(4)
    soft = np.where(_bits(raw), 1.0, -1.0)
    for index in (40, 99, 201):  # CRC-covered bits, weak and wrong
        soft[index] = -0.1 * np.sign(soft[index])
    recovered = recover([soft])
    assert recovered is not None
    assert recovered.raw == raw
    assert recovered.method is RecoveryMethod.CHASE
    assert recovered.flipped_bits == 3


def test_combining_two_copies_repairs_errors_neither_copy_can() -> None:
    raw = _frame(5)
    truth = np.where(_bits(raw), 1.0, -1.0)
    first, second = truth.copy(), truth.copy()
    first_errors = np.arange(20, 260, 12)  # 20 confident errors: beyond Chase
    second_errors = first_errors + 5
    first[first_errors] *= -0.5
    second[second_errors] *= -0.5
    assert recover([first]) is None
    assert recover([second]) is None
    recovered = recover([first, second])
    assert recovered is not None
    assert recovered.raw == raw
    assert recovered.method is RecoveryMethod.COMBINED
    assert recovered.copies == 2


def test_recovered_candidates_from_garbage_are_never_accepted() -> None:
    rng = np.random.default_rng(2026)
    produced = 0
    for _ in range(400):
        soft = rng.normal(0.0, 1.0, 34 * 8)
        recovered = recover([soft])
        if recovered is None:
            continue
        produced += 1
        assert crc_consistent(recovered.raw)
        result = validate_frame(recovered.raw, KEYS, 0)
        assert not result.accepted
        assert result.reason in {
            RejectReason.SYNC,
            RejectReason.VERSION,
            RejectReason.TYPE,
            RejectReason.FLAGS,
            RejectReason.HMAC,
        }
    # 400 trials x 255 flips / 65536 predicts about 1.6 CRC-consistent garbage candidates.
    assert produced <= 8


# ---------------------------------------------------------------- receiver


def test_repeated_burst_yields_one_candidate_and_duplicates() -> None:
    raw = _frame(6)
    events = _receive(_burst(raw, repeat=3))
    candidates = [event for event in events if isinstance(event, CandidateEvent)]
    duplicates = [event for event in events if isinstance(event, DuplicateEvent)]
    assert [event.raw for event in candidates] == [raw]
    assert len(duplicates) == 2


def _trial(channel: Channel, frames: int, *, soft_fallback: bool, repeat: int = 1) -> int:
    accepted = 0
    for index in range(frames):
        raw = _frame(100 + index)
        rng = np.random.default_rng(10_000 + index)
        pcm = impair(_burst(raw, repeat=repeat), RATE, channel, rng)
        if raw in _accepted(_receive(pcm, soft_fallback=soft_fallback)):
            accepted += 1
    return accepted


@pytest.mark.slow
def test_fallback_beats_strict_decoder_on_modelled_laptop_channel() -> None:
    strict = _trial(LAPTOP_SELF_TEST, 20, soft_fallback=False)
    robust = _trial(LAPTOP_SELF_TEST, 20, soft_fallback=True)
    assert robust >= 18, (strict, robust)
    assert robust > strict, (strict, robust)


@pytest.mark.slow
def test_three_repeats_reach_target_on_modelled_laptop_channel() -> None:
    assert _trial(LAPTOP_SELF_TEST, 20, soft_fallback=True, repeat=3) >= 19
