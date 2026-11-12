import Link from 'next/link';
import type { ReactNode } from 'react';
import metricsJson from '../../../docs/metrics.json';
import summaryJson from '../../../docs/test-summary.json';
import { Chip, type Tone } from '@/components/Panel';
import { fromHex } from '@/lib/frame';
import { signed5 } from '@/lib/format';
import { evidenceRows, liveRunStages, utcTime, type EvidenceStatus, type MetricsDoc, type TestSummary } from '@/lib/landing-data';
import { BAUD, byteTo8n1, MARK_HZ, SPACE_HZ } from '@/lib/modem';

const metrics = metricsJson as unknown as MetricsDoc;
const summary = summaryJson as TestSummary;
const REPO = 'https://github.com/0xshalah/apollo-26';
const blob = (p: string) => `${REPO}/blob/main/${p}`;
const tree = (p: string) => `${REPO}/tree/main/${p}`;

const NAV = [
  { href: '#how', label: 'How it works' },
  { href: '#gate', label: 'Safety gate' },
  { href: '#evidence', label: 'Evidence' },
  { href: '#kiro', label: 'Built with Kiro' },
  { href: '#faq', label: 'FAQ' },
];

const STATUS_TONE: Record<EvidenceStatus, Tone> = { MEASURED: 'ok', VERIFIED: 'ok', FAILED: 'bad', 'NOT RUN': 'muted' };

