// Live quotes/intraday. The server may name fields slightly differently; normalise here so screens see one shape.
import { getSettings } from '../settings';
import { request } from './client';
import * as mock from './mock';
import type { Intraday, IntradayPoint, Quote, QuotesResult } from './types';

type Raw = Record<string, unknown>;
const n = (...v: unknown[]): number | null => { for (const x of v) if (typeof x === 'number' && !Number.isNaN(x)) return x; return null; };
const s = (...v: unknown[]): string | null => { for (const x of v) if (typeof x === 'string' && x) return x; return null; };

const b = (v: unknown): boolean | null => (typeof v === 'boolean' ? v : null);

/** API.md section 8 quote object; tolerant of a few alternative names used by older servers. */
export function normQuote(r: Raw, fallbackSymbol = ''): Quote {
  const price = n(r.price, r.last_price, r.ltp, r.last, r.close);
  const prev = n(r.prev_close, r.previous_close);
  let change = n(r.change, r.abs_change);
  if (change === null && price !== null && prev !== null) change = price - prev;
  let pct = n(r.change_pct, r.pct_change, r.change_percent, r.percent_change);
  if (pct === null && change !== null && prev) pct = (change / prev) * 100;
  const note = s(r.delayed_note);
  return {
    symbol: s(r.symbol, r.normalized_ticker, r.ticker) ?? fallbackSymbol, name: s(r.name, r.company), currency: s(r.currency),
    price, change, change_pct: pct, prev_close: prev,
    open: n(r.open), high: n(r.high), low: n(r.low), volume: n(r.volume),
    as_of_ist: s(r.as_of_ist, r.as_of, r.time_ist), market_open: b(r.market_open),
    delayed: b(r.delayed) ?? (note || /delay/i.test(s(r.source) ?? '') ? true : null),
    source: s(r.source), delayed_note: note,
    display: (r.display && typeof r.display === 'object' ? r.display : null) as Quote['display'],
  };
}

export function normQuotes(raw: unknown): QuotesResult {
  const obj = (raw && typeof raw === 'object' && !Array.isArray(raw) ? raw : {}) as Raw;
  const list: unknown = Array.isArray(raw) ? raw : obj.quotes ?? obj.results ?? raw;
  const errors = Array.isArray(obj.errors) ? (obj.errors as Raw[]).map((e) => ({ symbol: s(e.symbol) ?? '', detail: s(e.detail) ?? 'No data' })) : [];
  if (Array.isArray(list)) return { quotes: list.filter(Boolean).map((q) => normQuote(q as Raw)), errors };
  if (list && typeof list === 'object') {
    return { quotes: Object.entries(list as Raw).filter(([k]) => k !== 'errors').map(([k, v]) => normQuote((v ?? {}) as Raw, k)), errors };
  }
  return { quotes: [], errors };
}

/** API.md: {"symbol", "interval", "session_date", "market_open", "bars": [{"time_ist", "open", "high", "low", "close", "volume"}]} */
export function normIntraday(raw: Raw, symbol: string, interval: string): Intraday {
  const arr = (raw.bars ?? raw.points ?? raw.candles ?? raw.data ?? []) as Raw[];
  const points: IntradayPoint[] = arr
    .map((p) => ({ t: s(p.time_ist, p.time, p.t, p.ts, p.datetime, p.date) ?? '', price: n(p.close, p.price, p.c) ?? NaN }))
    .filter((p) => p.t && !Number.isNaN(p.price));
  return {
    symbol: s(raw.symbol, raw.normalized_ticker, raw.ticker) ?? symbol, interval: s(raw.interval) ?? interval, points,
    session_date: s(raw.session_date), market_open: b(raw.market_open), source: s(raw.source),
    as_of_ist: s(raw.as_of_ist, raw.as_of) ?? (points.length ? points[points.length - 1].t : null),
    prev_close: n(raw.prev_close, raw.previous_close), currency: s(raw.currency),
  };
}

const enc = encodeURIComponent;
const useMock = () => getSettings().mock;

export const live = {
  quote: async (t: string): Promise<Quote> =>
    useMock() ? mock.liveQuote(t) : normQuote(await request<Raw>(`/api/india/quote/${enc(t)}`, { timeoutMs: 30_000 }), t),
  /** The server accepts 1-20 symbols per call; longer lists are split. Failed symbols land in `errors`. */
  quotes: async (symbols: string[]): Promise<QuotesResult> => {
    if (useMock()) return { quotes: await Promise.all(symbols.map(mock.liveQuote)), errors: [] };
    const chunks: string[][] = [];
    for (let i = 0; i < symbols.length; i += 20) chunks.push(symbols.slice(i, i + 20));
    const parts = await Promise.all(chunks.map(async (c) => normQuotes(await request(`/api/india/quotes?symbols=${enc(c.join(','))}`, { timeoutMs: 45_000 }))));
    return { quotes: parts.flatMap((p) => p.quotes), errors: parts.flatMap((p) => p.errors) };
  },
  intraday: async (t: string, interval: '1m' | '5m'): Promise<Intraday> =>
    useMock() ? mock.liveIntraday(t, interval) : normIntraday(await request<Raw>(`/api/india/intraday/${enc(t)}?interval=${interval}`, { timeoutMs: 45_000 }), t, interval),
};
