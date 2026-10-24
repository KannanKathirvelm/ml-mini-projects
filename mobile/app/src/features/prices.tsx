import {
  IonAlert, IonBadge, IonButton, IonCard, IonCardContent, IonCardHeader, IonCardSubtitle, IonCardTitle, IonIcon, IonInput, IonItem, IonItemOption,
  IonItemOptions, IonItemSliding, IonLabel, IonList, IonNote, IonToast, useIonViewWillEnter,
} from '@ionic/react';
import { notificationsOutline, pricetagsOutline, searchOutline, star, trashOutline, trendingDownOutline } from 'ionicons/icons';
import React, { useMemo, useState } from 'react';
import { api } from '../api/client';
import type { AlertResult, Offer, PriceHistory, PriceSearch, ProductGroup, TrackedItem } from '../api/types';
import { LineChart } from '../components/Chart';
import { Page } from '../components/Page';
import { AsyncStatus, Empty, ErrorCard } from '../components/Status';
import { inr } from '../components/Widgets';
import { FLAVOR } from '../flavor';
import { useAsync, useLoad } from '../hooks';
import type { FeatureModule } from './types';

const PALETTE = ['#2563eb', '#f97316', '#10b981', '#a855f7', '#ef4444', '#0ea5e9'];
const same = (a: Offer, b: Offer | null) => !!b && a.store === b.store && a.total_inr === b.total_inr && a.title === b.title;

const OfferRow: React.FC<{ o: Offer; best: boolean }> = ({ o, best }) => (
  <div className={`offer ${best ? 'best' : ''}`}>
    <div>
      <strong>{o.store}</strong> {best && <IonBadge color="success">Best deal</IonBadge>}
      <div className="small muted">{o.title}</div>
    </div>
    <div className="price">{inr(o.total_inr)}</div>
    <div className="meta">
      {inr(o.price_inr)} + {o.shipping_inr ? `${inr(o.shipping_inr)} shipping` : 'free shipping'}
      {o.delivery_days !== null && ` · ${o.delivery_days}d delivery`}
      {o.rating !== null && <> · <IonIcon icon={star} /> {o.rating}</>}
      {' · '}<span style={{ color: o.in_stock ? 'var(--ion-color-success)' : 'var(--ion-color-danger)' }}>{o.in_stock ? 'In stock' : 'Out of stock'}</span>
    </div>
  </div>
);

const HistoryChart: React.FC<{ product: string }> = ({ product }) => {
  const h = useLoad<PriceHistory>(() => api.prices.history(product, 30), [product]);
  const chart = useMemo(() => {
    if (!h.data?.series.length) return null;
    const labels = [...new Set(h.data.series.flatMap((s) => s.points.map((p) => p.date)))].sort();
    return {
      labels,
      series: h.data.series.map((s, i) => {
        const m = new Map(s.points.map((p) => [p.date, p.price_inr]));
        return { label: s.store, data: labels.map((d) => m.get(d) ?? null), color: PALETTE[i % PALETTE.length], width: 1.6 };
      }),
    };
  }, [h.data]);
  if (h.loading || h.error) return <AsyncStatus loading={h.loading} slow={h.slow} error={h.error} onRetry={h.reload} loadingLabel="Loading history…" />;
  return chart ? <LineChart labels={chart.labels} series={chart.series} height={200} yLabel="₹" /> : <Empty>No price history yet for this product.</Empty>;
};

const GroupCard: React.FC<{ g: ProductGroup; onTrack: (g: ProductGroup) => void }> = ({ g, onTrack }) => {
  const [hist, setHist] = useState(false);
  return (
    <IonCard>
      <IonCardHeader>
        <IonCardSubtitle>{g.store_count} store{g.store_count === 1 ? '' : 's'}</IonCardSubtitle>
        <IonCardTitle style={{ fontSize: '1.1rem' }}>{g.product}</IonCardTitle>
        {g.best ? (
          <div className="row-center">
            <span className="big-number">{inr(g.best.total_inr)}</span>
            <IonNote>at {g.best.store}</IonNote>
            {g.savings_inr > 0 && <IonBadge color="success">save {inr(g.savings_inr)}</IonBadge>}
          </div>
        ) : <IonNote color="danger">Out of stock everywhere</IonNote>}
      </IonCardHeader>
      <IonCardContent>
        {g.offers.map((o, i) => <OfferRow key={i} o={o} best={same(o, g.best)} />)}
        <div className="button-row">
          <IonButton size="small" fill="outline" onClick={() => setHist((x) => !x)}><IonIcon slot="start" icon={trendingDownOutline} />{hist ? 'Hide history' : 'Price history'}</IonButton>
          <IonButton size="small" onClick={() => onTrack(g)}><IonIcon slot="start" icon={notificationsOutline} />Track</IonButton>
        </div>
        {hist && <HistoryChart product={g.product} />}
      </IonCardContent>
    </IonCard>
  );
};

