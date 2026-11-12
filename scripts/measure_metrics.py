"""Measure Apollo-26 daemon metrics on this machine and merge them into docs/metrics.json.

What is measured (nothing is estimated or copied from targets):

* ``resources_idle``: RSS / private memory and CPU of the real daemon process
  while it listens to the default microphone with no signal (``--idle-seconds``).
* ``acoustic_self_test``: ``--frames`` authenticated COMMAND frames played through
  the default speaker and captured by the default microphone of the same machine
  (over the air, a few centimetres). Per frame: accepted / rejected / missing, and
  latency from the first preamble sample leaving the output stream to the daemon's
  ``received_at`` timestamp. This is NOT the 0.5 m phone trial (TASK 2.11).
* ``resources_during_decode``: CPU and peak memory while the self-test runs.

The daemon runs in an isolated telemetry directory under ``telemetry/state/`` on
ports 18026/18027, so the operator's normal state and sequence are untouched.

    python scripts/measure_metrics.py --frames 20 --idle-seconds 30
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import psutil

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from acoustic.audio import encode_wav_bytes  # noqa: E402
from acoustic.clock import parse_timestamp  # noqa: E402
from acoustic.config import load_key_material, merged_environment  # noqa: E402
from acoustic.frame import CommandFrame, encode_frame  # noqa: E402
from acoustic.modem import modulate  # noqa: E402

SAMPLE_RATE = 48_000
WEB_PORT = 18026
RPC_PORT = 18027
LEAD_S = 0.3
TAIL_S = 0.4
DECODE_WAIT_S = 4.0


def _start_daemon(
    telemetry: Path, device: str | None, *, loopback: bool = False
) -> tuple[subprocess.Popen[str], list[str]]:
    command = [
        sys.executable, "-m", "acoustic.daemon",
        "--telemetry-dir", str(telemetry),
        "--port", str(WEB_PORT), "--rpc-port", str(RPC_PORT),
        "--test-summary", str(telemetry / "no-summary.json"),
    ]  # fmt: skip
    if loopback:
        command.append("--loopback")
    else:
        command += ["--sample-rate", str(SAMPLE_RATE)]
        if device is not None:
            command += ["--device", device]
    process = subprocess.Popen(
        command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
    )
    lines: list[str] = []

    def pump() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            lines.append(line.rstrip())

    threading.Thread(target=pump, daemon=True).start()
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if any("daemon ready" in line for line in lines):
            return process, lines
        if process.poll() is not None:
            break
        time.sleep(0.1)
    process.kill()
    raise RuntimeError("daemon did not become ready:\n" + "\n".join(lines[-20:]))


def _daemon_process(launcher_pid: int) -> psutil.Process:
    """The venv launcher on Windows spawns the real interpreter as a child."""

    launcher = psutil.Process(launcher_pid)
    for child in launcher.children(recursive=True):
        if "acoustic.daemon" in " ".join(child.cmdline()):
            return child
    return launcher


def _memory(process: psutil.Process) -> dict[str, float]:
    info = process.memory_info()
    result = {"rss_mb": round(info.rss / 2**20, 1)}
    for name in ("private", "peak_wset"):
        if hasattr(info, name):
            result[f"{name}_mb"] = round(getattr(info, name) / 2**20, 1)
    return result


def _cpu_window(process: psutil.Process, seconds: float) -> dict[str, float]:
    process.cpu_percent(None)
    samples = []
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        time.sleep(1.0)
        samples.append(process.cpu_percent(None))
    cores = psutil.cpu_count() or 1
    mean = statistics.fmean(samples) if samples else 0.0
    return {
        "seconds": seconds,
        "mean_percent_of_one_core": round(mean, 2),
        "max_percent_of_one_core": round(max(samples, default=0.0), 2),
        "mean_percent_of_machine": round(mean / cores, 2),
        "logical_cpus": cores,
    }


def _acoustic_trial(
    telemetry: Path, process: psutil.Process, frames: int, amplitude: float, link_key: bytes
) -> tuple[dict[str, Any], dict[str, Any]]:
    import sounddevice as sd  # noqa: PLC0415 - hardware boundary

    inbox = telemetry / "inbox"
    rejected_dir = telemetry / "rejected"
    results: list[dict[str, Any]] = []
    cpu_samples: list[float] = []
    peak_rss = 0.0
    process.cpu_percent(None)
    for seq in range(1, frames + 1):
        frame = CommandFrame(
            seq=seq, critical=False, verb=25, noun=81, program=0,
            r1_centidegrees=1250, r2_centidegrees=420, delta_v_tenths_fps=3120,
        )  # fmt: skip
        tone = modulate(encode_frame(frame, link_key), SAMPLE_RATE, amplitude=amplitude)
        pcm = np.concatenate(
            (np.zeros(int(SAMPLE_RATE * LEAD_S)), tone, np.zeros(int(SAMPLE_RATE * TAIL_S)))
        ).astype(np.float32)
        rejected_before = {p.name for p in rejected_dir.glob("*.json")}
        started = time.time()
        sd.play(pcm, SAMPLE_RATE)
        output_latency = float(sd.get_stream().latency)
        first_tone = started + LEAD_S + output_latency
        sd.wait()
        target = inbox / f"{seq}.json"
        deadline = time.time() + DECODE_WAIT_S
        while time.time() < deadline and not target.exists():
            time.sleep(0.02)
        cpu_samples.append(process.cpu_percent(None))
        peak_rss = max(peak_rss, process.memory_info().rss / 2**20)
        entry: dict[str, Any] = {"seq": seq, "air_time_s": round(tone.size / SAMPLE_RATE, 3)}
        if target.exists():
            record = json.loads(target.read_text(encoding="utf-8"))
            received = parse_timestamp(record["received_at"]).timestamp()
            entry.update(
                outcome="ACCEPTED",
                latency_first_tone_to_received_s=round(received - first_tone, 3),
                snr_db=record["source"].get("snr_db"),
                frequency_deviation_hz=record["source"].get("frequency_deviation_hz"),
            )
        else:
            new_rejects = sorted({p.name for p in rejected_dir.glob("*.json")} - rejected_before)
            reasons = []
            for name in new_rejects:
                try:
                    reasons.append(json.loads((rejected_dir / name).read_text(encoding="utf-8")).get("reason"))
                except (OSError, json.JSONDecodeError):
                    reasons.append("UNREADABLE")
            entry.update(outcome="REJECTED" if reasons else "NOT_DETECTED", reasons=reasons)
        results.append(entry)
        print(f"seq {seq}: {entry}", flush=True)
        time.sleep(0.3)

    accepted = [r for r in results if r["outcome"] == "ACCEPTED"]
    latencies = [r["latency_first_tone_to_received_s"] for r in accepted]
    trial = {
        "status": "MEASURED",
        "path": "same-laptop speaker -> microphone over the air (not the 0.5 m phone trial)",
        "frames_sent": frames,
        "frames_accepted": len(accepted),
        "frames_rejected": sum(r["outcome"] == "REJECTED" for r in results),
        "frames_not_detected": sum(r["outcome"] == "NOT_DETECTED" for r in results),
        "amplitude": amplitude,
        "output_device": sd.query_devices(kind="output")["name"],
        "input_device": sd.query_devices(kind="input")["name"],
        "latency_first_tone_to_received_s": {
            "min": min(latencies, default=None),
            "median": statistics.median(latencies) if latencies else None,
            "max": max(latencies, default=None),
        },
        "latency_note": "first_tone = playback call time + lead silence + PortAudio output latency; includes the frame's air time (preamble + 34 bytes at 300 baud, 8N1).",
        "per_frame": results,
    }
    cores = psutil.cpu_count() or 1
    decode = {
        "status": "MEASURED",
        "mean_percent_of_one_core": round(statistics.fmean(cpu_samples), 2) if cpu_samples else None,
        "max_percent_of_one_core": round(max(cpu_samples, default=0.0), 2),
        "mean_percent_of_machine": round(statistics.fmean(cpu_samples) / cores, 2) if cpu_samples else None,
        "peak_rss_mb": round(peak_rss, 1),
    }
    return trial, decode


def _loopback_trial(telemetry: Path, process: psutil.Process, frames: int, link_key: bytes) -> dict[str, Any]:
    """POST each frame's WAV to /loopback and time decode + validation + atomic inbox write.

    The daemon consumes pushed audio faster than real time, so this isolates the
    processing cost. Over-the-air latency = air time (a protocol constant) + this.
    """

    import urllib.request  # noqa: PLC0415

    inbox = telemetry / "inbox"
    rows: list[dict[str, Any]] = []
    cpu_samples: list[float] = []
    peak_rss = 0.0
    air_time = None
    process.cpu_percent(None)
    for seq in range(1, frames + 1):
        frame = CommandFrame(
            seq=seq, critical=False, verb=25, noun=81, program=0,
            r1_centidegrees=1250, r2_centidegrees=420, delta_v_tenths_fps=3120,
        )  # fmt: skip
        tone = modulate(encode_frame(frame, link_key), SAMPLE_RATE, amplitude=0.6)
        air_time = tone.size / SAMPLE_RATE
        # Trailing silence longer than one receiver hop (0.25 s), as a live microphone would supply.
        body = encode_wav_bytes(np.concatenate((tone, np.zeros(int(SAMPLE_RATE * 0.3)))), SAMPLE_RATE)
        request = urllib.request.Request(
            f"http://127.0.0.1:{WEB_PORT}/loopback", data=body, method="POST",
            headers={"Content-Type": "audio/wav"},
        )  # fmt: skip
        posted = time.time()
        with urllib.request.urlopen(request, timeout=10) as response:
            response.read()
        target = inbox / f"{seq}.json"
        deadline = time.time() + 5
        while time.time() < deadline and not target.exists():
            time.sleep(0.005)
        cpu_samples.append(process.cpu_percent(None))
        peak_rss = max(peak_rss, process.memory_info().rss / 2**20)
        if target.exists():
            record = json.loads(target.read_text(encoding="utf-8"))
            received = parse_timestamp(record["received_at"]).timestamp()
            rows.append({"seq": seq, "outcome": record["verdict"], "post_to_received_s": round(received - posted, 4)})
        else:
            rows.append({"seq": seq, "outcome": "NOT_DETECTED"})
        time.sleep(0.2)
    values = [r["post_to_received_s"] for r in rows if "post_to_received_s" in r]
    cores = psutil.cpu_count() or 1
    median = statistics.median(values) if values else None
    return {
        "status": "MEASURED",
        "path": "HTTP POST of a 48 kHz WAV to the daemon's /loopback endpoint (same pipeline as microphone input, no air channel)",
        "frames_sent": frames,
        "frames_accepted": sum(r["outcome"] == "ACCEPTED" for r in rows),
        "processing_s": {"min": min(values, default=None), "median": median, "max": max(values, default=None)},
        "processing_note": "POST start -> daemon received_at; includes WAV parse, FSK demodulation of the whole burst, CRC/HMAC/sequence validation, and atomic inbox write.",
        "air_time_s": round(air_time, 3) if air_time else None,
        "derived_over_air_latency_s": round(air_time + median, 3) if (air_time and median is not None) else None,
        "derived_note": "DERIVED upper estimate, not measured over the air: air time of one frame (preamble + 34 bytes, 8N1, 300 baud) + median loopback processing. Processing already includes the upload and every demodulation pass over the burst; with a live microphone the passes run during the air time, and a frame is decoded at the first 0.25 s hop after its stop bit.",
        "cpu_during_trial": {
            "mean_percent_of_one_core": round(statistics.fmean(cpu_samples), 2) if cpu_samples else None,
            "mean_percent_of_machine": round(statistics.fmean(cpu_samples) / cores, 2) if cpu_samples else None,
        },
        "peak_rss_mb": round(peak_rss, 1),
        "per_frame": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", choices=("acoustic", "loopback"), default="acoustic")
    parser.add_argument("--frames", type=int, default=20)
    parser.add_argument("--idle-seconds", type=float, default=30.0)
    parser.add_argument("--amplitude", type=float, default=0.6)
    parser.add_argument("--device", help="sounddevice input device for the daemon (default: system default)")
    parser.add_argument("--skip-acoustic", action="store_true")
    parser.add_argument("--out", type=Path, default=ROOT / "docs" / "metrics.json")
    args = parser.parse_args(argv)

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    telemetry = ROOT / "telemetry" / "state" / f"metrics-run-{stamp}"
    provision = subprocess.run(
        [sys.executable, "-m", "acoustic.daemon", "--telemetry-dir", str(telemetry), "--provision-sequence", "0"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )  # fmt: skip
    if provision.returncode != 0:
        print(provision.stdout, provision.stderr, file=sys.stderr)
        return 1
    keys = load_key_material(merged_environment(os.environ, ROOT / ".env"))

    launcher, log = _start_daemon(telemetry, args.device, loopback=args.mode == "loopback")
    measured: dict[str, Any] = {}
    try:
        process = _daemon_process(launcher.pid)
        time.sleep(2.0)
        if args.mode == "loopback":
            measured["loopback_processing"] = _loopback_trial(telemetry, process, args.frames, keys.link_key)
            print("loopback:", {k: v for k, v in measured["loopback_processing"].items() if k != "per_frame"}, flush=True)
        else:
            measured["resources_idle"] = {"status": "MEASURED", **_memory(process), **_cpu_window(process, args.idle_seconds)}
            print("idle:", measured["resources_idle"], flush=True)
        if args.mode == "acoustic" and not args.skip_acoustic:
            trial, decode = _acoustic_trial(telemetry, process, args.frames, args.amplitude, keys.link_key)
            measured["acoustic_self_test"] = trial
            measured["resources_during_decode"] = decode
    finally:
        launcher.terminate()
        try:
            launcher.wait(timeout=10)
        except subprocess.TimeoutExpired:
            launcher.kill()
        for child in psutil.Process().children(recursive=True):
            if "acoustic.daemon" in " ".join(child.cmdline()):
                child.kill()

    document: dict[str, Any] = {}
    if args.out.exists():
        document = json.loads(args.out.read_text(encoding="utf-8"))
    document.setdefault("schema_version", "1.0")
    document["environment"] = {
        "measured_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu": platform.processor(),
        "logical_cpus": psutil.cpu_count(),
        "telemetry_dir": str(telemetry.relative_to(ROOT)),
    }
    document.update(measured)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.out.with_name(f".{args.out.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    temporary.replace(args.out)
    (telemetry / "daemon.log").write_text("\n".join(log) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
