import { FIELD_LAYOUT, parseFields, type FieldName } from '@/lib/frame';
import { centidegrees, hexBytes, tenthsFps } from '@/lib/format';
import { byteTo8n1, DEFAULT_PREAMBLE_SYMBOLS, DEFAULT_TAIL_SYMBOLS, BAUD } from '@/lib/modem';

/** Decoded meaning of each field, derived from the exact bytes (never from form state). */
function describe(bytes: Uint8Array): Record<FieldName, string> {
  const f = parseFields(bytes);
  return {
    sync: 'sync word',
    version: `v${bytes[2]}`,
    frame_type: f.frame_type,
    seq: String(f.seq),
    ref_seq: String(f.ref_seq),
    flags: f.critical ? 'CRITICAL (bit0)' : 'none',
    verb: `V${String(f.verb).padStart(2, '0')}`,
    noun: `N${String(f.noun).padStart(2, '0')}`,
    program: `P${String(f.program).padStart(2, '0')}`,
    r1: `${f.r1_centidegrees} (${centidegrees(f.r1_centidegrees)})`,
    r2: `${f.r2_centidegrees} (${centidegrees(f.r2_centidegrees)})`,
    delta_v: `${f.delta_v_tenths_fps} (${tenthsFps(f.delta_v_tenths_fps)})`,
    hmac: 'HMAC-SHA256[0..8] over bytes 2–23',
    crc: 'CRC-16/CCITT-FALSE over bytes 2–31',
  };
}

export function FrameInspector({ bytes, hex }: { bytes: Uint8Array; hex: string }) {
  const meaning = describe(bytes);
  const totalSymbols = DEFAULT_PREAMBLE_SYMBOLS + bytes.length * 10 + DEFAULT_TAIL_SYMBOLS;
  return (
    <div className="space-y-5">
      <div className="rounded-pill border border-rule-2 bg-paper-3 p-3">
        <h3 className="text-xs font-medium text-ink-2">Transmitted hex (34 bytes)</h3>
        <p className="mt-1 break-all font-mono text-sm text-cool tabular" data-testid="frame-hex">
          {hex}
        </p>
      </div>

      <div className="overflow-x-auto rounded-pill border border-rule" role="region" aria-label="Frame fields" tabIndex={0}>
        <table className="w-full min-w-[34rem] border-collapse text-left text-sm">
          <caption className="sr-only">Frame fields at normative offsets</caption>
          <thead>
            <tr className="border-b border-rule-2 bg-paper-3 text-xs text-muted">
              <th scope="col" className="px-3 py-2 font-medium">Offset</th>
              <th scope="col" className="px-3 py-2 font-medium">Field</th>
              <th scope="col" className="px-3 py-2 font-medium">Bytes</th>
              <th scope="col" className="px-3 py-2 font-medium">Value</th>
            </tr>
          </thead>
          <tbody>
            {FIELD_LAYOUT.map((f) => (
              <tr key={f.name} className="border-b border-rule last:border-b-0">
                <td className="px-3 py-2 font-mono text-muted tabular">{f.offset}</td>
                <th scope="row" className="px-3 py-2 font-normal text-ink-2">{f.name}</th>
                <td className="px-3 py-2 font-mono text-ok tabular">{hexBytes(bytes, f.offset, f.length)}</td>
                <td className="px-3 py-2 font-mono text-xs text-ink-2">{meaning[f.name]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div>
        <h3 className="text-xs font-medium text-ink-2">8N1 symbol stream (start · data LSB-first · stop)</h3>
        <p className="mt-1 text-xs text-muted">
          {DEFAULT_PREAMBLE_SYMBOLS} mark symbols preamble ({Math.round((DEFAULT_PREAMBLE_SYMBOLS * 1000) / BAUD)} ms), then{' '}
          {bytes.length * 10} frame symbols, then {DEFAULT_TAIL_SYMBOLS} idle mark symbols. Total {totalSymbols} symbols ≈{' '}
          {Math.round((totalSymbols * 1000) / BAUD)} ms at {BAUD} baud.
        </p>
        <ol className="mt-2 grid grid-cols-[repeat(auto-fill,minmax(8.5rem,1fr))] gap-px overflow-hidden rounded-pill border border-rule bg-rule font-mono text-xs tabular">
          {Array.from(bytes, (b, i) => {
            const bits = byteTo8n1(b);
            return (
              <li key={i} className="bg-paper-3 px-2 py-1.5">
                <span className="text-muted">{String(i).padStart(2, '0')} </span>
                <span className="text-muted">{bits[0]}</span>
                <span className="text-cool">{bits.slice(1, 9).join('')}</span>
                <span className="text-muted">{bits[9]}</span>
              </li>
            );
          })}
        </ol>
      </div>
    </div>
  );
}
