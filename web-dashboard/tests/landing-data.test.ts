import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { evidenceRows, liveRunStages, TARGETS, utcTime, type MetricsDoc, type TestSummary } from '../lib/landing-data';
import { REPO } from './fixtures';

const metrics = JSON.parse(readFileSync(path.join(REPO, 'docs/metrics.json'), 'utf8')) as MetricsDoc;
const summary = JSON.parse(readFileSync(path.join(REPO, 'docs/test-summary.json'), 'utf8')) as TestSummary;

describe('landing evidence', () => {
  it('copies numbers from the committed reports', () => {
    const rows = evidenceRows(metrics, summary);
    const byLabel = Object.fromEntries(rows.map((r) => [r.label, r]));
    const loop = metrics.loopback_processing;
    expect(byLabel['Loopback decode and validation'].value).toContain(`${loop.frames_accepted}/${loop.frames_sent}`);
    expect(byLabel['Loopback decode and validation'].value).toContain(loop.processing_s.median.toFixed(2));
    expect(byLabel['Python test suite, property-based profile'].value).toContain(`${summary.passed} passed`);
    expect(byLabel['Live Kiro agent, critical P40 with AUTH'].value).toContain(
      metrics.agent_path_live.p40_critical_with_auth.command_to_postcondition_s.toFixed(1),
    );
  });

  it('marks a missed target as FAILED instead of hiding it', () => {
    const rows = evidenceRows(metrics, summary);
    const air = rows.find((r) => r.label.startsWith('Over the air'))!;
    const agent = rows.find((r) => r.label.startsWith('Live Kiro agent'))!;
    const a = metrics.acoustic_self_test;
    expect(air.status).toBe(a.frames_accepted >= a.frames_sent * TARGETS.overAirAcceptRatio ? 'MEASURED' : 'FAILED');
    const p40 = metrics.agent_path_live.p40_critical_with_auth.command_to_postcondition_s;
    expect(agent.status).toBe(p40 <= TARGETS.agentPathSeconds ? 'MEASURED' : 'FAILED');
    expect(rows.find((r) => r.label.startsWith('Phone to laptop'))!.status).toBe('NOT RUN');
  });

  it('flags a failing test summary', () => {
    const rows = evidenceRows(metrics, { ...summary, failed: 1 });
    expect(rows.find((r) => r.label.startsWith('Python test suite'))!.status).toBe('FAILED');
  });

  it('derives live-run offsets from the recorded timestamps', () => {
    const stages = liveRunStages(metrics);
    const p40 = metrics.agent_path_live.p40_critical_with_auth;
    const expected = (Date.parse(p40.execution_finished_at) - Date.parse(p40.command_received_at)) / 1000;
    expect(stages[0].atSeconds).toBe(0);
    expect(stages[stages.length - 1].atSeconds).toBeCloseTo(expected, 2);
    expect(stages.find((x) => x.tone === 'bad')?.result).toContain(p40.refused_without_auth);
    expect(utcTime(p40.command_received_at)).toMatch(/^\d\d:\d\d:\d\d\.\d+ UTC$/);
  });
});
