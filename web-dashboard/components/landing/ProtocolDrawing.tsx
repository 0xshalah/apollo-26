import { FIELD_LAYOUT, FRAME_SIZE, fromHex } from '@/lib/frame';

const LABELS: Record<(typeof FIELD_LAYOUT)[number]['name'], string> = {
  sync: 'SYNC',
  version: 'VER',
  frame_type: 'TYPE',
  seq: 'SEQ',
  ref_seq: 'REF SEQ',
  flags: 'FLAGS',
  verb: 'VERB',
  noun: 'NOUN',
  program: 'PROG',
  r1: 'R1',
  r2: 'R2',
  delta_v: 'DELTA-V',
  hmac: 'HMAC',
  crc: 'CRC',
};

/**
 * Protocol anatomy rendered from the normative FIELD_LAYOUT and a recorded frame.
 * Proportions, offsets, byte counts and values are derived; the drawing has no
 * manually duplicated protocol dimensions.
 */
export function ProtocolDrawing({ rawHex }: { rawHex: string }) {
  const bytes = fromHex(rawHex);
  if (bytes.length !== FRAME_SIZE) throw new Error(`recorded frame must contain ${FRAME_SIZE} bytes`);

  return (
    <figure data-reveal className="mt-10 overflow-hidden rounded-card border border-rule-2 bg-paper-2">
      <figcaption className="grid gap-px border-b border-rule bg-rule sm:grid-cols-[minmax(0,1fr)_8rem_8rem_10rem]">
        <div className="bg-paper-3 px-4 py-3">
          <p className="text-[1.0625rem] font-medium text-ink">Acoustic frame dimensional reference</p>
          <p className="mt-1 text-xs text-muted">Wire layout derived from contracts/acoustic-frame-v1.md</p>
        </div>
        {[
          ['DWG NO.', 'FRAME-V1-034'],
          ['UNITS', 'BYTE'],
          ['SCALE', 'PROPORTIONAL'],
        ].map(([label, value]) => (
          <div key={label} className="bg-paper-3 px-4 py-3">
            <p className="text-[0.65rem] text-muted">{label}</p>
            <p className="mt-1 font-mono text-xs text-ink">{value}</p>
          </div>
        ))}
      </figcaption>

      <div className="overflow-x-auto bg-paper-3 p-4" role="region" aria-label="Proportional 34-byte frame drawing" tabIndex={0}>
        <div className="min-w-[70rem] rounded-pill border border-rule-2 bg-paper p-5">
          <div className="flex items-center justify-between gap-4 border-b border-rule pb-3">
            <p className="font-mono text-xs text-ink">FRAME OVERALL · W = {FRAME_SIZE} BYTE</p>
            <p className="font-mono text-xs text-muted">OFFSETS 0–{FRAME_SIZE - 1}</p>
          </div>

          <ol className="mt-5 grid gap-px bg-rule" style={{ gridTemplateColumns: `repeat(${FRAME_SIZE}, minmax(0, 1fr))` }}>
            {Array.from({ length: FRAME_SIZE }, (_, offset) => (
              <li key={offset} className="bg-paper-3 py-1 text-center font-mono text-[0.58rem] text-muted tabular">
                {offset}
              </li>
            ))}
          </ol>

          <ol className="mt-1 grid gap-px bg-rule" style={{ gridTemplateColumns: `repeat(${FRAME_SIZE}, minmax(0, 1fr))` }}>
            {FIELD_LAYOUT.map((field, index) => (
              <li
                key={field.name}
                style={{ gridColumn: `span ${field.length} / span ${field.length}` }}
                className="min-w-0 bg-paper-2 px-1 py-4 text-center"
              >
                <span className="block truncate text-[0.65rem] font-medium text-ink">{LABELS[field.name]}</span>
                <span className="mt-1 block font-mono text-[0.58rem] text-muted">
                  F{String(index + 1).padStart(2, '0')} · {field.length}B
                </span>
              </li>
            ))}
          </ol>

          <ol className="mt-1 grid gap-px bg-rule" style={{ gridTemplateColumns: `repeat(${FRAME_SIZE}, minmax(0, 1fr))` }}>
            {FIELD_LAYOUT.map((field) => (
              <li
                key={field.name}
                style={{ gridColumn: `span ${field.length} / span ${field.length}` }}
                className="min-w-0 bg-paper-3 px-1 py-2 text-center font-mono text-[0.58rem] text-ink-2"
              >
                <span className="block truncate">{rawHex.slice(field.offset * 2, (field.offset + field.length) * 2)}</span>
              </li>
            ))}
          </ol>

          <div className="relative mt-6 h-8 border-x border-b border-rule-2">
            <span className="absolute left-1/2 top-4 -translate-x-1/2 bg-paper px-2 font-mono text-xs text-ink">
              W · frame-size = {FRAME_SIZE}
            </span>
          </div>
        </div>
      </div>

      <div className="grid gap-px border-t border-rule bg-rule lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <div className="bg-paper-2 p-4">
          <p className="text-xs font-medium text-ink">Field schedule</p>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[32rem] border-collapse text-left text-xs">
              <thead className="text-muted">
                <tr className="border-b border-rule">
                  <th scope="col" className="py-2 pr-3 font-medium">Code</th>
                  <th scope="col" className="py-2 pr-3 font-medium">Field</th>
                  <th scope="col" className="py-2 pr-3 font-medium">Offset</th>
                  <th scope="col" className="py-2 font-medium">Length</th>
                </tr>
              </thead>
              <tbody>
                {FIELD_LAYOUT.map((field, index) => (
                  <tr key={field.name} className="border-b border-rule last:border-b-0">
                    <td className="py-1.5 pr-3 font-mono text-muted">F{String(index + 1).padStart(2, '0')}</td>
                    <th scope="row" className="py-1.5 pr-3 font-normal text-ink-2">{LABELS[field.name]}</th>
                    <td className="py-1.5 pr-3 font-mono text-ink-2 tabular">{field.offset}</td>
                    <td className="py-1.5 font-mono text-ink-2 tabular">{field.length} byte{field.length === 1 ? '' : 's'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <div className="bg-paper-2 p-4">
          <p className="text-xs font-medium text-ink">Notes, unless otherwise specified</p>
          <ol className="mt-3 space-y-3 text-xs text-muted">
            <li className="grid grid-cols-[1.5rem_minmax(0,1fr)] gap-2">
              <span className="font-mono text-ink">01</span>
              <span>All multi-byte integers are big-endian. Signed payload fields use two’s complement.</span>
            </li>
            <li className="grid grid-cols-[1.5rem_minmax(0,1fr)] gap-2">
              <span className="font-mono text-ink">02</span>
              <span>CRC-16/CCITT-FALSE covers bytes 2–31 and occupies bytes 32–33.</span>
            </li>
            <li className="grid grid-cols-[1.5rem_minmax(0,1fr)] gap-2">
              <span className="font-mono text-ink">03</span>
              <span>The 8-byte HMAC tag uses the link key for COMMAND and the operator key for AUTH.</span>
            </li>
            <li className="grid grid-cols-[1.5rem_minmax(0,1fr)] gap-2">
              <span className="font-mono text-ink">04</span>
              <span>AUTH binds to one held COMMAND through REF SEQ. Sequence ordering is global across both frame types.</span>
            </li>
          </ol>
        </div>
      </div>
    </figure>
  );
}
