// Live quotes/intraday. The server may name fields slightly differently; normalise here so screens see one shape.
import { getSettings } from '../settings';
import { request } from './client';
import * as mock from './mock';
import type { Intraday, IntradayPoint, Quote } from './types';

type Raw = Record<string, unknown>;
const n = (...v: unknown[]): number | null => { for (const x of v) if (typeof x === 'number' && !Number.isNaN(x)) return x; return null; };
const s = (...v: unknown[]): string | null => { for (const x of v) if (typeof x === 'string' && x) return x; return null; };

export function normQuote(r: Raw, fallbackSymbol = ''): Quote {
  const price = n(r.price, r.last_price, r.ltp, r.last, r.close);
  const prev = n(r.prev_close, r.previous_close);
  let change = n(r.change, r.abs_change);
  if (change === null && price !== null && prev !== null) change = price - prev;
  let pct = n(r.change_pct, r.pct_change, r.change_percent, r.percent_change);
  if (pct === null && change !== null && prev) pct = (change / prev) * 100;
  return {
    symbol: s(r.symbol, r.ticker) ?? fallbackSymbol, name: s(r.name, r.company), currency: s(r.currency),
    price, change, change_pct: pct, prev_close: prev, as_of_ist: s(r.as_of_ist, r.as_of, r.time_ist),
    delayed: typeof r.delayed === 'boolean' ? r.delayed : null, display: (r.display as Quote['display']) ?? null,
  };
}

function normQuotes(raw: unknown): Quote[] {
  const list: unknown = Array.isArray(raw) ? raw : (raw as Raw)?.quotes ?? (raw as Raw)?.results ?? raw;
  if (Array.isArray(list)) return list.filter(Boolean).map((q) => normQuote(q as Raw));
  if (list && typeof list === 'object') return Object.entries(list as Raw).map(([k, v]) => normQuote((v ?? {}) as Raw, k));
  return [];
}

export function normIntraday(raw: Raw, symbol: string, interval: string): Intraday {
  const arr = (raw.points ?? raw.bars ?? raw.candles ?? raw.data ?? []) as Raw[];
  const points: IntradayPoint[] = arr
    .map((p) => ({ t: s(p.time_ist, p.time, p.t, p.ts, p.datetime, p.date) ?? '', price: n(p.price, p.close, p.c) ?? NaN }))
    .filter((p) => p.t && !Number.isNaN(p.price));
  return { symbol: s(raw.symbol, raw.ticker) ?? symbol, interval: s(raw.interval) ?? interval, points,
    as_of_ist: s(raw.as_of_ist, raw.as_of), prev_close: n(raw.prev_close, raw.previous_close), currency: s(raw.currency) };
}

const enc = encodeURIComponent;
const useMock = () => getSettings().mock;

export const live = {
  quote: async (t: string): Promise<Quote> =>
    useMock() ? mock.liveQuote(t) : normQuote(await request<Raw>(`/api/india/quote/${enc(t)}`, { timeoutMs: 30_000 }), t),
  quotes: async (symbols: string[]): Promise<Quote[]> =>
    useMock() ? Promise.all(symbols.map(mock.liveQuote)) : normQuotes(await request(`/api/india/quotes?symbols=${enc(symbols.join(','))}`, { timeoutMs: 45_000 })),
  intraday: async (t: string, interval: '1m' | '5m'): Promise<Intraday> =>
    useMock() ? mock.liveIntraday(t, interval) : normIntraday(await request<Raw>(`/api/india/intraday/${enc(t)}?interval=${interval}`, { timeoutMs: 45_000 }), t, interval),
};
