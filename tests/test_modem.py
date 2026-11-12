from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest
from hypothesis import given, settings, strategies as st

from acoustic.modem import (
    BAUD,
    FRAME_BYTES,
    MARK_FREQUENCY_HZ,
    MIN_PREAMBLE_SYMBOLS,
    SPACE_FREQUENCY_HZ,
    DemodulatorConfig,
    ModemConfigurationError,
    ModemErrorCode,
    ReceiverState,
    SourceKind,
    Tone,
    demodulate,
    demodulate_chunks,
    estimate_frequency,
    frequency_anomaly,
    goertzel_tone,
    modulate,
    samples_per_symbol,
    serialize_8n1,
)

_FULL_PROFILE = os.getenv("HYPOTHESIS_PROFILE") == "full"
_P2_EXAMPLES = 500 if _FULL_PROFILE else 12
_P3_EXAMPLES = 300 if _FULL_PROFILE else 8
_P5_EXAMPLES = 1_000 if _FULL_PROFILE else 24
_SAMPLE_RATES = (44_100, 48_000)
_GOLDEN_FRAME = bytes.fromhex(
    "a52601010000002a000000000125002804e201a4000079e003"
    "ef57ace1ee8c8d7be6"
)


def _tone(frequency_hz: float, sample_rate: int, duration_seconds: float) -> np.ndarray:
    count = int(round(sample_rate * duration_seconds))
    index = np.arange(count, dtype=np.float64)
    return 0.8 * np.sin(2.0 * np.pi * frequency_hz * index / sample_rate)


def _awgn(waveform: np.ndarray, snr_db: float, seed: int) -> np.ndarray:
    """Add white Gaussian noise using mean-square signal/noise power.

    noise_power = signal_power / 10**(snr_db/10).  If a realization exceeds
    floating PCM bounds, the complete result is scaled; this preserves SNR and
    avoids clipping rather than clipping individual samples.
    """

    generator = np.random.default_rng(seed)
    signal_power = float(np.mean(np.square(waveform)))
    noise_power = signal_power / (10.0 ** (snr_db / 10.0))
    noise = generator.normal(0.0, np.sqrt(noise_power), waveform.size)
    noisy = waveform + noise
    peak = float(np.max(np.abs(noisy)))
    return noisy if peak <= 0.99 else noisy * (0.99 / peak)


def test_al_req_1_protocol_constants_match_normative_contract() -> None:
    contract = (Path(__file__).parents[1] / "contracts" / "acoustic-frame-v1.md").read_text(
        encoding="utf-8"
    )
    assert "Mark = 1200 Hz" in contract
    assert "space = 2200 Hz" in contract
    assert "300 symbols/s" in contract
    assert "Preamble = mark kontinu minimal 250 ms" in contract
    assert MARK_FREQUENCY_HZ == 1_200.0
    assert SPACE_FREQUENCY_HZ == 2_200.0
    assert BAUD == 300
    assert MIN_PREAMBLE_SYMBOLS == 75
    assert FRAME_BYTES == 34


@pytest.mark.parametrize(("sample_rate", "expected"), [(48_000, 160), (44_100, 147)])
def test_al_req_1_5_samples_per_symbol(sample_rate: int, expected: int) -> None:
    assert samples_per_symbol(sample_rate) == expected


@pytest.mark.parametrize("sample_rate", _SAMPLE_RATES)
def test_al_req_1_rejects_unsupported_configuration(sample_rate: int) -> None:
    with pytest.raises(ModemConfigurationError, match="unsupported baud"):
        DemodulatorConfig(sample_rate, baud=1_200)
    with pytest.raises(ModemConfigurationError, match="unsupported sample rate"):
        DemodulatorConfig(8_000)


def test_al_req_1_3_serializes_preamble_and_uart_lsb_first() -> None:
    frame = bytes((0xA5,)) + bytes(FRAME_BYTES - 1)
    symbols = serialize_8n1(frame)
    assert symbols.shape == (MIN_PREAMBLE_SYMBOLS + FRAME_BYTES * 10,)
    assert np.all(symbols[:MIN_PREAMBLE_SYMBOLS] == 1)
    # A5 data bits are 1,0,1,0,0,1,0,1 between start=0 and stop=1.
    assert symbols[MIN_PREAMBLE_SYMBOLS : MIN_PREAMBLE_SYMBOLS + 10].tolist() == [
        0,
        1,
        0,
        1,
        0,
        0,
        1,
        0,
        1,
        1,
    ]


