import { Chip, Panel } from '@/components/Panel';
import { AUDIT_LIMIT, type AuditRow, type ConnectionState } from '@/lib/console-state';
import { FIELD_LAYOUT, fromHex, parseFields } from '@/lib/frame';
import { centidegrees, hexBytes, pad2, tenthsFps } from '@/lib/format';

type Gate = boolean | null;

function GateCell({ value, label }: { value: Gate; label: string }) {
  const text = value === null ? 'N/A' : value ? 'PASS' : 'FAIL';
  return (
    <td className="px-2 py-1.5 font-mono text-xs">
      <span className="sr-only">{label}: </span>
      <span className={value === null ? 'text-electrum/50' : value ? 'text-phosphor' : 'bg-electrum px-1 text-void'}>{text}</span>
    </td>
  );
}

export function AuditLedger({
  rows,
  selectedId,
  onSelect,
  connection,
}: {
  rows: readonly AuditRow[];
  selectedId: number | null;
  onSelect: (id: number | null) => void;
  connection: ConnectionState;
}) {
  const newestFirst = [...rows].reverse();
  const selected = rows.find((r) => r.eventId === selectedId) ?? null;
  const disconnected = connection.kind !== 'connected';

  return (
    <Panel
      id="audit"
      title="Frame audit log"
      aside={<span className="font-mono text-xs text-electrum/70">{rows.length} rows · client window, newest {AUDIT_LIMIT} max</span>}
    >
      {rows.length === 0 ? (
        <p className="text-sm text-electrum/70">
          {disconnected
            ? 'DISCONNECTED. No telemetry.frame events received in this session.'
            : 'Connected. Waiting for the first telemetry.frame event.'}
        </p>
      ) : (
        <div className="max-h-[28rem] overflow-auto" role="region" aria-label="Frame audit table" tabIndex={0}>
          <table className="w-full min-w-[60rem] border-collapse text-left text-sm [&_td]:whitespace-nowrap">
            <caption className="sr-only">Validated telemetry frames, newest first. History after reconnect may be incomplete.</caption>
            <thead className="sticky top-0 z-10 bg-lunar-800 text-xs uppercase tracking-wider text-electrum/75">
              <tr>
                <th scope="col" className="sticky left-0 bg-lunar-800 px-2 py-2 font-normal">Event</th>
                <th scope="col" className="px-2 py-2 font-normal">Verdict</th>
                <th scope="col" className="px-2 py-2 font-normal">Reason</th>
                <th scope="col" className="px-2 py-2 font-normal">Type</th>
                <th scope="col" className="px-2 py-2 font-normal">Seq</th>
                <th scope="col" className="px-2 py-2 font-normal">Ref</th>
                <th scope="col" className="px-2 py-2 font-normal">Cmd</th>
                <th scope="col" className="px-2 py-2 font-normal">CRC</th>
                <th scope="col" className="px-2 py-2 font-normal">HMAC</th>
                <th scope="col" className="px-2 py-2 font-normal">Seq gate</th>
                <th scope="col" className="px-2 py-2 font-normal">Range</th>
                <th scope="col" className="px-2 py-2 font-normal">Source</th>
                <th scope="col" className="px-2 py-2 font-normal">SNR</th>
                <th scope="col" className="px-2 py-2 font-normal">Deviation</th>
                <th scope="col" className="px-2 py-2 font-normal">Received</th>
              </tr>
            </thead>
            <tbody>
              {newestFirst.map((r) => {
                const t = r.telemetry;
                const f = t.frame;
                const isSel = r.eventId === selectedId;
                return (
                  <tr key={r.eventId} className={`border-b border-electrum/10 ${isSel ? 'bg-lunar-800' : ''}`}>
                    <th scope="row" className={`sticky left-0 px-1 py-0.5 font-normal ${isSel ? 'bg-lunar-800' : 'bg-lunar-900'}`}>
                      <button
                        type="button"
                        onClick={() => onSelect(isSel ? null : r.eventId)}
                        aria-pressed={isSel}
                        aria-label={`Event ${r.eventId}, ${t.verdict} ${t.reason}. ${isSel ? 'Hide' : 'Show'} details`}
                        className="min-h-11 px-2 font-mono text-xs underline decoration-electrum/40 underline-offset-4"
                      >
                        #{r.eventId}
                      </button>
                    </th>
                    <td className="px-2 py-1.5">
                      <Chip tone={t.verdict === 'ACCEPTED' ? 'ok' : 'warn'}>{t.verdict}</Chip>
                    </td>
                    <td className="px-2 py-1.5 font-mono text-xs">
                      {t.reason}
                      {r.anomaly ? (
                        <span className="ml-2">
                          <Chip tone="info">Tone anomaly</Chip>
                        </span>
                      ) : null}
                    </td>
                    <td className="px-2 py-1.5 font-mono text-xs">{f ? f.frame_type : 'N/A'}</td>
                    <td className="px-2 py-1.5 font-mono text-xs tabular">{f ? f.seq : 'N/A'}</td>
                    <td className="px-2 py-1.5 font-mono text-xs tabular">{f ? f.ref_seq : 'N/A'}</td>
                    <td className="px-2 py-1.5 font-mono text-xs tabular">
                      {f ? `V${pad2(f.verb)} N${pad2(f.noun)} P${pad2(f.program)}${f.critical ? ' CRIT' : ''}` : 'N/A'}
                    </td>
                    <GateCell label="CRC" value={t.validation.crc} />
                    <GateCell label="HMAC" value={t.validation.hmac} />
                    <GateCell label="Sequence" value={t.validation.sequence} />
                    <GateCell label="Range" value={t.validation.range} />
                    <td className="px-2 py-1.5 font-mono text-xs">
                      {t.source.kind} · {t.source.sample_rate_hz}
                    </td>
                    <td className="px-2 py-1.5 font-mono text-xs tabular">
                      {typeof t.source.snr_db === 'number' ? `${t.source.snr_db} dB` : 'UNMEASURED'}
                    </td>
                    <td className="px-2 py-1.5 font-mono text-xs tabular">{t.source.frequency_deviation_hz} Hz</td>
                    <td className="px-2 py-1.5 font-mono text-xs">{t.received_at}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {selected ? <FrameDetail row={selected} /> : null}
    </Panel>
  );
}

function FrameDetail({ row }: { row: AuditRow }) {
  const t = row.telemetry;
  return (
    <section aria-labelledby="frame-detail-title" className="ticks mt-4 border border-electrum/25 bg-void p-4">
      <h3 id="frame-detail-title" className="text-xs font-semibold uppercase tracking-[0.16em] text-electrum/80">
        Event #{row.eventId} · {t.verdict} · {t.reason}
      </h3>
      {row.anomaly ? (
        <p className="mt-2 text-xs">
          Acoustic anomaly: tone deviation {t.source.frequency_deviation_hz} Hz exceeds 50 Hz. This is reported separately from
          the validation reason{t.reason === 'CRC' ? '; the CRC check also failed.' : '.'}
        </p>
      ) : null}
      {t.reason === 'CRC' ? <p className="mt-2 text-xs font-semibold">CRC-16 check failed for this frame.</p> : null}
      {t.frame === null ? (
        <p className="mt-2 text-sm text-electrum/75">No decoded frame: validation stopped at {t.reason} before fields were decoded.</p>
      ) : (
        <FrameFieldTable rawHex={t.frame.raw_hex} />
      )}
    </section>
  );
}

function FrameFieldTable({ rawHex }: { rawHex: string }) {
  const bytes = fromHex(rawHex);
  const p = parseFields(bytes);
  const value: Record<string, string> = {
    sync: '',
    version: String(bytes[2]),
    frame_type: p.frame_type,
    seq: String(p.seq),
    ref_seq: String(p.ref_seq),
    flags: p.critical ? 'CRITICAL' : 'none',
    verb: pad2(p.verb),
    noun: pad2(p.noun),
    program: pad2(p.program),
    r1: centidegrees(p.r1_centidegrees),
    r2: centidegrees(p.r2_centidegrees),
    delta_v: tenthsFps(p.delta_v_tenths_fps),
    hmac: '',
    crc: '',
  };
  return (
    <div className="mt-3 overflow-x-auto" role="region" aria-label="Decoded frame fields" tabIndex={0}>
      <p className="break-all font-mono text-xs text-phosphor">{rawHex}</p>
      <table className="mt-2 w-full min-w-[30rem] border-collapse text-left text-xs">
        <thead className="text-electrum/70">
          <tr>
            <th scope="col" className="py-1 pr-3 font-normal">Offset</th>
            <th scope="col" className="py-1 pr-3 font-normal">Field</th>
            <th scope="col" className="py-1 pr-3 font-normal">Bytes</th>
            <th scope="col" className="py-1 font-normal">Value</th>
          </tr>
        </thead>
        <tbody>
          {FIELD_LAYOUT.map((f) => (
            <tr key={f.name} className="border-t border-electrum/10">
              <td className="py-1 pr-3 font-mono">{f.offset}</td>
              <th scope="row" className="py-1 pr-3 font-normal">{f.name}</th>
              <td className="py-1 pr-3 font-mono text-phosphor">{hexBytes(bytes, f.offset, f.length)}</td>
              <td className="py-1 font-mono">{value[f.name]}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
