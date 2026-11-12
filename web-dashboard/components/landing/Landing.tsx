import Link from 'next/link';
import type { ReactNode } from 'react';
import metricsJson from '../../../docs/metrics.json';
import summaryJson from '../../../docs/test-summary.json';
import { LandingMotion } from '@/components/landing/LandingMotion';
import { ProtocolDrawing } from '@/components/landing/ProtocolDrawing';
import { Chip, type Tone } from '@/components/Panel';
import { fromHex } from '@/lib/frame';
import { signed5 } from '@/lib/format';
import {
  evidenceRows,
  liveRunStages,
  utcTime,
  type EvidenceRow,
  type EvidenceStatus,
  type MetricsDoc,
  type TestSummary,
} from '@/lib/landing-data';
import { BAUD, byteTo8n1, MARK_HZ, SPACE_HZ } from '@/lib/modem';

const metrics = metricsJson as unknown as MetricsDoc;
const summary = summaryJson as TestSummary;
const REPO = 'https://github.com/0xshalah/apollo-26';
const blob = (path: string) => `${REPO}/blob/main/${path}`;
const tree = (path: string) => `${REPO}/tree/main/${path}`;

const NAV = [
  { href: '#system', label: 'System' },
  { href: '#gate', label: 'Safety' },
  { href: '#evidence', label: 'Evidence' },
  { href: '#kiro', label: 'Kiro' },
  { href: '#faq', label: 'FAQ' },
];

const STATUS_TONE: Record<EvidenceStatus, Tone> = {
  MEASURED: 'ok',
  VERIFIED: 'ok',
  FAILED: 'bad',
  'NOT RUN': 'muted',
};

function ExternalLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a href={href} className="text-cool underline decoration-cool/40 underline-offset-4 hover:decoration-cool">
      {children}
    </a>
  );
}

function SectionHeading({
  id,
  eyebrow,
  title,
  lead,
}: {
  id: string;
  eyebrow: string;
  title: string;
  lead: string;
}) {
  return (
    <div className="grid gap-5 lg:grid-cols-[12rem_minmax(0,1fr)] lg:gap-12">
      <p className="font-mono text-xs text-accent tabular">{eyebrow}</p>
      <div>
        <h2 id={id} className="max-w-[24ch] text-[2rem] leading-[1.08] text-ink sm:text-[2.75rem]">{title}</h2>
        <p className="mt-4 max-w-[62ch] text-[1.0625rem] text-muted">{lead}</p>
      </div>
    </div>
  );
}

function Section({
  id,
  eyebrow,
  title,
  lead,
  children,
}: {
  id: string;
  eyebrow: string;
  title: string;
  lead: string;
  children: ReactNode;
}) {
  return (
    <section id={id} aria-labelledby={`${id}-head`} className="scroll-mt-24 border-t border-rule py-20 sm:py-28">
      <div className="mx-auto max-w-[78rem] px-4 sm:px-6">
        <SectionHeading id={`${id}-head`} eyebrow={eyebrow} title={title} lead={lead} />
        <div className="mt-12 lg:mt-16">{children}</div>
      </div>
    </section>
  );
}

function OrbitDiagram() {
  return (
    <svg
      data-orbit
      viewBox="0 0 760 440"
      aria-hidden="true"
      className="pointer-events-none absolute inset-x-0 bottom-0 -z-10 h-auto w-full text-rule-2 opacity-55"
    >
      <path d="M-40 366C116 190 306 126 796 58" fill="none" stroke="currentColor" strokeWidth="1" />
      <path d="M-12 406C212 216 426 184 790 108" fill="none" stroke="currentColor" strokeWidth="1" strokeDasharray="2 10" />
      <path d="M174 456C332 262 544 198 804 172" fill="none" stroke="currentColor" strokeWidth="1" />
      <circle cx="154" cy="264" r="4" className="fill-accent stroke-paper" strokeWidth="3" />
      <circle cx="532" cy="140" r="4" className="fill-cool stroke-paper" strokeWidth="3" />
      <circle cx="690" cy="92" r="3" className="fill-ok stroke-paper" strokeWidth="3" />
    </svg>
  );
}

