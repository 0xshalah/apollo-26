"""Streaming wrapper around the pure batch demodulator.

Bounded rolling buffer + periodic demodulation with three guarantees:

* memory is bounded (``max_seconds`` of float64 PCM, preallocated);
* a full demodulation pass runs only when a cheap vectorized detector has seen
  a mark run long enough to be a preamble (idle/noise CPU stays low);
* the same frame is never decoded twice: passes run every ``hop`` samples, so a
  frame first becomes decodable in the pass right after its last stop bit.
  After a pass that yields candidates the buffer keeps only the most recent
  ``hop + 2 symbols`` samples, which cannot contain another complete frame.

The receiver never validates frames; candidates are untrusted bytes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

import numpy as np
from numpy.typing import NDArray

from acoustic.modem import (
    FRAME_BYTES,
    MARK_FREQUENCY_HZ,
    SPACE_FREQUENCY_HZ,
    DemodulatorConfig,
    FrequencyAnomaly,
    ModemErrorCode,
    SourceKind,
    demodulate,
    samples_per_symbol,
)

DEFAULT_HOP_SECONDS: Final = 0.25
DEFAULT_MAX_SECONDS: Final = 4.0
_PREAMBLE_TRIGGER_SYMBOLS: Final = 60
_MAX_RESCANS: Final = 8


class CandidateLoss(StrEnum):
    """Modem-level losses mapped to wire reasons by the daemon (SYNC / LENGTH)."""

    SYNC = "SYNC"
    FRAMING = "FRAMING"
    TRUNCATED = "TRUNCATED"


@dataclass(frozen=True, slots=True)
class CandidateEvent:
    raw: bytes
    frequency_deviation_hz: float | None


@dataclass(frozen=True, slots=True)
class LostCandidateEvent:
    loss: CandidateLoss
    frequency_deviation_hz: float | None


@dataclass(frozen=True, slots=True)
class AnomalyEvent:
    anomaly: FrequencyAnomaly


@dataclass(frozen=True, slots=True)
class CarrierEvent:
    active: bool


type ReceiverEvent = CandidateEvent | LostCandidateEvent | AnomalyEvent | CarrierEvent


class StreamingReceiver:
    def __init__(
        self,
        config: DemodulatorConfig,
        source_kind: SourceKind,
        *,
        hop_seconds: float = DEFAULT_HOP_SECONDS,
        max_seconds: float = DEFAULT_MAX_SECONDS,
    ) -> None:
        self._config = config
        self._source_kind = source_kind
        self._width = samples_per_symbol(config.sample_rate, config.baud)
        self._hop = int(config.sample_rate * hop_seconds)
        self._capacity = int(config.sample_rate * max_seconds)
        frame_samples = (config.preamble_symbols + FRAME_BYTES * 10) * self._width
        if self._capacity < frame_samples + self._hop:
            raise ValueError("receiver buffer is shorter than one frame plus one hop")
        self._buffer = np.zeros(self._capacity, dtype=np.float64)
        self._length = 0
        self._since_pass = 0
        self._total = 0
        self._preamble_seen_at: int | None = None
        self._mark_run = 0
        self._carrier = False
        index = np.arange(self._width, dtype=np.float64)
        rate = config.sample_rate
        self._mark_lo = np.exp(-2j * np.pi * MARK_FREQUENCY_HZ * index / rate)
        self._space_lo = np.exp(-2j * np.pi * SPACE_FREQUENCY_HZ * index / rate)
        self._detector_tail = np.zeros(0, dtype=np.float64)

    @property
    def buffered_samples(self) -> int:
        return self._length

    @property
    def capacity_samples(self) -> int:
        return self._capacity

    def latest(self, count: int) -> NDArray[np.float64]:
        count = min(count, self._length)
        return self._buffer[self._length - count : self._length].copy()

    def reset(self) -> list[ReceiverEvent]:
        """Discard partial state (e.g. after a dropped block); require a fresh preamble."""

        self._length = 0
        self._since_pass = 0
        self._preamble_seen_at = None
        self._mark_run = 0
        self._detector_tail = np.zeros(0, dtype=np.float64)
        return self._set_carrier(False)

    def feed(self, samples: NDArray[np.floating]) -> list[ReceiverEvent]:
        pcm = np.asarray(samples, dtype=np.float64)
        if pcm.ndim != 1:
            raise ValueError("receiver accepts mono PCM only")
        if not np.all(np.isfinite(pcm)):
            raise ValueError("receiver accepts finite PCM only")
        events: list[ReceiverEvent] = []
        offset = 0
        while offset < pcm.size:
            take = min(pcm.size - offset, self._hop - self._since_pass)
            self._append(pcm[offset : offset + take])
            offset += take
            self._since_pass += take
            if self._since_pass >= self._hop:
                self._since_pass = 0
                events.extend(self._maybe_pass(final=False))
        return events

    def flush(self) -> list[ReceiverEvent]:
        """Run a final pass at end of input (WAV EOF drain)."""

        events = self._maybe_pass(final=True)
        events.extend(self.reset())
        return events

    def _append(self, chunk: NDArray[np.float64]) -> None:
        self._detect_preamble(chunk)
        self._total += chunk.size
        overflow = self._length + chunk.size - self._capacity
        if overflow > 0:
            self._buffer[: self._length - overflow] = self._buffer[overflow : self._length]
            self._length -= overflow
        self._buffer[self._length : self._length + chunk.size] = chunk
        self._length += chunk.size

    def _detect_preamble(self, chunk: NDArray[np.float64]) -> None:
        data = np.concatenate((self._detector_tail, chunk))
        count = data.size // self._width
        if count:
            windows = data[: count * self._width].reshape(count, self._width)
            mark = np.abs(windows @ self._mark_lo) * (2.0 / self._width)
            space = np.abs(windows @ self._space_lo) * (2.0 / self._width)
            is_mark = (mark >= self._config.minimum_tone_amplitude) & (
                mark >= self._config.confidence_ratio * space
            )
            for flag in is_mark:
                self._mark_run = self._mark_run + 1 if flag else 0
                if self._mark_run >= _PREAMBLE_TRIGGER_SYMBOLS:
                    self._preamble_seen_at = self._total + chunk.size
        self._detector_tail = data[count * self._width :].copy()

    def _set_carrier(self, active: bool) -> list[ReceiverEvent]:
        if active == self._carrier:
            return []
        self._carrier = active
        return [CarrierEvent(active)]

    def _maybe_pass(self, *, final: bool) -> list[ReceiverEvent]:
        if self._preamble_seen_at is None:
            return []
        if self._total - self._preamble_seen_at > self._capacity:
            self._preamble_seen_at = None
            return self._set_carrier(False)
        events = self._set_carrier(True)
        events.extend(self._run_pass(final=final))
        return events

    def _run_pass(self, *, final: bool) -> list[ReceiverEvent]:
        events: list[ReceiverEvent] = []
        start = 0
        found = False
        for _ in range(_MAX_RESCANS):
            view = self._buffer[start : self._length]
            if view.size < 20 * self._width:
                break
            result = demodulate(view, self._config, source_kind=self._source_kind)
            diagnostics = result.diagnostics
            deviation = diagnostics.max_frequency_deviation_hz
            # Anomalies are reported once, with the pass that concludes a candidate.
            anomalies = [AnomalyEvent(anomaly) for anomaly in diagnostics.anomalies]
            if result.candidates:
                events.extend(anomalies)
                anomalies = []
            for raw in result.candidates:
                events.append(CandidateEvent(raw, deviation))
                found = True
            failure = diagnostics.failure
            if failure is None:
                break
            if failure.code in (ModemErrorCode.SYNC, ModemErrorCode.FRAMING):
                loss = (
                    CandidateLoss.SYNC
                    if failure.code is ModemErrorCode.SYNC
                    else CandidateLoss.FRAMING
                )
                events.extend(anomalies)
                events.append(LostCandidateEvent(loss, deviation))
                start += failure.sample_offset + self._width
                continue
            if final and failure.code in (
                ModemErrorCode.FRAME_TIMEOUT,
                ModemErrorCode.SYNC_TIMEOUT,
            ):
                events.extend(anomalies)
                events.append(LostCandidateEvent(CandidateLoss.TRUNCATED, deviation))
            break
        if found:
            keep = min(self._length, self._hop + 2 * self._width)
            self._drop_front(self._length - keep)
            # Keep a trigger that belongs to a following preamble inside the kept tail.
            if self._preamble_seen_at is not None and self._preamble_seen_at <= self._total - keep:
                self._preamble_seen_at = None
            if self._preamble_seen_at is None:
                events.extend(self._set_carrier(False))
        elif start:
            self._drop_front(min(start, self._length))
        return events

    def _drop_front(self, count: int) -> None:
        if count <= 0:
            return
        remaining = self._length - count
        self._buffer[:remaining] = self._buffer[count : self._length]
        self._length = remaining
