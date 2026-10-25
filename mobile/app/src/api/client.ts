import { getSettings } from '../settings';
import * as mock from './mock';
import type {
  AlertResult, CardInput, CardMeta, CardResult, FaceDetector, FaceResult, FinanceReport, Health,
  ObjectClasses, ObjectResult, PriceHistory, PriceSearch, StockForecast, StockTickers, TrackedItem,
  UpiExample, UpiInput, UpiMeta, UpiResult, IndiaPopular, MarketStatus, IndiaSearch, IndiaStocksPage,
} from './types';

import { ApiError } from './errors';
export { ApiError };

/** A cold server (model loading, first request after restart) can take a while; give requests room. */
const DEFAULT_TIMEOUT_MS = 120_000;
const TRAIN_TIMEOUT_MS = 300_000;
/**
 * Render's free plan sleeps after 15 min idle; the first request then takes 50-60 s while it boots.
 * Until a request to the current server has succeeded, every call gets at least this timeout and is retried.
 */
const COLD_TIMEOUT_MS = 95_000;
const COLD_RETRIES = 2;
const WAKING_AFTER_MS = 4_000;

// ---------- "server waking up" state, shared by every screen ----------
let warmBase: string | null = null;
let waking = false;
let coldInFlight = 0;
const wakeSubs = new Set<() => void>();
const setWaking = (v: boolean) => { if (v !== waking) { waking = v; wakeSubs.forEach((f) => f()); } };
export const serverWaking = {
  get: () => waking,
  subscribe: (cb: () => void) => { wakeSubs.add(cb); return () => { wakeSubs.delete(cb); }; },
};
/** true until a request to the configured server has succeeded (or after the URL changes). */
export const isServerCold = () => warmBase !== getSettings().serverUrl;

interface ReqOpts { method?: string; body?: unknown; form?: FormData; timeoutMs?: number; signal?: AbortSignal }

