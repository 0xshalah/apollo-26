# Blog draft (skeleton) — publish on dev.to, Medium, or Hashnode

Rules for the Bonus Blog Prize: public, on a third-party platform, published during the submission period, and it must say it was written as part of the Kiroween 2026 hackathon.

The facts below are checked against the repository. The parts marked **YOU** are yours to write; do not paste generated text there.

---

## Title ideas
- "I let an AI agent fire a 1969 rocket engine. Here's what stopped it."
- "Agent safety for physical systems, tested on an Apollo guidance computer"

## Opening (YOU)
Why you picked this project. What worried you about giving an agent buttons on a real machine.

## What I built (facts, rewrite in your voice)
- A browser ground station signs a 34-byte command and plays it as 300-baud Bell-202 modem audio.
- A Python daemon on the laptop hears it, checks CRC, HMAC, and sequence number, and hands it to a Kiro agent over MCP.
- The agent plans key presses for an emulated Apollo DSKY. A safety gate in code allows only the canonical key sequence, and a P40 engine burn also needs a separate, single-use operator AUTH.
- Written for the Kiroween 2026 hackathon (Frankenstein category).

## The moment it worked (YOU)
Describe the first time the gate refused the burn with `AUTH_REQUIRED`, then executed 36/36 keys after AUTH.

## What broke (facts)
- 0 of 20 frames decoded over the air at first: Windows voice processing erased the steady 1200 Hz preamble.
- With enhancements off, still 3 of 20, because one ambiguous symbol in 340 dropped a frame.
- A soft-decision decoder plus three repeated bursts brought the live result to 19 of 20 on one laptop. CRC only picks a candidate; HMAC still decides.
- Three bugs appeared only with the real agent: an inspection window shorter than the agent's own latency, a Windows clock that made 100 ms gaps 93 ms, and an AUTH window too short for a human.

## How Kiro changed the way I work (YOU)
Pick one or two: specs that caught a design flaw before code, steering that kept numbers honest, the hook that blocked the agent's own shell, MCP as the safety boundary. Say what you would have done without it.

## Links
- Repository: https://github.com/0xshalah/apollo-26
- Landing page: https://0xshalah.github.io/apollo-26/
- Video: (YouTube link)
