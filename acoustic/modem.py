"""Pure NumPy Bell-202 modulation and batch demodulation for Apollo-26.

The modem only recovers fixed-size byte candidates.  It deliberately does not
validate CRC, HMAC, sequence numbers, or otherwise accept a command.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

import numpy as np
from numpy.typing import NDArray

BAUD = 300
MARK_FREQUENCY_HZ = 1_200.0
SPACE_FREQUENCY_HZ = 2_200.0
SUPPORTED_SAMPLE_RATES = (44_100, 48_000)
FRAME_BYTES = 34
MIN_PREAMBLE_SYMBOLS = 75
SYNC_BYTES = b"\xA5\x26"


class ModemConfigurationError(ValueError):
    """Raised before DSP starts when modem configuration is unsupported."""


class SourceKind(str, Enum):
    """Typed source identity retained in modem diagnostics."""

    MEMORY = "memory"
    MICROPHONE = "microphone"
    WAV = "wav"
    LOOPBACK = "loopback"


class ReceiverState(str, Enum):
    """State in which a diagnostic observation was made."""

    IDLE = "IDLE"
    PREAMBLE = "PREAMBLE"
    SYNC = "SYNC"
    RECEIVE = "RECEIVE"


class Tone(str, Enum):
    """Result of a matched-frequency symbol decision."""

    MARK = "MARK"
    SPACE = "SPACE"
    UNKNOWN = "UNKNOWN"


class ModemErrorCode(str, Enum):
    """Stable modem-local failure categories.

    Frame validation maps sync failures to ``SYNC`` and incomplete or UART
    framing failures to ``LENGTH`` at its boundary.  Keeping the modem detail
    separate makes acquisition, framing, and timeout failures diagnosable.
    """

    NO_CARRIER = "NO_CARRIER"
    PREAMBLE_TIMEOUT = "PREAMBLE_TIMEOUT"
    SYNC = "SYNC"
    SYNC_TIMEOUT = "SYNC_TIMEOUT"
    FRAMING = "FRAMING"
    FRAME_TIMEOUT = "FRAME_TIMEOUT"


@dataclass(frozen=True)
class DemodulatorConfig:
    """Validated thresholds for the pure batch demodulator."""

    sample_rate: int
    baud: int = BAUD
    frame_bytes: int = FRAME_BYTES
    preamble_symbols: int = MIN_PREAMBLE_SYMBOLS
    minimum_tone_amplitude: float = 0.05
    confidence_ratio: float = 1.8
    anomaly_threshold_hz: float = 50.0

    def __post_init__(self) -> None:
        _validate_sample_rate_and_baud(self.sample_rate, self.baud)
        if self.frame_bytes != FRAME_BYTES:
            raise ModemConfigurationError(f"frame_bytes must be {FRAME_BYTES}")
        if self.preamble_symbols < MIN_PREAMBLE_SYMBOLS:
            raise ModemConfigurationError(
                f"preamble_symbols must be at least {MIN_PREAMBLE_SYMBOLS}"
            )
        if not 0.0 < self.minimum_tone_amplitude <= 1.0:
            raise ModemConfigurationError("minimum_tone_amplitude must be in (0, 1]")
        if self.confidence_ratio <= 1.0 or not np.isfinite(self.confidence_ratio):
            raise ModemConfigurationError("confidence_ratio must be finite and greater than 1")
        if self.anomaly_threshold_hz != 50.0:
            raise ModemConfigurationError("Apollo-26 v1 anomaly_threshold_hz must be 50")


@dataclass(frozen=True)
class ToneMeasurement:
    """Matched-frequency energies and the resulting tone decision."""

    tone: Tone
    mark_energy: float
    space_energy: float
    confidence: float


@dataclass(frozen=True)
class FrequencyAnomaly:
    """Qualified frequency observation beyond the contractual 50 Hz limit."""

    source_kind: SourceKind
    expected_frequency_hz: float
    measured_frequency_hz: float
    absolute_deviation_hz: float
    receiver_state: ReceiverState
    candidate_correlation: str | None = None


@dataclass(frozen=True)
class ModemFailure:
    """A stable modem-local error with its receiver state and sample offset."""

    code: ModemErrorCode
    state: ReceiverState
    sample_offset: int
    message: str


@dataclass(frozen=True)
class DemodulationDiagnostics:
    """Typed observations returned alongside byte candidates."""

    source_kind: SourceKind
    sample_rate: int
    samples_processed: int
    max_frequency_deviation_hz: float | None
    anomalies: tuple[FrequencyAnomaly, ...] = field(default_factory=tuple)
    failure: ModemFailure | None = None


@dataclass(frozen=True)
class DemodulationResult:
    """Recovered bytes awaiting validation by the frame codec."""

    candidates: tuple[bytes, ...]
    diagnostics: DemodulationDiagnostics


@dataclass(frozen=True)
class _DecodedByte:
    value: int
    framing_valid: bool
    confidence: float


def _validate_sample_rate_and_baud(sample_rate: int, baud: int) -> None:
    if baud != BAUD:
        raise ModemConfigurationError(f"unsupported baud {baud}; Apollo-26 v1 requires {BAUD}")
    if sample_rate not in SUPPORTED_SAMPLE_RATES:
        rates = ", ".join(str(rate) for rate in SUPPORTED_SAMPLE_RATES)
        raise ModemConfigurationError(
            f"unsupported sample rate {sample_rate}; expected one of {rates}"
        )


def samples_per_symbol(sample_rate: int, baud: int = BAUD) -> int:
    """Return the exact integral symbol width for a supported configuration."""

    _validate_sample_rate_and_baud(sample_rate, baud)
    return sample_rate // baud


def serialize_8n1(
    frame: bytes,
    *,
    preamble_symbols: int = MIN_PREAMBLE_SYMBOLS,
    baud: int = BAUD,
) -> NDArray[np.uint8]:
    """Serialize one 34-byte frame to preamble and 8N1 symbol values."""

    if baud != BAUD:
        raise ModemConfigurationError(f"unsupported baud {baud}; Apollo-26 v1 requires {BAUD}")
    if len(frame) != FRAME_BYTES:
        raise ValueError(f"frame must contain exactly {FRAME_BYTES} bytes")
    if preamble_symbols < MIN_PREAMBLE_SYMBOLS:
        raise ValueError(f"preamble must contain at least {MIN_PREAMBLE_SYMBOLS} symbols")

    symbols = np.empty(preamble_symbols + FRAME_BYTES * 10, dtype=np.uint8)
    symbols[:preamble_symbols] = 1
    cursor = preamble_symbols
    for value in frame:
        symbols[cursor] = 0
        for bit_index in range(8):
            symbols[cursor + 1 + bit_index] = (value >> bit_index) & 1
        symbols[cursor + 9] = 1
        cursor += 10
    return symbols


def modulate(
    frame: bytes,
    sample_rate: int,
    *,
    amplitude: float = 0.8,
    initial_phase_radians: float = 0.0,
    preamble_symbols: int = MIN_PREAMBLE_SYMBOLS,
    baud: int = BAUD,
) -> NDArray[np.float64]:
    """Generate mono floating-point Bell-202 PCM with one phase accumulator."""

    symbol_samples = samples_per_symbol(sample_rate, baud)
    if not np.isfinite(amplitude) or not 0.0 < amplitude <= 1.0:
        raise ValueError("amplitude must be finite and in (0, 1]")
    if not np.isfinite(initial_phase_radians):
        raise ValueError("initial_phase_radians must be finite")

    symbols = serialize_8n1(frame, preamble_symbols=preamble_symbols, baud=baud)
    frequencies = np.where(symbols == 1, MARK_FREQUENCY_HZ, SPACE_FREQUENCY_HZ)
    per_sample_frequency = np.repeat(frequencies, symbol_samples)
    increments = (2.0 * np.pi / sample_rate) * per_sample_frequency
    phases = np.empty(increments.size, dtype=np.float64)
    phases[0] = initial_phase_radians
    if phases.size > 1:
        phases[1:] = initial_phase_radians + np.cumsum(increments[:-1], dtype=np.float64)
    return amplitude * np.sin(phases)


def _as_mono_float(samples: NDArray[np.floating] | Iterable[float]) -> NDArray[np.float64]:
    pcm = np.asarray(samples, dtype=np.float64)
    if pcm.ndim != 1:
        raise ValueError("PCM must be a one-dimensional mono array")
    if not np.all(np.isfinite(pcm)):
        raise ValueError("PCM must contain only finite samples")
    return pcm


def matched_tone_energy(
    samples: NDArray[np.floating] | Iterable[float],
    sample_rate: int,
    frequency_hz: float,
) -> float:
    """Return normalized quadrature matched-filter energy for one tone."""

    _validate_sample_rate_and_baud(sample_rate, BAUD)
    pcm = _as_mono_float(samples)
    if pcm.size == 0:
        return 0.0
    index = np.arange(pcm.size, dtype=np.float64)
    phase = 2.0 * np.pi * frequency_hz * index / sample_rate
    in_phase = float(np.dot(pcm, np.cos(phase)))
    quadrature = float(np.dot(pcm, np.sin(phase)))
    return (2.0 / pcm.size) ** 2 * (in_phase * in_phase + quadrature * quadrature)


def goertzel_tone(
    samples: NDArray[np.floating] | Iterable[float],
    config: DemodulatorConfig,
) -> ToneMeasurement:
    """Classify one symbol window by Bell-202 matched-frequency energy."""

    pcm = _as_mono_float(samples)
    mark_energy = matched_tone_energy(pcm, config.sample_rate, MARK_FREQUENCY_HZ)
    space_energy = matched_tone_energy(pcm, config.sample_rate, SPACE_FREQUENCY_HZ)
    minimum_energy = config.minimum_tone_amplitude**2
    stronger = max(mark_energy, space_energy)
    weaker = max(min(mark_energy, space_energy), np.finfo(np.float64).tiny)
    confidence = stronger / weaker
    if stronger < minimum_energy or confidence < config.confidence_ratio:
        tone = Tone.UNKNOWN
    else:
        tone = Tone.MARK if mark_energy > space_energy else Tone.SPACE
    return ToneMeasurement(tone, mark_energy, space_energy, confidence)


def estimate_frequency(
    samples: NDArray[np.floating] | Iterable[float],
    sample_rate: int,
    expected_frequency_hz: float,
) -> float | None:
    """Estimate a qualified tone frequency from matched-filter phase slope.

    At least eight symbols are required.  ``None`` denotes insufficient tone
    duration or confidence rather than an invented measurement.
    """

    _validate_sample_rate_and_baud(sample_rate, BAUD)
    pcm = _as_mono_float(samples)
    width = samples_per_symbol(sample_rate)
    block_count = pcm.size // width
    if block_count < 8:
        return None
    trimmed = pcm[: block_count * width].reshape(block_count, width)
    local_index = np.arange(width, dtype=np.float64)
    local_oscillator = np.exp(
        -2j * np.pi * expected_frequency_hz * local_index / sample_rate
    )
    correlations = trimmed @ local_oscillator
    amplitudes = 2.0 * np.abs(correlations) / width
    median_amplitude = float(np.median(amplitudes))
    if median_amplitude < 0.01:
        return None

    # Restore each block's absolute oscillator phase before fitting its slope.
    block_start = np.arange(block_count, dtype=np.float64) * width
    absolute_rotation = np.exp(
        -2j * np.pi * expected_frequency_hz * block_start / sample_rate
    )
    phases = np.unwrap(np.angle(correlations * absolute_rotation))
    times = (block_start + (width - 1) / 2.0) / sample_rate
    slope, _ = np.polyfit(times, phases, 1)
    measured = expected_frequency_hz + float(slope) / (2.0 * np.pi)
    if not np.isfinite(measured):
        return None
    return measured


def frequency_anomaly(
    measured_frequency_hz: float | None,
    expected_frequency_hz: float,
    *,
    source_kind: SourceKind,
    receiver_state: ReceiverState,
    candidate_correlation: str | None = None,
) -> FrequencyAnomaly | None:
    """Create an anomaly only when a qualified estimate exceeds 50 Hz."""

    if measured_frequency_hz is None or not np.isfinite(measured_frequency_hz):
        return None
    deviation = abs(measured_frequency_hz - expected_frequency_hz)
    if deviation <= 50.0:
        return None
    return FrequencyAnomaly(
        source_kind=source_kind,
        expected_frequency_hz=expected_frequency_hz,
        measured_frequency_hz=measured_frequency_hz,
        absolute_deviation_hz=deviation,
        receiver_state=receiver_state,
        candidate_correlation=candidate_correlation,
    )


def _symbol_tone(
    pcm: NDArray[np.float64], start: int, config: DemodulatorConfig
) -> ToneMeasurement | None:
    width = samples_per_symbol(config.sample_rate, config.baud)
    if start < 0 or start + width > pcm.size:
        return None
    return goertzel_tone(pcm[start : start + width], config)


def _decode_byte(
    pcm: NDArray[np.float64], start: int, config: DemodulatorConfig
) -> _DecodedByte | None:
    tones: list[Tone] = []
    confidence = 0.0
    width = samples_per_symbol(config.sample_rate, config.baud)
    for symbol_index in range(10):
        measurement = _symbol_tone(pcm, start + symbol_index * width, config)
        if measurement is None:
            return None
        tones.append(measurement.tone)
        confidence += np.log(max(measurement.confidence, 1.0))
    framing_valid = tones[0] is Tone.SPACE and tones[9] is Tone.MARK
    if any(tone is Tone.UNKNOWN for tone in tones[1:9]):
        framing_valid = False
    value = 0
    for bit_index, tone in enumerate(tones[1:9]):
        if tone is Tone.MARK:
            value |= 1 << bit_index
    return _DecodedByte(value, framing_valid, float(confidence))


def _sync_candidate(
    pcm: NDArray[np.float64], transition_guess: int, config: DemodulatorConfig
) -> tuple[int | None, bool, bool]:
    """Return best body offset, whether framing was seen, and whether data was available."""

    width = samples_per_symbol(config.sample_rate, config.baud)
    lower = max(0, transition_guess - 2 * width)
    upper = min(pcm.size - 20 * width, transition_guess + 2 * width)
    if upper < lower:
        return None, False, False

    coarse_step = max(1, width // 16)
    coarse_offsets = range(lower, upper + 1, coarse_step)
    framed: list[tuple[float, int, bytes]] = []
    for offset in coarse_offsets:
        first = _decode_byte(pcm, offset, config)
        second = _decode_byte(pcm, offset + 10 * width, config)
        if first is None or second is None:
            continue
        if first.framing_valid and second.framing_valid:
            framed.append((first.confidence + second.confidence, offset, bytes((first.value, second.value))))

    if not framed:
        return None, False, True
    sync_framed = [entry for entry in framed if entry[2] == SYNC_BYTES]
    if not sync_framed:
        return None, True, True
    _, coarse_best, _ = max(sync_framed)

    refined: list[tuple[float, int]] = []
    for offset in range(max(lower, coarse_best - coarse_step), min(upper, coarse_best + coarse_step) + 1):
        first = _decode_byte(pcm, offset, config)
        second = _decode_byte(pcm, offset + 10 * width, config)
        if (
            first is not None
            and second is not None
            and first.framing_valid
            and second.framing_valid
            and bytes((first.value, second.value)) == SYNC_BYTES
        ):
            refined.append((first.confidence + second.confidence, offset))
    if not refined:
        return coarse_best, True, True
    return max(refined)[1], True, True


def demodulate(
    samples: NDArray[np.floating] | Iterable[float],
    config: DemodulatorConfig,
    *,
    source_kind: SourceKind = SourceKind.MEMORY,
) -> DemodulationResult:
    """Recover fixed 34-byte candidates from a batch of mono PCM.

    The returned candidates are untrusted.  The caller must pass each one to
    the frame codec for sync/version/CRC/HMAC/replay validation before any
    command can be accepted.
    """

    pcm = _as_mono_float(samples)
    original_size = int(pcm.size)
    width = samples_per_symbol(config.sample_rate, config.baud)
    # Symbol-timing refinement can land a few samples after the true boundary.
    # Allow at most 1/8 symbol of silent tail so a frame that ends exactly at the
    # buffer edge is still measurable; larger truncation remains FRAME_TIMEOUT.
    pcm = np.concatenate((pcm, np.zeros(width // 8, dtype=np.float64)))
    hop = width // 4
    starts = np.arange(0, max(0, pcm.size - width + 1), hop, dtype=np.int64)
    decisions = [
        goertzel_tone(pcm[int(start) : int(start) + width], config).tone for start in starts
    ]
    minimum_duration = config.preamble_symbols * width
    candidates: list[bytes] = []
    anomalies: list[FrequencyAnomaly] = []
    max_deviation: float | None = None
    failure: ModemFailure | None = None
    run_start_index: int | None = None

    for decision_index, tone in enumerate(decisions):
        if tone is Tone.MARK:
            if run_start_index is None:
                run_start_index = decision_index
            continue

        if run_start_index is None:
            continue
        run_start = int(starts[run_start_index])
        last_mark_start = int(starts[decision_index - 1])
        run_duration = last_mark_start + width - run_start
        if run_duration < minimum_duration:
            run_start_index = None
            continue

        transition_guess = last_mark_start + width
        estimate = estimate_frequency(
            pcm[run_start : min(run_start + minimum_duration, pcm.size)],
            config.sample_rate,
            MARK_FREQUENCY_HZ,
        )
        if estimate is not None:
            deviation = abs(estimate - MARK_FREQUENCY_HZ)
            max_deviation = deviation if max_deviation is None else max(max_deviation, deviation)
            anomaly = frequency_anomaly(
                estimate,
                MARK_FREQUENCY_HZ,
                source_kind=source_kind,
                receiver_state=ReceiverState.PREAMBLE,
            )
            if anomaly is not None:
                anomalies.append(anomaly)

        body_start, saw_framing, had_sync_data = _sync_candidate(pcm, transition_guess, config)
        if body_start is None:
            if not had_sync_data:
                code = ModemErrorCode.SYNC_TIMEOUT
                message = "audio ended before the sync bytes were available"
            elif saw_framing:
                code = ModemErrorCode.SYNC
                message = "qualified preamble was not followed by sync A5 26"
            else:
                code = ModemErrorCode.FRAMING
                message = "sync bytes did not have valid 8N1 framing"
            failure = ModemFailure(code, ReceiverState.SYNC, transition_guess, message)
            break

        body_samples = config.frame_bytes * 10 * width
        if body_start + body_samples > pcm.size:
            failure = ModemFailure(
                ModemErrorCode.FRAME_TIMEOUT,
                ReceiverState.RECEIVE,
                body_start,
                "audio ended before the fixed 34-byte candidate completed",
            )
            break

        decoded = bytearray()
        framing_offset: int | None = None
        for byte_index in range(config.frame_bytes):
            item = _decode_byte(pcm, body_start + byte_index * 10 * width, config)
            if item is None:
                break
            if not item.framing_valid:
                framing_offset = byte_index
                break
            decoded.append(item.value)
        if framing_offset is not None or len(decoded) != config.frame_bytes:
            failure = ModemFailure(
                ModemErrorCode.FRAMING,
                ReceiverState.RECEIVE,
                body_start + (framing_offset or len(decoded)) * 10 * width,
                "candidate contains an invalid UART start or stop bit",
            )
            break

        # A candidate correlation is diagnostic context, not an acceptance token.
        correlation = decoded[:2].hex()
        if bytes(decoded[:2]) != SYNC_BYTES:
            failure = ModemFailure(
                ModemErrorCode.SYNC,
                ReceiverState.SYNC,
                body_start,
                "decoded candidate does not begin with sync A5 26",
            )
            break
        candidates.append(bytes(decoded))
        if anomalies:
            last = anomalies[-1]
            anomalies[-1] = FrequencyAnomaly(
                source_kind=last.source_kind,
                expected_frequency_hz=last.expected_frequency_hz,
                measured_frequency_hz=last.measured_frequency_hz,
                absolute_deviation_hz=last.absolute_deviation_hz,
                receiver_state=last.receiver_state,
                candidate_correlation=correlation,
            )
        run_start_index = None

    if failure is None and not candidates:
        if run_start_index is not None:
            run_start = int(starts[run_start_index])
            run_duration = pcm.size - run_start
            code = (
                ModemErrorCode.PREAMBLE_TIMEOUT
                if run_duration < minimum_duration
                else ModemErrorCode.SYNC_TIMEOUT
            )
            state = ReceiverState.PREAMBLE if code is ModemErrorCode.PREAMBLE_TIMEOUT else ReceiverState.SYNC
            failure = ModemFailure(code, state, run_start, "audio ended during acquisition")
        else:
            failure = ModemFailure(
                ModemErrorCode.NO_CARRIER,
                ReceiverState.IDLE,
                0,
                "no qualified Apollo-26 preamble was found",
            )

    return DemodulationResult(
        candidates=tuple(candidates),
        diagnostics=DemodulationDiagnostics(
            source_kind=source_kind,
            sample_rate=config.sample_rate,
            samples_processed=original_size,
            max_frequency_deviation_hz=max_deviation,
            anomalies=tuple(anomalies),
            failure=failure,
        ),
    )


def demodulate_chunks(
    chunks: Iterable[NDArray[np.floating]],
    config: DemodulatorConfig,
    *,
    source_kind: SourceKind = SourceKind.MEMORY,
) -> DemodulationResult:
    """Batch-decode explicitly supplied chunks without observing I/O or clocks."""

    normalized = [_as_mono_float(chunk) for chunk in chunks]
    pcm = np.concatenate(normalized) if normalized else np.empty(0, dtype=np.float64)
    return demodulate(pcm, config, source_kind=source_kind)
