import { Chip, Panel } from '@/components/Panel';
import type { PanelValue } from '@/lib/console-state';
import type { SpectrumData } from '@/lib/events';
import { MARK_HZ, SPACE_HZ } from '@/lib/modem';

const W = 640;
const H = 200;

/** Renders only received bins. Mark/space lines are labelled reference markers, not data. */
export function SpectrumPanel({ spectrum, disconnected }: { spectrum: PanelValue<SpectrumData>; disconnected: boolean }) {
  const status =
    spectrum.kind === 'loading' ? (
      <Chip tone={disconnected ? 'bad' : 'muted'}>{disconnected ? 'DISCONNECTED' : 'AWAITING'}</Chip>
    ) : spectrum.kind === 'stale' ? (
      <Chip tone="warn">STALE</Chip>
    ) : (
      <Chip tone="ok">LIVE</Chip>
    );

  return (
    <Panel id="spectrum" title={`Acoustic spectrum, Bell-202 (${MARK_HZ} / ${SPACE_HZ} Hz)`} aside={status}>
      {spectrum.kind === 'loading' ? (
        <SpectrumReference disconnected={disconnected} />
      ) : (
        <SpectrumPlot data={spectrum.value} eventId={spectrum.eventId} timestamp={spectrum.timestamp} stale={spectrum.kind === 'stale'} />
      )}
    </Panel>
  );
}

/** Normative frequency ruler only. It deliberately contains no power bars or measured values. */
function SpectrumReference({ disconnected }: { disconnected: boolean }) {
  const min = 800;
  const max = 2600;
  const left = (frequency: number) => `${((frequency - min) / (max - min)) * 100}%`;
  return (
    <div className="rounded-pill border border-rule-2 bg-paper-3 p-4">
      <div className="flex items-center justify-between gap-3">
        <p className="font-mono text-xs text-muted">REFERENCE FREQUENCIES</p>
        <Chip tone="muted">not measured</Chip>
      </div>
      <div className="relative mt-8 h-28 border-b border-rule-2" aria-hidden="true">
        {[MARK_HZ, SPACE_HZ].map((frequency) => (
          <div key={frequency} className="absolute inset-y-0 -translate-x-1/2" style={{ left: left(frequency) }}>
            <div className="h-full border-l border-dashed border-cool/70" />
            <span className="absolute -top-5 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-tag bg-cool-soft px-2 py-0.5 font-mono text-xs text-cool">
              {frequency} Hz
            </span>
            <span className="absolute bottom-2 left-1/2 -translate-x-1/2 text-xs text-muted">
              {frequency === MARK_HZ ? 'mark · bit 1' : 'space · bit 0'}
            </span>
          </div>
        ))}
        <span className="absolute -bottom-6 left-0 font-mono text-[0.65rem] text-muted">{min} Hz</span>
        <span className="absolute -bottom-6 right-0 font-mono text-[0.65rem] text-muted">{max} Hz</span>
      </div>
      <p className="mt-10 text-sm text-muted">
        {disconnected ? 'DISCONNECTED. ' : ''}No audio.spectrum event has arrived. These two markers are protocol references, not a
        generated or measured spectrum.
      </p>
    </div>
  );
}

function SpectrumPlot({ data, eventId, timestamp, stale }: { data: SpectrumData; eventId: number; timestamp: string; stale: boolean }) {
  const n = data.bin_hz.length;
  if (n === 0) {
    return <p className="text-sm text-muted">The latest spectrum event contained no bins.</p>;
  }
  const fMin = Math.min(...data.bin_hz);
  const fMax = Math.max(...data.bin_hz);
  const pMin = Math.min(...data.power_db);
  const pMax = Math.max(...data.power_db);
  const fSpan = fMax - fMin || 1;
  const pSpan = pMax - pMin || 1;
  const x = (f: number) => ((f - fMin) / fSpan) * W;
  const y = (p: number) => H - ((p - pMin) / pSpan) * H;
  let peak = 0;
  for (let i = 1; i < n; i++) if (data.power_db[i] > data.power_db[peak]) peak = i;
  const barW = Math.max(1, W / n - 1);

  return (
    <figure className="m-0 rounded-pill border border-rule-2 bg-paper-3 p-3">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className={`h-48 w-full ${stale ? 'opacity-60' : ''}`}
        preserveAspectRatio="none"
        aria-hidden="true"
      >
        {data.bin_hz.map((f, i) => (
          <rect
            key={i}
            x={x(f) - barW / 2}
            y={y(data.power_db[i])}
            width={barW}
            height={H - y(data.power_db[i])}
            className="fill-cool"
            fillOpacity={0.8}
          />
        ))}
        {[MARK_HZ, SPACE_HZ].map((f) =>
          f >= fMin && f <= fMax ? (
            <line
              key={f}
              x1={x(f)}
              x2={x(f)}
              y1={0}
              y2={H}
              className="stroke-accent"
              strokeOpacity={0.8}
              strokeDasharray="4 4"
              vectorEffect="non-scaling-stroke"
            />
          ) : null,
        )}
      </svg>
      <figcaption className="mt-2 font-mono text-xs text-muted tabular">
        {n} bins · {fMin}–{fMax} Hz · {data.sample_rate_hz} Hz sample rate · peak {data.bin_hz[peak]} Hz at {data.power_db[peak]} dB ·
        power range {pMin} to {pMax} dB · dashed lines mark reference tones {MARK_HZ} Hz (mark) and {SPACE_HZ} Hz (space) ·
        event #{eventId} · {timestamp}
        {stale ? ' · STALE' : ''}
      </figcaption>
    </figure>
  );
}
