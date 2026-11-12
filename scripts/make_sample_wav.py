"""Write ``web-dashboard/public/sample_burst.wav``: one authenticated COMMAND burst.

Default frame: seq 1, V25 N81 (load R1 azimuth 12.50 deg, R2 elevation 4.20 deg,
R3 delta-v 312.0 ft/s), signed with the public demo link key from
``contracts/acoustic-frame-v1.md`` (override via APOLLO26_LINK_KEY).

Decode it with:
    apollo26 --provision-sequence 0      # first run only (explicit, archives old inbox)
    apollo26 --input web-dashboard/public/sample_burst.wav

Critical P40 + operator AUTH (signed with APOLLO26_OPERATOR_KEY or the demo key):
    python scripts/make_sample_wav.py --out p40.wav --seq 2 --verb 37 --noun 0 --program 40
    python scripts/make_sample_wav.py --out auth.wav --seq 3 --auth-ref 2
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from acoustic.audio import encode_wav_bytes  # noqa: E402
from acoustic.frame import AuthFrame, CommandFrame, encode_frame  # noqa: E402
from acoustic.modem import modulate  # noqa: E402

DEMO_LINK_KEY = "apollo26-link-demo-key-v1"
DEMO_OPERATOR_KEY = "apollo26-operator-demo-key-v1"


def build_burst(
    frame: CommandFrame | AuthFrame, key: bytes, sample_rate: int, lead_s: float, tail_s: float
) -> np.ndarray:
    pcm = modulate(encode_frame(frame, key), sample_rate, amplitude=0.6)
    lead = np.zeros(int(sample_rate * lead_s))
    tail = np.zeros(int(sample_rate * tail_s))
    return np.concatenate((lead, pcm, tail))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=ROOT / "web-dashboard" / "public" / "sample_burst.wav")
    parser.add_argument("--seq", type=int, default=1)
    parser.add_argument("--verb", type=int, default=25)
    parser.add_argument("--noun", type=int, default=81)
    parser.add_argument("--program", type=int, default=0)
    parser.add_argument("--r1", type=int, default=1250, help="centidegrees")
    parser.add_argument("--r2", type=int, default=420, help="centidegrees")
    parser.add_argument("--delta-v", type=int, default=3120, help="tenths of ft/s")
    parser.add_argument("--critical", action="store_true")
    parser.add_argument(
        "--auth-ref",
        type=int,
        metavar="COMMAND_SEQ",
        help="write an operator AUTH frame (seq=--seq) referencing COMMAND_SEQ instead of a COMMAND",
    )
    parser.add_argument("--sample-rate", type=int, choices=(44100, 48000), default=48000)
    args = parser.parse_args(argv)

    frame: CommandFrame | AuthFrame
    if args.auth_ref is not None:
        key = os.environ.get("APOLLO26_OPERATOR_KEY", DEMO_OPERATOR_KEY).encode("utf-8")
        frame = AuthFrame(seq=args.seq, ref_seq=args.auth_ref)
    else:
        key = os.environ.get("APOLLO26_LINK_KEY", DEMO_LINK_KEY).encode("utf-8")
        frame = CommandFrame(
            seq=args.seq,
            critical=args.critical,
            verb=args.verb,
            noun=args.noun,
            program=args.program,
            r1_centidegrees=args.r1,
            r2_centidegrees=args.r2,
            delta_v_tenths_fps=args.delta_v,
        )
    pcm = build_burst(frame, key, args.sample_rate, lead_s=0.5, tail_s=0.5)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.out.with_name(args.out.name + ".tmp")
    temporary.write_bytes(encode_wav_bytes(pcm, args.sample_rate))
    temporary.replace(args.out)
    print(f"wrote {args.out} ({pcm.size / args.sample_rate:.2f} s, seq={args.seq}, raw={encode_frame(frame, key).hex()})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
