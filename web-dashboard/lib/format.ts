/** Integer-only display helpers (no floating-point rounding of wire values). */

export const pad2 = (n: number): string => String(n).padStart(2, '0');

/** DSKY register style: explicit sign + five digits, e.g. +01250. */
export function signed5(n: number): string {
  const sign = n < 0 ? '-' : '+';
  return `${sign}${String(Math.abs(n)).padStart(5, '0')}`;
}

/** Fixed-point with `decimals` implied digits, e.g. (1250, 2) → "12.50". */
export function fixedPoint(n: number, decimals: number): string {
  const neg = n < 0;
  const digits = String(Math.abs(n)).padStart(decimals + 1, '0');
  const intPart = digits.slice(0, digits.length - decimals);
  const frac = digits.slice(digits.length - decimals);
  return `${neg ? '-' : ''}${intPart}.${frac}`;
}

export const centidegrees = (n: number): string => `${fixedPoint(n, 2)}°`;
export const tenthsFps = (n: number): string => `${fixedPoint(n, 1)} ft/s`;

export function hexBytes(bytes: Uint8Array, offset: number, length: number): string {
  return Array.from(bytes.subarray(offset, offset + length), (b) => b.toString(16).padStart(2, '0')).join(' ');
}
