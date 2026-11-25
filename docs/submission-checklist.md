# Submission checklist (deadline 4 Dec 2026, 14:00 PT = 5 Dec 05:00 WIB; target 3 Dec)

## Repository
- [ ] Push this folder to https://github.com/0xshalah/apollo-26 (public).
- [ ] MIT license shows in the repository's About section.
- [ ] `.kiro/` is committed (specs, steering, hooks, settings, agents). It is not in `.gitignore`.
- [ ] `corpus/**/*.wav`, `.env`, and `aturan.md` stay out of git (already in `.gitignore`).
- [ ] Rebuild GitHub Pages so `/demo` exists and `/ground` sends 3× repeats: `scripts\deploy_pages.cmd`. Then open https://0xshalah.github.io/apollo-26/demo/ and click through it once.

## Video (under 3:00, public on YouTube)
Script: `docs/video-script.md`. Record it yourself; judges watch only the first three minutes.
1. Windows audio enhancements off; run `scripts\acoustic_lab.py calibrate --amplitude 0.4` and check `peak_abs` < 0.8.
2. Start the daemon on the microphone in your own terminal, open `/ground` and `/console` from `http://127.0.0.1:8026/`.
3. In Kiro, pick the **flight-director** agent and say "start Flight Watch".
4. Record with system audio on (Xbox Game Bar: Win+Alt+R, or OBS). No copyrighted music.
5. **Backup take (TASK 4.10):** record the same run with `--loopback` and the WAVs from `scripts/make_sample_wav.py --repeat 3`. If the final video uses it, say "loopback" on screen.
6. Cut the agent's waiting time and caption it "sped up".

## Devpost form
- Category: **Frankenstein**.
- Text: `docs/devpost.md`.
- Kiro write-up: `docs/kiro-writeup.md`.
- Working app URL: https://0xshalah.github.io/apollo-26/demo/ (browser demo, no install), plus the landing page and `/ground/`; the real daemon runs locally, instructions in README.
- Disclose pre-existing work: none, except the archived mockups in `docs/archive/mockups/` (check their creation dates; if earlier than 30 Oct, mention them).
- Bonus: Best Demo is automatic. Add the blog and social URLs below if you post them.

## Blog (Bonus Blog Prize) and social post (Social Blitz)
Drafts: `docs/blog-draft.md` and `docs/social-draft.md`. Both have sections marked **YOU** that must be written in your own words; the Social Blitz judges score original thoughts over AI writing. Publish during the submission period, start the social post with `#KiroweenHackathon26`, and say in the blog that it is written for the Kiroween 2026 hackathon.
