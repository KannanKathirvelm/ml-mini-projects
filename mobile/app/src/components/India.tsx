import { IonButton, IonChip, IonIcon, IonItem, IonLabel, IonList, IonNote, IonSearchbar } from '@ionic/react';
import { arrowForward, ellipse } from 'ionicons/icons';
import React, { useEffect, useRef, useState } from 'react';
import { ApiError, api } from '../api/client';
import { BUILTIN_POPULAR } from '../api/mock';
import type { IndiaInstrument, IndiaPopular, IndiaSearchResult } from '../api/types';
import { useLoad } from '../hooks';
import { useMarketStatus } from './Live';
import { fmtIst } from './Widgets';

/** NSE open/closed pill. Hidden entirely if the endpoint is missing or fails. */
export const MarketStatusPill: React.FC<{ refreshKey?: number }> = ({ refreshKey }) => {
  const { data: d, refresh } = useMarketStatus();
  useEffect(() => { if (refreshKey) refresh(); }, [refreshKey]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!d) return null;
  const open = typeof d.is_open === 'boolean' ? d.is_open : /open/i.test(String(d.status ?? d.label ?? ''));
  const next = fmtIst(open ? d.next_close_ist ?? d.next_close : d.next_open_ist ?? d.next_open, true);
  const label = `${d.exchange ?? 'NSE'} ${open ? 'Open' : 'Closed'}`;
  const detail = d.message ?? (next ? `${open ? 'closes' : 'opens'} ${next}` : null);
  return (
    <div className="market-pill" role="status">
      <IonChip color={open ? 'success' : 'medium'} outline={!open}>
        <IonIcon icon={ellipse} style={{ fontSize: 10 }} />
        <IonLabel><strong>{label}</strong>{detail ? ` · ${detail}` : ''}</IonLabel>
      </IonChip>
      {d.note && <IonNote className="small">{d.note}</IonNote>}
    </div>
  );
};

/** "Popular Indian stocks" chips from /api/india/popular, falling back to a built-in list. */
export const PopularIndian: React.FC<{ selected?: string; onPick: (symbol: string) => void }> = ({ selected, onPick }) => {
  const p = useLoad<IndiaPopular>(() => api.india.popular());
  const [all, setAll] = useState(false);
  const data: IndiaPopular = {
    indices: p.data?.indices?.length ? p.data.indices : BUILTIN_POPULAR.indices,
    stocks: p.data?.stocks?.length ? p.data.stocks : BUILTIN_POPULAR.stocks,
  };
  const chip = (i: IndiaInstrument) => {
    const on = selected?.toUpperCase() === i.symbol.toUpperCase();
    return (
      <IonChip key={i.symbol} color={on ? 'primary' : undefined} outline={!on} onClick={() => onPick(i.symbol)} title={i.sector ?? undefined}>
        <IonLabel>{i.name ?? i.symbol}{i.name && !i.symbol.startsWith('^') ? <span className="muted small-inline"> {i.symbol.replace(/\.(NS|BO)$/, '')}</span> : null}</IonLabel>
      </IonChip>
    );
  };
  return (
    <div>
      <IonNote className="small">Indices</IonNote>
      <div className="chip-row">{data.indices.map(chip)}</div>
      <IonNote className="small">Popular Indian stocks{p.error ? ' (built-in list)' : ''}</IonNote>
      <div className="chip-row">
        {(all ? data.stocks : data.stocks.slice(0, 6)).map(chip)}
        {data.stocks.length > 6 && (
          <IonChip color="primary" onClick={() => setAll((x) => !x)}><IonLabel>{all ? 'Less' : `+${data.stocks.length - 6} more`}</IonLabel></IonChip>
        )}
      </div>
    </div>
  );
};

/**
 * Ticker search: debounced (300 ms) type-ahead over all NSE listings via /api/india/search.
 * Enter submits the raw text (the server normalises "reliance" -> RELIANCE.NS, "nifty" -> ^NSEI).
 * If the search endpoint is missing, it silently behaves as a plain free-text box.
 */
export const TickerSearch: React.FC<{ onPick: (symbol: string) => void; placeholder?: string; busy?: boolean; onAdd?: (symbol: string) => void; isAdded?: (symbol: string) => boolean }> = ({ onPick, placeholder, busy, onAdd, isAdded }) => {
  const [text, setText] = useState('');
  const [results, setResults] = useState<IndiaSearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [unavailable, setUnavailable] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout>>();
  const ctrl = useRef<AbortController>();

  useEffect(() => {
    clearTimeout(timer.current);
    const q = text.trim();
    if (q.length < 2 || unavailable) { setResults([]); return; }
    timer.current = setTimeout(async () => {
      ctrl.current?.abort();
      const c = new AbortController(); ctrl.current = c;
      setSearching(true);
      try {
        const r = await api.india.search(q, 10, c.signal);
        if (!c.signal.aborted) setResults(r.results ?? []);
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) setUnavailable(true);
        if (!c.signal.aborted) setResults([]);
      } finally { if (!c.signal.aborted) setSearching(false); }
    }, 300);
    return () => clearTimeout(timer.current);
  }, [text, unavailable]);

  const pick = (s: string) => { setText(''); setResults([]); onPick(s); };
  const submit = () => { const t = text.trim(); if (t) pick(t); };

  return (
    <div className="ticker-search">
      <div className="row-center">
        <IonSearchbar value={text} debounce={0} placeholder={placeholder ?? 'Search any NSE stock, or type a symbol'} inputmode="search" enterkeyhint="go"
          showClearButton="focus" onIonInput={(e) => setText(String(e.detail.value ?? ''))} onKeyDown={(e) => e.key === 'Enter' && submit()} />
        <IonButton onClick={submit} disabled={!text.trim() || busy} aria-label="Load ticker"><IonIcon icon={arrowForward} /></IonButton>
      </div>
      {searching && <IonNote className="small">Searching…</IonNote>}
      {results.length > 0 && (
        <IonList lines="full" className="search-results">
          {results.map((r) => (
            <IonItem key={r.symbol} button detail={false} onClick={() => pick(r.symbol)}>
              <IonLabel>
                <strong>{r.nse_symbol ?? r.symbol.replace(/\.(NS|BO)$/, '')}</strong>{r.name ? ` · ${r.name}` : ''}
              </IonLabel>
              {onAdd && (
                <IonButton slot="end" fill="clear" size="small" disabled={isAdded?.(r.symbol)} aria-label={`Add ${r.symbol} to watchlist`}
                  onClick={(e) => { e.stopPropagation(); onAdd(r.symbol); }}>{isAdded?.(r.symbol) ? '✓' : '＋'}</IonButton>
              )}
            </IonItem>
          ))}
        </IonList>
      )}
      {!searching && text.trim().length >= 2 && results.length === 0 && !unavailable && (
        <IonNote className="small">No listed match. Press Go to try “{text.trim()}” as a symbol.</IonNote>
      )}
    </div>
  );
};
