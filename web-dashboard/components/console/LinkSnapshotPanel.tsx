import { Chip, Panel } from '@/components/Panel';
import type { AuditRow } from '@/lib/console-state';
import { commandLabel } from '@/lib/console-view';
import { centidegrees, tenthsFps } from '@/lib/format';

function Gate({ label, value }: { label: string; value: boolean | null }) {
  const text = value === null ? 'N/A' : value ? 'PASS' : 'FAIL';
  const color = value === null ? 'text-muted' : value ? 'text-ok' : 'text-bad';
  return (
    <div className="bg-paper px-3 py-2">
      <dt className="text-[0.65rem] text-muted">{label}</dt>
      <dd className={`mt-0.5 font-mono text-xs ${color}`}>{text}</dd>
    </div>
  );
}

/** Latest telemetry.frame projection. It never substitutes COMMAND values for AGC state. */
export function LinkSnapshotPanel({ latest, disconnected }: { latest: AuditRow | null; disconnected: boolean }) {
  const telemetry = latest?.telemetry ?? null;
  const frame = telemetry?.frame ?? null;
  const status = latest ? (
    <Chip tone={disconnected ? 'warn' : telemetry?.verdict === 'ACCEPTED' ? 'ok' : 'bad'}>
      {disconnected ? 'STALE' : telemetry?.verdict}
    </Chip>
  ) : (
    <Chip tone="muted">AWAITING</Chip>
  );

  return (
    <Panel id="link-snapshot" title="Latest link snapshot" aside={status}>
      {!telemetry || !latest ? (
        <div className="grid min-h-48 place-items-center rounded-pill border border-rule-2 bg-paper-3 p-6 text-center">
          <div>
            <p className="font-mono text-xs text-muted">NO FRAME IN CLIENT WINDOW</p>
            <p className="mt-2 max-w-xs text-sm text-muted">The first schema-valid telemetry.frame event will populate this instrument.</p>
          </div>
        </div>
      ) : (
        <div className={disconnected ? 'opacity-65' : ''}>
          <div className="flex flex-wrap items-start justify-between gap-4 rounded-pill border border-rule bg-paper-3 p-3">
            <div>
              <p className="font-mono text-xs text-muted">EVT-{latest.eventId}</p>
              <p className="mt-1 text-[1.125rem] font-medium text-ink">
                {frame ? commandLabel(frame) : `${telemetry.reason} before field decode`}
              </p>
              <p className="mt-1 text-xs text-muted">
                {telemetry.source.kind} · {telemetry.source.sample_rate_hz} Hz · {telemetry.received_at}
              </p>
            </div>
            <div className="text-right">
              <p className="font-mono text-xs text-muted">reason</p>
              <p className={`mt-1 font-mono text-sm ${telemetry.reason === 'OK' ? 'text-ok' : 'text-bad'}`}>{telemetry.reason}</p>
            </div>
          </div>

          <dl className="mt-3 grid grid-cols-3 gap-px overflow-hidden rounded-pill border border-rule bg-rule">
            <Gate label="CRC" value={telemetry.validation.crc} />
            <Gate label="HMAC" value={telemetry.validation.hmac} />
            <Gate label="Sequence" value={telemetry.validation.sequence} />
            <Gate label="Range" value={telemetry.validation.range} />
            <Gate label="Length" value={telemetry.validation.length} />
            <Gate label="Sync" value={telemetry.validation.sync} />
          </dl>

          {frame ? (
            <>
              <dl className="mt-3 grid grid-cols-2 gap-px overflow-hidden rounded-pill border border-rule bg-rule">
                <div className="bg-paper-3 px-3 py-2">
                  <dt className="text-[0.65rem] text-muted">Frame</dt>
                  <dd className="mt-0.5 font-mono text-xs text-ink">
                    {frame.frame_type} · seq {frame.seq} · ref {frame.ref_seq}
                  </dd>
                </div>
                <div className="bg-paper-3 px-3 py-2">
                  <dt className="text-[0.65rem] text-muted">Flag</dt>
                  <dd className="mt-0.5 font-mono text-xs text-ink">{frame.critical ? 'CRITICAL' : 'none'}</dd>
                </div>
                <div className="bg-paper-3 px-3 py-2">
                  <dt className="text-[0.65rem] text-muted">R1 / R2</dt>
                  <dd className="mt-0.5 font-mono text-xs text-ink">{centidegrees(frame.r1_centidegrees)} / {centidegrees(frame.r2_centidegrees)}</dd>
                </div>
                <div className="bg-paper-3 px-3 py-2">
                  <dt className="text-[0.65rem] text-muted">Delta-v</dt>
                  <dd className="mt-0.5 font-mono text-xs text-ink">{tenthsFps(frame.delta_v_tenths_fps)}</dd>
                </div>
              </dl>
              <div className="mt-3 rounded-pill border border-rule bg-paper-3 p-3">
                <p className="text-[0.65rem] text-muted">Raw frame</p>
                <p className="mt-1 break-all font-mono text-[0.7rem] leading-relaxed text-cool">{frame.raw_hex}</p>
              </div>
            </>
          ) : (
            <p className="mt-3 rounded-pill border border-rule bg-paper-3 p-3 text-xs text-muted">
              No decoded fields are shown because validation stopped at {telemetry.reason}.
            </p>
          )}

          <dl className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted">
            <div>
              <dt className="inline">Tone deviation </dt>
              <dd className={`inline font-mono ${latest.anomaly ? 'text-bad' : 'text-ink-2'}`}>{telemetry.source.frequency_deviation_hz} Hz</dd>
            </div>
            <div>
              <dt className="inline">SNR </dt>
              <dd className="inline font-mono text-ink-2">{typeof telemetry.source.snr_db === 'number' ? `${telemetry.source.snr_db} dB` : 'UNMEASURED'}</dd>
            </div>
          </dl>
        </div>
      )}
    </Panel>
  );
}
