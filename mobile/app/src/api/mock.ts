// Offline mock backend. Shapes are copied from mobile/API.md so screens behave the same as against the server.
import type {
  AlertResult, CardInput, CardMeta, CardResult, FaceDetector, FaceResult, FinanceReport, Health, ObjectClasses,
  ObjectResult, PriceHistory, PriceSearch, StockForecast, StockTickers, TrackedItem, UpiExample, UpiInput, UpiMeta, UpiResult,
} from './types';
import { ApiError } from './errors';

const wait = <T,>(v: T, ms = 450): Promise<T> => new Promise((r) => setTimeout(() => r(structuredClone(v)), ms));
const sigmoid = (x: number) => 1 / (1 + Math.exp(-x));
const round = (x: number, d = 4) => Math.round(x * 10 ** d) / 10 ** d;
const fail = (status: number, detail: string) => new Promise<never>((_, rej) => setTimeout(() => rej(new ApiError(detail, status, 'http')), 400));

/** Deterministic PRNG so mock charts don't jump around between renders. */
function rng(seed: string) {
  let h = 2166136261;
  for (const c of seed) h = Math.imul(h ^ c.charCodeAt(0), 16777619);
  return () => {
    h += 0x6d2b79f5;
    let t = h;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function tradingDays(endISO: string, n: number, forward = false): string[] {
  const out: string[] = [];
  const d = new Date(endISO + 'T00:00:00Z');
  while (out.length < n) {
    d.setUTCDate(d.getUTCDate() + (forward ? 1 : -1));
    const wd = d.getUTCDay();
    if (wd !== 0 && wd !== 6) out.push(d.toISOString().slice(0, 10));
  }
  return forward ? out : out.reverse();
}
const LAST_DATE = '2026-10-23';

export const health = (): Promise<Health> =>
  wait({ status: 'ok', version: '1', projects: ['credit-card', 'upi', 'stocks', 'finance', 'prices', 'faces', 'objects'] }, 250);

// ---- 1. Credit card ----
export const cardMeta = (): Promise<CardMeta> =>
  wait({
    categories: ['grocery', 'gas', 'restaurant', 'electronics', 'travel', 'online_retail'],
    threshold: 0.313,
    metrics: { best_model: 'random_forest', fraud_precision: 0.896, fraud_recall: 0.92, average_precision: 0.96, roc_auc: 0.997 },
  });
export function cardPredict(b: CardInput): Promise<CardResult> {
  const night = b.hour < 6 ? 1.2 : 0;
  const z = -5 + 0.004 * b.amount + 0.006 * b.distance_from_home_km + 0.004 * b.distance_from_last_txn_km + 0.45 * b.ratio_to_median_amount +
    1.1 * b.online_order - 1.3 * b.used_chip - 1.2 * b.used_pin + 0.25 * b.txn_count_last_24h + night +
    (['electronics', 'online_retail', 'travel'].includes(b.merchant_category) ? 0.8 : 0);
  const p = round(sigmoid(z));
  return wait({ fraud_probability: p, flagged: p >= 0.313, threshold: 0.313 });
}

// ---- 2. UPI ----
export const upiMeta = (): Promise<UpiMeta> =>
  wait({
    threshold: 0.77,
    metrics: {
      best_model: 'gradient_boosting', fraud_precision: 0.912, fraud_recall: 0.938, average_precision: 0.965, roc_auc: 0.991,
      recall_by_fraud_type: { account_takeover: 1.0, collect_scam: 0.946, fake_qr: 0.897 },
    },
  });
const UPI_BASE: UpiInput = {
  payee_vpa: 'rahul.sharma@okaxis', amount: 450, hour: 19, txn_type: 'P2P', mode: 'pay', is_new_payee: 0,
  payee_account_age_days: 900, payee_fraud_reports: 0, device_changed_48h: 0, sim_changed_48h: 0,
  failed_pin_attempts_24h: 0, txns_last_1h: 1, amount_to_avg_ratio: 0.9, remark: 'dinner split',
};
export const upiExamples = (): Promise<UpiExample[]> =>
  wait([
    { name: 'Normal: paying a friend', input: { ...UPI_BASE } },
    { name: 'Scam: fake refund collect request', input: { ...UPI_BASE, payee_vpa: 'refund.helpdesk42@ybl', amount: 4999, hour: 11, mode: 'collect_request', is_new_payee: 1, payee_account_age_days: 4, payee_fraud_reports: 2, amount_to_avg_ratio: 5.0, remark: 'refund processing' } },
    { name: 'Scam: SIM swap takeover', input: { ...UPI_BASE, payee_vpa: 'quickcash.7781@paytm', amount: 24000, hour: 3, is_new_payee: 1, payee_account_age_days: 12, device_changed_48h: 1, sim_changed_48h: 1, failed_pin_attempts_24h: 3, txns_last_1h: 5, amount_to_avg_ratio: 18.0, remark: '' } },
    { name: 'Scam: fake merchant QR', input: { ...UPI_BASE, payee_vpa: 'shop.offers.win@ibl', amount: 2999, hour: 15, txn_type: 'P2M', mode: 'qr_scan', is_new_payee: 1, payee_account_age_days: 9, payee_fraud_reports: 1, amount_to_avg_ratio: 3.2, remark: 'prize claim fee' } },
  ]);
export function upiPredict(b: UpiInput): Promise<UpiResult> {
  const reasons: string[] = [];
  let z = -4;
  if (b.mode === 'collect_request') { z += 2.2; reasons.push('Collect request: you are being asked to approve a payment, not receive money.'); }
  if (b.mode === 'qr_scan' && b.is_new_payee) { z += 1.2; reasons.push('Scanning a QR from an unknown merchant.'); }
  if (b.is_new_payee) { z += 0.8; reasons.push('First payment to this payee.'); }
  if (b.payee_account_age_days < 30) { z += 1.4; reasons.push(`Payee account is only ${b.payee_account_age_days} days old.`); }
  if (b.payee_fraud_reports > 0) { z += 1.5 * b.payee_fraud_reports; reasons.push(`Payee has ${b.payee_fraud_reports} fraud report(s).`); }
  if (b.sim_changed_48h) { z += 2.0; reasons.push('SIM changed in the last 48 hours.'); }
  if (b.device_changed_48h) { z += 1.2; reasons.push('New device in the last 48 hours.'); }
  if (b.failed_pin_attempts_24h >= 2) { z += 1.0; reasons.push(`${b.failed_pin_attempts_24h} failed PIN attempts in 24h.`); }
  if (b.amount_to_avg_ratio >= 3) { z += 0.25 * b.amount_to_avg_ratio; reasons.push(`Amount is ${b.amount_to_avg_ratio}x your usual.`); }
  if (b.hour < 6) { z += 0.6; reasons.push('Unusual hour.'); }
  if (/refund|prize|kyc|lottery|reward/i.test(b.remark + b.payee_vpa)) { z += 1.0; reasons.push(`Suspicious wording: "${b.remark || b.payee_vpa}".`); }
  const p = round(sigmoid(z), 3);
  const risk_level = p >= 0.77 ? 'HIGH' : p >= 0.4 ? 'MEDIUM' : 'LOW';
  if (!reasons.length) reasons.push('No strong risk signals found.');
  return wait({ fraud_probability: p, risk_level, flagged: p >= 0.77, threshold: 0.77, reasons });
}

// ---- 3. Stocks ----
const TRAINED = ['AAPL', 'MSFT', 'RELIANCE.NS', 'TCS.NS'];
const mockTrained = new Set(TRAINED);
export const stockTickers = (): Promise<StockTickers> => wait({ trained: [...mockTrained] });
const BASES: Record<string, number> = { AAPL: 347.73, MSFT: 512.4, 'RELIANCE.NS': 1420.5, 'TCS.NS': 3920.0 };
function buildForecast(t: string, days: number): StockForecast {
  const r = rng(t);
  const last = BASES[t] ?? 100 + r() * 400;
  const dates = tradingDays(LAST_DATE, 89).concat(LAST_DATE);
  const closes: number[] = new Array(90);
  closes[89] = last;
  for (let i = 88; i >= 0; i--) closes[i] = closes[i + 1] * (1 - (r() - 0.48) * 0.03);
  closes[89] = last;
  const fdates = tradingDays(LAST_DATE, days, true);
  let a = last, b = last;
  const forecast = fdates.map((date) => {
    a *= 1 + (r() - 0.49) * 0.004; b *= 1 + (r() - 0.47) * 0.003;
    return { date, rnn: round(a, 2), lstm: round(b, 2) };
  });
  const testDates = tradingDays('2026-08-20', 60, true);
  const actual = testDates.map((_, i) => round(closes[29 + i] ?? last, 2));
  const k = last / 100;
  return {
    ticker: t, last_close: round(last, 2), last_date: LAST_DATE, as_of_ist: '2026-10-23 15:30 IST',
    currency: t.endsWith('.NS') || t.startsWith('^') ? 'INR' : 'USD',
    history: dates.map((date, i) => ({ date, close: round(closes[i], 2) })),
    forecast,
    metrics: {
      naive_baseline: { rmse: round(1.25 * k, 3), mae: round(0.89 * k, 3), mape_pct: 1.09, direction_acc_pct: null },
      rnn: { rmse: round(1.38 * k, 3), mae: round(1.02 * k, 3), mape_pct: 1.24, direction_acc_pct: 50.8 },
      lstm: { rmse: round(1.31 * k, 3), mae: round(0.95 * k, 3), mape_pct: 1.16, direction_acc_pct: 52.1 },
    },
    test: {
      dates: testDates, actual,
      rnn: actual.map((v, i) => round((actual[i - 1] ?? v) * (1 + (r() - 0.5) * 0.01), 2)),
      lstm: actual.map((v, i) => round((actual[i - 1] ?? v) * (1 + (r() - 0.5) * 0.008), 2)),
    },
  };
}
export function stockForecast(t: string, days: number): Promise<StockForecast> {
  const T = t.toUpperCase();
  if (!mockTrained.has(T)) return fail(404, `No trained model for ${T} yet. Train it first (POST /api/stocks/${T}/train).`);
  return wait(buildForecast(T, Math.min(30, Math.max(1, days))));
}
export function stockTrain(t: string): Promise<StockForecast> {
  const T = t.toUpperCase();
  if (!/^[A-Z0-9.\-^]{1,12}$/.test(T)) return fail(400, `Unknown symbol: ${t}`);
  mockTrained.add(T);
  return wait(buildForecast(T, 10), 4000);
}

// ---- 4. Finance ----
export function financeReport(t: string): Promise<FinanceReport> {
  const T = t.toUpperCase();
  if (!/^[A-Z0-9.\-^]{1,12}$/.test(T)) return fail(404, `Unknown ticker: ${t}`);
  const r = rng('fin' + T);
  const last = BASES[T] ?? 50 + r() * 300;
  const dates = tradingDays(LAST_DATE, 249).concat(LAST_DATE);
  const closes: number[] = new Array(250);
  closes[249] = last;
  for (let i = 248; i >= 0; i--) closes[i] = closes[i + 1] * (1 - (r() - 0.485) * 0.025);
  const sma = (i: number, n: number) => (i + 1 < n ? null : round(closes.slice(i + 1 - n, i + 1).reduce((s, v) => s + v, 0) / n, 2));
  const chart = dates.map((date, i) => ({ date, close: round(closes[i], 2), sma20: sma(i, 20), sma50: sma(i, 50), sma200: sma(i, 200) }));
  const company = ({ AAPL: 'Apple Inc.', MSFT: 'Microsoft Corporation', 'RELIANCE.NS': 'Reliance Industries Limited', 'TCS.NS': 'Tata Consultancy Services' } as Record<string, string>)[T] ?? `${T} (mock company)`;
  return wait({
    ticker: T, company, mode: 'offline', mode_label: 'Offline mode (rule-based, no API key)',
    currency: T.endsWith('.NS') ? 'INR' : 'USD', last_close: round(last, 2), last_date: LAST_DATE,
    outlook: 'neutral', confidence: 'low',
    summary: `${company} trades above its 50-day average with moderate momentum. Valuation is stretched versus history and news flow is mixed, so the agents land on a neutral outlook.`,
    bullish: ['Price above 50-day and 200-day moving averages', 'Positive 1-month return (+3.5%)', 'Strong operating margins'],
    bearish: ['RSI near overbought (64)', 'P/E above 5-year average'],
    risks: ['Regulatory scrutiny in key markets', 'Slowing hardware demand', 'Currency headwinds'],
    overall: 'Mixed signals: trend is up but valuation and momentum limit upside in the near term.',
    agents: [
      { name: 'Technical Analyst', stance: 'bullish', summary: 'Uptrend intact; price above key SMAs.', points: ['Close > SMA50 > SMA200', 'RSI 64, not yet overbought', '1y volatility 24%'] },
      { name: 'Fundamental Analyst', stance: 'neutral', summary: 'Solid business, rich valuation.', points: ['Revenue growth ~6% y/y', 'Net margin 25%', 'Forward P/E 29'] },
      { name: 'News Sentiment Analyst', stance: 'bearish', summary: 'Headlines skew slightly negative this week.', points: ['2 positive, 3 negative, 1 neutral headline'] },
      { name: 'Risk Manager', stance: 'neutral', summary: 'Drawdown moderate; position sizing advised.', points: ['Max drawdown 1y: -12%', 'Beta ~1.2'] },
    ],
    headlines: [
      { title: `${company} unveils new product line at autumn event`, publisher: 'Mock Wire', link: null, sentiment: 'positive' },
      { title: `Regulators open inquiry into ${company} app store fees`, publisher: 'Daily Mock', link: null, sentiment: 'negative' },
      { title: `Analysts split on ${T} after earnings beat`, publisher: 'Market Mock', link: null, sentiment: 'neutral' },
    ],
    indicators: { rsi: 64.0, volatility_1y: 0.24, return_1m: 0.035, max_drawdown_1y: -0.12 },
    chart,
    markdown: `# Market insight: ${T}\n\nMock report.`,
    sector: T.endsWith('.NS') ? 'Energy' : 'Technology',
    industry: T.endsWith('.NS') ? 'Oil & Gas Refining & Marketing' : 'Consumer Electronics',
    market_cap_display: T.endsWith('.NS') ? '₹19.2 lakh crore' : '$5.1T',
    display: null,
    as_of_ist: '2026-10-23 15:30 IST',
    benchmark: T.endsWith('.NS') ? {
      name: 'NIFTY 50', symbol: '^NSEI', beta: 1.08,
      returns: { '1m': { stock: 0.021, index: 0.014 }, '3m': { stock: -0.035, index: 0.022 }, '1y': { stock: 0.112, index: 0.094 } },
    } : null,
  }, 900);
}

// ---- 5. Prices ----
const enc = encodeURIComponent;
const STORES = ['DummyJSON', 'FakeStore', 'ShopKart', 'MegaMart', 'QuickBuy'];
const CATALOG = [
  { product: 'iPhone 13 Pro', base: 85489 }, { product: 'iPhone 14', base: 69900 }, { product: 'Samsung Galaxy S23', base: 64999 },
  { product: 'Sony WH-1000XM5 Headphones', base: 26990 }, { product: 'Dell Inspiron 15 Laptop', base: 54990 },
  { product: 'Mens Cotton Jacket', base: 2499 }, { product: 'Running Shoes', base: 3199 }, { product: 'Smart Watch', base: 4999 },
];
export function priceSearch(query: string): Promise<PriceSearch> {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  const hits = CATALOG.filter((c) => words.some((w) => c.product.toLowerCase().includes(w)));
  const groups = hits.map((c) => {
    const r = rng(c.product);
    const offers = STORES.filter(() => r() > 0.2).map((store) => {
      const price = Math.round(c.base * (0.92 + r() * 0.22));
      const shipping = r() > 0.6 ? Math.round(40 + r() * 60) : 0;
      return {
        store, title: `${store === 'MegaMart' ? 'Apple ' : ''}${c.product}`, price_inr: price, shipping_inr: shipping, total_inr: price + shipping,
        delivery_days: 1 + Math.floor(r() * 6), rating: round(3.6 + r() * 1.3, 1), in_stock: r() > 0.15,
        url: `https://example.com/${store.toLowerCase()}/${enc(c.product)}`, image: null,
      };
    }).sort((a, b) => a.total_inr - b.total_inr);
    const inStock = offers.filter((o) => o.in_stock);
    const best = inStock[0] ?? null;
    const savings = best ? Math.max(...offers.map((o) => o.total_inr)) - best.total_inr : 0;
    return { product: c.product, store_count: offers.length, best, savings_inr: savings, offers };
  });
  return wait({ query, stores_ok: STORES, warnings: [], groups }, 700);
}
export function priceHistory(product: string, days: number): Promise<PriceHistory> {
  const r = rng('hist' + product);
  const base = CATALOG.find((c) => c.product === product)?.base ?? 10000;
  const end = new Date(LAST_DATE + 'T00:00:00Z');
  const dates = Array.from({ length: days }, (_, i) => { const d = new Date(end); d.setUTCDate(d.getUTCDate() - (days - 1 - i)); return d.toISOString().slice(0, 10); });
  const series = STORES.slice(2).map((store) => {
    let p = base * (0.98 + r() * 0.1);
    return { store, points: dates.map((date) => { p *= 1 + (r() - 0.52) * 0.02; return { date, price_inr: Math.round(p) }; }) };
  });
  return wait({ product, series });
}
const tracked = new Map<string, number>([['iPhone 13 Pro', 95000]]);
const bestFor = (p: string) => { const c = CATALOG.find((x) => x.product === p); return c ? { best: Math.round(c.base * 0.96), store: 'MegaMart' } : { best: null, store: null }; };
const trackedRow = (product: string, target: number): TrackedItem => { const b = bestFor(product); return { product, target_inr: target, latest_best_inr: b.best, latest_store: b.store, hit: b.best !== null && b.best <= target }; };
export const priceTracked = (): Promise<TrackedItem[]> => wait([...tracked].map(([p, t]) => trackedRow(p, t)));
export function priceTrack(product: string, target: number): Promise<TrackedItem> { tracked.set(product, target); return wait(trackedRow(product, target)); }
export function priceUntrack(product: string) { const removed = tracked.delete(product); return wait({ removed }); }
export const priceCheckAlerts = (): Promise<AlertResult[]> =>
  wait([...tracked].map(([product, target_inr]) => { const b = bestFor(product); return { product, target_inr, best_inr: b.best, store: b.store, hit: b.best !== null && b.best <= target_inr }; }));

// ---- 6/7. Images: draw fake boxes on the user's own photo so the UI is realistic offline ----
async function annotate(image: Blob, boxes: { x: number; y: number; w: number; h: number; label: string; color: string }[], blur = false) {
  const bmp = await createImageBitmap(image);
  const scale = Math.min(1, 1280 / Math.max(bmp.width, bmp.height));
  const W = Math.round(bmp.width * scale), H = Math.round(bmp.height * scale);
  const c = document.createElement('canvas');
  c.width = W; c.height = H;
  const g = c.getContext('2d')!;
  g.drawImage(bmp, 0, 0, W, H);
  const abs = boxes.map((b) => ({ ...b, x: b.x * W, y: b.y * H, w: b.w * W, h: b.h * H }));
  for (const b of abs) {
    if (blur) { g.save(); g.beginPath(); g.rect(b.x, b.y, b.w, b.h); g.clip(); g.filter = 'blur(14px)'; g.drawImage(c, 0, 0); g.restore(); }
    g.strokeStyle = b.color; g.lineWidth = Math.max(2, W / 300); g.strokeRect(b.x, b.y, b.w, b.h);
    g.fillStyle = b.color; g.font = `${Math.max(12, W / 50)}px sans-serif`; g.fillText(b.label, b.x + 4, Math.max(14, b.y - 4));
  }
  return { b64: c.toDataURL('image/jpeg', 0.85).split(',')[1], abs, W, H };
}
export async function facesDetect(image: Blob, o: { detector: FaceDetector; blur: boolean; threshold: number }): Promise<FaceResult> {
  const rel = [{ x: 0.2, y: 0.2, w: 0.18, h: 0.24 }, { x: 0.55, y: 0.25, w: 0.16, h: 0.22 }];
  const dets = o.detector === 'both' ? (['yunet', 'haar'] as const) : [o.detector];
  const results = [];
  for (const d of dets) {
    const use = d === 'haar' ? rel.slice(0, 1) : rel;
    const { b64, abs } = await annotate(image, use.map((b) => ({ ...b, label: d === 'yunet' ? '0.93' : 'face', color: d === 'yunet' ? '#22c55e' : '#3b82f6' })), o.blur);
    results.push({
      detector: d, count: abs.length, time_ms: d === 'yunet' ? 36.8 : 58.2,
      faces: abs.map((b) => ({ x: Math.round(b.x), y: Math.round(b.y), w: Math.round(b.w), h: Math.round(b.h), score: d === 'yunet' ? 0.93 : null, landmarks: d === 'yunet' ? [[Math.round(b.x + b.w * 0.3), Math.round(b.y + b.h * 0.4)]] : null })),
      image_base64: b64,
    });
  }
  return wait({ results }, 600);
}
const COCO = ['person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train', 'truck', 'boat', 'traffic light', 'fire hydrant', 'stop sign', 'parking meter', 'bench', 'bird', 'cat', 'dog', 'horse', 'sheep', 'cow', 'elephant', 'bear', 'zebra', 'giraffe', 'backpack', 'umbrella', 'handbag', 'tie', 'suitcase', 'frisbee', 'skis', 'snowboard', 'sports ball', 'kite', 'baseball bat', 'baseball glove', 'skateboard', 'surfboard', 'tennis racket', 'bottle', 'wine glass', 'cup', 'fork', 'knife', 'spoon', 'bowl', 'banana', 'apple', 'sandwich', 'orange', 'broccoli', 'carrot', 'hot dog', 'pizza', 'donut', 'cake', 'chair', 'couch', 'potted plant', 'bed', 'dining table', 'toilet', 'tv', 'laptop', 'mouse', 'remote', 'keyboard', 'cell phone', 'microwave', 'oven', 'toaster', 'sink', 'refrigerator', 'book', 'clock', 'vase', 'scissors', 'teddy bear', 'hair drier', 'toothbrush'];
export const objectClasses = (): Promise<ObjectClasses> => wait({ classes: COCO, models: ['yolo11n.pt', 'yolo11s.pt'] });
export async function objectsDetect(image: Blob, o: { conf: number; iou: number; classes: string[]; model: string }): Promise<ObjectResult> {
  const all = [
    { cls: 'person', conf: 0.91, b: { x: 0.1, y: 0.25, w: 0.2, h: 0.6 } }, { cls: 'person', conf: 0.86, b: { x: 0.35, y: 0.3, w: 0.18, h: 0.55 } },
    { cls: 'bus', conf: 0.94, b: { x: 0.05, y: 0.1, w: 0.9, h: 0.6 } }, { cls: 'dog', conf: 0.42, b: { x: 0.65, y: 0.6, w: 0.2, h: 0.25 } },
  ].filter((d) => d.conf >= o.conf && (!o.classes.length || o.classes.includes(d.cls)));
  const { b64, abs } = await annotate(image, all.map((d) => ({ ...d.b, label: `${d.cls} ${d.conf.toFixed(2)}`, color: '#f97316' })));
  const counts: Record<string, number> = {};
  all.forEach((d) => (counts[d.cls] = (counts[d.cls] ?? 0) + 1));
  return wait({
    count: all.length, time_ms: o.model === 'yolo11s.pt' ? 18.4 : 7.6, counts,
    detections: all.map((d, i) => ({ cls: d.cls, conf: d.conf, box: [Math.round(abs[i].x), Math.round(abs[i].y), Math.round(abs[i].x + abs[i].w), Math.round(abs[i].y + abs[i].h)] as [number, number, number, number] })),
    image_base64: b64,
  }, 600);
}

// ---- India extras ----
export const BUILTIN_POPULAR: import('./types').IndiaPopular = {
  indices: [
    { symbol: '^NSEI', name: 'NIFTY 50' }, { symbol: '^BSESN', name: 'SENSEX' }, { symbol: '^NSEBANK', name: 'BANK NIFTY' },
  ],
  stocks: [
    { symbol: 'RELIANCE.NS', name: 'Reliance Industries', sector: 'Energy' },
    { symbol: 'TCS.NS', name: 'Tata Consultancy Services', sector: 'IT' },
    { symbol: 'HDFCBANK.NS', name: 'HDFC Bank', sector: 'Financials' },
    { symbol: 'INFY.NS', name: 'Infosys', sector: 'IT' },
    { symbol: 'ICICIBANK.NS', name: 'ICICI Bank', sector: 'Financials' },
    { symbol: 'SBIN.NS', name: 'State Bank of India', sector: 'Financials' },
    { symbol: 'BHARTIARTL.NS', name: 'Bharti Airtel', sector: 'Telecom' },
    { symbol: 'ITC.NS', name: 'ITC', sector: 'FMCG' },
    { symbol: 'LT.NS', name: 'Larsen & Toubro', sector: 'Industrials' },
    { symbol: 'TATAMOTORS.NS', name: 'Tata Motors', sector: 'Auto' },
  ],
};
export const indiaPopular = () => wait(BUILTIN_POPULAR, 250);
export function marketStatus(): Promise<import('./types').MarketStatus> {
  // Approximate NSE hours (Mon-Fri 09:15-15:30 IST), ignoring holidays.
  const ist = new Date(Date.now() + (330 + new Date().getTimezoneOffset()) * 60000);
  const mins = ist.getHours() * 60 + ist.getMinutes();
  const wd = ist.getDay();
  const open = wd >= 1 && wd <= 5 && mins >= 555 && mins < 930;
  return wait({ exchange: 'NSE', is_open: open, status: open ? 'Open' : 'Closed', next_close_ist: open ? '15:30 IST' : null, next_open_ist: open ? null : 'next weekday 09:15 IST' }, 200);
}
const MOCK_LISTED = [
  ['RELIANCE', 'Reliance Industries Limited', 'INE002A01018'], ['INFY', 'Infosys Limited', 'INE009A01021'],
  ['INFIBEAM', 'Infibeam Avenues Limited', 'INE483S01020'], ['TCS', 'Tata Consultancy Services Limited', 'INE467B01029'],
  ['TATAMOTORS', 'Tata Motors Limited', 'INE155A01022'], ['TATASTEEL', 'Tata Steel Limited', 'INE081A01020'],
  ['HDFCBANK', 'HDFC Bank Limited', 'INE040A01034'], ['IRCTC', 'Indian Railway Catering And Tourism Corporation Limited', 'INE335Y01020'],
  ['ZOMATO', 'Zomato Limited', 'INE758T01015'], ['ASIANPAINT', 'Asian Paints Limited', 'INE021A01026'],
];
export function indiaSearch(query: string, limit = 10): Promise<import('./types').IndiaSearch> {
  const q = query.trim().toLowerCase();
  const results = MOCK_LISTED.filter(([s, n]) => s.toLowerCase().includes(q) || n.toLowerCase().includes(q)).slice(0, limit)
    .map(([s, n, isin]) => ({ symbol: `${s}.NS`, nse_symbol: s, name: n, isin, series: 'EQ' }));
  return wait({ query, results }, 200);
}

// ---- Live quotes (mock) ----
const LIVE_BASE: Record<string, number> = { 'RELIANCE.NS': 1190, 'TCS.NS': 3015.4, 'INFY.NS': 1488.9, 'HDFCBANK.NS': 1001.2, 'ICICIBANK.NS': 1352.6, 'SBIN.NS': 912.35, '^NSEI': 25795.15, '^BSESN': 84211.88, '^NSEBANK': 58114.6, AAPL: 347.73 };
const istNow = () => new Date(Date.now() + (330 + new Date().getTimezoneOffset()) * 60000);
const hhmm = (d: Date) => `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
export function liveQuote(t: string): Promise<import('./types').Quote> {
  const T = t.toUpperCase();
  const r = rng('q' + T + Math.floor(Date.now() / 30000));
  const prev = LIVE_BASE[T] ?? 500 + rng(T)() * 2000;
  const change = Math.round(prev * (r() - 0.45) * 0.03 * 100) / 100;
  return wait({
    symbol: T, name: BUILTIN_POPULAR.stocks.concat(BUILTIN_POPULAR.indices).find((x) => x.symbol === T)?.name ?? T,
    currency: T.endsWith('.NS') || T.startsWith('^') ? 'INR' : 'USD', price: Math.round((prev + change) * 100) / 100, change,
    change_pct: Math.round((change / prev) * 10000) / 100, prev_close: prev, as_of_ist: `${hhmm(istNow())} IST`, delayed: true, display: null,
  }, 250);
}
export function liveIntraday(t: string, interval: '1m' | '5m'): Promise<import('./types').Intraday> {
  const T = t.toUpperCase();
  const r = rng('i' + T);
  const prev = LIVE_BASE[T] ?? 1000;
  const step = interval === '1m' ? 1 : 5;
  const points = [];
  let p = prev;
  for (let m = 555; m <= 930; m += step) {
    p *= 1 + (r() - 0.5) * 0.002 * Math.sqrt(step);
    points.push({ t: `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`, price: Math.round(p * 100) / 100 });
  }
  return wait({ symbol: T, interval, points, as_of_ist: '15:30 IST', prev_close: prev, currency: 'INR' }, 300);
}
