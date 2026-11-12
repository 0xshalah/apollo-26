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
    <div className="min-w-0">
      <label htmlFor={id} className="block text-xs uppercase tracking-[0.14em] text-electrum/80">
        {label}
      </label>
      <input
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        className="mt-1 block min-h-11 w-full border border-electrum/25 bg-lunar-800 px-3 font-mono text-electrum tabular placeholder:text-electrum/40 hover:border-electrum/50 disabled:opacity-50 aria-[invalid=true]:border-electrum aria-[invalid=true]:border-2"
        {...input}
      />
      {hint ? (
        <p id={`${id}-hint`} className="mt-1 text-xs text-electrum/70">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={`${id}-err`} className="mt-1 text-xs font-semibold text-electrum">
          Error: {error}
        </p>
      ) : null}
    </div>
  );
}

const btn =
  'inline-flex min-h-11 items-center justify-center border px-4 text-sm font-semibold uppercase tracking-[0.12em] disabled:cursor-not-allowed disabled:opacity-50';
const btnPrimary = `${btn} border-electrum bg-electrum text-void hover:bg-electrum/90`;
const btnGhost = `${btn} border-electrum/40 text-electrum hover:border-electrum hover:bg-lunar-800`;

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
            <div role="radiogroup" aria-label="Frame type" className="grid grid-cols-2 gap-px bg-electrum/15">
              {(['COMMAND', 'AUTH'] as const).map((m) => (
                <label
                  key={m}
                  className="flex min-h-11 cursor-pointer items-center justify-center gap-2 bg-lunar-900 px-3 text-sm font-semibold uppercase tracking-[0.14em] has-[:checked]:bg-electrum has-[:checked]:text-void has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-electrum"
                >
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
                <div>
                  <label htmlFor="cmd-kind" className="block text-xs uppercase tracking-[0.14em] text-electrum/80">
                    Command (v1 vocabulary)
                  </label>
                  <select
                    id="cmd-kind"
                    value={kind}
                    onChange={(e) => edit(setKind)(e.target.value as CommandKind)}
                    className="mt-1 block min-h-11 w-full min-w-0 max-w-full border border-electrum/25 bg-lunar-800 px-3 text-sm text-electrum"
                  >
                    {COMMAND_KINDS.map((k) => (
                      <option key={k} value={k}>
                        {COMMAND_LABELS[k]}
                      </option>
                    ))}
                  </select>
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
                  <p className="text-xs text-electrum/70">This command carries no R1/R2/delta-v payload; those fields are encoded as 0.</p>
                )}
                <div className="border border-electrum/15 p-3 text-xs text-electrum/80">
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
                        className="h-5 w-5 accent-electrum"
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
                <p className="text-xs text-electrum/70">
                  AUTH frames always encode flags, verb, noun, program, R1, R2, and delta-v as 0 and are signed with the
                  operator key.
                </p>
              </>
            )}

            <div className="border-t border-electrum/15 pt-3 text-xs text-electrum/75">
              {lastTransmitted !== null ? (
                <div className="flex flex-wrap items-center gap-2">
                  <span>
                    Last seq transmitted from this browser: <span className="font-mono text-electrum">{lastTransmitted}</span>{' '}
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
                <p className="mt-2 font-semibold text-electrum" role="note">
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
            <p className="text-xs text-electrum/75">
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
            <div className="border border-dashed border-electrum/30 p-3">
              <p className="text-xs text-electrum/80">
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
          aside={<Chip tone={phase === 'failed' || phase === 'invalid' ? 'warn' : phase === 'completed' ? 'ok' : 'muted'}>{PHASE_LABEL[phase]}</Chip>}
        >
          <div className="flex flex-wrap gap-2">
            <button type="button" className={btnPrimary} onClick={onEncode} disabled={busy}>
              Encode &amp; sign
            </button>
            <button type="button" className={btnPrimary} onClick={onTransmit} disabled={!encoded || busy}>
              Transmit{estMs !== null ? ` (${(estMs / 1000).toFixed(2)} s)` : ''}
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
          <p role="status" aria-live="polite" className="mt-3 min-h-5 text-sm text-electrum/90">
            {message}
          </p>
          {warnings.length > 0 ? (
            <ul className="mt-2 space-y-1 text-xs text-electrum" aria-label="Warnings">
              {warnings.map((w) => (
                <li key={w}>Warning: {w}</li>
              ))}
            </ul>
          ) : null}
          <p className="mt-3 text-xs text-electrum/70">
            Turn the phone volume up and hold the speaker near the laptop microphone. The browser must allow audio output
            from a tap; on iOS, disable silent mode.
          </p>
        </Panel>

        <Panel id="preview" title="Frame preview" ticks>
          {encoded ? (
            <FrameInspector bytes={encoded.bytes} hex={encoded.hex} />
          ) : (
            <p className="text-sm text-electrum/70">No signed frame. Choose Encode &amp; sign to see the exact bytes and 8N1 bits.</p>
          )}
        </Panel>
      </div>
    </div>
  );
}
