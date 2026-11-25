"""Fallback soft-decision Bell-202 decoder for over-the-air audio.

The strict decoder in :mod:`acoustic.modem` makes a hard MARK/SPACE/UNKNOWN
decision per symbol and drops a frame on the first UNKNOWN symbol.  That is
correct for clean PCM but brittle on a speaker -> microphone channel, where the
two tones arrive at different levels ("twist"), room echoes smear symbol edges,
and low-frequency noise adds energy.  This module retries a burst whose
preamble already qualified, using techniques documented by software TNCs:

* zero-phase band-limiting to 700-2900 Hz before tone detection;
* tone detection over the central part of each symbol only, so echo tails from
  the previous symbol are not integrated;
* data-aided twist compensation: per-tone reference levels are measured on the
  known sync word ``A5 26`` and each tone is normalized before comparison;
* soft decisions (no UNKNOWN state) and per-byte start-bit re-alignment.

The output is soft bits, never an accepted command.  :mod:`acoustic.recovery`
turns soft bits into at most one CRC-consistent candidate, and the daemon still
runs the full contract validation (sync, version, CRC, HMAC, replay, ranges).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

from acoustic.modem import (
    FRAME_BYTES,
    MARK_FREQUENCY_HZ,
    SPACE_FREQUENCY_HZ,
    SYNC_BYTES,
    DemodulatorConfig,
    samples_per_symbol,
)

CENTER_FRACTION: Final = 0.6
SYNC_SEARCH_SYMBOLS: Final = 2
MIN_SYNC_SCORE: Final = 0.35
BYTE_SEARCH_FRACTION: Final = 0.125
MAX_GRID_DEVIATION_FRACTION: Final = 0.5
SYNC_SEARCH_GAINS: Final = (1.0, 2.0, 4.0, 8.0)
_BAND_EDGES_HZ: Final = (700.0, 1000.0, 2500.0, 2900.0)
_EPSILON: Final = 1e-12


@dataclass(frozen=True, slots=True)
class SoftFrame:
    """Soft decisions for one 34-byte burst; positive values mean bit 1."""

    soft_bits: NDArray[np.float64]
    """``FRAME_BYTES * 8`` values, byte order then LSB-first, normalized to median |x| = 1."""

    body_start: int
    body_end: int
    twist_db: float
    sync_score: float
    framing_errors: int


def _sync_symbols() -> NDArray[np.float64]:
    pattern: list[float] = []
    for value in SYNC_BYTES:
        pattern.append(-1.0)  # start bit (space)
        pattern.extend(1.0 if (value >> bit) & 1 else -1.0 for bit in range(8))
        pattern.append(1.0)  # stop bit (mark)
    return np.asarray(pattern, dtype=np.float64)


_SYNC_PATTERN: Final = _sync_symbols()


def band_limit(pcm: NDArray[np.float64], sample_rate: int) -> NDArray[np.float64]:
    """Zero-phase raised-cosine band-pass that keeps both Bell-202 tones."""

    size = int(pcm.size)
    if size == 0:
        return pcm.copy()
    fft_size = 1 << int(np.ceil(np.log2(size + sample_rate // 20)))
    spectrum = np.fft.rfft(pcm, fft_size)
    frequencies = np.fft.rfftfreq(fft_size, 1.0 / sample_rate)
    low_stop, low_pass, high_pass, high_stop = _BAND_EDGES_HZ
    mask = np.zeros_like(frequencies)
    rising = (frequencies > low_stop) & (frequencies < low_pass)
    mask[rising] = 0.5 - 0.5 * np.cos(
        np.pi * (frequencies[rising] - low_stop) / (low_pass - low_stop)
    )
    mask[(frequencies >= low_pass) & (frequencies <= high_pass)] = 1.0
    falling = (frequencies > high_pass) & (frequencies < high_stop)
    mask[falling] = 0.5 + 0.5 * np.cos(
        np.pi * (frequencies[falling] - high_pass) / (high_stop - high_pass)
    )
    return np.fft.irfft(spectrum * mask, fft_size)[:size]


def tone_envelope(
    pcm: NDArray[np.float64], sample_rate: int, frequency_hz: float, window: int
) -> NDArray[np.float64]:
    """Amplitude of ``frequency_hz`` over every window ``[t, t + window)``."""

    index = np.arange(pcm.size, dtype=np.float64)
    mixed = pcm * np.exp(-2j * np.pi * frequency_hz * index / sample_rate)
    cumulative = np.concatenate((np.zeros(1, dtype=np.complex128), np.cumsum(mixed)))
    return np.abs(cumulative[window:] - cumulative[:-window]) * (2.0 / window)


class _Envelopes:
    """Mark/space envelopes sampled at the centre of a symbol starting at ``s``."""

    def __init__(self, pcm: NDArray[np.float64], config: DemodulatorConfig) -> None:
        self.width = samples_per_symbol(config.sample_rate, config.baud)
        window = max(8, int(round(self.width * CENTER_FRACTION)))
        self.lead = (self.width - window) // 2
        filtered = band_limit(pcm, config.sample_rate)
        self.mark = tone_envelope(filtered, config.sample_rate, MARK_FREQUENCY_HZ, window)
        self.space = tone_envelope(filtered, config.sample_rate, SPACE_FREQUENCY_HZ, window)
        self.size = int(self.mark.size)


def _find_sync(env: _Envelopes, transition_guess: int) -> tuple[int, float, float, float] | None:
    """Return (sync_start, score, mark_ref, space_ref) for the best A5 26 alignment."""

    width = env.width
    symbol_offsets = np.arange(_SYNC_PATTERN.size, dtype=np.int64) * width
    lower = max(0, transition_guess - SYNC_SEARCH_SYMBOLS * width)
    upper = transition_guess + SYNC_SEARCH_SYMBOLS * width
    candidates = np.arange(lower, upper + 1, 2, dtype=np.int64)
    candidates = candidates[candidates + symbol_offsets[-1] + env.lead < env.size]
    if candidates.size == 0:
        return None
    centers = candidates[:, None] + symbol_offsets[None, :] + env.lead
    mark = env.mark[centers]
    space = env.space[centers]
    best: tuple[float, int] | None = None
    for gain in SYNC_SEARCH_GAINS:
        ratio = (mark - gain * space) / (mark + gain * space + _EPSILON)
        scores = ratio @ _SYNC_PATTERN / _SYNC_PATTERN.size
        index = int(np.argmax(scores))
        if best is None or scores[index] > best[0]:
            best = (float(scores[index]), index)
    assert best is not None
    score, index = best
    if score < MIN_SYNC_SCORE:
        return None
    is_mark = _SYNC_PATTERN > 0
    mark_ref = float(np.mean(mark[index][is_mark]))
    space_ref = float(np.mean(space[index][~is_mark]))
    if mark_ref <= _EPSILON or space_ref <= _EPSILON:
        return None
    return int(candidates[index]), score, mark_ref, space_ref


def soft_decode(
    pcm: NDArray[np.float64],
    config: DemodulatorConfig,
    transition_guess: int,
) -> SoftFrame | None:
    """Soft-decode one burst whose preamble ended near ``transition_guess``.

    Returns ``None`` when no sync alignment is plausible or the buffer does not
    yet contain the whole frame.
    """

    samples = np.asarray(pcm, dtype=np.float64)
    if samples.ndim != 1 or samples.size == 0:
        return None
    env = _Envelopes(samples, config)
    sync = _find_sync(env, transition_guess)
    if sync is None:
        return None
    sync_start, sync_score, mark_ref, space_ref = sync
    width = env.width
    byte_span = 10 * width

    search = max(1, int(width * BYTE_SEARCH_FRACTION))
    max_deviation = int(width * MAX_GRID_DEVIATION_FRACTION)
    deltas = np.arange(-search, search + 1, dtype=np.int64)
    symbol_offsets = np.arange(10, dtype=np.int64) * width
    soft = np.empty(FRAME_BYTES * 8, dtype=np.float64)
    framing_errors = 0
    predicted = sync_start
    last_start = sync_start
    for byte_index in range(FRAME_BYTES):
        nominal = sync_start + byte_index * byte_span
        starts = predicted + deltas
        starts = starts[np.abs(starts - nominal) <= max_deviation]
        positions = starts[:, None] + symbol_offsets[None, :]
        centers = positions + env.lead
        keep = (centers >= 0).all(axis=1) & (centers < env.size).all(axis=1)
        if not keep.any():
            return None
        starts = starts[keep]
        centers = centers[keep]
        decision = env.mark[centers] / mark_ref - env.space[centers] / space_ref
        scores = -decision[:, 0] + decision[:, 9] + np.abs(decision[:, 1:9]).sum(axis=1)
        best = int(np.argmax(scores))
        values = decision[best]
        if values[0] > 0 or values[9] < 0:
            framing_errors += 1
        soft[byte_index * 8 : byte_index * 8 + 8] = values[1:9]
        last_start = int(starts[best])
        predicted = last_start + byte_span

    scale = float(np.median(np.abs(soft)))
    if scale > _EPSILON:
        soft = soft / scale
    return SoftFrame(
        soft_bits=soft,
        body_start=sync_start,
        body_end=last_start + byte_span,
        twist_db=float(20.0 * np.log10(mark_ref / space_ref)),
        sync_score=sync_score,
        framing_errors=framing_errors,
    )
