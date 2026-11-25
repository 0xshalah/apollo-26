# Video script: Apollo-26 (target 2:45, hard limit 3:00)

Record the screen at 1080p with system audio on, so the FSK tones are heard. No copyrighted music. Upload to YouTube as public and check the duration is under 3:00.

Before recording:
- Windows audio enhancements off for the microphone (run `scripts\acoustic_lab.py calibrate` first; `peak_abs` below about 0.8).
- Terminal A: `.venv\Scripts\python -m acoustic.daemon --device <mic index>` (stays open), so the burst is heard over the air.
- Kiro: `apollo26` MCP server enabled; new chat session.
- Browser tab 1: http://127.0.0.1:8026/ground/ (same laptop's speaker, repeats 3×).
- Browser tab 2: http://127.0.0.1:8026/console/
- Browser tab 3: http://127.0.0.1:8026/demo/ (for the 2:05 abuse cuts; reset the mission first).
- Backup: `p40.wav` and `auth.wav` from `scripts/make_sample_wav.py --repeat 3` and Terminal B ready with `curl` to `/loopback`, in case the room is noisy (TASK 4.10). If you use the backup, say so on screen.
- The agent part takes about 80 s live. Cut the waiting and caption it "sped up".

| Time | Screen | Voice-over (say it, don't read the screen) |
| :-- | :-- | :-- |
| 0:00–0:20 | Title card, then `/console` | "AI agents are getting buttons on real machines, like robots, lab gear, and industrial controllers. The safety rule is usually one sentence in a prompt. Apollo-26 tests a different idea: the agent orchestrates, and code decides." |
| 0:20–0:35 | DSKY close-up on `/console` | "Our test bench is a 1969 Apollo guidance computer. It has a real control panel, a critical action in the P40 engine burn, and an input channel with no internet at all, only sound." |
| 0:35–1:00 | `/ground`: fill a P40 burn, show the 34-byte frame inspector, press transmit, tones audible; console audit row turns ACCEPTED | "The ground station signs a 34-byte frame and plays it as 300-baud modem audio. The laptop hears it, checks CRC, HMAC and the sequence number, and only then hands it to the agent." |
| 1:00–1:35 | Kiro chat: ask for Flight Watch; await → inspect → plan; execute refused `AUTH_REQUIRED` | "Kiro waits over MCP, reads the computer's state, and asks for the canonical key plan. A burn is critical, so the safety gate, which is code, refuses to run it." |
| 1:35–2:05 | `/ground` AUTH for that seq; agent awaits AUTH, re-plans, approve execute; DSKY shows P40, R1 to R3 | "The operator sends a separate AUTH, bound to that one command and usable once. Only then can the agent press exactly these 36 keys." |
| 2:05–2:25 | Quick cuts in the browser demo (`/demo`, caption "browser simulation"): Replay last frame → `REPLAY`; Execute tampered plan → `PLAN_MISMATCH` | "Replay the burst and it is rejected. Change one key in the plan and it is refused. Each layer fails closed, and you can try every one of these in the browser demo, no install." |
| 2:25–2:45 | `.kiro/` tree: specs, steering, hooks; `docs/evidence-matrix.md` | "Kiro specs drove each subsystem, steering holds the safety rules, a hook locks the agent's shell during flight, and property tests cover the codec, modem and gate. Over the air we measured 19 of 20 frames on one laptop. The phone test is next." |

Do not say "100% secure", "offline", or quote any number that is not in `docs/metrics.json`, `docs/pbt-report.md`, or `docs/evidence-matrix.md`.
