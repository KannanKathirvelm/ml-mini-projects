import { getSettings } from '../settings';
import * as mock from './mock';
import type {
  AlertResult, CardInput, CardMeta, CardResult, FaceDetector, FaceResult, FinanceReport, Health,
  ObjectClasses, ObjectResult, PriceHistory, PriceSearch, StockForecast, StockTickers, TrackedItem,
  UpiExample, UpiInput, UpiMeta, UpiResult, IndiaPopular, MarketStatus, IndiaSearch,
} from './types';

import { ApiError } from './errors';
export { ApiError };

/** A cold server (model loading, first request after restart) can take a while; give requests room. */
const DEFAULT_TIMEOUT_MS = 120_000;
const TRAIN_TIMEOUT_MS = 300_000;

interface ReqOpts { method?: string; body?: unknown; form?: FormData; timeoutMs?: number; signal?: AbortSignal }

export async function request<T>(path: string, opts: ReqOpts = {}): Promise<T> {
  const base = getSettings().serverUrl;
  const ctrl = new AbortController();
  const timeout = setTimeout(() => ctrl.abort('timeout'), opts.timeoutMs ?? DEFAULT_TIMEOUT_MS);
  opts.signal?.addEventListener('abort', () => ctrl.abort('cancelled'));
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
    throw new ApiError(`Can't reach the server at ${base}. Check the URL in Settings, or turn on mock mode.`, null, 'network');
  } finally {
    clearTimeout(timeout);
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
