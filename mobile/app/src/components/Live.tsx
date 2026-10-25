import { Preferences } from '@capacitor/preferences';
import {
  IonButton, IonCard, IonCardContent, IonCardHeader, IonCardSubtitle, IonIcon, IonItem, IonItemOption, IonItemOptions,
  IonItemSliding, IonLabel, IonList, IonNote, IonSegment, IonSegmentButton,
} from '@ionic/react';
import { caretDown, caretUp, closeCircleOutline } from 'ionicons/icons';
import React, { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import { ApiError, api } from '../api/client';
import { live } from '../api/live';
import type { Intraday, MarketStatus, Quote } from '../api/types';
import { LineChart } from './Chart';
import { currencyOf, fmtIst, istToday, money } from './Widgets';

// ---------- market status (shared, refreshed every 5 min) ----------
let statusCache: { data: MarketStatus | null; at: number } = { data: null, at: 0 };
const statusSubs = new Set<() => void>();
async function refreshStatus(force = false) {
  if (!force && Date.now() - statusCache.at < 300_000 && statusCache.at) return;
  statusCache = { ...statusCache, at: Date.now() };
  try { statusCache = { data: await api.india.marketStatus(), at: Date.now() }; } catch { statusCache = { data: null, at: Date.now() }; }
  statusSubs.forEach((f) => f());
}
export const isOpen = (d: MarketStatus | null) =>
  !d ? null : typeof d.is_open === 'boolean' ? d.is_open : /open/i.test(String(d.status ?? d.label ?? ''));
export function useMarketStatus() {
  const data = useSyncExternalStore((cb) => { statusSubs.add(cb); return () => statusSubs.delete(cb); }, () => statusCache.data);
  useEffect(() => { refreshStatus(); const i = setInterval(() => refreshStatus(), 300_000); return () => clearInterval(i); }, []);
  return { data, open: isOpen(data), refresh: () => refreshStatus(true) };
}

// ---------- foreground-aware polling ----------
function useVisible() {
  const [v, setV] = useState(() => typeof document === 'undefined' || document.visibilityState === 'visible');
  useEffect(() => {
    const f = () => setV(document.visibilityState === 'visible');
    document.addEventListener('visibilitychange', f); // Capacitor's WebView fires this on app pause/resume
    return () => document.removeEventListener('visibilitychange', f);
  }, []);
  return v;
}
/** Calls fn every `ms` while enabled and the app is in the foreground. */
export function usePoll(fn: () => void, ms: number, enabled: boolean) {
  const visible = useVisible();
  const ref = useRef(fn); ref.current = fn;
  useEffect(() => {
    if (!enabled || !visible) return;
    const i = setInterval(() => ref.current(), ms);
    return () => clearInterval(i);
  }, [enabled, visible, ms]);
}

// ---------- live quote header ----------
const sign = (x: number) => (x > 0 ? '+' : '');
export const ChangeText: React.FC<{ q: Quote; cur: string }> = ({ q, cur }) => {
  if (q.change === null && q.change_pct === null) return null;
  const up = (q.change ?? q.change_pct ?? 0) >= 0;
  return (
    <span className={up ? 'chg up' : 'chg down'}>
      <IonIcon icon={up ? caretUp : caretDown} />
      {q.display?.change ?? (q.change !== null ? `${sign(q.change)}${money(q.change, cur).replace(/^([₹$])-/, '-$1')}` : '')}
      {q.change_pct !== null && !String(q.display?.change ?? '').includes('%') ? ` (${sign(q.change_pct)}${q.change_pct.toFixed(2)}%)` : ''}
    </span>
  );
};

/** Reloads when `refreshKey` changes (the page's pull-to-refresh bumps it). */
export const QuoteHeader: React.FC<{ ticker: string; refreshKey?: number }> = ({ ticker, refreshKey }) => {
  const { open } = useMarketStatus();
  const [q, setQ] = useState<Quote | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [missing, setMissing] = useState(false);
  const load = useCallback(async () => {
    try { setQ(await live.quote(ticker)); setErr(null); } catch (e) {
      if (e instanceof ApiError && e.status === 404 && /not found/i.test(e.message)) setMissing(true); // endpoint absent
      else setErr((e as Error).message);
    }
  }, [ticker]);
  useEffect(() => { setQ(null); setErr(null); load(); }, [load]);
  useEffect(() => { if (refreshKey) { load(); refreshStatus(true); } }, [refreshKey]); // eslint-disable-line react-hooks/exhaustive-deps
  const polling = open === true || q?.market_open === true;
  usePoll(load, 30_000, polling);
  if (missing) return null;
  const cur = currencyOf(ticker, q?.currency);
  return (
    <IonCard className="quote-card">
      <IonCardContent>
        <div className="quote-top">
          <div>
            <div className="quote-name">{q?.name ?? ticker}</div>
            <IonNote className="small">{q?.symbol ?? ticker}</IonNote>
          </div>
          <MarketPillInline />
        </div>
        {q && q.price !== null ? (
          <>
            <div className="quote-price">{q.display?.price ?? money(q.price, cur)}</div>
            <ChangeText q={q} cur={cur} />
            {(q.high !== null && q.high !== undefined) || (q.low !== null && q.low !== undefined) ? (
              <IonNote className="small quote-range">Day range {money(q.low, cur)} – {money(q.high, cur)}{q.open !== null && q.open !== undefined ? ` · open ${money(q.open, cur)}` : ''}</IonNote>
            ) : null}
            <IonNote className="small" title={q.delayed_note ?? undefined}>
              {q.as_of_ist ? `as of ${fmtIst(q.as_of_ist)}` : 'latest'} · {q.source ?? 'may be delayed'}{polling ? ' · refreshes every 30 s' : ''}
            </IonNote>
          </>
        ) : err ? <IonNote color="danger" className="small">Live quote unavailable: {err}</IonNote> : <IonNote className="small">Loading live quote…</IonNote>}
      </IonCardContent>
    </IonCard>
  );
};

export const MarketPillInline: React.FC = () => {
  const { data, open } = useMarketStatus();
  if (!data) return null;
  const next = fmtIst(open ? data.next_close_ist ?? data.next_close : data.next_open_ist ?? data.next_open, true);
  return (
    <div className={`pill ${open ? 'open' : 'closed'}`} title={next ? `${open ? 'Closes' : 'Opens'} ${next}` : undefined}>
      <span className="dot" />{data.exchange ?? 'NSE'} {open ? 'Open' : 'Closed'}
      {next && <span className="pill-sub">{open ? 'closes' : 'opens'} {next}</span>}
    </div>
  );
};

// ---------- intraday chart ----------
const sessionLabel = (d: Intraday | null) => {
  if (!d?.session_date || d.session_date === istToday()) return 'Today';
  return `Last session ${fmtIst(`${d.session_date}T00:00`)?.replace(/, 00:00 IST$/, '')}`;
};

export const IntradayCard: React.FC<{ ticker: string; refreshKey?: number }> = ({ ticker, refreshKey }) => {
  const { open } = useMarketStatus();
  const [interval, setIntervalV] = useState<'1m' | '5m'>('5m');
  const [d, setD] = useState<Intraday | null>(null);
  const [missing, setMissing] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const load = useCallback(async () => {
    try { setD(await live.intraday(ticker, interval)); setErr(null); } catch (e) {
      if (e instanceof ApiError && e.status === 404 && /not found/i.test(e.message)) setMissing(true);
      else setErr((e as Error).message);
    }
  }, [ticker, interval]);
  useEffect(() => { setD(null); load(); }, [load]);
  useEffect(() => { if (refreshKey) { load(); refreshStatus(true); } }, [refreshKey]); // eslint-disable-line react-hooks/exhaustive-deps
  usePoll(load, 60_000, open === true || d?.market_open === true);
  const chart = useMemo(() => {
    if (!d?.points.length) return null;
    const labels = d.points.map((p) => (p.t.length > 8 ? p.t.slice(11, 16) || p.t : p.t));
    const series = [{ label: 'Price', data: d.points.map((p) => p.price), color: '#0ea5e9', width: 1.8, fill: true }];
    if (d.prev_close) series.push({ label: 'Prev close', data: d.points.map(() => d.prev_close!), color: '#94a3b8', width: 1, fill: false, dashed: true } as never);
    return { labels, series };
  }, [d]);
  if (missing) return null;
  return (
    <IonCard>
      <IonCardHeader>
        <div className="agent-head">
          <IonCardSubtitle>{sessionLabel(d)}{d?.as_of_ist ? ` · as of ${fmtIst(d.as_of_ist)}` : ''}</IonCardSubtitle>
          <IonSegment value={interval} onIonChange={(e) => setIntervalV(e.detail.value as '1m' | '5m')} style={{ width: 120 }}>
            <IonSegmentButton value="1m"><IonLabel>1m</IonLabel></IonSegmentButton>
            <IonSegmentButton value="5m"><IonLabel>5m</IonLabel></IonSegmentButton>
          </IonSegment>
        </div>
      </IonCardHeader>
      <IonCardContent>
        {chart ? <LineChart labels={chart.labels} series={chart.series} height={180} />
          : err ? <IonNote color="danger" className="small">{err}</IonNote>
            : <IonNote className="small">{d ? 'No trades yet today.' : 'Loading intraday…'}</IonNote>}
        {d?.source && <IonNote className="small">{d.source}</IonNote>}
      </IonCardContent>
    </IonCard>
  );
};

// ---------- watchlist ----------
const WL_KEY = 'mlapps.watchlist.v1';
export const DEFAULT_WATCHLIST = ['^NSEI', 'RELIANCE.NS', 'TCS.NS', 'HDFCBANK.NS', 'INFY.NS', 'ICICIBANK.NS'];
let wl: string[] = DEFAULT_WATCHLIST;
let wlLoaded = false;
const wlSubs = new Set<() => void>();
const wlSet = (next: string[]) => { wl = next; Preferences.set({ key: WL_KEY, value: JSON.stringify(next) }); wlSubs.forEach((f) => f()); };
export function useWatchlist() {
  const list = useSyncExternalStore((cb) => { wlSubs.add(cb); return () => wlSubs.delete(cb); }, () => wl);
  useEffect(() => {
    if (wlLoaded) return; wlLoaded = true;
    Preferences.get({ key: WL_KEY }).then(({ value }) => { if (value) { try { wl = JSON.parse(value); wlSubs.forEach((f) => f()); } catch { /* ignore */ } } });
  }, []);
  return {
    list,
    add: (s: string) => { const S = s.trim(); if (S && !wl.some((x) => x.toUpperCase() === S.toUpperCase())) wlSet([...wl, S]); },
    remove: (s: string) => wlSet(wl.filter((x) => x !== s)),
    has: (s: string) => wl.some((x) => x.toUpperCase() === s.toUpperCase()),
  };
}

export const WatchlistCard: React.FC<{ onOpen: (s: string) => void; refreshKey?: number }> = ({ onOpen, refreshKey }) => {
  const { list, remove } = useWatchlist();
  const { open } = useMarketStatus();
  const [quotes, setQuotes] = useState<Record<string, Quote>>({});
  const [failed, setFailed] = useState<Record<string, string>>({});
  const [missing, setMissing] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const load = useCallback(async () => {
    if (!list.length) return;
    try {
      const { quotes: qs, errors } = await live.quotes(list);
      const m: Record<string, Quote> = {};
      qs.forEach((q) => { m[q.symbol.toUpperCase()] = q; });
      // The server echoes the normalised symbol ("reliance" -> RELIANCE.NS); map typed entries onto it.
      list.forEach((s) => { const S = s.toUpperCase(); if (!m[S] && m[`${S}.NS`]) m[S] = m[`${S}.NS`]; });
      const f: Record<string, string> = {};
      errors.forEach((e) => { f[e.symbol.toUpperCase()] = e.detail; });
      setQuotes(m); setFailed(f); setErr(null);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404 && /not found/i.test(e.message)) setMissing(true);
      else setErr((e as Error).message);
    }
  }, [list]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (refreshKey) { load(); refreshStatus(true); } }, [refreshKey]); // eslint-disable-line react-hooks/exhaustive-deps
  usePoll(load, 30_000, open === true);
  return (
    <IonCard>
      <IonCardHeader><IonCardSubtitle>Watchlist{missing ? ' (live prices not available on this server)' : ''}</IonCardSubtitle></IonCardHeader>
      <IonCardContent className="tight-content">
        {err && <IonNote color="danger" className="small">{err}</IonNote>}
        {list.length === 0 && <IonNote className="small">Empty. Search a stock and tap ＋ to add it.</IonNote>}
        <IonList lines="full">
          {list.map((s) => {
            const q = quotes[s.toUpperCase()];
            const cur = currencyOf(s, q?.currency);
            return (
              <IonItemSliding key={s}>
                <IonItem button detail={false} onClick={() => onOpen(s)}>
                  <IonLabel>
                    <h3>{q?.name && q.name !== s ? q.name : s.replace(/\.(NS|BO)$/, '')}</h3>
                    <p>{s}</p>
                  </IonLabel>
                  <div slot="end" className="wl-right">
                    <div className="wl-price" title={failed[s.toUpperCase()]}>{q && q.price !== null ? q.display?.price ?? money(q.price, cur) : missing ? '' : failed[s.toUpperCase()] ? 'n/a' : '…'}</div>
                    {q && <ChangeText q={q} cur={cur} />}
                  </div>
                  <IonButton slot="end" fill="clear" color="medium" size="small" aria-label={`Remove ${s}`} onClick={(e) => { e.stopPropagation(); remove(s); }}>
                    <IonIcon icon={closeCircleOutline} />
                  </IonButton>
                </IonItem>
                <IonItemOptions side="end"><IonItemOption color="danger" onClick={() => remove(s)}>Remove</IonItemOption></IonItemOptions>
              </IonItemSliding>
            );
          })}
        </IonList>
      </IonCardContent>
    </IonCard>
  );
};

// ---------- shared ticker selection across tabs ----------
let currentTicker = 'RELIANCE.NS';
const tickerSubs = new Set<() => void>();
export function useSelectedTicker(): [string, (t: string) => void] {
  const t = useSyncExternalStore((cb) => { tickerSubs.add(cb); return () => tickerSubs.delete(cb); }, () => currentTicker);
  return [t, (v: string) => { currentTicker = v; tickerSubs.forEach((f) => f()); }];
}
