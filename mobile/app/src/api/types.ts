// Types mirror mobile/API.md (v1) exactly. snake_case on purpose.

export interface Health { status: string; version: string; projects: string[] }

export interface ModelMetrics {
  best_model?: string;
  fraud_precision: number;
  fraud_recall: number;
  average_precision: number;
  roc_auc: number;
  [k: string]: unknown;
}

// 1. Credit card
export interface CardMeta { categories: string[]; threshold: number; metrics: ModelMetrics }
export interface CardInput {
  amount: number; hour: number; distance_from_home_km: number; distance_from_last_txn_km: number;
  ratio_to_median_amount: number; online_order: 0 | 1; used_chip: 0 | 1; used_pin: 0 | 1;
  txn_count_last_24h: number; merchant_category: string;
}
export interface CardResult { fraud_probability: number; flagged: boolean; threshold: number }

// 2. UPI
export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH';
export interface UpiMeta { threshold: number; metrics: ModelMetrics & { recall_by_fraud_type?: Record<string, number> } }
export interface UpiInput {
  payee_vpa: string; amount: number; hour: number; txn_type: 'P2P' | 'P2M';
  mode: 'pay' | 'collect_request' | 'qr_scan'; is_new_payee: 0 | 1; payee_account_age_days: number;
  payee_fraud_reports: number; device_changed_48h: 0 | 1; sim_changed_48h: 0 | 1;
  failed_pin_attempts_24h: number; txns_last_1h: number; amount_to_avg_ratio: number; remark: string;
}
export interface UpiExample { name: string; input: UpiInput }
export interface UpiResult { fraud_probability: number; risk_level: RiskLevel; flagged: boolean; threshold: number; reasons: string[] }

// 3. Stocks
export interface ForecastMetric { rmse: number | null; mae: number | null; mape_pct: number | null; direction_acc_pct: number | null }
export interface StockForecast extends StockExtras {
  ticker: string; last_close: number; last_date: string;
  history: { date: string; close: number }[];
  forecast: { date: string; rnn: number; lstm: number }[];
  metrics: { naive_baseline: ForecastMetric; rnn: ForecastMetric; lstm: ForecastMetric };
  test: { dates: string[]; actual: number[]; rnn: number[]; lstm: number[] };
}
export interface StockTickers { trained: string[] }

// 4. Finance
export type Stance = 'bullish' | 'neutral' | 'bearish';
export interface FinanceAgent { name: string; stance: Stance | null; summary: string | null; points: string[] }
export interface FinanceReport extends FinanceExtras {
  ticker: string; company: string | null; mode: 'offline' | 'llm'; mode_label: string;
  currency: string | null; last_close: number | null; last_date: string | null;
  outlook: Stance | null; confidence: 'low' | 'medium' | 'high' | null;
  summary: string | null; bullish: string[]; bearish: string[]; risks: string[]; overall: string | null;
  agents: FinanceAgent[];
  headlines: { title: string; publisher: string | null; link: string | null; sentiment: string | null }[];
  indicators: { rsi: number | null; volatility_1y: number | null; return_1m: number | null; max_drawdown_1y: number | null };
  chart: { date: string; close: number; sma20: number | null; sma50: number | null; sma200: number | null }[];
  markdown: string | null;
}

// 5. Prices
export interface Offer {
  store: string; title: string; price_inr: number; shipping_inr: number; total_inr: number;
  delivery_days: number | null; rating: number | null; in_stock: boolean; url: string | null; image: string | null;
}
export interface ProductGroup { product: string; store_count: number; best: Offer | null; savings_inr: number; offers: Offer[] }
export interface PriceSearch { query: string; stores_ok: string[]; warnings: string[]; groups: ProductGroup[] }
export interface PriceHistory { product: string; series: { store: string; points: { date: string; price_inr: number }[] }[] }
export interface TrackedItem { product: string; target_inr: number; latest_best_inr: number | null; latest_store: string | null; hit: boolean }
export interface AlertResult { product: string; target_inr: number; best_inr: number | null; store: string | null; hit: boolean }

// 6. Faces
export type FaceDetector = 'yunet' | 'haar' | 'both';
export interface Face { x: number; y: number; w: number; h: number; score: number | null; landmarks: number[][] | null }
export interface FaceRun { detector: 'yunet' | 'haar'; count: number; time_ms: number; faces: Face[]; image_base64: string }
export interface FaceResult { results: FaceRun[] }

// 7. Objects
export interface ObjectClasses { classes: string[]; models: string[] }
export interface ObjectResult {
  count: number; time_ms: number; counts: Record<string, number>;
  detections: { cls: string; conf: number; box: [number, number, number, number] }[];
  image_base64: string;
}

// India extras (additive; every field optional so the app copes with older servers)
export interface IndiaInstrument { symbol: string; name?: string | null; sector?: string | null }
export interface IndiaPopular { stocks: IndiaInstrument[]; indices: IndiaInstrument[] }
export interface MarketStatus {
  exchange?: string; is_open?: boolean; status?: string; label?: string; message?: string;
  now_ist?: string | null; next_open_ist?: string | null; next_close_ist?: string | null;
  next_open?: string | null; next_close?: string | null; [k: string]: unknown;
}
export interface BenchmarkReturn { stock?: number | null; index?: number | null; benchmark?: number | null }
export interface Benchmark {
  name?: string; symbol?: string; beta?: number | null;
  returns?: Record<string, BenchmarkReturn | null> | null;
  [k: string]: unknown;
}
export interface FinanceExtras {
  as_of_ist?: string | null;
  sector?: string | null; industry?: string | null; market_cap_display?: string | null;
  display?: { last_close?: string | null; [k: string]: unknown } | null;
  benchmark?: Benchmark | null;
}
export interface StockExtras { as_of_ist?: string | null; currency?: string | null; name?: string | null; display?: { last_close?: string | null; [k: string]: unknown } | null }
export interface IndiaSearchResult { symbol: string; nse_symbol?: string | null; name?: string | null; isin?: string | null; series?: string | null }
export interface IndiaSearch { query: string; results: IndiaSearchResult[] }

// Live data (tolerant: field names normalised in api/live.ts)
export interface Quote {
  symbol: string; name?: string | null; currency?: string | null;
  price: number | null; change: number | null; change_pct: number | null; prev_close?: number | null;
  as_of_ist?: string | null; delayed?: boolean | null;
  display?: { price?: string | null; change?: string | null; [k: string]: unknown } | null;
}
export interface IntradayPoint { t: string; price: number }
export interface Intraday { symbol: string; interval: string; points: IntradayPoint[]; as_of_ist?: string | null; prev_close?: number | null; currency?: string | null }
