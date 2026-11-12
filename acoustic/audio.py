"""Audio source adapters: microphone (sounddevice), WAV file (stdlib ``wave``), loopback.

Adapters only normalize PCM into bounded mono float blocks.  They never
demodulate or validate frames, so every source feeds the same receiver.
"""

from __future__ import annotations

import asyncio
import io
import logging
import queue
import wave
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Final, Protocol

import numpy as np
from numpy.typing import NDArray

from acoustic.modem import SUPPORTED_SAMPLE_RATES

_LOG = logging.getLogger(__name__)

BLOCK_MS: Final = 20
QUEUE_BLOCKS: Final = 32
MAX_LOOPBACK_SECONDS: Final = 20


class SourceKind(StrEnum):
    """Telemetry ``source.kind`` values from ``telemetry-frame.schema.json``."""

    MICROPHONE = "microphone"
    WAV = "wav"
    LOOPBACK = "loopback"


class SourceErrorCode(StrEnum):
    SOURCE_CONFIG = "SOURCE_CONFIG"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    SOURCE_IO = "SOURCE_IO"


class AudioSourceError(RuntimeError):
    def __init__(self, code: SourceErrorCode, message: str) -> None:
        super().__init__(f"{code.value}: {message}")
        self.code = code


@dataclass(frozen=True, slots=True)
class SourceMetadata:
    kind: SourceKind
    sample_rate: int

    def __post_init__(self) -> None:
        if self.sample_rate not in SUPPORTED_SAMPLE_RATES:
            raise AudioSourceError(
                SourceErrorCode.SOURCE_CONFIG,
                f"unsupported sample rate {self.sample_rate}; expected 48000 or 44100",
            )


class AudioSource(Protocol):
    overflows: int
    """Count of blocks dropped because the bounded queue was full."""

    @property
    def metadata(self) -> SourceMetadata: ...

    def blocks(self) -> AsyncIterator[NDArray[np.float64]]: ...

    async def close(self) -> None: ...


def block_samples(sample_rate: int) -> int:
    return sample_rate * BLOCK_MS // 1000


def split_blocks(pcm: NDArray[np.float64], sample_rate: int) -> list[NDArray[np.float64]]:
    size = block_samples(sample_rate)
    return [pcm[index : index + size] for index in range(0, pcm.size, size)]


def decode_wav_bytes(data: bytes) -> tuple[int, NDArray[np.float64]]:
    """Validate and decode mono 16-bit PCM WAV bytes to float samples in [-1, 1)."""

    try:
        with wave.open(io.BytesIO(data), "rb") as reader:
            channels = reader.getnchannels()
            width = reader.getsampwidth()
            rate = reader.getframerate()
            frames = reader.readframes(reader.getnframes())
    except (wave.Error, EOFError) as error:
        raise AudioSourceError(SourceErrorCode.SOURCE_CONFIG, f"invalid WAV data: {error}") from error
    if channels != 1:
        raise AudioSourceError(SourceErrorCode.SOURCE_CONFIG, "WAV must be mono")
    if width != 2:
        raise AudioSourceError(SourceErrorCode.SOURCE_CONFIG, "WAV must be 16-bit PCM")
    if rate not in SUPPORTED_SAMPLE_RATES:
        raise AudioSourceError(
            SourceErrorCode.SOURCE_CONFIG, f"WAV sample rate {rate} is not 48000 or 44100"
        )
    pcm = np.frombuffer(frames, dtype="<i2").astype(np.float64) / 32768.0
    return rate, pcm


def encode_wav_bytes(pcm: NDArray[np.floating[Any]], sample_rate: int) -> bytes:
    """Encode float PCM as mono 16-bit WAV with explicit clipping protection."""

    if sample_rate not in SUPPORTED_SAMPLE_RATES:
        raise AudioSourceError(SourceErrorCode.SOURCE_CONFIG, "unsupported sample rate")
    clipped = np.clip(np.asarray(pcm, dtype=np.float64), -1.0, 32767 / 32768)
    integers = np.round(clipped * 32768.0).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(sample_rate)
        writer.writeframes(integers.tobytes())
    return buffer.getvalue()


class WavFileSource:
    """Reads a validated WAV file and yields 20 ms blocks until EOF."""

    def __init__(self, path: Path) -> None:
        try:
            data = path.read_bytes()
        except OSError as error:
            raise AudioSourceError(
                SourceErrorCode.SOURCE_UNAVAILABLE, f"cannot read WAV {path}"
            ) from error
        rate, self._pcm = decode_wav_bytes(data)
        self._metadata = SourceMetadata(SourceKind.WAV, rate)
        self.overflows = 0

    @property
    def metadata(self) -> SourceMetadata:
        return self._metadata

    async def blocks(self) -> AsyncIterator[NDArray[np.float64]]:
        for block in split_blocks(self._pcm, self._metadata.sample_rate):
            yield block
            await asyncio.sleep(0)

    async def close(self) -> None:
        return None


