"""Deterministic speaker -> air -> microphone impairments for modem tests.

The impairments mirror what the 12-13 Nov 2026 over-the-air trials recorded
(TASK.md decision log): space tone weaker than mark, dominant 170-850 Hz room
energy, short reflections, and a laptop speaker driven hard.  This is a model,
not a measurement; real recordings (``scripts/acoustic_lab.py record``) are the
evidence that counts.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class Channel:
    twist_db: float = 0.0
    """Attenuation of 2200 Hz relative to 1200 Hz (positive = space weaker)."""

    echoes: Sequence[tuple[float, float]] = field(default_factory=tuple)
    """``(delay_ms, gain)`` reflections added to the direct path."""

    hum_amplitude: float = 0.0
    """Total amplitude of random 170-850 Hz room tones."""

    drive: float = 0.0
    """Soft-clip drive (0 = linear); creates harmonics such as 2400 Hz."""

    snr_db: float | None = None
    """White-noise SNR relative to the signal RMS; ``None`` = no noise."""

    gain: float = 1.0


def _apply_twist(pcm: NDArray[np.float64], rate: int, twist_db: float) -> NDArray[np.float64]:
    spectrum = np.fft.rfft(pcm)
    frequencies = np.fft.rfftfreq(pcm.size, 1.0 / rate)
    slope_db = -twist_db * (frequencies - 1200.0) / 1000.0
    return np.fft.irfft(spectrum * 10.0 ** (slope_db / 20.0), pcm.size)


def impair(
    pcm: NDArray[np.float64], rate: int, channel: Channel, rng: np.random.Generator
) -> NDArray[np.float64]:
    out = np.asarray(pcm, dtype=np.float64) * channel.gain
    if channel.twist_db:
        out = _apply_twist(out, rate, channel.twist_db)
    if channel.echoes:
        direct = out.copy()
        for delay_ms, echo_gain in channel.echoes:
            delay = int(rate * delay_ms / 1000.0)
            out[delay:] += echo_gain * direct[: out.size - delay]
    if channel.drive:
        out = np.tanh(channel.drive * out) / np.tanh(channel.drive)
    signal_rms = float(np.sqrt(np.mean(out[np.abs(out) > 1e-6] ** 2))) if np.any(out) else 0.0
    if channel.hum_amplitude:
        t = np.arange(out.size) / rate
        for _ in range(4):
            frequency = rng.uniform(170.0, 850.0)
            out += (channel.hum_amplitude / 4.0) * np.sin(
                2 * np.pi * frequency * t + rng.uniform(0, 2 * np.pi)
            )
    if channel.snr_db is not None and signal_rms > 0:
        noise_rms = signal_rms / (10.0 ** (channel.snr_db / 20.0))
        out += rng.normal(0.0, noise_rms, out.size)
    return out


LAPTOP_SELF_TEST = Channel(
    twist_db=8.0,
    echoes=((0.7, 0.45), (1.9, 0.3), (3.4, 0.2)),
    hum_amplitude=0.15,
    drive=1.5,
    snr_db=14.0,
    gain=0.5,
)
"""Rough model of the same-laptop speaker -> microphone-array trial."""
