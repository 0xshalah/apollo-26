/**
 * Landing-page evidence, read at build time from the committed reports:
 * docs/metrics.json (scripts/measure_metrics.py + the recorded live Kiro run) and
 * docs/test-summary.json (scripts/write_test_summary.py). Nothing here is typed in by hand;
 * a missed target is shown as missed.
 */

export type EvidenceStatus = 'MEASURED' | 'VERIFIED' | 'FAILED' | 'NOT RUN';

export interface EvidenceRow {
  label: string;
  value: string;
  detail: string;
  status: EvidenceStatus;
}

export interface MetricsDoc {
  agent_path_live: {
    runs: number;
    p40_critical_with_auth: {
      command_received_at: string;
      auth_received_at: string;
      execution_finished_at: string;
      command_to_postcondition_s: number;
      keys: number;
      key_execution_s: number;
      command_raw_hex: string;
      auth_raw_hex: string;
      refused_without_auth: string;
      critical_reasons: string[];
      postcondition: { program: number; verb: number; noun: number; r1: number; r2: number; r3: number };
    };
  };
  resources_idle: { rss_mb: number; mean_percent_of_one_core: number; seconds: number };
  acoustic_self_test: { frames_sent: number; frames_accepted: number };
  loopback_processing: { frames_sent: number; frames_accepted: number; processing_s: { median: number; max: number } };
  environment: { measured_at: string; platform: string; python: string };
}

export interface TestSummary {
  profile: string;
  passed: number;
  failed: number;
  skipped: number;
  report_path: string;
}

/** Targets from docs/evidence-matrix.md "Competition claims". */
export const TARGETS = {
  agentPathSeconds: 10,
  overAirAcceptRatio: 0.95,
  idleCpuPercentOfCore: 10,
  ramMb: 256,
} as const;

const s = (n: number, digits = 2) => n.toFixed(digits);

export function evidenceRows(m: MetricsDoc, t: TestSummary): EvidenceRow[] {
  const loop = m.loopback_processing;
  const air = m.acoustic_self_test;
  const p40 = m.agent_path_live.p40_critical_with_auth;
  const idle = m.resources_idle;
  return [
    {
      label: 'Loopback decode and validation',
      value: `${loop.frames_accepted}/${loop.frames_sent} accepted · median ${s(loop.processing_s.median)} s`,
      detail: `Same daemon pipeline as the microphone, no air channel. Max ${s(loop.processing_s.max)} s.`,
      status: loop.frames_accepted === loop.frames_sent ? 'MEASURED' : 'FAILED',
    },
    {
      label: 'Over the air, laptop speaker to its own microphone',
      value: `${air.frames_accepted}/${air.frames_sent} accepted`,
      detail: `Target ${Math.round(TARGETS.overAirAcceptRatio * 100)} percent or more. Needs Windows audio enhancements off; with defaults the preamble is suppressed.`,
      status: air.frames_accepted >= air.frames_sent * TARGETS.overAirAcceptRatio ? 'MEASURED' : 'FAILED',
    },
    {
      label: 'Phone to laptop at 0.5 m',
      value: 'Not run yet',
      detail: `Target ${Math.round(TARGETS.overAirAcceptRatio * 100)} percent or more of 20 frames.`,
      status: 'NOT RUN',
    },
    {
      label: 'Live Kiro agent, critical P40 with AUTH',
      value: `${s(p40.command_to_postcondition_s, 1)} s`,
      detail: `${m.agent_path_live.runs} run, COMMAND accepted to DSKY postcondition, including a deliberate refused attempt. Target ${TARGETS.agentPathSeconds} s.`,
      status: p40.command_to_postcondition_s <= TARGETS.agentPathSeconds ? 'MEASURED' : 'FAILED',
    },
    {
      label: 'Daemon idle, listening to the microphone',
      value: `${s(idle.mean_percent_of_one_core, 1)}% of one core · ${s(idle.rss_mb, 0)} MB`,
      detail: `${idle.seconds} s sample. Targets ${TARGETS.idleCpuPercentOfCore}% CPU and ${TARGETS.ramMb} MB.`,
      status:
        idle.mean_percent_of_one_core <= TARGETS.idleCpuPercentOfCore && idle.rss_mb <= TARGETS.ramMb ? 'MEASURED' : 'FAILED',
    },
    {
      label: 'Python test suite, property-based profile',
      value: `${t.passed} passed · ${t.failed} failed`,
      detail: `Hypothesis "${t.profile}" profile, fixed seed. Report: ${t.report_path}.`,
      status: t.failed === 0 && t.passed > 0 ? 'VERIFIED' : 'FAILED',
    },
  ];
}

export interface LiveStage {
  step: string;
  result: string;
  /** Seconds after the COMMAND was accepted, from recorded timestamps; null when not recorded. */
  atSeconds: number | null;
  tone: 'ok' | 'bad' | 'info';
}

export function liveRunStages(m: MetricsDoc): LiveStage[] {
  const p40 = m.agent_path_live.p40_critical_with_auth;
  const t0 = Date.parse(p40.command_received_at);
  const since = (iso: string) => Math.round((Date.parse(iso) - t0) / 10) / 100;
  return [
    { step: 'COMMAND seq 2 accepted', result: 'CRC, HMAC, sequence, range', atSeconds: 0, tone: 'ok' },
    { step: 'AUTH seq 3 accepted', result: 'ref_seq 2, operator key', atSeconds: since(p40.auth_received_at), tone: 'ok' },
    { step: 'Execute without AUTH', result: `refused ${p40.refused_without_auth}`, atSeconds: null, tone: 'bad' },
    {
      step: `${p40.keys}/${p40.keys} keys pressed`,
      result: `${s(p40.key_execution_s)} s at the 100 ms cadence`,
      atSeconds: since(p40.execution_finished_at),
      tone: 'ok',
    },
  ];
}

/** "2026-11-12T09:24:44.924Z" -> "09:24:44.924 UTC" */
export function utcTime(iso: string): string {
  const match = /T(\d\d:\d\d:\d\d(?:\.\d+)?)Z$/.exec(iso);
  return match ? `${match[1]} UTC` : iso;
}
