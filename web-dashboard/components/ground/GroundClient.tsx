'use client';

import { useId, useRef, useState, useSyncExternalStore, type InputHTMLAttributes } from 'react';
import vectors from '../../../contracts/vectors/frames.json';
import { Chip, Panel } from '@/components/Panel';
import { FrameInspector } from '@/components/ground/FrameInspector';
import { encodeFrame, toHex, utf8, webCryptoSigner, type FrameFields } from '@/lib/frame';
import {
  ALWAYS_CRITICAL,
  CARRIES_PAYLOAD,
  COMMAND_KINDS,
  COMMAND_LABELS,
  parseAuthForm,
  parseCommandForm,
  parseStoredSeq,
  SEQ_STORAGE_KEY,
  type CommandKind,
  type FieldErrors,
} from '@/lib/ground-form';
import { durationMs, transmitFrame } from '@/lib/modem';

type Mode = 'COMMAND' | 'AUTH';
type Phase = 'editing' | 'invalid' | 'signing' | 'ready' | 'transmitting' | 'completed' | 'failed';

interface Encoded {
  bytes: Uint8Array;
  hex: string;
  fields: FrameFields;
}

/* Last transmitted seq from this browser (localStorage). A convenience only; the daemon owns freshness. */
const seqListeners = new Set<() => void>();
function subscribeSeq(cb: () => void) {
  seqListeners.add(cb);
  window.addEventListener('storage', cb);
  return () => {
    seqListeners.delete(cb);
    window.removeEventListener('storage', cb);
  };
}
function readSeqSnapshot(): string | null {
  try {
    return window.localStorage.getItem(SEQ_STORAGE_KEY);
  } catch {
    return null;
  }
}
function writeSeq(seq: number) {
  try {
    window.localStorage.setItem(SEQ_STORAGE_KEY, String(seq));
  } catch {
    /* storage unavailable: convenience feature only */
  }
  seqListeners.forEach((l) => l());
}

const PHASE_LABEL: Record<Phase, string> = {
  editing: 'EDITING',
  invalid: 'INVALID INPUT',
  signing: 'SIGNING',
  ready: 'READY TO TRANSMIT',
  transmitting: 'TRANSMITTING',
  completed: 'PLAYBACK COMPLETED',
  failed: 'FAILED',
};

function Field({
  label,
  hint,
  error,
  ...input
}: { label: string; hint?: string; error?: string } & InputHTMLAttributes<HTMLInputElement>) {
  const id = useId();
  const describedBy = [hint ? `${id}-hint` : '', error ? `${id}-err` : ''].filter(Boolean).join(' ') || undefined;
  return (
    <div className="grid min-w-0 gap-1">
      <label htmlFor={id} className="text-xs font-medium text-ink-2">
        {label}
      </label>
      <input
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        className="input font-mono tabular"
        {...input}
      />
      {hint ? (
        <p id={`${id}-hint`} className="text-xs text-muted">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={`${id}-err`} className="text-xs font-medium text-bad">
          Error: {error}
        </p>
      ) : null}
    </div>
  );
}

const btnPrimary = 'btn btn-amber';
const btnGhost = 'btn';

/** Short labels for the quick-command buttons (mockup preset row). */
const QUICK_LABEL: Record<CommandKind, string> = {
  V37_P40: 'P40 burn (V37 N00)',
  V25_N81: 'Load R1–R3 (V25 N81)',
  V37_P00: 'Idle P00 (V37 N00)',
  V34: 'Terminate (V34)',
};