function MiniDsky({ values }: { values: MetricsDoc['agent_path_live']['p40_critical_with_auth']['postcondition'] }) {
  const top = [
    ['PROG', values.program],
    ['VERB', values.verb],
    ['NOUN', values.noun],
  ] as const;
  const registers = [
    ['R1', values.r1],
    ['R2', values.r2],
    ['R3', values.r3],
  ] as const;
  return (
    <div className="overflow-hidden rounded-card border border-rule-2 bg-rule-2">
      <dl className="grid grid-cols-3 gap-px bg-rule">
        {top.map(([label, value]) => (
          <div key={label} className="bg-paper px-3 py-2">
            <dt className="text-[0.65rem] text-muted">{label}</dt>
            <dd className="font-mono text-[1.35rem] text-ok tabular">{String(value).padStart(2, '0')}</dd>
          </div>
        ))}
      </dl>
      <dl className="grid gap-px bg-rule">
        {registers.map(([label, value]) => (
          <div key={label} className="flex items-baseline justify-between bg-paper px-3 py-2">
            <dt className="text-xs text-muted">{label}</dt>
            <dd className="font-mono text-sm text-ok tabular">{signed5(value)}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function LiveRunCard() {
  const p40 = metrics.agent_path_live.p40_critical_with_auth;
  const bytes = fromHex(p40.command_raw_hex);
  const stages = liveRunStages(metrics);
  return (
    <figure className="landing-live-card m-0 overflow-hidden rounded-card border border-rule-2 bg-paper-2">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-rule bg-paper-3 px-4 py-3">
        <div>
          <p className="text-xs text-muted">Recorded mission</p>
          <figcaption className="mt-0.5 text-[1.0625rem] font-medium text-ink">P40 burn · live Kiro run</figcaption>
        </div>
        <Chip tone="ok">postcondition matched</Chip>
      </div>

      <div className="grid gap-px bg-rule lg:grid-cols-[minmax(0,1fr)_12rem]">
        <div className="bg-paper-3 px-4 py-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs text-muted">Authenticated COMMAND · 34 bytes</p>
            <span className="font-mono text-xs text-cool">
              {MARK_HZ}/{SPACE_HZ} Hz · {BAUD} bd
            </span>
          </div>
          <p className="mt-2 break-all font-mono text-xs leading-relaxed text-cool tabular">{p40.command_raw_hex}</p>
          <ol aria-label="First four bytes as 8N1 symbols" className="mt-3 grid grid-cols-4 gap-1 font-mono text-[0.7rem] tabular">
            {Array.from(bytes.subarray(0, 4), (byte, index) => {
              const bits = byteTo8n1(byte);
              return (
                <li key={index} className="rounded-tag bg-paper-2 px-1.5 py-1 text-center">
                  <span className="text-muted">{bits[0]}</span>
                  <span className="text-ok">{bits.slice(1, 9).join('')}</span>
                  <span className="text-muted">{bits[9]}</span>
                </li>
              );
            })}
          </ol>
        </div>
        <div className="bg-paper-3 p-3">
          <MiniDsky values={p40.postcondition} />
        </div>
      </div>

      <ol className="divide-y divide-rule">
        {stages.map((stage, index) => (
          <li key={stage.step} className="grid grid-cols-[1.5rem_minmax(0,1fr)_auto] items-start gap-3 px-4 py-3">
            <span
              className={`mt-0.5 grid h-5 w-5 place-items-center rounded-full font-mono text-[0.65rem] ${
                stage.tone === 'bad' ? 'bg-bad-soft text-bad' : 'bg-ok-soft text-ok'
              }`}
            >
              {index + 1}
            </span>
            <span>
              <span className="block text-sm text-ink">{stage.step}</span>
              <span className={`block font-mono text-xs ${stage.tone === 'bad' ? 'text-bad' : 'text-ok'}`}>{stage.result}</span>
            </span>
            <span className="font-mono text-xs text-muted tabular">
              {stage.atSeconds === null ? '—' : `+${stage.atSeconds.toFixed(2)} s`}
            </span>
          </li>
        ))}
      </ol>

      <div className="grid gap-px border-t border-rule bg-rule sm:grid-cols-3">
        <div className="bg-paper-2 px-4 py-3">
          <p className="text-xs text-muted">Controller</p>
          <p className="mt-1 text-sm text-accent">Kiro Flight Watch</p>
        </div>
        <div className="bg-paper-2 px-4 py-3">
          <p className="text-xs text-muted">Without AUTH</p>
          <p className="mt-1 font-mono text-xs text-bad">{p40.refused_without_auth}</p>
        </div>
        <div className="bg-paper-2 px-4 py-3">
          <p className="text-xs text-muted">Key actuation</p>
          <p className="mt-1 font-mono text-xs text-ok">
            {p40.keys}/{p40.keys} in {p40.key_execution_s.toFixed(2)} s
          </p>
        </div>
      </div>
      <p className="border-t border-rule px-4 py-3 text-xs text-muted">
        One run, recorded {utcTime(p40.command_received_at)} on 12 Nov 2026. Total {p40.command_to_postcondition_s} s,
        including a deliberate refused attempt and agent model time.
      </p>
    </figure>
  );
}

const PIPELINE = [
  {
    key: 'TX',
    title: 'Ground station',
    body: 'Signs a 34-byte frame and plays it as 300-baud Bell-202 audio from a phone or laptop.',
  },
  {
    key: 'RX',
    title: 'Acoustic daemon',
    body: 'Demodulates sound, then checks sync, CRC, HMAC, replay and ranges before publishing a frame.',
  },
  {
    key: 'MCP',
    title: 'Kiro Flight Watch',
    body: 'Waits for accepted frames, inspects the AGC, and requests the one canonical DSKY plan.',
  },
  {
    key: 'AGC',
    title: 'DSKY emulator',
    body: 'Presses approved keys at a 100 ms cadence inside an AGC-faithful P00/P40 subset.',
  },
];

const GATE_STEPS = [
  ['01', 'Await', 'Only daemon-accepted COMMAND and AUTH frames enter Flight Watch.'],
  ['02', 'Inspect', 'Read one coherent AGC snapshot. KEY REL and OPR ERR must be clear.'],
  ['03', 'Plan', 'Derive the only canonical key sequence from the signed command catalog.'],
  ['04', 'Authorize', 'Critical P40 actions need one fresh operator AUTH bound to the COMMAND seq.'],
  ['05', 'Execute', 'Recheck revision and keys, claim once, press at 100 ms cadence, verify postcondition.'],
];

const COMPARE: Array<[string, string]> = [
  ['Safety rules live only in a prompt.', 'Rules execute in safety_gate.py and are checked independently inside the daemon.'],
  ['The model chooses which keys to press.', 'Execution accepts only the canonical key plan for that exact signed frame.'],
  ['A critical burn runs if the model decides to.', 'P40 actions need an operator AUTH frame bound to the command sequence.'],
  ['State can change between looking and acting.', 'A changed AGC revision invalidates the inspection and refuses execution.'],
  ['The agent can shell out around its tools.', 'A PreToolUse hook blocks shell tools while Flight Watch is live.'],
];

const CAUGHT = [
  {
    key: 'INSPECTION_STALE',
    title: 'Every plan expired before planning',
    body: 'Agent tool calls were 5–30 s apart; the inspection window was 5 s. It is now 20 s while the exact AGC revision check remains.',
  },
  {
    key: 'KEY_CADENCE',
    title: 'Key 2 of 29 was rejected',
    body: 'A Windows clock made a 100 ms sleep return after 93 ms. The production clock now uses a high-resolution deadline loop.',
  },
  {
    key: 'AUTH_EXPIRED',
    title: 'A human could not authorize in time',
    body: 'Thirty seconds could not fit a human plus several agent calls. The hold is now 120 s; sequence binding and single use remain.',
  },
];

const KIRO = [
  {
    key: '01',
    title: 'Specs',
    body: 'Four EARS requirement → design → task flows. Requirement IDs appear in test names.',
    href: tree('.kiro/specs'),
  },
  {
    key: '02',
    title: 'Steering',
    body: 'Allowed claims, module boundaries, visual rules, and Flight Watch safety rules S-01 to S-07.',
    href: tree('.kiro/steering'),
  },
  {
    key: '03',
    title: 'Hooks',
    body: 'Shell guard in flight mode, fast property tests on save, tests after spec tasks.',
    href: tree('.kiro/hooks'),
  },
  {
    key: '04',
    title: 'MCP server',
    body: 'Six Flight Watch tools. execute_dsky_sequence is never auto-approved, enforced by a test.',
    href: tree('mcp_server'),
  },
  {
    key: '05',
    title: 'Property tests',
    body: 'Hypothesis P1–P8 and fast-check P9 share golden vectors across Python and TypeScript.',
    href: blob('docs/pbt-report.md'),
  },
  {
    key: '06',
    title: 'Build journal',
    body: 'The decisions, failed live runs, and fixes that shaped the final protocol.',
    href: blob('docs/kiro-journal.md'),
  },
];

const FAQ: Array<[string, ReactNode]> = [
  [
    'Is the whole system offline?',
    'No. The daemon, MCP server and emulator use only local listeners, but the Kiro agent itself uses a cloud model.',
  ],
  [
    'Does it run Apollo flight software?',
    'No. It is an AGC-faithful subset: 15-bit ones’ complement words, a DSKY state machine, P00, simplified P40, and V25/V34/V37.',
  ],
  [
    'Does the acoustic link work over the air?',
    <>
      Not yet. The same-laptop speaker-to-microphone trial detected 0 of 20 frames, and the phone trial has not run. WAV and
      loopback input work through the same daemon pipeline. See{' '}
      <ExternalLink href={blob('docs/metrics.json')}>docs/metrics.json</ExternalLink>.
    </>,
  ],
  [
    'What does the authentication protect?',
    'HMAC and sequence checks reject forged and replayed frames in tests. They do not stop eavesdropping or jamming, and the public demo keys are not secrets.',
  ],
  [
    'How can judges run it without audio hardware?',
    'Use the committed sample WAV, open the local mission console, connect Kiro to the MCP server, and start Flight Watch.',
  ],
];

function EvidenceCard({ row }: { row: EvidenceRow }) {
  return (
    <article className="flex h-full flex-col rounded-card border border-rule-2 bg-paper-2 p-5">
      <div className="flex items-start justify-between gap-3">
        <h3 className="max-w-[24ch] text-[1.0625rem] text-ink">{row.label}</h3>
        <Chip tone={STATUS_TONE[row.status]}>{row.status}</Chip>
      </div>
      <p className="mt-8 font-mono text-[1.35rem] text-ink tabular">{row.value}</p>
      <p className="mt-3 text-xs text-muted">{row.detail}</p>
    </article>
  );
}

export function Landing() {
  const rows = evidenceRows(metrics, summary);
  const loopback = rows[0];
  const overAir = rows[1];
  const agent = rows[3];
  const secondaryEvidence = rows.filter((_, index) => ![0, 1, 3].includes(index));

  return (
    <LandingMotion>
      <header className="sticky top-0 z-40 px-3 pt-3 sm:px-6">
        <div className="mx-auto flex max-w-[78rem] items-center gap-4 rounded-card border border-rule-2 bg-paper-3/90 px-3 py-2 backdrop-blur">
          <Link href="/" className="inline-flex min-h-11 items-center gap-2 px-1 text-[1.0625rem] font-medium tracking-tight text-ink">
            <span aria-hidden className="font-mono text-accent">
              {'///'}
            </span>
            Apollo-26
          </Link>
          <nav aria-label="Landing sections" className="hidden flex-1 items-center gap-1 lg:flex">
            {NAV.map((item) => (
              <a
                key={item.href}
                href={item.href}
                className="inline-flex min-h-11 items-center rounded-pill px-3 text-sm text-ink-2 transition-colors hover:bg-paper-2 hover:text-ink"
              >
                {item.label}
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
        <section
          aria-labelledby="hero-head"
          className="landing-hero relative isolate mx-auto grid min-h-[calc(100dvh-5rem)] max-w-[90rem] gap-12 overflow-hidden px-4 pb-24 pt-16 sm:px-6 lg:grid-cols-[minmax(0,0.82fr)_minmax(38rem,1.18fr)] lg:items-center lg:px-12 lg:pt-20"
        >
          <OrbitDiagram />
          <div data-hero-item className="max-w-[38rem]">
            <p className="font-mono text-xs text-accent">KIROWEEN 2026 / FRANKENSTEIN</p>
            <h1 id="hero-head" className="mt-5 max-w-[14ch] text-[3.25rem] leading-[0.98] tracking-[-0.04em] text-ink sm:text-[4.75rem]">
              Emergency guidance, carried by sound.
            </h1>
            <p className="mt-6 max-w-[42ch] text-[1.125rem] leading-relaxed text-ink-2">
              A Kiro agent drives an Apollo-style DSKY through authenticated Bell-202 frames. A safety gate written in code
              controls every key press.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link href="/ground/" className="btn btn-amber">
                Open ground station
              </Link>
              <Link href="/console/" className="btn">
                View mission console
              </Link>
            </div>
            <dl className="mt-8 grid grid-cols-1 gap-px overflow-hidden rounded-card border border-rule bg-rule sm:grid-cols-3">
              <div className="bg-paper-3 p-3">
                <dt className="text-xs text-muted">Loopback path</dt>
                <dd className="mt-1 font-mono text-sm text-ok">
                  {metrics.loopback_processing.frames_accepted}/{metrics.loopback_processing.frames_sent} measured
                </dd>
              </div>
              <div className="bg-paper-3 p-3">
                <dt className="text-xs text-muted">Live MCP path</dt>
                <dd className="mt-1 font-mono text-sm text-ok">
                  P{metrics.agent_path_live.p40_critical_with_auth.postcondition.program} + AUTH
                </dd>
              </div>
              <div className="bg-paper-3 p-3">
                <dt className="text-xs text-muted">Over the air</dt>
                <dd className="mt-1 font-mono text-sm text-bad">
                  {metrics.acoustic_self_test.frames_accepted}/{metrics.acoustic_self_test.frames_sent} detected
                </dd>
              </div>
            </dl>
          </div>
          <div data-hero-item className="relative lg:translate-y-6">
            <div aria-hidden className="absolute -inset-4 -z-10 rounded-card border border-rule/60" />
            <LiveRunCard />
          </div>
        </section>

        <Section
          id="system"
          eyebrow="01 / SYSTEM"
          title="The network ends at the operator. The command continues as sound."
          lead="Apollo-26 separates transmission, validation, agent planning and execution. Each boundary receives typed data and checks what it owns."
        >
          <ol className="landing-pipeline grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {PIPELINE.map((item, index) => (
              <li key={item.key} className="relative rounded-card border border-rule-2 bg-paper-2 p-5">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs text-muted">{String(index + 1).padStart(2, '0')}</span>
                  <span className="rounded-tag bg-paper-3 px-2 py-1 font-mono text-xs text-accent">{item.key}</span>
                </div>
                <h3 className="mt-10 text-[1.125rem] text-ink">{item.title}</h3>
                <p className="mt-3 text-sm text-muted">{item.body}</p>
              </li>
            ))}
          </ol>
          <ProtocolDrawing rawHex={metrics.agent_path_live.p40_critical_with_auth.command_raw_hex} />
        </Section>

        <Section
          id="gate"
          eyebrow="02 / SAFETY"
          title="The model proposes. The gate decides."
          lead="The agent can interpret a command, but it cannot invent the sequence, skip inspection, authorize a critical burn, or retry an uncertain actuation."
        >
          <ol className="grid gap-px overflow-hidden rounded-card border border-rule-2 bg-rule lg:grid-cols-5">
            {GATE_STEPS.map(([key, title, body]) => (
              <li key={key} className="bg-paper-3 p-5">
                <p className="font-mono text-xs text-accent">{key}</p>
                <h3 className="mt-8 text-[1.0625rem] text-ink">{title}</h3>
                <p className="mt-2 text-sm text-muted">{body}</p>
              </li>
            ))}
          </ol>

          <div className="mt-12 overflow-hidden rounded-card border border-rule-2">
            <div className="grid grid-cols-2 border-b border-rule-2 bg-paper-3 text-xs font-medium">
              <p className="px-5 py-3 text-muted">Prompt-only agent</p>
              <p className="border-l border-rule px-5 py-3 text-accent">Apollo-26</p>
            </div>
            <ul>
              {COMPARE.map(([before, after]) => (
                <li key={before} className="grid grid-cols-1 border-b border-rule bg-paper-2 last:border-b-0 sm:grid-cols-2">
                  <p className="px-5 py-4 text-sm text-muted">{before}</p>
                  <p className="px-5 py-4 text-sm text-ink sm:border-l sm:border-rule">{after}</p>
                </li>
              ))}
            </ul>
          </div>

          <div className="mt-16 grid gap-8 lg:grid-cols-[minmax(0,0.7fr)_minmax(0,1.3fr)]">
            <div>
              <p className="font-mono text-xs text-accent">LIVE-RUN FINDINGS</p>
              <h3 className="mt-3 text-[1.65rem] leading-tight text-ink">The test suite passed. Reality still found three bugs.</h3>
              <p className="mt-4 text-sm text-muted">
                Each failure stopped closed. Fixes widened timing windows or improved the clock; none removed a state, key or
                authorization check.
              </p>
              <p className="mt-5 text-sm">
                <ExternalLink href={blob('docs/kiro-journal.md')}>Read the Kiro build journal</ExternalLink>
              </p>
            </div>
            <ol className="grid gap-3">
              {CAUGHT.map((item, index) => (
                <li key={item.key} className="grid gap-4 rounded-card border border-rule-2 bg-paper-2 p-5 sm:grid-cols-[2.5rem_minmax(0,1fr)]">
                  <span className="font-mono text-xs text-accent">0{index + 1}</span>
                  <div>
                    <p className="font-mono text-xs text-bad">{item.key}</p>
                    <h4 className="mt-1 text-[1.0625rem] font-medium text-ink">{item.title}</h4>
                    <p className="mt-2 text-sm text-muted">{item.body}</p>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </Section>

        <Section
          id="evidence"
          eyebrow="03 / EVIDENCE"
          title="Measured, not promised."
          lead="This page reads committed reports at build time. Results that miss the target remain visible and are labelled FAILED."
        >
          <div className="grid gap-4 lg:grid-cols-3">
            <EvidenceCard row={loopback} />
            <EvidenceCard row={overAir} />
            <EvidenceCard row={agent} />
          </div>
          <div className="mt-4 overflow-x-auto rounded-card border border-rule-2" role="region" aria-label="Additional evidence" tabIndex={0}>
            <table className="w-full min-w-[42rem] border-collapse text-left text-sm">
              <caption className="sr-only">Additional measured and verified results</caption>
              <thead>
                <tr className="border-b border-rule-2 bg-paper-3 text-xs text-muted">
                  <th scope="col" className="px-5 py-3 font-medium">Evidence</th>
                  <th scope="col" className="px-5 py-3 font-medium">Result</th>
                  <th scope="col" className="px-5 py-3 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {secondaryEvidence.map((row) => (
                  <tr key={row.label} className="border-b border-rule bg-paper-2 last:border-b-0">
                    <th scope="row" className="px-5 py-4 align-top font-normal">
                      <span className="block text-ink">{row.label}</span>
                      <span className="mt-1 block text-xs text-muted">{row.detail}</span>
                    </th>
                    <td className="whitespace-nowrap px-5 py-4 align-top font-mono text-sm text-ink-2 tabular">{row.value}</td>
                    <td className="px-5 py-4 align-top">
                      <Chip tone={STATUS_TONE[row.status]}>{row.status}</Chip>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-5 text-xs text-muted">
            Sources: <ExternalLink href={blob('docs/metrics.json')}>metrics.json</ExternalLink> ·{' '}
            <ExternalLink href={blob('docs/pbt-report.md')}>pbt-report.md</ExternalLink> ·{' '}
            <ExternalLink href={blob('docs/evidence-matrix.md')}>evidence-matrix.md</ExternalLink>. Measured{' '}
            {metrics.environment.measured_at.slice(0, 10)} on {metrics.environment.platform}, Python {metrics.environment.python}.
          </p>
        </Section>

        <Section
          id="kiro"
          eyebrow="04 / BUILD SYSTEM"
          title="Kiro is visible in the repository."
          lead="Specs shaped the architecture, steering constrained every session, hooks enforced the work mode, and MCP became the flight-control boundary."
        >
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {KIRO.map((item) => (
              <li key={item.key}>
                <a
                  href={item.href}
                  className="group flex h-full min-h-11 flex-col rounded-card border border-rule-2 bg-paper-2 p-5 transition-colors hover:border-ink-2 hover:bg-paper-3"
                >
                  <span className="font-mono text-xs text-accent">{item.key}</span>
                  <span className="mt-8 text-[1.125rem] font-medium text-ink group-hover:text-accent">{item.title}</span>
                  <span className="mt-2 block text-sm text-muted">{item.body}</span>
                  <span className="mt-auto pt-6 text-xs text-cool">View source →</span>
                </a>
              </li>
            ))}
          </ul>
        </Section>

        <section id="try" aria-labelledby="try-head" className="scroll-mt-24 border-t border-rule py-20 sm:py-28">
          <div className="mx-auto grid max-w-[78rem] gap-10 px-4 sm:px-6 lg:grid-cols-[minmax(0,0.75fr)_minmax(0,1.25fr)] lg:items-start">
            <div>
              <p className="font-mono text-xs text-accent">05 / RUN IT</p>
              <h2 id="try-head" className="mt-4 max-w-[18ch] text-[2rem] leading-[1.08] text-ink sm:text-[2.75rem]">
                No microphone required.
              </h2>
              <p className="mt-4 max-w-[42ch] text-[1.0625rem] text-muted">
                The committed WAV passes through the same modem, frame validation and telemetry path. Python 3.12 is enough;
                Node.js is not required.
              </p>
              <div className="mt-6 flex flex-wrap gap-3">
                <Link href="/console/" className="btn btn-amber">
                  Open console
                </Link>
                <ExternalLink href={REPO}>View repository</ExternalLink>
              </div>
            </div>
            <pre className="overflow-x-auto rounded-card border border-rule-2 bg-paper-3 p-5 font-mono text-sm leading-relaxed text-ink-2">
              <code>{`git clone ${REPO}.git
cd apollo-26
python -m venv .venv
.venv\\Scripts\\python -m pip install -e ".[dev]"
copy .env.example .env
.venv\\Scripts\\python -m acoustic.daemon --provision-sequence 0
.venv\\Scripts\\python -m acoustic.daemon \\
  --input web-dashboard\\public\\sample_burst.wav \\
  --serve-after-input
# open http://127.0.0.1:8026/console/`}</code>
            </pre>
          </div>
        </section>

        <Section
          id="faq"
          eyebrow="06 / FLIGHT NOTES"
          title="Questions before launch."
          lead="The short answers reviewers need, including the limits that the demo does not hide."
        >
          <dl className="grid gap-px overflow-hidden rounded-card border border-rule-2 bg-rule">
            {FAQ.map(([question, answer]) => (
              <div key={question} className="grid gap-3 bg-paper-2 px-5 py-5 md:grid-cols-[20rem_minmax(0,1fr)] md:gap-10">
                <dt className="font-medium text-ink">{question}</dt>
                <dd className="text-sm leading-relaxed text-ink-2">{answer}</dd>
              </div>
            ))}
          </dl>
        </Section>

        <section aria-labelledby="closing-head" className="border-t border-rule py-24">
          <div className="mx-auto max-w-[78rem] px-4 sm:px-6">
            <div className="landing-closing relative isolate overflow-hidden rounded-card border border-rule-2 bg-paper-3 p-7 sm:p-12">
              <OrbitDiagram />
              <p className="font-mono text-xs text-accent">END OF BRIEFING</p>
              <h2 id="closing-head" className="mt-4 max-w-[18ch] text-[2.25rem] leading-[1.06] text-ink sm:text-[3.25rem]">
                Send the frame. Inspect the state. Let the gate decide.
              </h2>
              <div className="mt-8 flex flex-wrap gap-3">
                <Link href="/ground/" className="btn btn-amber">
                  Open ground station
                </Link>
                <Link href="/console/" className="btn">
                  View mission console
                </Link>
              </div>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-rule">
        <div className="mx-auto flex max-w-[78rem] flex-wrap items-baseline justify-between gap-4 px-4 py-10 sm:px-6">
          <p className="inline-flex items-center gap-2 text-[1.35rem] font-medium tracking-tight text-ink">
            <span aria-hidden className="font-mono text-accent">
              {'///'}
            </span>
            Apollo-26
          </p>
          <p className="text-xs text-muted">
            MIT License · Kiroween 2026 · <ExternalLink href={REPO}>github.com/0xshalah/apollo-26</ExternalLink>
          </p>
        </div>
      </footer>
    </LandingMotion>
  );
}
