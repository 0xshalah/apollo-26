# Video script — Apollo-26 (target 2:45, hard limit 3:00)

Record the screen at 1080p with system audio on, so the FSK tones are heard. No copyrighted music. Upload to YouTube as public and check the duration is under 3:00.

Before recording:
- Terminal A: `.venv\Scripts\python -m acoustic.daemon --loopback` (stays open).
- Kiro: `apollo26` MCP server enabled; new chat session.
- Browser tab: http://127.0.0.1:8026/console/
- WAVs: `p40.wav` (seq N, V37 P40) and `auth.wav` (seq N+1, `--auth-ref N`) from `scripts/make_sample_wav.py`, with N above the daemon's last accepted seq.

| Time | Screen | Voice-over (say it, don't read the screen) |
| :-- | :-- | :-- |
| 0:00–0:15 | Title over `/console` | "Apollo-26 lets a Kiro agent fly a 1969-style guidance computer, but only through sound, and only through a safety gate written in code." |
| 0:15–0:40 | `/ground`: fill a P40 burn, show the 34-byte frame inspector, play the tones | "The ground station signs a 34-byte frame with a sequence number, an HMAC and a CRC, and plays it as 300-baud Bell-202 audio." |
| 0:40–1:00 | Terminal B: `curl` P40 WAV to `/loopback`; console audit row turns ACCEPTED | "The daemon demodulates and validates every frame. Forged, corrupted or replayed frames never reach the agent." |
| 1:00–1:35 | Kiro chat: ask for Flight Watch; show await → inspect → plan; execute is refused `AUTH_REQUIRED` | "The agent waits over MCP, inspects the AGC, and asks for the canonical key plan. A burn is critical, so the gate refuses it without operator authorization." |
| 1:35–2:05 | `curl` AUTH WAV; agent awaits AUTH, re-plans, approve execute; DSKY shows P40, R1–R3 | "The operator sends a separate AUTH frame bound to that sequence number. Only then can the agent press the 36 keys, and the DSKY shows P40 with the loaded burn." |
| 2:05–2:30 | `.kiro/` tree: specs, steering, hooks; flash `docs/pbt-report.md` | "Kiro specs drove each subsystem, steering holds the safety rules, a hook locks the agent's shell during flight, and property tests cover the codec, modem and gate." |
| 2:30–2:45 | `docs/metrics.json` / README "Measured so far" | "Everything shown is measured. Loopback decode takes about half a second. Over-the-air decoding on a laptop microphone does not work yet; that is next." |

Do not say "100% secure", "offline", or quote any number that is not in `docs/metrics.json` or `docs/pbt-report.md`.