export function GroundClient() {
  const [mode, setMode] = useState<Mode>('COMMAND');
  const [kind, setKind] = useState<CommandKind>('V37_P40');
  const [seq, setSeq] = useState('');
  const [r1, setR1] = useState('0');
  const [r2, setR2] = useState('0');
  const [deltaV, setDeltaV] = useState('0');
  const [extraCritical, setExtraCritical] = useState(false);
  const [authSeq, setAuthSeq] = useState('');
  const [refSeq, setRefSeq] = useState('');
  const [linkKey, setLinkKey] = useState('');
  const [operatorKey, setOperatorKey] = useState('');
  const [showKeys, setShowKeys] = useState(false);
  const [demoKeys, setDemoKeys] = useState(false);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [warnings, setWarnings] = useState<string[]>([]);
  const [phase, setPhase] = useState<Phase>('editing');
  const [message, setMessage] = useState('');
  const [encoded, setEncoded] = useState<Encoded | null>(null);
  const [lastCommandSeq, setLastCommandSeq] = useState<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const storedRaw = useSyncExternalStore(subscribeSeq, readSeqSnapshot, () => null);
  const lastTransmitted = parseStoredSeq(storedRaw);

  /** Any edit invalidates the signed frame, so preview and transmission never diverge. */
  const edit = <T,>(setter: (v: T) => void) => (v: T) => {
    setter(v);
    if (phase !== 'transmitting') {
      setEncoded(null);
      setPhase('editing');
      setMessage('');
    }
  };

  const activeSeqText = mode === 'COMMAND' ? seq : authSeq;
  const activeSeqNum = /^\d+$/.test(activeSeqText.trim()) ? Number(activeSeqText) : null;
  const seqNotIncreasing = lastTransmitted !== null && activeSeqNum !== null && activeSeqNum <= lastTransmitted;

  async function onEncode() {
    const parsed =
      mode === 'COMMAND'
        ? parseCommandForm({ kind, seq, r1, r2, deltaV, extraCritical })
        : parseAuthForm({ seq: authSeq, refSeq });
    const key = mode === 'COMMAND' ? linkKey : operatorKey;
    if (!parsed.ok) {
      setErrors(parsed.errors);
      setWarnings([]);
      setPhase('invalid');
      setMessage('Fix the highlighted fields. Nothing was signed or transmitted.');
      return;
    }
    if (key.length === 0) {
      setErrors({});
      setPhase('invalid');
      setMessage(`Enter the ${mode === 'COMMAND' ? 'link' : 'operator'} key before signing.`);
      return;
    }
    setErrors({});
    setWarnings(parsed.warnings);
    const subtle = globalThis.crypto?.subtle;
    if (!subtle) {
      setPhase('failed');
      setMessage('Web Crypto is unavailable. Open this page over HTTPS or from 127.0.0.1.');
      return;
    }
    setPhase('signing');
    const keyBytes = utf8(key);
    try {
      const bytes = await encodeFrame(parsed.fields, keyBytes, webCryptoSigner(subtle));
      const frozen = bytes.slice();
      setEncoded({ bytes: frozen, hex: toHex(frozen), fields: parsed.fields });
      setPhase('ready');
      setMessage(`${mode} seq ${parsed.fields.seq} signed. Review the bytes, then transmit.`);
    } catch (e) {
      setPhase('failed');
      setMessage(`Signing failed: ${e instanceof Error ? e.message : 'unknown error'}`);
    } finally {
      keyBytes.fill(0);
    }
  }

  async function onTransmit() {
    if (!encoded) return;
    const controller = new AbortController();
    abortRef.current = controller;
    setPhase('transmitting');
    setMessage(`Transmitting ${encoded.fields.frame_type} seq ${encoded.fields.seq}…`);
    const Ctor =
      window.AudioContext ??
      (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    const outcome = await transmitFrame(encoded.bytes, Ctor, controller.signal);
    abortRef.current = null;
    if (outcome.kind === 'completed') {
      setPhase('completed');
      if (lastTransmitted === null || encoded.fields.seq > lastTransmitted) writeSeq(encoded.fields.seq);
      if (encoded.fields.frame_type === 'COMMAND') setLastCommandSeq(encoded.fields.seq);
      setMessage(
        `Browser playback completed (${Math.round(outcome.durationMs)} ms at ${outcome.sampleRate} Hz). ` +
          'This does not mean the daemon accepted the frame; check the console audit log.',
      );
    } else if (outcome.kind === 'cancelled') {
      setPhase('failed');
      setMessage('Transmission cancelled. The signed frame is kept; you can transmit again.');
    } else {
      setPhase('failed');
      setMessage(`${outcome.message} The signed frame is kept.`);
    }
  }

  function onCancel() {
    abortRef.current?.abort();
  }

  function prepareAuth() {
    if (lastCommandSeq === null) return;
    setMode('AUTH');
    setRefSeq(String(lastCommandSeq));
    setAuthSeq(String(lastCommandSeq + 1));
    setEncoded(null);
    setPhase('editing');
    setMessage(`AUTH prepared for COMMAND seq ${lastCommandSeq}.`);
  }

  function applyDemoKeys() {
    setLinkKey(vectors.demo_keys.link);
    setOperatorKey(vectors.demo_keys.operator);
    setDemoKeys(true);
    setEncoded(null);
    setPhase('editing');
  }

  function clearKeys() {
    setLinkKey('');
    setOperatorKey('');
    setDemoKeys(false);
    setShowKeys(false);
  }

  const busy = phase === 'signing' || phase === 'transmitting';
  const payload = CARRIES_PAYLOAD[kind];
  const estMs = encoded ? Math.round(durationMs(encoded.bytes, 48000)) : null;

  return (
    <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,26rem)_minmax(0,1fr)]">
      <div className="min-w-0 space-y-6">
        <Panel id="compose" title="Compose frame">
          <fieldset disabled={busy} className="space-y-4">
            <legend className="sr-only">Frame fields</legend>
            <div role="radiogroup" aria-label="Frame type" className="seg-group grid w-full grid-cols-2">
              {(['COMMAND', 'AUTH'] as const).map((m) => (
                <label key={m} className="text-sm">
                  <input
                    type="radio"
                    name="frame-type"
                    value={m}
                    checked={mode === m}
                    onChange={() => edit(setMode)(m)}
                    className="sr-only"
                  />
                  {m}
                </label>
              ))}
            </div>

            {mode === 'COMMAND' ? (
              <>
                <div className="grid gap-2">
                  <p id="cmd-kind-label" className="text-xs font-medium text-ink-2">
                    Command (v1 vocabulary)
                  </p>
                  <div role="group" aria-labelledby="cmd-kind-label" className="grid gap-2 sm:grid-cols-2">
                    {COMMAND_KINDS.map((k) => (
                      <button
                        key={k}
                        type="button"
                        aria-pressed={kind === k}
                        onClick={() => edit(setKind)(k)}
                        title={COMMAND_LABELS[k]}
                        className={kind === k ? 'btn btn-amber' : 'btn'}
                      >
                        {QUICK_LABEL[k]}
                      </button>
                    ))}
                  </div>
                  <p className="text-xs text-muted">{COMMAND_LABELS[kind]}</p>
                </div>
                <Field
                  label="Sequence (seq)"
                  inputMode="numeric"
                  autoComplete="off"
                  value={seq}
                  onChange={(e) => edit(setSeq)(e.target.value)}
                  error={errors.seq}
                  hint="Global across COMMAND and AUTH. Must exceed the daemon's last accepted seq; the daemon is the authority."
                />
                {payload ? (
                  <div className="grid gap-4 sm:grid-cols-3 lg:grid-cols-1 xl:grid-cols-3">
                    <Field
                      label="R1 azimuth"
                      inputMode="numeric"
                      value={r1}
                      onChange={(e) => edit(setR1)(e.target.value)}
                      error={errors.r1}
                      hint="int16, 0.01° units"
                    />
                    <Field
                      label="R2 elevation"
                      inputMode="numeric"
                      value={r2}
                      onChange={(e) => edit(setR2)(e.target.value)}
                      error={errors.r2}
                      hint="int16, 0.01° units"
                    />
                    <Field
                      label="Delta-v"
                      inputMode="numeric"
                      value={deltaV}
                      onChange={(e) => edit(setDeltaV)(e.target.value)}
                      error={errors.deltaV}
                      hint="int32, 0.1 ft/s units"
                    />
                  </div>
                ) : (
                  <p className="text-xs text-muted">This command carries no R1/R2/delta-v payload; those fields are encoded as 0.</p>
                )}
                <div className="rounded-pill border border-rule-2 bg-paper-3 p-3 text-xs text-ink-2">
                  {ALWAYS_CRITICAL[kind] ? (
                    <p>
                      <Chip tone="info">CRITICAL set</Chip> This command is always marked CRITICAL by the sender. The flag is
                      frame metadata, not authorization: the MCP safety gate recomputes it and requires a valid AUTH.
                    </p>
                  ) : (
                    <label className="flex min-h-11 items-center gap-3">
                      <input
                        type="checkbox"
                        checked={extraCritical}
                        onChange={(e) => edit(setExtraCritical)(e.target.checked)}
                        className="h-5 w-5 accent-accent"
                      />
                      Also mark this frame CRITICAL (metadata only; the safety gate decides independently).
                    </label>
                  )}
                </div>
              </>
            ) : (
              <>
                <Field
                  label="Sequence (seq)"
                  inputMode="numeric"
                  autoComplete="off"
                  value={authSeq}
                  onChange={(e) => edit(setAuthSeq)(e.target.value)}
                  error={errors.seq}
                  hint="Must be newer than the referenced COMMAND and the daemon's last accepted seq."
                />
                <Field
                  label="Referenced COMMAND seq (ref_seq)"
                  inputMode="numeric"
                  autoComplete="off"
                  value={refSeq}
                  onChange={(e) => edit(setRefSeq)(e.target.value)}
                  error={errors.refSeq}
                  hint="AUTH authorizes exactly one held COMMAND, once. Reuse is rejected."
                />
                <p className="text-xs text-muted">
                  AUTH frames always encode flags, verb, noun, program, R1, R2, and delta-v as 0 and are signed with the
                  operator key.
                </p>
              </>
            )}

            <div className="border-t border-rule pt-3 text-xs text-muted">
              {lastTransmitted !== null ? (
                <div className="flex flex-wrap items-center gap-2">
                  <span>
                    Last seq transmitted from this browser: <span className="font-mono text-ink">{lastTransmitted}</span>{' '}
                    (stored locally, not authoritative)
                  </span>
                  <button
                    type="button"
                    className={btnGhost}
                    onClick={() =>
                      mode === 'COMMAND'
                        ? edit(setSeq)(String(lastTransmitted + 1))
                        : edit(setAuthSeq)(String(lastTransmitted + 1))
                    }
                  >
                    Use {lastTransmitted + 1}
                  </button>
                </div>
              ) : (
                <span>No sequence transmitted from this browser yet.</span>
              )}
              {seqNotIncreasing ? (
                <p className="mt-2 font-medium text-accent" role="note">
                  Warning: seq {activeSeqNum} is not greater than the last seq sent from this browser. The daemon will
                  likely reject it as REPLAY.
                </p>
              ) : null}
            </div>
          </fieldset>
        </Panel>

        <Panel
          id="keys"
          title="Signing keys (session only)"
          aside={demoKeys ? <Chip tone="warn">Public demo keys</Chip> : null}
        >
          <div className="space-y-4">
            <p className="text-xs text-muted">
              Keys stay in this tab&apos;s memory. They are never stored, sent over the network, or included in the page
              bundle. COMMAND uses the link key; AUTH uses the operator key.
            </p>
            <Field
              label="Link key (APOLLO26_LINK_KEY)"
              type={showKeys ? 'text' : 'password'}
              autoComplete="off"
              spellCheck={false}
              value={linkKey}
              onChange={(e) => {
                setDemoKeys(false);
                edit(setLinkKey)(e.target.value);
              }}
              disabled={busy}
            />
            <Field
              label="Operator key (APOLLO26_OPERATOR_KEY)"
              type={showKeys ? 'text' : 'password'}
              autoComplete="off"
              spellCheck={false}
              value={operatorKey}
              onChange={(e) => {
                setDemoKeys(false);
                edit(setOperatorKey)(e.target.value);
              }}
              disabled={busy}
            />
            <div className="flex flex-wrap gap-2">
              <button type="button" className={btnGhost} onClick={() => setShowKeys((s) => !s)} aria-pressed={showKeys}>
                {showKeys ? 'Hide keys' : 'Show keys'}
              </button>
              <button type="button" className={btnGhost} onClick={clearKeys} disabled={busy}>
                Clear keys
              </button>
            </div>
            <div className="rounded-pill border border-dashed border-rule-2 bg-paper-3 p-3">
              <p className="text-xs text-ink-2">
                Public demo keys come from the protocol contract. They are not secret: anyone can forge frames with them.
                Use them only with a daemon configured for the public demo.
              </p>
              <button type="button" className={`${btnGhost} mt-2`} onClick={applyDemoKeys} disabled={busy}>
                Use public demo keys
              </button>
            </div>
          </div>
        </Panel>
      </div>

      <div className="min-w-0 space-y-6">
        <Panel
          id="transmit"
          title="Sign and transmit"
          aside={<Chip tone={phase === 'failed' || phase === 'invalid' ? 'bad' : phase === 'completed' ? 'ok' : phase === 'ready' ? 'warn' : 'muted'}>{PHASE_LABEL[phase]}</Chip>}
        >
          <div className="grid gap-2 sm:grid-cols-2">
            <button type="button" className={encoded ? btnGhost : btnPrimary} onClick={onEncode} disabled={busy}>
              Encode &amp; sign
            </button>
            <button type="button" className={btnPrimary} onClick={onTransmit} disabled={!encoded || busy}>
              Modulate &amp; transmit{estMs !== null ? ` (${(estMs / 1000).toFixed(2)} s)` : ''}
            </button>
            {phase === 'transmitting' ? (
              <button type="button" className={btnGhost} onClick={onCancel}>
                Cancel
              </button>
            ) : null}
            {phase === 'completed' && encoded?.fields.frame_type === 'COMMAND' && encoded.fields.critical ? (
              <button type="button" className={btnGhost} onClick={prepareAuth}>
                Prepare AUTH for seq {encoded.fields.seq}
              </button>
            ) : null}
          </div>
          <p role="status" aria-live="polite" className="mt-3 min-h-5 text-sm text-ink-2">
            {message}
          </p>
          {warnings.length > 0 ? (
            <ul className="mt-2 space-y-1 text-xs text-accent" aria-label="Warnings">
              {warnings.map((w) => (
                <li key={w}>Warning: {w}</li>
              ))}
            </ul>
          ) : null}
          <p className="mt-3 text-xs text-muted">
            Turn the phone volume up and hold the speaker near the laptop microphone. The browser must allow audio output
            from a tap; on iOS, disable silent mode.
          </p>
        </Panel>

        <Panel id="preview" title="Frame preview" aside={<Chip tone="warn">Ground station</Chip>}>
          {encoded ? (
            <FrameInspector bytes={encoded.bytes} hex={encoded.hex} />
          ) : (
            <div className="grid min-h-32 place-items-center rounded-pill border border-rule-2 bg-paper-3 p-6 text-center">
              <p className="text-sm text-muted">No signed frame. Choose Encode &amp; sign to see the exact bytes and 8N1 bits.</p>
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}
