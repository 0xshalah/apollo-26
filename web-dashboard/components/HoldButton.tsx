'use client';

import { useEffect, useId, useRef, useState, type ReactNode } from 'react';

/**
 * A button that confirms only after it is held for `holdMs`, by pointer or by
 * holding Enter/Space. Releasing early cancels. Assistive-technology clicks
 * (a click with no pointer or key hold behind it) confirm directly, so the
 * control never locks those users out. The hold is a UI affordance; the
 * authorization itself is still the signed AUTH frame checked downstream.
 */
export function HoldButton({
  onConfirm,
  disabled,
  holdMs = 1000,
  hint,
  children,
}: {
  onConfirm: () => void;
  disabled?: boolean;
  holdMs?: number;
  hint: string;
  children: ReactNode;
}) {
  const [holding, setHolding] = useState(false);
  const timer = useRef<number | null>(null);
  const viaInput = useRef(false);
  const disabledRef = useRef(Boolean(disabled));
  const hintId = useId();

  const clear = () => {
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = null;
    setHolding(false);
  };
  const start = () => {
    if (disabled || timer.current !== null) return;
    viaInput.current = true;
    setHolding(true);
    timer.current = window.setTimeout(() => {
      timer.current = null;
      setHolding(false);
      // The button may have been disabled mid-hold (for example by the story runner).
      if (!disabledRef.current) onConfirm();
    }, holdMs);
  };
  const release = () => {
    clear();
    // The click that follows a pointer or key release must not confirm again.
    window.setTimeout(() => {
      viaInput.current = false;
    }, 0);
  };

  useEffect(() => {
    disabledRef.current = Boolean(disabled);
  }, [disabled]);
  useEffect(
    () => () => {
      if (timer.current !== null) window.clearTimeout(timer.current);
    },
    [],
  );
  const active = holding && !disabled;

  return (
    <span className="inline-grid gap-1">
      <button
        type="button"
        className={`btn relative touch-none select-none overflow-hidden ${active ? 'border-accent' : ''}`}
        disabled={disabled}
        onContextMenu={(e) => e.preventDefault()}
        aria-describedby={hintId}
        onPointerDown={(e) => {
          if (e.button !== 0) return;
          e.currentTarget.setPointerCapture?.(e.pointerId);
          start();
        }}
        onPointerUp={release}
        onPointerCancel={release}
        onLostPointerCapture={release}
        onKeyDown={(e) => {
          if ((e.key === 'Enter' || e.key === ' ') && !e.repeat) {
            e.preventDefault();
            start();
          } else if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
          }
        }}
        onKeyUp={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            release();
          }
        }}
        onBlur={release}
        onClick={() => {
          if (!viaInput.current && !disabled) onConfirm();
        }}
      >
        <span
          aria-hidden="true"
          className="absolute inset-0 origin-left bg-accent-soft"
          style={{
            transform: `scaleX(${active ? 1 : 0})`,
            transition: active ? `transform ${holdMs}ms linear` : 'transform 120ms ease-out',
          }}
        />
        <span className="relative">{active ? 'Keep holding…' : children}</span>
      </button>
      <span id={hintId} className="text-xs text-muted">
        {hint}
      </span>
    </span>
  );
}
