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
        <div className="grid min-h-48 place-items-center rounded-pill border border-rule-2 bg-paper-3 p-6 text-center">
          <p className="max-w-sm text-sm text-muted">
            {disconnected ? 'DISCONNECTED. ' : ''}No audio.spectrum event received. The daemon publishes the spectrum only while it
            listens to a microphone; nothing is plotted until it sends one.
          </p>
        </div>
      ) : (
        <SpectrumPlot data={spectrum.value} eventId={spectrum.eventId} timestamp={spectrum.timestamp} stale={spectrum.kind === 'stale'} />
      )}
    </Panel>
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