function Section({ id, title, lead, children }: { id: string; title: string; lead?: string; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-head`} className="scroll-mt-24 border-t border-rule py-20">
      <div className="mx-auto max-w-[76rem] px-4 sm:px-6">
        <h2 id={`${id}-head`} className="max-w-[28ch] text-[2rem] text-ink sm:text-[2.5rem]">
          {title}
        </h2>
        {lead ? <p className="mt-3 max-w-prose text-[1.0625rem] text-muted">{lead}</p> : null}
        <div className="mt-10">{children}</div>
      </div>
    </section>
  );
}

function ExternalLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a href={href} className="text-cool underline decoration-cool/40 underline-offset-4 hover:decoration-cool">
      {children}
    </a>
  );
}

function LiveRunCard() {
  const p40 = metrics.agent_path_live.p40_critical_with_auth;
  const bytes = fromHex(p40.command_raw_hex);
  const pc = p40.postcondition;
  const stages = liveRunStages(metrics);
  return (
    <figure className="m-0 overflow-hidden rounded-card border border-rule-2 bg-paper-2">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-rule px-4 py-3">
        <figcaption className="text-[0.9375rem] font-medium text-ink">P40 burn, live Kiro run</figcaption>
        <span className="font-mono text-xs text-cool">
          Bell-202 · {MARK_HZ} / {SPACE_HZ} Hz · {BAUD} bd
        </span>
      </div>

      <div className="border-b border-rule bg-paper-3 px-4 py-3">
        <p className="text-xs text-muted">COMMAND frame as received (34 bytes)</p>
        <p className="mt-1 break-all font-mono text-xs text-cool tabular">{p40.command_raw_hex}</p>
        <ol aria-label="First four bytes as 8N1 symbols" className="mt-3 grid grid-cols-4 gap-1 font-mono text-[0.7rem] tabular">
          {Array.from(bytes.subarray(0, 4), (b, i) => {
            const bits = byteTo8n1(b);
            return (
              <li key={i} className="rounded-tag bg-paper-2 px-1.5 py-1 text-center">
                <span className="text-muted">{bits[0]}</span>
                <span className="text-ok">{bits.slice(1, 9).join('')}</span>
                <span className="text-muted">{bits[9]}</span>
              </li>
            );
          })}
        </ol>
      </div>

      <table className="w-full border-collapse text-left text-sm">
        <caption className="sr-only">Stages of the recorded run, seconds after the COMMAND was accepted</caption>
        <thead>
          <tr className="border-b border-rule-2 bg-paper-3 text-xs text-muted">
            <th scope="col" className="px-4 py-2 font-medium">Stage</th>
            <th scope="col" className="px-4 py-2 font-medium">Result</th>
            <th scope="col" className="px-4 py-2 text-right font-medium">Time</th>
          </tr>
        </thead>
        <tbody>
          {stages.map((st, i) => (
            <tr key={st.step} className="border-b border-rule">
              <th scope="row" className="px-4 py-2.5 font-normal text-ink">
                <span className="mr-2 font-mono text-xs text-muted">{i + 1}</span>
                {st.step}
              </th>
              <td className={`px-4 py-2.5 font-mono text-xs ${st.tone === 'bad' ? 'text-bad' : st.tone === 'ok' ? 'text-ok' : 'text-cool'}`}>
                {st.result}
              </td>
              <td className="px-4 py-2.5 text-right font-mono text-xs text-ink-2 tabular">
                {st.atSeconds === null ? '—' : `${st.atSeconds.toFixed(2)} s`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <dl className="grid grid-cols-1 gap-px bg-rule sm:grid-cols-3">
        <div className="bg-paper-2 px-4 py-3">
          <dt className="text-xs text-muted">Controller</dt>
          <dd className="mt-0.5 text-sm text-accent">Kiro Flight Watch</dd>
        </div>
        <div className="bg-paper-2 px-4 py-3">
          <dt className="text-xs text-muted">Critical because</dt>
          <dd className="mt-0.5 font-mono text-xs text-cool">{p40.critical_reasons.join(', ')}</dd>
        </div>
        <div className="bg-paper-2 px-4 py-3">
          <dt className="text-xs text-muted">DSKY after</dt>
          <dd className="mt-0.5 font-mono text-xs text-ok tabular">
            P{pc.program} V{pc.verb} · {signed5(pc.r1)} {signed5(pc.r2)} {signed5(pc.r3)}
          </dd>
        </div>
      </dl>
      <p className="border-t border-rule px-4 py-3 text-xs text-muted">
        Recorded {utcTime(p40.command_received_at)} on 12 Nov 2026, one run. AUTH reached the daemon at once, but the agent had
        not received it yet when it tried to execute, so the safety gate refused. Total {p40.command_to_postcondition_s} s,
        mostly agent model time.
      </p>
    </figure>
  );
}

const PIPELINE = [
  { key: 'TX', title: 'Ground station', body: 'A web page signs a 34-byte frame and plays it as 300-baud Bell-202 audio from a phone or laptop.' },
  { key: 'RX', title: 'Acoustic daemon', body: 'Demodulates sound, then checks sync, CRC, HMAC, replay and ranges. Rejected frames never reach the agent.' },
  { key: 'MCP', title: 'Kiro Flight Watch', body: 'The agent waits for frames, inspects the AGC, and asks for the one canonical key plan for that frame.' },
  { key: 'AGC', title: 'DSKY emulator', body: 'An AGC-faithful subset presses the keys at a 100 ms cadence after the safety gate allows them.' },
];

const SPEC = [
  ['Frame', '34 bytes: type, seq, ref_seq, flags, VERB/NOUN/PROG, R1, R2, delta-v'],
  ['Integrity', 'CRC-16/CCITT-FALSE'],
  ['Authentication', 'HMAC-SHA256 truncated to 64 bits; separate operator key for AUTH'],
  ['Replay', 'Global sequence counter, persisted atomically by the daemon'],
  ['Modem', `Bell-202 FSK, ${MARK_HZ} Hz mark / ${SPACE_HZ} Hz space, ${BAUD} baud, 8N1`],
  ['Command path', 'Daemon, MCP server and emulator listen on 127.0.0.1 only (tested)'],
];

const COMPARE: Array<[string, string]> = [
  ['Safety rules live in the prompt.', 'Rules are code in mcp_server/safety_gate.py, checked again inside the daemon.'],
  ['The model chooses which keys to press.', 'Only the canonical key plan for that exact frame can execute.'],
  ['A critical burn runs if the model decides to.', 'P40 and V37/V34 during P40 need an operator AUTH frame, bound to the seq and single use.'],
  ['State can change between looking and acting.', 'Execute is refused if the AGC changed since the last inspection.'],
  ['The agent can shell out around its tools.', 'A Kiro PreToolUse hook blocks shell tools while Flight Watch is live.'],
];

const CAUGHT = [
  {
    title: 'Every plan was stale',
    body: 'Agent tool calls were 5 to 30 s apart and the inspection window was 5 s. Now 20 s, with the exact AGC state check kept.',
  },
  {
    title: 'Key 2 of 29 rejected',
    body: 'Python 3.12 on Windows times sleeps with a 15.6 ms clock, so 100 ms waits ran 93 ms. Fixed with a high-resolution clock and a real-clock test.',
  },
  {
    title: 'AUTH always expired',
    body: 'A human plus several agent calls never fit in 30 s. The hold window is now 120 s; binding, single use and ordering are unchanged.',
  },
];

const KIRO = [
  { title: 'Specs', body: 'Four specs: EARS requirements, design, tasks. Requirement IDs appear in test names.', href: tree('.kiro/specs') },
  { title: 'Steering', body: 'Allowed and banned claims, module boundaries, Flight Watch rules S-01 to S-07, design tokens.', href: tree('.kiro/steering') },
  { title: 'Hooks', body: 'Shell guard during Flight Watch, fast property tests on save, tests after spec tasks.', href: tree('.kiro/hooks') },
  { title: 'MCP server', body: 'Six Flight Watch tools. execute_dsky_sequence is never auto-approved, enforced by a test.', href: tree('mcp_server') },
  { title: 'Property-based tests', body: 'Hypothesis P1 to P8 and fast-check P9 against shared golden vectors.', href: blob('docs/pbt-report.md') },
  { title: 'Build journal', body: 'What happened during the build, including the bugs the live runs found.', href: blob('docs/kiro-journal.md') },
];

const FAQ: Array<[string, ReactNode]> = [
  [
    'Is the system offline?',
    'The command path is local: daemon, MCP server and emulator bind to 127.0.0.1 only. The Kiro agent itself uses a cloud model, so the laptop is not offline.',
  ],
  [
    'Does it run real Apollo flight software?',
    'No. It is an AGC-faithful subset written for this project: 15-bit ones’ complement words, the DSKY state machine, P00 and a simplified P40, and V25, V34, V37. It does not run Luminary or Colossus.',
  ],
  [
    'Does decoding over the air work?',
    <>
      Not yet. Twenty frames from a laptop speaker into the same laptop’s microphone were not detected, and the phone test has not
      been run. WAV and loopback input go through the same pipeline and work. See <ExternalLink href={blob('docs/metrics.json')}>docs/metrics.json</ExternalLink>.
    </>,
  ],
  [
    'Can someone fake a command?',
    'Not without the link key: frames carry a truncated HMAC and a sequence number, so forged, corrupted and replayed frames are rejected in tests. Sound can still be overheard or jammed, and payloads are not encrypted. The demo keys are public.',
  ],
  [
    'How do I try it without a microphone?',
    'Run the daemon with the sample WAV (below), open the mission console, then connect Kiro to the MCP server and start Flight Watch.',
  ],
];

export function Landing() {
  const rows = evidenceRows(metrics, summary);
  return (
    <>
      <header className="sticky top-0 z-40 px-3 pt-3 sm:px-6">
        <div className="mx-auto flex max-w-[76rem] items-center gap-4 rounded-card border border-rule-2 bg-paper-3/90 px-3 py-2 backdrop-blur">
          <Link href="/" className="inline-flex min-h-11 items-center gap-2 px-1 text-[1.0625rem] font-medium tracking-tight text-ink">
            <span aria-hidden className="font-mono text-accent">
              {'///'}
            </span>
            Apollo-26
          </Link>
          <nav aria-label="Sections" className="hidden flex-1 items-center gap-1 lg:flex">
            {NAV.map((n) => (
              <a key={n.href} href={n.href} className="inline-flex min-h-11 items-center rounded-pill px-3 text-sm text-ink-2 hover:bg-paper-2 hover:text-ink">
                {n.label}
              </a>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <Link href="/console/" className="btn hidden sm:inline-flex">
              Mission console
            </Link>
            <Link href="/ground/" className="btn btn-amber">
              Ground station
            </Link>
          </div>
        </div>
      </header>

      <main id="main">
        <section aria-labelledby="hero-head" className="mx-auto grid max-w-[76rem] gap-10 px-4 pb-20 pt-16 sm:px-6 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] lg:items-center lg:pt-24">
          <div>
            <p className="mb-5 inline-flex items-center gap-2 rounded-tag bg-accent-soft px-2 py-1 font-mono text-xs text-accent">
              Kiroween 2026 · Frankenstein
            </p>
            <h1 id="hero-head" className="max-w-[16ch] text-[2.75rem] leading-[1.02] text-ink sm:text-[3.75rem]">
              Steer a 1969 guidance computer with sound.
            </h1>
            <p className="mt-5 max-w-[44ch] text-[1.125rem] text-ink-2">
              A Kiro agent flies an Apollo-style DSKY through authenticated Bell-202 audio frames, and a safety gate written in
              code decides which keys it may press.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link href="/ground/" className="btn btn-amber">
                Open the ground station
              </Link>
              <Link href="/console/" className="btn">
                Open the mission console
              </Link>
            </div>
            <p className="mt-5 max-w-[52ch] text-sm text-muted">
              Status: works end to end with WAV and loopback audio, including a live Kiro run. Over-the-air decoding does not work
              yet. The console needs the local daemon on 127.0.0.1.
            </p>
          </div>
          <LiveRunCard />
        </section>

        <Section id="how" title="Cut the network cable, keep the sound" lead="Four parts, one direction. Each one trusts the previous part only after checking it.">
          <ol className="grid gap-px overflow-hidden rounded-card border border-rule-2 bg-rule sm:grid-cols-2 lg:grid-cols-4">
            {PIPELINE.map((p, i) => (
              <li key={p.key} className="bg-paper-2 p-5">
                <p className="flex items-center justify-between font-mono text-xs">
                  <span className="text-muted">{String(i + 1).padStart(2, '0')}</span>
                  <span className="rounded-tag bg-paper-3 px-1.5 py-0.5 text-accent">{p.key}</span>
                </p>
                <h3 className="mt-4 text-[1.125rem] text-ink">{p.title}</h3>
                <p className="mt-2 text-sm text-muted">{p.body}</p>
              </li>
            ))}
          </ol>
          <dl className="mt-8 grid gap-px overflow-hidden rounded-card border border-rule bg-rule md:grid-cols-2">
            {SPEC.map(([k, v]) => (
              <div key={k} className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1 bg-paper px-5 py-3">
                <dt className="text-sm text-muted">{k}</dt>
                <dd className="font-mono text-xs text-ink-2">{v}</dd>
              </div>
            ))}
          </dl>
        </Section>

        <Section id="gate" title="Why not just let the model type?" lead="The agent is useful because it reads frames and explains them. It is safe only because it cannot decide what runs.">
          <div className="overflow-hidden rounded-card border border-rule-2">
            <div className="grid grid-cols-2 border-b border-rule-2 bg-paper-3 text-xs font-medium">
              <p className="px-5 py-3 text-muted">Prompt-only agent</p>
              <p className="border-l border-rule px-5 py-3 text-accent">Apollo-26</p>
            </div>
            <ul>
              {COMPARE.map(([before, after]) => (
                <li key={before} className="grid grid-cols-1 border-b border-rule bg-paper-2 last:border-b-0 sm:grid-cols-2">
                  <p className="px-5 py-4 text-sm text-muted">
                    <span className="sr-only">Prompt-only: </span>
                    {before}
                  </p>
                  <p className="px-5 py-4 text-sm text-ink sm:border-l sm:border-rule">
                    <span className="sr-only">Apollo-26: </span>
                    {after}
                  </p>
                </li>
              ))}
            </ul>
          </div>
          <h3 className="mt-14 text-[1.35rem] text-ink">What the first live Kiro runs caught</h3>
          <p className="mt-2 max-w-prose text-sm text-muted">
            The unit tests passed. Running the real agent through the real MCP server still found three problems, and each time the
            gate stopped safely.
          </p>
          <ul className="mt-6 grid gap-4 md:grid-cols-3">
            {CAUGHT.map((c) => (
              <li key={c.title} className="rounded-card border border-rule-2 bg-paper-2 p-5">
                <Chip tone="warn">Found live</Chip>
                <h4 className="mt-3 text-[1.0625rem] font-medium text-ink">{c.title}</h4>
                <p className="mt-2 text-sm text-muted">{c.body}</p>
              </li>
            ))}
          </ul>
        </Section>

        <Section id="evidence" title="Measured, not promised" lead="Read from the committed reports at build time. Missed targets are shown as missed.">
          <div className="overflow-x-auto rounded-card border border-rule-2" role="region" aria-label="Evidence table" tabIndex={0}>
            <table className="w-full min-w-[44rem] border-collapse text-left text-sm">
              <thead>
                <tr className="border-b border-rule-2 bg-paper-3 text-xs text-muted">
                  <th scope="col" className="px-5 py-3 font-medium">What</th>
                  <th scope="col" className="px-5 py-3 font-medium">Result</th>
                  <th scope="col" className="px-5 py-3 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.label} className="border-b border-rule bg-paper-2 last:border-b-0">
                    <th scope="row" className="px-5 py-4 align-top font-normal">
                      <span className="block text-ink">{r.label}</span>
                      <span className="mt-1 block text-xs text-muted">{r.detail}</span>
                    </th>
                    <td className="whitespace-nowrap px-5 py-4 align-top font-mono text-sm text-ink-2 tabular">{r.value}</td>
                    <td className="px-5 py-4 align-top">
                      <Chip tone={STATUS_TONE[r.status]}>{r.status}</Chip>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-4 text-xs text-muted">
            Sources: <ExternalLink href={blob('docs/metrics.json')}>docs/metrics.json</ExternalLink> (measured{' '}
            {metrics.environment.measured_at.slice(0, 10)}, {metrics.environment.platform}, Python {metrics.environment.python}),{' '}
            <ExternalLink href={blob('docs/pbt-report.md')}>docs/pbt-report.md</ExternalLink>,{' '}
            <ExternalLink href={blob('docs/evidence-matrix.md')}>docs/evidence-matrix.md</ExternalLink>.
          </p>
        </Section>

        <Section id="kiro" title="Built with Kiro" lead="Everything Kiro used is in the repository, not just described.">
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {KIRO.map((k) => (
              <li key={k.title}>
                <a href={k.href} className="block h-full min-h-11 rounded-card border border-rule-2 bg-paper-2 p-5 transition-colors hover:border-ink-2 hover:bg-paper-3">
                  <span className="text-[1.0625rem] font-medium text-ink">{k.title}</span>
                  <span className="mt-2 block text-sm text-muted">{k.body}</span>
                </a>
              </li>
            ))}
          </ul>
        </Section>

        <Section id="try" title="Try it without a microphone" lead="Python 3.12 only. Node.js is not needed; the built pages ship in the repository.">
          <pre className="overflow-x-auto rounded-card border border-rule-2 bg-paper-3 p-5 font-mono text-sm leading-relaxed text-ink-2">
            <code>{`git clone ${REPO}.git && cd apollo-26
python -m venv .venv
.venv\\Scripts\\python -m pip install -e ".[dev]"
copy .env.example .env
.venv\\Scripts\\python -m acoustic.daemon --provision-sequence 0
.venv\\Scripts\\python -m acoustic.daemon --input web-dashboard\\public\\sample_burst.wav --serve-after-input
# then open http://127.0.0.1:8026/console/`}</code>
          </pre>
        </Section>

        <Section id="faq" title="What judges ask">
          <dl className="grid gap-px overflow-hidden rounded-card border border-rule-2 bg-rule">
            {FAQ.map(([q, a]) => (
              <div key={q} className="grid gap-2 bg-paper-2 px-5 py-5 md:grid-cols-[18rem_minmax(0,1fr)] md:gap-8">
                <dt className="font-medium text-ink">{q}</dt>
                <dd className="text-sm text-ink-2">{a}</dd>
              </div>
            ))}
          </dl>
        </Section>
      </main>

      <footer className="border-t border-rule">
        <div className="mx-auto flex max-w-[76rem] flex-wrap items-baseline justify-between gap-4 px-4 py-10 sm:px-6">
          <p className="text-[1.35rem] font-medium tracking-tight text-ink">Apollo-26</p>
          <p className="text-xs text-muted">
            MIT License · Kiroween 2026 ·{' '}
            <ExternalLink href={REPO}>github.com/0xshalah/apollo-26</ExternalLink>
          </p>
        </div>
      </footer>
    </>
  );
}