class LoopbackSource:
    """In-memory source; PCM pushed by tests or the local loopback endpoint."""

    def __init__(self, sample_rate: int = 48_000) -> None:
        self._metadata = SourceMetadata(SourceKind.LOOPBACK, sample_rate)
        self._queue: asyncio.Queue[NDArray[np.float64] | None] = asyncio.Queue(QUEUE_BLOCKS)
        self._closed = False
        self.overflows = 0

    @property
    def metadata(self) -> SourceMetadata:
        return self._metadata

    async def push(self, pcm: NDArray[np.floating[Any]]) -> None:
        """Push PCM with back-pressure (bounded queue of 20 ms blocks)."""

        samples = np.asarray(pcm, dtype=np.float64)
        if samples.ndim != 1 or not np.all(np.isfinite(samples)):
            raise AudioSourceError(SourceErrorCode.SOURCE_CONFIG, "PCM must be finite mono")
        if samples.size > MAX_LOOPBACK_SECONDS * self._metadata.sample_rate:
            raise AudioSourceError(SourceErrorCode.SOURCE_CONFIG, "loopback burst too long")
        if self._closed:
            raise AudioSourceError(SourceErrorCode.SOURCE_IO, "loopback source is closed")
        for block in split_blocks(samples, self._metadata.sample_rate):
            await self._queue.put(block)

    async def drained(self) -> None:
        """Wait until the consumer has taken every pushed block."""

        while not self._queue.empty():
            await asyncio.sleep(0.001)

    async def blocks(self) -> AsyncIterator[NDArray[np.float64]]:
        while True:
            block = await self._queue.get()
            if block is None:
                return
            yield block

    async def close(self) -> None:
        if not self._closed:
            self._closed = True
            await self._queue.put(None)


class MicrophoneSource:
    """sounddevice capture; the callback only copies into a bounded queue."""

    def __init__(self, device: int | str | None = None, sample_rate: int | None = None) -> None:
        try:
            import sounddevice  # noqa: PLC0415 - optional hardware boundary
        except (ImportError, OSError) as error:
            raise AudioSourceError(
                SourceErrorCode.SOURCE_UNAVAILABLE, f"sounddevice unavailable: {error}"
            ) from error
        self._sd = sounddevice
        rate = sample_rate or self._pick_rate(device)
        self._metadata = SourceMetadata(SourceKind.MICROPHONE, rate)
        self._queue: queue.Queue[NDArray[np.float64]] = queue.Queue(QUEUE_BLOCKS)
        self.overflows = 0
        try:
            self._stream = sounddevice.InputStream(
                device=device,
                channels=1,
                samplerate=rate,
                blocksize=block_samples(rate),
                dtype="float32",
                callback=self._callback,
            )
            self._stream.start()
        except Exception as error:  # PortAudio raises its own error hierarchy
            raise AudioSourceError(
                SourceErrorCode.SOURCE_UNAVAILABLE,
                f"cannot open input device {device!r} at {rate} Hz: {error}",
            ) from error
        self._closed = False

    def _pick_rate(self, device: int | str | None) -> int:
        for rate in SUPPORTED_SAMPLE_RATES[::-1]:  # prefer 48 kHz, fall back to 44.1 kHz
            try:
                self._sd.check_input_settings(device=device, channels=1, samplerate=rate)
                return rate
            except Exception as error:  # noqa: BLE001 - PortAudio capability probe
                _LOG.info("input device %r rejected %d Hz: %s", device, rate, error)
                continue
        raise AudioSourceError(
            SourceErrorCode.SOURCE_UNAVAILABLE, f"device {device!r} supports neither 48 kHz nor 44.1 kHz"
        )

    def _callback(self, indata: Any, frames: int, time_info: Any, status: Any) -> None:
        del frames, time_info, status
        try:
            self._queue.put_nowait(np.array(indata[:, 0], dtype=np.float64))
        except queue.Full:
            self.overflows += 1

    @property
    def metadata(self) -> SourceMetadata:
        return self._metadata

    async def blocks(self) -> AsyncIterator[NDArray[np.float64]]:
        while not self._closed:
            try:
                block = await asyncio.to_thread(self._queue.get, True, 0.25)
            except queue.Empty:
                continue
            yield block

    async def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._stream.stop()
            self._stream.close()
