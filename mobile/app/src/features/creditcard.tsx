import { IonButton, IonCard, IonCardContent, IonCardHeader, IonCardSubtitle, IonCardTitle, IonIcon, IonList, IonText } from '@ionic/react';
import { alertCircle, barChartOutline, cardOutline, checkmarkCircle } from 'ionicons/icons';
import React, { useState } from 'react';
import { api } from '../api/client';
import type { CardInput, CardMeta, CardResult } from '../api/types';
import { NumField, RangeField, SelectField, Toggle01 } from '../components/Form';
import { MetricsCard } from '../components/MetricsCard';
import { Page } from '../components/Page';
import { AsyncStatus } from '../components/Status';
import { ProbabilityGauge, titleCase } from '../components/Widgets';
import { FLAVOR } from '../flavor';
import { useAsync, useLoad } from '../hooks';
import type { FeatureModule } from './types';

const DEFAULTS: CardInput = {
  amount: 950, hour: 2, distance_from_home_km: 400, distance_from_last_txn_km: 300, ratio_to_median_amount: 6,
  online_order: 1, used_chip: 0, used_pin: 0, txn_count_last_24h: 8, merchant_category: 'electronics',
};
const NORMAL: CardInput = { ...DEFAULTS, amount: 42, hour: 13, distance_from_home_km: 3, distance_from_last_txn_km: 2, ratio_to_median_amount: 0.9, online_order: 0, used_chip: 1, used_pin: 1, txn_count_last_24h: 2, merchant_category: 'grocery' };

const CheckPage: React.FC = () => {
  const meta = useLoad<CardMeta>(() => api.card.meta());
  const [f, setF] = useState<CardInput>(DEFAULTS);
  const res = useAsync<CardResult>();
  const set = <K extends keyof CardInput>(k: K) => (v: CardInput[K]) => setF((p) => ({ ...p, [k]: v }));
  const cats = meta.data?.categories ?? [];

  return (
    <Page title={FLAVOR.appName} onRefresh={meta.reload}>
      <AsyncStatus loading={meta.loading} slow={meta.slow} error={meta.error} onRetry={meta.reload} loadingLabel="Loading merchant categories…" />
      <IonCard>
        <IonCardHeader><IonCardSubtitle>Transaction</IonCardSubtitle></IonCardHeader>
        <IonCardContent>
          <div className="chip-row">
            <IonButton size="small" fill="outline" onClick={() => { setF(DEFAULTS); res.reset(); }}>Suspicious example</IonButton>
            <IonButton size="small" fill="outline" onClick={() => { setF(NORMAL); res.reset(); }}>Normal example</IonButton>
          </div>
          <IonList className="form-grid" lines="full">
            <NumField label="Amount" value={f.amount} onChange={set('amount')} min={0} />
            <RangeField label="Hour of day" value={f.hour} onChange={set('hour')} min={0} max={23} step={1} format={(v) => `${v}:00`} />
            {cats.length > 0 && (
              <SelectField label="Merchant category" value={f.merchant_category} onChange={set('merchant_category')}
                options={cats.map((c) => ({ value: c, label: titleCase(c) }))} />
            )}
            <NumField label="Distance from home (km)" value={f.distance_from_home_km} onChange={set('distance_from_home_km')} min={0} />
            <NumField label="Distance from last transaction (km)" value={f.distance_from_last_txn_km} onChange={set('distance_from_last_txn_km')} min={0} />
            <NumField label="Ratio to median amount" value={f.ratio_to_median_amount} onChange={set('ratio_to_median_amount')} min={0} step={0.1} helper="This amount ÷ the cardholder's median purchase" />
            <NumField label="Transactions in last 24 h" value={f.txn_count_last_24h} onChange={set('txn_count_last_24h')} min={0} step={1} />
            <Toggle01 label="Online order" value={f.online_order} onChange={set('online_order')} />
            <Toggle01 label="Used chip" value={f.used_chip} onChange={set('used_chip')} />
            <Toggle01 label="Used PIN" value={f.used_pin} onChange={set('used_pin')} />
          </IonList>
          <IonButton expand="block" className="ion-margin-top" disabled={res.loading || cats.length === 0}
            onClick={() => res.run(() => api.card.predict(f))}>Check transaction</IonButton>
        </IonCardContent>
      </IonCard>
      <AsyncStatus loading={res.loading} slow={res.slow} error={res.error} loadingLabel="Scoring…" />
      {res.data && <ResultCard r={res.data} />}
    </Page>
  );
};

const ResultCard: React.FC<{ r: CardResult }> = ({ r }) => (
  <IonCard>
    <IonCardHeader><IonCardSubtitle>Fraud probability</IonCardSubtitle></IonCardHeader>
    <IonCardContent>
      <ProbabilityGauge value={r.fraud_probability} threshold={r.threshold} />
      <IonText color={r.flagged ? 'danger' : 'success'}>
        <div className="verdict">
          <IonIcon icon={r.flagged ? alertCircle : checkmarkCircle} />
          {r.flagged ? 'Likely fraud: block or verify with the cardholder' : 'Looks legitimate'}
        </div>
      </IonText>
    </IonCardContent>
  </IonCard>
);

const MetricsPage: React.FC = () => {
  const meta = useLoad<CardMeta>(() => api.card.meta());
  return (
    <Page title="Model metrics" onRefresh={meta.reload}>
      <AsyncStatus loading={meta.loading} slow={meta.slow} error={meta.error} onRetry={meta.reload} />
      {meta.data && <MetricsCard metrics={meta.data.metrics} threshold={meta.data.threshold} />}
      <IonCard>
        <IonCardHeader><IonCardTitle>About</IonCardTitle></IonCardHeader>
        <IonCardContent>
          A classifier trained on a synthetic card-transaction dataset with heavy class imbalance. The threshold was tuned on validation data
          to balance catching fraud (recall) against false alarms (precision), so a probability of 35% can already be flagged.
        </IonCardContent>
      </IonCard>
    </Page>
  );
};

const mod: FeatureModule = {
  tabs: [
    { path: '/check', label: 'Check', icon: cardOutline, component: CheckPage },
    { path: '/metrics', label: 'Metrics', icon: barChartOutline, component: MetricsPage },
  ],
};
export default mod;
