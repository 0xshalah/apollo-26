'use client';

import { useEffect, useRef } from 'react';
import { MARK_HZ, SPACE_HZ } from '@/lib/modem';
import { barForHz, dominantTone, SCOPE_BAND, scopeLevels } from '@/lib/scope';

const TONE_TEXT = { MARK: `Mark ${MARK_HZ} Hz`, SPACE: `Space ${SPACE_HZ} Hz`, NONE: 'No tone' } as const;

function token(name: string) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/**
 * Live spectrum of the tones being played, read from the AnalyserNode that
 * `transmitFrame` places in front of the speakers. With no analyser it draws
 * nothing and says so; it never animates without real audio.
 */
export function ToneScope({ analyser, className = '' }: { analyser: AnalyserNode | null; className?: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const toneRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx) return;
    const colors = { bar: token('--color-cool'), marker: token('--color-rule-2'), rule: token('--color-rule') };

    const size = () => {
      const ratio = window.devicePixelRatio || 1;
      canvas.width = Math.max(1, Math.round(canvas.clientWidth * ratio));
      canvas.height = Math.max(1, Math.round(canvas.clientHeight * ratio));
    };
    const drawFrame = (levels: number[] | null) => {
      const { width, height } = canvas;
      ctx.clearRect(0, 0, width, height);
      ctx.fillStyle = colors.rule;
      ctx.fillRect(0, height - 1, width, 1);
      const slot = width / SCOPE_BAND.bars;
      ctx.fillStyle = colors.marker;
      for (const hz of [MARK_HZ, SPACE_HZ]) {
        ctx.fillRect(Math.round((barForHz(hz) + 0.5) * slot), 0, 1, height);
      }
      if (!levels) return;
      ctx.fillStyle = colors.bar;
      levels.forEach((v, i) => {
        const h = Math.round(v * (height - 2));
        if (h > 0) ctx.fillRect(Math.round(i * slot + 1), height - 1 - h, Math.max(1, Math.round(slot - 2)), h);
      });
    };

    size();
    if (!analyser) {
      drawFrame(null);
      if (toneRef.current) toneRef.current.textContent = 'Idle';
      return;
    }
    const rate = analyser.context.sampleRate;
    const data = new Float32Array(analyser.frequencyBinCount);
    let raf = 0;
    let lastLabel = 0;
    const loop = (t: number) => {
      analyser.getFloatFrequencyData(data);
      drawFrame(scopeLevels(data, rate, analyser.fftSize));
      if (t - lastLabel > 120 && toneRef.current) {
        lastLabel = t;
        toneRef.current.textContent = TONE_TEXT[dominantTone(data, rate, analyser.fftSize, MARK_HZ, SPACE_HZ)];
      }
      raf = window.requestAnimationFrame(loop);
    };
    raf = window.requestAnimationFrame(loop);
    return () => window.cancelAnimationFrame(raf);
  }, [analyser]);

  return (
    <figure className={`m-0 rounded-pill border border-rule bg-paper-3 p-3 ${className}`}>
      <div className="flex items-center justify-between gap-2 text-xs">
        <span className="text-muted">Tone scope</span>
        <span ref={toneRef} className="font-mono text-ink-2 tabular">
          Idle
        </span>
      </div>
      <canvas ref={canvasRef} aria-hidden="true" className="mt-2 block h-16 w-full" />
      <figcaption className="mt-2 flex flex-wrap justify-between gap-x-3 text-xs text-muted">
        <span>
          Guides at mark {MARK_HZ} Hz and space {SPACE_HZ} Hz
        </span>
        <span>Read live from the Web Audio analyser while tones play.</span>
      </figcaption>
    </figure>
  );
}