@pytest.mark.parametrize("sample_rate", _SAMPLE_RATES)
def test_al_req_1_modulation_duration_bounds_and_continuous_phase(sample_rate: int) -> None:
    amplitude = 0.73
    initial_phase = 0.41
    symbols = serialize_8n1(_GOLDEN_FRAME)
    width = samples_per_symbol(sample_rate)
    waveform = modulate(
        _GOLDEN_FRAME,
        sample_rate,
        amplitude=amplitude,
        initial_phase_radians=initial_phase,
    )
    assert waveform.shape == (symbols.size * width,)
    assert float(np.max(np.abs(waveform))) <= amplitude + 1e-12

    frequencies = np.repeat(
        np.where(symbols == 1, MARK_FREQUENCY_HZ, SPACE_FREQUENCY_HZ), width
    )
    increments = 2.0 * np.pi * frequencies / sample_rate
    expected_phases = np.empty(waveform.size)
    expected_phases[0] = initial_phase
    expected_phases[1:] = initial_phase + np.cumsum(increments[:-1])
    np.testing.assert_allclose(waveform, amplitude * np.sin(expected_phases), atol=2e-11)


@pytest.mark.parametrize(("frequency", "expected_tone"), [(1_200.0, Tone.MARK), (2_200.0, Tone.SPACE)])
def test_al_req_1_goertzel_detects_bell_202_tones(
    frequency: float, expected_tone: Tone
) -> None:
    config = DemodulatorConfig(48_000)
    measurement = goertzel_tone(_tone(frequency, 48_000, 1 / BAUD), config)
    assert measurement.tone is expected_tone
    assert measurement.confidence > config.confidence_ratio


def test_al_req_10_frequency_estimate_and_anomaly_boundary() -> None:
    sample_rate = 48_000
    measured = estimate_frequency(_tone(1_237.0, sample_rate, 0.25), sample_rate, 1_200.0)
    assert measured == pytest.approx(1_237.0, abs=0.5)

    exact_boundary = frequency_anomaly(
        1_250.0,
        1_200.0,
        source_kind=SourceKind.MEMORY,
        receiver_state=ReceiverState.PREAMBLE,
    )
    beyond_boundary = frequency_anomaly(
        1_250.01,
        1_200.0,
        source_kind=SourceKind.WAV,
        receiver_state=ReceiverState.PREAMBLE,
        candidate_correlation="a526",
    )
    assert exact_boundary is None
    assert beyond_boundary is not None
    assert beyond_boundary.absolute_deviation_hz == pytest.approx(50.01)
    assert beyond_boundary.candidate_correlation == "a526"


def test_al_req_10_insufficient_frequency_evidence_returns_none() -> None:
    assert estimate_frequency(np.zeros(10), 48_000, MARK_FREQUENCY_HZ) is None


@settings(max_examples=_P2_EXAMPLES, deadline=None)
@given(
    payload=st.binary(min_size=FRAME_BYTES - 2, max_size=FRAME_BYTES - 2),
    sample_rate=st.sampled_from(_SAMPLE_RATES),
    leading_silence_symbols=st.integers(min_value=0, max_value=3),
)
def test_p2_clean_audio_round_trip(
    payload: bytes, sample_rate: int, leading_silence_symbols: int
) -> None:
    frame = b"\xA5\x26" + payload
    waveform = modulate(frame, sample_rate, initial_phase_radians=0.37)
    leading = np.zeros(leading_silence_symbols * samples_per_symbol(sample_rate))
    result = demodulate(np.concatenate((leading, waveform)), DemodulatorConfig(sample_rate))
    # This is a byte candidate, not an accepted command. Frame acceptance is codec-owned.
    assert result.candidates == (frame,)
    assert result.diagnostics.failure is None


@pytest.mark.slow
@settings(max_examples=_P3_EXAMPLES, deadline=None)
@given(
    payload=st.binary(min_size=FRAME_BYTES - 2, max_size=FRAME_BYTES - 2),
    sample_rate=st.sampled_from(_SAMPLE_RATES),
    snr_db=st.floats(min_value=15.0, max_value=30.0, allow_nan=False, allow_infinity=False),
    seed=st.integers(min_value=0, max_value=2**32 - 1),
)
def test_p3_awgn_at_or_above_15_db_round_trip(
    payload: bytes, sample_rate: int, snr_db: float, seed: int
) -> None:
    frame = b"\xA5\x26" + payload
    waveform = modulate(frame, sample_rate, amplitude=0.65, initial_phase_radians=1.1)
    noisy = _awgn(waveform, snr_db, seed)
    assert float(np.max(np.abs(noisy))) <= 0.99
    result = demodulate(noisy, DemodulatorConfig(sample_rate))
    assert result.candidates == (frame,)