const SearchPage: React.FC = () => {
  const [q, setQ] = useState('iphone');
  const res = useAsync<PriceSearch>();
  const [trackFor, setTrackFor] = useState<ProductGroup | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const go = () => q.trim() && res.run(() => api.prices.search(q.trim()));
  const track = async (g: ProductGroup, target: number) => {
    try {
      const t = await api.prices.track(g.product, target);
      setToast(`Tracking ${t.product} at ${inr(t.target_inr)}${t.hit ? ' (already below target!)' : ''}`);
    } catch (e) { setToast(`Couldn't track: ${(e as Error).message}`); }
  };
  return (
    <Page title={FLAVOR.appName} onRefresh={() => (q.trim() ? go() : undefined)}>
      <IonCard>
        <IonCardContent>
          <IonList lines="full">
            <IonItem>
              <IonInput label="Search products" labelPlacement="stacked" value={q} placeholder="iphone, headphones, jacket…"
                onIonInput={(e) => setQ(String(e.detail.value ?? ''))} onKeyDown={(e) => e.key === 'Enter' && go()} />
              <IonButton slot="end" onClick={go} disabled={res.loading || !q.trim()}><IonIcon icon={searchOutline} /></IonButton>
            </IonItem>
          </IonList>
        </IonCardContent>
      </IonCard>
      <AsyncStatus loading={res.loading} slow={res.slow} error={res.error} onRetry={go} loadingLabel="Comparing stores…" />
      {res.data && !res.loading && (
        <>
          <IonNote className="small">Stores searched: {res.data.stores_ok.join(', ') || 'none'}</IonNote>
          {res.data.warnings.map((w, i) => <IonNote key={i} color="warning" className="small">{w}</IonNote>)}
          {res.data.groups.length === 0 && <Empty>No products found for “{res.data.query}”.</Empty>}
          {res.data.groups.map((g) => <GroupCard key={g.product} g={g} onTrack={setTrackFor} />)}
        </>
      )}
      {!res.data && !res.loading && !res.error && <Empty>Search to compare prices across stores.</Empty>}
      <IonAlert isOpen={!!trackFor} header="Track price" subHeader={trackFor?.product}
        message="Alert me when the best price is at or below:"
        inputs={[{ name: 'target', type: 'number', placeholder: 'Target ₹', value: trackFor?.best ? Math.round(trackFor.best.total_inr * 0.95) : '' }]}
        buttons={[{ text: 'Cancel', role: 'cancel' }, {
          text: 'Track', handler: (v: { target: string }) => { const n = Number(v.target); if (trackFor && n > 0) track(trackFor, n); else return false; },
        }]}
        onDidDismiss={() => setTrackFor(null)} />
      <IonToast isOpen={!!toast} message={toast ?? ''} duration={2500} onDidDismiss={() => setToast(null)} />
    </Page>
  );
};

const TrackedPage: React.FC = () => {
  const list = useAsync<TrackedItem[]>();
  const alerts = useAsync<AlertResult[]>();
  const load = () => list.run(() => api.prices.tracked());
  useIonViewWillEnter(() => { load(); });
  const remove = async (p: string) => { try { await api.prices.untrack(p); } finally { load(); } };
  return (
    <Page title="Tracked" onRefresh={load}>
      <IonButton expand="block" onClick={() => alerts.run(() => api.prices.checkAlerts())} disabled={alerts.loading}>
        <IonIcon slot="start" icon={notificationsOutline} />Check alerts now
      </IonButton>
      <AsyncStatus loading={alerts.loading} slow={alerts.slow} error={alerts.error} loadingLabel="Checking current prices…" />
      {alerts.data && (
        <IonCard>
          <IonCardHeader><IonCardSubtitle>Alert check</IonCardSubtitle></IonCardHeader>
          <IonCardContent>
            {alerts.data.length === 0 && <Empty>Nothing tracked.</Empty>}
            {alerts.data.map((a) => (
              <div key={a.product} className="offer">
                <div><strong>{a.product}</strong><div className="small muted">target {inr(a.target_inr)}</div></div>
                <div className="price">{a.hit ? <IonBadge color="success">HIT {inr(a.best_inr)}</IonBadge> : <IonBadge color="medium">{inr(a.best_inr)}</IonBadge>}</div>
                <div className="meta">{a.store ? `best at ${a.store}` : 'no in-stock offer'}</div>
              </div>
            ))}
          </IonCardContent>
        </IonCard>
      )}
      {list.loading && !list.data && <AsyncStatus loading slow={list.slow} error={null} />}
      {list.error && <ErrorCard error={list.error} onRetry={load} />}
      {list.data && list.data.length === 0 && <Empty>No tracked products yet. Search and tap “Track”.</Empty>}
      {list.data && list.data.length > 0 && (
        <IonList inset>
          {list.data.map((t) => (
            <IonItemSliding key={t.product}>
              <IonItem>
                <IonLabel>
                  <h2>{t.product}</h2>
                  <p>Target {inr(t.target_inr)} · best {inr(t.latest_best_inr)}{t.latest_store ? ` at ${t.latest_store}` : ''}</p>
                </IonLabel>
                <IonBadge slot="end" color={t.hit ? 'success' : 'medium'}>{t.hit ? 'Below target' : 'Waiting'}</IonBadge>
                <IonButton slot="end" fill="clear" color="danger" onClick={() => remove(t.product)} aria-label="Stop tracking"><IonIcon icon={trashOutline} /></IonButton>
              </IonItem>
              <IonItemOptions side="end"><IonItemOption color="danger" onClick={() => remove(t.product)}>Remove</IonItemOption></IonItemOptions>
            </IonItemSliding>
          ))}
        </IonList>
      )}
    </Page>
  );
};

const mod: FeatureModule = {
  tabs: [
    { path: '/search', label: 'Compare', icon: pricetagsOutline, component: SearchPage },
    { path: '/tracked', label: 'Tracked', icon: notificationsOutline, component: TrackedPage },
  ],
};
export default mod;
