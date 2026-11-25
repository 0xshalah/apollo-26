"""Apollo-26 acoustic lab: calibrate the air channel, record a corpus, analyze it.

Subcommands
-----------
calibrate   Play a mark tone, a space tone and silence through the speaker while
            recording the microphone.  Reports levels, twist (mark vs space),
            clipping, 2nd-harmonic distortion at 2400 Hz, tone fading caused by
            OS voice processing, and the noise floor, with concrete advice.
record      Record raw microphone audio to WAV for later analysis.
            ``--play`` sends N signed COMMAND bursts from this machine's speaker
            (same-laptop trial); ``--listen-seconds S`` only records, for a
            phone or another device transmitting from /ground.
simulate    Write impaired WAVs from the channel model in tests/channel_sim.py.
analyze     Decode every WAV in a corpus with the strict decoder and with the
            soft fallback; report success, recovery method, twist, framing
            errors and the byte positions of bit errors.

Typical day-1 loop::

    python scripts/acoustic_lab.py calibrate --amplitude 0.4
    python scripts/acoustic_lab.py record --play --frames 20 --out-dir corpus/laptop-a04
    python scripts/acoustic_lab.py analyze corpus/laptop-a04

Recordings stay local (``corpus/`` is git-ignored); commit only analysis JSON.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from acoustic.audio import decode_wav_bytes, encode_wav_bytes  # noqa: E402
from acoustic.frame import CommandFrame, KeyMaterial, encode_frame, validate_frame  # noqa: E402
from acoustic.modem import (  # noqa: E402
    MARK_FREQUENCY_HZ,
    SPACE_FREQUENCY_HZ,
    DemodulatorConfig,
    SourceKind,
    demodulate,
    matched_tone_energy,
    modulate,
)
from acoustic.receiver import CandidateEvent, DuplicateEvent, StreamingReceiver  # noqa: E402
from acoustic.soft_decoder import soft_decode  # noqa: E402

DEMO_LINK_KEY = "apollo26-link-demo-key-v1"
DEMO_OPERATOR_KEY = "apollo26-operator-demo-key-v1"
MANIFEST = "manifest.json"


def _keys() -> KeyMaterial:
    return KeyMaterial(
        os.environ.get("APOLLO26_LINK_KEY", DEMO_LINK_KEY).encode("utf-8"),
        os.environ.get("APOLLO26_OPERATOR_KEY", DEMO_OPERATOR_KEY).encode("utf-8"),
    )


def _command(seq: int, keys: KeyMaterial) -> bytes:
    return encode_frame(
        CommandFrame(
            seq=seq,
            critical=False,
            verb=25,
            noun=81,
            program=0,
            r1_centidegrees=1250,
            r2_centidegrees=420,
            delta_v_tenths_fps=3120,
        ),
        keys,
    )


def _burst(
    raw: bytes, rate: int, amplitude: float, repeat: int, gap_s: float
) -> NDArray[np.float64]:
    tone = modulate(raw, rate, amplitude=amplitude)
    parts: list[NDArray[np.float64]] = [np.zeros(int(rate * 0.3))]
    for index in range(repeat):
        parts.append(tone)
        if index + 1 < repeat:
            parts.append(np.zeros(int(rate * gap_s)))
    parts.append(np.zeros(int(rate * 0.6)))
    return np.concatenate(parts)


def _write_wav(path: Path, pcm: NDArray[np.float64], rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encode_wav_bytes(pcm, rate))


def _read_wav(path: Path) -> tuple[int, NDArray[np.float64]]:
    return decode_wav_bytes(path.read_bytes())


# ---------------------------------------------------------------- audio I/O


def _sounddevice() -> Any:
    try:
        import sounddevice  # noqa: PLC0415 - optional hardware boundary
    except (ImportError, OSError) as error:
        raise SystemExit(f"sounddevice unavailable: {error}") from error
    return sounddevice


def _play_and_record(
    pcm: NDArray[np.float64],
    rate: int,
    *,
    input_device: int | None,
    output_device: int | None,
    exclusive: bool,
    tail_s: float = 0.4,
) -> NDArray[np.float64]:
    sd = _sounddevice()
    extra = sd.WasapiSettings(exclusive=True) if exclusive else None
    captured: list[NDArray[np.float32]] = []

    def callback(indata: Any, frames: int, time_info: Any, status: Any) -> None:
        del frames, time_info
        if status:
            print(f"  input status: {status}", file=sys.stderr)
        captured.append(indata[:, 0].copy())

    with sd.InputStream(
        device=input_device,
        channels=1,
        samplerate=rate,
        dtype="float32",
        callback=callback,
        extra_settings=extra,
    ):
        time.sleep(0.2)
        sd.play(pcm.astype(np.float32), rate, device=output_device, blocking=True)
        time.sleep(tail_s)
    return np.concatenate(captured).astype(np.float64) if captured else np.zeros(0)


def _record_only(
    seconds: float, rate: int, *, input_device: int | None, exclusive: bool
) -> NDArray[np.float64]:
    sd = _sounddevice()
    extra = sd.WasapiSettings(exclusive=True) if exclusive else None
    frames = sd.rec(
        int(seconds * rate),
        samplerate=rate,
        channels=1,
        dtype="float32",
        device=input_device,
        extra_settings=extra,
        blocking=True,
    )
    return np.asarray(frames[:, 0], dtype=np.float64)


# ---------------------------------------------------------------- measurements


def _tone_amplitude(pcm: NDArray[np.float64], rate: int, frequency: float) -> float:
    return float(np.sqrt(matched_tone_energy(pcm, rate, frequency))) if pcm.size else 0.0


def _band_rms(pcm: NDArray[np.float64], rate: int, low: float, high: float) -> float:
    if pcm.size == 0:
        return 0.0
    spectrum = np.fft.rfft(pcm * np.hanning(pcm.size))
    frequencies = np.fft.rfftfreq(pcm.size, 1.0 / rate)
    band = (frequencies >= low) & (frequencies <= high)
    power = np.sum(np.abs(spectrum[band]) ** 2) / np.sum(np.hanning(pcm.size) ** 2)
    return float(np.sqrt(2.0 * power) / np.sqrt(pcm.size))


def _db(ratio: float) -> float:
    return float(20.0 * np.log10(max(ratio, 1e-12)))


def _segment(
    pcm: NDArray[np.float64], rate: int, start_s: float, end_s: float
) -> NDArray[np.float64]:
    return pcm[int(start_s * rate) : int(end_s * rate)]


def calibrate(args: argparse.Namespace) -> int:
    rate = args.sample_rate
    seconds = 1.2
    t = np.arange(int(rate * seconds)) / rate
    fade = np.minimum(1.0, np.minimum(t, t[::-1]) / 0.01)
    mark = args.amplitude * np.sin(2 * np.pi * MARK_FREQUENCY_HZ * t) * fade
    space = args.amplitude * np.sin(2 * np.pi * SPACE_FREQUENCY_HZ * t) * fade
    gap = np.zeros(int(rate * 0.4))
    silence = np.zeros(int(rate * seconds))
    program = np.concatenate((mark, gap, space, gap, silence))
    print(f"playing calibration tones at amplitude {args.amplitude} ...")
    recording = _play_and_record(
        program,
        rate,
        input_device=args.input_device,
        output_device=args.output_device,
        exclusive=args.exclusive,
    )
    # Locate the mark onset by energy so output latency does not matter.
    window = rate // 100
    envelope = np.convolve(np.abs(recording), np.ones(window) / window, mode="same")
    floor = float(np.median(envelope[: int(rate * 0.15)])) if recording.size > rate else 0.0
    onset_candidates = np.flatnonzero(envelope > max(4 * floor, 0.002))
    onset = int(onset_candidates[0]) / rate if onset_candidates.size else 0.2
    mark_rec = _segment(recording, rate, onset + 0.15, onset + seconds - 0.15)
    space_start = onset + seconds + 0.4
    space_rec = _segment(recording, rate, space_start + 0.15, space_start + seconds - 0.15)
    quiet_start = space_start + seconds + 0.4
    quiet_rec = _segment(recording, rate, quiet_start + 0.15, quiet_start + seconds - 0.15)
    mark_early = _segment(recording, rate, onset + 0.05, onset + 0.25)
    mark_late = _segment(recording, rate, onset + seconds - 0.25, onset + seconds - 0.05)

    mark_amp = _tone_amplitude(mark_rec, rate, MARK_FREQUENCY_HZ)
    space_amp = _tone_amplitude(space_rec, rate, SPACE_FREQUENCY_HZ)
    harmonic = _tone_amplitude(mark_rec, rate, 2 * MARK_FREQUENCY_HZ)
    fade_db = _db(
        _tone_amplitude(mark_late, rate, MARK_FREQUENCY_HZ)
        / max(_tone_amplitude(mark_early, rate, MARK_FREQUENCY_HZ), 1e-12)
    )
    report: dict[str, Any] = {
        "measured_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "sample_rate": rate,
        "tx_amplitude": args.amplitude,
        "input_device": args.input_device,
        "output_device": args.output_device,
        "wasapi_exclusive": args.exclusive,
        "peak_abs": round(float(np.max(np.abs(recording))) if recording.size else 0.0, 4),
        "mark_amplitude": round(mark_amp, 5),
        "space_amplitude": round(space_amp, 5),
        "twist_db": round(_db(mark_amp / max(space_amp, 1e-12)), 2),
        "mark_2nd_harmonic_db": round(_db(harmonic / max(mark_amp, 1e-12)), 2),
        "mark_fade_db": round(fade_db, 2),
        "noise_floor_rms": round(
            float(np.sqrt(np.mean(quiet_rec**2))) if quiet_rec.size else 0.0, 6
        ),
        "room_170_850_hz_rms": round(_band_rms(quiet_rec, rate, 170, 850), 6),
        "noise_in_band_1000_2500_hz_rms": round(_band_rms(quiet_rec, rate, 1000, 2500), 6),
    }
    in_band_noise = max(report["noise_in_band_1000_2500_hz_rms"], 1e-9)
    report["mark_snr_db"] = round(_db(mark_amp / np.sqrt(2) / in_band_noise), 1)
    report["space_snr_db"] = round(_db(space_amp / np.sqrt(2) / in_band_noise), 1)

    advice: list[str] = []
    if report["peak_abs"] >= 0.8:
        advice.append(
            "Peak level is near full scale; frame bursts will clip. Lower the speaker "
            "volume or --amplitude until peak_abs is below about 0.5."
        )
    if report["mark_2nd_harmonic_db"] > -25:
        advice.append(
            "Strong 2400 Hz harmonic (speaker distortion, near the 2200 Hz space tone): "
            "lower the volume."
        )
    if report["mark_fade_db"] < -6:
        advice.append(
            "Mark tone fades while it plays: OS voice processing is active. Turn off audio "
            "enhancements / noise suppression, try --exclusive, or use a USB microphone."
        )
    if max(mark_amp, space_amp) < 0.02:
        advice.append("Signal is weak: raise the volume or move the transmitter closer.")
    if min(report["mark_snr_db"], report["space_snr_db"]) < 15:
        advice.append("In-band SNR below 15 dB: reduce room noise or move closer.")
    if abs(report["twist_db"]) > 6:
        advice.append(
            f"Twist {report['twist_db']} dB: the soft fallback compensates, "
            "but a flatter speaker or a different position helps."
        )
    if not advice:
        advice.append("Channel looks usable. Record a corpus next.")
    report["advice"] = advice
    print(json.dumps(report, indent=2))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        _write_wav(args.out.with_suffix(".wav"), recording, rate)
    return 0


def record(args: argparse.Namespace) -> int:
    rate = args.sample_rate
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    keys = _keys()
    manifest: dict[str, Any] = {
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "mode": "play" if args.play else "listen",
        "sample_rate": rate,
        "amplitude": args.amplitude,
        "repeat": args.repeat,
        "input_device": args.input_device,
        "output_device": args.output_device,
        "wasapi_exclusive": args.exclusive,
        "conditions": args.conditions,
        "files": [],
    }
    if args.play:
        for index in range(args.frames):
            seq = args.start_seq + index
            raw = _command(seq, keys)
            burst = _burst(raw, rate, args.amplitude, args.repeat, args.gap_ms / 1000.0)
            recording = _play_and_record(
                burst,
                rate,
                input_device=args.input_device,
                output_device=args.output_device,
                exclusive=args.exclusive,
            )
            name = f"trial-{index + 1:02d}-seq{seq}.wav"
            _write_wav(out_dir / name, recording, rate)
            manifest["files"].append({"file": name, "seq": seq, "expected_hex": raw.hex()})
            print(f"  {name}: {recording.size / rate:.2f} s, peak {np.max(np.abs(recording)):.3f}")
    else:
        print(f"recording {args.listen_seconds:.0f} s; transmit from /ground now ...")
        recording = _record_only(
            args.listen_seconds, rate, input_device=args.input_device, exclusive=args.exclusive
        )
        name = f"listen-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.wav"
        _write_wav(out_dir / name, recording, rate)
        manifest["files"].append({"file": name, "seq": None, "expected_hex": None})
        print(f"  {name}: {recording.size / rate:.2f} s, peak {np.max(np.abs(recording)):.3f}")
    manifest_path = out_dir / MANIFEST
    if manifest_path.exists() and not args.play:
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["files"] = previous.get("files", []) + manifest["files"]
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {manifest_path}")
    return 0


def simulate(args: argparse.Namespace) -> int:
    from tests.channel_sim import LAPTOP_SELF_TEST, Channel, impair  # noqa: PLC0415

    rate = args.sample_rate
    channel = LAPTOP_SELF_TEST
    if args.twist_db is not None or args.snr_db is not None:
        channel = Channel(
            twist_db=args.twist_db if args.twist_db is not None else LAPTOP_SELF_TEST.twist_db,
            echoes=LAPTOP_SELF_TEST.echoes,
            hum_amplitude=LAPTOP_SELF_TEST.hum_amplitude,
            drive=LAPTOP_SELF_TEST.drive,
            snr_db=args.snr_db if args.snr_db is not None else LAPTOP_SELF_TEST.snr_db,
            gain=LAPTOP_SELF_TEST.gain,
        )
    keys = _keys()
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    files: list[dict[str, Any]] = []
    for index in range(args.frames):
        seq = args.start_seq + index
        raw = _command(seq, keys)
        pcm = impair(
            _burst(raw, rate, args.amplitude, args.repeat, args.gap_ms / 1000.0),
            rate,
            channel,
            np.random.default_rng(args.seed + index),
        )
        name = f"sim-{index + 1:02d}-seq{seq}.wav"
        _write_wav(out_dir / name, np.clip(pcm, -1.0, 1.0), rate)
        files.append({"file": name, "seq": seq, "expected_hex": raw.hex()})
    manifest = {
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "mode": "simulate",
        "sample_rate": rate,
        "amplitude": args.amplitude,
        "repeat": args.repeat,
        "channel": {
            "twist_db": channel.twist_db,
            "echoes": list(channel.echoes),
            "hum_amplitude": channel.hum_amplitude,
            "drive": channel.drive,
            "snr_db": channel.snr_db,
            "gain": channel.gain,
        },
        "files": files,
    }
    (out_dir / MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(files)} simulated bursts to {out_dir}")
    return 0


# ---------------------------------------------------------------- analysis


def _run_receiver(pcm: NDArray[np.float64], rate: int, soft_fallback: bool) -> list[Any]:
    receiver = StreamingReceiver(
        DemodulatorConfig(sample_rate=rate), SourceKind.WAV, soft_fallback=soft_fallback
    )
    events: list[Any] = []
    block = rate // 10
    for start in range(0, pcm.size, block):
        events.extend(receiver.feed(pcm[start : start + block]))
    events.extend(receiver.flush())
    return events


def _bit_errors(soft_bits: NDArray[np.float64], expected: bytes) -> list[int]:
    truth = np.array([(byte >> bit) & 1 for byte in expected for bit in range(8)], dtype=bool)
    wrong = np.flatnonzero((soft_bits > 0) != truth)
    return sorted({int(index) // 8 for index in wrong})


def analyze_file(path: Path, expected_hex: str | None, keys: KeyMaterial) -> dict[str, Any]:
    rate, pcm = _read_wav(path)
    expected = bytes.fromhex(expected_hex) if expected_hex else None
    row: dict[str, Any] = {
        "file": path.name,
        "duration_s": round(pcm.size / rate, 3),
        "peak_abs": round(float(np.max(np.abs(pcm))) if pcm.size else 0.0, 4),
    }
    strict = _run_receiver(pcm, rate, soft_fallback=False)
    robust = _run_receiver(pcm, rate, soft_fallback=True)

    def outcome(events: Sequence[Any]) -> tuple[bool, list[str], str | None]:
        candidates = [event for event in events if isinstance(event, CandidateEvent)]
        method = next(
            (event.recovery.method.value for event in candidates if event.recovery is not None),
            None,
        )
        raws = [event.raw for event in candidates]
        if expected is not None:
            ok = expected in raws
        else:
            ok = any(validate_frame(raw, keys, 0).accepted for raw in raws)
        return ok, [raw.hex() for raw in raws], method

    row["strict_ok"], _, _ = outcome(strict)
    row["robust_ok"], candidates, row["robust_method"] = outcome(robust)
    row["candidates"] = len(candidates)
    row["duplicates"] = sum(isinstance(event, DuplicateEvent) for event in robust)
    if expected is None and candidates:
        row["candidate_hex"] = candidates

    config = DemodulatorConfig(sample_rate=rate)
    failure = demodulate(pcm, config, source_kind=SourceKind.WAV).diagnostics.failure
    transition = failure.transition_guess if failure is not None else None
    row["strict_failure"] = None if failure is None else failure.code.value
    if transition is not None:
        soft = soft_decode(pcm, config, transition)
        if soft is not None:
            row["twist_db"] = round(soft.twist_db, 2)
            row["sync_score"] = round(soft.sync_score, 3)
            row["framing_errors"] = soft.framing_errors
            if expected is not None:
                row["soft_error_bytes"] = _bit_errors(soft.soft_bits, expected)
    mark = _tone_amplitude(pcm, rate, MARK_FREQUENCY_HZ)
    row["harmonic_2400_vs_1200_db"] = round(
        _db(_tone_amplitude(pcm, rate, 2 * MARK_FREQUENCY_HZ) / max(mark, 1e-12)), 2
    )
    row["space_vs_mark_db"] = round(
        _db(_tone_amplitude(pcm, rate, SPACE_FREQUENCY_HZ) / max(mark, 1e-12)), 2
    )
    return row


def analyze(args: argparse.Namespace) -> int:
    keys = _keys()
    targets: list[tuple[Path, str | None]] = []
    for item in args.paths:
        path = Path(item)
        if path.is_dir():
            manifest_path = path / MANIFEST
            if manifest_path.exists():
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                targets.extend(
                    (path / entry["file"], entry.get("expected_hex")) for entry in manifest["files"]
                )
            else:
                targets.extend((wav, None) for wav in sorted(path.glob("*.wav")))
        else:
            targets.append((path, None))
    rows = [analyze_file(path, expected, keys) for path, expected in targets]
    total = len(rows)
    strict_ok = sum(row["strict_ok"] for row in rows)
    robust_ok = sum(row["robust_ok"] for row in rows)
    header = (
        f"{'file':34} {'strict':>6} {'robust':>6} {'method':>15} {'twist':>6} {'h2':>7} err bytes"
    )
    print(header)
    print("-" * len(header))
    for row in rows:
        print(
            f"{row['file'][:34]:34} {str(row['strict_ok']):>6} {str(row['robust_ok']):>6} "
            f"{str(row.get('robust_method') or '-'):>15} {str(row.get('twist_db', '-')):>6} "
            f"{row['harmonic_2400_vs_1200_db']:>7} {row.get('soft_error_bytes', '-')}"
        )
    summary = {
        "analyzed_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "files": total,
        "strict_accepted": strict_ok,
        "robust_accepted": robust_ok,
        "rows": rows,
    }
    print(f"\nstrict decoder: {strict_ok}/{total}   with soft fallback: {robust_ok}/{total}")
    if args.out:
        args.out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {args.out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def audio_options(command: argparse.ArgumentParser) -> None:
        command.add_argument("--sample-rate", type=int, choices=(44100, 48000), default=48000)
        command.add_argument("--input-device", type=int, default=None)
        command.add_argument("--output-device", type=int, default=None)
        command.add_argument(
            "--exclusive",
            action="store_true",
            help="open the microphone in WASAPI exclusive mode (bypasses the shared-mode mixer)",
        )

    cal = sub.add_parser("calibrate", help="measure the speaker -> microphone channel")
    audio_options(cal)
    cal.add_argument("--amplitude", type=float, default=0.4)
    cal.add_argument("--out", type=Path, default=None, help="write report JSON (+ recording WAV)")
    cal.set_defaults(handler=calibrate)

    rec = sub.add_parser("record", help="record raw microphone audio into a corpus")
    audio_options(rec)
    mode = rec.add_mutually_exclusive_group(required=True)
    mode.add_argument("--play", action="store_true", help="play signed bursts from this machine")
    mode.add_argument(
        "--listen-seconds", type=float, help="record only, for an external transmitter"
    )
    rec.add_argument("--out-dir", type=Path, required=True)
    rec.add_argument("--frames", type=int, default=20)
    rec.add_argument("--start-seq", type=int, default=1000)
    rec.add_argument("--amplitude", type=float, default=0.4)
    rec.add_argument("--repeat", type=int, default=1)
    rec.add_argument("--gap-ms", type=float, default=300.0)
    rec.add_argument("--conditions", default="", help="free text: device, distance, settings")
    rec.set_defaults(handler=record)

    sim = sub.add_parser("simulate", help="write impaired WAVs from the channel model")
    sim.add_argument("--out-dir", type=Path, required=True)
    sim.add_argument("--frames", type=int, default=20)
    sim.add_argument("--start-seq", type=int, default=1000)
    sim.add_argument("--sample-rate", type=int, choices=(44100, 48000), default=48000)
    sim.add_argument("--amplitude", type=float, default=0.6)
    sim.add_argument("--repeat", type=int, default=1)
    sim.add_argument("--gap-ms", type=float, default=300.0)
    sim.add_argument("--twist-db", type=float, default=None)
    sim.add_argument("--snr-db", type=float, default=None)
    sim.add_argument("--seed", type=int, default=2026)
    sim.set_defaults(handler=simulate)

    ana = sub.add_parser("analyze", help="decode a corpus with strict and soft decoders")
    ana.add_argument("paths", nargs="+")
    ana.add_argument("--out", type=Path, default=None)
    ana.set_defaults(handler=analyze)

    args = parser.parse_args(argv)
    if getattr(args, "repeat", 1) < 1:
        parser.error("--repeat must be at least 1")
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