@pytest.mark.slow
@settings(max_examples=_P5_EXAMPLES, deadline=None)
@given(
    sample_rate=st.sampled_from(_SAMPLE_RATES),
    duration_ms=st.integers(min_value=1, max_value=400),
    seed=st.integers(min_value=0, max_value=2**32 - 1),
)
def test_p5_random_noise_never_yields_a_modem_candidate(
    sample_rate: int, duration_ms: int, seed: int
) -> None:
    generator = np.random.default_rng(seed)
    pcm = generator.normal(0.0, 0.3, sample_rate * duration_ms // 1_000)
    result = demodulate(pcm, DemodulatorConfig(sample_rate))
    assert result.candidates == ()


@pytest.mark.parametrize("frequency", [300.0, 700.0, 3_100.0, 5_000.0])
def test_p5_unrelated_tones_do_not_yield_candidates(frequency: float) -> None:
    result = demodulate(_tone(frequency, 48_000, 1.5), DemodulatorConfig(48_000))
    assert result.candidates == ()


def test_p5_clicks_do_not_yield_candidates() -> None:
    pcm = np.zeros(48_000, dtype=np.float64)
    pcm[::997] = 0.9
    pcm[499::997] = -0.9
    assert demodulate(pcm, DemodulatorConfig(48_000)).candidates == ()


def test_p2_arbitrary_chunking_matches_batch_candidate() -> None:
    waveform = modulate(_GOLDEN_FRAME, 44_100)
    cuts = (13, 1_017, 9_999, 31_001, waveform.size)
    chunks: list[np.ndarray] = []
    start = 0
    for stop in cuts:
        chunks.append(waveform[start:stop])
        start = stop
    result = demodulate_chunks(chunks, DemodulatorConfig(44_100))
    assert result.candidates == (_GOLDEN_FRAME,)


def test_al_req_2_stable_preamble_and_sync_timeout_errors() -> None:
    config = DemodulatorConfig(48_000)
    partial = _tone(MARK_FREQUENCY_HZ, 48_000, 0.1)
    partial_result = demodulate(partial, config)
    assert partial_result.diagnostics.failure is not None
    assert partial_result.diagnostics.failure.code is ModemErrorCode.PREAMBLE_TIMEOUT

    preamble_only = _tone(MARK_FREQUENCY_HZ, 48_000, 0.3)
    sync_timeout = demodulate(preamble_only, config)
    assert sync_timeout.diagnostics.failure is not None
    assert sync_timeout.diagnostics.failure.code is ModemErrorCode.SYNC_TIMEOUT


def test_al_req_2_stable_sync_error() -> None:
    frame_without_sync = bytes(FRAME_BYTES)
    result = demodulate(modulate(frame_without_sync, 48_000), DemodulatorConfig(48_000))
    assert result.candidates == ()
    assert result.diagnostics.failure is not None
    assert result.diagnostics.failure.code is ModemErrorCode.SYNC


def test_al_req_2_stable_frame_timeout_error() -> None:
    waveform = modulate(_GOLDEN_FRAME, 48_000)
    truncated = waveform[: -(20 * samples_per_symbol(48_000))]
    result = demodulate(truncated, DemodulatorConfig(48_000))
    assert result.candidates == ()
    assert result.diagnostics.failure is not None
    assert result.diagnostics.failure.code is ModemErrorCode.FRAME_TIMEOUT


def test_al_req_2_stable_uart_framing_error() -> None:
    sample_rate = 48_000
    width = samples_per_symbol(sample_rate)
    waveform = modulate(_GOLDEN_FRAME, sample_rate)
    # Replace byte 2's stop bit (mark) with space. The codec maps this detail to LENGTH.
    stop_start = (MIN_PREAMBLE_SYMBOLS + 2 * 10 + 9) * width
    waveform[stop_start : stop_start + width] = _tone(
        SPACE_FREQUENCY_HZ, sample_rate, 1 / BAUD
    )
    result = demodulate(waveform, DemodulatorConfig(sample_rate))
    assert result.candidates == ()
    assert result.diagnostics.failure is not None
    assert result.diagnostics.failure.code is ModemErrorCode.FRAMING