async function requestOnce<T>(path: string, opts: ReqOpts, base: string, timeoutMs: number): Promise<T> {
  const ctrl = new AbortController();
  const timeout = setTimeout(() => ctrl.abort('timeout'), timeoutMs);
  const onAbort = () => ctrl.abort('cancelled');
  opts.signal?.addEventListener('abort', onAbort);
  let res: Response;
  try {
    res = await fetch(base + path, {
      method: opts.method || (opts.body || opts.form ? 'POST' : 'GET'),
      headers: opts.body !== undefined ? { 'Content-Type': 'application/json', Accept: 'application/json' } : { Accept: 'application/json' },
      body: opts.form ?? (opts.body !== undefined ? JSON.stringify(opts.body) : undefined),
      signal: ctrl.signal,
    });
  } catch (e) {
    if (ctrl.signal.aborted && ctrl.signal.reason === 'timeout') {
      throw new ApiError(`The server at ${base} did not answer in time.`, null, 'timeout');
    }
    if (ctrl.signal.aborted) throw new ApiError('Request cancelled.', null, 'network');
    throw new ApiError(`Can't reach the server at ${base}. Check the URL in Settings, or turn on mock mode.`, null, 'network');
  } finally {
    clearTimeout(timeout);
    opts.signal?.removeEventListener('abort', onAbort);
  }
  const text = await res.text();
  let data: unknown = null;
  try { data = text ? JSON.parse(text) : null; } catch { /* non-JSON */ }
  if (!res.ok) {
    const detail = (data as { detail?: unknown } | null)?.detail;
    const msg = typeof detail === 'string' ? detail : detail ? JSON.stringify(detail) : `HTTP ${res.status} ${res.statusText}`;
    throw new ApiError(msg, res.status, 'http');
  }
  if (data === null) throw new ApiError('The server returned an empty or non-JSON response.', res.status, 'parse');
  return data as T;
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export async function request<T>(path: string, opts: ReqOpts = {}): Promise<T> {
  const base = getSettings().serverUrl;
  const cold = warmBase !== base;
  const timeoutMs = cold ? Math.max(opts.timeoutMs ?? DEFAULT_TIMEOUT_MS, COLD_TIMEOUT_MS) : opts.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const method = (opts.method || (opts.body || opts.form ? 'POST' : 'GET')).toUpperCase();
  if (cold) coldInFlight++;
  const wakeTimer = cold ? setTimeout(() => warmBase !== base && setWaking(true), WAKING_AFTER_MS) : undefined;
  try {
    for (let attempt = 0; ; attempt++) {
      try {
        const d = await requestOnce<T>(path, opts, base, timeoutMs);
        warmBase = base;
        return d;
      } catch (e) {
        if (e instanceof ApiError && e.kind === 'http' && e.status !== null && e.status < 500) warmBase = base; // server answered
        const gateway = e instanceof ApiError && (e.status === 502 || e.status === 503 || e.status === 504);
        // Retry while the server is (probably) booting: always for GET, and for other methods only when
        // nothing reached the app (connection refused / gateway error), so a POST is never run twice.
        const retryable = e instanceof ApiError && !opts.signal?.aborted
          && (gateway || e.kind === 'network' || (e.kind === 'timeout' && method === 'GET'));
        if (!cold || !retryable || attempt >= COLD_RETRIES) {
          if (e instanceof ApiError && cold && (e.kind === 'network' || e.kind === 'timeout' || gateway)) {
            e.message += ' If it is on free hosting it may still be waking up: wait a few seconds and retry.';
          }
          throw e;
        }
        setWaking(true);
        await sleep(3_000 * (attempt + 1));
      }
    }
  } finally {
    clearTimeout(wakeTimer);
    if (cold) coldInFlight--;
    if (warmBase === base || coldInFlight <= 0) setWaking(false);
  }
}

/** Fire-and-forget ping at app start so a sleeping server starts booting before the user taps anything. */
export function wakeServer() {
  if (getSettings().mock || !isServerCold()) return;
  request('/health', { timeoutMs: COLD_TIMEOUT_MS }).catch(() => { /* screens show their own errors */ });
}

const useMock = () => getSettings().mock;
const q = (o: Record<string, string | number>) => '?' + new URLSearchParams(Object.entries(o).map(([k, v]) => [k, String(v)])).toString();
const enc = encodeURIComponent;

export const api = {
  health: (): Promise<Health> => (useMock() ? mock.health() : request('/health', { timeoutMs: 60_000 })),

  card: {
    meta: (): Promise<CardMeta> => (useMock() ? mock.cardMeta() : request('/api/credit-card/meta')),
    predict: (b: CardInput): Promise<CardResult> => (useMock() ? mock.cardPredict(b) : request('/api/credit-card/predict', { body: b })),
  },
  upi: {
    meta: (): Promise<UpiMeta> => (useMock() ? mock.upiMeta() : request('/api/upi/meta')),
    examples: (): Promise<UpiExample[]> => (useMock() ? mock.upiExamples() : request('/api/upi/examples')),
    predict: (b: UpiInput): Promise<UpiResult> => (useMock() ? mock.upiPredict(b) : request('/api/upi/predict', { body: b })),
  },
  stocks: {
    tickers: (): Promise<StockTickers> => (useMock() ? mock.stockTickers() : request('/api/stocks/tickers')),
    forecast: (t: string, days: number): Promise<StockForecast> =>
      useMock() ? mock.stockForecast(t, days) : request(`/api/stocks/${enc(t)}/forecast${q({ days })}`),
    train: (t: string): Promise<StockForecast> =>
      useMock() ? mock.stockTrain(t) : request(`/api/stocks/${enc(t)}/train`, { method: 'POST', timeoutMs: TRAIN_TIMEOUT_MS }),
  },
  india: {
    popular: (): Promise<IndiaPopular> => (useMock() ? mock.indiaPopular() : request('/api/india/popular', { timeoutMs: 60_000 })),
    search: (query: string, limit = 10, signal?: AbortSignal): Promise<IndiaSearch> =>
      useMock() ? mock.indiaSearch(query, limit) : request(`/api/india/search${q({ q: query, limit })}`, { timeoutMs: 30_000, signal }),
    marketStatus: (): Promise<MarketStatus> => (useMock() ? mock.marketStatus() : request('/api/india/market-status', { timeoutMs: 60_000 })),
    /** The whole NSE list, paged (0 <= offset, 1 <= limit <= 500). */
    stocks: (offset = 0, limit = 100): Promise<IndiaStocksPage> =>
      useMock() ? mock.indiaStocks(offset, limit) : request(`/api/india/stocks${q({ offset, limit })}`, { timeoutMs: 60_000 }),
  },
  finance: {
    report: (t: string): Promise<FinanceReport> =>
      useMock() ? mock.financeReport(t) : request(`/api/finance/${enc(t)}/report`, { timeoutMs: 180_000 }),
  },
  prices: {
    search: (query: string): Promise<PriceSearch> => (useMock() ? mock.priceSearch(query) : request(`/api/prices/search${q({ q: query })}`)),
    history: (product: string, days = 30): Promise<PriceHistory> =>
      useMock() ? mock.priceHistory(product, days) : request(`/api/prices/history${q({ product, days })}`),
    tracked: (): Promise<TrackedItem[]> => (useMock() ? mock.priceTracked() : request('/api/prices/tracked')),
    track: (product: string, target_inr: number): Promise<TrackedItem> =>
      useMock() ? mock.priceTrack(product, target_inr) : request('/api/prices/track', { body: { product, target_inr } }),
    untrack: (product: string): Promise<{ removed: boolean }> =>
      useMock() ? mock.priceUntrack(product) : request(`/api/prices/track${q({ product })}`, { method: 'DELETE' }),
    checkAlerts: (): Promise<AlertResult[]> => (useMock() ? mock.priceCheckAlerts() : request('/api/prices/check-alerts', { method: 'POST' })),
  },
  faces: {
    detect: (image: Blob, o: { detector: FaceDetector; blur: boolean; threshold: number }): Promise<FaceResult> => {
      if (useMock()) return mock.facesDetect(image, o);
      const f = new FormData();
      f.append('image', image, image.type === 'image/png' ? 'photo.png' : 'photo.jpg');
      f.append('detector', o.detector);
      f.append('blur', String(o.blur));
      f.append('threshold', String(o.threshold));
      return request('/api/faces/detect', { form: f });
    },
  },
  objects: {
    classes: (): Promise<ObjectClasses> => (useMock() ? mock.objectClasses() : request('/api/objects/classes')),
    detect: (image: Blob, o: { conf: number; iou: number; classes: string[]; model: string }): Promise<ObjectResult> => {
      if (useMock()) return mock.objectsDetect(image, o);
      const f = new FormData();
      f.append('image', image, image.type === 'image/png' ? 'photo.png' : 'photo.jpg');
      f.append('conf', String(o.conf));
      f.append('iou', String(o.iou));
      f.append('classes', o.classes.join(','));
      f.append('model', o.model);
      return request('/api/objects/detect', { form: f });
    },
  },
};
