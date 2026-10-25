import { IonItem, IonLabel, IonList, IonNote, IonProgressBar } from '@ionic/react';
import React from 'react';

export const pct = (x: number | null | undefined, d = 1) => (x === null || x === undefined ? '—' : `${(x * 100).toFixed(d)}%`);
export const num = (x: number | null | undefined, d = 2) => (x === null || x === undefined ? '—' : x.toLocaleString(undefined, { maximumFractionDigits: d }));
export const inr = (x: number | null | undefined) => (x === null || x === undefined ? '—' : '₹' + Math.round(x).toLocaleString('en-IN'));
export const titleCase = (s: string) => s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

/** Horizontal gauge with a threshold marker. */
export const ProbabilityGauge: React.FC<{ value: number; threshold: number }> = ({ value, threshold }) => {
  const color = value >= threshold ? 'danger' : value >= threshold / 2 ? 'warning' : 'success';
  return (
    <div className="gauge">
      <div className="gauge-value">{pct(value)}</div>
      <div className="gauge-track">
        <IonProgressBar value={value} color={color} />
        <div className="gauge-threshold" style={{ left: `${threshold * 100}%` }} title={`threshold ${pct(threshold)}`} />
      </div>
      <div className="gauge-scale"><span>0%</span><span>threshold {pct(threshold)}</span><span>100%</span></div>
    </div>
  );
};

export const KeyValueList: React.FC<{ rows: [string, React.ReactNode][] }> = ({ rows }) => (
  <IonList inset={false} lines="full">
    {rows.map(([k, v]) => (
      <IonItem key={k}><IonLabel>{k}</IonLabel><IonNote slot="end" className="kv-value">{v}</IonNote></IonItem>
    ))}
  </IonList>
);

export const BarRow: React.FC<{ label: string; value: number; color?: string }> = ({ label, value, color = 'primary' }) => (
  <div className="bar-row">
    <div className="bar-row-head"><span>{label}</span><strong>{pct(value)}</strong></div>
    <IonProgressBar value={value} color={color} />
  </div>
);

const INR_SUFFIX = /\.(NS|BO)$/i;
const INR_INDICES = new Set(['^NSEI', '^BSESN', '^NSEBANK', '^CNXIT', '^NSMIDCP']);
/** Currency for a ticker when the server didn't say: Indian listings and indices are INR. */
export const currencyOf = (ticker: string, given?: string | null) =>
  given || (INR_SUFFIX.test(ticker) || INR_INDICES.has(ticker.toUpperCase()) ? 'INR' : 'USD');

/** ₹12,34,567.80 for INR (Indian grouping), $1,234.50 for USD, else "1,234.50 EUR". */
export function money(x: number | null | undefined, currency?: string | null, digits = 2): string {
  if (x === null || x === undefined || Number.isNaN(x)) return '—';
  const c = (currency || '').toUpperCase();
  if (c === 'INR') return '₹' + x.toLocaleString('en-IN', { minimumFractionDigits: digits, maximumFractionDigits: digits });
  const s = x.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
  if (c === 'USD') return '$' + s;
  return c ? `${s} ${c}` : s;
}

/** Today's date in India as "YYYY-MM-DD". */
export function istToday(): string {
  const ist = new Date(Date.now() + 330 * 60000);
  return ist.toISOString().slice(0, 10);
}
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const DOW = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
/**
 * IST ISO-8601 from the server ("2026-10-23T15:29:00+05:30") -> "23 Oct, 15:29 IST", or "15:29 IST" when it is today (IST).
 * `withDay` gives "Mon 09:15 IST" (for next open/close). Anything that isn't ISO is returned unchanged.
 */
export function fmtIst(v: string | null | undefined, withDay = false): string | null {
  if (!v) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/.exec(v);
  if (!m) return v;
  const [, y, mo, d, hh, mm] = m;
  const hm = `${hh}:${mm} IST`;
  const today = istToday() === `${y}-${mo}-${d}`;
  if (withDay) {
    const dow = DOW[new Date(Date.UTC(+y, +mo - 1, +d)).getUTCDay()];
    return today ? `today ${hm}` : `${dow} ${hm}`;
  }
  return today ? hm : `${+d} ${MON[+mo - 1]}, ${hm}`;
}
